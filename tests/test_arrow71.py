from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow65 import fill_session_of
from research.arrow66 import hold_exit_of
from research.arrow71 import (
    CONTROL_ID,
    EXPERIMENTS,
    FILL_KIND,
    HOLD_BACKSTOP,
    IDS,
    NOTIONAL,
    first_cash_rule,
    fires_A,
    fires_B,
    fires_C,
    remaining_names,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id0_hold10_no_abc() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "h10_4k"
    assert EXPERIMENTS[0][1] == ()
    assert FILL_KIND == "nextrth"
    assert HOLD_BACKSTOP == 10
    assert NOTIONAL == 4000.0
    assert len(EXPERIMENTS) == 6
    assert IDS == tuple(e[0] for e in EXPERIMENTS)
    fill = date(2026, 1, 8)
    sess = [
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
        date(2026, 1, 13),
        date(2026, 1, 14),
        date(2026, 1, 15),
        date(2026, 1, 16),
        date(2026, 1, 20),
        date(2026, 1, 21),
        date(2026, 1, 22),
        date(2026, 1, 23),
    ]
    assert hold_exit_of(fill, 10, sess) == date(2026, 1, 23)
    assert shares_for(20.0, 4000.0) == 200
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert first_cash_rule(3, "AAA", 10.0, 9.0, [], {"AAA"}, ()) is None


def test_id1_cashes_name_that_leaves_top20_before_day10() -> None:
    assert EXPERIMENTS[1][0] == "cash_A"
    assert EXPERIMENTS[1][1] == ("A",)
    top20 = {f"N{i}" for i in range(20)}
    assert fires_A("ZZZ", top20) is True
    assert fires_A("N0", top20) is False
    assert fires_A("ZZZ", None) is False
    assert first_cash_rule(4, "ZZZ", 10.0, 12.0, [], top20, ("A",)) == "A"
    assert first_cash_rule(4, "N0", 10.0, 12.0, [], top20, ("A",)) is None
    assert 4 < HOLD_BACKSTOP


def test_id5_does_not_open_new_leftover_after_cash() -> None:
    assert EXPERIMENTS[5][0] == "cash_ABC"
    assert EXPERIMENTS[5][1] == ("A", "B", "C")
    kept = remaining_names(["OLD1", "OLD2", "OLD3"], {"OLD1"}, ["NEW", "OLD2", "OLD3"])
    assert kept == ["OLD2", "OLD3"]
    assert "NEW" not in kept
    assert "OLD1" not in kept
    assert fires_B(12.0, 10.0, []) is True
    assert fires_B(9.0, 10.0, [8.0, 8.5]) is True
    assert fires_B(9.0, 10.0, [9.5, 11.0]) is False
    assert fires_C(2, 10.0, 10.0) is False
    assert fires_C(3, 10.0, 10.0) is True
    assert fires_C(3, 9.89, 10.0) is False


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
