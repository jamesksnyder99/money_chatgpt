from datetime import date, time

from ingest.paths import BARS_DIR, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow65 import fill_px, fill_session_of
from research.arrow66 import FILL_KIND
from research.arrow76 import EXIT_1029
from research.arrow77 import (
    CONTROL_ID,
    EXPERIMENTS,
    h10_live_at_0930,
    weekday_ok,
)
from research.clock import (
    arrow76_sessions,
    feature_sessions,
    tape_root,
)
from research.costs import signed_pnl
from research.signals import MINUTE_1559


def test_id0_every_session_exit_1029() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "all"
    assert EXPERIMENTS[0][1] is None
    assert weekday_ok(None, date(2026, 1, 2)) is True
    assert weekday_ok(None, date(2026, 1, 14)) is True
    assert EXIT_1029 == time(10, 29)
    assert EXIT_1029 != MINUTE_1559
    assert len(EXPERIMENTS) == 6
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_id3_wednesday_only() -> None:
    assert EXPERIMENTS[3][0] == "wed"
    assert EXPERIMENTS[3][1] == 2
    wed = date(2026, 1, 14)
    assert wed.weekday() == 2
    assert weekday_ok(2, wed) is True
    assert weekday_ok(2, date(2026, 1, 15)) is False
    assert weekday_ok(2, date(2026, 1, 12)) is False


def test_h10_fill_is_not_daybook_0930() -> None:
    assert FILL_KIND == "nextrth"
    wed = date(2026, 1, 14)
    nxt = date(2026, 1, 15)
    cal = [wed, nxt, date(2026, 1, 16)]
    assert fill_session_of(wed, "nextrth", cal) == nxt
    assert fill_session_of(wed, "nextrth", cal) != wed
    assert fill_px("nextrth", "sig_close", "next_open", "next_rth") == "next_rth"
    assert fill_px("nextrth", "sig_close", "next_open", "next_rth") != "next_open"
    assert fill_px("open", "sig_close", "next_open", "next_rth") == "next_open"
    # live at 09:30: after fill last-RTH, through exit session morning
    fill_d, exit_d = nxt, date(2026, 1, 30)
    assert h10_live_at_0930(fill_d, exit_d, fill_d) is False
    assert h10_live_at_0930(fill_d, exit_d, date(2026, 1, 16)) is True
    assert h10_live_at_0930(fill_d, exit_d, exit_d) is True
    assert EXIT_1029 == time(10, 29)


def test_may_is_not_scored() -> None:
    sess = arrow76_sessions()
    assert sess[0] == date(2026, 1, 2)
    assert sess[-1] <= date(2026, 4, 30)
    assert date(2026, 5, 1) not in sess
    assert all(d.month in {1, 2, 3, 4} and d.year == 2026 for d in sess)
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)


def test_do_not_read_lab_a() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 4, 30)) == VIRGIN_BARS
    for d in (date(2026, 1, 2), date(2026, 3, 16), date(2026, 4, 30)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) == VIRGIN_BARS
