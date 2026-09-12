from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow76 import (
    CONTROL_ID,
    EXIT_1029,
    EXPERIMENTS,
    last_at_or_before,
    exit_stamp,
)
from research.clock import (
    arrow76_feature_sessions,
    arrow76_sessions,
    feature_sessions,
    is_is_session,
    tape_root,
)
from research.costs import signed_pnl
from research.signals import MINUTE_1559

ET = ZoneInfo("America/New_York")


def test_id0_exits_1029_not_1559() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "h1029_n8"
    assert EXPERIMENTS[0][2] == "1029"
    assert exit_stamp(EXPERIMENTS[0][2]) == EXIT_1029 == time(10, 29)
    assert exit_stamp(EXPERIMENTS[0][2]) != MINUTE_1559
    prints = [
        (datetime(2026, 1, 16, 9, 30, tzinfo=ET), 10.0),
        (datetime(2026, 1, 16, 10, 29, tzinfo=ET), 10.1),
        (datetime(2026, 1, 16, 11, 29, tzinfo=ET), 10.2),
        (datetime(2026, 1, 16, 15, 59, tzinfo=ET), 10.3),
    ]
    got = last_at_or_before(prints, exit_stamp("1029"))
    assert got is not None
    assert got[0].timetz().replace(tzinfo=None) == time(10, 29)
    assert got[1] == 10.1
    late = last_at_or_before(prints, MINUTE_1559)
    assert late is not None and late[1] == 10.3


def test_id2_exits_1559() -> None:
    assert EXPERIMENTS[2][0] == "h1559_n8"
    assert EXPERIMENTS[2][2] == "1559"
    assert exit_stamp(EXPERIMENTS[2][2]) == MINUTE_1559 == time(15, 59)
    prints = [
        (datetime(2026, 1, 16, 10, 29, tzinfo=ET), 10.1),
        (datetime(2026, 1, 16, 15, 59, tzinfo=ET), 9.5),
    ]
    got = last_at_or_before(prints, exit_stamp("1559"))
    assert got is not None
    assert got[0].timetz().replace(tzinfo=None) == MINUTE_1559
    assert got[1] == 9.5


def test_id0_is_short_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "h1029_n8"
    assert len(EXPERIMENTS) == 6
    assert not any("long" in e[0] for e in EXPERIMENTS)
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert shares_for(20.0, 3000.0) == 150
    assert EXPERIMENTS[4][3] == 4000.0
    assert EXPERIMENTS[5][4] == "wed"


def test_may_is_not_scored() -> None:
    sess = arrow76_sessions()
    assert sess[0] == date(2026, 1, 2)
    assert sess[-1] <= date(2026, 4, 30)
    assert date(2026, 5, 1) not in sess
    assert date(2026, 5, 29) not in sess
    assert all(d.month in {1, 2, 3, 4} and d.year == 2026 for d in sess)
    assert all(is_is_session(d) for d in sess if d.month in {1, 3})
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)
    feats = arrow76_feature_sessions()
    assert feats[0] == date(2025, 12, 1)
    assert feats[-1] <= date(2026, 4, 30)


def test_do_not_read_lab_a() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 3, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 4, 30)) == VIRGIN_BARS
    for d in (date(2026, 1, 2), date(2026, 3, 16), date(2026, 4, 30)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) == VIRGIN_BARS
