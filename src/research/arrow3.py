from __future__ import annotations

import math
import os
import random
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import BARS_DIR, ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.split import develop_holdout
from research.strategies import (
    first5_volume,
    gap_fade_signals,
    open_drive_signals,
    vwap_reclaim_signals,
)

ET = ZoneInfo("America/New_York")
GRIDS = {
    "cash": [None],
    "gap_fade": [3.0, 5.0, 8.0],
    "open_drive": [1.5, 2.0, 3.0],
    "vwap_reclaim": [3.0, 5.0, 8.0],
}


def _session_dir(d: date) -> Path:
    return BARS_DIR / f"session_date={d.isoformat()}"


def _read_session_bars(d: date) -> pl.DataFrame:
    folder = _session_dir(d)
    files = list(folder.glob("*.parquet"))
    if not files:
        return pl.DataFrame()
    return pl.read_parquet(files)


def _split_by_symbol(df: pl.DataFrame) -> dict[str, pl.DataFrame]:
    if df.height == 0:
        return {}
    out: dict[str, pl.DataFrame] = {}
    for key, part in df.group_by("symbol"):
        sym = key[0] if isinstance(key, tuple) else key
        out[str(sym)] = part.sort("bar_start")
    return out


def _median_prior(
    history: dict[str, list[tuple[str, float]]], symbol: str, session: date, lookback: int = 10
) -> float | None:
    vals = history.get(symbol) or []
    iso = session.isoformat()
    vols = [v for d, v in vals if d < iso][-lookback:]
    if not vols:
        return None
    return float(statistics.median(vols))


def _first5_one(d: date) -> list[tuple[str, str, float]]:
    df = _read_session_bars(d)
    if df.height == 0:
        return []
    df = df.with_columns(pl.col("bar_start").dt.time().alias("t"))
    first5 = df.filter((pl.col("t") >= time(9, 30)) & (pl.col("t") <= time(9, 34)))
    if first5.height == 0:
        return []
    summed = first5.group_by("symbol").agg(pl.col("volume").fill_null(0).sum().alias("v"))
    iso = d.isoformat()
    return [(str(r["symbol"]), iso, float(r["v"])) for r in summed.iter_rows(named=True)]


def _build_first5_history(sessions: list[date], workers: int) -> dict[str, list[tuple[str, float]]]:
    hist: dict[str, list[tuple[str, float]]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(_first5_one, sessions):
            for sym, iso, vol in part:
                hist.setdefault(sym, []).append((iso, vol))
    for sym in hist:
        hist[sym].sort()
    return hist


def _signals_for(
    name: str,
    param,
    by_sym: dict[str, pl.DataFrame],
    elig: dict[str, dict],
    session: date,
    first5_hist: dict[tuple[str, str], float],
):
    if name == "cash":
        return []
    sigs = []
    for sym, bars in by_sym.items():
        meta = elig.get(sym)
        if not meta:
            continue
        prior = float(meta["prior_close"] or 0.0)
        if name == "gap_fade":
            sigs.extend(gap_fade_signals(bars, prior, float(param)))
        elif name == "open_drive":
            f5 = first5_volume(bars)
            for d, v in first5_hist.get(sym, []):
                if d == session.isoformat():
                    f5 = v
                    break
            med = _median_prior(first5_hist, sym, session)
            if med is None:
                continue
            sigs.extend(open_drive_signals(bars, f5, med, float(param)))
        elif name == "vwap_reclaim":
            sigs.extend(vwap_reclaim_signals(bars, float(param), prior))
    return sigs


def _replay_one_session(args: tuple) -> list[dict]:
    """Load a session once; score every named rule/grid on it."""
    session_iso, first5_hist = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(ELIGIBILITY).filter(
        (pl.col("session_date") == session) & (pl.col("eligible"))
    )
    empty = []
    for name, grid in GRIDS.items():
        for param in grid:
            empty.append(
                {"session": session_iso, "name": name, "param": param, "pnl": 0.0, "trades": []}
            )
    if elig_df.height == 0:
        return empty
    keep = set(elig_df["symbol"].to_list())
    bars = _read_session_bars(session)
    if bars.height == 0:
        return empty
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    out = []
    for name, grid in GRIDS.items():
        for param in grid:
            if name == "cash":
                out.append(
                    {"session": session_iso, "name": name, "param": param, "pnl": 0.0, "trades": []}
                )
                continue
            sigs = _signals_for(name, param, by_sym, meta, session, first5_hist)
            trades = replay_session(by_sym, sigs, prior_dv)
            out.append(
                {
                    "session": session_iso,
                    "name": name,
                    "param": param,
                    "pnl": sum(t.pnl for t in trades),
                    "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
                }
            )
    return out


def bootstrap_ci(daily: list[float], *, n_boot: int = 1000, seed: int = 17) -> tuple[float, float]:
    n = len(daily)
    if n == 0:
        return 0.0, 0.0
    rng = random.Random(seed)
    boots: list[float] = []
    for _ in range(n_boot):
        s = 0.0
        for _i in range(n):
            s += daily[rng.randrange(n)]
        boots.append(s / n)
    boots.sort()
    lo = boots[int(0.025 * (n_boot - 1))]
    hi = boots[int(0.975 * (n_boot - 1))]
    return lo, hi


def _summarize(daily: list[float], trades: list[dict], n_sessions: int) -> dict:
    total = sum(daily)
    per_day = total / n_sessions if n_sessions else 0.0
    n_tr = len(trades)
    wins = sum(1 for t in trades if t["win"])
    hit = wins / n_tr if n_tr else 0.0
    rs = [t["pnl"] / t["risk"] for t in trades if t.get("risk")]
    avg_r = (sum(rs) / len(rs)) if rs else 0.0
    peak = 0.0
    eq = 0.0
    max_dd = 0.0
    for x in daily:
        eq += x
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
    n = len(daily)
    if n >= 2:
        std_day = float(statistics.stdev(daily))
        se_day = std_day / math.sqrt(n)
        t_stat = per_day / se_day if se_day > 1e-15 else 0.0
    else:
        std_day = 0.0
        se_day = 0.0
        t_stat = 0.0
    ci_lo, ci_hi = bootstrap_ci(daily)
    return {
        "pnl_total": total,
        "per_day": per_day,
        "n_trades": n_tr,
        "hit_rate": hit,
        "avg_r": avg_r,
        "max_dd": max_dd,
        "clears_200": per_day >= FAILURE_LINE,
        "std_day": std_day,
        "se_day": se_day,
        "t_stat": t_stat,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
    }


def run_arrow3(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sessions = list(WARMUP_SESSIONS) + study_sessions()
    print(
        f"research start mode=arrow3 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} n={len(develop)} "
        f"holdout={holdout[0]}..{holdout[-1]} n={len(holdout)}",
        flush=True,
    )
    print("precompute first-5-minute volumes (warmup+study)", flush=True)
    first5 = _build_first5_history(all_sessions, workers)
    print(f"first5 keys={len(first5)}", flush=True)

    jobs = [(d.isoformat(), first5) for d in develop + holdout]
    prog = Progress(len(jobs), "arrow3")
    prog.start_heartbeat()
    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one_session, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk)
            last = chunk[0]["session"] if chunk else ""
            ntr = sum(len(r["trades"]) for r in chunk)
            prog.mark(last, rows=ntr)
            prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}

    results = []
    for name, grid in GRIDS.items():
        scored = []
        for param in grid:
            dev_rows = [r for r in rows if r["name"] == name and r["param"] == param and r["session"] in develop_set]
            daily = [r["pnl"] for r in sorted(dev_rows, key=lambda x: x["session"])]
            # one pnl per session
            by_s = {r["session"]: r["pnl"] for r in dev_rows}
            daily = [by_s.get(d.isoformat(), 0.0) for d in develop]
            trades = [t for r in dev_rows for t in r["trades"]]
            sm = _summarize(daily, trades, len(develop))
            scored.append((param, sm, daily, trades))
        if name == "cash":
            best = scored[0]
        else:
            best = max(scored, key=lambda x: (x[1]["per_day"], -abs(float(x[0] or 0))))
        param, dev_sm, _, _ = best
        hol_rows = [r for r in rows if r["name"] == name and r["param"] == param and r["session"] in holdout_set]
        by_s = {r["session"]: r["pnl"] for r in hol_rows}
        hol_daily = [by_s.get(d.isoformat(), 0.0) for d in holdout]
        hol_trades = [t for r in hol_rows for t in r["trades"]]
        hol_sm = _summarize(hol_daily, hol_trades, len(holdout))
        results.append(
            {
                "name": name,
                "param": param,
                "grid": grid,
                "develop": dev_sm,
                "holdout": hol_sm,
            }
        )

    _write_reports(results, workers, cpu, develop, holdout)
    return 0


def _fmt(sm: dict, *, holdout: bool) -> str:
    extra = (
        f"  vs_$200={'YES' if sm['clears_200'] else 'NO'}  vs_$300-500={'YES' if sm['per_day'] >= TARGET_LO else 'NO'}"
        if holdout
        else ""
    )
    disp = (
        f"  std={sm.get('std_day', 0.0):.2f}  se={sm.get('se_day', 0.0):.2f}  "
        f"t={sm.get('t_stat', 0.0):.2f}  ci95=[{sm.get('ci_lo', 0.0):.2f},{sm.get('ci_hi', 0.0):.2f}]"
    )
    return (
        f"$/day={sm['per_day']:.2f}  trades={sm['n_trades']}  hit={sm['hit_rate']:.3f}  "
        f"avgR={sm['avg_r']:.3f}  maxDD$={sm['max_dd']:.2f}{disp}{extra}"
    )


def _write_reports(results, workers, cpu, develop, holdout) -> None:
    any_clear = any(r["holdout"]["clears_200"] for r in results if r["name"] != "cash")
    names = [r["name"] for r in results if r["holdout"]["clears_200"] and r["name"] != "cash"]
    if any_clear:
        verdict = f"VERDICT: HOLD OUT CLEARS $200 — {', '.join(names)}"
    else:
        verdict = "VERDICT: FAIL — no named rule printed ≥ $200/day net on holdout"

    lines = [
        "Arrow 3 — costed 1m replay (Lab A)",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "fills: next tradeable bar OPEN after signal close (no same-bar OHLC fills)",
        "costs: $0.005/share + 1x spread proxy max($0.01, 0.10% of price) PER SIDE; round trip = both sides",
        "size: risk $200 / stop_distance, notional cap min(10% of $100k, 2% prior-day dollar volume)",
        "book: max 5 positions, 10 entries/session, $1000 risk outstanding",
        "entries RTH 09:30-12:00; premarket features only; warmup has no PnL",
        "zero-volume / non-finite OHLC bars are not trades",
        "",
    ]
    for r in results:
        lines.append(f"=== {r['name']}  chosen_param={r['param']}  grid={r['grid']} ===")
        lines.append(f"  develop  {_fmt(r['develop'], holdout=False)}")
        lines.append(f"  holdout  {_fmt(r['holdout'], holdout=True)}")
        lines.append("")
    text = "\n".join(lines)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow03_results.txt").write_text(text + "\n", encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    dead = [r for r in results if r["name"] != "cash" and not r["holdout"]["clears_200"]]
    alive = [r for r in results if r["name"] != "cash" and r["holdout"]["clears_200"]]
    log_bits = [
        f"## {stamp} — Arrow 3",
        "",
        verdict,
        "",
        "Tried (only these): cash; gap-fade X in {3,5,8}; open-drive Y in {1.5,2.0,3.0}; "
        "RTH VWAP reclaim min-price in {3,5,8}. Parameters picked on develop $/day only; holdout once.",
        "",
    ]
    if alive:
        log_bits.append("Cleared holdout $200: " + ", ".join(f"{r['name']} param={r['param']}" for r in alive))
    else:
        log_bits.append("Nothing cleared the $200 holdout line.")
    log_bits.append("")
    log_bits.append("What died:")
    for r in dead:
        log_bits.append(
            f"- {r['name']} (param {r['param']}): holdout ${r['holdout']['per_day']:.2f}/day, "
            f"develop ${r['develop']['per_day']:.2f}/day, trades_holdout={r['holdout']['n_trades']}. "
            "Do not retry this exact grid without a new costed reason."
        )
    log_bits.append("")
    log_bits.append("Do not retry in Arrow 3: extra indicators, ML, MACD, extra setups, peeking holdout.")
    log_bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(log_bits) + "\n", encoding="utf-8")
