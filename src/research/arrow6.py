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
from research.arrow5 import (
    _adv_ok,
    _build_stats,
    _channel_hl,
    _lookback_ranges,
    _maps_from_elig,
    _pct,
)
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.split import develop_holdout
from research.strategies5 import (
    adv_expanding_free_signals,
    channel_position_signals,
    compression_expansion_free_signals,
    down_day_then_trend_signals,
    gap_with_trend_signals,
    late_with_trend_signals,
    rs_vs_book_free_signals,
    rth_return_at,
    session_pullback_signals,
    trend_open_signals,
    yday_level_break_free_signals,
)
from research.trend import prior10, trend_for

ET = ZoneInfo("America/New_York")

WITH_TREND = (
    "trend_open",
    "gap_with_trend",
    "down_day_then_trend",
    "late_with_trend",
    "channel_position",
)
FREE = (
    "session_pullback",
    "yday_level_break",
    "compression_expansion",
    "rs_vs_book",
    "adv_expanding",
)
RULES = WITH_TREND + FREE
STANCE = {n: "with-trend" for n in WITH_TREND} | {n: "free" for n in FREE}


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, pc, dv, stats = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty_rows = [
        {"session": session_iso, "track": track, "name": n, "pnl": 0.0, "trades": []}
        for n in RULES
    ]
    counts = {"up": 0, "down": 0, "flat": 0}
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

    trends = {}
    for sym in keep:
        tr = trend_for(sym, session, pc)
        trends[sym] = tr
        if tr is None or tr.side == "flat":
            counts["flat"] += 1
        elif tr.side == "up":
            counts["up"] += 1
        else:
            counts["down"] += 1

    rets_1015 = {sym: rth_return_at(sdf, time(10, 15)) for sym, sdf in by_sym.items()}
    book_rets = [v for v in rets_1015.values() if v is not None]
    p70, p30 = _pct(book_rets, 0.70), _pct(book_rets, 0.30)

    sigs: dict[str, list] = {n: [] for n in RULES}
    open_entries: list = []
    for sym, sdf in by_sym.items():
        tr = trends.get(sym)
        m = meta.get(sym) or {}
        prior_c = float(m.get("prior_close") or 0.0)
        yday = prior[-1] if prior else None
        ystat = stats.get((sym, yday.isoformat())) if yday else None
        rngs = _lookback_ranges(sym, prior, stats) if prior else []
        med_rng = sorted(rngs)[len(rngs) // 2] if len(rngs) == 10 else None
        prior_rng = ystat["range"] if ystat else None
        h, l = _channel_hl(sym, prior, stats) if prior else (None, None)
        mret = ystat["morning_ret"] if ystat else None
        yhi = ystat["high"] if ystat else None
        ylo = ystat["low"] if ystat else None

        # free rules — ignore 10d trend (may trade flat)
        sigs["session_pullback"].extend(session_pullback_signals(sdf))
        sigs["yday_level_break"].extend(yday_level_break_free_signals(sdf, yhi, ylo))
        sigs["compression_expansion"].extend(
            compression_expansion_free_signals(sdf, med_rng, prior_rng)
        )
        sigs["rs_vs_book"].extend(rs_vs_book_free_signals(sdf, rets_1015.get(sym), p70, p30))
        sigs["adv_expanding"].extend(
            adv_expanding_free_signals(sdf, _adv_ok(sym, session, prior, dv))
        )

        # with-trend — skip flat
        if tr is None or tr.side == "flat":
            continue
        open_entries.extend(trend_open_signals(sdf, tr))
        sigs["gap_with_trend"].extend(gap_with_trend_signals(sdf, tr, prior_c))
        sigs["down_day_then_trend"].extend(down_day_then_trend_signals(sdf, tr, mret))
        sigs["late_with_trend"].extend(late_with_trend_signals(sdf, tr))
        sigs["channel_position"].extend(channel_position_signals(sdf, tr, h, l))

    rows = []
    for name in RULES:
        if name == "trend_open":
            trades = replay_session(by_sym, [], prior_dv, rth_open_entries=open_entries)
        else:
            trades = replay_session(by_sym, sigs[name], prior_dv)
        rows.append(
            {
                "session": session_iso,
                "track": track,
                "name": name,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    return {"rows": rows, "counts": counts}


def run_arrow6(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    print(
        f"research start mode=arrow6 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "engine: Trade.risk avgR=mean(pnl/risk); RTH-only VWAP helper; "
        "queue by |score| + can_enter; next-open stop fills unchanged",
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
    prog = Progress(len(jobs), "arrow6")
    prog.start_heartbeat()
    rows: list[dict] = []
    counts = {"A": {"up": 0, "down": 0, "flat": 0}, "B": {"up": 0, "down": 0, "flat": 0}}
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
        for name in RULES:
            subset = [r for r in rows if r["track"] == track and r["name"] == name]
            pnl_map = {r["session"]: r for r in subset}
            daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
            daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
            tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
            tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
            results.append(
                {
                    "track": track,
                    "name": name,
                    "stance": STANCE[name],
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
            "VERDICT: FAIL — no Arrow 6 rule has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass (Arrow 5 B/down_day_then_trend warning)."
        )

    lines = [
        "Arrow 6 — engine repair + optional trend stance",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "avgR = mean(pnl/risk) on Trade.risk (not pnl/200). Next-open stop fills unchanged (slippage through stop is intended).",
        "RTH VWAP helper ignores premarket. Queue: sort |score| desc, can_enter before staging rth_open_entries.",
        "With-trend (skip flat): trend_open, gap_with_trend, down_day_then_trend, late_with_trend, channel_position.",
        "Free (ignore 10d trend): session_pullback, yday_level_break, compression_expansion, rs_vs_book, adv_expanding.",
        "Do not promote Arrow 5 B/down_day_then_trend (develop -$185 / holdout +$217 is not a pass).",
        "No 10d-trend fade book. No 11th rule.",
        "",
        "name-days (study sessions, tradable book):",
        f"  Track A up={counts['A']['up']} down={counts['A']['down']} flat={counts['A']['flat']}",
        f"  Track B up={counts['B']['up']} down={counts['B']['down']} flat={counts['B']['flat']}",
        "",
        f"{'track':<6} {'rule':<24} {'stance':<11} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(
            f"{r['track']:<6} {r['name']:<24} {r['stance']:<11} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
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
    (REPORTS / "arrow06_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 6",
        "",
        verdict,
        "",
        "Tether correction: Arrow 5 chained the 10-session EOD trend onto every mechanism. "
        "James's warmup-trend intent is a stance for some variants, not a lock on all of them. "
        "Arrow 6 with-trend: trend_open, gap_with_trend, down_day_then_trend, late_with_trend, channel_position (skip flat). "
        "Free: session_pullback (renamed from trend_pullback), yday_level_break, compression_expansion (15-min expansion direction), "
        "rs_vs_book, adv_expanding (09:30-10:00 session direction). No 10d-trend fade book. No 11th rule.",
        "",
        "Engine: Trade.risk stored; avgR = mean(pnl/risk); RTH-only VWAP helper; "
        "rth_open_entries sorted by |score| and can_enter before queue; next-open stop fills kept (slippage through stop intended).",
        "",
        "Develop-red / holdout-green is not a pass. Arrow 5 B/down_day_then_trend "
        "(develop about -$185/day, holdout +$217 on 22 days) is not promoted.",
        "",
        "What died (holdout < $200, or holdout green with red develop):",
    ]
    for r in results:
        if _promotable(r):
            continue
        bits.append(
            f"- Track {r['track']} {r['name']} ({r['stance']}): "
            f"holdout ${r['holdout']['per_day']:.2f}/day develop ${r['develop']['per_day']:.2f}/day "
            f"trades_holdout={r['holdout']['n_trades']} avgR={r['holdout']['avg_r']:.3f}. "
            "Do not retry this exact (track, rule, stance) without a new costed reason."
        )
    if promo:
        bits.append("")
        bits.append("Promotable: " + ", ".join(f"{r['track']}/{r['name']}" for r in promo))
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
