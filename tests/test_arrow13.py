from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from research.strategies10 import or15_break_long, or15_break_short
from research.strategies13 import (
    five_min_close_below_ema9,
    pullback_or_mid_ema9,
    quiet_open_pop,
    vwap_reclaim_long,
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


def _flat_15m(n: int = 30, px: float = 10.0) -> list:
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    return [(t0 + timedelta(minutes=15 * i), px) for i in range(n)]


def test_short_helpers_emit_no_longs() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.50, 10.00, 1000),
            _row("TEST", 9, 44, 10.00, 10.40, 9.50, 9.90, 1000),
            _row("TEST", 9, 45, 9.40, 9.50, 9.20, 9.30, 1000),
            _row("TEST", 11, 59, 9.20, 9.30, 9.10, 9.20, 1000),
        ]
    )
    sigs = or15_break_short(df)
    assert sigs
    assert all(s.side == -1 for s in sigs)


def test_long_helpers_emit_no_shorts() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.60, 10.20, 1000),
            _row("TEST", 9, 44, 10.20, 10.40, 10.00, 10.30, 1000),
            _row("TEST", 9, 45, 10.40, 10.50, 10.30, 10.45, 1000),
            _row("TEST", 11, 59, 10.40, 10.50, 10.30, 10.40, 1000),
        ]
    )
    sigs = or15_break_long(df)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_c5_ema9_silent_if_closes_stay_above() -> None:
    rows = [_row("TEST", 9, 30, 10.00, 10.20, 9.80, 10.00, 1000)]
    rows.append(_row("TEST", 9, 44, 10.00, 10.20, 9.80, 10.00, 1000))
    for mm in range(45, 50):
        rows.append(_row("TEST", 9, mm, 10.20, 10.30, 10.15, 10.25, 1000))
    df = _bars(rows)
    stitched = _flat_15m(px=10.0)
    assert five_min_close_below_ema9(df, stitched, or_high=10.20) == []


def test_pullback_silent_if_never_tags_mid_or_ema9() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.60, 10.10, 1000),
            _row("TEST", 9, 44, 10.10, 10.40, 9.60, 10.20, 1000),  # mid=10.00
            _row("TEST", 9, 45, 10.50, 10.60, 10.40, 10.50, 1000),  # low stays above mid/ema
            _row("TEST", 9, 46, 10.50, 10.55, 10.35, 10.45, 1000),
            _row("TEST", 11, 59, 10.40, 10.50, 10.30, 10.40, 1000),
        ]
    )
    stitched = _flat_15m(px=10.0)
    assert pullback_or_mid_ema9(df, stitched) == []


def test_vwap_reclaim_silent_if_never_loses_vwap() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.90, 10.10, 5000),
            _row("TEST", 9, 44, 10.10, 10.20, 10.00, 10.15, 5000),
            _row("TEST", 9, 45, 10.20, 10.40, 10.15, 10.35, 5000),
            _row("TEST", 11, 59, 10.30, 10.40, 10.20, 10.30, 5000),
        ]
    )
    assert vwap_reclaim_long(df) == []


def test_quiet_open_silent_on_2pct_gap() -> None:
    assert quiet_open_pop(0.95, 0.02, 0.02) is False
    assert quiet_open_pop(0.95, -0.02, 0.02) is False
    assert quiet_open_pop(0.95, 0.002, 0.02) is True
