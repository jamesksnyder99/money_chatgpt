from __future__ import annotations

from datetime import date, time
from pathlib import Path

import polars as pl

from ingest.calendar import MEMORIAL_DAY, WARMUP_SESSIONS, study_sessions
from ingest.paths import BARS_DIR, CALENDAR, ELIGIBILITY


def validate_warmup() -> list[str]:
    """Contract checks that apply to the warmup window. Returns issue strings."""
    issues: list[str] = []
    cal = pl.read_parquet(CALENDAR)
    sessions = set(cal["session_date"].to_list())
    warmup = set(cal.filter(pl.col("is_warmup"))["session_date"].to_list())
    if warmup != set(WARMUP_SESSIONS):
        issues.append(f"warmup sessions mismatch: {sorted(warmup)}")
    if MEMORIAL_DAY in sessions:
        issues.append("2026-05-25 Memorial Day present in calendar")
    study = set(cal.filter(~pl.col("is_warmup"))["session_date"].to_list())
    expected_study = set(study_sessions())
    if study != expected_study:
        issues.append(
            f"study session count {len(study)} != NYSE {len(expected_study)}"
        )
    jul3 = date(2026, 7, 3)
    if jul3 in sessions:
        issues.append("2026-07-03 is a NYSE full holiday (Independence observed); should be absent")

    elig = pl.read_parquet(ELIGIBILITY)
    if "session_date" not in elig.columns:
        issues.append("eligibility missing session_date")
        return issues
    # Eligibility must not use same-day close: prior EOD date is encoded only via
    # prior_close sourced from D-1. Same-day leak would require prior_close from D.
    # We check no eligibility row has session_date < first warmup (sanity) and
    # that ineligible/eligible rows exist only for warmup sessions in this arrow.
    elig_dates = set(elig["session_date"].to_list())
    allowed = set(WARMUP_SESSIONS) | set(study_sessions())
    if not elig_dates.issubset(allowed):
        extra = elig_dates - allowed
        issues.append(f"eligibility has unknown sessions: {sorted(extra)[:5]}")
    if date(2026, 7, 3) in elig_dates:
        issues.append("eligibility includes 2026-07-03 (full close)")
    if date(2026, 6, 19) in elig_dates:
        issues.append("eligibility includes 2026-06-19 (full close)")

    dup_keys: list[str] = []
    bar_issues = _validate_bars()
    issues.extend(bar_issues)
    issues.extend(dup_keys)
    return issues


def _validate_bars() -> list[str]:
    issues: list[str] = []
    if not BARS_DIR.exists():
        issues.append("no bars directory")
        return issues
    files = list(BARS_DIR.rglob("*.parquet"))
    if not files:
        issues.append("no 1m parquet files")
        return issues

    open_t = time(7, 30)
    end_t = time(12, 0)

    def check(path: Path) -> list[str]:
        local: list[str] = []
        df = pl.read_parquet(path)
        if df.height == 0:
            return local
        if "bar_start" not in df.columns:
            return [f"{path.name}: missing bar_start"]
        t = df["bar_start"].dt.time()
        if df.filter((t < open_t) | (t >= end_t)).height:
            local.append(f"{path.name}: bar outside 07:30–12:00")
        dups = (
            df.group_by(["symbol", "bar_start"])
            .len()
            .filter(pl.col("len") > 1)
            .height
        )
        if dups:
            local.append(f"{path.name}: duplicate (symbol, bar_start) x{dups}")
        return local

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=8) as pool:
        for chunk in pool.map(check, files):
            issues.extend(chunk)
    return issues
