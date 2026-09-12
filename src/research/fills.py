from __future__ import annotations

import math
from datetime import time

import polars as pl

RTH_OPEN = time(9, 30)
RTH_END = time(12, 0)


def is_tradeable(open_: float, close: float, volume: int | float | None) -> bool:
    if volume is None or volume <= 0:
        return False
    if close is None or open_ is None:
        return False
    if not math.isfinite(float(close)) or not math.isfinite(float(open_)):
        return False
    return True


def tradeable_mask(df: pl.DataFrame) -> pl.Expr:
    return (
        (pl.col("volume") > 0)
        & pl.col("close").is_finite()
        & pl.col("open").is_finite()
        & pl.col("high").is_finite()
        & pl.col("low").is_finite()
    )


def rth_session_vwap(df: pl.DataFrame) -> list[float]:
    """Cumulative VWAP from RTH tradeable bars only (09:30+). Premarket is ignored."""
    n = df.height
    out = [float("nan")] * n
    if n == 0:
        return out
    times = df["bar_start"].to_list()
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    opens = df["open"].to_list()
    cpv = 0.0
    cv = 0.0
    last = float("nan")
    for i in range(n):
        ts = times[i]
        clock = ts.timetz().replace(tzinfo=None) if getattr(ts, "tzinfo", None) else ts.time()
        if clock < RTH_OPEN:
            out[i] = last
            continue
        if not is_tradeable(opens[i], closes[i], vols[i]):
            out[i] = last
            continue
        typical = (float(highs[i]) + float(lows[i]) + float(closes[i])) / 3.0
        v = float(vols[i])
        cpv += typical * v
        cv += v
        if cv > 0:
            last = cpv / cv
        out[i] = last
    return out


def next_tradeable_row(df: pl.DataFrame, after_idx: int) -> int | None:
    """Index of the next tradeable bar strictly after after_idx, or None."""
    n = df.height
    opens = df["open"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    for j in range(after_idx + 1, n):
        if is_tradeable(opens[j], closes[j], vols[j]):
            return j
    return None
