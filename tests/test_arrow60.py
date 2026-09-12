from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow60 import (
    CONTROL_ID,
    EXPERIMENTS,
    LONG_H1,
    gave_back,
    is_extreme,
    select_extremes,
    still_extended,
)
from research.clock import entry_split, is_is_session, session_shift, tape_root
from research.costs import signed_pnl


def test_id0_short_only_id1_long_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "short_0930_1159"
    assert EXPERIMENTS[0][1] == "short"
    assert EXPERIMENTS[1][0] == LONG_H1 == "long_0930_1159"
    assert EXPERIMENTS[1][1] == "long"
    assert len(EXPERIMENTS) == 6
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 21.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_extreme_uses_t_high_vs_prior_close_entry_is_tplus1() -> None:
    assert is_extreme(11.0, 10.0) is True
    assert is_extreme(10.9, 10.0) is False
    assert is_extreme(None, 10.0) is False
    rows = [
        {"ext": 0.20, "symbol": "A"},
        {"ext": 0.12, "symbol": "B"},
        {"ext": 0.15, "symbol": "C"},
    ]
    top = select_extremes(rows, 2)
    assert [r["symbol"] for r in top] == ["A", "C"]
    sess = [date(2026, 1, 2), date(2026, 1, 5), date(2026, 1, 6)]
    assert session_shift(date(2026, 1, 2), 1, sess) == date(2026, 1, 5)


def test_id3_rejects_t_close_lt_1_05_prior() -> None:
    assert EXPERIMENTS[3][0] == "short_still_1159"
    assert EXPERIMENTS[3][3] == "still"
    assert still_extended(10.5, 10.0) is True
    assert still_extended(10.4, 10.0) is False
    assert still_extended(10.49, 10.0) is False
    assert gave_back(10.4, 10.0) is True
    assert gave_back(10.5, 10.0) is False


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
