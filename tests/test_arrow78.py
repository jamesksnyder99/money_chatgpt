from datetime import date, time

from ingest.paths import BARS_DIR, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow76 import EXIT_1029, FILL_0931
from research.arrow77 import h10_live_at_0930
from research.arrow78 import (
    CAUSAL_ID,
    CONTROL_ID,
    EXPERIMENTS,
    fill_stamp,
    filter_eight,
)
from research.clock import arrow76_sessions, feature_sessions, tape_root
from research.costs import signed_pnl
from research.signals import RTH_OPEN


def test_id2_never_shorts_h10_live() -> None:
    assert EXPERIMENTS[2][0] == "complement"
    assert EXPERIMENTS[2][2] == "complement"
    eight = [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}]
    live = {"BBB", "DDD"}
    got = filter_eight(eight, "complement", live)
    assert [r["symbol"] for r in got] == ["AAA", "CCC"]
    assert all(r["symbol"] not in live for r in got)
    assert not any(r["symbol"] == "EEE" for r in got)


def test_id3_never_shorts_off_h10() -> None:
    assert EXPERIMENTS[3][0] == "overlap_only"
    assert EXPERIMENTS[3][2] == "overlap"
    eight = [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}]
    live = {"BBB", "DDD"}
    got = filter_eight(eight, "overlap", live)
    assert [r["symbol"] for r in got] == ["BBB"]
    assert all(r["symbol"] in live for r in got)
    fill_d, exit_d = date(2026, 1, 15), date(2026, 1, 30)
    assert h10_live_at_0930(fill_d, exit_d, fill_d) is False
    assert h10_live_at_0930(fill_d, exit_d, date(2026, 1, 16)) is True


def test_id1_fill_is_0931_not_0930() -> None:
    assert EXPERIMENTS[1][0] == CAUSAL_ID == "all_0931"
    assert EXPERIMENTS[1][1] == "0931"
    assert EXPERIMENTS[0][0] == CONTROL_ID == "all_0930"
    assert EXPERIMENTS[0][1] == "0930"
    assert fill_stamp("0931") == FILL_0931 == time(9, 31)
    assert fill_stamp("0931") != RTH_OPEN
    assert fill_stamp("0930") == RTH_OPEN == time(9, 30)
    assert fill_stamp("0931") >= time(9, 31)
    assert EXIT_1029 == time(10, 29)
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert shares_for(20.0, 3000.0) == 150
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
