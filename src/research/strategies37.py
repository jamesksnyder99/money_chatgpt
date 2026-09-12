"""Arrow 37 — noon hold and afternoon continuation (not afternoon birth)."""

from __future__ import annotations

from datetime import time

import polars as pl

from research.harness import attach_atr, confirmed_launch
from research.signals import (
    MINUTE_1100,
    MINUTE_1130,
    MINUTE_1159,
    MINUTE_1200,
    MINUTE_1330,
    MINUTE_1430,
    Signal,
    bar_time,
)

MINUTE_1400 = time(14, 0)
TIGHT_EXT_1200 = 0.10
TIGHT_EXT_1100 = 0.08
TIGHT_RANGE = 0.04
TIGHT_RVOL = 2.0
LOOSE_EXT_1200 = 0.08
LOOSE_EXT_1100 = 0.05
PULLBACK = 0.05
POWER_EXT = 0.08
POWER_NEAR_HIGH = 0.015
POWER_RANGE = 0.03


def _range_mid(hi, lo) -> float | None:
    if hi is None or lo is None:
        return None
    mid = (float(hi) + float(lo)) / 2.0
    if mid <= 0:
        return None
    return (float(hi) - float(lo)) / mid


def _idx_at_or_before(pack: dict, clock: time) -> int | None:
    last = None
    for i, ts in enumerate(pack["ts"]):
        if bar_time(ts) > clock:
            break
        last = i
    return last


def _idx_at_or_after(pack: dict, clock: time) -> int | None:
    for i, ts in enumerate(pack["ts"]):
        if bar_time(ts) >= clock:
            return i
    return None


def _min_low(pack: dict, t0: time, t1: time) -> float | None:
    lo = None
    for ts, l in zip(pack["ts"], pack["low"]):
        t = bar_time(ts)
        if t < t0:
            continue
        if t > t1:
            break
        lv = float(l)
        lo = lv if lo is None else min(lo, lv)
    return lo


def _range_between(pack: dict, t0: time, t1: time) -> float | None:
    hi = lo = None
    for ts, h, l in zip(pack["ts"], pack["high"], pack["low"]):
        t = bar_time(ts)
        if t < t0:
            continue
        if t > t1:
            break
        hv, lv = float(h), float(l)
        hi = hv if hi is None else max(hi, hv)
        lo = lv if lo is None else min(lo, lv)
    return _range_mid(hi, lo)


def _sess_high_to(pack: dict, i: int) -> float | None:
    if i < 0:
        return None
    mh = None
    for h in pack["high"][: i + 1]:
        hv = float(h)
        mh = hv if mh is None else max(mh, hv)
    return mh


def _sym(bars: pl.DataFrame) -> str:
    return str(bars["symbol"][0]) if "symbol" in bars.columns else "TEST"


def noon_hold_long(
    bars: pl.DataFrame,
    pack: dict,
    prior_close: float,
    *,
    tight: bool,
    rvol: float | None = None,
    score: float = 1.0,
    tag: str = "noon",
) -> list[Signal]:
    """Noon hold. Features from the completed 11:59 bar. Signal at 12:00 → fill 12:01 open."""
    if pack is None or prior_close is None or float(prior_close) <= 0:
        return []
    pc = float(prior_close)
    i1100 = _idx_at_or_before(pack, MINUTE_1100)
    i1159 = _idx_at_or_before(pack, MINUTE_1159)
    i1200 = _idx_at_or_after(pack, MINUTE_1200)
    if i1100 is None or i1159 is None or i1200 is None:
        return []
    if bar_time(pack["ts"][i1159]) < MINUTE_1159:
        return []
    if bar_time(pack["ts"][i1200]) < MINUTE_1200:
        return []
    ext1100 = float(pack["close"][i1100]) / pc - 1.0
    ext1200 = float(pack["close"][i1159]) / pc - 1.0
    if tight:
        if ext1200 < TIGHT_EXT_1200 - 1e-12:
            return []
        if ext1100 < TIGHT_EXT_1100 - 1e-12:
            return []
        rng = _range_between(pack, MINUTE_1130, MINUTE_1159)
        if rng is None or rng > TIGHT_RANGE + 1e-12:
            return []
        if rvol is None or float(rvol) < TIGHT_RVOL - 1e-12:
            return []
    else:
        if ext1200 < LOOSE_EXT_1200 - 1e-12:
            return []
        if ext1100 < LOOSE_EXT_1100 - 1e-12:
            return []
    stop = _min_low(pack, MINUTE_1100, MINUTE_1159)
    if stop is None:
        return []
    sig = Signal(pack["ts"][i1200], _sym(bars), 1, float(stop), None, float(score), tag)
    return [attach_atr(sig, bars)]


def relaunch_long(
    bars: pl.DataFrame,
    pack: dict,
    prior_close: float,
    *,
    score: float = 1.0,
    tag: str = "relaunch",
) -> list[Signal]:
    """Morning confirmed launch, ≥5% pullback from pre-noon session high, close back above it after 12:00."""
    if pack is None or prior_close is None or float(prior_close) <= 0:
        return []
    rec = confirmed_launch(pack, prior_close)
    if not rec["confirmed"] or rec["launch_close_ts"] is None:
        return []
    if bar_time(rec["launch_close_ts"]) >= MINUTE_1200:
        return []
    h_pre = None
    h_i = None
    for i, (ts, h) in enumerate(zip(pack["ts"], pack["high"])):
        if bar_time(ts) >= MINUTE_1200:
            break
        hv = float(h)
        if h_pre is None or hv > h_pre:
            h_pre = hv
            h_i = i
    if h_pre is None or h_i is None or h_pre <= 0:
        return []
    thresh = h_pre * (1.0 - PULLBACK)
    pb_low = None
    pulled = False
    for i in range(h_i + 1, len(pack["ts"])):
        lv = float(pack["low"][i])
        pb_low = lv if pb_low is None else min(pb_low, lv)
        if pb_low <= thresh + 1e-12:
            pulled = True
        if bar_time(pack["ts"][i]) < MINUTE_1200:
            continue
        if not pulled or pb_low is None:
            continue
        if float(pack["close"][i]) > h_pre + 1e-12:
            sig = Signal(pack["ts"][i], _sym(bars), 1, float(pb_low), None, float(score), tag)
            return [attach_atr(sig, bars)]
    return []


def power_hour_long(
    bars: pl.DataFrame,
    pack: dict,
    prior_close: float,
    *,
    score: float = 1.0,
    tag: str = "power",
) -> list[Signal]:
    """14:30 continuation. Features from completed 14:29 bar. Signal at 14:30 → fill 14:31 open."""
    if pack is None or prior_close is None or float(prior_close) <= 0:
        return []
    i_noon = _idx_at_or_before(pack, MINUTE_1159)
    i_feat = _idx_at_or_before(pack, time(14, 29))
    i_sig = _idx_at_or_after(pack, MINUTE_1430)
    if i_noon is None or i_feat is None or i_sig is None:
        return []
    if bar_time(pack["ts"][i_sig]) < MINUTE_1430:
        return []
    px_noon = float(pack["close"][i_noon])
    px = float(pack["close"][i_feat])
    if px_noon <= 0 or px / px_noon - 1.0 < POWER_EXT - 1e-12:
        return []
    sess_high = _sess_high_to(pack, i_feat)
    if sess_high is None or sess_high <= 0:
        return []
    if px < sess_high * (1.0 - POWER_NEAR_HIGH) - 1e-12:
        return []
    rng = _range_between(pack, MINUTE_1400, time(14, 29))
    if rng is None or rng > POWER_RANGE + 1e-12:
        return []
    stop = _min_low(pack, MINUTE_1330, MINUTE_1430)
    if stop is None:
        return []
    sig = Signal(pack["ts"][i_sig], _sym(bars), 1, float(stop), None, float(score), tag)
    return [attach_atr(sig, bars)]
