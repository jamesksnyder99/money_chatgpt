from __future__ import annotations

import polars as pl

from research.signals import MINUTE_0944
from research.strategies8 import _bar_at, _t, _tradeable, opening_range


def bearish_or(bars: pl.DataFrame) -> bool:
    """True iff the 09:44 close is in the lower half of the 09:30–09:44 range."""
    rng = opening_range(bars)
    if rng is None:
        return False
    hi, lo, _w = rng
    mid = (hi + lo) / 2.0
    df = _t(_tradeable(bars))
    b = _bar_at(df, MINUTE_0944)
    if b is None:
        return False
    return float(b["close"]) <= mid
