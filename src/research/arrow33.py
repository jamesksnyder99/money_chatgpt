from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _summarize
from research.arrow4 import TRACK_A_MAX_PX, TRACK_A_MIN_PX, _filter_track_b
from research.arrow20 import _iso, _read_hot_bars
from research.arrow31 import (
    SHORT_POP,
    _alpha_daily,
    _dv_through,
    _pack_trades,
    _summ_side,
    ensure_iwm_full_hours,
)
from research.arrow32 import CONTROL_KW, FLUSH_ID, _flush_reprint
from research.book import concurrent_stats, joint_peak_risk, marked_equity_session, replay_session, ssr_active
from research.character import dv_ranks
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import resample_15m, stitch_15m
from research.fills import is_tradeable
from research.harness import attach_atr, calendar_prior_dvs, run_rel_vol
from research.signals import MINUTE_0929, MINUTE_0945, MINUTE_1559, RTH_OPEN, Signal, bar_time
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies30 import r1_haircut
from research.strategies32 import conjunction_c5_ema9

ET = ZoneInfo("America/New_York")
STITCH_0400 = time(4, 0)
MIN_RVOL_PRIORS = 5
A32_CONJ_N_DEV = 244
A32_CONJ_N_HOL = 98
COUNT_TOL = 0.10
A27_UPTICK10_N_HOL = 75

CONTROL_ID = "B|conj|atr1559|lock"
DRIFT_ID = "drift_elig"


def _cap(n: int) -> dict:
    return {
        "max_positions": n,
        "max_entries": n * 2,
        "max_risk_outstanding": float(n) * 200.0,
        "harness_stop": True,
    }


EXPERIMENTS = (
    (CONTROL_ID, {**CONTROL_KW, **_cap(8)}, "conj"),
    ("B|conj|cap12", {**CONTROL_KW, **_cap(12)}, "conj"),
    ("B|conj|cap16", {**CONTROL_KW, **_cap(16)}, "conj"),
    ("B|conj|rank_gap", {**CONTROL_KW, **_cap(8)}, "gap"),
    ("B|conj|rank_rvol", {**CONTROL_KW, **_cap(8)}, "rvol"),
    ("B|conj|rank_orw", {**CONTROL_KW, **_cap(8)}, "orw"),
    (DRIFT_ID, {**CONTROL_KW, **_cap(8)}, "drift"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _within(n: int, ref: int, tol: float = COUNT_TOL) -> bool:
    return abs(n - ref) <= tol * ref + 1e-9


def _rescore(sig: Signal, score: float) -> Signal:
    return Signal(
        signal_ts=sig.signal_ts,
        symbol=sig.symbol,
        side=sig.side,
        stop=sig.stop,
        target=sig.target,
        score=float(score),
        tag=sig.tag,
        stop_from_entry=sig.stop_from_entry,
        overnight=sig.overnight,
        atr=sig.atr,
    )


def _prep_one(args: tuple) -> tuple:
    d, want = args
    iso = d.isoformat()
    folder = FULL_BARS / iso
    b15: dict[str, list] = {}
    lows: dict[str, float] = {}
    dv9: dict[str, float] = {}
    if not folder.exists() or not want:
        return iso, b15, lows, dv9
    for path in folder.glob("*.parquet"):
        try:
            df = pl.read_parquet(path)
        except Exception:  # noqa: BLE001
            continue
        if df.height == 0:
            continue
        sym = str(df["symbol"][0]) if "symbol" in df.columns else path.stem.lstrip("_")
        if sym not in want:
            continue
        b15[sym] = resample_15m(df, not_before=STITCH_0400)
        lo = df["low"].min()
        if lo is not None:
            lows[sym] = float(lo)
        dv9[sym] = _dv_through(df, MINUTE_0929)
    return iso, b15, lows, dv9


def _px_at(df: pl.DataFrame, clock) -> float | None:
    last = None
    for rec in df.sort("bar_start").iter_rows(named=True):
        if bar_time(rec["bar_start"]) > clock:
            break
        if not is_tradeable(rec["open"], rec["close"], rec["volume"]):
            continue
        last = float(rec["close"])
    return last


def _field_depth(df: pl.DataFrame, px45: float, r1: float) -> tuple[float, datetime | None]:
    min_low = None
    low_ts = None
    for rec in df.sort("bar_start").iter_rows(named=True):
        t = bar_time(rec["bar_start"])
        if t < RTH_OPEN or t < MINUTE_0945:
            continue
        if t > MINUTE_1559:
            break
        if not is_tradeable(rec["open"], rec["close"], rec["volume"]):
            continue
        lo = float(rec["low"])
        if min_low is None or lo < min_low:
            min_low = lo
            low_ts = rec["bar_start"]
    if px45 is None or px45 <= 0 or min_low is None:
        return 0.0, None
    raw = (px45 - min_low) / px45
    return max(0.0, raw - float(r1 or 0.0)), low_ts


def _replay_one(args: tuple) -> dict:
    (
        session_iso,
        names,
        drift_names,
        bars15,
        sess_order,
        lows,
        pc_by,
        dv9_hist,
        dv9_now,
        want_depth,
    ) = args
    session = date.fromisoformat(session_iso)
    empty_rows = [
        {
            "session": session_iso,
            "name": n,
            "pnl": 0.0,
            "trades": [],
            "peak": 0,
            "mean_conc": 0.0,
            "at_cap": 0,
            "filled": [],
            "rvol_skip": 0,
            "kernel_n": 0,
        }
        for n in IDS
    ]
    empty = {
        "session": session_iso,
        "n_cand": len(names),
        "rows": empty_rows,
        "depth": [],
        "rvol_skip": 0,
        "kernel_n": 0,
    }
    if not names:
        return empty
    symbols = list({h["symbol"] for h in names + drift_names})
    bars = _read_hot_bars(session, symbols)
    meta = {h["symbol"]: h for h in names}
    prior_dv = {h["symbol"]: float(h["prior_dv"]) for h in names}
    prior_c = {
        h["symbol"]: float(h["prior_close"])
        for h in names
        if h.get("prior_close") is not None
    }
    for h in drift_names:
        prior_dv.setdefault(h["symbol"], float(h["prior_dv"]))
        if h.get("prior_close") is not None:
            prior_c.setdefault(h["symbol"], float(h["prior_close"]))
    idx = sess_order.index(session_iso) if session_iso in sess_order else -1
    prev_iso = sess_order[idx - 1] if idx > 0 else None
    psl = dict(lows.get(prev_iso) or {}) if prev_iso else {}
    pspc = dict(pc_by.get(prev_iso) or {}) if prev_iso else {}
    ranks = dv_ranks({h["symbol"]: float(h["prior_dv"]) for h in names})
    conj_by: dict[str, Signal] = {}
    feat: dict[str, dict] = {}
    kernel_n = 0
    rvol_skip = 0
    depth_rows = []
    for h in names:
        sym = h["symbol"]
        sdf = bars.get(sym)
        if sdf is None or sdf.height == 0:
            continue
        pc = h.get("prior_close")
        pc = float(pc) if pc is not None else None
        rank = ranks.get(sym, 0.0)
        rng = opening_range(sdf)
        or_w = rng[2] if rng else None
        or_high = rng[0] if rng else None
        gap = session_gap(sdf, pc)
        if (
            want_depth
            and gap is not None
            and gap <= -0.015 + 1e-12
            and or_w is not None
            and or_w > 0.025 + 1e-12
        ):
            px45 = _px_at(sdf, MINUTE_0945)
            ts45 = None
            for rec in sdf.sort("bar_start").iter_rows(named=True):
                if bar_time(rec["bar_start"]) >= MINUTE_0945:
                    ts45 = rec["bar_start"]
                    break
            if ts45 is None:
                ts45 = sdf["bar_start"][0]
            r1 = r1_haircut(sdf, ts45, pc) if pc else 0.006
            dep, low_ts = _field_depth(sdf, px45 or 0.0, r1)
            lo = float(sdf["low"].min()) if sdf.height else None
            ssr = ssr_active(lo, pc) if pc else False
            depth_rows.append(
                {
                    "session": session_iso,
                    "symbol": sym,
                    "depth": dep,
                    "hour": low_ts.hour if low_ts is not None else None,
                    "ssr": bool(ssr),
                }
            )
        if not short_kernel_pop(rank, gap, or_w, **SHORT_POP) or or_high is None:
            continue
        kernel_n += 1
        win = calendar_prior_dvs(dv9_hist.get(sym) or {}, session_iso, sess_order)
        if int(win["n_present"]) < MIN_RVOL_PRIORS:
            rvol_skip += 1
            continue
        rel = run_rel_vol((dv9_now or {}).get(sym), win["values"])
        stitched = stitch_15m(sym, session_iso, sess_order, bars15)
        got, _led = conjunction_c5_ema9(sdf, stitched, or_high)
        for sig in got:
            if sig.side != -1:
                continue
            attached = attach_atr(sig, sdf)
            conj_by[sym] = attached
            feat[sym] = {"gap": gap, "rel": rel, "orw": or_w}
    drift_set = {h["symbol"] for h in drift_names}
    rows = []
    for name, kw, src in EXPERIMENTS:
        if src == "drift":
            sigs = [conj_by[s] for s in drift_set if s in conj_by]
        elif src == "gap":
            sigs = []
            for s, sig in conj_by.items():
                g = feat[s].get("gap")
                if g is None:
                    continue
                sigs.append(_rescore(sig, -float(g)))
        elif src == "rvol":
            sigs = []
            for s, sig in conj_by.items():
                rel = feat[s].get("rel")
                if rel is None:
                    continue
                sigs.append(_rescore(sig, float(rel)))
        elif src == "orw":
            sigs = []
            for s, sig in conj_by.items():
                ow = feat[s].get("orw")
                if ow is None:
                    continue
                sigs.append(_rescore(sig, float(ow)))
        else:
            sigs = list(conj_by.values())
        st = {}
        trades = replay_session(
            bars,
            sigs,
            prior_dv,
            prior_close=prior_c,
            prior_session_low=psl,
            prior_session_prior_close=pspc,
            stats=st,
            **kw,
        )
        peak, mean_c = concurrent_stats(trades)
        packed = _pack_trades(trades, bars)
        mtm = marked_equity_session(trades, bars)
        cap_n = int(kw.get("max_positions") or 8)
        rows.append(
            {
                "session": session_iso,
                "name": name,
                "pnl": sum(t.pnl for t in trades),
                "trades": packed,
                "peak": peak,
                "mean_conc": mean_c,
                "at_cap": 1 if peak >= cap_n else 0,
                "filled": sorted({t.symbol for t in trades}),
                "intraday_dd": float(mtm["intraday_peak_to_trough"]),
                "ssr_nofill": int(st.get("ssr_nofill") or 0),
                "n_short_signals": int(st.get("n_short_signals") or 0),
                "n_ssr_signals": int(st.get("n_ssr_signals") or 0),
                "unresolved_flatten": int(st.get("unresolved_flatten") or 0),
                "unresolved_late": int(st.get("unresolved_late") or 0),
                "rvol_skip": rvol_skip,
                "kernel_n": kernel_n,
            }
        )
    return {
        "session": session_iso,
        "n_cand": len(names),
        "rows": rows,
        "depth": depth_rows,
        "rvol_skip": rvol_skip,
        "kernel_n": kernel_n,
        "leader_filled": rows[0]["filled"] if rows else [],
    }


def run_arrow33(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow33 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "hygiene, cap/rank on A32 conjunction lock, develop depth rollup. "
        "Do not promote atr150. No flush rings. No $500/idea. No virgin pull. "
        "Combined holdout is not EV. No Arrow 34.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    track_b, capped = _filter_track_b(elig)
    print(f"Track B rows={track_b.height} cap_file={capped} tape=data/full", flush=True)
    iwm = ensure_iwm_full_hours(workers=workers)

    want_b = set(str(s) for s in track_b["symbol"].unique().to_list())
    by_sess: dict[str, list[dict]] = {iso: [] for iso in sess_order}
    drift_sess: dict[str, list[dict]] = {iso: [] for iso in sess_order}
    pc_by: dict[str, dict[str, float]] = {}
    for rec in track_b.select(
        "session_date", "symbol", "prior_close", "prior_dollar_volume"
    ).iter_rows(named=True):
        iso = _iso(rec["session_date"])
        sym = str(rec["symbol"])
        pc = rec["prior_close"]
        if pc is None:
            continue
        pc = float(pc)
        row = {"symbol": sym, "prior_close": pc, "prior_dv": float(rec["prior_dollar_volume"] or 0.0)}
        by_sess.setdefault(iso, []).append(row)
        if TRACK_A_MIN_PX - 1e-12 <= pc <= TRACK_A_MAX_PX + 1e-12:
            drift_sess.setdefault(iso, []).append(row)
        pc_by.setdefault(iso, {})[sym] = pc
    for rec in elig.select("session_date", "symbol", "prior_close").iter_rows(named=True):
        pc = rec["prior_close"]
        if pc is None:
            continue
        iso = _iso(rec["session_date"])
        pc_by.setdefault(iso, {})[str(rec["symbol"])] = float(pc)

    print(f"pass 1: 15m + dv0929 n={len(all_sess)} symbols={len(want_b)}", flush=True)
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow33_pre")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_prep_one, (d, want_b)): d for d in all_sess}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, b15, lo, d9 = fut.result()
            lows[iso] = lo
            dv9[iso] = d9
            for sym, series in b15.items():
                bars15[(sym, iso)] = series
            prog.mark(iso, rows=len(b15))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    dv9_hist: dict[str, dict[str, float]] = {}
    for iso in sess_order:
        for sym, v in (dv9.get(iso) or {}).items():
            dv9_hist.setdefault(sym, {})[iso] = v

    jobs = []
    for d in develop + holdout:
        iso = _iso(d)
        jobs.append(
            (
                iso,
                by_sess.get(iso, []),
                drift_sess.get(iso, []),
                bars15,
                sess_order,
                lows,
                pc_by,
                dv9_hist,
                dv9.get(iso, {}),
                d in develop,
            )
        )
    print(f"pass 2: B-short {len(jobs)} sessions x {len(IDS)}", flush=True)
    prog2 = Progress(len(jobs), "arrow33_b")
    prog2.start_heartbeat()
    b_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            b_chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    print("pass 3: reprint A31 flush|max6|repaired (not a new ring)", flush=True)
    flush_chunks = _flush_reprint(elig, all_sess, study, develop, holdout, workers)
    _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped)
    return 0


def _depth_block(rows: list[dict], leader_keys: set[tuple[str, str]]) -> list[str]:
    n = len(rows)
    depths = [float(r["depth"]) for r in rows]
    s_depth = sum(depths)
    n_lead = len(leader_keys)
    cov = n_lead / n if n else 0.0
    on = [r for r in rows if (r["session"], r["symbol"]) in leader_keys]
    s_on = sum(float(r["depth"]) for r in on)
    by_hour: dict[int, list[float]] = {}
    by_ssr = {True: [], False: []}
    for r in rows:
        h = r.get("hour")
        if h is not None:
            by_hour.setdefault(int(h), []).append(float(r["depth"]))
        by_ssr[bool(r.get("ssr"))].append(float(r["depth"]))
    lines = [
        f"DEPTH develop field n={n} leader_name_days={n_lead} coverage={cov:.3f}",
        f"  sum_depth={s_depth:.4f}  on_leader_name_days={s_on:.4f}  "
        f"frac_depth_on_leader={s_on / s_depth if s_depth else 0.0:.3f}",
    ]
    hour_bits = []
    for h in sorted(by_hour):
        xs = by_hour[h]
        hour_bits.append(f"{h:02d}h n={len(xs)} sum={sum(xs):.3f}")
    lines.append("  by hour of the low: " + "; ".join(hour_bits) if hour_bits else "  by hour: none")
    lines.append(
        f"  by SSR: ssr n={len(by_ssr[True])} sum={sum(by_ssr[True]):.3f}  "
        f"no_ssr n={len(by_ssr[False])} sum={sum(by_ssr[False]):.3f}"
    )
    return lines


def _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    b_rows = [r for c in b_chunks for r in c["rows"]]
    kernel_n = sum(int(c.get("kernel_n") or 0) for c in b_chunks)
    rvol_skip = sum(int(c.get("rvol_skip") or 0) for c in b_chunks)
    skip_share = rvol_skip / kernel_n if kernel_n else 0.0

    results = []
    daily_map = {}
    trades_map = {}
    for name in IDS:
        sub = [r for r in b_rows if r["name"] == name]
        sm_d, _dd, tr_d, map_d = _summ_side(sub, develop)
        sm_h, _dh, tr_h, map_h = _summ_side(sub, holdout)
        daily_map[name] = {**map_d, **map_h}
        trades_map[name] = {"dev": tr_d, "hol": tr_h}
        a_hol, skip_h, n_ah = _alpha_daily(tr_h, holdout, iwm)
        days_cap_d = sum(int(r.get("at_cap") or 0) for r in sub if r["session"] in develop_set)
        days_cap_h = sum(int(r.get("at_cap") or 0) for r in sub if r["session"] in holdout_set)
        sm_d["days_at_cap"] = days_cap_d
        sm_h["days_at_cap"] = days_cap_h
        sm_d["unresolved_late"] = sum(int(r.get("unresolved_late") or 0) for r in sub if r["session"] in develop_set)
        sm_h["unresolved_late"] = sum(int(r.get("unresolved_late") or 0) for r in sub if r["session"] in holdout_set)
        results.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "alpha_hol": {"per_day": (sum(a_hol) / len(holdout)) if holdout else 0.0},
                "n_alpha_hol": n_ah,
                "alpha_skip_hol": skip_h,
            }
        )

    ctrl = next(r for r in results if r["name"] == CONTROL_ID)
    n_d, n_h = ctrl["develop"]["n_trades"], ctrl["holdout"]["n_trades"]
    if _within(n_d, A32_CONJ_N_DEV) and _within(n_h, A32_CONJ_N_HOL):
        drift = (
            f"Id 0 vs A32 {CONTROL_ID}: develop {n_d}/{A32_CONJ_N_DEV} "
            f"holdout {n_h}/{A32_CONJ_N_HOL} — within ±10%."
        )
    else:
        drift = (
            f"Id 0 vs A32 {CONTROL_ID}: develop {n_d}/{A32_CONJ_N_DEV} "
            f"({n_d / max(A32_CONJ_N_DEV, 1):.2f}x) holdout {n_h}/{A32_CONJ_N_HOL} "
            f"({n_h / max(A32_CONJ_N_HOL, 1):.2f}x) — DRIFT beyond ±10%."
        )
    drift_row = next(r for r in results if r["name"] == DRIFT_ID)
    drift_elig_line = (
        f"drift_elig (prior_close [{TRACK_A_MIN_PX:.0f},{TRACK_A_MAX_PX:.0f}] Lab-A band) "
        f"develop n={drift_row['develop']['n_trades']} holdout n={drift_row['holdout']['n_trades']} "
        f"vs A27 B_uptick10 holdout 75 and A32 conj holdout 98. Not a champion."
    )

    depth_rows = [r for c in b_chunks if c["session"] in develop_set for r in c.get("depth") or []]
    leader_keys = set()
    for c in b_chunks:
        if c["session"] not in develop_set:
            continue
        for rec in c["rows"]:
            if rec["name"] != CONTROL_ID:
                continue
            for sym in rec.get("filled") or []:
                leader_keys.add((c["session"], sym))
    mfe_pts = sum(max(0.0, float(t.get("mfe_ext") or 0.0)) for t in trades_map[CONTROL_ID]["dev"])
    field_pts = sum(float(r["depth"]) for r in depth_rows)
    depth_lines = _depth_block(depth_rows, leader_keys)
    if field_pts > 0:
        lever = (
            "Leftover lever: "
            + (
                "the door — leader covers little of the gap/OR field."
                if (len(leader_keys) / max(len(depth_rows), 1)) < 0.20
                else "the exit — the door sits on the field but captures little of the depth."
                if (mfe_pts / field_pts) < 0.20
                else "split — coverage and MFE-from-entry are both material; neither is an unused pile."
            )
        )
    else:
        lever = "Leftover lever: field depth is empty; nothing to attribute to door vs exit."
    depth_lines.append(
        f"  MFE-from-entry points={mfe_pts:.4f} / field depth points={field_pts:.4f}  "
        f"ratio={mfe_pts / field_pts if field_pts else 0.0:.3f}"
    )
    depth_lines.append("  " + lever)

    flush_map = {c["session"]: c for c in flush_chunks}
    daily_flush = {
        **{d.isoformat(): float(flush_map.get(d.isoformat(), {}).get("pnl") or 0.0) for d in develop},
        **{d.isoformat(): float(flush_map.get(d.isoformat(), {}).get("pnl") or 0.0) for d in holdout},
    }
    flush_sm_d = _summarize([daily_flush[d.isoformat()] for d in develop], [], len(develop))
    flush_sm_h = _summarize([daily_flush[d.isoformat()] for d in holdout], [], len(holdout))
    flush_tr_d = [t for c in flush_chunks if c["session"] in develop_set for t in c.get("trades") or []]
    flush_tr_h = [t for c in flush_chunks if c["session"] in holdout_set for t in c.get("trades") or []]

    def _promo(dev, hol) -> bool:
        return hol["clears_200"] and dev["per_day"] >= 0

    scored = [r for r in results if r["name"] != DRIFT_ID]
    green = [r for r in scored if r["develop"]["per_day"] >= 0]
    if green:
        best = max(green, key=lambda r: r["develop"]["per_day"])
    else:
        best = ctrl
    comb_d = combine_books(
        {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in develop},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in develop},
    )
    comb_h = combine_books(
        {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in holdout},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in holdout},
    )
    peak_d = joint_peak_risk(trades_map[best["name"]]["dev"], flush_tr_d)
    peak_h = joint_peak_risk(trades_map[best["name"]]["hol"], flush_tr_h)

    promo = [r["name"] for r in scored if _promo(r["develop"], r["holdout"])]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 33 book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not expected value (EV)."
        )
    honesty = (
        f"Do not promote A32 atr150. Frozen leader is {CONTROL_ID}. "
        f"COMBINED uses best develop-not-red B ({best['name']}, "
        f"develop ${best['develop']['per_day']:.2f}/day) + A31 flush reprint. Combined holdout is not EV."
    )

    lines = [
        "Arrow 33 — hygiene, cap/rank on the standing short, depth rollup",
        verdict,
        honesty,
        "Combined holdout is not expected value (EV). Do not write that the account is one improvement from $200.",
        "A1-A5 on. last_entry_at=11:59. Flatten 15:59. SSR=uptick10. No flush rings. No $500/idea. "
        "No virgin pull. No atr150. No Arrow 34.",
        "Acronyms: EMA = exponential moving average; ATR = Average True Range; "
        "MFE = maximum favorable excursion; RVOL = relative volume; IWM = iShares Russell 2000 ETF; "
        "SSR = Short Sale Restriction.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap={capped}  tape={FULL_BARS}",
        "Door: A32 conjunction (5-min close < EMA9 and EMA9 < EMA21 at bar_end), 1.0× ATR trail after +1R.",
        drift,
        (
            f"RVOL skip <{MIN_RVOL_PRIORS} prior exchange sessions: "
            f"skip={rvol_skip} kernel_n={kernel_n} share={skip_share:.3f}"
        ),
        drift_elig_line,
        "",
        f"{'id':<22} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'avgR':>7} "
        f"{'PF':>6} {'t_hold':>7} {'MFE-cap':>8} {'capD':>5} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if r["name"] != DRIFT_ID and _promo(r["develop"], h):
            flag = "BOTH"
        if r["name"] == DRIFT_ID:
            flag = "diag"
        lines.append(
            f"{r['name']:<22} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['avg_r']:7.3f} {h['pf_s']:>6} {h['t_stat']:7.2f} "
            f"{h['mfe_cap']:8.3f} {r['develop']['days_at_cap']:5d} {flag:>6}"
        )
        lines.append(f"  develop {_fmt(r['develop'], holdout=False)}")
        lines.append(
            f"    PF={r['develop']['pf_s']}  peak_conc={r['develop']['peak_conc']}  "
            f"mean_conc={r['develop']['mean_conc']:.2f}  days_at_cap={r['develop']['days_at_cap']}  "
            f"MFE-capture={r['develop']['mfe_cap']:.3f}  unresolved_late={r['develop'].get('unresolved_late', 0)}"
        )
        lines.append(
            f"    marked equity: daily-close DD$={r['develop']['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={r['develop']['intraday_dd']:.2f}"
        )
        lines.append(f"  holdout {_fmt(r['holdout'], holdout=True)}")
        lines.append(
            f"    PF={h['pf_s']}  peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}  "
            f"days_at_cap={h['days_at_cap']}  MFE-capture={h['mfe_cap']:.3f}  "
            f"IWM alpha hold ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
        lines.append(
            f"    marked equity: daily-close DD$={h['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={h['intraday_dd']:.2f}"
        )
    lines.append("")
    lines.extend(depth_lines)
    lines.append("")
    lines.append(
        f"flush|max6|repaired (A31 reprint, not rescored) develop ${flush_sm_d['per_day']:.2f}/day "
        f"holdout ${flush_sm_h['per_day']:.2f}/day"
    )
    lines.append("")
    lines.append(f"COMBINED {best['name']} + {FLUSH_ID}  (best develop-not-red B this file + A31 flush)")
    lines.append(
        f"  develop $/day={comb_d['per_day']:.2f}  std={comb_d['std_day']:.2f}  "
        f"se={comb_d['se_day']:.2f}  t={comb_d['t_stat']:.2f}  "
        f"ci95=[{comb_d['ci_lo']:.2f},{comb_d['ci_hi']:.2f}]  maxDD$={comb_d['max_dd']:.2f}  "
        f"corr={comb_d['corr'].get((0, 1), 0.0):.3f}  joint_peak_risk$={peak_d:.2f}"
    )
    lines.append(
        f"  holdout $/day={comb_h['per_day']:.2f}  std={comb_h['std_day']:.2f}  "
        f"se={comb_h['se_day']:.2f}  t={comb_h['t_stat']:.2f}  "
        f"ci95=[{comb_h['ci_lo']:.2f},{comb_h['ci_hi']:.2f}]  maxDD$={comb_h['max_dd']:.2f}  "
        f"corr={comb_h['corr'].get((0, 1), 0.0):.3f}  joint_peak_risk$={peak_h:.2f}  NOT EV"
    )
    lines.append("NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow33_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 33",
        "",
        verdict,
        "",
        "Hygiene, cap/rank on A32 conjunction lock, develop depth rollup. Do not promote atr150. "
        "No flush rings. No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 34.",
        honesty,
        drift,
        f"RVOL skip share={skip_share:.3f} ({rvol_skip}/{kernel_n}).",
        drift_elig_line,
        lever,
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"MFE-capture={r['holdout']['mfe_cap']:.3f} IWM skip={r['alpha_skip_hol']}"
        )
    bits.append(
        f"COMBINED {best['name']}+flush|max6|repaired develop ${comb_d['per_day']:.2f} "
        f"holdout ${comb_h['per_day']:.2f} NOT EV"
    )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")

