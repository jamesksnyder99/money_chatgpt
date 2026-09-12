"""Arrow 38 — premarket-high reclaim after the open wash."""

from __future__ import annotations

from datetime import timedelta

import polars as pl

from research.harness import attach_atr, confirmed_launch
from research.signals import MINUTE_0929, MINUTE_1000, RTH_OPEN, Signal, bar_time

DIP_CTRL = 0.03
DIP_LOOSE = 0.02
LOOKBACK_MIN = 30
RVOL_SENS = 3.0


def _sym(bars: pl.DataFrame) -> str:
    return str(bars["symbol"][0]) if "symbol" in bars.columns else "TEST"


def premarket_high(pack: dict) -> float | None:
    """Max high on 04:00–09:29 one-minute bars."""
    mh = None
    for ts, h in zip(pack["ts"], pack["high"]):
        t = bar_time(ts)
        if t > MINUTE_0929:
            break
        hv = float(h)
        mh = hv if mh is None else max(mh, hv)
    return mh


def rth_open_px(pack: dict) -> float | None:
    for ts, o in zip(pack["ts"], pack["open"]):
        if bar_time(ts) >= RTH_OPEN:
            return float(o)
    return None


def _min_low_by_1000(pack: dict) -> float | None:
    """Min low from 09:30 through 09:59 (by 10:00)."""
    lo = None
    for ts, l in zip(pack["ts"], pack["low"]):
        t = bar_time(ts)
        if t < RTH_OPEN:
            continue
        if t >= MINUTE_1000:
            break
        lv = float(l)
        lo = lv if lo is None else min(lo, lv)
    return lo


def lookback_low(pack: dict, stamp, minutes: int = LOOKBACK_MIN) -> float | None:
    floor = stamp - timedelta(minutes=minutes)
    lo = None
    for ts, l in zip(pack["ts"], pack["low"]):
        if ts < floor:
            continue
        if ts >= stamp:
            break
        lv = float(l)
        lo = lv if lo is None else min(lo, lv)
    return lo


def pm_reclaim_long(
    bars: pl.DataFrame,
    pack: dict,
    prior_close: float,
    *,
    dip_frac: float = DIP_CTRL,
    rvol: float | None = None,
    rvol_min: float | None = None,
    score: float = 1.0,
    tag: str = "pm_reclaim",
) -> list[Signal]:
    """Premarket confirmed launch, open under pm high, wash by 10:00, then 1-min close above pm high after 10:00.

    Silent if the wash never prints. Silent if only an RTH high (not the premarket high) is reclaimed.
    """
    if pack is None or prior_close is None or float(prior_close) <= 0:
        return []
    rec = confirmed_launch(pack, prior_close)
    if not rec["confirmed"] or rec["launch_close_ts"] is None:
        return []
    if bar_time(rec["launch_close_ts"]) >= RTH_OPEN:
        return []
    pm_h = premarket_high(pack)
    if pm_h is None or pm_h <= 0:
        return []
    o930 = rth_open_px(pack)
    if o930 is None or o930 >= pm_h - 1e-12:
        return []
    wash = _min_low_by_1000(pack)
    if wash is None:
        return []
    if wash > o930 * (1.0 - float(dip_frac)) + 1e-12:
        return []
    if rvol_min is not None:
        if rvol is None or float(rvol) < float(rvol_min) - 1e-12:
            return []
    for ts, c in zip(pack["ts"], pack["close"]):
        if bar_time(ts) < MINUTE_1000:
            continue
        if float(c) > pm_h + 1e-12:
            stop = lookback_low(pack, ts)
            if stop is None:
                stop = wash
            sig = Signal(ts, _sym(bars), 1, float(stop), None, float(score), tag)
            return [attach_atr(sig, bars)]
    return []
