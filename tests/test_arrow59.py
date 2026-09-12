from datetime import date, time

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow59 import (
    CONTROL_ID,
    EXPERIMENTS,
    FILL_CLOCK,
    LONG_H1,
    PACE_OPEN,
    WINDOW_END,
    bar_dollar_volume,
    hot_up_pass,
    pace,
    quiet_dn_pass,
    select_hot,
    select_quiet,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl
from research.signals import MINUTE_1000, RTH_OPEN


def test_id0_short_only_id1_long_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "short_hot_1159"
    assert EXPERIMENTS[0][1] == "short"
    assert EXPERIMENTS[1][0] == LONG_H1 == "long_quiet_1159"
    assert EXPERIMENTS[1][1] == "long"
    assert len(EXPERIMENTS) == 6
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 21.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_pace_uses_0930_0959_dollar_volume_over_1000_fill_not_15session_residual() -> None:
    assert PACE_OPEN == RTH_OPEN == time(9, 30)
    assert WINDOW_END == FILL_CLOCK == MINUTE_1000 == time(10, 0)
    assert bar_dollar_volume(10.0, 100) == 1000.0
    assert pace(2000.0, 1000.0) == 2.0
    assert pace(100.0, 0.0) is None
    rows = [
        {"pace": 3.0, "residual": 0.01, "symbol": "HOT"},
        {"pace": 0.4, "residual": 0.90, "symbol": "QUIET"},
        {"pace": 1.0, "residual": 0.50, "symbol": "MID"},
    ]
    assert select_hot(rows, 1)[0]["symbol"] == "HOT"
    assert select_quiet(rows, 1)[0]["symbol"] == "QUIET"
    assert select_hot(rows, 1)[0]["symbol"] != select_quiet(rows, 1)[0]["symbol"]


def test_id4_rejects_hot_name_1000_last_lt_prior_close() -> None:
    assert EXPERIMENTS[4][0] == "short_hot_up_1159"
    assert EXPERIMENTS[4][4] == "up"
    assert hot_up_pass(21.0, 20.0) is True
    assert hot_up_pass(20.0, 20.0) is True
    assert hot_up_pass(19.0, 20.0) is False
    assert hot_up_pass(None, 20.0) is False
    assert quiet_dn_pass(19.0, 20.0) is True
    assert quiet_dn_pass(21.0, 20.0) is False


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
