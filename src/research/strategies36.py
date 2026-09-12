"""Arrow 36 — ungated regular-trading-hours confirmed-launch birth (one-minute)."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import polars as pl

from research.harness import attach_atr, confirmed_launch
from research.signals import Signal, bar_time

WIN_AM = (time(9, 45), time(11, 59))
WIN_EARLY = (time(9, 45), time(10, 29))
WIN_LATE = (time(10, 30), time(11, 59))
WIN_PM = (time(12, 0), time(15, 0))
LOOKBACK_MIN = 15


def in_launch_window(ts: datetime | None, win: tuple[time, time]) -> bool:
    if ts is None:
        return False
    clock = bar_time(ts)
    return win[0] <= clock <= win[1]


def lookback_low(pack: dict, launch_ts: datetime, minutes: int = LOOKBACK_MIN) -> float | None:
    """Low of the one-minute bars in the `minutes` before launch_close (launch bar excluded)."""
    floor = launch_ts - timedelta(minutes=minutes)
    lo = None
    for ts, l in zip(pack["ts"], pack["low"]):
        if ts < floor:
            continue
        if ts >= launch_ts:
            break
        lv = float(l)
        lo = lv if lo is None else min(lo, lv)
    return lo


def rth_birth_long(
    bars: pl.DataFrame,
    pack: dict,
    prior_close: float,
    win: tuple[time, time],
    *,
    score: float = 1.0,
    tag: str = "birth",
) -> list[Signal]:
    """Long-only: confirmed 1-min launch whose launch close sits in `win`.

    Signal at confirm_ts (launch close is already complete). Fill = next 1-min open.
    Stop structure = 15-minute lookback low before launch. No 5-min close wait.
    """
    if pack is None or prior_close is None or float(prior_close) <= 0:
        return []
    rec = confirmed_launch(pack, prior_close)
    if not rec["confirmed"] or rec["launch_close_ts"] is None or rec["confirm_ts"] is None:
        return []
    if not in_launch_window(rec["launch_close_ts"], win):
        return []
    if bar_time(rec["confirm_ts"]) < win[0]:
        return []
    struct = lookback_low(pack, rec["launch_close_ts"])
    if struct is None:
        struct = rec["confirm_low"]
    if struct is None:
        return []
    sym = str(bars["symbol"][0]) if "symbol" in bars.columns else "TEST"
    sig = Signal(
        rec["confirm_ts"],
        sym,
        1,
        float(struct),
        None,
        float(score),
        tag,
    )
    return [attach_atr(sig, bars)]
