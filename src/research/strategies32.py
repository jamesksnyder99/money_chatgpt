from __future__ import annotations

from datetime import datetime

import polars as pl

from research.ema15 import bar_end, ema9_at, ema_stack
from research.signals import MINUTE_0945, Signal, bar_time
from research.strategies13 import resample_5m_ohlc


def conjunction_c5_ema9(
    bars: pl.DataFrame,
    stitched: list[tuple[datetime, float]],
    or_high: float,
) -> tuple[list[Signal], dict]:
    """First 5-min bar after 09:45 where close < EMA9 and EMA9 < EMA21 at the same bar_end.

    One name-day. Does not emit on close-below-EMA9 while the 9/21 regime is still long.
    Ledger: first primitive time, veto reason, first full-conjunction time.
    """
    ledger = {
        "first_primitive_ts": None,
        "first_primitive": None,
        "veto_reason": None,
        "conjunction_ts": None,
    }
    bars5 = resample_5m_ohlc(bars)
    for b in bars5:
        if bar_time(b["start"]) < MINUTE_0945:
            continue
        end = b.get("bar_end") or bar_end(b["start"], 5)
        ema9 = ema9_at(stitched, end)
        stack = ema_stack(stitched, end)
        below = ema9 is not None and b["close"] < ema9
        short = stack == "short"
        if ledger["first_primitive_ts"] is None:
            if below and short:
                ledger["first_primitive_ts"] = end
                ledger["first_primitive"] = "both"
            elif below:
                ledger["first_primitive_ts"] = end
                ledger["first_primitive"] = "close_below_ema9"
                ledger["veto_reason"] = "regime_not_short" if stack != "short" else None
            elif short:
                ledger["first_primitive_ts"] = end
                ledger["first_primitive"] = "ema9_lt_ema21"
                ledger["veto_reason"] = "close_not_below_ema9"
        if below and short:
            ledger["conjunction_ts"] = end
            stop = max(or_high, b["high"])
            sig = Signal(
                end,
                b["symbol"],
                -1,
                stop,
                None,
                ema9 - b["close"],
                "c5_conj",
            )
            return [sig], ledger
    return [], ledger
