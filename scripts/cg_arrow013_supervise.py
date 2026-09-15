"""CG Arrow 013 — supervised resume for the minute-bar stage.

The vendor session expires under sustained load. The acquisition stage fails closed when that
happens, which is correct but means an overnight run needs restarting. This supervisor does
exactly that and nothing more: it re-runs the same acquisition command, each run authenticating
a fresh session and skipping every partition that already landed.

It never changes what is acquired, never relaxes a check and never retries a genuine data
failure. It stops when the stage reports completion, when no progress is made across two
consecutive attempts, or when the attempt limit is reached.

Usage: python scripts/cg_arrow013_supervise.py [--attempts 40] [--workers 8]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import holdout2024 as H  # noqa: E402
from verification.r4r5_data import dump_json, stamp  # noqa: E402


def landed() -> int:
    return sum(1 for _ in H.RAW_BARS.rglob("*.parquet")) if H.RAW_BARS.exists() else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--attempts", type=int, default=40)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    log = []
    stagnant = 0
    for attempt in range(1, args.attempts + 1):
        before = landed()
        t0 = time.monotonic()
        proc = subprocess.run(
            [sys.executable, "scripts/cg_arrow013_acquire.py", "bars",
             "--workers", str(args.workers), "--threads", str(args.workers)],
            cwd=ROOT, capture_output=True, text=True)
        after = landed()
        gained = after - before
        done = (H.WORK / "acquire_bars_manifest.json").exists() and proc.returncode == 0
        line = (f"{stamp()} attempt {attempt}: exit {proc.returncode}, partitions {before:,} -> {after:,} "
                f"(+{gained:,}) in {(time.monotonic() - t0) / 60:.1f}m")
        print(line, flush=True)
        log.append(line)
        dump_json(H.WORK / "supervise_progress.json",
                  {"attempts": attempt, "partitions": after, "last_gain": gained,
                   "complete": done, "log": log, "at": stamp()})
        if done:
            print(f"{stamp()} minute stage reported completion", flush=True)
            return 0
        stagnant = stagnant + 1 if gained == 0 else 0
        if stagnant >= 2:
            print(f"{stamp()} stopping: two consecutive attempts acquired nothing, so the blocker is "
                  "not session expiry. Inspect data/holdout2024/work/vendor_errors_bars.jsonl.", flush=True)
            return 1
        time.sleep(5)
    print(f"{stamp()} attempt limit reached; re-run to continue", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
