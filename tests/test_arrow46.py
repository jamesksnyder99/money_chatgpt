from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow44 import residual
from research.arrow45 import select_shorts
from research.clock import entry_split, is_is_session, session_shift, tape_root
from research.costs import signed_pnl


def test_id0_short_only() -> None:
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


def test_r15_never_shorts_under_bar() -> None:
    rows = [
        {"residual": 0.20, "symbol": "HI"},
        {"residual": 0.16, "symbol": "OK"},
        {"residual": 0.14, "symbol": "LO"},
        {"residual": 0.08, "symbol": "MID"},
    ]
    got = select_shorts(rows, 15, 0.15)
    assert {r["symbol"] for r in got} == {"HI", "OK"}
    assert all(r["residual"] >= 0.15 - 1e-12 for r in got)
    assert "LO" not in {r["symbol"] for r in got}


def test_lb10_uses_close_ten_sessions_back_not_five() -> None:
    r5 = residual(105.0, 110.0, 100.0, 100.0)
    r10 = residual(100.0, 110.0, 100.0, 100.0)
    assert r5 is not None and r10 is not None
    assert abs(r10 - 0.10) < 1e-12
    assert abs(r5 - r10) > 1e-6
    d = date(2026, 1, 2)
    back5 = session_shift(d, -5)
    back10 = session_shift(d, -10)
    assert back5 is not None and back10 is not None
    assert back10 < back5 < d


def test_h10_exit_is_ten_sessions_after_entry() -> None:
    d = date(2026, 1, 2)
    e5 = session_shift(d, 5)
    e10 = session_shift(d, 10)
    assert e5 is not None and e10 is not None
    assert e10 > e5


def test_july_from_full_january_from_virgin() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 2)) == FULL_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 2), date(2026, 6, 5), date(2026, 8, 28)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
