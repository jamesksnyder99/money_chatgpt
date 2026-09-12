from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.ema15 import completed_15m_closes, resample_15m
from research.strategies10 import (
    hhhl3_long,
    hhhl3_short,
    is_hot_cell,
    or15_break_long,
    orbr5_high_retest,
)

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(sym, hh, mm, o, h, l, c, v, day=1):
    return {
        "symbol": sym,
        "bar_start": datetime(2026, 6, day, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "pre" if hh < 9 else "rth",
    }


def test_ema_uses_only_completed_15m_bars() -> None:
    # 09:30 15m bar (09:30-09:44) closes at 10.0; 09:45-09:50 would print 20 if included.
    rows = []
    for mm in range(30, 45):
        rows.append(_row("TEST", 9, mm, 10.0, 10.1, 9.9, 10.0, 1000))
    rows.append(_row("TEST", 9, 45, 10.0, 20.0, 10.0, 20.0, 1000))
    rows.append(_row("TEST", 9, 46, 20.0, 20.5, 19.5, 20.0, 1000))
    df = _bars(rows)
    series = resample_15m(df)
    ts_0944 = datetime(2026, 6, 1, 9, 44, tzinfo=ET)
    ts_0945 = datetime(2026, 6, 1, 9, 45, tzinfo=ET)
    ts_0950 = datetime(2026, 6, 1, 9, 50, tzinfo=ET)
    # 09:30 bar ends 09:45; not complete at 09:44
    assert completed_15m_closes(series, ts_0944) == []
    assert completed_15m_closes(series, ts_0945)[-1] == 10.0
    # 09:45 15m (would close at 20) is not complete at 09:50
    assert completed_15m_closes(series, ts_0950)[-1] == 10.0
    assert 20.0 not in completed_15m_closes(series, ts_0950)


def test_long_id_emits_no_shorts() -> None:
    # Downside break after a wide OR — long helper must stay silent (not flip short).
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.50, 10.00, 1000),
            _row("TEST", 9, 44, 10.00, 10.40, 9.50, 9.90, 1000),  # OR ~9%
            _row("TEST", 9, 45, 9.80, 9.85, 9.20, 9.30, 1000),  # close below OR low
            _row("TEST", 11, 59, 9.40, 9.50, 9.30, 9.40, 1000),
        ]
    )
    sigs = or15_break_long(df)
    assert sigs == []
    assert all(s.side == 1 for s in sigs)


def test_orbr5_silent_without_retest() -> None:
    rows = []
    for mm in range(30, 35):
        rows.append(_row("TEST", 9, mm, 10.00, 10.10, 10.00, 10.08, 1000))  # high=10.10
    rows.append(_row("TEST", 9, 35, 10.10, 10.20, 10.10, 10.18, 1000))  # break high
    for mm in range(36, 50):
        rows.append(_row("TEST", 9, mm, 10.20, 10.30, 10.15, 10.22, 1000))  # never touch 10.10
    rows.append(_row("TEST", 11, 59, 10.20, 10.25, 10.15, 10.20, 1000))
    df = _bars(rows)
    assert orbr5_high_retest(df) == []


def test_hot_cell_rejects_3pct_or() -> None:
    assert is_hot_cell(0.95, 0.03, 0.03) is False
    assert is_hot_cell(0.95, 0.03, 0.041) is True
    assert is_hot_cell(0.50, 0.03, 0.05) is False


def test_rising_lows_do_not_arm_shorts() -> None:
    assert hhhl3_long((9.0, 9.5, 10.0)) is True
    assert hhhl3_short((12.0, 12.2, 12.5)) is False  # rising highs, not falling
    assert hhhl3_short((12.0, 11.5, 11.0)) is True
    # rising lows must not be treated as short structure
    assert hhhl3_short((10.0, 10.5, 11.0)) is False
