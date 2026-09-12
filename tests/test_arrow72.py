from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow65 import fill_session_of
from research.arrow72 import (
    CONTROL_ID,
    EXPERIMENTS,
    FILL_KIND,
    IDS,
    NOTIONAL,
    wednesday_exists,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_has_no_wednesday_skip() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "h10_4k"
    assert EXPERIMENTS[0][1] == "always"
    assert FILL_KIND == "nextrth"
    assert NOTIONAL == 4000.0
    assert len(EXPERIMENTS) == 6
    assert IDS == tuple(e[0] for e in EXPERIMENTS)
    cuts = {"width": 0.10, "crowd": 12.0, "ivol": 0.02}
    down = {"iwm_15": -0.04, "width": 0.0, "crowd": 99, "ivol": 0.50}
    assert wednesday_exists("always", down, cuts) is True
    assert wednesday_exists("always", None, cuts) is True
    assert shares_for(20.0, 4000.0) == 200
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0


def test_id1_no_new_fills_when_iwm_15_negative() -> None:
    assert EXPERIMENTS[1][0] == "iwm_up"
    assert EXPERIMENTS[1][1] == "iwm_up"
    cuts = {"width": 0.10, "crowd": 12.0, "ivol": 0.02}
    down = {"iwm_15": -0.01, "width": 0.20, "crowd": 1, "ivol": 0.01}
    zero = {"iwm_15": 0.0, "width": 0.20, "crowd": 1, "ivol": 0.01}
    up = {"iwm_15": 0.02, "width": 0.20, "crowd": 1, "ivol": 0.01}
    assert wednesday_exists("iwm_up", down, cuts) is False
    assert wednesday_exists("iwm_up", zero, cuts) is True
    assert wednesday_exists("iwm_up", up, cuts) is True
    assert wednesday_exists("iwm_dn", down, cuts) is True
    assert wednesday_exists("iwm_dn", zero, cuts) is False


def test_even_month_signal_is_not_is() -> None:
    wed = date(2026, 2, 4)
    assert wed.weekday() == 2
    assert entry_split(wed) == "OOS"
    assert not is_is_session(wed)
    assert is_is_session(date(2026, 1, 7))
    sess = [date(2026, 1, 7), date(2026, 1, 8)]
    assert fill_session_of(date(2026, 1, 7), "nextrth", sess) == date(2026, 1, 8)


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 7), date(2026, 6, 3), date(2026, 8, 26)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
    assert tape_root(date(2026, 1, 7)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
