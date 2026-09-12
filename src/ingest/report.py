from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ARROW01_REPORT, INGEST_REPORT

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")


def write_reports(
    *,
    started: datetime,
    ended: datetime,
    workers: int,
    theta_concurrency_start: int,
    theta_concurrency_end: int,
    cpu_count: int,
    elig: pl.DataFrame,
    rows_by_session: dict,
    failures: list[dict],
    mean_request_s: float,
    sessions_ok: int,
    sessions_fail: int,
    extra_notes: list[str],
    title: str = "Arrow 1 — warmup pull timing",
    report_path=None,
    sessions_attempted: int | None = None,
) -> None:
    wall_s = (ended - started).total_seconds()
    wall_h = wall_s / 3600.0
    per = (
        elig.filter(pl.col("eligible"))
        .group_by("session_date")
        .len()
        .sort("session_date")
    )
    counts = per["len"].to_list() if per.height else [0]
    mean_n = sum(counts) / len(counts)
    min_n = min(counts)
    max_n = max(counts)
    n_study = len(study_sessions())
    est_linear = wall_h * (10 + n_study) / 10.0
    total_rows = sum(rows_by_session.values()) if rows_by_session else 0

    start_utc = started.astimezone(UTC).isoformat(timespec="seconds")
    end_utc = ended.astimezone(UTC).isoformat(timespec="seconds")
    start_et = started.astimezone(ET).isoformat(timespec="seconds")
    end_et = ended.astimezone(ET).isoformat(timespec="seconds")

    n_sess = sessions_attempted if sessions_attempted is not None else len(WARMUP_SESSIONS)
    dest = report_path or ARROW01_REPORT
    lines = [
        title,
        f"start_utc: {start_utc}",
        f"end_utc:   {end_utc}",
        f"start_et:  {start_et}",
        f"end_et:    {end_et}",
        f"wall_seconds: {wall_s:.1f}",
        f"wall_hours: {wall_h:.4f}",
        f"cpu_count: {cpu_count}",
        f"workers: {workers}",
        f"theta_concurrency_start: {theta_concurrency_start}",
        f"theta_concurrency_end: {theta_concurrency_end}",
        f"sessions_attempted: {n_sess}",
        f"sessions_ok: {sessions_ok}",
        f"sessions_fail: {sessions_fail}",
        f"eligible_mean: {mean_n:.1f}",
        f"eligible_min: {min_n}",
        f"eligible_max: {max_n}",
        "eligible_per_session:",
    ]
    for row in per.iter_rows(named=True):
        d = row["session_date"]
        n = row["len"]
        r = rows_by_session.get(d, rows_by_session.get(str(d), 0))
        lines.append(f"  {d}: eligible={n} 1m_rows={r}")
    lines += [
        f"1m_rows_total: {total_rows}",
        f"mean_seconds_per_1m_request: {mean_request_s:.4f}",
        f"failures_count: {len(failures)}",
        "failures (class/message, no secrets):",
    ]
    if not failures:
        lines.append("  (none)")
    else:
        for item in failures[:200]:
            lines.append(
                f"  {item.get('symbol')} {item.get('session')} "
                f"{item.get('error_class')}: {item.get('error_message')}"
            )
        if len(failures) > 200:
            lines.append(f"  ... {len(failures) - 200} more")

    lines += [
        "",
        "extrapolation (estimate, not a promise):",
        f"  N_warmup=10  N_study={n_study}  N_full={10 + n_study}",
        f"  est_full_hours = {wall_h:.4f} * ({10 + n_study}) / 10 = {est_linear:.2f}",
        f"  est_full_hours_scaled_by_eligible = {est_linear:.2f}  "
        "(assumed mean_eligible_study / mean_eligible_warmup = 1.0; "
        "study eligibility was not observed)",
        "",
        "assumptions:",
        "  - Jun–Aug 2026 trading days use the official NYSE calendar "
        "(closed 2026-06-19 Juneteenth and 2026-07-03 Independence observed).",
        "  - 2026-07-03 is a full holiday, not an early close (NYSE/Nasdaq 2026 schedule).",
        "  - Warmup mean eligible count holds in the study window.",
        "  - Same workers / theta_concurrency / venue=utp_cta / 07:30–12:00 1m OHLC.",
        "  - Wall time scales with session count (eligibility + 1m pulls).",
        "  - No tick/quotes/options/flat files.",
        "  - Splits endpoint is not in thetadata v3 SDK; 1m prints left unadjusted.",
    ]
    lines.extend(f"  - {n}" for n in extra_notes)

    text = "\n".join(lines) + "\n"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    INGEST_REPORT.write_text(text, encoding="utf-8")
    print(text, flush=True)
