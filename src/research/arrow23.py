from __future__ import annotations

import math
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _summarize
from research.arrow18 import load_iwm
from research.arrow19 import CLOCK_0800, CLOCK_0929, _last_at_or_before, _pack
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.rockets import median_prior_window
from research.signals import MINUTE_1100, MINUTE_1159, MINUTE_1559
from research.split import develop_holdout
from research.strategies20 import STOP_MIN_FRAC
from research.strategies22 import hot_gate_0800
from research.strategies23 import (
    afternoon_break_long,
    climax_short,
    coil_break_long,
    coil_range_ok,
    failed_rocket_short,
    flush_higher_low_long,
    holds_vs_iwm_long,
    session_high_before,
)

ET = ZoneInfo("America/New_York")

CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": STOP_MIN_FRAC,
}

IDS = (
    "coil_break",
    "am_high_pm",
    "fail_rocket",
    "flush_hl",
    "vs_iwm",
    "climax",
)
FLATTEN = {
    "coil_break": MINUTE_1159,
    "am_high_pm": MINUTE_1559,
    "fail_rocket": MINUTE_1159,
    "flush_hl": MINUTE_1159,
    "vs_iwm": MINUTE_1159,
    "climax": MINUTE_1159,
}


def _pre_both(pack: dict) -> dict | None:
    i8, dv8 = _last_at_or_before(pack, CLOCK_0800)
    i9, dv9 = _last_at_or_before(pack, CLOCK_0929)
    if i9 is None:
        return None
    highs = pack["high"][: i9 + 1]
    lows = pack["low"][: i9 + 1]
    return {
        "dv0800": dv8 if i8 is not None else None,
        "last_px_0800": pack["close"][i8] if i8 is not None else None,
        "last_ts_0800": pack["ts"][i8] if i8 is not None else None,
        "dv0929": dv9,
        "last_px_0929": pack["close"][i9],
        "last_ts_0929": pack["ts"][i9],
        "pre_high": max(highs) if highs else None,
        "pre_low": min(lows) if lows else None,
    }


def _session_pre(args: tuple) -> tuple[str, dict[str, dict]]:
    d, want = args
    iso = d.isoformat()
    folder = FULL_BARS / iso
    out: dict[str, dict] = {}
    if not folder.exists():
        return iso, out
    for path in folder.glob("*.parquet"):
        try:
            df = pl.read_parquet(path)
        except Exception:  # noqa: BLE001
            continue
        if df.height == 0:
            continue
        sym = str(df["symbol"][0]) if "symbol" in df.columns else path.stem.lstrip("_")
        if want is not None and sym not in want:
            continue
        pack = _pack(df)
        if pack is None:
            continue
        st = _pre_both(pack)
        if st is None:
            continue
        out[sym] = st
    return iso, out


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = (p / 100.0) * (len(ys) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    w = pos - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def _flight(df: pl.DataFrame | None, trade) -> tuple[float, bool]:
    if df is None or df.height == 0 or trade.entry_px <= 0 or trade.shares < 1:
        return 0.0, False
    stop_dist = trade.risk / trade.shares if trade.shares else 0.0
    times = df["bar_start"].to_list()
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    fav = 0.0
    for ts, h, l in zip(times, highs, lows):
        if ts < trade.entry_ts:
            continue
        if ts >= trade.exit_ts:
            break
        if trade.side > 0:
            fav = max(fav, float(h) - trade.entry_px)
        else:
            fav = max(fav, trade.entry_px - float(l))
    ext = fav / trade.entry_px
    reached = stop_dist > 0 and fav >= stop_dist - 1e-12
    return ext, reached


def _pack_trades(trades, bars: dict[str, pl.DataFrame]) -> list[dict]:
    out = []
    for t in trades:
        mfe_ext, reached = _flight(bars.get(t.symbol), t)
        minutes = (t.exit_ts - t.entry_ts).total_seconds() / 60.0
        r = t.pnl / t.risk if t.risk else 0.0
        out.append(
            {
                "pnl": t.pnl,
                "win": t.pnl > 0,
                "risk": t.risk,
                "tag": t.tag,
                "side": t.side,
                "minutes": minutes,
                "r": r,
                "mfe_ext": mfe_ext,
                "reached_1r": reached,
            }
        )
    return out


def _signals_for(exp_id: str, names: list[dict], bars: dict, iwm) -> tuple[list, int]:
    sigs = []
    skips = 0
    for h in names:
        sdf = bars.get(h["symbol"])
        if sdf is None or sdf.height == 0:
            continue
        if exp_id == "coil_break":
            sigs.extend(coil_break_long(sdf, h["pre_high"], h["pre_low"]))
        elif exp_id == "am_high_pm":
            am_high = session_high_before(sdf, MINUTE_1100)
            sigs.extend(afternoon_break_long(sdf, am_high))
        elif exp_id == "fail_rocket":
            sigs.extend(failed_rocket_short(sdf))
        elif exp_id == "flush_hl":
            sigs.extend(flush_higher_low_long(sdf, h.get("last_px_0800")))
        elif exp_id == "vs_iwm":
            got, nskip = holds_vs_iwm_long(sdf, iwm)
            sigs.extend(got)
            skips += nskip
        elif exp_id == "climax":
            sigs.extend(climax_short(sdf))
    if exp_id in ("fail_rocket", "climax"):
        sigs = [s for s in sigs if s.side == -1]
    else:
        sigs = [s for s in sigs if s.side == 1]
    return sigs, skips


def _replay_one(args: tuple) -> dict:
    session_iso, feats, prior_dv, iwm = args
    session = date.fromisoformat(session_iso)
    empty_rows = [
        {
            "session": session_iso,
            "name": n,
            "pnl": 0.0,
            "trades": [],
            "iwm_skips": 0,
        }
        for n in IDS
    ]
    empty = {
        "session": session_iso,
        "n_coil": 0,
        "n_0800": 0,
        "n_cand": 0,
        "rows": empty_rows,
    }
    if not feats:
        return empty
    symbols = [h["symbol"] for h in feats]
    bars = _read_hot_bars(session, symbols)
    rows = []
    for exp_id in IDS:
        names = [h for h in feats if exp_id in h["ids"]]
        sigs, skips = _signals_for(exp_id, names, bars, iwm)
        trades = replay_session(
            bars,
            sigs,
            prior_dv,
            flatten_at=FLATTEN[exp_id],
            **CAP8,
        )
        packed = _pack_trades(trades, bars)
        rows.append(
            {
                "session": session_iso,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": packed,
                "iwm_skips": skips,
            }
        )
    return {
        "session": session_iso,
        "n_coil": sum(1 for h in feats if "coil_break" in h["ids"]),
        "n_0800": sum(1 for h in feats if "am_high_pm" in h["ids"]),
        "n_cand": len(feats),
        "rows": rows,
    }


def _assign_ids(feat: dict) -> list[str]:
    ids = []
    rel9 = feat.get("pre_dv_rel")
    dv9 = feat.get("pre_dv")
    ext9 = feat.get("ext_0929")
    if (
        rel9 is not None
        and dv9 is not None
        and ext9 is not None
        and dv9 >= 250_000.0 - 1e-9
        and rel9 >= 3.0 - 1e-12
        and coil_range_ok(feat.get("pre_high"), feat.get("pre_low"))
        and -0.01 - 1e-12 <= float(ext9) <= 0.03 + 1e-12
    ):
        ids.append("coil_break")
    if hot_gate_0800(
        pre_dv=feat.get("dv0800"),
        pre_dv_rel=feat.get("pre_dv_rel_0800"),
        ext_0800=feat.get("ext_0800"),
    ):
        ids.append("am_high_pm")
        ids.append("flush_hl")
    if (
        rel9 is not None
        and dv9 is not None
        and ext9 is not None
        and dv9 >= 250_000.0 - 1e-9
        and rel9 >= 3.0 - 1e-12
        and float(ext9) >= 0.05 - 1e-12
    ):
        ids.append("fail_rocket")
    if (
        rel9 is not None
        and ext9 is not None
        and rel9 >= 3.0 - 1e-12
        and 0.0 - 1e-12 <= float(ext9) <= 0.08 + 1e-12
    ):
        ids.append("vs_iwm")
    if rel9 is not None and rel9 >= 3.0 - 1e-12:
        ids.append("climax")
    return ids


def run_arrow23(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow23 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "orthogonal rocket jobs; data/full only; cap8; did not rerun 08:00/09:29 buy-the-open, "
        "A21 pullback, strong5, newhigh, or fade-the-hot-open. No Arrow 24.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    by_sess: dict[str, dict[str, dict]] = {}
    for rec in elig.select(
        "session_date", "symbol", "prior_close", "prior_dollar_volume", "eligible"
    ).iter_rows(named=True):
        if rec.get("eligible") is False:
            continue
        pc = rec["prior_close"]
        if pc is None:
            continue
        pc = float(pc)
        if pc < PRICE_LO - 1e-12 or pc > PRICE_HI + 1e-12:
            continue
        iso = _iso(rec["session_date"])
        by_sess.setdefault(iso, {})[str(rec["symbol"])] = {
            "prior_close": pc,
            "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
        }

    print(f"pass 1: 08:00+09:29 pre stats warmup+study n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow23_pre")
    prog.start_heartbeat()
    study_syms: set[str] = set()
    for iso, mp in by_sess.items():
        if iso in {_iso(d) for d in study}:
            study_syms.update(mp)
    jobs = [(d, study_syms) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_pre, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    dv9_hist: dict[str, list[tuple[str, float]]] = {}
    dv8_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for sym, st in feat.get(iso, {}).items():
            dv9_hist.setdefault(sym, []).append((iso, st["dv0929"]))
            if st.get("dv0800") is not None:
                dv8_hist.setdefault(sym, []).append((iso, st["dv0800"]))

    print("load IWM bench", flush=True)
    iwm_all = load_iwm()
    print(f"IWM sessions loaded={len(iwm_all)}", flush=True)

    study_set = {_iso(d) for d in study}
    feats_by_sess: dict[str, list[dict]] = {iso: [] for iso in study_set}
    prior_dv_by_sess: dict[str, dict[str, float]] = {iso: {} for iso in study_set}
    for d in study:
        iso = _iso(d)
        for sym, meta in by_sess.get(iso, {}).items():
            st = (feat.get(iso) or {}).get(sym)
            if not st:
                continue
            prior9 = [v for s, v in (dv9_hist.get(sym) or []) if s < iso]
            med9 = median_prior_window(prior9)
            rel9 = (st["dv0929"] / med9) if med9 else None
            ext9 = st["last_px_0929"] / meta["prior_close"] - 1.0
            rel8 = None
            ext8 = None
            if st.get("dv0800") is not None and st.get("last_px_0800") is not None:
                prior8 = [v for s, v in (dv8_hist.get(sym) or []) if s < iso]
                med8 = median_prior_window(prior8)
                if med8:
                    rel8 = st["dv0800"] / med8
                ext8 = st["last_px_0800"] / meta["prior_close"] - 1.0
            row = {
                "symbol": sym,
                "pre_dv": st["dv0929"],
                "pre_dv_rel": rel9,
                "ext_0929": ext9,
                "pre_high": st["pre_high"],
                "pre_low": st["pre_low"],
                "dv0800": st.get("dv0800"),
                "pre_dv_rel_0800": rel8,
                "ext_0800": ext8,
                "last_px_0800": st.get("last_px_0800"),
            }
            row["ids"] = _assign_ids(row)
            if not row["ids"]:
                continue
            feats_by_sess[iso].append(row)
            prior_dv_by_sess[iso][sym] = meta["prior_dv"]

    replay_jobs = [
        (
            _iso(d),
            feats_by_sess[_iso(d)],
            prior_dv_by_sess[_iso(d)],
            iwm_all.get(_iso(d)),
        )
        for d in develop + holdout
    ]
    print(
        f"pass 2: replay {len(replay_jobs)} sessions; "
        f"coil develop={sum(sum(1 for h in feats_by_sess[_iso(d)] if 'coil_break' in h['ids']) for d in develop)} "
        f"hot0800 develop={sum(sum(1 for h in feats_by_sess[_iso(d)] if 'am_high_pm' in h['ids']) for d in develop)}",
        flush=True,
    )
    prog2 = Progress(len(replay_jobs), "arrow23")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    _write_reports(chunks, feats_by_sess, workers, cpu, develop, holdout)
    return 0


def _summarize_adv(daily: list[float], trades: list[dict], n_sessions: int) -> dict:
    base = _summarize(daily, trades, n_sessions)
    rs = [float(t["r"]) for t in trades]
    wins = [float(t["pnl"]) for t in trades if t["pnl"] > 0]
    losses = [float(t["pnl"]) for t in trades if t["pnl"] < 0]
    gross_w = sum(wins)
    gross_l = abs(sum(losses))
    if not trades:
        pf = 0.0
        pf_s = "0"
    elif gross_l <= 1e-12:
        pf = math.inf
        pf_s = "inf"
    else:
        pf = gross_w / gross_l
        pf_s = f"{pf:.3f}"
    n = len(trades)
    n_stop = sum(1 for t in trades if t.get("tag") == "stop")
    n_time = sum(1 for t in trades if t.get("tag") == "time")
    n_other = n - n_stop - n_time
    mins = [float(t["minutes"]) for t in trades]
    mfe = [float(t["mfe_ext"]) for t in trades]
    reached = sum(1 for t in trades if t.get("reached_1r"))
    base.update(
        {
            "trades_per_sess": n / n_sessions if n_sessions else 0.0,
            "median_r": statistics.median(rs) if rs else 0.0,
            "p10_r": _pct(rs, 10),
            "p90_r": _pct(rs, 90),
            "avg_win": (sum(wins) / len(wins)) if wins else 0.0,
            "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
            "profit_factor": pf,
            "pf_s": pf_s,
            "pct_stop": n_stop / n if n else 0.0,
            "pct_time": n_time / n if n else 0.0,
            "pct_other": n_other / n if n else 0.0,
            "median_min": statistics.median(mins) if mins else 0.0,
            "mean_mfe_ext": (sum(mfe) / len(mfe)) if mfe else 0.0,
            "frac_1r": reached / n if n else 0.0,
        }
    )
    return base


def _fmt_adv(sm: dict) -> list[str]:
    return [
        (
            f"    n={sm['n_trades']}  trades/sess={sm['trades_per_sess']:.2f}  "
            f"hit={sm['hit_rate']:.3f}  avgR={sm['avg_r']:.3f}  medR={sm['median_r']:.3f}  "
            f"p10R={sm['p10_r']:.3f}  p90R={sm['p90_r']:.3f}"
        ),
        (
            f"    avgWin$={sm['avg_win']:.2f}  avgLoss$={sm['avg_loss']:.2f}  PF={sm['pf_s']}  "
            f"stop%={100*sm['pct_stop']:.1f}  time%={100*sm['pct_time']:.1f}  "
            f"other%={100*sm['pct_other']:.1f}  medMin={sm['median_min']:.1f}"
        ),
        (
            f"    $/day={sm['per_day']:.2f}  std={sm['std_day']:.2f}  se={sm['se_day']:.2f}  "
            f"t={sm['t_stat']:.2f}  ci95=[{sm['ci_lo']:.2f},{sm['ci_hi']:.2f}]  "
            f"maxDD$={sm['max_dd']:.2f}"
        ),
        (
            f"    flight mean_ext={sm['mean_mfe_ext']:.4f}  reached_1R={sm['frac_1r']:.3f}"
        ),
    ]


def _shape_paragraph(results: list[dict]) -> str:
    by = {r["name"]: r for r in results}
    am = by.get("am_high_pm")
    fr = by.get("fail_rocket")
    fl = by.get("flush_hl")
    if not (am and fr and fl):
        return (
            "Shape vs Arrows 20-22: those books were ~30% hit, negative avgR, buying already-extended "
            "names at the open. See the stat block for this arrow's six jobs."
        )
    return (
        "Shape vs Arrows 20-22: those books were ~30% hit, negative avgR, stop-driven losses "
        "from buying an already-extended open. Three jobs here are a different shape even though "
        "none clear $200. fail_rocket shorts print "
        f"{fr['holdout']['hit_rate']:.0%} holdout hit and PF {fr['holdout']['pf_s']} with "
        f"{fr['holdout']['pct_time']:.0%} time-flattens and avgR near zero — a slow bleed, not a "
        "chase wash. am_high_pm is almost flat on develop "
        f"({am['develop']['per_day']:.0f}/day) and {am['holdout']['frac_1r']:.0%} of holdout "
        f"trades tag +1R, then give it back (medR {am['holdout']['median_r']:.1f}, "
        f"{am['holdout']['pct_stop']:.0%} stopped). flush_hl is the least-bad holdout "
        f"({fl['holdout']['per_day']:.0f}/day, PF {fl['holdout']['pf_s']}) with a fat right tail "
        f"(p90R {fl['holdout']['p90_r']:.2f}) and {fl['holdout']['frac_1r']:.0%} reaching +1R; "
        "still negative EV. coil_break is ~80% time-flatten dead money (mean extension ~1.5%). "
        "vs_iwm and climax are the same wreck as 20-22, only larger."
    )


def _write_reports(chunks, feats_by_sess, workers, cpu, develop, holdout) -> None:
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    rows = [r for c in chunks for r in c["rows"]]

    def _count(d, key):
        return sum(1 for h in feats_by_sess[_iso(d)] if key in h["ids"])

    coil_dev = [_count(d, "coil_break") for d in develop]
    coil_hol = [_count(d, "coil_break") for d in holdout]
    h8_dev = [_count(d, "am_high_pm") for d in develop]
    h8_hol = [_count(d, "am_high_pm") for d in holdout]

    def _hot_line(label, xs):
        if not xs:
            return f"{label}: n=0"
        return (
            f"{label}: n_sess={len(xs)} total={sum(xs)} mean={sum(xs)/len(xs):.2f} "
            f"median={statistics.median(xs):.1f} max={max(xs)}"
        )

    results = []
    iwm_skips_dev = 0
    iwm_skips_hol = 0
    for exp_id in IDS:
        subset = [r for r in rows if r["name"] == exp_id]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in holdout]
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        if exp_id == "vs_iwm":
            iwm_skips_dev = sum(
                pnl_map.get(_iso(d), {}).get("iwm_skips", 0) for d in develop
            )
            iwm_skips_hol = sum(
                pnl_map.get(_iso(d), {}).get("iwm_skips", 0) for d in holdout
            )
        results.append(
            {
                "name": exp_id,
                "develop": _summarize_adv(daily_dev, tr_dev, len(develop)),
                "holdout": _summarize_adv(daily_hol, tr_hol, len(holdout)),
            }
        )

    def _promotable(r) -> bool:
        return r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0

    promo = [r for r in results if _promotable(r)]
    false_green = [
        r for r in results if r["holdout"]["clears_200"] and r["develop"]["per_day"] < 0
    ]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(
            r["name"] for r in promo
        )
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 23 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass. Did not rerun 08:00/09:29 buy-the-open, "
            "A21 pullback, strong5, newhigh, or fade-the-hot-open."
        )

    lines = [
        "Arrow 23 — orthogonal rocket logics; advanced flight stats (data/full)",
        verdict,
        "Did not rerun 09:29/08:00 buy-the-open of an already-extended name, A21 pullback, "
        "strong5, newhigh, or fade-the-hot-open. No B-short rescore. Did not touch data/bars. "
        "No Arrow 24.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "cap8=8/16/1600 RISK_PER_IDEA=200. Fills=next tradeable open. Leak-fixed flatten.",
        "ids: coil_break long flatten 11:59; am_high_pm long flatten 15:59; fail_rocket short; "
        "flush_hl long; vs_iwm long; climax short.",
        "",
        _hot_line("coil name-days develop", coil_dev),
        _hot_line("coil name-days holdout", coil_hol),
        _hot_line("08:00 hot name-days develop", h8_dev),
        _hot_line("08:00 hot name-days holdout", h8_hol),
        f"id5 IWM window skips develop={iwm_skips_dev} holdout={iwm_skips_hol}",
        "",
        "STAT BLOCK",
    ]
    for r in results:
        flag = "YES" if r["holdout"]["clears_200"] else "NO"
        if r["holdout"]["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(f"{r['name']}  holdout>=200={flag}")
        lines.append("  develop")
        lines.extend(_fmt_adv(r["develop"]))
        lines.append("  holdout")
        lines.extend(_fmt_adv(r["holdout"]))
    if false_green:
        lines.append("")
        lines.append("NO* = holdout >= $200 but develop is red — not a pass:")
        for r in false_green:
            lines.append(
                f"  {r['name']}: develop {r['develop']['per_day']:.2f}/day "
                f"holdout {r['holdout']['per_day']:.2f}/day"
            )
    lines.append("")
    lines.append(_shape_paragraph(results))
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow23_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 23",
        "",
        verdict,
        "",
        "Six orthogonal jobs on data/full: coil break; afternoon AM-high break; failed-rocket "
        "short; flush higher-low; vs-IWM hold; climax short. cap8. Did not rerun 08:00/09:29 "
        "buy-the-open, A21 pullback, strong5, newhigh, or fade. Did not rescore the B-short. "
        "Did not touch data/bars. No Arrow 24.",
        "",
        _hot_line("coil develop", coil_dev),
        _hot_line("coil holdout", coil_hol),
        _hot_line("08:00 hot develop", h8_dev),
        _hot_line("08:00 hot holdout", h8_hol),
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day trades_holdout={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} hit={r['holdout']['hit_rate']:.3f} "
            f"PF={r['holdout']['pf_s']} reached_1R={r['holdout']['frac_1r']:.3f} "
            f"t={r['holdout']['t_stat']:.2f}."
        )
    bits.append("")
    bits.append(_shape_paragraph(results))
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
