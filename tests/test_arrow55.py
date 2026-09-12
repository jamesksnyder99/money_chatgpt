from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import shares_for
from research.arrow55 import (
    CONTROL_ID,
    EXPERIMENTS,
    NET_ID,
    WED_ID,
    already_on,
    nearest_wednesday,
    net_skip,
    ticket_live,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_friday_only_6000() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "fri_6k"
    assert EXPERIMENTS[0][1] == (4,)
    assert EXPERIMENTS[0][2] == 6000.0
    assert EXPERIMENTS[0][3] is False
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
    assert shares_for(20.0, 6000.0) == 300


def test_id1_wednesday_only_6000() -> None:
    assert EXPERIMENTS[1][0] == WED_ID == "wed_6k"
    assert EXPERIMENTS[1][1] == (2,)
    assert EXPERIMENTS[1][2] == 6000.0
    assert EXPERIMENTS[1][3] is False
    assert date(2026, 1, 7).weekday() == 2
    assert date(2026, 1, 2).weekday() != 2


def test_id4_does_not_open_second_ticket_already_on_from_friday() -> None:
    assert EXPERIMENTS[4][0] == NET_ID == "pair_3k_net"
    assert EXPERIMENTS[4][3] is True
    assert EXPERIMENTS[4][2] == 3000.0
    fri = date(2026, 1, 2)
    wed = date(2026, 1, 7)
    ex = date(2026, 1, 16)
    open_tickets = [{"symbol": "A", "entry": fri, "exit": ex, "wd": 4}]
    assert ticket_live(fri, ex, wed) is True
    assert already_on("A", open_tickets, wed, from_wd=4) is True
    assert net_skip("A", open_tickets, wed, other_wd=4) is True
    assert net_skip("B", open_tickets, wed, other_wd=4) is False
    assert already_on("A", open_tickets, wed, from_wd=2) is False
    later = date(2026, 1, 16)
    assert ticket_live(fri, ex, later) is False
    assert net_skip("A", open_tickets, later, other_wd=4) is False


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


def test_nearest_wednesday_prefers_following() -> None:
    fri = date(2026, 1, 2)
    weds = [date(2025, 12, 31), date(2026, 1, 7), date(2026, 1, 14)]
    assert nearest_wednesday(fri, weds) == date(2026, 1, 7)
    assert nearest_wednesday(fri, [date(2025, 12, 31)]) == date(2025, 12, 31)
    assert nearest_wednesday(fri, []) is None
