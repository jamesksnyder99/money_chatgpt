from __future__ import annotations

import polars as pl

from research.signals import Signal
from research.strategies8 import STOP_MIN_FRAC, _bar_at, _t, _tradeable, RTH_OPEN


def gap_continuation_signals(
    bars: pl.DataFrame, prior_close: float | None, min_abs_gap: float = 0.02
) -> list[Signal]:
    """09:31 continuation with the gap (does not fade). Stop = 09:30 low/high if ≥ 0.4%."""
    if prior_close is None or prior_close <= 0:
        return []
    df = _t(_tradeable(bars))
    b = _bar_at(df, RTH_OPEN)
    if b is None:
        return []
    o = float(b["open"])
    if o <= 0:
        return []
    gap = o / float(prior_close) - 1.0
    if abs(gap) < min_abs_gap - 1e-12:
        return []
    if gap > 0:
        side, stop = 1, float(b["low"])
    elif gap < 0:
        side, stop = -1, float(b["high"])
    else:
        return []
    px = float(b["close"]) if float(b["close"]) > 0 else o
    dist = abs(px - stop)
    if px <= 0 or dist / px < STOP_MIN_FRAC - 1e-12:
        return []
    if side > 0 and stop >= px:
        return []
    if side < 0 and stop <= px:
        return []
    return [
        Signal(b["bar_start"], str(b["symbol"]), side, stop, None, abs(gap), "gap_cont")
    ]


def orb_matches_gap(
    bars: pl.DataFrame, prior_close: float | None, side: int, min_abs_gap: float = 0.01
) -> bool:
    """True iff |gap| ≥ min and break side matches gap sign."""
    if prior_close is None or prior_close <= 0:
        return False
    df = _t(_tradeable(bars))
    b = _bar_at(df, RTH_OPEN)
    if b is None:
        return False
    o = float(b["open"])
    if o <= 0:
        return False
    gap = o / float(prior_close) - 1.0
    if abs(gap) < min_abs_gap - 1e-12:
        return False
    if gap > 0:
        return side > 0
    if gap < 0:
        return side < 0
    return False
