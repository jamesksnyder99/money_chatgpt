from datetime import date, datetime
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow42 import (
    SHELVE_N,
    TAPE,
    is_score_session,
    keep_b_signal,
    keep_f_signal,
    score_sessions,
    shelve_reason,
    warmup_for_features,
)
from research.signals import Signal

ET = ZoneInfo("America/New_York")


def test_score_window_is_one_look_not_split() -> None:
    study = score_sessions()
    warm = warmup_for_features()
    assert study[0] == date(2026, 1, 2)
    assert study[-1] == date(2026, 5, 29)
    assert date(2026, 1, 16) in study
    assert date(2026, 6, 1) not in study
    assert date(2026, 7, 31) not in study
    assert all(d.year == 2026 for d in study)
    assert not set(study) & set(warm)
    assert all(d.year == 2025 for d in warm)
    assert date(2025, 12, 31) in warm
    assert not is_score_session(date(2025, 12, 31))
    assert not is_score_session(date(2026, 6, 1))
    assert is_score_session(date(2026, 1, 2))


def test_warmup_dates_are_not_scored() -> None:
    for d in warmup_for_features():
        assert not is_score_session(d)


def test_june_2026_not_in_virgin_score() -> None:
    assert date(2026, 6, 1) not in score_sessions()
    assert date(2026, 6, 19) not in score_sessions()


def test_tape_is_virgin_not_full_or_lab_a() -> None:
    assert TAPE == VIRGIN_BARS
    assert TAPE != FULL_BARS
    assert TAPE != BARS_DIR
    assert "virgin" in TAPE.parts
    assert "full" not in TAPE.parts


def test_long_flush_short_b_only() -> None:
    ts = datetime(2026, 1, 2, 10, 0, tzinfo=ET)
    short_b = Signal(ts, "AAA", -1, 11.0, None, 1.0, "b")
    long_b = Signal(ts, "AAA", 1, 9.0, None, 1.0, "b")
    long_f = Signal(ts, "BBB", 1, 9.0, None, 1.0, "f")
    short_f = Signal(ts, "BBB", -1, 11.0, None, 1.0, "f")
    assert keep_b_signal(short_b)
    assert not keep_b_signal(long_b)
    assert keep_f_signal(long_f)
    assert not keep_f_signal(short_f)


def test_nice_houses_shelve_under_40() -> None:
    assert SHELVE_N == 40
    assert "SHELVE" in shelve_reason(0)
    assert "SHELVE" in shelve_reason(39)
    assert shelve_reason(40) == ""
    assert shelve_reason(41) == ""
