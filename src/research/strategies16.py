from __future__ import annotations

import math
from datetime import datetime, timedelta

import polars as pl

from research.ema15 import ema9_at
from research.fills import is_tradeable, tradeable_mask
from research.rockets import median_prior_window, window_volume
from research.signals import MINUTE_1000, RTH_OPEN, Signal, bar_time
from research.strategies15 import (
    _finite,
    _vwap_at,
    c5_ema9_plus_memory,
    control_c5_ema9,
    resample_5m,
)

STOP_MIN_FRAC = 0.004
REL_VOL_MIN = 3.0
PRE_ROCKET = 1.10


def _ctrl_idx(bars: pl.DataFrame, sig: Signal) -> tuple[list[dict], int | None]:
    bars5 = resample_5m(bars)
    idx = next((i for i, b in enumerate(bars5) if b["last_ts"] == sig.signal_ts), None)
    return bars5, idx


def _retag(sig: Signal, tag: str, stop: float | None = None) -> Signal:
    return Signal(
        sig.signal_ts,
        sig.symbol,
        -1,
        sig.stop if stop is None else stop,
        None,
        sig.score,
        tag,
    )


def _next_fill_open(bars: pl.DataFrame, signal_ts: datetime) -> float | None:
    ok = bars.filter(tradeable_mask(bars)).sort("bar_start")
    if ok.height == 0:
        return None
    times = ok["bar_start"].to_list()
    opens = ok["open"].to_list()
    closes = ok["close"].to_list()
    vols = ok["volume"].to_list()
    for ts, o, c, v in zip(times, opens, closes, vols):
        if ts <= signal_ts:
            continue
        if is_tradeable(o, c, v):
            return float(o)
    return None


def premarket_hit_10(bars: pl.DataFrame, prior_close: float) -> bool:
    """True if a 07:30-09:29 tradeable high reached +10% vs prior close."""
    if prior_close is None or prior_close <= 0:
        return False
    thresh = PRE_ROCKET * float(prior_close)
    ok = bars.filter(tradeable_mask(bars)).sort("bar_start")
    if ok.height == 0:
        return False
    times = ok["bar_start"].to_list()
    highs = ok["high"].to_list()
    for ts, h in zip(times, highs):
        if bar_time(ts) >= RTH_OPEN:
            break
        if float(h) >= thresh - 1e-12:
            return True
    return False


def c5_ema9_three_down(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """Control only if the three 5-min closes before the signal bar are descending."""
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    bars5, idx = _ctrl_idx(bars, sigs[0])
    if idx is None or idx < 3:
        return []
    a, b, c = bars5[idx - 3]["close"], bars5[idx - 2]["close"], bars5[idx - 1]["close"]
    if not (a > b + 1e-12 and b > c + 1e-12):
        return []
    return [_retag(sigs[0], "c5_ema9_3down")]


def c5_ema9_below_avwap(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """Control only if the signal 5-min close is also below 09:30 AVWAP."""
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    bars5, idx = _ctrl_idx(bars, sigs[0])
    if idx is None:
        return []
    vw = _vwap_at(bars)
    av = vw.get(bars5[idx]["last_ts"])
    if not _finite(av) or bars5[idx]["close"] >= float(av):
        return []
    return [_retag(sigs[0], "c5_ema9_avwap")]


def c5_ema9_relvol(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
    prior_vols: list[float],
) -> list[Signal]:
    """Control + rocket-scan rel vol >= 3x. Silent if fewer than 5 prior windows."""
    med = median_prior_window(prior_vols)
    if med is None:
        return []
    today = window_volume(bars)
    if today / med < REL_VOL_MIN - 1e-12:
        return []
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    return [_retag(sigs[0], "c5_ema9_rv3")]


def c5_ema9_prior_morning_stop(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
    prior_high: float | None,
) -> list[Signal]:
    """Control, stop = prior session morning high if above fill and >= 0.4% away."""
    if prior_high is None or not math.isfinite(prior_high):
        return []
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    sig = sigs[0]
    fill = _next_fill_open(bars, sig.signal_ts)
    if fill is None or fill <= 0:
        return []
    if prior_high <= fill + 1e-12:
        return []
    if (prior_high - fill) / fill < STOP_MIN_FRAC - 1e-12:
        return []
    return [_retag(sig, "c5_ema9_pdhigh", stop=float(prior_high))]


def c5_ema9_after_1000(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """First 5-min close below ema9 at or after 10:00. Ignores 09:45-09:59 crosses."""
    bars5 = resample_5m(bars)
    delta = timedelta(minutes=5)
    for b in bars5:
        if bar_time(b["start"]) < MINUTE_1000:
            continue
        ema9 = ema9_at(stitched, b["start"] + delta)
        if ema9 is None:
            continue
        if b["close"] < ema9:
            stop = max(or_high, b["high"])
            return [
                Signal(
                    b["last_ts"],
                    b["symbol"],
                    -1,
                    stop,
                    None,
                    ema9 - b["close"],
                    "c5_ema9_1000",
                )
            ]
    return []


def c5_ema9_no_pre_rocket(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
    prior_close: float | None,
) -> list[Signal]:
    """Control only if 07:30-09:29 never printed +10% vs prior close."""
    if prior_close is None or premarket_hit_10(bars, prior_close):
        return []
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    return [_retag(sigs[0], "c5_ema9_nopre")]


def c5_ema9_expanding(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """Control only if the signal 5-min range > prior 5-min range."""
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    bars5, idx = _ctrl_idx(bars, sigs[0])
    if idx is None or idx < 1:
        return []
    prev = bars5[idx - 1]["high"] - bars5[idx - 1]["low"]
    cur = bars5[idx]["high"] - bars5[idx]["low"]
    if not (cur > prev + 1e-12):
        return []
    return [_retag(sigs[0], "c5_ema9_expand")]


def c5_ema9_mem_avwap(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """Ids 2+4: memory and signal 5-min close below AVWAP."""
    mem = c5_ema9_plus_memory(bars, stitched, or_high)
    if not mem:
        return []
    below = c5_ema9_below_avwap(bars, stitched, or_high)
    if not below:
        return []
    return [_retag(mem[0], "c5_ema9_mem_avwap")]
