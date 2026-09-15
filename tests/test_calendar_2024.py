"""The 2024 exchange calendar belongs to the calendar module, and adding it changed nothing.

Arrow 014 scores a pristine corridor that opens in August 2024. The execution layer reads its
close times from `ingest.calendar`, which knew only 2025 and 2026; on the two 2024 early closes
it would have looked for a 15:59 print that cannot exist and recorded every name on those
sessions as a thin-session fallback. Those sessions carry a cohort entry, a ranking endpoint and
three holding exits, so the error was not cosmetic.
"""
from datetime import date, time

from ingest import holdout2024 as H
from ingest.calendar import (
    NYSE_CLOSED, NYSE_CLOSED_2024, NYSE_EARLY_CLOSE, NYSE_EARLY_CLOSE_2024, nyse_sessions,
)
from verification import r4r5_data as D


def test_engine_knows_the_2024_early_closes():
    for d in (date(2024, 7, 3), date(2024, 11, 29), date(2024, 12, 24)):
        assert D.close_time(d) == time(13, 0)
        assert D.final_minute(d) == time(12, 59)


def test_engine_and_ingest_agree_across_the_whole_corridor():
    for d in H.sessions(date(2024, 8, 1), date(2025, 9, 30)):
        assert D.close_time(d) == H.close_time(d)


def test_adding_2024_is_inert_for_the_historical_study():
    """The 2025-26 study window contains no 2024 date, so its results cannot move."""
    feats = nyse_sessions(date(2025, 8, 1), date(2026, 9, 30))
    assert not [d for d in feats if d.year == 2024]
    assert not [d for d in NYSE_CLOSED_2024 if d.year != 2024]
    assert not [d for d in NYSE_EARLY_CLOSE_2024 if d.year != 2024]


def test_holdout_reexports_the_shared_tables():
    assert H.NYSE_CLOSED_2024 is NYSE_CLOSED_2024
    assert H.NYSE_EARLY_CLOSE_2024 is NYSE_EARLY_CLOSE_2024
    assert NYSE_CLOSED_2024 <= NYSE_CLOSED
    assert all(NYSE_EARLY_CLOSE[d] == v for d, v in NYSE_EARLY_CLOSE_2024.items())


def test_2024_closures_are_not_sessions():
    for d in NYSE_CLOSED_2024:
        assert not H.is_session(d)
