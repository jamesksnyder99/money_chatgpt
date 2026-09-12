from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import shares_for
from research.arrow54 import (
    CONTROL_ID,
    EXPERIMENTS,
    fade_pass,
    no_repeat_pass,
    rth_down_pass,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_short_only_friday_no_fade_filter() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "plain"
    assert EXPERIMENTS[0][1] == 4
    assert EXPERIMENTS[0][2] == "none"
    assert len(EXPERIMENTS) == 6
    rows = [
        {"residual": 0.20, "symbol": "A"},
        {"residual": 0.05, "symbol": "B"},
        {"residual": -0.10, "symbol": "C"},
    ]
    picks = select_shorts(rows, 8, None)
    assert picks[0]["symbol"] == "A"
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert date(2026, 1, 2).weekday() == 4


def test_id1_rejects_last_session_residual_vs_iwm_ge_0() -> None:
    assert EXPERIMENTS[1][0] == "fade1"
    assert fade_pass(-0.02, 0.0) is True
    assert fade_pass(0.02, 0.0) is False
    assert fade_pass(0.0, 0.0) is False
    assert fade_pass(0.05, 0.10) is True
    assert fade_pass(None, 0.0) is False
    assert fade_pass(0.01, None) is False


def test_id3_rejects_close_ge_open930() -> None:
    assert EXPERIMENTS[3][0] == "rth_down"
    assert rth_down_pass(19.0, 20.0) is True
    assert rth_down_pass(20.0, 20.0) is False
    assert rth_down_pass(21.0, 20.0) is False
    assert rth_down_pass(None, 20.0) is False
    assert rth_down_pass(19.0, None) is False


def test_id4_rejects_name_in_prior_friday_eight() -> None:
    assert EXPERIMENTS[4][0] == "no_repeat"
    prior = {"A", "B", "C"}
    assert no_repeat_pass("D", prior) is True
    assert no_repeat_pass("A", prior) is False
    assert no_repeat_pass("A", set()) is True


def test_id5_entries_are_wednesdays_only() -> None:
    assert EXPERIMENTS[5][0] == "wed_fade1"
    assert EXPERIMENTS[5][1] == 2
    assert EXPERIMENTS[5][2] == "fade1"
    assert date(2026, 1, 7).weekday() == 2
    assert date(2026, 1, 2).weekday() != 2
    assert shares_for(20.0, 6000.0) == 300


def test_even_month_entry_is_not_is() -> None:
    assert entry_split(date(2026, 2, 6)) == "OOS"
    assert not is_is_session(date(2026, 2, 6))
    assert is_is_session(date(2026, 1, 2))


def test_july_from_full_january_from_virgin() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 2)) == FULL_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 2), date(2026, 6, 5), date(2026, 8, 28)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
