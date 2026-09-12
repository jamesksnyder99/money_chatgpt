from __future__ import annotations

from datetime import time

import polars as pl

from research.fills import tradeable_mask
from research.signals import (
    MINUTE_0944,
    MINUTE_0945,
    MINUTE_1000,
    MINUTE_1015,
    MINUTE_1100,
    Signal,
    bar_time,
)
from research.trend import Trend

RTH_OPEN = time(9, 30)


def _tradeable(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(tradeable_mask(df))


def _t(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("bar_start").dt.time().alias("t"))


def _side(trend: Trend) -> int | None:
    if trend.side == "up":
        return 1
    if trend.side == "down":
        return -1
    return None


def _bar_at(df: pl.DataFrame, t: time) -> dict | None:
    hit = df.filter(pl.col("t") == t)
    if hit.height != 1:
        return None
    return hit.row(0, named=True)


def trend_open_signals(bars: pl.DataFrame, trend: Trend) -> list[Signal]:
    """Fill at first tradeable 09:30 open (rth_open_entries). Flat → no signal."""
    sd = _side(trend)
    if sd is None:
        return []
    df = _t(_tradeable(bars))
    b = _bar_at(df, RTH_OPEN)
    if b is None:
        return []
    return [
        Signal(
            b["bar_start"],
            str(b["symbol"]),
            sd,
            0.0,
            None,
            trend.score,
            "trend_open",
            stop_from_entry=True,
        )
    ]


def trend_pullback_signals(bars: pl.DataFrame, trend: Trend) -> list[Signal]:
    sd = _side(trend)
    if sd is None:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    rth = df.filter(pl.col("t") >= RTH_OPEN)
    if rth.height == 0:
        return []
    highs = rth["high"].to_list()
    lows = rth["low"].to_list()
    closes = rth["close"].to_list()
    times = rth["bar_start"].to_list()
    ts_clock = rth["t"].to_list()
    sym = str(rth["symbol"][0])
    ext_hi = float("-inf")
    ext_lo = float("inf")
    for i in range(rth.height):
        ext_hi = max(ext_hi, float(highs[i]))
        ext_lo = min(ext_lo, float(lows[i]))
        if ts_clock[i] < MINUTE_1000:
            continue
        close = float(closes[i])
        if sd > 0 and ext_hi > 0 and (ext_hi - close) / ext_hi >= 0.01:
            stop = float(lows[i])
            if stop <= 0 or close - stop < 0.01:
                continue
            return [Signal(times[i], sym, 1, stop, None, (ext_hi - close) / ext_hi, "trend_pullback")]
        if sd < 0 and ext_lo > 0 and (close - ext_lo) / ext_lo >= 0.01:
            stop = float(highs[i])
            if stop - close < 0.01:
                continue
            return [Signal(times[i], sym, -1, stop, None, (close - ext_lo) / ext_lo, "trend_pullback")]
    return []


def yday_level_break_signals(
    bars: pl.DataFrame, trend: Trend, prior_high: float | None, prior_low: float | None
) -> list[Signal]:
    sd = _side(trend)
    if sd is None or prior_high is None or prior_low is None:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    rth = df.filter(pl.col("t") >= RTH_OPEN)
    for rec in rth.iter_rows(named=True):
        close = float(rec["close"])
        ts = rec["bar_start"]
        sym = str(rec["symbol"])
        if sd > 0 and close > prior_high:
            return [Signal(ts, sym, 1, prior_high, None, close - prior_high, "yday_level_break")]
        if sd < 0 and close < prior_low:
            return [Signal(ts, sym, -1, prior_low, None, prior_low - close, "yday_level_break")]
    return []


def gap_with_trend_signals(bars: pl.DataFrame, trend: Trend, prior_close: float) -> list[Signal]:
    sd = _side(trend)
    if sd is None or prior_close is None or prior_close <= 0:
        return []
    df = _t(_tradeable(bars))
    b = _bar_at(df, RTH_OPEN)
    if b is None:
        return []
    open_930 = float(b["open"])
    gap = (open_930 - prior_close) / prior_close
    if sd > 0 and gap < 0.015:
        return []
    if sd < 0 and gap > -0.015:
        return []
    return [
        Signal(b["bar_start"], str(b["symbol"]), sd, open_930, None, abs(gap), "gap_with_trend")
    ]


def compression_expansion_signals(
    bars: pl.DataFrame,
    trend: Trend,
    median_range: float | None,
    prior_range: float | None,
) -> list[Signal]:
    sd = _side(trend)
    if sd is None or median_range is None or prior_range is None or median_range <= 0:
        return []
    if prior_range > 0.7 * median_range:
        return []
    df = _t(_tradeable(bars))
    first15 = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0944))
    last = first15.filter(pl.col("t") == MINUTE_0944)
    if last.height != 1 or first15.height < 2:
        return []
    hi = float(first15["high"].max())
    lo = float(first15["low"].min())
    rng = hi - lo
    if rng < 1.2 * median_range:
        return []
    stop = lo if sd > 0 else hi
    rec = last.row(0, named=True)
    return [
        Signal(rec["bar_start"], str(rec["symbol"]), sd, stop, None, rng / median_range, "compression_expansion")
    ]


def rs_vs_book_signals(
    bars: pl.DataFrame,
    trend: Trend,
    name_ret: float | None,
    p70: float | None,
    p30: float | None,
) -> list[Signal]:
    sd = _side(trend)
    if sd is None or name_ret is None:
        return []
    if sd > 0 and (p70 is None or name_ret < p70):
        return []
    if sd < 0 and (p30 is None or name_ret > p30):
        return []
    df = _t(_tradeable(bars))
    b = _bar_at(df, MINUTE_1015)
    if b is None:
        return []
    return [
        Signal(
            b["bar_start"],
            str(b["symbol"]),
            sd,
            0.0,
            None,
            abs(name_ret),
            "rs_vs_book",
            stop_from_entry=True,
        )
    ]


def down_day_then_trend_signals(
    bars: pl.DataFrame, trend: Trend, prior_morning_ret: float | None
) -> list[Signal]:
    sd = _side(trend)
    if sd is None or prior_morning_ret is None:
        return []
    against = (sd > 0 and prior_morning_ret < 0) or (sd < 0 and prior_morning_ret > 0)
    if not against:
        return []
    df = _t(_tradeable(bars))
    b = _bar_at(df, RTH_OPEN)
    if b is None:
        return []
    return [
        Signal(
            b["bar_start"],
            str(b["symbol"]),
            sd,
            0.0,
            None,
            abs(prior_morning_ret),
            "down_day_then_trend",
            stop_from_entry=True,
        )
    ]


def adv_expanding_signals(bars: pl.DataFrame, trend: Trend, adv_ok: bool) -> list[Signal]:
    sd = _side(trend)
    if sd is None or not adv_ok:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    b930 = _bar_at(df, RTH_OPEN)
    if b930 is None:
        return []
    open_930 = float(b930["open"])
    later = df.filter(pl.col("t") >= MINUTE_1000)
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        with_trend = (sd > 0 and close > open_930) or (sd < 0 and close < open_930)
        if with_trend:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    sd,
                    0.0,
                    None,
                    abs(close / open_930 - 1.0),
                    "adv_expanding",
                    stop_from_entry=True,
                )
            ]
    return []


def late_with_trend_signals(bars: pl.DataFrame, trend: Trend) -> list[Signal]:
    sd = _side(trend)
    if sd is None:
        return []
    df = _t(_tradeable(bars))
    b930 = _bar_at(df, RTH_OPEN)
    b1100 = _bar_at(df, MINUTE_1100)
    if b930 is None or b1100 is None:
        return []
    open_930 = float(b930["open"])
    close = float(b1100["close"])
    with_trend = (sd > 0 and close > open_930) or (sd < 0 and close < open_930)
    if not with_trend:
        return []
    return [
        Signal(b1100["bar_start"], str(b1100["symbol"]), sd, open_930, None, abs(close / open_930 - 1.0), "late_with_trend")
    ]


def channel_position_signals(
    bars: pl.DataFrame, trend: Trend, h: float | None, l: float | None
) -> list[Signal]:
    sd = _side(trend)
    if sd is None or h is None or l is None or h <= l:
        return []
    mid = (h + l) / 2.0
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        ok = (sd > 0 and mid <= close <= h) or (sd < 0 and l <= close <= mid)
        if ok:
            return [
                Signal(rec["bar_start"], str(rec["symbol"]), sd, mid, None, abs(close - mid), "channel_position")
            ]
    return []


def session_pullback_signals(bars: pl.DataFrame) -> list[Signal]:
    """After 10:00, 1% pullback from today's RTH extreme; both directions, no 10d trend."""
    df = _t(_tradeable(bars)).sort("bar_start")
    rth = df.filter(pl.col("t") >= RTH_OPEN)
    if rth.height == 0:
        return []
    highs = rth["high"].to_list()
    lows = rth["low"].to_list()
    closes = rth["close"].to_list()
    times = rth["bar_start"].to_list()
    clocks = rth["t"].to_list()
    sym = str(rth["symbol"][0])
    ext_hi = float("-inf")
    ext_lo = float("inf")
    for i in range(rth.height):
        ext_hi = max(ext_hi, float(highs[i]))
        ext_lo = min(ext_lo, float(lows[i]))
        if clocks[i] < MINUTE_1000:
            continue
        close = float(closes[i])
        off_hi = (ext_hi - close) / ext_hi if ext_hi > 0 else 0.0
        off_lo = (close - ext_lo) / ext_lo if ext_lo > 0 else 0.0
        if off_hi >= 0.01 and off_hi >= off_lo:
            stop = float(lows[i])
            if stop > 0 and close - stop >= 0.01:
                return [Signal(times[i], sym, 1, stop, None, off_hi, "session_pullback")]
        if off_lo >= 0.01:
            stop = float(highs[i])
            if stop - close >= 0.01:
                return [Signal(times[i], sym, -1, stop, None, off_lo, "session_pullback")]
    return []


def failed_yday_break_signals(
    bars: pl.DataFrame, prior_high: float | None, prior_low: float | None
) -> list[Signal]:
    """Fade a failed prior-session break: first RTH close beyond yday high/low, then
    a later RTH close back inside that level before 11:00. Stop = failed extreme.
    No 10d-trend tether. Clean (un-failed) breaks do not fire.
    """
    if prior_high is None or prior_low is None:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    rth = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") < MINUTE_1100))
    if rth.height == 0:
        return []
    highs = rth["high"].to_list()
    lows = rth["low"].to_list()
    closes = rth["close"].to_list()
    times = rth["bar_start"].to_list()
    sym = str(rth["symbol"][0])
    broke: str | None = None
    ext: float | None = None
    for i in range(rth.height):
        close = float(closes[i])
        hi = float(highs[i])
        lo = float(lows[i])
        if broke is None:
            if close > prior_high:
                broke = "high"
                ext = hi
            elif close < prior_low:
                broke = "low"
                ext = lo
            continue
        if broke == "high":
            ext = max(float(ext), hi)
            if close <= prior_high:
                stop = float(ext)
                if stop - close < 0.01:
                    continue
                return [
                    Signal(times[i], sym, -1, stop, None, stop - prior_high, "failed_yday_break")
                ]
        else:
            ext = min(float(ext), lo)
            if close >= prior_low:
                stop = float(ext)
                if close - stop < 0.01:
                    continue
                return [
                    Signal(times[i], sym, 1, stop, None, prior_low - stop, "failed_yday_break")
                ]
    return []


def yday_level_break_free_signals(
    bars: pl.DataFrame, prior_high: float | None, prior_low: float | None
) -> list[Signal]:
    if prior_high is None or prior_low is None:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    rth = df.filter(pl.col("t") >= RTH_OPEN)
    for rec in rth.iter_rows(named=True):
        close = float(rec["close"])
        ts = rec["bar_start"]
        sym = str(rec["symbol"])
        if close > prior_high:
            return [Signal(ts, sym, 1, prior_high, None, close - prior_high, "yday_level_break")]
        if close < prior_low:
            return [Signal(ts, sym, -1, prior_low, None, prior_low - close, "yday_level_break")]
    return []


def compression_expansion_free_signals(
    bars: pl.DataFrame,
    median_range: float | None,
    prior_range: float | None,
) -> list[Signal]:
    """Direction = 15-min expansion (09:44 close vs opening range), not EOD trend."""
    if median_range is None or prior_range is None or median_range <= 0:
        return []
    if prior_range > 0.7 * median_range:
        return []
    df = _t(_tradeable(bars))
    first15 = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0944))
    last = first15.filter(pl.col("t") == MINUTE_0944)
    if last.height != 1 or first15.height < 2:
        return []
    hi = float(first15["high"].max())
    lo = float(first15["low"].min())
    rng = hi - lo
    if rng < 1.2 * median_range:
        return []
    rec = last.row(0, named=True)
    close = float(rec["close"])
    third = rng / 3.0
    if close >= hi - third:
        sd, stop = 1, lo
    elif close <= lo + third:
        sd, stop = -1, hi
    else:
        return []
    return [
        Signal(rec["bar_start"], str(rec["symbol"]), sd, stop, None, rng / median_range, "compression_expansion")
    ]


def rs_vs_book_free_signals(
    bars: pl.DataFrame,
    name_ret: float | None,
    p70: float | None,
    p30: float | None,
) -> list[Signal]:
    if name_ret is None:
        return []
    sd = None
    if p70 is not None and name_ret >= p70:
        sd = 1
    elif p30 is not None and name_ret <= p30:
        sd = -1
    if sd is None:
        return []
    df = _t(_tradeable(bars))
    b = _bar_at(df, MINUTE_1015)
    if b is None:
        return []
    return [
        Signal(
            b["bar_start"],
            str(b["symbol"]),
            sd,
            0.0,
            None,
            abs(name_ret),
            "rs_vs_book",
            stop_from_entry=True,
        )
    ]


def adv_expanding_free_signals(bars: pl.DataFrame, adv_ok: bool) -> list[Signal]:
    """Direction = 09:30→10:00 session direction, not 10d trend."""
    if not adv_ok:
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    b930 = _bar_at(df, RTH_OPEN)
    b1000 = _bar_at(df, MINUTE_1000)
    if b930 is None or b1000 is None:
        return []
    open_930 = float(b930["open"])
    if open_930 <= 0:
        return []
    ret0 = float(b1000["close"]) / open_930 - 1.0
    if ret0 > 0:
        sd = 1
    elif ret0 < 0:
        sd = -1
    else:
        return []
    later = df.filter(pl.col("t") >= MINUTE_1000)
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        still = (sd > 0 and close > open_930) or (sd < 0 and close < open_930)
        if still:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    sd,
                    0.0,
                    None,
                    abs(close / open_930 - 1.0),
                    "adv_expanding",
                    stop_from_entry=True,
                )
            ]
    return []


def rth_return_at(bars: pl.DataFrame, t: time) -> float | None:
    df = _t(_tradeable(bars))
    b930 = _bar_at(df, RTH_OPEN)
    bt = _bar_at(df, t)
    if b930 is None or bt is None:
        return None
    o = float(b930["open"])
    if o <= 0:
        return None
    return float(bt["close"]) / o - 1.0
