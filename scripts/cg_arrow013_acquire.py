"""CG Arrow 013 — resumable, idempotent acquisition of the pristine holdout source layers.

Two stages, each independently resumable:

  eod     one request per symbol and calendar month over the full roster, which supplies the
          point-in-time eligibility inputs: prior close and prior-day dollar volume
  bars    one request per eligible symbol and calendar month of one-minute bars over the
          04:00 to 16:00 window, honouring each session's actual close

Discipline. Raw partitions land once and are never rewritten; a resume skips only a partition
that already exists and reads back cleanly. Writes are atomic through a temporary file and a
replace, so an interrupted run cannot leave a half-written partition. Vendor errors are
persisted separately from market data, so a failure can never be mistaken for an absence of
trading. Total vendor concurrency never exceeds eight across the process tree.

No strategy, ranking, selection or performance is computed anywhere in this file.

Usage:
  python scripts/cg_arrow013_acquire.py eod   [--workers 8]
  python scripts/cg_arrow013_acquire.py bars  [--workers 8] [--months 2024-08,...]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402
from thetadata.errors import NoDataFoundError  # noqa: E402

from ingest import holdout2024 as H  # noqa: E402
from ingest.bars import normalize_ohlc_full  # noqa: E402
from ingest.paths import SYMBOLS, safe_symbol_filename  # noqa: E402
from ingest.theta_pool import ThetaLimiter, call_theta  # noqa: E402
from verification.r4r5_data import dump_json, stamp  # noqa: E402

MAX_CONCURRENCY = 8
LOG: list[str] = []
T0 = time.monotonic()


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def atomic_write(df: pl.DataFrame, path: Path) -> None:
    """One writer per partition, and never a half-written file visible to a resume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp)
    tmp.replace(path)


def landed_ok(path: Path) -> bool:
    """A partition counts as landed only if it exists and reads back as a valid parquet."""
    if not path.exists():
        return False
    try:
        pl.read_parquet(path, n_rows=1)
        return True
    except Exception:  # noqa: BLE001
        return False


def roster() -> list[str]:
    return sorted(pl.read_parquet(SYMBOLS)["symbol"].to_list())


def errors_path(stage: str) -> Path:
    return H.WORK / f"vendor_errors_{stage}.jsonl"


def record_error(stage: str, **fields) -> None:
    errors_path(stage).parent.mkdir(parents=True, exist_ok=True)
    with errors_path(stage).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"stage": stage, "at": stamp(), **fields}) + "\n")


# ------------------------------------------------------------------ end of day
def _empty_eod(symbol: str) -> pl.DataFrame:
    return pl.DataFrame(schema={"symbol": pl.String, "eod_date": pl.Date,
                                "close": pl.Float64, "volume": pl.Int64})


def pull_one_eod(client, limiter, symbol: str, start: date, end: date, chunk: str) -> dict:
    path = H.raw_eod_path(symbol, chunk)
    if landed_ok(path):
        return {"symbol": symbol, "chunk": chunk, "state": "ALREADY_LANDED", "rows": None, "seconds": 0.0}
    try:
        df, elapsed = call_theta(limiter, client.stock_history_eod,
                                 symbol=symbol, start_date=start, end_date=end)
        from ingest.eligibility import eod_session_dates
        df = eod_session_dates(df.with_columns(pl.lit(symbol).alias("symbol")))
        atomic_write(df, path)
        return {"symbol": symbol, "chunk": chunk, "state": "RETRIEVED", "rows": df.height, "seconds": elapsed}
    except NoDataFoundError:
        # A documented "this security had no end-of-day record in this month" answer. It is a
        # real vendor state and is landed as an explicit empty partition, never as a zero value.
        atomic_write(_empty_eod(symbol), path)
        return {"symbol": symbol, "chunk": chunk, "state": "VENDOR_NO_DATA", "rows": 0, "seconds": 0.0}
    except Exception as exc:  # noqa: BLE001
        record_error("eod", symbol=symbol, chunk=chunk,
                     error_class=type(exc).__name__, error_message=str(exc)[:400])
        return {"symbol": symbol, "chunk": chunk, "state": "VENDOR_ERROR",
                "error_class": type(exc).__name__, "rows": None, "seconds": 0.0}


def stage_eod(client, limiter, workers: int) -> dict:
    syms = roster()
    chunks = H.eod_chunks()
    note(f"end-of-day stage: {len(syms)} roster symbols x {len(chunks)} months = {len(syms) * len(chunks)} partitions")
    counts = {"RETRIEVED": 0, "VENDOR_NO_DATA": 0, "ALREADY_LANDED": 0, "VENDOR_ERROR": 0}
    for start, end, chunk in chunks:
        need = [s for s in syms if not landed_ok(H.raw_eod_path(s, chunk))]
        note(f"  chunk {chunk} {start}..{end}: {len(need)} of {len(syms)} to retrieve")
        if not need:
            counts["ALREADY_LANDED"] += len(syms)
            continue
        t = time.monotonic()
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(pull_one_eod, client, limiter, s, start, end, chunk) for s in need]
            for fut in as_completed(futs):
                r = fut.result()
                counts[r["state"]] = counts.get(r["state"], 0) + 1
                done += 1
                if done % 2500 == 0:
                    el = time.monotonic() - t
                    note(f"    {chunk}: {done}/{len(need)} in {el:.0f}s ({done / el:.1f}/s)")
        counts["ALREADY_LANDED"] += len(syms) - len(need)
        note(f"  chunk {chunk} complete in {time.monotonic() - t:.0f}s")
    note(f"end-of-day stage counts: {counts}")
    return counts


# ------------------------------------------------------------------ minute bars
def pull_one_month_bars(client, limiter, symbol: str, start: date, end: date, chunk: str) -> dict:
    """One symbol-month of one-minute bars, split into immutable per-session partitions."""
    days = H.sessions(start, end)
    missing = [d for d in days if not landed_ok(H.raw_bar_path(d, symbol))]
    if not missing:
        return {"symbol": symbol, "chunk": chunk, "state": "ALREADY_LANDED", "sessions": 0, "rows": 0, "seconds": 0.0}
    try:
        df, elapsed = call_theta(limiter, client.stock_history_ohlc, symbol=symbol,
                                 start_date=start, end_date=end, interval=H.INTERVAL, venue=H.VENUE,
                                 start_time=H.PREMARKET_START, end_time=H.SESSION_WINDOW_END)
    except NoDataFoundError:
        for d in missing:
            atomic_write(pl.DataFrame(schema=_bar_schema()), H.raw_bar_path(d, symbol))
        return {"symbol": symbol, "chunk": chunk, "state": "VENDOR_NO_DATA",
                "sessions": len(missing), "rows": 0, "seconds": 0.0}
    except Exception as exc:  # noqa: BLE001
        record_error("bars", symbol=symbol, chunk=chunk,
                     error_class=type(exc).__name__, error_message=str(exc)[:400])
        return {"symbol": symbol, "chunk": chunk, "state": "VENDOR_ERROR",
                "error_class": type(exc).__name__, "sessions": 0, "rows": 0, "seconds": 0.0}
    norm = normalize_ohlc_full(df, symbol, False)
    rows = 0
    by_day = {d: g for (d,), g in norm.group_by("session_date")} if norm.height else {}
    for d in missing:
        g = by_day.get(d)
        out = g if g is not None else pl.DataFrame(schema=_bar_schema())
        # a session outside the window, or one the security did not trade, lands as an explicit
        # empty partition so a resume never re-requests it and never confuses it with an error
        atomic_write(out, H.raw_bar_path(d, symbol))
        rows += out.height
    return {"symbol": symbol, "chunk": chunk, "state": "RETRIEVED",
            "sessions": len(missing), "rows": rows, "seconds": elapsed}


def _bar_schema() -> dict:
    return {"symbol": pl.String, "bar_start": pl.Datetime("ms", "America/New_York"),
            "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64,
            "volume": pl.Int64, "count": pl.Int64, "vwap": pl.Float64,
            "session_date": pl.Date, "session_part": pl.String, "is_warmup": pl.Boolean}


def minute_universe() -> list[str]:
    """Symbols whose minute bars the holdout needs, from the certified eligibility layer.

    This is the union over the acquisition window of every security that was point-in-time
    eligible on at least one session, plus every security eligible on a session adjacent to
    the window so ranking and feature corridors are complete. It is a universe definition, not
    a selection: no return is computed and no security is ordered or preferred.
    """
    path = H.WORK / "eligibility.parquet"
    if not path.exists():
        raise SystemExit("eligibility layer missing; run the eod stage and cg_arrow013_eligibility.py first")
    el = pl.read_parquet(path)
    return sorted(el.filter(pl.col("eligible"))["symbol"].unique().to_list())


def stage_bars(client, limiter, workers: int, months: list[str] | None) -> dict:
    syms = minute_universe()
    chunks = [c for c in H.eod_chunks() if not months or c[2] in months]
    note(f"minute stage: {len(syms)} eligible symbols x {len(chunks)} months = {len(syms) * len(chunks)} symbol-months")
    counts = {"RETRIEVED": 0, "VENDOR_NO_DATA": 0, "ALREADY_LANDED": 0, "VENDOR_ERROR": 0}
    total_rows = 0
    for start, end, chunk in chunks:
        t = time.monotonic()
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(pull_one_month_bars, client, limiter, s, start, end, chunk) for s in syms]
            for fut in as_completed(futs):
                r = fut.result()
                counts[r["state"]] = counts.get(r["state"], 0) + 1
                total_rows += r.get("rows") or 0
                done += 1
                if done % 500 == 0:
                    el = time.monotonic() - t
                    note(f"    {chunk}: {done}/{len(syms)} in {el:.0f}s ({done / el:.1f}/s)")
        note(f"  chunk {chunk} complete in {time.monotonic() - t:.0f}s; running rows {total_rows:,}")
        dump_json(H.WORK / "bars_progress.json",
                  {"last_completed_chunk": chunk, "counts": counts, "rows": total_rows, "at": stamp()})
    note(f"minute stage counts: {counts}; rows {total_rows:,}")
    return {**counts, "rows": total_rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["eod", "bars"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--months", type=str, default="")
    args = ap.parse_args()
    workers = max(1, min(args.workers, MAX_CONCURRENCY))
    H.WORK.mkdir(parents=True, exist_ok=True)
    from theta.client import get_shared_client
    client = get_shared_client()
    limiter = ThetaLimiter(workers)
    months = [m for m in args.months.split(",") if m] or None
    note(f"stage={args.stage} workers={workers} (vendor cap {MAX_CONCURRENCY}) months={months or 'all'}")
    counts = stage_eod(client, limiter, workers) if args.stage == "eod" else stage_bars(client, limiter, workers, months)
    dump_json(H.WORK / f"acquire_{args.stage}_manifest.json",
              {"arrow": "CG Arrow 013", "stage": args.stage, "timestamp": stamp(),
               "workers": workers, "max_concurrency": MAX_CONCURRENCY,
               "window": {"start": H.BULK_START.isoformat(), "end": H.BULK_END.isoformat()},
               "counts": counts, "elapsed_minutes": (time.monotonic() - T0) / 60, "log": LOG})
    note(f"stage {args.stage} finished in {(time.monotonic() - T0) / 60:.1f} minutes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
