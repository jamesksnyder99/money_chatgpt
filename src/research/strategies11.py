from __future__ import annotations

import math

import polars as pl

from research.fills import is_tradeable, rth_session_vwap
from research.signals import MINUTE_0945, Signal, bar_time
from research.strategies8 import _t, _tradeable, opening_range


def short_kernel_pop(
    dv_rank: float,
    gap: float | None,
    or_w: float | None,
    *,
    dv_min: float = 0.80,
    gap_min: float = 0.02,
    or_w_min: float | None = 0.04,
) -> bool:
    """Gap-down short population. or_w_min=None means no OR-width floor."""
    if dv_rank < dv_min - 1e-12:
        return False
    if gap is None or gap >= 0:
        return False
    if abs(gap) < gap_min - 1e-12:
        return False
    if or_w_min is not None:
        if or_w is None or or_w <= or_w_min + 1e-12:
            return False
    return True


def two_close_below_or_low(bars: pl.DataFrame) -> list[Signal]:
    """First two consecutive RTH closes after 09:45 below the 09:30–09:44 low. Shorts only."""
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, lo, _w = rng
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    prev_below = False
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        below = close < lo
        if below and prev_below:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    -1,
                    hi,
                    None,
                    lo - close,
                    "two_close_short",
                )
            ]
        prev_below = below
    return []


def vwap_short_after_or(bars: pl.DataFrame) -> list[Signal]:
    """First RTH close after 09:45 below RTH VWAP. Shorts only. Stop = max(OR high, VWAP)."""
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, _lo, _w = rng
    df = bars.sort("bar_start")
    if df.height == 0:
        return []
    vw = rth_session_vwap(df)
    times = df["bar_start"].to_list()
    opens = df["open"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    for i in range(df.height):
        t = bar_time(times[i])
        if t < MINUTE_0945:
            continue
        if not is_tradeable(opens[i], closes[i], vols[i]):
            continue
        c = float(closes[i])
        v = vw[i]
        if not math.isfinite(v):
            continue
        if c < v:
            stop = max(hi, v)
            return [
                Signal(
                    times[i],
                    str(df["symbol"][i]),
                    -1,
                    stop,
                    None,
                    v - c,
                    "vwap_short",
                )
            ]
    return []
