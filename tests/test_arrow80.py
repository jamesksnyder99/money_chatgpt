from datetime import date, time

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow76 import EXIT_1029, EXIT_1129, exit_stamp
from research.arrow78 import filter_eight
from research.arrow79 import TUESDAY, is_tuesday
from research.arrow80 import CONTROL_ID, EXPERIMENTS, year_picks
from research.clock import (
    arrow70_score_sessions,
    feature_sessions,
    tape_root,
)
from research.costs import signed_pnl


def test_id4_never_shorts_h10_live() -> None:
    assert EXPERIMENTS[4][0] == "comp_1029"
    assert EXPERIMENTS[4][4] is True
    eight = [{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}]
    live = {"BBB", "DDD"}
    got = filter_eight(eight, "complement", live)
    assert [r["symbol"] for r in got] == ["AAA", "CCC"]
    assert all(r["symbol"] not in live for r in got)
    got2 = year_picks(eight, 8, live, skip_tue=False, complement=True, weekday=0)
    assert all(r["symbol"] not in live for r in got2)


def test_id2_has_no_tuesday_fills() -> None:
    assert EXPERIMENTS[2][0] == "n8_1029_notue"
    assert EXPERIMENTS[2][3] is True
    tue = date(2026, 1, 6)
    assert tue.weekday() == TUESDAY == 1
    assert is_tuesday(tue) is True
    eight = [{"symbol": "AAA"}, {"symbol": "BBB"}]
    got = year_picks(eight, 8, set(), skip_tue=True, complement=False, weekday=tue.weekday())
    assert got == []
    mon = date(2026, 1, 5)
    got_mon = year_picks(eight, 8, set(), skip_tue=True, complement=False, weekday=mon.weekday())
    assert [r["symbol"] for r in got_mon] == ["AAA", "BBB"]
    assert EXPERIMENTS[1][0] == CONTROL_ID == "n8_1029"
    assert len(EXPERIMENTS) == 5
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_id3_exits_1129_not_1029() -> None:
    assert EXPERIMENTS[3][0] == "n8_1129"
    assert EXPERIMENTS[3][2] == "1129"
    assert exit_stamp("1129") == EXIT_1129 == time(11, 29)
    assert exit_stamp("1029") == EXIT_1029 == time(10, 29)
    assert exit_stamp("1129") != EXIT_1029
    assert EXPERIMENTS[0][2] == "1029"
    assert EXPERIMENTS[1][2] == "1029"


def test_do_not_read_lab_a() -> None:
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)
    score = arrow70_score_sessions()
    assert score[0] == date(2025, 9, 2)
    assert score[-1] == date(2026, 8, 31)
    assert tape_root(date(2025, 9, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 5, 29)) == VIRGIN_BARS
    assert tape_root(date(2026, 6, 1)) == FULL_BARS
    for d in (date(2025, 9, 2), date(2026, 1, 16), date(2026, 6, 1), date(2026, 8, 31)):
        assert tape_root(d) != BARS_DIR
