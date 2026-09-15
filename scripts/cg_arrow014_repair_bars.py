"""CG Arrow 014 — acquire the minute bars the August 2025 eligibility extension exposed.

Arrow 013 built its minute universe from the eligibility layer it had, which stopped on
2025-08-01, and reused the separately authenticated 2025-26 study tree for August 2025. Phase 0A
then extended eligibility across August 2025, and the August cohorts turned out to need two
different kinds of observation neither source held: securities the Arrow 013 minute universe
never contained, and securities it did contain whose August sessions the study tree does not
carry. Candidates in both classes had no bars at their ranking endpoint, so the ranking rule
could not rank them at all.

That is a coverage gap, not a property of the securities, and the lab's rule is to resolve the
gap rather than to drop the candidate: a name that cannot be ranked might belong in the top
eight, and quietly excluding it would be choosing the selection by hand.

The gap is therefore defined by the direct question — does any source resolve for this
symbol-session — rather than by membership of a universe list, because the universe test sees
only the first class.

The bars land in `data/holdout2024/repair/bars`, which `candidate_paths` resolves LAST. A
gap-fill tree that sorts after every existing source can supply an observation nothing else
has and can never replace one that already exists, so this acquisition cannot alter a single
previously certified observation.

No ranking, selection or performance is computed here.

Usage:
  python scripts/cg_arrow014_repair_bars.py --mode ranking  [--workers 8] [--dry-run]
  python scripts/cg_arrow014_repair_bars.py --mode corridor [--workers 8] [--dry-run]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402
from thetadata.errors import NoDataFoundError  # noqa: E402

from ingest import holdout2024 as H  # noqa: E402
from ingest.bars import normalize_ohlc_full  # noqa: E402
from ingest.paths import REPO_ROOT, safe_symbol_filename  # noqa: E402
from ingest.theta_pool import ThetaLimiter, call_theta  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    HOLDOUT_REPAIR_BARS, candidate_paths, dump_json, read_json, stamp,
)

MAX_CONCURRENCY = 8
SESSION_FAILURE_ABORT = 50
LOOKBACK = 15
FEATURE_WINDOW = 20
LOG: list[str] = []
T0 = time.monotonic()
_consecutive_session_failures = 0


class SessionLost(RuntimeError):
    pass


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def repair_path(d: date, symbol: str) -> Path:
    return HOLDOUT_REPAIR_BARS / d.isoformat() / (safe_symbol_filename(symbol) + ".parquet")


def atomic_write(df: pl.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    df.write_parquet(tmp)
    tmp.replace(path)


def bar_schema() -> dict:
    return {"symbol": pl.String, "bar_start": pl.Datetime("ms", "America/New_York"),
            "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64,
            "volume": pl.Int64, "count": pl.Int64, "vwap": pl.Float64,
            "session_date": pl.Date, "session_part": pl.String, "is_warmup": pl.Boolean}


def _needed(mode: str) -> dict:
    """Symbol -> the corridor sessions the engine must be able to observe, by stage.

    `ranking` is every eligible candidate's two ranking endpoints on every one of the 52 signal
    sessions. That is what the ranking rule reads, so a gap there can silently drop a candidate
    that belongs in the top eight.

    `corridor` is the 21-session feature window and the fill-through-H10 lifecycle of every
    rank 1-20 name in the frozen membership — what the sizing rule, the causal pre-order and the
    three holds read.
    """
    field = read_json(H.WORK / "phase0b_field.json")
    want: dict[str, set] = defaultdict(set)
    if mode == "ranking":
        for iso, cands in field.items():
            i = HO.INDEX[date.fromisoformat(iso)]
            back = HO.FEATS[i - LOOKBACK]
            for sym in cands:
                want[sym].add(HO.FEATS[i])
                want[sym].add(back)
    else:
        membership = read_json(H.WORK / "phase0b_membership.json")
        for iso, top in membership["top8"].items():
            i = HO.INDEX[date.fromisoformat(iso)]
            for sym in top + membership["ranks_9_20"].get(iso, []):
                for j in range(max(0, i - FEATURE_WINDOW - 1),
                               min(len(HO.FEATS), i + 1 + max(HO.HOLDS) + 1)):
                    want[sym].add(HO.FEATS[j])
    return want


def gaps(mode: str = "ranking") -> dict:
    """Symbol -> the needed corridor sessions for which no source tree holds an observation.

    The criterion is the direct one: does anything resolve for this symbol-session. An earlier
    version asked instead whether the symbol was in the Arrow 013 minute universe, which missed
    a whole class of gap — securities that are in that universe but whose August 2025 sessions
    were reused from the 2025-26 study tree, which does not carry them.
    """
    want = _needed(mode)
    out: dict[str, list[date]] = defaultdict(list)
    for sym, days in want.items():
        for d in sorted(days):
            if not any(p.is_file() for _, p in candidate_paths(d, sym)):
                out[sym].append(d)
    note(f"{mode} stage: {len(want):,} securities need "
         f"{sum(len(v) for v in want.values()):,} observations; securities with a gap: "
         f"{len(out):,}; missing symbol-sessions: {sum(len(v) for v in out.values()):,}")
    return dict(out)


def months_for(days: list[date]) -> list[tuple[date, date, str]]:
    by: dict[str, list[date]] = defaultdict(list)
    for d in days:
        by[d.strftime("%Y-%m")].append(d)
    return [(min(v), max(v), k) for k, v in sorted(by.items())]


def pull(client, limiter, symbol: str, start: date, end: date, chunk: str,
         wanted: set[date]) -> dict:
    """One symbol-month, written as immutable per-session partitions in the repair tree."""
    global _consecutive_session_failures
    todo = [d for d in H.sessions(start, end) if d in wanted and not repair_path(d, symbol).is_file()]
    if not todo:
        return {"symbol": symbol, "chunk": chunk, "state": "ALREADY_LANDED", "sessions": 0, "rows": 0}
    try:
        df, _ = call_theta(limiter, client.stock_history_ohlc, symbol=symbol,
                           start_date=start, end_date=end, interval=H.INTERVAL, venue=H.VENUE,
                           start_time=H.PREMARKET_START, end_time=H.SESSION_WINDOW_END)
    except NoDataFoundError:
        # An explicit empty partition records that the vendor was asked and had nothing. It is
        # evidence of absence, which is not the same thing as a missing request.
        for d in todo:
            atomic_write(pl.DataFrame(schema=bar_schema()), repair_path(d, symbol))
        _consecutive_session_failures = 0
        return {"symbol": symbol, "chunk": chunk, "state": "VENDOR_NO_DATA",
                "sessions": len(todo), "rows": 0}
    except Exception as exc:  # noqa: BLE001
        if "session" in str(exc).lower() or "UNAUTHENTICATED" in str(exc):
            _consecutive_session_failures += 1
            if _consecutive_session_failures >= SESSION_FAILURE_ABORT:
                raise SessionLost(f"{_consecutive_session_failures} consecutive session failures")
        return {"symbol": symbol, "chunk": chunk, "state": "VENDOR_ERROR",
                "error_class": type(exc).__name__, "error": str(exc)[:200],
                "sessions": 0, "rows": 0}
    _consecutive_session_failures = 0
    norm = normalize_ohlc_full(df, symbol, False)
    by_day = {d: g for (d,), g in norm.group_by("session_date")} if norm.height else {}
    rows = 0
    for d in todo:
        out = by_day.get(d)
        out = out if out is not None else pl.DataFrame(schema=bar_schema())
        atomic_write(out, repair_path(d, symbol))
        rows += out.height
    return {"symbol": symbol, "chunk": chunk, "state": "RETRIEVED",
            "sessions": len(todo), "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--mode", choices=("ranking", "corridor"), default="ranking")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    workers = max(1, min(args.workers, MAX_CONCURRENCY))

    todo = gaps(args.mode)
    jobs = [(sym, lo, hi, chunk, set(days))
            for sym, days in sorted(todo.items())
            for lo, hi, chunk in months_for(days)]
    note(f"{len(jobs)} symbol-month vendor requests at concurrency {workers} (cap {MAX_CONCURRENCY})")
    if args.dry_run:
        dump_json(H.WORK / "repair_plan.json",
                  {"securities": len(todo), "requests": len(jobs),
                   "missing_symbol_sessions": sum(len(v) for v in todo.values()),
                   "by_symbol": {k: [d.isoformat() for d in v] for k, v in todo.items()}})
        note("dry run: plan written, nothing requested")
        return 0
    if not jobs:
        note("no gap remains")
        return 0

    stale = [q for q in H.WORK.glob("*.running") if q.stat().st_mtime > time.time() - 120]
    if stale:
        raise SystemExit(f"another acquisition stage holds a vendor session: {stale}")
    marker = H.WORK / "repair.running"
    marker.write_text(stamp(), encoding="utf-8")
    try:
        from theta.client import get_shared_client
        client = get_shared_client()
        limiter = ThetaLimiter(workers)
        counts: dict = defaultdict(int)
        total_rows, errors = 0, []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(pull, client, limiter, s, lo, hi, c, days)
                    for s, lo, hi, c, days in jobs]
            for n, f in enumerate(as_completed(futs), 1):
                r = f.result()
                counts[r["state"]] += 1
                total_rows += r["rows"]
                if r["state"] == "VENDOR_ERROR":
                    errors.append(r)
                if n % 25 == 0 or n == len(futs):
                    note(f"  {n}/{len(futs)} requests, {total_rows:,} rows, states {dict(counts)}")
    finally:
        marker.unlink(missing_ok=True)

    remaining = gaps(args.mode)
    dump_json(H.WORK / "repair_manifest.json", {
        "arrow": "CG Arrow 014", "stage": f"repair_bars_{args.mode}", "timestamp": stamp(),
        "why": ("the August 2025 eligibility extension admitted candidates outside the Arrow 013 "
                "minute universe, leaving four cohorts with unrankable candidates"),
        "tree": HOLDOUT_REPAIR_BARS.relative_to(REPO_ROOT).as_posix(),
        "precedence": "resolved last, so it can fill a gap but never shadow an existing observation",
        "mode": args.mode,
        "vendor_concurrency": workers, "requests": len(jobs), "counts": dict(counts),
        "rows": total_rows, "vendor_errors": errors[:20],
        "symbol_sessions_still_missing": sum(len(v) for v in remaining.values()),
        "securities_still_missing": len(remaining),
        "no_outcomes_calculated": True, "log": LOG})
    note(f"repair complete: {total_rows:,} rows; symbol-sessions still missing: "
         f"{sum(len(v) for v in remaining.values()):,}")
    return 0 if not remaining else 1


if __name__ == "__main__":
    sys.exit(main())
