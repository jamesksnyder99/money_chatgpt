from datetime import date
import statistics

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow45 import select_shorts
from research.arrow47 import shares_for
from research.arrow53 import (
    CONTROL_ID,
    EXPERIMENTS,
    LB,
    NOTIONAL,
    WED_ID,
    name_return,
    price_bucket,
    residual_vs_iwm,
    residual_vs_median,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_short_only_friday_lb15_residual_subtracts_iwm() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "vs_iwm"
    assert EXPERIMENTS[0][1] == 4
    assert EXPERIMENTS[0][2] == "iwm"
    assert LB == 15
    assert NOTIONAL == 6000.0
    assert len(EXPERIMENTS) == 6
    rows = [
        {"residual": 0.20, "symbol": "A"},
        {"residual": 0.05, "symbol": "B"},
        {"residual": -0.10, "symbol": "C"},
    ]
    picks = select_shorts(rows, 8, None)
    assert picks[0]["symbol"] == "A"
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert date(2026, 1, 2).weekday() == 4
    nr = name_return(100.0, 120.0)
    assert nr is not None and abs(nr - 0.20) < 1e-12
    assert abs(residual_vs_iwm(0.20, 0.10) - 0.10) < 1e-12
    assert residual_vs_iwm(0.20, 0.10) != 0.20


def test_id1_residual_is_name_minus_eligible_median_not_iwm() -> None:
    name_rets = [0.30, 0.10, 0.00]
    iwm = 0.20
    med = statistics.median(name_rets)
    assert abs(med - 0.10) < 1e-12
    univ = residual_vs_median(0.30, med)
    iwm_r = residual_vs_iwm(0.30, iwm)
    assert abs(univ - 0.20) < 1e-12
    assert abs(iwm_r - 0.10) < 1e-12
    assert univ != iwm_r
    assert EXPERIMENTS[1][0] == "vs_univ"
    assert EXPERIMENTS[1][2] == "univ"


def test_id2_uses_the_same_price_bucket() -> None:
    assert price_bucket(15.0) == price_bucket(19.99) == 0
    assert price_bucket(20.0) == price_bucket(39.99) == 1
    assert price_bucket(40.0) == price_bucket(80.0) == 2
    assert price_bucket(15.0) != price_bucket(25.0)
    assert price_bucket(9.99) is None
    assert EXPERIMENTS[2][0] == "vs_px"


def test_id5_entries_are_wednesdays_only() -> None:
    assert EXPERIMENTS[5][0] == WED_ID == "wed_vs_univ"
    assert EXPERIMENTS[5][1] == 2
    wed = date(2026, 1, 7)
    assert wed.weekday() == 2
    assert date(2026, 1, 2).weekday() != 2
    assert shares_for(20.0, 6000.0) == 300


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
