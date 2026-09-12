from __future__ import annotations

from datetime import time

import polars as pl

from research.harness import attach_atr
from research.signals import MINUTE_0945, RTH_OPEN, Signal, bar_time
from research.strategies15 import candle_anatomy, resample_5m
from research.strategies23 import _long_ok

FLUSH_UNDERCUT = 0.02
FLY_ORW_MIN = 0.051
FLY_DV0929_MIN = 98_000.0
FLY_EXT0944_MIN = 0.034
FLY_AVAILABLE_AT = MINUTE_0945
PX5 = 5.0


def fly_cell_ok(orw: float | None, dv0929: float | None, ext0944: float | None) -> bool:
    """Arrow 24 develop-locked FLY cell. Holdout did not pick these cuts."""
    if orw is None or dv0929 is None or ext0944 is None:
        return False
    return (
        float(orw) >= FLY_ORW_MIN - 1e-12
        and float(dv0929) >= FLY_DV0929_MIN - 1e-9
        and float(ext0944) >= FLY_EXT0944_MIN - 1e-12
    )


def _bar_rng(b: dict) -> float:
    return float(b["high"]) - float(b["low"])


def _ring_filters_ok(
    b: dict,
    *,
    flush_low_bar: dict | None,
    flush_low_prev: dict | None,
    first_tag_start,
    range_accel: float | None,
    decel_hl: float | None,
    vol_accel: float | None,
    slow_wash_min: float | None,
    flush_low_after: time | None,
) -> bool:
    """Arrow 26 accel/decel cuts. Default-off kwargs keep the Arrow 25 path."""
    if range_accel is not None:
        if flush_low_bar is None or flush_low_prev is None:
            return False
        prev_rng = _bar_rng(flush_low_prev)
        if prev_rng <= 1e-12:
            return False
        if _bar_rng(flush_low_bar) < range_accel * prev_rng - 1e-12:
            return False
    if decel_hl is not None:
        if flush_low_bar is None:
            return False
        flush_rng = _bar_rng(flush_low_bar)
        if flush_rng <= 1e-12:
            return False
        if _bar_rng(b) > decel_hl * flush_rng + 1e-12:
            return False
    if vol_accel is not None:
        if flush_low_bar is None:
            return False
        fv = float(flush_low_bar.get("volume") or 0.0)
        sv = float(b.get("volume") or 0.0)
        if fv <= 1e-12:
            return False
        if sv < vol_accel * fv - 1e-12:
            return False
    if slow_wash_min is not None:
        if first_tag_start is None or flush_low_bar is None:
            return False
        minutes = (flush_low_bar["start"] - first_tag_start).total_seconds() / 60.0
        if minutes < float(slow_wash_min) - 1e-12:
            return False
    if flush_low_after is not None:
        if flush_low_bar is None or bar_time(flush_low_bar["start"]) < flush_low_after:
            return False
    return True


def flush_ring_long(
    bars: pl.DataFrame,
    last_px_0800: float | None,
    *,
    min_undercut: float = FLUSH_UNDERCUT,
    max_undercut: float | None = None,
    min_close_loc: float = 0.75,
    reclaim_0800: bool = False,
    flush_after: time | None = None,
    range_accel: float | None = None,
    decel_hl: float | None = None,
    vol_accel: float | None = None,
    slow_wash_min: float | None = None,
    two_hls: bool = False,
    flush_low_after: time | None = None,
    signal_after: time | None = None,
    tag: str = "flush_ring",
) -> list[Signal]:
    """Flush then higher-low. Optional depth, reclaim, clock, and accel/decel cuts.

    C-R1: an undercut before `flush_after` is ignored; do not return [].
    A1: `signal_after` (FLY cell available_at=09:45) skips HLs whose last_ts is earlier
    and waits for the next qualifying higher-low.
    """
    if last_px_0800 is None or last_px_0800 <= 0:
        return []
    px = float(last_px_0800)
    thresh = px * (1.0 - min_undercut)
    floor = px * (1.0 - max_undercut) if max_undercut is not None else None
    bars5 = resample_5m(bars)
    flushed = False
    flush_low = None
    flush_low_bar = None
    flush_low_prev = None
    first_tag_start = None
    hl_count = 0
    prev = None
    for b in bars5:
        if bar_time(b["start"]) < RTH_OPEN:
            prev = b
            continue
        already = flushed
        if b["low"] <= thresh + 1e-12:
            if not flushed:
                if flush_after is not None and bar_time(b["start"]) < flush_after:
                    prev = b
                    continue
                flushed = True
                flush_low = b["low"]
                flush_low_bar = b
                flush_low_prev = prev
                first_tag_start = b["start"]
            else:
                new_low = b["low"] < flush_low - 1e-12
                flush_low = min(flush_low, b["low"])
                if new_low:
                    flush_low_bar = b
                    flush_low_prev = prev
                    if two_hls:
                        hl_count = 0
        if floor is not None and flush_low is not None and flush_low < floor - 1e-12:
            return []
        is_hl = (
            already
            and flushed
            and flush_low is not None
            and prev is not None
            and bar_time(prev["start"]) >= RTH_OPEN
            and b["low"] > prev["low"] + 1e-12
        )
        if is_hl:
            hl_count += 1
        if is_hl and (not two_hls or hl_count >= 2):
            a = candle_anatomy(b["open"], b["high"], b["low"], b["close"])
            if a is None or a["close_loc"] < min_close_loc - 1e-12:
                prev = b
                continue
            if reclaim_0800 and b["close"] < px - 1e-12:
                prev = b
                continue
            if not _ring_filters_ok(
                b,
                flush_low_bar=flush_low_bar,
                flush_low_prev=flush_low_prev,
                first_tag_start=first_tag_start,
                range_accel=range_accel,
                decel_hl=decel_hl,
                vol_accel=vol_accel,
                slow_wash_min=slow_wash_min,
                flush_low_after=flush_low_after,
            ):
                prev = b
                continue
            stop = float(flush_low)
            if _long_ok(b["close"], stop):
                sig_ts = b["last_ts"]
                if signal_after is not None and bar_time(sig_ts) < signal_after:
                    prev = b
                    continue
                sig = Signal(
                    sig_ts,
                    b["symbol"],
                    1,
                    stop,
                    None,
                    b["close"] - stop,
                    tag,
                )
                return [attach_atr(sig, bars)]
        prev = b
    return []


def score_flush(sig: Signal, score: float) -> Signal:
    return Signal(
        signal_ts=sig.signal_ts,
        symbol=sig.symbol,
        side=sig.side,
        stop=sig.stop,
        target=sig.target,
        score=float(score),
        tag=sig.tag,
        stop_from_entry=sig.stop_from_entry,
        overnight=sig.overnight,
        atr=sig.atr,
    )
