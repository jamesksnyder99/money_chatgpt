from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _read_session_bars, _split_by_symbol, _summarize
from research.arrow4 import _filter_track_a, _filter_track_b
from research.arrow5 import _build_stats, _channel_hl, _maps_from_elig
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.signals import MINUTE_1045
from research.split import develop_holdout
from research.strategies5 import (
    channel_position_signals,
    failed_yday_break_signals,
    yday_level_break_free_signals,
)
from research.trend import prior10, trend_for

ET = ZoneInfo("America/New_York")

# Six experiments only. Do not retry exact dead Arrow 6 (track, rule, stance) pairs.
EXPERIMENTS = (
    ("failed_yday_break|baseline", "failed_yday_break", {}),
    ("failed_yday_break|2R", "failed_yday_break", {"take_2r": True}),
    ("failed_yday_break|time_box", "failed_yday_break", {"flatten_at": MINUTE_1045}),
    ("channel_position|2R", "channel_position", {"take_2r": True}),
    ("channel_position|trail", "channel_position", {"trail_after_1r": True}),
    ("yday_level_break|tight_2R", "yday_level_break", {"take_2r": True, "max_positions": 2, "max_entries": 4}),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, pc, dv, stats = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty_rows = [
        {"session": session_iso, "track": track, "name": n, "pnl": 0.0, "trades": []}
        for n in IDS
    ]
    if elig_df.height == 0:
        return {"rows": empty_rows}
    bars = _read_session_bars(session)
    if bars.height == 0:
        return {"rows": empty_rows}
    keep = set(elig_df["symbol"].to_list())
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    prior = prior10(session) or []

    sigs: dict[str, list] = {
        "failed_yday_break": [],
        "channel_position": [],
        "yday_level_break": [],
    }
    for sym, sdf in by_sym.items():
        yday = prior[-1] if prior else None
        ystat = stats.get((sym, yday.isoformat())) if yday else None
        yhi = ystat["high"] if ystat else None
        ylo = ystat["low"] if ystat else None
        h, l = _channel_hl(sym, prior, stats) if prior else (None, None)
        sigs["failed_yday_break"].extend(failed_yday_break_signals(sdf, yhi, ylo))
        sigs["yday_level_break"].extend(yday_level_break_free_signals(sdf, yhi, ylo))
        tr = trend_for(sym, session, pc)
        if tr is None or tr.side == "flat":
            continue
        sigs["channel_position"].extend(channel_position_signals(sdf, tr, h, l))

    rows = []
    for exp_id, entry, kwargs in EXPERIMENTS:
        trades = replay_session(by_sym, sigs[entry], prior_dv, **kwargs)
        rows.append(
            {
                "session": session_iso,
                "track": track,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    return {"rows": rows}


def run_arrow7(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    print(
        f"research start mode=arrow7 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "engine: repaired book; 2R target and trail-after-1R (H/L trigger, next-open fill); "
        "time-box flatten >= 10:45; tight book 2 pos / 4 entries. Next-open stop fills unchanged.",
        flush=True,
    )
    elig_all = pl.read_parquet(ELIGIBILITY)
    a_path = ELIGIBILITY.parent / "eligibility_a.parquet"
    b_path = ELIGIBILITY.parent / "eligibility_b.parquet"
    if a_path.exists():
        track_a = pl.read_parquet(a_path)
    else:
        track_a = _filter_track_a(elig_all)
        track_a.write_parquet(a_path)
    if b_path.exists():
        track_b = pl.read_parquet(b_path)
        capped = True
    else:
        track_b, capped = _filter_track_b(elig_all)
        track_b.write_parquet(b_path)
    print(f"Track A rows={track_a.height} Track B rows={track_b.height}", flush=True)

    pc, dv = _maps_from_elig(elig_all)
    print("precompute 1m session high/low/range/open", flush=True)
    stats = _build_stats(all_sess, workers)
    print(f"session_stats keys={len(stats)}", flush=True)

    jobs = []
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for d in develop + holdout:
            jobs.append((d.isoformat(), track, path, pc, dv, stats))
    prog = Progress(len(jobs), "arrow7")
    prog.start_heartbeat()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk["rows"])
            prog.mark(chunk["rows"][0]["session"] if chunk["rows"] else "", rows=len(chunk["rows"]))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    _write_reports(rows, workers, cpu, develop, holdout, capped)
    return 0


def _write_reports(rows, workers, cpu, develop, holdout, capped) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    results = []
    for track in ("A", "B"):
        for exp_id in IDS:
            subset = [r for r in rows if r["track"] == track and r["name"] == exp_id]
            pnl_map = {r["session"]: r for r in subset}
            daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
            daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
            tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
            tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
            results.append(
                {
                    "track": track,
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
            f"{r['track']}/{r['name']}" for r in promo
        )
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 7 experiment has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass."
        )

    lines = [
        "Arrow 7 — manage/exit lab (same population, no new hours)",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "Pass = holdout >= $200/day AND develop not red. Do not promote develop-red / holdout-green.",
        "avgR = mean(pnl/risk) on Trade.risk. 2R and trail trigger on bar H/L, fill next open.",
        "Chassis: channel_position (with-trend), yday_level_break (free), failed_yday_break (new, free).",
        "Six experiments only. No retry of exact dead Arrow 6 (track, rule, stance) pairs. No 12:00-16:00. No Arrow 8.",
        "",
        f"{'track':<6} {'id':<32} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(
            f"{r['track']:<6} {r['name']:<32} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} {h['max_dd']:10.2f} {flag:>6}"
        )
        lines.append(f"       develop {_fmt(r['develop'], holdout=False)}")
        lines.append(f"       holdout {_fmt(r['holdout'], holdout=True)}")
    if false_green:
        lines.append("")
        lines.append("NO* = holdout >= $200 but develop is red — not a pass:")
        for r in false_green:
            lines.append(
                f"  {r['track']}/{r['name']}: develop ${r['develop']['per_day']:.2f}/day holdout ${r['holdout']['per_day']:.2f}/day"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow07_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 7",
        "",
        verdict,
        "",
        "Same Tracks A and B. No new hours. Six experiments only: failed_yday_break with baseline / 2R / time-box 10:45; "
        "channel_position with 2R / trail-after-1R; yday_level_break with tight book (2 positions, 4 entries) + 2R. "
        "Did not retry exact dead Arrow 6 (track, rule, stance) pairs. Did not promote develop-red / holdout-green. "
        "Pass = holdout >= $200/day and develop not red.",
        "",
        "Engine: 2R target = entry +/- 2 x stop distance; trail after close >= +1R (stop to entry, then 0.5% from favorable extreme). "
        "Stops/targets trigger on bar H/L, fill next open. Time-box flattens at first tradeable open >= 10:45.",
        "",
        "What died (holdout < $200, or holdout green with red develop):",
    ]
    for r in results:
        if _promotable(r):
            continue
        bits.append(
            f"- Track {r['track']} {r['name']}: "
            f"holdout ${r['holdout']['per_day']:.2f}/day develop ${r['develop']['per_day']:.2f}/day "
            f"trades_holdout={r['holdout']['n_trades']} avgR={r['holdout']['avg_r']:.3f}. "
            "Do not retry this exact (track, id) without a new costed reason."
        )
    if promo:
        bits.append("")
        bits.append("Promotable: " + ", ".join(f"{r['track']}/{r['name']}" for r in promo))
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
