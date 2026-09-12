from __future__ import annotations

from datetime import datetime

import polars as pl

from research.signals import MINUTE_0945, RTH_OPEN, Signal, bar_time
from research.strategies15 import is_strong_close, resample_5m

PRE_DV_MIN = 250_000.0
PRE_DV_REL_MIN = 3.0
EXT_LO = 0.03
EXT_HI = 0.15
STOP_MIN_FRAC = 0.004


def hot_gate(
    *,
    pre_dv: float | None,
    pre_dv_rel: float | None,
    ext_0929: float | None,
) -> bool:
    """09:29 point-in-time hot engine: 3x pre$vol, +3% to <+15%, $250k floor."""
    if pre_dv is None or pre_dv < PRE_DV_MIN - 1e-9:
        return False
    if pre_dv_rel is None or pre_dv_rel < PRE_DV_REL_MIN - 1e-12:
        return False
    if ext_0929 is None:
        return False
    return EXT_LO - 1e-12 <= float(ext_0929) < EXT_HI


def gap_and_go_long(
    last_ts: datetime,
    symbol: str,
    sess_low: float,
    last_px: float,
    score: float,
    *,
    tag: str = "hot_open",
) -> list[Signal]:
    """Long only. Stop = 09:29 session low. Skip if stop >= last_px or < 0.4% away."""
    if last_px is None or sess_low is None or last_px <= 0:
        return []
    if sess_low >= last_px - 1e-12:
        return []
    if (last_px - sess_low) / last_px < STOP_MIN_FRAC - 1e-12:
        return []
    return [Signal(last_ts, symbol, 1, float(sess_low), None, float(score), tag)]


def strong_hold_long(bars: pl.DataFrame, last_px: float) -> list[Signal]:
    """After 09:30, first 5-min strong close that holds >= 09:29 last_px. Longs only."""
    if last_px is None:
        return []
    for b in resample_5m(bars):
        if bar_time(b["start"]) < RTH_OPEN:
            continue
        if not is_strong_close(b["open"], b["high"], b["low"], b["close"]):
            continue
        if b["close"] < last_px - 1e-12:
            continue
        stop = b["low"]
        if stop >= b["close"] - 1e-12:
            continue
        if (b["close"] - stop) / b["close"] < STOP_MIN_FRAC - 1e-12:
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - last_px,
                "hot_strong5",
            )
        ]
    return []


def new_high_long(bars: pl.DataFrame) -> list[Signal]:
    """After 09:45, first 5-min close that is a new session high. Longs only."""
    bars5 = resample_5m(bars)
    if not bars5:
        return []
    ok = bars.filter(pl.col("bar_start").is_not_null()).sort("bar_start")
    if ok.height == 0:
        return []
    times = ok["bar_start"].to_list()
    highs = [float(x) for x in ok["high"].to_list()]
    for b in bars5:
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        prior_high = None
        for ts, h in zip(times, highs):
            if ts >= b["start"]:
                break
            prior_high = h if prior_high is None else max(prior_high, h)
        if prior_high is None:
            continue
        if b["close"] <= prior_high + 1e-12:
            continue
        stop = b["low"]
        if stop >= b["close"] - 1e-12:
            continue
        if (b["close"] - stop) / b["close"] < STOP_MIN_FRAC - 1e-12:
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - prior_high,
                "hot_newhigh",
            )
        ]
    return []
