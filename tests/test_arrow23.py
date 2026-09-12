from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.strategies23 import (
    afternoon_break_long,
    climax_short,
    coil_break_long,
    coil_range_ok,
    failed_rocket_short,
    session_high_before,
)
from research.signals import MINUTE_1100

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(hh, mm, o, h, l, c, v, sym="TEST"):
    return {
        "symbol": sym,
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session_part": "pre" if hh < 9 or (hh == 9 and mm < 30) else "rth",
    }


def test_id1_silent_if_premarket_range_8pct() -> None:
    # mid=10.4, range=0.832 → 8%
    pre_low, pre_high = 10.0, 10.832
    assert coil_range_ok(pre_high, pre_low) is False
    df = _bars(
        [
            _row(9, 0, 10.20, 10.832, 10.00, 10.40, 1000),
            _row(9, 30, 10.90, 11.10, 10.80, 11.00, 1000),
        ]
    )
    assert coil_break_long(df, pre_high, pre_low) == []
    # tight coil does fire on a close above pre_high
    tight_hi, tight_lo = 10.20, 10.00  # range/mid = 0.02/10.1 < 4%
    assert coil_range_ok(tight_hi, tight_lo) is True
    df2 = _bars(
        [
            _row(9, 0, 10.05, 10.20, 10.00, 10.10, 1000),
            _row(9, 30, 10.25, 10.40, 10.20, 10.35, 1000),
        ]
    )
    sigs = coil_break_long(df2, tight_hi, tight_lo)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id2_silent_before_1200() -> None:
    df = _bars(
        [
            _row(10, 0, 10.00, 11.00, 9.90, 10.50, 1000),
            _row(11, 0, 11.10, 11.60, 11.00, 11.50, 1000),
            _row(11, 59, 11.50, 11.70, 11.40, 11.60, 1000),
        ]
    )
    am_high = session_high_before(df, MINUTE_1100)
    assert am_high == 11.00
    assert afternoon_break_long(df, am_high) == []
    df_pm = _bars(
        [
            _row(10, 0, 10.00, 11.00, 9.90, 10.50, 1000),
            _row(12, 0, 11.20, 11.40, 11.10, 11.30, 1000),
        ]
    )
    sigs = afternoon_break_long(df_pm, 11.00)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id3_emits_only_shorts() -> None:
    rows = [_row(9, 30, 10.50, 10.60, 10.40, 10.50, 1000)]
    for mm in range(31, 45):
        rows.append(_row(9, mm, 10.50, 10.55, 10.45, 10.50, 1000))
    rows.append(_row(9, 45, 10.40, 10.50, 10.00, 10.10, 1000))
    df = _bars(rows)
    sigs = failed_rocket_short(df)
    assert sigs
    assert all(s.side == -1 for s in sigs)
    assert all(s.tag == "fail_rocket" for s in sigs)


def test_id6_silent_if_5min_close_loc_is_08() -> None:
    rows = []
    for start_mm, o, h, l, c in (
        (30, 10.00, 10.10, 10.00, 10.05),
        (35, 10.05, 10.15, 10.05, 10.10),
        (40, 10.10, 10.20, 10.10, 10.15),
    ):
        rows.append(_row(9, start_mm, o, h, l, c, 1000))
    # 09:45 5-min: range 0.40 (>= 2x 0.10), close_loc = 0.8
    rows.append(_row(9, 45, 10.00, 10.40, 10.00, 10.32, 1000))
    df = _bars(rows)
    assert climax_short(df) == []
