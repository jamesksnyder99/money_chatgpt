from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from research.ema15 import ema_stack
from research.strategies13 import five_min_close_below_ema9
from research.strategies15 import (
    avwap_reclaim_strong,
    control_c5_ema9,
    grind_up,
    hold_the_open,
    is_hammer,
    is_weak_close,
    one_min_close_below_ema9,
    one_min_ema9_running_or,
    one_min_hammer_long,
    prior_morning_break,
    washout_hammer,
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


def _short_stack(n: int = 30, start: float = 12.0) -> list:
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    return [(t0 + timedelta(minutes=15 * i), start - 0.05 * i) for i in range(n)]


def _long_stack(n: int = 30, start: float = 8.0) -> list:
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    return [(t0 + timedelta(minutes=15 * i), start + 0.05 * i) for i in range(n)]


def test_weak_close_rejects_close_loc_0_8() -> None:
    # range 2.0, close_loc = (10.6-9.0)/2.0 = 0.8
    assert is_weak_close(10.0, 11.0, 9.0, 10.6) is False
    # close_loc = (9.4-9.0)/2.0 = 0.2
    assert is_weak_close(10.0, 11.0, 9.0, 9.4) is True


def test_hammer_rejects_long_upper_wick() -> None:
    # lower wick 1.6 >= 2*body 0.4, close_loc 0.64, but upper 0.7 > body 0.2
    assert is_hammer(10.8, 11.5, 9.0, 10.6) is False
    # small upper wick, long lower, close near high
    assert is_hammer(10.2, 10.5, 9.0, 10.4) is True


def test_id5_silent_before_0945() -> None:
    rows = [
        _row("TEST", 9, 30, 10.20, 10.50, 10.00, 10.20, 1000),
        _row("TEST", 9, 31, 10.20, 10.40, 10.00, 10.10, 1000),
        _row("TEST", 9, 32, 10.10, 10.20, 9.40, 9.50, 1000),  # below ema9, before 09:45
        _row("TEST", 9, 44, 10.10, 10.50, 10.00, 10.20, 1000),
    ]
    for mm in range(45, 50):
        # stay well above ema9 after 09:45 so the only puncture is pre-gate
        rows.append(_row("TEST", 9, mm, 12.00, 12.20, 11.80, 12.10, 1000))
    rows.append(_row("TEST", 11, 59, 12.00, 12.10, 11.90, 12.00, 1000))
    df = _bars(rows)
    stitched = _short_stack()
    assert one_min_close_below_ema9(df, stitched, or_high=10.50) == []


def test_id6_may_signal_at_0932() -> None:
    rows = [
        _row("TEST", 9, 30, 11.80, 12.00, 10.00, 11.70, 1000),  # seeds running OR, width > 2.5%
        _row("TEST", 9, 31, 11.70, 11.80, 11.50, 11.60, 1000),  # still above ema9
        _row("TEST", 9, 32, 11.50, 11.60, 9.40, 9.50, 1000),  # first close below ema9
        _row("TEST", 11, 59, 9.50, 9.60, 9.40, 9.50, 1000),
    ]
    df = _bars(rows)
    stitched = _short_stack()
    sigs = one_min_ema9_running_or(df, stitched)
    assert sigs
    assert all(s.side == -1 for s in sigs)
    assert sigs[0].signal_ts.timetz().replace(tzinfo=None) == time(9, 32)
    assert ema_stack(stitched, sigs[0].signal_ts) == "short"


def test_id1_still_5min_and_ema_short() -> None:
    # 09:45 1-min punches below ema9; rest of the 5-min bar closes back above.
    rows = [
        _row("TEST", 9, 30, 10.00, 10.40, 9.80, 10.10, 1000),
        _row("TEST", 9, 44, 10.10, 10.40, 9.80, 10.00, 1000),
        _row("TEST", 9, 45, 9.70, 9.90, 9.50, 9.60, 1000),  # 1-min below ema9
        _row("TEST", 9, 46, 12.00, 12.20, 11.80, 12.10, 1000),
        _row("TEST", 9, 47, 12.10, 12.20, 11.90, 12.10, 1000),
        _row("TEST", 9, 48, 12.10, 12.20, 11.90, 12.10, 1000),
        _row("TEST", 9, 49, 12.10, 12.20, 11.90, 12.10, 1000),  # 5-min close well above ema9
        _row("TEST", 11, 59, 12.00, 12.10, 11.90, 12.00, 1000),
    ]
    df = _bars(rows)
    stitched = _short_stack()
    assert five_min_close_below_ema9(df, stitched, or_high=10.40) == []
    assert control_c5_ema9(df, stitched, or_high=10.40) == []
    tape = one_min_close_below_ema9(df, stitched, or_high=10.40)
    assert tape and tape[0].side == -1
    assert tape[0].tag == "c1_ema9"

    # A completed 5-min close under ema9 still fires id 1, and stack is short.
    dump = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.80, 10.10, 1000),
            _row("TEST", 9, 44, 10.10, 10.40, 9.80, 10.00, 1000),
            _row("TEST", 9, 45, 9.80, 9.90, 9.40, 9.50, 1000),
            _row("TEST", 9, 46, 9.50, 9.60, 9.30, 9.40, 1000),
            _row("TEST", 9, 47, 9.40, 9.50, 9.20, 9.30, 1000),
            _row("TEST", 9, 48, 9.30, 9.40, 9.10, 9.20, 1000),
            _row("TEST", 9, 49, 9.20, 9.30, 9.00, 9.10, 1000),
            _row("TEST", 11, 59, 9.10, 9.20, 9.00, 9.10, 1000),
        ]
    )
    sigs = control_c5_ema9(dump, stitched, or_high=10.40)
    assert sigs
    assert all(s.side == -1 for s in sigs)
    assert sigs[0].tag == "c5_ema9_short"
    assert ema_stack(stitched, sigs[0].signal_ts) == "short"
    assert sigs[0].signal_ts.timetz().replace(tzinfo=None) == time(9, 50)


def test_longs_emit_no_shorts() -> None:
    # Washout hammer 5-min: low under OR low, close back inside.
    wash = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.80, 10.10, 1000),
            _row("TEST", 9, 44, 10.10, 10.40, 9.80, 10.00, 1000),
            _row("TEST", 9, 45, 9.85, 9.92, 9.60, 9.90, 1000),
            _row("TEST", 11, 59, 9.90, 10.00, 9.80, 9.90, 1000),
        ]
    )
    hold = _bars(
        [
            _row("TEST", 9, 30, 10.20, 10.40, 10.00, 10.30, 1000),
            _row("TEST", 9, 44, 10.30, 10.40, 10.10, 10.35, 1000),  # top half
            _row("TEST", 9, 45, 10.30, 10.50, 10.25, 10.48, 1000),  # strong close above mid
            _row("TEST", 11, 59, 10.40, 10.50, 10.30, 10.40, 1000),
        ]
    )
    grind = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.10, 9.90, 10.00, 1000),
            _row("TEST", 9, 35, 10.00, 10.20, 9.95, 10.10, 1000),
            _row("TEST", 9, 40, 10.10, 10.30, 10.05, 10.20, 1000),
            _row("TEST", 9, 45, 10.20, 10.50, 10.15, 10.45, 1000),  # strong, higher closes
            _row("TEST", 11, 59, 10.40, 10.50, 10.30, 10.40, 1000),
        ]
    )
    reclaim = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.90, 10.10, 5000),
            _row("TEST", 9, 44, 10.10, 10.20, 10.00, 10.15, 5000),
            _row("TEST", 9, 45, 10.00, 10.05, 9.70, 9.75, 5000),  # lose AVWAP
            _row("TEST", 9, 50, 9.80, 10.40, 9.75, 10.35, 5000),  # strong reclaim
            _row("TEST", 11, 59, 10.30, 10.40, 10.20, 10.30, 5000),
        ]
    )
    pd = _bars(
        [
            _row("TEST", 9, 30, 11.00, 11.40, 10.90, 11.30, 1000),
            _row("TEST", 9, 45, 11.20, 11.60, 11.10, 11.55, 1000),  # strong close above 11.0
            _row("TEST", 11, 59, 11.40, 11.50, 11.30, 11.40, 1000),
        ]
    )
    hammer = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row("TEST", 9, 45, 10.20, 10.50, 9.00, 10.40, 1000),  # hammer tags ema ~9.5-10
            _row("TEST", 11, 59, 10.30, 10.40, 10.20, 10.30, 1000),
        ]
    )
    stitched_long = _long_stack()
    groups = [
        washout_hammer(wash),
        hold_the_open(hold),
        grind_up(grind),
        avwap_reclaim_strong(reclaim),
        prior_morning_break(pd, prior_high=11.0),
        one_min_hammer_long(hammer, stitched_long),
    ]
    fired = 0
    for sigs in groups:
        assert all(s.side == 1 for s in sigs)
        fired += len(sigs)
    assert fired >= 1
