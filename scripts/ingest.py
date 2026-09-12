"""Ingest CLI. See docs/DATA_CONTRACT.md and docs/BUILD_ARROW_01.md."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
# scripts/ is sys.path[0] when running this file; that would shadow src/ingest.
sys.path.insert(0, str(REPO_ROOT / "src"))

from ingest.paths import ensure_dirs  # noqa: E402
from ingest.full import run_arrow17  # noqa: E402
from ingest.run import run_arrow2, run_study, run_universe, run_warmup, write_calendar  # noqa: E402
from ingest.validate import validate_warmup  # noqa: E402
from ingest.virgin import run_arrow41, run_arrow61  # noqa: E402


def _defaults() -> tuple[int, int]:
    cpu = os.cpu_count() or 1
    workers = min(8, cpu)
    return workers, 8


def main(argv: list[str] | None = None) -> int:
    workers_default, theta_default = _defaults()
    p = argparse.ArgumentParser(
        description="Theta Data ingest (warmup/study). Parallel by default."
    )
    p.add_argument(
        "--mode",
        choices=(
            "warmup",
            "calendar",
            "eligibility",
            "bars",
            "validate",
            "universe",
            "study",
            "arrow2",
            "arrow17",
            "arrow41",
            "arrow61",
        ),
        default="arrow61",
        help="arrow61=append 2025-12-01..16 into data/virgin",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=workers_default,
        help="local worker threads (default min(8, cpu_count))",
    )
    p.add_argument(
        "--theta-concurrency",
        type=int,
        default=theta_default,
        help="max concurrent Theta requests (Pro cap 8; backoff on 429)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="re-pull even if parquet + ok manifest line exist",
    )
    args = p.parse_args(argv)
    if args.mode == "arrow41":
        return run_arrow41(
            workers=args.workers,
            theta_concurrency=args.theta_concurrency,
            force=args.force,
        )
    if args.mode == "arrow61":
        return run_arrow61(
            workers=args.workers,
            theta_concurrency=args.theta_concurrency,
            force=args.force,
        )
    ensure_dirs()
    if args.mode == "calendar":
        write_calendar()
        return 0
    if args.mode == "validate":
        issues = validate_warmup()
        for item in issues:
            print(item)
        print("ok" if not issues else "FAIL")
        return 0 if not issues else 1
    kwargs = dict(
        workers=args.workers,
        theta_concurrency=args.theta_concurrency,
        force=args.force,
    )
    if args.mode == "universe":
        code, _ = run_universe(**kwargs)
        return code
    if args.mode == "study":
        return run_study(**kwargs)
    if args.mode == "arrow2":
        return run_arrow2(**kwargs)
    if args.mode == "arrow17":
        return run_arrow17(**kwargs)
    if args.mode in {"eligibility", "bars"}:
        print(
            f"{args.mode} is included in --mode warmup; run warmup (resumable)",
            flush=True,
        )
    return run_warmup(**kwargs)


if __name__ == "__main__":
    sys.exit(main())
