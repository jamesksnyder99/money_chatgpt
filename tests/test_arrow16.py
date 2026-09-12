from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from research.ema15 import ema_stack
from research.strategies15 import control_c5_ema9
from research.strategies16 import (
    c5_ema9_after_1000,
    c5_ema9_below_avwap,
    c5_ema9_expanding,
    c5_ema9_mem_avwap,
    c5_ema9_no_pre_rocket,
    c5_ema9_prior_morning_stop,
    c5_ema9_relvol,
    c5_ema9_three_down,
    premarket_hit_10,
)

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(hh, mm, o, h, l, c, v):
    return {
        "symbol": "TEST",
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "pre" if hh < 9 or (hh == 9 and mm < 30) else "rth",
    }


def _short_stack(n: int = 30, start: float = 12.0) -> list:
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    return [(t0 + timedelta(minutes=15 * i), start - 0.05 * i) for i in range(n)]


def _or_dump():
    """Wide OR then a 09:45 5-min close well below ema9 (~10.7)."""
    rows = [
        _row(9, 30, 10.00, 10.40, 9.80, 10.10, 1000),
        _row(9, 44, 10.10, 10.40, 9.80, 10.00, 1000),
    ]
    for mm in range(45, 50):
        rows.append(_row(9, mm, 9.80, 9.90, 9.00, 9.10, 1000))
    rows.append(_row(11, 59, 9.10, 9.20, 9.00, 9.10, 1000))
    return _bars(rows)


def test_id7_silent_on_0950_only_cross() -> None:
    rows = [
        _row(9, 30, 10.00, 10.40, 9.80, 10.10, 1000),
        _row(9, 44, 10.10, 10.40, 9.80, 10.00, 1000),
    ]
    for mm in range(45, 50):
        rows.append(_row(9, mm, 9.80, 9.90, 9.00, 9.10, 1000))  # 09:45 5-min dumps
    for mm in range(0, 5):
        rows.append(_row(10, mm, 12.00, 12.20, 11.80, 12.10, 1000))  # 10:00 stays above ema9
    rows.append(_row(11, 59, 12.00, 12.10, 11.90, 12.00, 1000))
    df = _bars(rows)
    stitched = _short_stack()
    ctrl = control_c5_ema9(df, stitched, or_high=10.40)
    assert ctrl and ctrl[0].side == -1
    assert c5_ema9_after_1000(df, stitched, or_high=10.40) == []


def test_id8_rejects_plus10_at_0810() -> None:
    rows = [
        _row(8, 10, 10.50, 11.20, 10.40, 11.00, 1000),  # +12% vs prior 10
        _row(9, 30, 10.00, 10.40, 9.80, 10.10, 1000),
        _row(9, 44, 10.10, 10.40, 9.80, 10.00, 1000),
    ]
    for mm in range(45, 50):
        rows.append(_row(9, mm, 9.80, 9.90, 9.00, 9.10, 1000))
    rows.append(_row(11, 59, 9.10, 9.20, 9.00, 9.10, 1000))
    df = _bars(rows)
    stitched = _short_stack()
    assert premarket_hit_10(df, 10.0) is True
    assert control_c5_ema9(df, stitched, or_high=10.40)
    assert c5_ema9_no_pre_rocket(df, stitched, or_high=10.40, prior_close=10.0) == []


def test_id5_silent_with_two_prior_windows() -> None:
    df = _or_dump()
    stitched = _short_stack()
    assert control_c5_ema9(df, stitched, or_high=10.40)
    assert c5_ema9_relvol(df, stitched, or_high=10.40, prior_vols=[1000.0, 1000.0]) == []


def test_id1_still_the_kernel() -> None:
    df = _or_dump()
    stitched = _short_stack()
    sigs = control_c5_ema9(df, stitched, or_high=10.40)
    assert sigs
    assert all(s.side == -1 for s in sigs)
    assert sigs[0].tag == "c5_ema9_short"
    assert ema_stack(stitched, sigs[0].signal_ts) == "short"
    assert sigs[0].signal_ts.timetz().replace(tzinfo=None) == time(9, 50)


def test_helpers_shorts_only() -> None:
    df = _or_dump()
    stitched = _short_stack()
    groups = [
        control_c5_ema9(df, stitched, 10.40),
        c5_ema9_three_down(df, stitched, 10.40),
        c5_ema9_below_avwap(df, stitched, 10.40),
        c5_ema9_relvol(df, stitched, 10.40, [1000.0] * 10),
        c5_ema9_prior_morning_stop(df, stitched, 10.40, prior_high=12.0),
        c5_ema9_after_1000(df, stitched, 10.40),
        c5_ema9_no_pre_rocket(df, stitched, 10.40, prior_close=10.0),
        c5_ema9_expanding(df, stitched, 10.40),
        c5_ema9_mem_avwap(df, stitched, 10.40),
    ]
    for sigs in groups:
        assert all(s.side == -1 for s in sigs)
    assert any(groups[0])
