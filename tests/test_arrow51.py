from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import shares_for
from research.arrow50 import give5_hold
from research.arrow51 import EXPERIMENTS, NOTIONAL
from research.clock import entry_split, is_is_session, session_shift, tape_root
from research.costs import signed_pnl
from research.signals import MINUTE_1559, RTH_OPEN


def test_id0_short_only_6000_lookback_15_entry_last_rth() -> None:
    assert EXPERIMENTS[0][0] == "lb15_h10"
    assert EXPERIMENTS[0][1:] == (15, "h10")
    assert NOTIONAL == 6000.0
    assert len(EXPERIMENTS) == 6
    rows = [
        {"residual": 0.20, "symbol": "A"},
        {"residual": 0.05, "symbol": "B"},
        {"residual": -0.10, "symbol": "C"},
    ]
    picks = select_shorts(rows, 8, None)
    assert picks[0]["symbol"] == "A"
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 19.0) < 0
    assert shares_for(20.0, 6000.0) == 300
    assert RTH_OPEN != MINUTE_1559


def test_id1_exits_at_5_when_ahead_else_10() -> None:
    assert EXPERIMENTS[1][0] == "lb15_give5"
    assert EXPERIMENTS[1][2] == "give5"
    assert give5_hold(20.0, 19.0, 18.0) == 5
    assert give5_hold(20.0, 21.0, 18.0) == 10
    assert give5_hold(20.0, 20.0, 18.0) == 10
    assert give5_hold(20.0, 19.0, None) == 5
    assert give5_hold(20.0, 21.0, None) is None


def test_id3_uses_close_20_sessions_back() -> None:
    assert EXPERIMENTS[3][0] == "lb20_h10"
    assert EXPERIMENTS[3][1] == 20
    d = date(2026, 1, 30)
    back15 = session_shift(d, -15)
    back20 = session_shift(d, -20)
    assert back15 is not None and back20 is not None
    assert back20 < back15 < d


def test_id5_exit_is_15_sessions_after_entry() -> None:
    assert EXPERIMENTS[5][0] == "lb15_h15"
    assert EXPERIMENTS[5][2] == "h15"
    d = date(2026, 1, 2)
    e10 = session_shift(d, 10)
    e15 = session_shift(d, 15)
    assert e10 is not None and e15 is not None
    assert e15 > e10 > d


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
