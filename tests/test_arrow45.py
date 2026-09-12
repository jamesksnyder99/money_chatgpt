from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.clock import entry_split, is_is_session, session_shift, tape_root
from research.arrow43 import _pack
from research.costs import signed_pnl


def test_id0_is_short_only() -> None:
    rows = [
        {"residual": 0.10, "symbol": "A"},
        {"residual": -0.10, "symbol": "B"},
        {"residual": 0.05, "symbol": "C"},
    ]
    picks = select_shorts(rows, 15, None)
    assert [p["symbol"] for p in picks] == ["A", "C", "B"]
    # control shorts winners (high residual) first; no long leg in this family
    assert picks[0]["residual"] > 0
    pnl_short = signed_pnl(-1, 10, 20.0, 19.0)
    pnl_long = signed_pnl(1, 10, 20.0, 19.0)
    assert pnl_short > 0
    assert pnl_long < 0
    rec = _pack(pnl_short, -1, 10, 20.0, 19.0, None, None, "n15_h5", "A")
    assert rec["side"] == -1


def test_even_month_entry_is_not_is() -> None:
    assert entry_split(date(2026, 2, 6)) == "OOS"
    assert not is_is_session(date(2026, 2, 6))
    assert is_is_session(date(2026, 1, 2))


def test_r04_r08_never_short_under_bar() -> None:
    rows = [
        {"residual": 0.09, "symbol": "HI"},
        {"residual": 0.05, "symbol": "MID"},
        {"residual": 0.03, "symbol": "LO"},
        {"residual": -0.01, "symbol": "NEG"},
    ]
    r04 = select_shorts(rows, 15, 0.04)
    assert {r["symbol"] for r in r04} == {"HI", "MID"}
    assert all(r["residual"] >= 0.04 - 1e-12 for r in r04)
    r08 = select_shorts(rows, 15, 0.08)
    assert [r["symbol"] for r in r08] == ["HI"]
    assert all(r["residual"] >= 0.08 - 1e-12 for r in r08)
    # do not fill the seat with names under the bar even if n < 8
    assert len(r08) < 8


def test_h10_exit_is_ten_sessions_not_five() -> None:
    d = date(2026, 1, 2)
    e5 = session_shift(d, 5)
    e10 = session_shift(d, 10)
    assert e5 is not None and e10 is not None
    assert e10 > e5
    assert e10 != e5
    # 2026-01-02 plus 10 sessions is still on the combined calendar
    assert e10.month in (1, 2)


def test_july_from_full_january_from_virgin() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 2)) == FULL_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR
    assert tape_root(date(2026, 7, 2)) != BARS_DIR


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 2), date(2026, 6, 5), date(2026, 8, 28)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
