from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import shares_for
from research.arrow48 import EXPERIMENTS
from research.clock import entry_split, is_is_session, session_shift, tape_root
from research.costs import signed_pnl


def test_id0_short_only_and_3000_share_count() -> None:
    assert EXPERIMENTS[0][0] == "n15_h10_3k"
    assert EXPERIMENTS[0][1:] == (15, 10, 3000.0)
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
    assert shares_for(20.0, 3000.0) == 150


def test_even_month_entry_is_not_is() -> None:
    assert entry_split(date(2026, 2, 6)) == "OOS"
    assert not is_is_session(date(2026, 2, 6))
    assert is_is_session(date(2026, 1, 2))


def test_4k_5k_share_counts_match_notional() -> None:
    assert EXPERIMENTS[1][0] == "n15_h10_4k"
    assert EXPERIMENTS[1][3] == 4000.0
    assert EXPERIMENTS[2][0] == "n15_h10_5k"
    assert EXPERIMENTS[2][3] == 5000.0
    assert shares_for(20.0, 4000.0) == 200
    assert shares_for(20.0, 5000.0) == 250
    assert shares_for(20.0, 4000.0) != shares_for(20.0, 3000.0)
    assert shares_for(20.0, 5000.0) != shares_for(20.0, 4000.0)


def test_h5_exit_is_five_sessions_h10_is_ten() -> None:
    d = date(2026, 1, 2)
    e5 = session_shift(d, 5)
    e10 = session_shift(d, 10)
    assert e5 is not None and e10 is not None
    assert e10 > e5
    assert EXPERIMENTS[0][2] == 10
    assert EXPERIMENTS[4][0] == "n15_h5_3k"
    assert EXPERIMENTS[4][2] == 5
    assert EXPERIMENTS[5][0] == "n8_h5_3k"
    assert EXPERIMENTS[5][2] == 5


def test_july_from_full_january_from_virgin() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 2)) == FULL_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 2), date(2026, 6, 5), date(2026, 8, 28)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
