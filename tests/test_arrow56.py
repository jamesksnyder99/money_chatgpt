from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow55 import already_on, net_skip, ticket_live
from research.arrow56 import (
    CONTROL_ID,
    DBL_ID,
    EXPERIMENTS,
    WM_ID,
    allows_second_ticket,
    nearest_following,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_net_friday_wednesday_3000_no_second_ticket() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "fw_3k_net"
    assert EXPERIMENTS[0][1] == (4, 2)
    assert EXPERIMENTS[0][2] == 3000.0
    assert EXPERIMENTS[0][3] is True
    assert len(EXPERIMENTS) == 5
    assert allows_second_ticket(True) is False
    fri = date(2026, 1, 2)
    wed = date(2026, 1, 7)
    ex = date(2026, 1, 16)
    open_tickets = [{"symbol": "A", "entry": fri, "exit": ex, "wd": 4}]
    assert ticket_live(fri, ex, wed) is True
    assert already_on("A", open_tickets, wed, from_wd=4) is True
    assert net_skip("A", open_tickets, wed, other_wd=4) is True
    assert net_skip("B", open_tickets, wed, other_wd=4) is False
    assert date(2026, 1, 2).weekday() == 4
    assert date(2026, 1, 7).weekday() == 2
    assert shares_for(20.0, 3000.0) == 150
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0


def test_id3_may_open_two_tickets_same_name() -> None:
    assert EXPERIMENTS[3][0] == DBL_ID == "fw_4k_dbl"
    assert EXPERIMENTS[3][1] == (4, 2)
    assert EXPERIMENTS[3][2] == 4000.0
    assert EXPERIMENTS[3][3] is False
    assert allows_second_ticket(False) is True
    fri = date(2026, 1, 2)
    wed = date(2026, 1, 7)
    ex = date(2026, 1, 16)
    open_tickets = [{"symbol": "A", "entry": fri, "exit": ex, "wd": 4}]
    assert net_skip("A", open_tickets, wed, other_wd=4) is True
    assert allows_second_ticket(EXPERIMENTS[3][3]) is True


def test_id4_monday_entries_exist() -> None:
    assert EXPERIMENTS[4][0] == WM_ID == "wm_3k_net"
    assert 0 in EXPERIMENTS[4][1]
    assert 2 in EXPERIMENTS[4][1]
    assert 4 not in EXPERIMENTS[4][1]
    assert EXPERIMENTS[4][2] == 3000.0
    assert EXPERIMENTS[4][3] is True
    mon = date(2026, 1, 5)
    assert mon.weekday() == 0
    assert date(2026, 1, 2).weekday() != 0
    assert date(2026, 1, 7).weekday() == 2


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


def test_nearest_following_prefers_later() -> None:
    wed = date(2026, 1, 7)
    mons = [date(2026, 1, 5), date(2026, 1, 12)]
    assert nearest_following(wed, mons) == date(2026, 1, 12)
    assert nearest_following(wed, [date(2026, 1, 5)]) == date(2026, 1, 5)
    assert nearest_following(wed, []) is None
