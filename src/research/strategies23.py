from __future__ import annotations

import math
from datetime import time

import polars as pl

from research.fills import is_tradeable, rth_session_vwap, tradeable_mask
from research.signals import (
    MINUTE_0944,
    MINUTE_0945,
    MINUTE_1100,
    MINUTE_1200,
    RTH_OPEN,
    Signal,
    bar_time,
)
from research.strategies15 import candle_anatomy, is_strong_close, is_weak_close, resample_5m
from research.strategies20 import STOP_MIN_FRAC

COIL_RANGE_MAX = 0.04
FLUSH_UNDERCUT = 0.02
CLIMAX_RANGE_MULT = 2.0


def resample_minutes(df: pl.DataFrame, minutes: int) -> list[dict]:
    """Completed N-min OHLC with open and last 1-min ts."""
    if df is None or df.height == 0 or minutes < 1:
        return []
    ok = df.filter(tradeable_mask(df)).sort("bar_start")
    if ok.height == 0:
        return []
    every = f"{int(minutes)}m"
    ok = ok.with_columns(pl.col("bar_start").dt.truncate(every).alias("bn"))
    g = (
        ok.group_by("bn")
        .agg(
            pl.col("open").sort_by("bar_start").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").sort_by("bar_start").last().alias("close"),
            pl.col("bar_start").sort_by("bar_start").last().alias("last_ts"),
            pl.col("symbol").first().alias("symbol"),
        )
        .sort("bn")
    )
    out: list[dict] = []
    for rec in g.iter_rows(named=True):
        out.append(
            {
                "start": rec["bn"],
                "open": float(rec["open"]),
                "high": float(rec["high"]),
                "low": float(rec["low"]),
                "close": float(rec["close"]),
                "last_ts": rec["last_ts"],
                "symbol": str(rec["symbol"]),
            }
        )
    return out


def coil_range_ok(pre_high: float | None, pre_low: float | None, max_frac: float = COIL_RANGE_MAX) -> bool:
    """True iff (pre_high - pre_low) / mid < max_frac."""
    if pre_high is None or pre_low is None:
        return False
    hi, lo = float(pre_high), float(pre_low)
    if hi < lo:
        return False
    mid = (hi + lo) / 2.0
    if mid <= 0:
        return False
    return (hi - lo) / mid < max_frac - 1e-12


def _long_ok(close: float, stop: float) -> bool:
    if stop >= close - 1e-12:
        return False
    return (close - stop) / close >= STOP_MIN_FRAC - 1e-12


def _short_ok(close: float, stop: float) -> bool:
    if stop <= close + 1e-12:
        return False
    return (stop - close) / close >= STOP_MIN_FRAC - 1e-12


def session_high_before(bars: pl.DataFrame, clock: time) -> float | None:
    if bars is None or bars.height == 0:
        return None
    hi = None
    for rec in bars.sort("bar_start").iter_rows(named=True):
        if bar_time(rec["bar_start"]) >= clock:
            break
        if not is_tradeable(rec["open"], rec["close"], rec["volume"]):
            continue
        h = float(rec["high"])
        hi = h if hi is None else max(hi, h)
    return hi


def coil_break_long(bars: pl.DataFrame, pre_high: float, pre_low: float) -> list[Signal]:
    """After 09:30, first 1-min close above premarket high. Stop = premarket low.

    Silent if the premarket coil is too wide (range/mid >= 4%).
    """
    if not coil_range_ok(pre_high, pre_low):
        return []
    if bars is None or bars.height == 0:
        return []
    df = bars.sort("bar_start")
    times = df["bar_start"].to_list()
    opens = df["open"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    sym = str(df["symbol"][0])
    for i in range(df.height):
        if bar_time(times[i]) < RTH_OPEN:
            continue
        if not is_tradeable(opens[i], closes[i], vols[i]):
            continue
        close = float(closes[i])
        if close <= float(pre_high) + 1e-12:
            continue
        stop = float(pre_low)
        if not _long_ok(close, stop):
            continue
        return [
            Signal(times[i], sym, 1, stop, None, close - float(pre_high), "coil_break")
        ]
    return []


def afternoon_break_long(bars: pl.DataFrame, am_high: float | None) -> list[Signal]:
    """After 12:00, first 5-min close above the session high made before 11:00."""
    if am_high is None:
        return []
    for b in resample_5m(bars):
        if bar_time(b["start"]) < MINUTE_1200:
            continue
        if b["close"] <= float(am_high) + 1e-12:
            continue
        stop = float(b["low"])
        if not _long_ok(b["close"], stop):
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - float(am_high),
                "am_high_break",
            )
        ]
    return []


def failed_rocket_short(bars: pl.DataFrame) -> list[Signal]:
    """After 09:45, first 5-min close below RTH VWAP. Stop = session high at signal. Shorts only."""
    if bars is None or bars.height == 0:
        return []
    df = bars.sort("bar_start")
    vw = rth_session_vwap(df)
    times = df["bar_start"].to_list()
    highs = [float(x) for x in df["high"].to_list()]
    vw_at = {times[i]: vw[i] for i in range(df.height)}
    high_at: dict = {}
    run_hi = None
    for ts, h in zip(times, highs):
        run_hi = h if run_hi is None else max(run_hi, h)
        high_at[ts] = run_hi
    for b in resample_5m(df):
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        v = vw_at.get(b["last_ts"])
        if v is None or not math.isfinite(float(v)):
            continue
        if b["close"] >= float(v) - 1e-12:
            continue
        stop = high_at.get(b["last_ts"])
        if stop is None:
            continue
        if not _short_ok(b["close"], float(stop)):
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                -1,
                float(stop),
                None,
                float(v) - b["close"],
                "fail_rocket",
            )
        ]
    return []


def flush_higher_low_long(bars: pl.DataFrame, last_px_0800: float | None) -> list[Signal]:
    """After 09:30, undercut 08:00 last_px by >= 2%, then 5-min higher-low + strong close."""
    if last_px_0800 is None or last_px_0800 <= 0:
        return []
    thresh = float(last_px_0800) * (1.0 - FLUSH_UNDERCUT)
    bars5 = resample_5m(bars)
    flushed = False
    flush_low = None
    prev = None
    for b in bars5:
        if bar_time(b["start"]) < RTH_OPEN:
            prev = b
            continue
        already = flushed
        if b["low"] <= thresh + 1e-12:
            flushed = True
            flush_low = b["low"] if flush_low is None else min(flush_low, b["low"])
        if (
            already
            and flushed
            and flush_low is not None
            and prev is not None
            and bar_time(prev["start"]) >= RTH_OPEN
            and b["low"] > prev["low"] + 1e-12
            and is_strong_close(b["open"], b["high"], b["low"], b["close"])
        ):
            stop = float(flush_low)
            if _long_ok(b["close"], stop):
                return [
                    Signal(
                        b["last_ts"],
                        b["symbol"],
                        1,
                        stop,
                        None,
                        b["close"] - stop,
                        "flush_hl",
                    )
                ]
        prev = b
    return []


def holds_vs_iwm_long(bars: pl.DataFrame, iwm: pl.DataFrame | None) -> tuple[list[Signal], int]:
    """After 09:45, first 15-min green while the same 15-min IWM bar is red.

    Missing IWM for a window skips that candidate and increments the skip count.
    """
    name15 = resample_minutes(bars, 15)
    iwm15 = resample_minutes(iwm, 15) if iwm is not None else []
    iwm_by = {b["start"]: b for b in iwm15}
    skips = 0
    for b in name15:
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        # last fillable 15-min starts 11:30 (last_ts 11:44); 11:45 fills at/after 11:59 flatten
        if bar_time(b["start"]) > time(11, 30):
            continue
        if b["close"] <= b["open"] + 1e-12:
            continue
        ib = iwm_by.get(b["start"])
        if ib is None:
            skips += 1
            continue
        if ib["close"] >= ib["open"] - 1e-12:
            continue
        stop = float(b["low"])
        if not _long_ok(b["close"], stop):
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - b["open"],
                "vs_iwm",
            )
        ], skips
    return [], skips


def climax_short(bars: pl.DataFrame) -> list[Signal]:
    """After 09:45, first 5-min with range >= 2x median 09:30-09:44 range and close_loc <= 0.25."""
    bars5 = resample_5m(bars)
    or_ranges = [
        b["high"] - b["low"]
        for b in bars5
        if RTH_OPEN <= bar_time(b["start"]) <= MINUTE_0944 and b["high"] > b["low"]
    ]
    if not or_ranges:
        return []
    ys = sorted(or_ranges)
    mid = ys[len(ys) // 2] if len(ys) % 2 else 0.5 * (ys[len(ys) // 2 - 1] + ys[len(ys) // 2])
    if mid <= 1e-12:
        return []
    need = CLIMAX_RANGE_MULT * mid
    for b in bars5:
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        rng = b["high"] - b["low"]
        if rng < need - 1e-12:
            continue
        a = candle_anatomy(b["open"], b["high"], b["low"], b["close"])
        if a is None or a["close_loc"] > 0.25 + 1e-12:
            continue
        if not is_weak_close(b["open"], b["high"], b["low"], b["close"]):
            continue
        stop = float(b["high"])
        if not _short_ok(b["close"], stop):
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                -1,
                stop,
                None,
                rng,
                "climax",
            )
        ]
    return []
