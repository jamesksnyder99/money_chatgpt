from __future__ import annotations

import math
from datetime import datetime

import polars as pl

from research.fills import is_tradeable, rth_session_vwap
from research.signals import RTH_OPEN, Signal, bar_time
from research.strategies20 import STOP_MIN_FRAC, gap_and_go_long

EXT8_HI = 0.08
PRE_DV_1M = 1_000_000.0
MAX_OPEN_GAP = 0.01


def first_rth_open(bars: pl.DataFrame) -> float | None:
    if bars.height == 0:
        return None
    df = bars.sort("bar_start")
    for rec in df.iter_rows(named=True):
        if bar_time(rec["bar_start"]) < RTH_OPEN:
            continue
        if is_tradeable(rec["open"], rec["close"], rec["volume"]):
            return float(rec["open"])
    return None


def rth_open_gap_ok(open_930: float | None, last_px: float | None, *, max_gap: float = MAX_OPEN_GAP) -> bool:
    """True iff 09:30 open is no more than max_gap above the 09:29 last_px."""
    if open_930 is None or last_px is None or last_px <= 0:
        return False
    return float(open_930) / float(last_px) - 1.0 <= max_gap + 1e-12


def gap1_open_long(
    bars: pl.DataFrame,
    last_ts: datetime,
    symbol: str,
    sess_low: float,
    last_px: float,
    score: float,
) -> list[Signal]:
    """09:30 open long only if that open is <= +1% vs 09:29 last_px."""
    if not rth_open_gap_ok(first_rth_open(bars), last_px, max_gap=MAX_OPEN_GAP):
        return []
    return gap_and_go_long(last_ts, symbol, sess_low, last_px, score, tag="hot_open_gap1")


def pullback_long(bars: pl.DataFrame, last_px: float, score: float | None = None) -> list[Signal]:
    """After 09:30, first bar that tags 09:29 last_px or prior RTH VWAP from below and closes above.

    VWAP is the running RTH VWAP through the previous tradeable RTH bar so the
    first print cannot tautologically 'tag' its own typical price.
    """
    if last_px is None:
        return []
    df = bars.sort("bar_start")
    if df.height == 0:
        return []
    vw = rth_session_vwap(df)
    times = df["bar_start"].to_list()
    opens = df["open"].to_list()
    lows = df["low"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    sym = str(df["symbol"][0])
    prev_vw = float("nan")
    for i in range(df.height):
        if bar_time(times[i]) < RTH_OPEN:
            continue
        if not is_tradeable(opens[i], closes[i], vols[i]):
            continue
        low = float(lows[i])
        close = float(closes[i])
        tagged = False
        if low <= last_px + 1e-12 and close > last_px + 1e-12:
            tagged = True
        if math.isfinite(prev_vw) and low <= prev_vw + 1e-12 and close > prev_vw + 1e-12:
            tagged = True
        v = vw[i]
        if math.isfinite(v):
            prev_vw = float(v)
        if not tagged:
            continue
        stop = low
        if stop >= close - 1e-12:
            continue
        if (close - stop) / close < STOP_MIN_FRAC - 1e-12:
            continue
        sc = float(score) if score is not None else close - stop
        return [
            Signal(
                times[i],
                sym,
                1,
                stop,
                None,
                sc,
                "hot_pullback",
            )
        ]
    return []


def fade_open_short(
    last_ts: datetime,
    symbol: str,
    sess_high: float,
    last_px: float,
    score: float,
) -> list[Signal]:
    """Short only. Stop = 09:29 session high. Skip if stop <= last_px or < 0.4% away."""
    if last_px is None or sess_high is None or last_px <= 0:
        return []
    if sess_high <= last_px + 1e-12:
        return []
    if (sess_high - last_px) / last_px < STOP_MIN_FRAC - 1e-12:
        return []
    return [Signal(last_ts, symbol, -1, float(sess_high), None, float(score), "hot_fade")]
