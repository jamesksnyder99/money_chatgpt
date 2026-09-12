from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.strategies10 import or15_break_short
from research.strategies11 import short_kernel_pop, two_close_below_or_low, vwap_short_after_or

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


def test_helpers_emit_only_shorts() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.50, 10.00, 1000),
            _row("TEST", 9, 44, 10.00, 10.40, 9.50, 9.90, 1000),
            _row("TEST", 9, 45, 9.40, 9.50, 9.20, 9.30, 1000),
            _row("TEST", 9, 46, 9.30, 9.35, 9.10, 9.20, 1000),
            _row("TEST", 11, 59, 9.20, 9.30, 9.10, 9.20, 1000),
        ]
    )
    for sigs in (or15_break_short(df), two_close_below_or_low(df), vwap_short_after_or(df)):
        assert all(s.side == -1 for s in sigs)


def test_gap1_pop_accepts_1p2_rejects_0p5() -> None:
    kwargs = {"dv_min": 0.80, "gap_min": 0.01, "or_w_min": 0.04}
    assert short_kernel_pop(0.95, -0.012, 0.05, **kwargs) is True
    assert short_kernel_pop(0.95, -0.005, 0.05, **kwargs) is False
    assert short_kernel_pop(0.95, 0.012, 0.05, **kwargs) is False  # up gap is not this kernel


def test_two_close_silent_after_one_close_below() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.80, 10.00, 1000),
            _row("TEST", 9, 44, 10.00, 10.20, 9.80, 10.00, 1000),  # OR low=9.80
            _row("TEST", 9, 45, 9.70, 9.75, 9.60, 9.70, 1000),  # one close below
            _row("TEST", 9, 46, 9.90, 10.00, 9.85, 9.95, 1000),  # back above
            _row("TEST", 11, 59, 10.00, 10.10, 9.90, 10.00, 1000),
        ]
    )
    assert two_close_below_or_low(df) == []


def test_vwap_short_silent_above_vwap() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.80, 10.10, 5000),
            _row("TEST", 9, 44, 10.10, 10.20, 9.90, 10.15, 5000),
            _row("TEST", 9, 45, 10.20, 10.40, 10.15, 10.35, 5000),  # close above RTH VWAP ~10.1
            _row("TEST", 11, 59, 10.30, 10.40, 10.20, 10.30, 5000),
        ]
    )
    assert vwap_short_after_or(df) == []
