"""CG Arrow 014 — pull a same-vintage end-of-day reference for the gap-fill sessions.

The gap-fill bars were acquired now; the end-of-day layer they were first checked against was
pulled for the 2025-26 study months earlier. Across August and September 2025 the two disagreed
more than the accepted data does on the very same sessions, and thinness only explained part of
it. A vendor tape is revised after the fact, so a new pull and an old pull are not the same
measurement, and comparing them measures vintage as much as quality.

This pulls the end-of-day report for exactly the repaired securities and sessions, now, so the
cross-check can be made like-for-like. It lands in its own tree and replaces nothing.

No ranking, selection or performance is computed here.

Usage: python scripts/cg_arrow014_repair_eod.py [--workers 8]
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
from ingest.paths import DATA, REPO_ROOT, safe_symbol_filename  # noqa: E402
from ingest.theta_pool import ThetaLimiter, call_theta  # noqa: E402
from verification.r4r5_data import HOLDOUT_REPAIR_BARS, dump_json, stamp  # noqa: E402

MAX_CONCURRENCY = 8
REPAIR_EOD = DATA / "holdout2024" / "repair" / "eod"
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def targets() -> dict:
    """Symbol -> the repaired sessions, grouped by calendar month for the vendor."""
    by: dict = defaultdict(set)
    for folder in sorted(HOLDOUT_REPAIR_BARS.iterdir()):
        d = date.fromisoformat(folder.name)
        for f in folder.glob("*.parquet"):
            by[f.stem].add(d)
    return {s: sorted(v) for s, v in by.items()}


def pull(client, limiter, symbol: str, lo: date, hi: date, chunk: str) -> dict:
    path = REPAIR_EOD / chunk / (safe_symbol_filename(symbol) + ".parquet")
    if path.is_file():
        return {"symbol": symbol, "chunk": chunk, "state": "ALREADY_LANDED", "rows": 0}
    try:
        df, _ = call_theta(limiter, client.stock_history_eod, symbol=symbol,
                           start_date=lo, end_date=hi)
    except NoDataFoundError:
        df = None
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "chunk": chunk, "state": "VENDOR_ERROR",
                "error": str(exc)[:200], "rows": 0}
    path.parent.mkdir(parents=True, exist_ok=True)
    if df is not None:
        from ingest.eligibility import eod_session_dates
        out = eod_session_dates(df.with_columns(pl.lit(symbol).alias("symbol")))
    else:
        out = pl.DataFrame(schema={"symbol": pl.String, "eod_date": pl.Date,
                                   "close": pl.Float64, "volume": pl.Float64})
    tmp = path.with_suffix(".tmp")
    out.write_parquet(tmp)
    tmp.replace(path)
    return {"symbol": symbol, "chunk": chunk,
            "state": "RETRIEVED" if df is not None else "VENDOR_NO_DATA",
            "rows": 0 if df is None else out.height}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    workers = max(1, min(args.workers, MAX_CONCURRENCY))

    want = targets()
    jobs = []
    for sym, days in sorted(want.items()):
        by_month: dict = defaultdict(list)
        for d in days:
            by_month[d.strftime("%Y-%m")].append(d)
        for chunk, ds in sorted(by_month.items()):
            jobs.append((sym, min(ds), max(ds), chunk))
    note(f"{len(want)} repaired securities, {len(jobs)} symbol-month end-of-day requests")

    stale = [q for q in H.WORK.glob("*.running") if q.stat().st_mtime > time.time() - 120]
    if stale:
        raise SystemExit(f"another acquisition stage holds a vendor session: {stale}")
    marker = H.WORK / "repair_eod.running"
    marker.write_text(stamp(), encoding="utf-8")
    counts: dict = defaultdict(int)
    rows = 0
    try:
        from theta.client import get_shared_client
        client = get_shared_client()
        limiter = ThetaLimiter(workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(pull, client, limiter, *j) for j in jobs]
            for n, f in enumerate(as_completed(futs), 1):
                r = f.result()
                counts[r["state"]] += 1
                rows += r["rows"]
                if n % 100 == 0 or n == len(futs):
                    note(f"  {n}/{len(futs)} requests, {rows:,} rows, {dict(counts)}")
    finally:
        marker.unlink(missing_ok=True)

    dump_json(H.WORK / "repair_eod_manifest.json", {
        "arrow": "CG Arrow 014", "stage": "repair_eod", "timestamp": stamp(),
        "why": ("a same-vintage end-of-day reference for the gap-fill bars, so the cross-check "
                "measures data quality rather than the gap between an old pull and a new one"),
        "tree": REPAIR_EOD.relative_to(REPO_ROOT).as_posix(),
        "securities": len(want), "requests": len(jobs), "counts": dict(counts), "rows": rows,
        "no_outcomes_calculated": True, "log": LOG})
    note(f"same-vintage end-of-day reference landed: {rows:,} rows, {dict(counts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
