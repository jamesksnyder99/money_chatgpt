from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from research.fills import is_tradeable
from research.harness import ATR_BARS, STOP_FLOOR_FRAC, atr_last6_5m
from research.signals import MINUTE_0945, RTH_OPEN, bar_time
from research.strategies15 import resample_5m


def r1_haircut(bars: pl.DataFrame, launch_ts: datetime, prior_close: float) -> float:
    """1R as a fraction of sea level (prior close). <6 completed 5-min bars → 0.6%."""
    if prior_close is None or float(prior_close) <= 0:
        return STOP_FLOOR_FRAC
    bars5 = resample_5m(bars)
    done = [b for b in bars5 if b["last_ts"] <= launch_ts]
    if len(done) < 6:
        return STOP_FLOOR_FRAC
    atr = atr_last6_5m(bars, launch_ts)
    if atr <= 0:
        return STOP_FLOOR_FRAC
    return max(float(atr) / float(prior_close), STOP_FLOOR_FRAC)


def gross_altitude(max_high: float | None, prior_close: float | None, r1: float) -> float:
    """max(0, (max_high/prior_close − 1) − r1). Depths below sea do not subtract."""
    if max_high is None or prior_close is None or float(prior_close) <= 0:
        return 0.0
    ext = float(max_high) / float(prior_close) - 1.0
    return max(0.0, ext - float(r1))


HARVEST_MIN_VOL = 2000


def first_fillable_index(pack: dict, confirm_ts: datetime) -> int | None:
    """Index of first volume>=2000 tradeable bar at/after the fillable clock.

    RTH launches: confirm+5m. Premarket (before 09:30): 09:45.
    """
    launch_pre = bar_time(confirm_ts) < RTH_OPEN
    earliest = confirm_ts + timedelta(minutes=5)
    floor_clock = MINUTE_0945 if launch_pre else RTH_OPEN
    times = pack["ts"]
    opens = pack["open"]
    closes = pack["close"]
    vols = pack["vol"]
    for i, ts in enumerate(times):
        if ts < earliest:
            continue
        if bar_time(ts) < floor_clock:
            continue
        if not is_tradeable(opens[i], closes[i], vols[i]):
            continue
        if float(vols[i] or 0.0) < HARVEST_MIN_VOL - 1e-12:
            continue
        return i
    return None


def atr_last6_from_bars5(bars5: list[dict], asof: datetime) -> float:
    """Mean true range of last six completed 5-min bars with last_ts <= asof."""
    done = [b for b in bars5 if b["last_ts"] <= asof]
    if not done:
        return 0.0
    start = max(0, len(done) - ATR_BARS - 1)
    window = done[start:]
    prev_c = None
    trs: list[float] = []
    for b in window:
        h, l, c = b["high"], b["low"], b["close"]
        if prev_c is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        prev_c = c
        trs.append(tr)
    trs = trs[-ATR_BARS:]
    if not trs:
        return 0.0
    return float(sum(trs) / len(trs))


def r1_at_price(bars: pl.DataFrame, stamp: datetime, price: float) -> float:
    """1.0× ATR of last six completed 5-min bars / price, floored at 0.6% of price."""
    if price is None or float(price) <= 0:
        return STOP_FLOOR_FRAC
    bars5 = resample_5m(bars)
    done = [b for b in bars5 if b["last_ts"] <= stamp]
    if len(done) < 6:
        return STOP_FLOOR_FRAC
    atr = atr_last6_from_bars5(bars5, stamp)
    if atr <= 0:
        return STOP_FLOOR_FRAC
    return max(float(atr) / float(price), STOP_FLOOR_FRAC)


def r1_from_bars5(bars5: list[dict], stamp: datetime, price: float) -> tuple[float, float]:
    """Return (atr, r1_frac) at stamp vs price. <6 completed 5-min bars → floor."""
    if price is None or float(price) <= 0:
        return 0.0, STOP_FLOOR_FRAC
    done_n = sum(1 for b in bars5 if b["last_ts"] <= stamp)
    if done_n < 6:
        return 0.0, STOP_FLOOR_FRAC
    atr = atr_last6_from_bars5(bars5, stamp)
    if atr <= 0:
        return 0.0, STOP_FLOOR_FRAC
    return float(atr), max(float(atr) / float(price), STOP_FLOOR_FRAC)


def harvestable_from_fillable(
    pack: dict | None,
    confirm_ts: datetime | None,
    bars: pl.DataFrame | None,
    *,
    bars5: list[dict] | None = None,
) -> dict:
    """A35: leftover after 1R from the first fillable bar's price, not from prior close.

    harvestable = max(0, max_high_after_fillable / fill_px − 1 − r1)
    r1 at the fillable stamp, floored at 0.6% of fill_px.
    """
    out = {
        "harvest_ts": None,
        "fill_px": None,
        "max_high": None,
        "harvestable": 0.0,
        "r1": None,
        "atr": None,
        "fill_low": None,
    }
    if pack is None or confirm_ts is None:
        return out
    i = first_fillable_index(pack, confirm_ts)
    if i is None:
        return out
    px = float(pack["close"][i])
    if px <= 0:
        return out
    ts = pack["ts"][i]
    if bars5 is not None:
        atr, r1 = r1_from_bars5(bars5, ts, px)
    elif bars is not None:
        r1 = r1_at_price(bars, ts, px)
        atr = atr_last6_5m(bars, ts)
    else:
        r1 = STOP_FLOOR_FRAC
        atr = 0.0
    mh = None
    highs = pack["high"]
    for j in range(i, len(pack["ts"])):
        h = float(highs[j])
        mh = h if mh is None else max(mh, h)
    harv = 0.0
    if mh is not None:
        harv = max(0.0, float(mh) / px - 1.0 - float(r1))
    out["harvest_ts"] = ts
    out["fill_px"] = px
    out["max_high"] = mh
    out["harvestable"] = harv
    out["r1"] = r1
    out["atr"] = atr
    out["fill_low"] = float(pack["low"][i])
    return out


def harvestable_altitude(
    pack: dict | None,
    confirm_ts: datetime | None,
    prior_close: float | None,
    r1: float,
) -> dict:
    """C-R7: altitude from the first fillable bar after confirm+5m.

    RTH launches harvest from RTH; premarket launches from 09:45.
    Fillable = tradeable open/close and volume ≥ 2000.
    """
    out = {
        "harvest_ts": None,
        "harvestable": 0.0,
        "max_high": None,
    }
    if pack is None or confirm_ts is None or prior_close is None or float(prior_close) <= 0:
        return out
    launch_pre = bar_time(confirm_ts) < RTH_OPEN
    earliest = confirm_ts + timedelta(minutes=5)
    if launch_pre:
        floor_clock = MINUTE_0945
    else:
        floor_clock = RTH_OPEN
    times = pack["ts"]
    opens = pack["open"]
    highs = pack["high"]
    closes = pack["close"]
    vols = pack["vol"]
    harvest_i = None
    for i, ts in enumerate(times):
        if ts < earliest:
            continue
        if bar_time(ts) < floor_clock:
            continue
        if not is_tradeable(opens[i], closes[i], vols[i]):
            continue
        if float(vols[i] or 0.0) < HARVEST_MIN_VOL - 1e-12:
            continue
        harvest_i = i
        break
    if harvest_i is None:
        return out
    mh = None
    for i in range(harvest_i, len(times)):
        h = float(highs[i])
        mh = h if mh is None else max(mh, h)
    out["harvest_ts"] = times[harvest_i]
    out["max_high"] = mh
    out["harvestable"] = gross_altitude(mh, prior_close, r1)
    return out
