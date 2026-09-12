from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import EXPERIMENTS, shares_for
from research.clock import entry_split, is_is_session, session_shift, tape_root
from research.costs import signed_pnl


def test_id0_short_only() -> None:
    assert EXPERIMENTS[0][0] == "n15_lb10_h10"
    assert EXPERIMENTS[0][1:] == (15, 10, 10, None, 2000.0)
    assert len(EXPERIMENTS) == 6
    rows = [
        {"residual": 0.20, "symbol": "A"},
        {"residual": 0.05, "symbol": "B"},
        {"residual": -0.10, "symbol": "C"},
    ]
    picks = select_shorts(rows, 15, None)
    assert picks[0]["symbol"] == "A"
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 19.0) < 0


def test_even_month_entry_is_not_is() -> None:
    assert entry_split(date(2026, 2, 6)) == "OOS"
    assert not is_is_session(date(2026, 2, 6))
    assert is_is_session(date(2026, 1, 2))


def test_r20_never_shorts_under_bar() -> None:
    rows = [
        {"residual": 0.25, "symbol": "HI"},
        {"residual": 0.20, "symbol": "OK"},
        {"residual": 0.19, "symbol": "LO"},
        {"residual": 0.08, "symbol": "MID"},
    ]
    got = select_shorts(rows, 15, 0.20)
    assert {r["symbol"] for r in got} == {"HI", "OK"}
    assert all(r["residual"] >= 0.20 - 1e-12 for r in got)
    assert "LO" not in {r["symbol"] for r in got}


def test_h5_exit_is_five_sessions_h10_is_ten() -> None:
    d = date(2026, 1, 2)
    e5 = session_shift(d, 5)
    e10 = session_shift(d, 10)
    assert e5 is not None and e10 is not None
    assert e10 > e5
    assert EXPERIMENTS[3][0] == "n15_lb10_h5"
    assert EXPERIMENTS[3][3] == 5
    assert EXPERIMENTS[0][3] == 10


def test_id5_uses_3000_in_share_count() -> None:
    assert EXPERIMENTS[5][0] == "n15_lb10_h10_3k"
    assert EXPERIMENTS[5][5] == 3000.0
    assert shares_for(20.0, 2000.0) == 100
    assert shares_for(20.0, 3000.0) == 150
    assert shares_for(20.0, 3000.0) != shares_for(20.0, 2000.0)


def test_july_from_full_january_from_virgin() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 2)) == FULL_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 2), date(2026, 6, 5), date(2026, 8, 28)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
