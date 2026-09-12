from datetime import date

from ingest.paths import BARS_DIR, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow76 import EXIT_1029, FILL_0931
from research.arrow79 import (
    COMP_ID,
    CONTROL_ID,
    EXPERIMENTS,
    TUESDAY,
    cross_picks,
    is_tuesday,
)
from research.clock import arrow76_sessions, feature_sessions, tape_root
from research.costs import signed_pnl


def test_id2_off_h10_and_gap_dn() -> None:
    assert EXPERIMENTS[2][0] == "comp_gap_dn"
    assert EXPERIMENTS[2][1] == "complement"
    assert EXPERIMENTS[2][2] == "dn"
    eight = [
        {"symbol": "AAA", "gap": -0.02},
        {"symbol": "BBB", "gap": -0.01},
        {"symbol": "CCC", "gap": 0.03},
        {"symbol": "DDD", "gap": None},
    ]
    live = {"BBB", "EEE"}
    got = cross_picks(eight, live, base="complement", gap="dn", skip_tue=False, weekday=0)
    assert [r["symbol"] for r in got] == ["AAA"]
    assert all(r["symbol"] not in live for r in got)
    assert all(r["gap"] < 0 for r in got)
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_id4_has_no_tuesday_fills() -> None:
    assert EXPERIMENTS[4][0] == "all_not_tue"
    assert EXPERIMENTS[4][3] is True
    tue = date(2026, 1, 6)
    assert tue.weekday() == TUESDAY == 1
    assert is_tuesday(tue) is True
    eight = [{"symbol": "AAA", "gap": -0.01}, {"symbol": "BBB", "gap": 0.02}]
    got = cross_picks(eight, set(), base="all", gap=None, skip_tue=True, weekday=tue.weekday())
    assert got == []
    mon = date(2026, 1, 5)
    got_mon = cross_picks(eight, set(), base="all", gap=None, skip_tue=True, weekday=mon.weekday())
    assert [r["symbol"] for r in got_mon] == ["AAA", "BBB"]
    assert FILL_0931.hour == 9 and FILL_0931.minute == 31
    assert EXIT_1029.hour == 10 and EXIT_1029.minute == 29
    assert EXPERIMENTS[0][0] == CONTROL_ID == "all_0931"
    assert EXPERIMENTS[1][0] == COMP_ID == "comp"
    assert len(EXPERIMENTS) == 6


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
