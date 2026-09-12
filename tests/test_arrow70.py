from datetime import date

from ingest.calendar import nyse_sessions
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow65 import fill_px, fill_session_of
from research.arrow70 import (
    BASE_TICKET,
    COMP_ID,
    FILL_KIND,
    FLAT_ID,
    IDS,
    START_EQUITY,
    arrow70_signal_dates,
    compound_ticket,
    flat_ticket,
)
from research.clock import (
    arrow70_feature_sessions,
    arrow70_score_sessions,
    feature_sessions,
    session_shift,
    tape_root,
)
from research.costs import signed_pnl


def test_id0_ticket_always_4000() -> None:
    assert IDS == (FLAT_ID, COMP_ID)
    assert FLAT_ID == "flat_4k"
    assert COMP_ID == "comp_4k"
    assert len(IDS) == 2
    assert flat_ticket() == BASE_TICKET == 4000.0
    assert flat_ticket() == 4000.0
    assert shares_for(20.0, 4000.0) == 200
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0


def test_id1_ticket_not_4000_when_equity_not_100k() -> None:
    assert compound_ticket(START_EQUITY) == 4000.0
    assert compound_ticket(120_000.0) == 4800.0
    assert compound_ticket(120_000.0) != 4000.0
    assert compound_ticket(80_000.0) == 3200.0
    assert compound_ticket(80_000.0) != 4000.0
    assert compound_ticket(0.0) == 0.0
    assert compound_ticket(-50.0) == 0.0
    later = date(2026, 1, 7)
    assert later.weekday() == 2
    assert compound_ticket(110_000.0) != flat_ticket()


def test_fill_is_next_lastrth() -> None:
    feats = arrow70_feature_sessions()
    sig = date(2025, 9, 3)
    assert sig.weekday() == 2
    assert FILL_KIND == "nextrth"
    assert fill_session_of(sig, "nextrth", feats) == date(2025, 9, 4)
    assert fill_session_of(sig, "nextrth", feats) != sig
    assert fill_session_of(date(2026, 5, 27), "nextrth", feats) == date(2026, 5, 28)
    sc, op, rth = (10.0, "sig"), (11.0, "open"), (12.0, "rth")
    assert fill_px("nextrth", sc, op, rth) == rth
    assert fill_px("nextrth", sc, op, rth) != sc


def test_first_signal_not_before_15_prior_sessions() -> None:
    sep_only = nyse_sessions(date(2025, 9, 2), date(2026, 8, 31))
    assert session_shift(date(2025, 9, 3), -15, sep_only) is None
    feats = arrow70_feature_sessions()
    assert session_shift(date(2025, 9, 3), -15, feats) == date(2025, 8, 12)
    assert arrow70_signal_dates(sep_only)[0] != date(2025, 9, 3)
    assert arrow70_signal_dates(feats)[0] == date(2025, 9, 3)
    for d in arrow70_signal_dates(feats):
        assert session_shift(d, -15, feats) is not None
        assert fill_session_of(d, "nextrth", feats) is not None
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)
    score = arrow70_score_sessions()
    assert score[0] == date(2025, 9, 2)
    assert score[-1] == date(2026, 8, 31)


def test_do_not_read_lab_a_bars() -> None:
    assert tape_root(date(2025, 9, 3)) == VIRGIN_BARS
    assert tape_root(date(2025, 9, 3)) != BARS_DIR
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 5, 29)) == VIRGIN_BARS
    assert tape_root(date(2026, 6, 1)) == FULL_BARS
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
    assert tape_root(date(2026, 7, 1)) != BARS_DIR
    for d in (date(2025, 9, 3), date(2026, 1, 7), date(2026, 6, 3), date(2026, 8, 26)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
