from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow57 import hold_exit, select_losers, select_winners
from research.arrow58 import CONTROL_ID, EXPERIMENTS
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_all_ids_short_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "lose_h1"
    assert len(EXPERIMENTS) == 6
    assert all(name.startswith("lose_") for name, _n, _h, _nt in EXPERIMENTS)
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_loser_slot_is_smallest_not_largest() -> None:
    rows = [
        {"ret": 0.10, "symbol": "WIN"},
        {"ret": 0.01, "symbol": "MID"},
        {"ret": -0.08, "symbol": "LOSE"},
    ]
    lose = select_losers(rows, 1, "ret")
    win = select_winners(rows, 1, "ret")
    assert lose[0]["symbol"] == "LOSE"
    assert win[0]["symbol"] == "WIN"
    assert lose[0]["symbol"] != win[0]["symbol"]
    eight = select_losers(
        [{"ret": i / 100.0, "symbol": str(i)} for i in range(20)],
        8,
        "ret",
    )
    assert [r["symbol"] for r in eight] == [str(i) for i in range(8)]


def test_h1_h5_h10_exit_at_1_5_10_sessions() -> None:
    sess = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
        date(2026, 1, 13),
        date(2026, 1, 14),
        date(2026, 1, 15),
        date(2026, 1, 16),
    ]
    assert EXPERIMENTS[0][2] == 1
    assert EXPERIMENTS[1][2] == 5
    assert EXPERIMENTS[2][2] == 10
    assert hold_exit(date(2026, 1, 2), 1, sess) == date(2026, 1, 5)
    assert hold_exit(date(2026, 1, 2), 5, sess) == date(2026, 1, 9)
    assert hold_exit(date(2026, 1, 2), 10, sess) == date(2026, 1, 16)


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
