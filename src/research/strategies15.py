from __future__ import annotations

import math
from datetime import datetime, time

import polars as pl

from research.ema15 import bar_end, ema9_at
from research.fills import rth_session_vwap, tradeable_mask
from research.signals import MINUTE_0944, MINUTE_0945, RTH_OPEN, Signal, bar_time
from research.strategies8 import _bar_at, _t, _tradeable, opening_range
from research.strategies13 import five_min_close_below_ema9

MINUTE_0931 = time(9, 31)
OR_W_MIN = 0.025


def candle_anatomy(
    open_: float, high: float, low: float, close: float
) -> dict[str, float] | None:
    rng = float(high) - float(low)
    if rng <= 1e-12:
        return None
    o, c = float(open_), float(close)
    body = abs(c - o)
    upper = float(high) - max(o, c)
    lower = min(o, c) - float(low)
    close_loc = (c - float(low)) / rng
    return {
        "body": body,
        "range": rng,
        "close_loc": close_loc,
        "upper": upper,
        "lower": lower,
    }


def is_weak_close(open_: float, high: float, low: float, close: float) -> bool:
    a = candle_anatomy(open_, high, low, close)
    return a is not None and a["close_loc"] <= 0.25 + 1e-12


def is_strong_close(open_: float, high: float, low: float, close: float) -> bool:
    a = candle_anatomy(open_, high, low, close)
    return a is not None and a["close_loc"] >= 0.75 - 1e-12


def is_hammer(open_: float, high: float, low: float, close: float) -> bool:
    """Lower wick >= 2x body, close_loc >= 0.6, upper wick not longer than the body."""
    a = candle_anatomy(open_, high, low, close)
    if a is None:
        return False
    if a["lower"] < 2.0 * a["body"] - 1e-12:
        return False
    if a["close_loc"] < 0.6 - 1e-12:
        return False
    if a["upper"] > a["body"] + 1e-12:
        return False
    return True


def resample_5m(df: pl.DataFrame) -> list[dict]:
    """Completed 5-min OHLC with open and last 1-min ts."""
    if df.height == 0:
        return []
    ok = df.filter(tradeable_mask(df)).sort("bar_start")
    if ok.height == 0:
        return []
    ok = ok.with_columns(pl.col("bar_start").dt.truncate("5m").alias("b5"))
    g = (
        ok.group_by("b5")
        .agg(
            pl.col("open").sort_by("bar_start").first().alias("open"),
            pl.col("high").max().alias("high"),
            pl.col("low").min().alias("low"),
            pl.col("close").sort_by("bar_start").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
            pl.col("bar_start").sort_by("bar_start").last().alias("last_ts"),
            pl.col("symbol").first().alias("symbol"),
        )
        .sort("b5")
    )
    out: list[dict] = []
    for rec in g.iter_rows(named=True):
        start = rec["b5"]
        out.append(
            {
                "start": start,
                "open": float(rec["open"]),
                "high": float(rec["high"]),
                "low": float(rec["low"]),
                "close": float(rec["close"]),
                "volume": float(rec["volume"]),
                "last_ts": rec["last_ts"],
                "bar_end": bar_end(start, 5),
                "symbol": str(rec["symbol"]),
            }
        )
    return out


def _vwap_at(bars: pl.DataFrame) -> dict:
    df = bars.sort("bar_start")
    vw = rth_session_vwap(df)
    times = df["bar_start"].to_list()
    return {times[i]: vw[i] for i in range(len(times))}


def _finite(x) -> bool:
    return x is not None and math.isfinite(float(x))


def control_c5_ema9(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """Exact Arrow 13/14 door: first 5-min close below ema9 after 09:45. Shorts only."""
    return [s for s in five_min_close_below_ema9(bars, stitched, or_high) if s.side == -1]


def c5_ema9_plus_memory(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """Control entry only if the last two completed 5-min highs are descending."""
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    bars5 = resample_5m(bars)
    sig = sigs[0]
    idx = next(
        (i for i, b in enumerate(bars5) if b.get("bar_end") == sig.signal_ts or b["last_ts"] == sig.signal_ts),
        None,
    )
    if idx is None or idx < 1:
        return []
    if not (bars5[idx - 1]["high"] > bars5[idx]["high"] + 1e-12):
        return []
    return [Signal(sig.signal_ts, sig.symbol, -1, sig.stop, None, sig.score, "c5_ema9_mem")]


def c5_ema9_plus_weak(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """Control entry only if the signal 5-min is a weak close."""
    sigs = control_c5_ema9(bars, stitched, or_high)
    if not sigs:
        return []
    bars5 = resample_5m(bars)
    sig = sigs[0]
    b = next(
        (x for x in bars5 if x.get("bar_end") == sig.signal_ts or x["last_ts"] == sig.signal_ts),
        None,
    )
    if b is None or not is_weak_close(b["open"], b["high"], b["low"], b["close"]):
        return []
    return [Signal(sig.signal_ts, sig.symbol, -1, sig.stop, None, sig.score, "c5_ema9_weak")]


def c5_close_below_avwap_weak(bars: pl.DataFrame, or_high: float) -> list[Signal]:
    """First 5-min after 09:45: close < 09:30 AVWAP and weak close. No 9/21. Shorts only."""
    bars5 = resample_5m(bars)
    vw = _vwap_at(bars)
    for b in bars5:
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        av = vw.get(b["last_ts"])
        if not _finite(av):
            continue
        if b["close"] >= float(av):
            continue
        if not is_weak_close(b["open"], b["high"], b["low"], b["close"]):
            continue
        stop = max(or_high, b["high"])
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                -1,
                stop,
                None,
                float(av) - b["close"],
                "c5_avwap_weak",
            )
        ]
    return []


def one_min_close_below_ema9(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> list[Signal]:
    """After 09:45, first 1-min close below ema9. Stop = max(OR high, that 1-min high)."""
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        ema9 = ema9_at(stitched, rec["bar_start"])
        if ema9 is None:
            continue
        close = float(rec["close"])
        if close < ema9:
            stop = max(or_high, float(rec["high"]))
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    -1,
                    stop,
                    None,
                    ema9 - close,
                    "c1_ema9",
                )
            ]
    return []


def one_min_ema9_running_or(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
) -> list[Signal]:
    """From 09:31, first 1-min close below ema9 with running OR width > 2.5%. Stop = run high."""
    df = _t(_tradeable(bars)).sort("bar_start")
    rth = df.filter(pl.col("t") >= RTH_OPEN)
    run_h: float | None = None
    run_l: float | None = None
    for rec in rth.iter_rows(named=True):
        h = float(rec["high"])
        l = float(rec["low"])
        run_h = h if run_h is None else max(run_h, h)
        run_l = l if run_l is None else min(run_l, l)
        if rec["t"] < MINUTE_0931:
            continue
        mid = (run_h + run_l) / 2.0
        if mid <= 0:
            continue
        width = (run_h - run_l) / mid
        if width <= OR_W_MIN + 1e-12:
            continue
        ema9 = ema9_at(stitched, rec["bar_start"])
        if ema9 is None:
            continue
        close = float(rec["close"])
        if close < ema9:
            return [
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    -1,
                    run_h,
                    None,
                    ema9 - close,
                    "c1_ema9_early",
                )
            ]
    return []


def washout_hammer(bars: pl.DataFrame) -> list[Signal]:
    """5-min hammer: low <= OR low, close back inside OR. Longs only. Stop = hammer low."""
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, lo, _w = rng
    for b in resample_5m(bars):
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        if not is_hammer(b["open"], b["high"], b["low"], b["close"]):
            continue
        if b["low"] > lo + 1e-12:
            continue
        if not (lo < b["close"] < hi):
            continue
        stop = b["low"]
        if stop >= b["close"]:
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - stop,
                "washout_hammer",
            )
        ]
    return []


def hold_the_open(bars: pl.DataFrame) -> list[Signal]:
    """09:44 close in top half of OR, then first 5-min strong close above OR mid. Longs only."""
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, lo, _w = rng
    mid = (hi + lo) / 2.0
    df = _t(_tradeable(bars))
    b044 = _bar_at(df, MINUTE_0944)
    if b044 is None or float(b044["close"]) < mid - 1e-12:
        return []
    for b in resample_5m(bars):
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        if not is_strong_close(b["open"], b["high"], b["low"], b["close"]):
            continue
        if b["close"] <= mid + 1e-12:
            continue
        stop = mid
        if stop >= b["close"]:
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - mid,
                "hold_open",
            )
        ]
    return []


def grind_up(bars: pl.DataFrame) -> list[Signal]:
    """Three completed 5-min closes each higher, last bar strong. Stop = low of those three."""
    bars5 = resample_5m(bars)
    for i in range(2, len(bars5)):
        a, b, c = bars5[i - 2], bars5[i - 1], bars5[i]
        if bar_time(c["start"]) < MINUTE_0945:
            continue
        if not (a["close"] < b["close"] < c["close"]):
            continue
        if not is_strong_close(c["open"], c["high"], c["low"], c["close"]):
            continue
        stop = min(a["low"], b["low"], c["low"])
        if stop >= c["close"]:
            continue
        return [
            Signal(
                c["last_ts"],
                c["symbol"],
                1,
                stop,
                None,
                c["close"] - stop,
                "grind_up",
            )
        ]
    return []


def avwap_reclaim_strong(bars: pl.DataFrame) -> list[Signal]:
    """After 09:45 lose 09:30 AVWAP on a 5-min close, then 5-min strong close back above."""
    bars5 = resample_5m(bars)
    vw = _vwap_at(bars)
    lost = False
    for b in bars5:
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        av = vw.get(b["last_ts"])
        if not _finite(av):
            continue
        avf = float(av)
        if not lost:
            if b["close"] < avf:
                lost = True
            continue
        if not is_strong_close(b["open"], b["high"], b["low"], b["close"]):
            continue
        if b["close"] <= avf:
            continue
        stop = b["low"]
        if stop >= b["close"]:
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - avf,
                "avwap_reclaim",
            )
        ]
    return []


def prior_morning_break(bars: pl.DataFrame, prior_high: float | None) -> list[Signal]:
    """5-min close above prior-day RTH high, body >= 0.5x range, strong close. Longs only."""
    if prior_high is None or not math.isfinite(prior_high):
        return []
    for b in resample_5m(bars):
        if bar_time(b["start"]) < RTH_OPEN:
            continue
        if b["close"] <= prior_high + 1e-12:
            continue
        a = candle_anatomy(b["open"], b["high"], b["low"], b["close"])
        if a is None or a["body"] < 0.5 * a["range"] - 1e-12:
            continue
        if not is_strong_close(b["open"], b["high"], b["low"], b["close"]):
            continue
        stop = b["low"]
        if stop >= b["close"]:
            continue
        return [
            Signal(
                b["last_ts"],
                b["symbol"],
                1,
                stop,
                None,
                b["close"] - prior_high,
                "pd_morn_high",
            )
        ]
    return []


def one_min_hammer_long(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
) -> list[Signal]:
    """After 09:45, first 1-min hammer-like bar that tags ema9 and strong-closes. Longs only."""
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        o, h, l, c = (
            float(rec["open"]),
            float(rec["high"]),
            float(rec["low"]),
            float(rec["close"]),
        )
        if not is_hammer(o, h, l, c):
            continue
        if not is_strong_close(o, h, l, c):
            continue
        ema9 = ema9_at(stitched, rec["bar_start"])
        if ema9 is None:
            continue
        if l > ema9 + 1e-12 or h < ema9 - 1e-12:
            continue
        stop = l
        if stop >= c:
            continue
        return [
            Signal(
                rec["bar_start"],
                str(rec["symbol"]),
                1,
                stop,
                None,
                c - stop,
                "c1_hammer",
            )
        ]
    return []
