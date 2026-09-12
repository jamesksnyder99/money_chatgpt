from __future__ import annotations

from datetime import datetime

import polars as pl

from research.signals import MINUTE_0945, Signal
from research.strategies8 import _t, _tradeable, opening_range
from research.strategies13 import five_min_close_below_ema9


def union_c5_or_orlow(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
) -> list[Signal]:
    """First after 09:45 of: 5-min close < ema9, or 1-min close < 15-min OR low. Shorts only."""
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, lo, _w = rng
    cands: list[Signal] = [
        s for s in five_min_close_below_ema9(bars, stitched, hi) if s.side == -1
    ]
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        if close < lo:
            stop = max(hi, float(rec["high"]))
            cands.append(
                Signal(
                    rec["bar_start"],
                    str(rec["symbol"]),
                    -1,
                    stop,
                    None,
                    lo - close,
                    "union_or_low",
                )
            )
            break
    if not cands:
        return []
    cands.sort(key=lambda s: s.signal_ts)
    return [cands[0]]
