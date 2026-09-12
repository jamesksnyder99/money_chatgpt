from datetime import date

from ingest.calendar import nyse_sessions
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow65 import fill_px, fill_session_of
from research.arrow68 import (
    CONTROL_ID,
    EXPERIMENTS,
    FILL_KIND,
    IDS,
    KEEP,
    NOTIONAL,
    SIGNAL_HI,
    SIGNAL_LO,
    arrow68_signal_dates,
)
from research.clock import (
    arrow68_feature_sessions,
    arrow68_score_sessions,
    feature_sessions,
    session_shift,
    tape_root,
)
from research.costs import signed_pnl


def test_only_one_id() -> None:
    assert IDS == (CONTROL_ID,)
    assert EXPERIMENTS[0][0] == CONTROL_ID == "wed_h10_4k"
    assert EXPERIMENTS[0][1] == FILL_KIND == "nextrth"
    assert EXPERIMENTS[0][2] == NOTIONAL == 4000.0
    assert EXPERIMENTS[0][3] is KEEP is False
    assert len(EXPERIMENTS) == 1
    assert shares_for(20.0, 4000.0) == 200
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0


def test_fill_is_next_lastrth_not_signal_close() -> None:
    feats = arrow68_feature_sessions()
    sig = date(2025, 9, 3)
    assert sig.weekday() == 2
    assert fill_session_of(sig, "nextrth", feats) == date(2025, 9, 4)
    assert fill_session_of(sig, "nextrth", feats) != sig
    assert fill_session_of(date(2025, 12, 31), "nextrth", feats) == date(2026, 1, 2)
    sc, op, rth = (10.0, "sig"), (11.0, "open"), (12.0, "rth")
    assert fill_px("nextrth", sc, op, rth) == rth
    assert fill_px("nextrth", sc, op, rth) != sc
    assert fill_px("close", sc, op, rth) == sc


def test_no_signal_before_15_prior_sessions() -> None:
    sep_only = nyse_sessions(date(2025, 9, 2), date(2025, 12, 31))
    assert session_shift(date(2025, 9, 3), -15, sep_only) is None
    feats = arrow68_feature_sessions()
    assert session_shift(date(2025, 9, 3), -15, feats) == date(2025, 8, 12)
    assert arrow68_signal_dates(sep_only)[0] != date(2025, 9, 3)
    assert arrow68_signal_dates(feats)[0] == date(2025, 9, 3)
    for d in arrow68_signal_dates(sep_only):
        assert session_shift(d, -15, sep_only) is not None
    for d in arrow68_signal_dates(feats):
        assert session_shift(d, -15, feats) is not None


def test_2026_not_in_signal_set() -> None:
    sigs = arrow68_signal_dates()
    assert sigs[0] == SIGNAL_LO == date(2025, 9, 3)
    assert sigs[-1] == SIGNAL_HI == date(2025, 12, 31)
    assert all(d.year == 2025 for d in sigs)
    assert all(SIGNAL_LO <= d <= SIGNAL_HI for d in sigs)
    assert date(2026, 1, 7) not in sigs
    assert date(2026, 1, 7).weekday() == 2
    for d in nyse_sessions(date(2026, 1, 2), date(2026, 8, 31)):
        assert d not in sigs
    score = arrow68_score_sessions()
    assert score[0] == date(2025, 9, 2)
    assert score[-1] == date(2025, 12, 31)
    assert date(2026, 1, 2) not in score
    feats = arrow68_feature_sessions()
    assert date(2025, 8, 1) in feats
    assert date(2026, 1, 2) in feats
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)


def test_do_not_read_lab_a_bars() -> None:
    assert tape_root(date(2025, 9, 3)) == VIRGIN_BARS
    assert tape_root(date(2025, 9, 3)) != BARS_DIR
    assert tape_root(date(2025, 9, 3)) != FULL_BARS
    assert tape_root(date(2025, 8, 1)) == VIRGIN_BARS
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR
    for d in (date(2025, 9, 3), date(2026, 1, 7), date(2026, 6, 3), date(2026, 8, 26)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
