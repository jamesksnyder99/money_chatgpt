from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _read_session_bars, _split_by_symbol, _summarize
from research.arrow4 import _filter_track_a, _filter_track_b
from research.arrow5 import _build_stats, _maps_from_elig
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.split import develop_holdout
from research.strategies8 import (
    filter_breadth,
    filter_cost_gate,
    opening_range,
    orb_wide_signals,
    three_day_hl_signals,
    width_ok,
)
from research.trend import prior10

ET = ZoneInfo("America/New_York")

# Six experiments only. Do not retry dead Arrow 6/7 pairs or channel|2R / channel|trail.
IDS = (
    "orb_wide|baseline",
    "orb_wide|2R",
    "orb_wide|trail",
    "orb_wide|breadth",
    "orb_wide|cost_gate",
    "three_day_hl|2R",
)


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, _pc, _dv, stats = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty_rows = [
        {"session": session_iso, "track": track, "name": n, "pnl": 0.0, "trades": []}
        for n in IDS
    ]
    counts = {"or": 0, "width_fail": 0, "width_ok": 0, "fired": 0}
    if elig_df.height == 0:
        return {"rows": empty_rows, "counts": counts}
    bars = _read_session_bars(session)
    if bars.height == 0:
        return {"rows": empty_rows, "counts": counts}
    keep = set(elig_df["symbol"].to_list())
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    prior = prior10(session) or []
    d1, d2, d3 = (prior[-3], prior[-2], prior[-1]) if len(prior) >= 3 else (None, None, None)

    orb_base: list = []
    open_entries: list = []
    for sym, sdf in by_sym.items():
        rng = opening_range(sdf)
        if rng is not None:
            counts["or"] += 1
            _hi, _lo, w = rng
            if width_ok(w):
                counts["width_ok"] += 1
            else:
                counts["width_fail"] += 1
        fired = orb_wide_signals(sdf)
        if fired:
            counts["fired"] += 1
            orb_base.extend(fired)
        if d1 is None:
            continue
        m = meta.get(sym) or {}
        prior_c = m.get("prior_close")
        prior_c = float(prior_c) if prior_c is not None else None
        lows, highs = [], []
        for d in (d1, d2, d3):
            row = stats.get((sym, d.isoformat())) if d is not None else None
            lows.append(row["low"] if row else None)
            highs.append(row["high"] if row else None)
        open_entries.extend(
            three_day_hl_signals(sdf, tuple(lows), tuple(highs), prior_c)
        )

    orb_breadth = filter_breadth(orb_base, by_sym)
    orb_cost = filter_cost_gate(orb_base, by_sym)

    runs = (
        ("orb_wide|baseline", orb_base, {}),
        ("orb_wide|2R", orb_base, {"take_2r": True}),
        ("orb_wide|trail", orb_base, {"trail_after_1r": True}),
        ("orb_wide|breadth", orb_breadth, {}),
        ("orb_wide|cost_gate", orb_cost, {}),
    )
    rows = []
    for exp_id, sigs, kwargs in runs:
        trades = replay_session(by_sym, sigs, prior_dv, **kwargs)
        rows.append(
            {
                "session": session_iso,
                "track": track,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    trades = replay_session(by_sym, [], prior_dv, rth_open_entries=open_entries, take_2r=True)
    rows.append(
        {
            "session": session_iso,
            "track": track,
            "name": "three_day_hl|2R",
            "pnl": sum(t.pnl for t in trades),
            "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
        }
    )
    return {"rows": rows, "counts": counts}


def run_arrow8(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    print(
        f"research start mode=arrow8 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "engine: Arrow 7 book flags (take_2r, trail_after_1r); orb_wide 1-4% OR; "
        "breadth vs book-median; cost gate 0.25R; three_day_hl rth_open + 2R. No new hours.",
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
    prog = Progress(len(jobs), "arrow8")
    prog.start_heartbeat()
    rows: list[dict] = []
    counts = {
        "A": {"or": 0, "width_fail": 0, "width_ok": 0, "fired": 0},
        "B": {"or": 0, "width_fail": 0, "width_ok": 0, "fired": 0},
    }
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk["rows"])
            trk = chunk["rows"][0]["track"] if chunk["rows"] else "A"
            for k, v in chunk["counts"].items():
                counts[trk][k] += v
            prog.mark(chunk["rows"][0]["session"] if chunk["rows"] else "", rows=len(chunk["rows"]))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    _write_reports(rows, counts, workers, cpu, develop, holdout, capped)
    return 0


def _write_reports(rows, counts, workers, cpu, develop, holdout, capped) -> None:
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
            "VERDICT: FAIL — no Arrow 8 experiment has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass."
        )

    def _orb_line(trk: str) -> str:
        c = counts[trk]
        return (
            f"  Track {trk}: or_names={c['or']} width_fail={c['width_fail']} "
            f"width_ok={c['width_ok']} fired={c['fired']}"
        )

    lines = [
        "Arrow 8 — wide-stop opening range + selection",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "Pass = holdout >= $200/day AND develop not red. Do not promote develop-red / holdout-green.",
        "orb_wide: 09:30-09:44 range, W in 1%-4%, stop = other side of range. Free of 10d trend.",
        "Reuse Arrow 7 book flags (take_2r, trail_after_1r). Did not rerun channel|2R or channel|trail.",
        "No retry of exact dead Arrow 6/7 pairs. No 12:00-16:00. No Arrow 9.",
        "",
        "orb_wide width band (study name-days with an opening range):",
        _orb_line("A"),
        _orb_line("B"),
        "",
        f"{'track':<6} {'id':<28} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(
            f"{r['track']:<6} {r['name']:<28} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
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
    (REPORTS / "arrow08_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 8",
        "",
        verdict,
        "",
        "Same Tracks A and B. No new hours. Six experiments only: orb_wide baseline / 2R / trail / "
        "breadth-vs-book-median / cost gate (skip if round-trip cost > 0.25R); three_day_hl with 2R. "
        "Did not retry exact dead Arrow 6/7 pairs. Did not rerun channel|2R or channel|trail. "
        "Pass = holdout >= $200/day and develop not red.",
        "",
        "orb_wide width band:",
        _orb_line("A"),
        _orb_line("B"),
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
