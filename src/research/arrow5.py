from __future__ import annotations

import math
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
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.fills import tradeable_mask
from research.split import develop_holdout
from research.strategies5 import (
    adv_expanding_signals,
    channel_position_signals,
    compression_expansion_signals,
    down_day_then_trend_signals,
    gap_with_trend_signals,
    late_with_trend_signals,
    rs_vs_book_signals,
    rth_return_at,
    trend_open_signals,
    trend_pullback_signals,
    yday_level_break_signals,
)
from research.trend import prior10, trend_for

ET = ZoneInfo("America/New_York")
RULES = (
    "trend_open",
    "trend_pullback",
    "yday_level_break",
    "gap_with_trend",
    "compression_expansion",
    "rs_vs_book",
    "down_day_then_trend",
    "adv_expanding",
    "late_with_trend",
    "channel_position",
)


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * p
    f = int(math.floor(k))
    c = min(f + 1, len(s) - 1)
    w = k - f
    return s[f] * (1.0 - w) + s[c] * w


def _maps_from_elig(elig: pl.DataFrame) -> tuple[dict, dict]:
    pc: dict[tuple[str, str], float] = {}
    dv: dict[tuple[str, str], float] = {}
    for rec in elig.select("symbol", "session_date", "prior_close", "prior_dollar_volume").iter_rows():
        sym, d, close, dollar = rec
        key = (str(sym), d.isoformat())
        if close is not None:
            pc[key] = float(close)
        if dollar is not None:
            dv[key] = float(dollar)
    return pc, dv


def _stats_one(d: date) -> dict[str, dict]:
    df = _read_session_bars(d)
    if df.height == 0:
        return {}
    ok = df.filter(tradeable_mask(df)).sort(["symbol", "bar_start"])
    if ok.height == 0:
        return {}
    ok = ok.with_columns(pl.col("bar_start").dt.time().alias("t"))
    hl = ok.group_by("symbol").agg(
        pl.col("high").max().alias("high"),
        pl.col("low").min().alias("low"),
        pl.col("close").sort_by("bar_start").last().alias("last_close"),
    )
    o930 = (
        ok.filter(pl.col("t") == time(9, 30))
        .select("symbol", pl.col("open").alias("open930"))
        .unique(subset=["symbol"])
    )
    joined = hl.join(o930, on="symbol", how="left")
    out: dict[str, dict] = {}
    iso = d.isoformat()
    for rec in joined.iter_rows(named=True):
        hi, lo = rec["high"], rec["low"]
        o = rec.get("open930")
        last = rec["last_close"]
        mret = None
        if o is not None and o and last is not None:
            mret = float(last) / float(o) - 1.0
        rng = float(hi) - float(lo) if hi is not None and lo is not None else None
        out[str(rec["symbol"])] = {
            "iso": iso,
            "high": float(hi) if hi is not None else None,
            "low": float(lo) if lo is not None else None,
            "range": rng,
            "open930": float(o) if o is not None else None,
            "last_close": float(last) if last is not None else None,
            "morning_ret": mret,
        }
    return out


def _build_stats(sessions: list[date], workers: int) -> dict[tuple[str, str], dict]:
    stats: dict[tuple[str, str], dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_stats_one, d): d for d in sessions}
        for fut in as_completed(futs):
            d = futs[fut]
            part = fut.result()
            iso = d.isoformat()
            for sym, row in part.items():
                stats[(sym, iso)] = row
    return stats


def _lookback_ranges(sym: str, prior: list[date], stats: dict) -> list[float]:
    out = []
    for d in prior:
        row = stats.get((sym, d.isoformat()))
        if row and row.get("range") is not None:
            out.append(float(row["range"]))
    return out


def _channel_hl(sym: str, prior: list[date], stats: dict) -> tuple[float | None, float | None]:
    hs, ls = [], []
    for d in prior:
        row = stats.get((sym, d.isoformat()))
        if not row:
            continue
        if row.get("high") is not None:
            hs.append(row["high"])
        if row.get("low") is not None:
            ls.append(row["low"])
    if not hs or not ls:
        return None, None
    return max(hs), min(ls)


def _adv_ok(sym: str, session: date, prior: list[date], dv: dict) -> bool:
    dvs = []
    for k in range(9):
        v = dv.get((sym, prior[k + 1].isoformat()))
        if v is None:
            return False
        dvs.append(v)
    v10 = dv.get((sym, session.isoformat()))
    if v10 is None:
        return False
    dvs.append(v10)
    med = sorted(dvs)[len(dvs) // 2]
    return v10 > med


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

    rets_1015 = {}
    for sym, sdf in by_sym.items():
        rets_1015[sym] = rth_return_at(sdf, time(10, 15))
    book_rets = [v for v in rets_1015.values() if v is not None]
    p70, p30 = _pct(book_rets, 0.70), _pct(book_rets, 0.30)

    sigs: dict[str, list] = {n: [] for n in RULES}
    open_entries = []
    for sym, sdf in by_sym.items():
        tr = trends.get(sym)
        if tr is None or tr.side == "flat":
            continue
        m = meta.get(sym) or {}
        prior_c = float(m.get("prior_close") or 0.0)
        yday = prior[-1] if prior else None
        ystat = stats.get((sym, yday.isoformat())) if yday else None
        rngs = _lookback_ranges(sym, prior, stats) if prior else []
        med_rng = sorted(rngs)[len(rngs) // 2] if len(rngs) == 10 else None
        prior_rng = ystat["range"] if ystat else None
        h, l = _channel_hl(sym, prior, stats) if prior else (None, None)
        mret = ystat["morning_ret"] if ystat else None

        open_entries.extend(trend_open_signals(sdf, tr))
        sigs["trend_pullback"].extend(trend_pullback_signals(sdf, tr))
        sigs["yday_level_break"].extend(
            yday_level_break_signals(
                sdf, tr, ystat["high"] if ystat else None, ystat["low"] if ystat else None
            )
        )
        sigs["gap_with_trend"].extend(gap_with_trend_signals(sdf, tr, prior_c))
        sigs["compression_expansion"].extend(
            compression_expansion_signals(sdf, tr, med_rng, prior_rng)
        )
        sigs["rs_vs_book"].extend(
            rs_vs_book_signals(sdf, tr, rets_1015.get(sym), p70, p30)
        )
        sigs["down_day_then_trend"].extend(down_day_then_trend_signals(sdf, tr, mret))
        sigs["adv_expanding"].extend(adv_expanding_signals(sdf, tr, _adv_ok(sym, session, prior, dv)))
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


def run_arrow5(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    print(
        f"research start mode=arrow5 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
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
    print(f"Track A rows={track_a.height} Track B rows={track_b.height} b_cap_file={b_path.exists()}", flush=True)

    pc, dv = _maps_from_elig(elig_all)
    print("precompute 1m session high/low/range/open", flush=True)
    stats = _build_stats(all_sess, workers)
    print(f"session_stats keys={len(stats)}", flush=True)

    jobs = []
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for d in develop + holdout:
            jobs.append((d.isoformat(), track, path, pc, dv, stats))
    prog = Progress(len(jobs), "arrow5")
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
                    "develop": _summarize(daily_dev, tr_dev, len(develop)),
                    "holdout": _summarize(daily_hol, tr_hol, len(holdout)),
                }
            )
    clears = [r for r in results if r["holdout"]["clears_200"]]
    if clears:
        verdict = "VERDICT: HOLD OUT CLEARS $200 — " + ", ".join(
            f"{r['track']}/{r['name']}" for r in clears
        )
    else:
        verdict = "VERDICT: FAIL — no Arrow 5 rule printed ≥ $200/day net on holdout"

    lines = [
        "Arrow 5 — ten trend-with mechanisms (warmup 10-session EOD)",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B used existing cap file={capped}",
        "trend: 10 prior official EOD closes; up=C10>C1 and C10>mean; down=inverse; flat=no trade",
        "never fade 10-session trend; no gap-fade / open-drive / vwap / 15m OR / Arrow4 swing",
        "",
        "name-days (study sessions, tradable book):",
        f"  Track A up={counts['A']['up']} down={counts['A']['down']} flat={counts['A']['flat']}",
        f"  Track B up={counts['B']['up']} down={counts['B']['down']} flat={counts['B']['flat']}",
        "",
        f"{'track':<6} {'rule':<24} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        lines.append(
            f"{r['track']:<6} {r['name']:<24} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} {h['max_dd']:10.2f} "
            f"{'YES' if h['clears_200'] else 'NO':>6}"
        )
        lines.append(f"       develop {_fmt(r['develop'], holdout=False)}")
        lines.append(f"       holdout {_fmt(r['holdout'], holdout=True)}")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow05_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    dead = [r for r in results if not r["holdout"]["clears_200"]]
    bits = [
        f"## {stamp} — Arrow 5",
        "",
        verdict,
        "",
        "Ten frozen trend-with rules on Track A ($10-30, ADV>=$5M) and Track B ($10-50, 400/day cap). "
        "Trend = 10 prior official EOD closes. Flat = no trade. Did not fade the 10-session trend. "
        "Did not rebuild gap-fade, open-drive, VWAP reclaim, 15-min OR-break, or Arrow 4 +1.5% swing.",
        "",
        "What died:",
    ]
    for r in dead:
        bits.append(
            f"- Track {r['track']} {r['name']}: holdout ${r['holdout']['per_day']:.2f}/day "
            f"develop ${r['develop']['per_day']:.2f}/day trades_holdout={r['holdout']['n_trades']}. "
            "Do not retry this exact (track, rule) without a new costed reason."
        )
    if clears:
        bits.append("")
        bits.append("Cleared: " + ", ".join(f"{r['track']}/{r['name']}" for r in clears))
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
