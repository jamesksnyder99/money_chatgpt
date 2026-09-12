from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import virgin_warmup_sessions
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow43 import last_rth
from research.arrow44 import residual
from research.clock import (
    combined_study_sessions,
    entry_split,
    is_is_session,
    rebalance_sessions,
    tape_root,
)
from research.signals import MINUTE_1559, RTH_OPEN

ET = ZoneInfo("America/New_York")


def test_warmup_dates_produce_no_fills() -> None:
    study = set(combined_study_sessions())
    reb = set(rebalance_sessions())
    for d in virgin_warmup_sessions():
        assert d not in study
        assert d not in reb
        assert d.year == 2025


def test_even_month_entry_friday_is_not_is() -> None:
    fri = date(2026, 2, 6)
    assert fri.weekday() == 4
    assert fri in rebalance_sessions()
    assert entry_split(fri) == "OOS"
    assert not is_is_session(fri)


def test_residual_subtracts_iwm_not_raw_name() -> None:
    r = residual(100.0, 110.0, 200.0, 220.0)
    assert r is not None
    assert abs(r) < 1e-12
    raw_name = 110.0 / 100.0 - 1.0
    assert abs(raw_name - 0.10) < 1e-12
    ranked = sorted([-0.05] * 15 + [0.0] + [0.05] * 15)
    bottom = ranked[:15]
    top = ranked[-15:]
    assert all(x < 0 for x in bottom)
    assert all(x > 0 for x in top)
    assert 0.0 not in bottom and 0.0 not in top


def test_entry_is_last_rth_not_0930() -> None:
    d = date(2026, 1, 2)
    df = pl.DataFrame(
        {
            "bar_start": [
                datetime(2026, 1, 2, 9, 30, tzinfo=ET),
                datetime(2026, 1, 2, 15, 59, tzinfo=ET),
            ],
            "open": [10.0, 10.4],
            "high": [10.2, 10.5],
            "low": [9.9, 10.3],
            "close": [10.1, 10.45],
            "volume": [5000, 5000],
        }
    ).with_columns(pl.col("bar_start").dt.replace_time_zone("America/New_York"))
    rec = last_rth(df, d)
    assert rec is not None
    assert rec["bar_start"].timetz().replace(tzinfo=None) == MINUTE_1559
    assert rec["bar_start"].timetz().replace(tzinfo=None) != RTH_OPEN
    assert rec["close"] == 10.45


def test_july_weeks_from_full_january_from_virgin() -> None:
    jan = date(2026, 1, 2)
    jul = date(2026, 7, 2)
    assert jan in rebalance_sessions()
    assert tape_root(jan) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 10)) == FULL_BARS
    assert tape_root(jul) == FULL_BARS
    assert tape_root(jan) != BARS_DIR
    assert tape_root(jul) != BARS_DIR


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 2), date(2026, 6, 5), date(2026, 8, 31)):
        assert tape_root(d) != BARS_DIR
        assert "bars" not in tape_root(d).parts or tape_root(d) in {VIRGIN_BARS, FULL_BARS}
