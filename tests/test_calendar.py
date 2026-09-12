from datetime import date

import polars as pl

from ingest.calendar import (
    MEMORIAL_DAY,
    WARMUP_SESSIONS,
    prior_session,
    sessions_frame,
    study_sessions,
)


def test_warmup_ten_sessions_no_memorial() -> None:
    assert len(WARMUP_SESSIONS) == 10
    assert MEMORIAL_DAY not in WARMUP_SESSIONS
    assert date(2026, 5, 25) not in WARMUP_SESSIONS
    assert WARMUP_SESSIONS[0] == date(2026, 5, 15)
    assert WARMUP_SESSIONS[-1] == date(2026, 5, 29)


def test_prior_session_skips_weekend_and_holiday() -> None:
    assert prior_session(date(2026, 5, 15)) == date(2026, 5, 14)
    assert prior_session(date(2026, 5, 18)) == date(2026, 5, 15)
    assert prior_session(date(2026, 5, 26)) == date(2026, 5, 22)


def test_study_calendar_matches_nyse_2026() -> None:
    study = study_sessions()
    assert date(2026, 6, 1) in study
    assert date(2026, 6, 19) not in study
    assert date(2026, 7, 3) not in study
    assert date(2026, 8, 31) in study
    assert len(study) == 64


def test_sessions_frame_flags() -> None:
    df = sessions_frame()
    warmup = set(df.filter(pl.col("is_warmup"))["session_date"].to_list())
    assert warmup == set(WARMUP_SESSIONS)
    assert MEMORIAL_DAY not in set(df["session_date"].to_list())
    assert date(2026, 7, 3) not in set(df["session_date"].to_list())
