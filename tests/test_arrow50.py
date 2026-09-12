from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import shares_for
from research.arrow50 import (
    EXPERIMENTS,
    NOTIONAL,
    give5_hold,
    iwm_blocks_week,
)
from research.clock import entry_split, is_is_session, next_session, session_shift, tape_root
from research.costs import signed_pnl
from research.signals import MINUTE_1559, RTH_OPEN


def test_id0_short_only_6000_entry_last_rth_not_0930() -> None:
    assert EXPERIMENTS[0][0] == "fri_h10"
    assert EXPERIMENTS[0][1:] == (10, "close", "h10", None)
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
    assert EXPERIMENTS[0][2] == "close"


def test_id1_entry_is_0930_of_next_session() -> None:
    assert EXPERIMENTS[1][0] == "mon_h10"
    assert EXPERIMENTS[1][2] == "open_next"
    fri = date(2026, 1, 2)
    nxt = next_session(fri)
    assert nxt is not None and nxt > fri
    assert RTH_OPEN.hour == 9 and RTH_OPEN.minute == 30


def test_id3_exits_at_5_when_ahead_else_10() -> None:
    assert EXPERIMENTS[3][0] == "fri_give5"
    assert EXPERIMENTS[3][3] == "give5"
    assert give5_hold(20.0, 19.0, 18.0) == 5
    assert give5_hold(20.0, 21.0, 18.0) == 10
    assert give5_hold(20.0, 20.0, 18.0) == 10
    assert give5_hold(20.0, 19.0, None) == 5
    assert give5_hold(20.0, 21.0, None) is None


def test_id4_does_not_enter_when_iwm_10s_at_or_above_008() -> None:
    assert EXPERIMENTS[4][0] == "fri_h10_iwm8"
    assert EXPERIMENTS[4][4] == 0.08
    assert iwm_blocks_week(100.0, 108.0) is True
    assert iwm_blocks_week(100.0, 107.9) is False
    assert iwm_blocks_week(100.0, 108.0 + 1e-9) is True


def test_id5_uses_close_15_sessions_back() -> None:
    assert EXPERIMENTS[5][0] == "lb15_fri_h10"
    assert EXPERIMENTS[5][1] == 15
    d = date(2026, 1, 16)
    back10 = session_shift(d, -10)
    back15 = session_shift(d, -15)
    assert back10 is not None and back15 is not None
    assert back15 < back10 < d


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
