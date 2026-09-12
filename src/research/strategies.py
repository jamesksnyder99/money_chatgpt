from __future__ import annotations

from datetime import time

import polars as pl

from research.fills import tradeable_mask
from research.signals import (
    MINUTE_0934,
    MINUTE_0944,
    MINUTE_0945,
    MINUTE_1000,
    MINUTE_1130,
    MINUTE_1150,
    Signal,
    bar_time,
)

RTH_OPEN = time(9, 30)


def _tradeable(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(tradeable_mask(df))


def _t(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("bar_start").dt.time().alias("t"))


def gap_fade_signals(bars: pl.DataFrame, prior_close: float, x_pct: float) -> list[Signal]:
    """Gap ≥ X% at 09:30; first 5 RTH minutes fail to extend; fade toward prior close."""
    if prior_close is None or prior_close <= 0:
        return []
    df = _t(_tradeable(bars))
    b930 = df.filter(pl.col("t") == RTH_OPEN)
    if b930.height != 1:
        return []
    open_930 = float(b930["open"][0])
    gap = (open_930 - prior_close) / prior_close
    first5 = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0934))
    last = first5.filter(pl.col("t") == MINUTE_0934)
    earlier = first5.filter(pl.col("t") < MINUTE_0934)
    if last.height != 1 or earlier.height < 1:
        return []
    hi = float(first5["high"].max())
    lo = float(first5["low"].min())
    hi_early = float(earlier["high"].max())
    lo_early = float(earlier["low"].min())
    last_high = float(last["high"][0])
    last_low = float(last["low"][0])
    ts = last["bar_start"][0]
    sym = str(last["symbol"][0])
    if gap >= x_pct / 100.0:
        if last_high >= hi_early:  # made a new high (or tied) — no stall
            return []
        stop = hi
        target = prior_close
        if stop <= open_930 or target >= open_930:
            return []
        return [Signal(ts, sym, -1, stop, target, abs(gap), f"gap_fade_{x_pct:g}")]
    if gap <= -x_pct / 100.0:
        if last_low <= lo_early:
            return []
        stop = lo
        target = prior_close
        if stop >= open_930 or target <= open_930:
            return []
        return [Signal(ts, sym, 1, stop, target, abs(gap), f"gap_fade_{x_pct:g}")]
    return []


def open_drive_signals(
    bars: pl.DataFrame,
    first5_vol: float,
    median_prior: float,
    y: float,
) -> list[Signal]:
    if median_prior is None or median_prior <= 0:
        return []
    if first5_vol < y * median_prior:
        return []
    df = _t(_tradeable(bars))
    first5 = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0934))
    last = first5.filter(pl.col("t") == MINUTE_0934)
    if last.height != 1 or first5.height < 2:
        return []
    hi = float(first5["high"].max())
    lo = float(first5["low"].min())
    rng = hi - lo
    if rng < 0.01:
        return []
    close = float(last["close"][0])
    ts = last["bar_start"][0]
    sym = str(last["symbol"][0])
    third = rng / 3.0
    if close >= hi - third:
        return [Signal(ts, sym, 1, lo, None, first5_vol / median_prior, f"open_drive_{y:g}")]
    if close <= lo + third:
        return [Signal(ts, sym, -1, hi, None, first5_vol / median_prior, f"open_drive_{y:g}")]
    return []


def _atr20(df: pl.DataFrame) -> list[float]:
    """Wilder-style simple rolling mean of TR over 20 tradeable bars; aligned to df rows."""
    n = df.height
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    closes = df["close"].to_list()
    atr = [float("nan")] * n
    trs: list[float] = []
    prev_c = None
    for i in range(n):
        h, l, c = float(highs[i]), float(lows[i]), float(closes[i])
        if prev_c is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
        prev_c = c
        if len(trs) >= 20:
            atr[i] = sum(trs[-20:]) / 20.0
    return atr


def vwap_reclaim_signals(bars: pl.DataFrame, min_price: float, prior_close: float) -> list[Signal]:
    if prior_close is None or prior_close < min_price:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    if df.height < 25:
        return []
    typical = (pl.col("high") + pl.col("low") + pl.col("close")) / 3.0
    df = df.with_columns(
        (typical * pl.col("volume")).alias("pv"),
        pl.col("volume").alias("v"),
    ).with_columns(
        pl.col("pv").cum_sum().alias("cpv"),
        pl.col("v").cum_sum().alias("cv"),
    ).with_columns((pl.col("cpv") / pl.col("cv")).alias("svwap"))
    atr = _atr20(df)
    times = df["bar_start"].to_list()
    closes = df["close"].to_list()
    vw = df["svwap"].to_list()
    sym = str(df["symbol"][0])
    below = 0
    above = 0
    out: list[Signal] = []
    fired = False
    for i in range(df.height):
        t = bar_time(times[i])
        if t < MINUTE_1000:
            if closes[i] < vw[i]:
                below += 1
                above = 0
            elif closes[i] > vw[i]:
                above += 1
                below = 0
            else:
                below = 0
                above = 0
            continue
        if fired:
            break
        a = atr[i]
        if a != a or a <= 0:  # NaN
            if closes[i] < vw[i]:
                below += 1
                above = 0
            elif closes[i] > vw[i]:
                above += 1
                below = 0
            continue
        if below >= 3 and closes[i] > vw[i]:
            stop = float(vw[i]) - 1.5 * a
            if stop <= 0 or abs(float(closes[i]) - stop) < 0.01:
                break
            out.append(
                Signal(times[i], sym, 1, stop, None, abs(closes[i] - vw[i]), f"vwap_reclaim_{min_price:g}")
            )
            fired = True
            break
        if above >= 3 and closes[i] < vw[i]:
            stop = float(vw[i]) + 1.5 * a
            if abs(stop - float(closes[i])) < 0.01:
                break
            out.append(
                Signal(times[i], sym, -1, stop, None, abs(closes[i] - vw[i]), f"vwap_reclaim_{min_price:g}")
            )
            fired = True
            break
        if closes[i] < vw[i]:
            below += 1
            above = 0
        elif closes[i] > vw[i]:
            above += 1
            below = 0
        else:
            below = 0
            above = 0
    return out


def or_break_signals(bars: pl.DataFrame) -> list[Signal]:
    """First close beyond 09:30–09:44 range, only after 09:45."""
    df = _t(_tradeable(bars)).sort("bar_start")
    opening = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0944))
    if opening.height < 2:
        return []
    hi = float(opening["high"].max())
    lo = float(opening["low"].min())
    if hi - lo < 0.01:
        return []
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        t = rec["t"]
        if t < MINUTE_0945:
            continue
        close = float(rec["close"])
        ts = rec["bar_start"]
        sym = str(rec["symbol"])
        if close > hi:
            return [Signal(ts, sym, 1, lo, None, close - hi, "or_break")]
        if close < lo:
            return [Signal(ts, sym, -1, hi, None, lo - close, "or_break")]
    return []


def swing_signals(bars: pl.DataFrame, session_vol_so_far: float, median_full_vol: float | None) -> list[Signal]:
    """Signal 11:30–11:50 only. Fill is next session RTH open (overnight)."""
    if median_full_vol is None or median_full_vol <= 0:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    b930 = df.filter(pl.col("t") == RTH_OPEN)
    if b930.height != 1:
        return []
    open_930 = float(b930["open"][0])
    if open_930 <= 0:
        return []
    window = df.filter((pl.col("t") >= MINUTE_1130) & (pl.col("t") <= MINUTE_1150))
    if window.height == 0:
        return []
    last = window.tail(1)
    close = float(last["close"][0])
    ts = last["bar_start"][0]
    t = last["t"][0]
    if t < MINUTE_1130 or t > MINUTE_1150:
        return []
    if session_vol_so_far < median_full_vol:
        return []
    ret = (close - open_930) / open_930
    sym = str(last["symbol"][0])
    if ret >= 0.015:
        return [
            Signal(
                ts, sym, 1, 0.0, None, abs(ret), "swing",
                stop_from_entry=True, overnight=True,
            )
        ]
    if ret <= -0.015:
        return [
            Signal(
                ts, sym, -1, 0.0, None, abs(ret), "swing",
                stop_from_entry=True, overnight=True,
            )
        ]
    return []


def session_volume(bars: pl.DataFrame, through: time | None = None) -> float:
    df = _t(bars)
    if through is not None:
        df = df.filter(pl.col("t") <= through)
    if df.height == 0:
        return 0.0
    return float(df["volume"].fill_null(0).sum())


def first5_volume(bars: pl.DataFrame) -> float:
    df = _t(bars).filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0934))
    if df.height == 0:
        return 0.0
    vol = df["volume"].fill_null(0).sum()
    return float(vol)
