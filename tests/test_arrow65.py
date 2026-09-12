from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow65 import (
    CONTROL_ID,
    EXPERIMENTS,
    fill_px,
    fill_session_of,
    resolve_exit_bar,
)
from research.clock import entry_split, is_is_session, session_shift, tape_root
from research.costs import signed_pnl


def test_id0_wednesday_only_3000_close_fill() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "close_3k"
    assert EXPERIMENTS[0][1] == "close"
    assert EXPERIMENTS[0][2] == 3000.0
    assert EXPERIMENTS[0][3] is False
    assert len(EXPERIMENTS) == 6
    assert all(e[1] == "close" or e[1] == "open" or e[1] == "nextrth" for e in EXPERIMENTS)
    wed = date(2026, 1, 7)
    assert wed.weekday() == 2
    sess = [date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 22)]
    assert fill_session_of(wed, "close", sess) == wed
    assert shares_for(20.0, 3000.0) == 150
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0


def test_id2_fill_is_next_session_0930_not_signal_close() -> None:
    assert EXPERIMENTS[2][0] == "open_4k"
    assert EXPERIMENTS[2][1] == "open"
    assert EXPERIMENTS[2][2] == 4000.0
    signal_close, nxt_open, nxt_rth = (10.0, "sig"), (11.0, "open"), (12.0, "rth")
    assert fill_px("open", signal_close, nxt_open, nxt_rth) == nxt_open
    assert fill_px("open", signal_close, nxt_open, nxt_rth) != signal_close
    assert fill_px("close", signal_close, nxt_open, nxt_rth) == signal_close
    assert fill_px("nextrth", signal_close, nxt_open, nxt_rth) == nxt_rth
    sess = [
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    assert fill_session_of(date(2026, 1, 7), "open", sess) == date(2026, 1, 8)
    assert fill_session_of(date(2026, 1, 7), "open", sess) != date(2026, 1, 7)


def test_id4_keeps_trade_whose_day10_exit_is_missing() -> None:
    assert EXPERIMENTS[4][0] == "open_4k_keep"
    assert EXPERIMENTS[4][3] is True
    assert EXPERIMENTS[2][3] is False
    target = None
    last_avail = ("ts", 9.5)
    got, partial = resolve_exit_bar(target, True, last_avail)
    assert got == last_avail
    assert partial is True
    dropped, part2 = resolve_exit_bar(None, False, last_avail)
    assert dropped is None
    assert part2 is False
    kept_ok, part3 = resolve_exit_bar(("ts", 10.0), True, last_avail)
    assert kept_ok == ("ts", 10.0)
    assert part3 is False


def test_even_month_signal_is_not_is() -> None:
    wed = date(2026, 2, 4)
    assert wed.weekday() == 2
    assert entry_split(wed) == "OOS"
    assert not is_is_session(wed)
    assert is_is_session(date(2026, 1, 7))
    assert date(2026, 1, 7).weekday() == 2


def test_july_from_full_january_from_virgin() -> None:
    assert tape_root(date(2026, 1, 7)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR
    sess = [date(2026, 1, 7), date(2026, 1, 8)]
    assert session_shift(date(2026, 1, 7), 1, sess) == date(2026, 1, 8)


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 7), date(2026, 6, 3), date(2026, 8, 26)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
