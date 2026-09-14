"""CG Arrow 013 — build the point-in-time eligibility layer for the holdout window.

Applies the frozen universe contract to the landed end-of-day partitions: a security is
eligible for a session when its prior session's official close sits inside the $10 to $80
band and its prior-session dollar volume reaches $10 million, and when it is a common stock
rather than an exchange-traded product or a test issue under contemporaneous evidence.

This establishes which securities could have entered the point-in-time field. It computes no
return, orders nothing and selects nothing, so it reveals no strategy outcome. Its purpose is
the completeness guarantee the certification gate requires: no future top eight may benefit
from a competitor silently disappearing because its source data were absent.

Usage: python scripts/cg_arrow013_eligibility.py [--workers 8]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest import holdout2024 as H  # noqa: E402
from ingest.eligibility import MAX_CLOSE_VIRGIN, MIN_CLOSE, PDV_10M  # noqa: E402
from ingest.paths import ETP_TICKERS, SYMBOLS  # noqa: E402
from verification.r4r5_data import dump_json, stamp  # noqa: E402

TEST_ISSUE = re.compile(r"^Z[A-Z]ZZT$")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def load_chunk(chunk: str) -> pl.DataFrame:
    """Concatenate one month of landed end-of-day partitions."""
    folder = H.RAW_EOD / chunk
    files = sorted(p for p in folder.glob("*.parquet") if not p.name.startswith("_"))
    if not files:
        return pl.DataFrame(schema={"symbol": pl.String, "eod_date": pl.Date,
                                    "close": pl.Float64, "volume": pl.Int64})
    frames = []
    for i in range(0, len(files), 500):
        try:
            df = pl.read_parquet(files[i:i + 500])
        except Exception:  # noqa: BLE001
            df = pl.concat([pl.read_parquet(f) for f in files[i:i + 500]], how="diagonal_relaxed")
        keep = [c for c in ("symbol", "eod_date", "close", "volume") if c in df.columns]
        if len(keep) == 4 and df.height:
            frames.append(df.select(keep))
    if not frames:
        return pl.DataFrame(schema={"symbol": pl.String, "eod_date": pl.Date,
                                    "close": pl.Float64, "volume": pl.Int64})
    return pl.concat(frames, how="diagonal_relaxed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    H.WORK.mkdir(parents=True, exist_ok=True)

    roster = set(pl.read_parquet(SYMBOLS)["symbol"].to_list())
    etp = {x.strip().upper() for x in ETP_TICKERS.read_text(encoding="utf-8").splitlines()
           if x.strip() and not x.startswith("#")}
    tests = sorted(s for s in roster if TEST_ISSUE.match(s))
    note(f"universe contract: roster {len(roster)}, exchange-traded products excluded {len(etp)}, "
         f"test issues excluded {len(tests)}")

    chunks = [c[2] for c in H.eod_chunks()]
    frames = []
    with ProcessPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futs = {pool.submit(load_chunk, c): c for c in chunks}
        for fut in as_completed(futs):
            c = futs[fut]
            df = fut.result()
            note(f"  loaded end-of-day chunk {c}: {df.height:,} rows")
            frames.append(df)
    eod = pl.concat(frames, how="diagonal_relaxed").unique(subset=["symbol", "eod_date"])
    note(f"end-of-day layer: {eod.height:,} symbol-sessions, "
         f"{eod['symbol'].n_unique():,} securities, {eod['eod_date'].n_unique()} dates")
    eod.write_parquet(H.WORK / "eod_layer.parquet")

    # Point-in-time eligibility: session D uses the official end-of-day record of session D-1.
    sess = H.sessions(H.BULK_START, H.REUSE_END)
    prior_of = {sess[i]: sess[i - 1] for i in range(1, len(sess))}
    pairs = pl.DataFrame({"session_date": list(prior_of.keys()),
                          "prior_date": list(prior_of.values())})
    elig = (eod.rename({"eod_date": "prior_date", "close": "prior_close", "volume": "prior_volume"})
            .join(pairs, on="prior_date", how="inner")
            .with_columns((pl.col("prior_close") * pl.col("prior_volume")).alias("prior_dollar_volume")))
    elig = elig.with_columns(
        pl.col("symbol").is_in(list(etp)).alias("is_etp"),
        pl.col("symbol").str.contains(r"^Z[A-Z]ZZT$").alias("is_test_issue"),
        pl.col("symbol").is_in(list(roster)).alias("in_roster"),
    )
    reason = (
        pl.when(~pl.col("in_roster")).then(pl.lit("not_in_common_stock_roster"))
        .when(pl.col("is_test_issue")).then(pl.lit("exchange_test_issue"))
        .when(pl.col("is_etp")).then(pl.lit("exchange_traded_product"))
        .when(pl.col("prior_close").is_null() | pl.col("prior_volume").is_null())
        .then(pl.lit("no_prior_end_of_day_record"))
        .when((pl.col("prior_close") < MIN_CLOSE) | (pl.col("prior_close") > MAX_CLOSE_VIRGIN))
        .then(pl.lit("prior_close_out_of_band"))
        .when(pl.col("prior_dollar_volume") < PDV_10M)
        .then(pl.lit("prior_dollar_volume_below_10m"))
        .otherwise(pl.lit(""))
    )
    elig = elig.with_columns(reason.alias("exclude_reason"),
                             (reason == "").alias("eligible"),
                             (pl.col("prior_dollar_volume") >= PDV_10M).fill_null(False).alias("pdv_ge_10m"))
    elig = elig.with_columns(
        pl.when(pl.col("session_date") <= H.WARMUP_END).then(pl.lit("WARMUP"))
        .otherwise(pl.lit("SIGNAL")).alias("period_role"))
    elig.write_parquet(H.WORK / "eligibility.parquet")

    by_sess = (elig.filter(pl.col("eligible"))
               .group_by("session_date").len().sort("session_date"))
    counts = by_sess["len"].to_list()
    note(f"eligibility layer: {elig.height:,} rows over {elig['session_date'].n_unique()} sessions; "
         f"eligible field per session min {min(counts)} median {sorted(counts)[len(counts) // 2]} max {max(counts)}")
    universe = sorted(elig.filter(pl.col("eligible"))["symbol"].unique().to_list())
    note(f"union of the point-in-time eligible field across the window: {len(universe)} securities")
    (H.WORK / "minute_universe.txt").write_text("\n".join(universe) + "\n", encoding="utf-8")

    reasons = elig.group_by("exclude_reason").len().sort("len", descending=True).to_dicts()
    dump_json(H.WORK / "eligibility_manifest.json", {
        "arrow": "CG Arrow 013", "stage": "eligibility", "timestamp": stamp(),
        "contract": {"prior_close_band": [MIN_CLOSE, MAX_CLOSE_VIRGIN],
                     "min_prior_dollar_volume": PDV_10M,
                     "basis": "session D uses the official end-of-day record of session D-1",
                     "exclusions": "exchange-traded products and exchange test issues, by contemporaneous list"},
        "roster": len(roster), "etp_excluded": len(etp), "test_issues_excluded": tests,
        "eod_rows": eod.height, "eod_securities": eod["symbol"].n_unique(), "eod_dates": eod["eod_date"].n_unique(),
        "eligibility_rows": elig.height, "sessions": elig["session_date"].n_unique(),
        "eligible_field_min": min(counts), "eligible_field_max": max(counts),
        "eligible_field_median": sorted(counts)[len(counts) // 2],
        "minute_universe_size": len(universe),
        "exclude_reasons": reasons,
        "per_session_eligible": {str(r["session_date"]): r["len"] for r in by_sess.to_dicts()},
        "embargo_note": ("this layer counts securities and reports coverage only; no return is computed, "
                         "nothing is ranked and no security is selected"),
        "log": LOG})
    note("eligibility layer written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
