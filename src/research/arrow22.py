from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _summarize
from research.arrow19 import CLOCK_0800, _last_at_or_before, _pack
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.rockets import median_prior_window
from research.signals import MINUTE_0929, MINUTE_1159
from research.split import develop_holdout
from research.strategies20 import STOP_MIN_FRAC
from research.strategies22 import (
    EXT6_HI,
    EXT_HI,
    PRE_DV_750K,
    PRE_DV_MIN,
    hot_gate_0800,
    open_longs_0800,
)

ET = ZoneInfo("America/New_York")

CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": STOP_MIN_FRAC,
}
CAP3 = {
    "max_positions": 3,
    "max_entries": 16,
    "max_risk_outstanding": 600.0,
    "min_stop_frac": STOP_MIN_FRAC,
}

EXPERIMENTS = (
    ("open|flat0929", MINUTE_0929, PRE_DV_MIN, EXT_HI, CAP8, False),
    ("open|flat1159", MINUTE_1159, PRE_DV_MIN, EXT_HI, CAP8, False),
    ("open|dv750k", MINUTE_0929, PRE_DV_750K, EXT_HI, CAP8, False),
    ("open|ext6", MINUTE_0929, PRE_DV_MIN, EXT6_HI, CAP8, False),
    ("open|max3", MINUTE_0929, PRE_DV_MIN, EXT_HI, CAP3, False),
    ("open|nocluster", MINUTE_0929, PRE_DV_MIN, EXT_HI, CAP8, True),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _pre_stats_0800(pack: dict) -> dict | None:
    idx, dv = _last_at_or_before(pack, CLOCK_0800)
    if idx is None:
        return None
    lows = pack["low"][: idx + 1]
    return {
        "dv0800": dv,
        "last_px": pack["close"][idx],
        "last_ts": pack["ts"][idx],
        "sess_low": min(lows) if lows else None,
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
        st = _pre_stats_0800(pack)
        if st is None:
            continue
        out[sym] = st
    return iso, out


def _replay_one(args: tuple) -> dict:
    session_iso, hots, prior_dv = args
    session = date.fromisoformat(session_iso)
    empty = {
        "session": session_iso,
        "n_hot": len(hots),
        "rows": [
            {"session": session_iso, "name": n, "pnl": 0.0, "trades": []} for n in IDS
        ],
    }
    if not hots:
        return empty
    bars = _read_hot_bars(session, [h["symbol"] for h in hots])
    morning_dv = {h["symbol"]: float(h["pre_dv"]) for h in hots}
    rows = []
    for exp_id, flatten_at, pre_dv_min, ext_hi, cap, skip_if_cluster in EXPERIMENTS:
        sigs = open_longs_0800(
            hots,
            pre_dv_min=pre_dv_min,
            ext_hi=ext_hi,
            skip_if_cluster=skip_if_cluster,
        )
        trades = replay_session(
            bars,
            sigs,
            prior_dv,
            flatten_at=flatten_at,
            morning_dv=morning_dv,
            allow_premarket=True,
            **cap,
        )
        rows.append(
            {
                "session": session_iso,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    return {"session": session_iso, "n_hot": len(hots), "rows": rows}


def run_arrow22(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow22 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "long only; 08:00 hot gate; data/full only; 5pct pre_dv_0800 notional cap; "
        "did not rerun 09:29 open/pullback/strong5/newhigh/fade. No Arrow 23.",
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

    print(f"pass 1: 08:00 pre stats warmup+study n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow22_pre")
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

    dv_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for sym, st in feat.get(iso, {}).items():
            dv_hist.setdefault(sym, []).append((iso, st["dv0800"]))

    study_set = {_iso(d) for d in study}
    hots_by_sess: dict[str, list[dict]] = {iso: [] for iso in study_set}
    prior_dv_by_sess: dict[str, dict[str, float]] = {iso: {} for iso in study_set}
    for d in study:
        iso = _iso(d)
        for sym, meta in by_sess.get(iso, {}).items():
            st = (feat.get(iso) or {}).get(sym)
            if not st:
                continue
            prior = [v for s, v in (dv_hist.get(sym) or []) if s < iso]
            med = median_prior_window(prior)
            if med is None:
                continue
            ext = st["last_px"] / meta["prior_close"] - 1.0
            rel = st["dv0800"] / med
            if not hot_gate_0800(pre_dv=st["dv0800"], pre_dv_rel=rel, ext_0800=ext):
                continue
            hots_by_sess[iso].append(
                {
                    "symbol": sym,
                    "last_ts": st["last_ts"],
                    "last_px": st["last_px"],
                    "sess_low": st["sess_low"],
                    "pre_dv": st["dv0800"],
                    "pre_dv_rel": rel,
                    "ext_0800": ext,
                }
            )
            prior_dv_by_sess[iso][sym] = meta["prior_dv"]

    replay_jobs = [
        (_iso(d), hots_by_sess[_iso(d)], prior_dv_by_sess[_iso(d)]) for d in develop + holdout
    ]
    print(
        f"pass 2: replay {len(replay_jobs)} sessions; "
        f"hot name-days develop={sum(len(hots_by_sess[_iso(d)]) for d in develop)} "
        f"holdout={sum(len(hots_by_sess[_iso(d)]) for d in holdout)}",
        flush=True,
    )
    prog2 = Progress(len(replay_jobs), "arrow22")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_hot"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    _write_reports(chunks, hots_by_sess, workers, cpu, develop, holdout)
    return 0


def _write_reports(chunks, hots_by_sess, workers, cpu, develop, holdout) -> None:
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    rows = [r for c in chunks for r in c["rows"]]
    hot_dev = [len(hots_by_sess[_iso(d)]) for d in develop]
    hot_hol = [len(hots_by_sess[_iso(d)]) for d in holdout]

    def _hot_line(label, xs):
        if not xs:
            return f"{label}: n=0"
        return (
            f"{label}: n_sess={len(xs)} total={sum(xs)} mean={sum(xs)/len(xs):.2f} "
            f"median={statistics.median(xs):.1f} max={max(xs)}"
        )

    results = []
    for exp_id in IDS:
        subset = [r for r in rows if r["name"] == exp_id]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in holdout]
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        results.append(
            {
                "name": exp_id,
                "develop": _summarize(daily_dev, tr_dev, len(develop)),
                "holdout": _summarize(daily_hol, tr_hol, len(holdout)),
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
            "VERDICT: FAIL — no Arrow 22 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass. Did not rerun 09:29 open/pullback/"
            "strong5/newhigh/fade."
        )

    lines = [
        "Arrow 22 — 08:00 rockets, not the 09:29 funeral (data/full)",
        verdict,
        "Long only. Decision stamp 08:00; fill next tradeable open. Size min(10pct account, "
        "5pct pre_dv_0800, 2pct prior-day DV). Did not rerun Arrow 20/21 09:29-open, pullback, "
        "strong5, newhigh, or fade. No B-short rescore. Did not touch data/bars. No Arrow 23.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "Hot gate at 08:00: prior_close [$1,$20], pre_dv_0800>=400k, pre_dv_rel_0800>=3, "
        "ext in [0.02, 0.10).",
        "id3 tightens pre_dv_0800>=750k. id4 tightens ext to [0.02, 0.06). cap8=8/16/1600 except "
        "id5 max_positions=3. id6 skips sessions with >15 hot names. Flatten 09:29 except id2 "
        "11:59. RISK_PER_IDEA=200. Fills=next tradeable open. Leak-fixed flatten. Premarket stops on.",
        "",
        _hot_line("08:00 hot name-days develop", hot_dev),
        _hot_line("08:00 hot name-days holdout", hot_hol),
        "develop hot/session:",
    ]
    for d in develop:
        lines.append(f"  {_iso(d)} {len(hots_by_sess[_iso(d)])}")
    lines.append("holdout hot/session:")
    for d in holdout:
        lines.append(f"  {_iso(d)} {len(hots_by_sess[_iso(d)])}")
    lines.append("")
    lines.append(
        f"{'id':<16} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} "
        f"{'hit':>6} {'avgR':>7} {'t_hold':>7} {'ci95 hold':>22} {'>=200':>6}"
    )
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        ci = f"[{h['ci_lo']:.1f},{h['ci_hi']:.1f}]"
        lines.append(
            f"{r['name']:<16} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} {h['t_stat']:7.2f} "
            f"{ci:>22} {flag:>6}"
        )
        lines.append(f"       develop {_fmt(r['develop'], holdout=False)}")
        lines.append(f"       holdout {_fmt(r['holdout'], holdout=True)}")
    if false_green:
        lines.append("")
        lines.append("NO* = holdout >= $200 but develop is red — not a pass:")
        for r in false_green:
            lines.append(
                f"  {r['name']}: develop {r['develop']['per_day']:.2f}/day "
                f"holdout {r['holdout']['per_day']:.2f}/day"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow22_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 22",
        "",
        verdict,
        "",
        "08:00 hot gate (prior_close $1-20, pre_dv_0800>=400k, pre_dv_rel_0800>=3, ext in "
        "[2%, 10)). Fill next tradeable open. Size min(10pct account, 5pct pre_dv_0800, 2pct "
        "prior-day DV). Six longs: flatten 09:29; flatten 11:59; pre_dv>=750k; ext [2%, 6%); "
        "max_positions=3; skip sessions with >15 hot names. Did not rerun 09:29 open/pullback/"
        "strong5/newhigh/fade. Did not rescore the B-short. Did not touch data/bars. No Arrow 23.",
        "",
        _hot_line("08:00 hot develop", hot_dev),
        _hot_line("08:00 hot holdout", hot_hol),
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day trades_holdout={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} t={r['holdout']['t_stat']:.2f}."
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
