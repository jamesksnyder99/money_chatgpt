from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow65 import fill_session_of
from research.arrow66 import (
    CONTROL_ID,
    EXPERIMENTS,
    FILL_KIND,
    PATH_N,
    hold_exit_of,
    path_is_only,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_next_lastrth_fill_hold10_4000() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "h10_4k"
    assert EXPERIMENTS[0][1] == 10
    assert EXPERIMENTS[0][2] == 4000.0
    assert EXPERIMENTS[0][3] is False
    assert FILL_KIND == "nextrth"
    assert len(EXPERIMENTS) == 6
    wed = date(2026, 1, 7)
    sess = [date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 22)]
    assert fill_session_of(wed, "nextrth", sess) == date(2026, 1, 8)
    assert fill_session_of(wed, "nextrth", sess) != wed
    assert shares_for(20.0, 4000.0) == 200
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert wed.weekday() == 2


def test_id1_exits_5_after_fill_id2_exits_15() -> None:
    assert EXPERIMENTS[1][0] == "h5_4k"
    assert EXPERIMENTS[1][1] == 5
    assert EXPERIMENTS[2][0] == "h15_4k"
    assert EXPERIMENTS[2][1] == 15
    fill = date(2026, 1, 8)
    sess = [
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
        date(2026, 1, 13),
        date(2026, 1, 14),
        date(2026, 1, 15),
        date(2026, 1, 16),
        date(2026, 1, 20),
        date(2026, 1, 21),
        date(2026, 1, 22),
        date(2026, 1, 23),
        date(2026, 1, 26),
        date(2026, 1, 27),
        date(2026, 1, 28),
        date(2026, 1, 29),
        date(2026, 1, 30),
    ]
    assert hold_exit_of(fill, 5, sess) == date(2026, 1, 15)
    assert hold_exit_of(fill, 10, sess) == date(2026, 1, 23)
    assert hold_exit_of(fill, 15, sess) == date(2026, 1, 30)
    assert hold_exit_of(fill, 5, sess) != hold_exit_of(fill, 15, sess)
    assert hold_exit_of(fill, 10, sess) != hold_exit_of(fill, 5, sess)


def test_path_table_has_15_rows_and_is_is_only() -> None:
    assert PATH_N == 15
    rows = [{"hold_day": i} for i in range(1, 16)]
    assert path_is_only(rows)
    assert not path_is_only(rows[:14])
    assert not path_is_only([{"hold_day": 2}] + rows[1:])
    oos_label = "OOS path"
    assert "OOS path" not in "IS path on id 0 fills"
    assert oos_label != "IS path"


def test_even_month_signal_is_not_is() -> None:
    wed = date(2026, 2, 4)
    assert wed.weekday() == 2
    assert entry_split(wed) == "OOS"
    assert not is_is_session(wed)
    assert is_is_session(date(2026, 1, 7))


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 7), date(2026, 6, 3), date(2026, 8, 26)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
    assert tape_root(date(2026, 1, 7)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
