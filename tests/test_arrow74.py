from datetime import date, time

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow74 import (
    CONTROL_ID,
    EXPERIMENTS,
    FILL_1101,
    LONG_ID,
    fill_clock,
    morning_return,
)
from research.clock import (
    arrow74_february,
    arrow74_january,
    arrow74_sessions,
    feature_sessions,
    tape_root,
)
from research.costs import signed_pnl
from research.signals import MINUTE_1100


def test_id0_short_only_id1_long_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "short_all"
    assert EXPERIMENTS[0][1] == "short"
    assert EXPERIMENTS[1][0] == LONG_ID == "long_all"
    assert EXPERIMENTS[1][1] == "long"
    assert len(EXPERIMENTS) == 6
    assert all(e[1] == "short" for e in EXPERIMENTS if e[0].startswith("short_"))
    assert all(e[1] == "long" for e in EXPERIMENTS if e[0].startswith("long_"))
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 21.0) > 0
    assert shares_for(20.0, 3000.0) == 150
    mr = morning_return(10.0, 11.0)
    assert mr is not None and abs(mr - 0.10) < 1e-12
    assert morning_return(None, 11.0) is None


def test_id0_fill_is_1101_not_1100_rank_stamp() -> None:
    assert fill_clock("1101") == FILL_1101 == time(11, 1)
    assert fill_clock("1100") == MINUTE_1100 == time(11, 0)
    assert fill_clock(EXPERIMENTS[0][4]) == FILL_1101
    assert fill_clock(EXPERIMENTS[0][4]) != MINUTE_1100
    assert EXPERIMENTS[3][0] == "short_1100"
    assert EXPERIMENTS[3][4] == "1100"
    assert fill_clock("1101") >= time(11, 1)
    assert fill_clock("1101") != fill_clock("1100")


def test_march_2026_is_not_scored() -> None:
    sess = arrow74_sessions()
    assert sess[0] == date(2026, 1, 2)
    assert sess[-1] <= date(2026, 2, 28)
    assert date(2026, 3, 2) not in sess
    assert date(2026, 3, 2).month == 3
    assert all(d.month in {1, 2} and d.year == 2026 for d in sess)
    jan = arrow74_january()
    feb = arrow74_february()
    assert all(d.month == 1 for d in jan)
    assert all(d.month == 2 for d in feb)
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)


def test_do_not_read_lab_a_or_full() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 2, 3)) == VIRGIN_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR
    assert tape_root(date(2026, 2, 3)) != FULL_BARS
    for d in (date(2026, 1, 2), date(2026, 1, 7), date(2026, 2, 27)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) != FULL_BARS
        assert tape_root(d) == VIRGIN_BARS
