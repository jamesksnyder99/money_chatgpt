from datetime import date

from ingest.calendar import nyse_sessions
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow68 import arrow68_signal_dates
from research.arrow72 import wednesday_exists
from research.arrow73 import ALWAYS_ID, EXPERIMENTS, FILL_KIND, IDS, NOTIONAL, UP_ID
from research.clock import (
    arrow68_feature_sessions,
    arrow68_score_sessions,
    feature_sessions,
    tape_root,
)
from research.costs import signed_pnl


def test_id0_has_no_skip() -> None:
    assert EXPERIMENTS[0][0] == ALWAYS_ID == "always"
    assert EXPERIMENTS[0][1] == "always"
    assert len(EXPERIMENTS) == 2
    assert IDS == (ALWAYS_ID, UP_ID)
    assert FILL_KIND == "nextrth"
    assert NOTIONAL == 4000.0
    down = {"iwm_15": -0.04}
    assert wednesday_exists("always", down, None) is True
    assert wednesday_exists("always", None, None) is True
    assert shares_for(20.0, 4000.0) == 200
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0


def test_id1_no_new_fills_when_iwm_15_negative() -> None:
    assert EXPERIMENTS[1][0] == UP_ID == "iwm_up"
    assert EXPERIMENTS[1][1] == "iwm_up"
    down = {"iwm_15": -0.01}
    zero = {"iwm_15": 0.0}
    up = {"iwm_15": 0.02}
    assert wednesday_exists("iwm_up", down, None) is False
    assert wednesday_exists("iwm_up", zero, None) is True
    assert wednesday_exists("iwm_up", up, None) is True


def test_2026_not_in_signal_set() -> None:
    sigs = arrow68_signal_dates()
    assert sigs[0] == date(2025, 9, 3)
    assert sigs[-1] == date(2025, 12, 31)
    assert all(d.year == 2025 for d in sigs)
    for d in nyse_sessions(date(2026, 1, 2), date(2026, 8, 31)):
        assert d not in sigs
    score = arrow68_score_sessions()
    assert score[0] == date(2025, 9, 2)
    assert score[-1] == date(2025, 12, 31)
    assert date(2026, 1, 2) not in score
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)
    feats = arrow68_feature_sessions()
    assert date(2025, 8, 1) in feats
    assert date(2026, 1, 2) in feats


def test_do_not_read_lab_a_bars() -> None:
    assert tape_root(date(2025, 9, 3)) == VIRGIN_BARS
    assert tape_root(date(2025, 9, 3)) != BARS_DIR
    assert tape_root(date(2025, 9, 3)) != FULL_BARS
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR
    for d in (date(2025, 9, 3), date(2026, 1, 7), date(2026, 6, 3), date(2026, 8, 26)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
