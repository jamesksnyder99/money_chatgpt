from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow57 import (
    CONTROL_ID,
    EXPERIMENTS,
    LONG_H1,
    hold_exit,
    name_return,
    select_losers,
    select_winners,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_short_only_id1_long_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "short_win_h1"
    assert EXPERIMENTS[0][1] == "short"
    assert EXPERIMENTS[1][0] == LONG_H1 == "long_lose_h1"
    assert EXPERIMENTS[1][1] == "long"
    assert len(EXPERIMENTS) == 6
    assert all(e[1] == "short" for e in EXPERIMENTS if e[0].startswith("short_"))
    assert all(e[1] == "long" for e in EXPERIMENTS if e[0].startswith("long_"))
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 21.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_id0_ranks_raw_return_not_15session_residual() -> None:
    rows = [
        {"ret": 0.02, "residual": 0.50, "symbol": "A"},
        {"ret": 0.10, "residual": 0.01, "symbol": "B"},
        {"ret": -0.05, "residual": 0.20, "symbol": "C"},
    ]
    win = select_winners(rows, 1, "ret")
    assert win[0]["symbol"] == "B"
    lose = select_losers(rows, 1, "ret")
    assert lose[0]["symbol"] == "C"
    assert EXPERIMENTS[0][3] == "raw"
    nr = name_return(100.0, 110.0)
    assert nr is not None and abs(nr - 0.10) < 1e-12
    assert name_return(None, 110.0) is None


def test_hold1_exits_next_session_hold5_exits_five_later() -> None:
    sess = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    assert EXPERIMENTS[0][4] == 1
    assert EXPERIMENTS[2][4] == 5
    assert hold_exit(date(2026, 1, 2), 1, sess) == date(2026, 1, 5)
    assert hold_exit(date(2026, 1, 2), 5, sess) == date(2026, 1, 9)
    assert hold_exit(date(2026, 1, 2), 1, sess) != hold_exit(date(2026, 1, 2), 5, sess)


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
