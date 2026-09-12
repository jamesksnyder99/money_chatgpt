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
from research.character import (
    dv_ranks,
    format_character_report,
    name_day_character,
    quintile,
    sessions_for_character,
    summarize_character,
)
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.signals import MINUTE_1100
from research.split import develop_holdout
from research.strategies8 import orb_wide_signals, three_day_hl_signals
from research.strategies9 import gap_continuation_signals, orb_matches_gap
from research.trend import prior10, trend_for

ET = ZoneInfo("America/New_York")

# Six frozen books. No 7th. No ML. No Arrow 8 cost_gate rerun.
IDS = (
    "orb_q5|baseline",
    "orb_q5|2R",
    "gap_q5|2R",
    "orb_q5_gapsign|trail",
    "three_day_q5|2R",
    "orb_q5|flat1100",
)


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, pc, stats, want_char = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty_rows = [
        {"session": session_iso, "track": track, "name": n, "pnl": 0.0, "trades": []}
        for n in IDS
    ]
    if elig_df.height == 0:
        return {"rows": empty_rows, "char": []}
    bars = _read_session_bars(session)
    if bars.height == 0:
        return {"rows": empty_rows, "char": []}
    keep = set(elig_df["symbol"].to_list())
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    ranks = dv_ranks(prior_dv)
    q5 = {s for s, r in ranks.items() if r >= 0.80 - 1e-12}
    prior = prior10(session) or []
    d1, d2, d3 = (prior[-3], prior[-2], prior[-1]) if len(prior) >= 3 else (None, None, None)

    orb_q5: list = []
    orb_gap: list = []
    gap_q5: list = []
    open_q5: list = []
    char_rows: list[dict] = []

    for sym, sdf in by_sym.items():
        m = meta.get(sym) or {}
        prior_c = m.get("prior_close")
        prior_c = float(prior_c) if prior_c is not None else None
        rank = ranks.get(sym, 0.0)
        if want_char:
            feat = name_day_character(sdf, prior_c)
            if feat is not None:
                tr = trend_for(sym, session, pc)
                side = tr.side if tr is not None else "flat"
                feat["session"] = session_iso
                feat["track"] = track
                feat["symbol"] = sym
                feat["dv_rank"] = rank
                feat["quintile"] = quintile(rank)
                feat["trend"] = side
                char_rows.append(feat)
        if sym not in q5:
            continue
        orb = orb_wide_signals(sdf)
        orb_q5.extend(orb)
        for sig in orb:
            if orb_matches_gap(sdf, prior_c, sig.side, min_abs_gap=0.01):
                orb_gap.append(sig)
        gap_q5.extend(gap_continuation_signals(sdf, prior_c, min_abs_gap=0.02))
        if d1 is None:
            continue
        lows, highs = [], []
        for d in (d1, d2, d3):
            row = stats.get((sym, d.isoformat())) if d is not None else None
            lows.append(row["low"] if row else None)
            highs.append(row["high"] if row else None)
        open_q5.extend(three_day_hl_signals(sdf, tuple(lows), tuple(highs), prior_c))

    runs = (
        ("orb_q5|baseline", orb_q5, {}, False),
        ("orb_q5|2R", orb_q5, {"take_2r": True}, False),
        ("gap_q5|2R", gap_q5, {"take_2r": True}, False),
        ("orb_q5_gapsign|trail", orb_gap, {"trail_after_1r": True}, False),
        ("three_day_q5|2R", open_q5, {"take_2r": True}, True),
        ("orb_q5|flat1100", orb_q5, {"flatten_at": MINUTE_1100}, False),
    )
    rows = []
    for exp_id, sigs, kwargs, rth_open in runs:
        if rth_open:
            trades = replay_session(by_sym, [], prior_dv, rth_open_entries=sigs, **kwargs)
        else:
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
    return {"rows": rows, "char": char_rows}


def run_arrow9(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    print(
        f"research start mode=arrow9 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "phase1 develop-only character; phase2 six frozen Q5 books "
        "(orb_wide / gap-continuation / three_day_hl). No cost_gate rerun. No Arrow 10.",
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

    pc, _dv = _maps_from_elig(elig_all)
    print("precompute 1m session high/low/range/open", flush=True)
    stats = _build_stats(all_sess, workers)
    print(f"session_stats keys={len(stats)}", flush=True)

    develop_set = set(develop)
    char_dates = sessions_for_character(develop + holdout, develop=develop)
    print(
        f"character dates={len(char_dates)} (holdout ignored); "
        f"first={char_dates[0] if char_dates else None} last={char_dates[-1] if char_dates else None}",
        flush=True,
    )

    jobs = []
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for d in develop + holdout:
            jobs.append((d.isoformat(), track, path, pc, stats, d in develop_set))
    prog = Progress(len(jobs), "arrow9")
    prog.start_heartbeat()
    rows: list[dict] = []
    char_rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk["rows"])
            char_rows.extend(chunk["char"])
            prog.mark(chunk["rows"][0]["session"] if chunk["rows"] else "", rows=len(chunk["rows"]))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    by_track = {
        "A": summarize_character([r for r in char_rows if r.get("track") == "A"]),
        "B": summarize_character([r for r in char_rows if r.get("track") == "B"]),
    }
    char_text = format_character_report(by_track, develop)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow09_character.txt").write_text(char_text, encoding="utf-8")
    print(char_text, flush=True)
    _write_results(rows, workers, cpu, develop, holdout, capped, char_text)
    return 0


def _write_results(rows, workers, cpu, develop, holdout, capped, char_text: str) -> None:
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
            "VERDICT: FAIL — no Arrow 9 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass."
        )

    para = ""
    marker = "Where movement lives (develop only):"
    if marker in char_text:
        para = char_text.split(marker, 1)[1].strip().split("\n", 1)[0].strip()

    lines = [
        "Arrow 9 — Q5 liquid names with a real OR and/or gap",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "Pass = holdout >= $200/day AND develop not red. Character used develop only.",
        "Six frozen books: orb_q5 baseline/2R/trail-gapsign/flat1100; gap_q5 2R continuation; three_day_q5 2R.",
        "No 7th id. No ML. No Arrow 8 cost_gate rerun. No 12:00-16:00. No Arrow 10.",
        "",
        f"{'track':<6} {'id':<24} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(
            f"{r['track']:<6} {r['name']:<24} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
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
    (REPORTS / "arrow09_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 9",
        "",
        verdict,
        "",
        "Phase 1 (develop only): mean post-09:44 range by DV quintile, |gap|, OR-width, 10d trend, "
        "and clock hour of the session extreme. Holdout was not used to choose buckets or the paragraph.",
        "",
        "Where movement lives: " + para,
        "",
        "Phase 2 six frozen books on that intended population (Q5 DV, wide OR and/or |gap|>=2%). "
        "orb_wide / gap-continuation / three_day_hl; manage baseline, 2R, trail, or 11:00 flatten. "
        "No 7th. No ML. No Arrow 8 cost_gate rerun.",
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
