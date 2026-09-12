from __future__ import annotations

import polars as pl

from research.signals import (
    MINUTE_0934,
    MINUTE_0935,
    MINUTE_0945,
    MINUTE_1100,
    Signal,
)
from research.strategies8 import RTH_OPEN, _bar_at, _t, _tradeable, opening_range


def is_hot_cell(dv_rank: float, gap: float | None, or_w: float | None) -> bool:
    """Q5 DV, |gap| ≥ 2%, 15-min OR width > 4%."""
    if dv_rank < 0.80 - 1e-12:
        return False
    if gap is None or abs(gap) < 0.02 - 1e-12:
        return False
    if or_w is None or or_w <= 0.04 + 1e-12:
        return False
    return True


def session_gap(bars: pl.DataFrame, prior_close: float | None) -> float | None:
    if prior_close is None or prior_close <= 0:
        return None
    df = _t(_tradeable(bars))
    b = _bar_at(df, RTH_OPEN)
    if b is None:
        return None
    o = float(b["open"])
    if o <= 0:
        return None
    return o / float(prior_close) - 1.0


def hhhl3_long(lows: tuple[float | None, float | None, float | None]) -> bool:
    l1, l2, l3 = lows
    return l1 is not None and l2 is not None and l3 is not None and l1 < l2 < l3


def hhhl3_short(highs: tuple[float | None, float | None, float | None]) -> bool:
    h1, h2, h3 = highs
    return h1 is not None and h2 is not None and h3 is not None and h1 > h2 > h3


def or15_break_long(bars: pl.DataFrame) -> list[Signal]:
    """First close above 09:30–09:44 high after 09:45. Longs only."""
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, lo, _w = rng
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        if close > hi:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    1,
                    lo,
                    None,
                    close - hi,
                    "or15_long",
                )
            ]
    return []


def or15_break_short(bars: pl.DataFrame) -> list[Signal]:
    """First close below 09:30–09:44 low after 09:45. Shorts only."""
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, lo, _w = rng
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        if close < lo:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    -1,
                    hi,
                    None,
                    lo - close,
                    "or15_short",
                )
            ]
    return []


def _five_min_range(bars: pl.DataFrame) -> tuple[float, float] | None:
    df = _t(_tradeable(bars))
    opening = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0934))
    if opening.height < 1:
        return None
    hi = float(opening["high"].max())
    lo = float(opening["low"].min())
    mid = (hi + lo) / 2.0
    if mid <= 0:
        return None
    if (hi - lo) / mid < 0.004 - 1e-12:
        return None
    return hi, lo


def orbr5_high_retest(bars: pl.DataFrame) -> list[Signal]:
    """5-min ORBR + retest of the high. Longs only. No retest by 11:00 → silent."""
    rng = _five_min_range(bars)
    if rng is None:
        return []
    hi, lo = rng
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter((pl.col("t") >= MINUTE_0935) & (pl.col("t") < MINUTE_1100))
    broken = False
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        low = float(rec["low"])
        if not broken:
            if close > hi:
                broken = True
            continue
        # retest: touch the broken high from the outside, close still outside
        if low <= hi and close >= hi:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    1,
                    lo,
                    None,
                    hi - lo,
                    "orbr5_long",
                )
            ]
    return []


def orbr5_low_retest(bars: pl.DataFrame) -> list[Signal]:
    """5-min ORBR + retest of the low. Shorts only. No retest by 11:00 → silent."""
    rng = _five_min_range(bars)
    if rng is None:
        return []
    hi, lo = rng
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter((pl.col("t") >= MINUTE_0935) & (pl.col("t") < MINUTE_1100))
    broken = False
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        high = float(rec["high"])
        if not broken:
            if close < lo:
                broken = True
            continue
        if high >= lo and close <= lo:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    -1,
                    hi,
                    None,
                    hi - lo,
                    "orbr5_short",
                )
            ]
    return []
