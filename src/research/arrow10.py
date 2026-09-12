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
from research.arrow5 import _build_stats, _maps_from_elig
from research.book import replay_session
from research.character import dv_ranks
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, resample_15m_by_symbol, stitch_15m
from research.fills import tradeable_mask
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import (
    hhhl3_long,
    hhhl3_short,
    is_hot_cell,
    or15_break_long,
    or15_break_short,
    orbr5_high_retest,
    orbr5_low_retest,
    session_gap,
)
from research.trend import prior10, trend_for

ET = ZoneInfo("America/New_York")

# Six experiments. Long ids emit only longs; short ids emit only shorts.
EXPERIMENTS = (
    ("long_hot_or15|ema", "long", False),
    ("long_hot_or15|ema_hhhl|2R", "long", True),
    ("long_q5_orbr5|ema", "long", False),
    ("short_hot_or15|ema", "short", False),
    ("short_hot_or15|ema_hhhl|2R", "short", True),
    ("short_q5_orbr5|ema", "short", False),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
SIDES = {e[0]: e[1] for e in EXPERIMENTS}


def _bars15_one(d: date) -> dict[str, list]:
    df = _read_session_bars(d)
    if df.height == 0:
        return {}
    return resample_15m_by_symbol(df)


def _build_bars15(sessions: list[date], workers: int) -> dict[tuple[str, str], list]:
    out: dict[tuple[str, str], list] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_bars15_one, d): d for d in sessions}
        for fut in as_completed(futs):
            d = futs[fut]
            iso = d.isoformat()
            for sym, series in fut.result().items():
                out[(sym, iso)] = series
    return out


def _hhhl(sym: str, prior: list[date], stats: dict) -> tuple[tuple, tuple]:
    if len(prior) < 3:
        return (None, None, None), (None, None, None)
    lows, highs = [], []
    for d in prior[-3:]:
        row = stats.get((sym, d.isoformat()))
        lows.append(row["low"] if row else None)
        highs.append(row["high"] if row else None)
    return tuple(lows), tuple(highs)


def _ts_at(sdf: pl.DataFrame, t: time):
    df = sdf.filter(tradeable_mask(sdf)).with_columns(pl.col("bar_start").dt.time().alias("tt"))
    hit = df.filter(pl.col("tt") == t)
    if hit.height != 1:
        return None
    return hit["bar_start"][0]


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, pc, stats, bars15, sess_order, want_agree = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty_rows = [
        {"session": session_iso, "track": track, "name": n, "pnl": 0.0, "trades": []}
        for n in IDS
    ]
    hot = {"n": 0, "gapup": 0, "gapdn": 0}
    agree = {
        "n": 0,
        "agree": 0,
        "ema_long": 0,
        "ema_short": 0,
        "eod_up": 0,
        "eod_down": 0,
        "eod_flat": 0,
    }
    if elig_df.height == 0:
        return {"rows": empty_rows, "hot": hot, "agree": agree}
    bars = _read_session_bars(session)
    if bars.height == 0:
        return {"rows": empty_rows, "hot": hot, "agree": agree}
    keep = set(elig_df["symbol"].to_list())
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    ranks = dv_ranks(prior_dv)
    prior = prior10(session) or []

    buckets: dict[str, list] = {n: [] for n in IDS}

    for sym, sdf in by_sym.items():
        m = meta.get(sym) or {}
        prior_c = m.get("prior_close")
        prior_c = float(prior_c) if prior_c is not None else None
        rank = ranks.get(sym, 0.0)
        rng = opening_range(sdf)
        or_w = rng[2] if rng else None
        gap = session_gap(sdf, prior_c)
        stitched = stitch_15m(sym, session_iso, sess_order, bars15)
        lows, highs = _hhhl(sym, prior, stats)
        hot_ok = is_hot_cell(rank, gap, or_w)
        if hot_ok:
            hot["n"] += 1
            if gap is not None and gap > 0:
                hot["gapup"] += 1
            elif gap is not None and gap < 0:
                hot["gapdn"] += 1

        if want_agree:
            ts0945 = _ts_at(sdf, time(9, 45))
            stack0 = ema_stack(stitched, ts0945) if ts0945 is not None else None
            eod = trend_for(sym, session, pc)
            if stack0 is not None and eod is not None:
                agree["n"] += 1
                if stack0 == "long":
                    agree["ema_long"] += 1
                else:
                    agree["ema_short"] += 1
                if eod.side == "up":
                    agree["eod_up"] += 1
                elif eod.side == "down":
                    agree["eod_down"] += 1
                else:
                    agree["eod_flat"] += 1
                if (stack0 == "long" and eod.side == "up") or (
                    stack0 == "short" and eod.side == "down"
                ):
                    agree["agree"] += 1

        q5 = rank >= 0.80 - 1e-12

        if hot_ok and gap is not None and gap > 0:
            for sig in or15_break_long(sdf):
                stack = ema_stack(stitched, sig.signal_ts)
                if stack != "long":
                    continue
                buckets["long_hot_or15|ema"].append(sig)
                if hhhl3_long(lows):
                    buckets["long_hot_or15|ema_hhhl|2R"].append(sig)

        if hot_ok and gap is not None and gap < 0:
            for sig in or15_break_short(sdf):
                stack = ema_stack(stitched, sig.signal_ts)
                if stack != "short":
                    continue
                buckets["short_hot_or15|ema"].append(sig)
                if hhhl3_short(highs):
                    buckets["short_hot_or15|ema_hhhl|2R"].append(sig)

        if q5:
            for sig in orbr5_high_retest(sdf):
                stack = ema_stack(stitched, sig.signal_ts)
                if stack == "long":
                    buckets["long_q5_orbr5|ema"].append(sig)
            for sig in orbr5_low_retest(sdf):
                stack = ema_stack(stitched, sig.signal_ts)
                if stack == "short":
                    buckets["short_q5_orbr5|ema"].append(sig)

    rows = []
    for exp_id, _side, take_2r in EXPERIMENTS:
        sigs = buckets[exp_id]
        # belt: drop the wrong side if anything slipped through
        want = 1 if _side == "long" else -1
        sigs = [s for s in sigs if s.side == want]
        trades = replay_session(by_sym, sigs, prior_dv, take_2r=take_2r)
        rows.append(
            {
                "session": session_iso,
                "track": track,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    return {"rows": rows, "hot": hot, "agree": agree}


def run_arrow10(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow10 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "15m EMA 9/21 completed bars, stitched prior sessions; hhhl3; "
        "asymmetric long vs short hot-cell books. No Arrow 11.",
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
    print("precompute 1m session high/low + 15m closes", flush=True)
    stats = _build_stats(all_sess, workers)
    bars15 = _build_bars15(all_sess, workers)
    print(f"session_stats keys={len(stats)} bars15 keys={len(bars15)}", flush=True)

    develop_set = set(develop)
    jobs = []
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for d in develop + holdout:
            jobs.append(
                (d.isoformat(), track, path, pc, stats, bars15, sess_order, d in develop_set)
            )
    prog = Progress(len(jobs), "arrow10")
    prog.start_heartbeat()
    rows: list[dict] = []
    hot = {
        "A": {"n": 0, "gapup": 0, "gapdn": 0},
        "B": {"n": 0, "gapup": 0, "gapdn": 0},
    }
    agree = {
        "A": {"n": 0, "agree": 0, "ema_long": 0, "ema_short": 0, "eod_up": 0, "eod_down": 0, "eod_flat": 0},
        "B": {"n": 0, "agree": 0, "ema_long": 0, "ema_short": 0, "eod_up": 0, "eod_down": 0, "eod_flat": 0},
    }
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk["rows"])
            trk = chunk["rows"][0]["track"] if chunk["rows"] else "A"
            for k, v in chunk["hot"].items():
                hot[trk][k] += v
            for k, v in chunk["agree"].items():
                agree[trk][k] += v
            prog.mark(chunk["rows"][0]["session"] if chunk["rows"] else "", rows=len(chunk["rows"]))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    _write_reports(rows, hot, agree, workers, cpu, develop, holdout, capped)
    return 0


def _write_reports(rows, hot, agree, workers, cpu, develop, holdout, capped) -> None:
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
                    "side": SIDES[exp_id],
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
            "VERDICT: FAIL — no Arrow 10 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass."
        )

    def _agree_line(trk: str) -> str:
        a = agree[trk]
        pct = (100.0 * a["agree"] / a["n"]) if a["n"] else 0.0
        return (
            f"  Track {trk}: n={a['n']} agree={a['agree']} ({pct:.1f}%) "
            f"ema_long={a['ema_long']} ema_short={a['ema_short']} "
            f"eod_up={a['eod_up']} eod_down={a['eod_down']} eod_flat={a['eod_flat']}"
        )

    def _hot_line(trk: str) -> str:
        h = hot[trk]
        return f"  Track {trk}: hot={h['n']} gap_up={h['gapup']} gap_down={h['gapdn']}"

    lines = [
        "Arrow 10 — hot cell, 15m EMA trend, asymmetric long vs short",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "Pass = holdout >= $200/day AND develop not red.",
        "ema15 = 9/21 on stitched 15m closes, last completed bar before the decision. eod10 is a tag.",
        "Long ids emit only longs. Short ids emit only shorts. No Arrow 9 Q5+1-4% rerun. No Arrow 11.",
        "",
        "hot cell (dv_rank>=0.80 and |gap|>=2% and OR width>4%):",
        _hot_line("A"),
        _hot_line("B"),
        "",
        "ema15 vs eod10 on develop (descriptive; not an entry filter):",
        _agree_line("A"),
        _agree_line("B"),
        "",
        f"{'track':<6} {'side':<6} {'id':<28} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(
            f"{r['track']:<6} {r['side']:<6} {r['name']:<28} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
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
    (REPORTS / "arrow10_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 10",
        "",
        verdict,
        "",
        "Same Tracks A and B. No new hours. Six asymmetric books: long hot-cell gap-up 15m break + ema stack; "
        "long same + rising lows + 2R; long Q5 5-min high-retest + ema stack; short hot-cell gap-down 15m break + ema stack; "
        "short same + falling highs + 2R; short Q5 5-min low-retest + ema stack. "
        "Long ids emit only longs. Short ids emit only shorts. eod10 is a report tag. "
        "Did not rerun Arrow 9 Q5+1-4% books. No 7th. No Arrow 11.",
        "",
        "ema15 vs eod10 on develop:",
        _agree_line("A"),
        _agree_line("B"),
        "",
        "hot cell:",
        _hot_line("A"),
        _hot_line("B"),
        "",
        "What died (holdout < $200, or holdout green with red develop):",
    ]
    for r in results:
        if _promotable(r):
            continue
        bits.append(
            f"- Track {r['track']} {r['name']} ({r['side']}): "
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
