from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import shares_for
from research.arrow52 import (
    CONTROL_ID,
    IDS,
    LB,
    NOTIONAL,
    STAND_ID,
    stand_enters,
    stand_exits,
    weekday_id,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl
from research.signals import MINUTE_1559, RTH_OPEN


def test_id0_short_only_lookback_15_friday_entries_only() -> None:
    assert IDS[0] == CONTROL_ID == "fri_h10"
    assert LB == 15
    assert NOTIONAL == 6000.0
    assert len(IDS) == 6
    rows = [
        {"residual": 0.20, "symbol": "A"},
        {"residual": 0.05, "symbol": "B"},
        {"residual": -0.10, "symbol": "C"},
    ]
    picks = select_shorts(rows, 8, None)
    assert picks[0]["symbol"] == "A"
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    fri = date(2026, 1, 2)
    assert fri.weekday() == 4
    assert weekday_id(fri) == "fri_h10"
    assert weekday_id(date(2026, 1, 5)) != "fri_h10"
    assert RTH_OPEN != MINUTE_1559


def test_id1_entries_are_mondays_only() -> None:
    mon = date(2026, 1, 5)
    assert mon.weekday() == 0
    assert weekday_id(mon) == "mon_h10"
    assert weekday_id(date(2026, 1, 2)) != "mon_h10"
    assert weekday_id(date(2026, 1, 6)) != "mon_h10"


def test_id5_can_enter_on_a_tuesday() -> None:
    tue = date(2026, 1, 6)
    assert tue.weekday() == 1
    assert stand_enters(set(), {"A", "B"}) == {"A", "B"}
    assert "A" in stand_enters({"B"}, {"A", "B"})
    assert STAND_ID == "stand_top8"


def test_id5_exits_a_name_the_session_it_leaves_top8() -> None:
    assert stand_exits({"A", "B", "C"}, {"B", "C", "D"}) == {"A"}
    assert stand_enters({"A", "B", "C"}, {"B", "C", "D"}) == {"D"}
    assert stand_exits({"A"}, {"A"}) == set()
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
