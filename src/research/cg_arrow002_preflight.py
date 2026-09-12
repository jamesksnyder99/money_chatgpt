"""Read-only corporate-action preflight. Never generates or scores signals.

An empty event table is not evidence of zero events without coverage provenance.
Nonempty data requires a separate coverage and adjustment review; this diagnostic
does not certify it or unlock research automatically.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl

from ingest.paths import REPO_ROOT, SPLITS


def assess_splits(frame: pl.DataFrame) -> dict:
    expected = {"symbol": pl.String, "ex_date": pl.Date, "factor": pl.Float64}
    if any(frame.schema.get(name) != dtype for name, dtype in expected.items()):
        return {"status": "BLOCKED", "reason": "Missing or incompatible split schema."}
    if frame.is_empty():
        return {
            "status": "BLOCKED",
            "reason": "Empty split reference; zero events and coverage are unverified.",
        }
    invalid = frame.filter(
        pl.col("symbol").is_null()
        | (pl.col("symbol").str.strip_chars() == "")
        | pl.col("ex_date").is_null()
        | pl.col("factor").is_null()
        | ~pl.col("factor").is_finite()
        | (pl.col("factor") <= 0)
    )
    if invalid.height:
        return {"status": "BLOCKED", "reason": "Invalid split reference rows."}
    return {
        "status": "REVIEW_REQUIRED",
        "reason": "Verify universe/date coverage, factor convention, and causal treatment.",
    }


def inspect_splits(path: Path = SPLITS) -> dict:
    # Reject lexical escapes before any filesystem resolution/read of the target.
    root = REPO_ROOT.absolute()
    target = path.absolute()
    if not target.is_relative_to(root) or ".." in target.parts:
        raise ValueError("Split reference must be inside the lab repository.")
    relative = target.relative_to(root)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError("Linked split reference paths are forbidden.")
    if not target.is_file():
        return {"status": "BLOCKED", "reason": "Split reference is missing."}
    frame = pl.read_parquet(target)
    return {
        **assess_splits(frame),
        "path": relative.as_posix(),
        "rows": frame.height,
        "bytes": target.stat().st_size,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "signals_generated": 0,
        "oos_cohorts_scored": 0,
    }


def main() -> int:
    print(json.dumps(inspect_splits(), indent=2))
    return 2  # Neither BLOCKED nor REVIEW_REQUIRED authorizes research.


if __name__ == "__main__":
    raise SystemExit(main())
