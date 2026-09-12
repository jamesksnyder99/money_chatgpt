from __future__ import annotations

from datetime import time
from statistics import median

import polars as pl

from research.costs import cost_per_share
from research.fills import tradeable_mask
from research.signals import MINUTE_0944, MINUTE_0945, Signal

RTH_OPEN = time(9, 30)
WIDTH_LO = 0.010
WIDTH_HI = 0.040
STOP_MIN_FRAC = 0.004


def _tradeable(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(tradeable_mask(df))


def _t(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(pl.col("bar_start").dt.time().alias("t"))


def _bar_at(df: pl.DataFrame, t: time) -> dict | None:
    hit = df.filter(pl.col("t") == t)
    if hit.height != 1:
        return None
    return hit.row(0, named=True)


def opening_range(bars: pl.DataFrame) -> tuple[float, float, float] | None:
    """09:30–09:44 high/low and width W=(high-low)/mid. None if no range."""
    df = _t(_tradeable(bars))
    opening = df.filter((pl.col("t") >= RTH_OPEN) & (pl.col("t") <= MINUTE_0944))
    if opening.height < 1:
        return None
    hi = float(opening["high"].max())
    lo = float(opening["low"].min())
    mid = (hi + lo) / 2.0
    if mid <= 0:
        return None
    w = (hi - lo) / mid
    return hi, lo, w


def width_ok(w: float) -> bool:
    return WIDTH_LO - 1e-12 <= w <= WIDTH_HI + 1e-12


def orb_wide_signals(bars: pl.DataFrame) -> list[Signal]:
    """First close beyond 09:30–09:44 range after 09:45, only if W in 1%–4%.
    Stop = the other side of the opening range. Silent outside the band.
    """
    rng = opening_range(bars)
    if rng is None:
        return []
    hi, lo, w = rng
    if not width_ok(w):
        return []
    df = _t(_tradeable(bars)).sort("bar_start")
    later = df.filter(pl.col("t") >= MINUTE_0945)
    for rec in later.iter_rows(named=True):
        close = float(rec["close"])
        ts = rec["bar_start"]
        sym = str(rec["symbol"])
        if close > hi:
            return [Signal(ts, sym, 1, lo, None, close - hi, "orb_wide")]
        if close < lo:
            return [Signal(ts, sym, -1, hi, None, lo - close, "orb_wide")]
    return []


def filter_breadth(signals: list[Signal], by_sym: dict[str, pl.DataFrame]) -> list[Signal]:
    """Keep a signal only if its side agrees with sign(median 09:30→signal return)."""
    if not signals:
        return []
    open930: dict[str, float] = {}
    packed: dict[str, dict] = {}
    for sym, sdf in by_sym.items():
        df = _t(_tradeable(sdf))
        b = _bar_at(df, RTH_OPEN)
        if b is None:
            continue
        o = float(b["open"])
        if o <= 0:
            continue
        open930[sym] = o
        packed[sym] = {rec["bar_start"]: float(rec["close"]) for rec in df.iter_rows(named=True)}
    out: list[Signal] = []
    med_cache: dict = {}
    for sig in signals:
        ts = sig.signal_ts
        if ts not in med_cache:
            rets = []
            for sym, o in open930.items():
                c = packed.get(sym, {}).get(ts)
                if c is None:
                    continue
                rets.append(c / o - 1.0)
            med_cache[ts] = median(rets) if rets else None
        med = med_cache[ts]
        if med is None or med == 0.0:
            continue
        if sig.side > 0 and med > 0:
            out.append(sig)
        elif sig.side < 0 and med < 0:
            out.append(sig)
    return out


def cost_gate_ok(entry: float, stop: float) -> bool:
    dist = abs(entry - stop)
    if dist <= 0:
        return False
    rt = cost_per_share(entry) + cost_per_share(stop)
    return rt <= 0.25 * dist + 1e-12


def filter_cost_gate(signals: list[Signal], by_sym: dict[str, pl.DataFrame]) -> list[Signal]:
    """Skip if estimated round-trip cost at the signal close > 0.25R."""
    out: list[Signal] = []
    for sig in signals:
        sdf = by_sym.get(sig.symbol)
        if sdf is None:
            continue
        hit = sdf.filter(pl.col("bar_start") == sig.signal_ts)
        if hit.height != 1:
            continue
        entry = float(hit["close"][0])
        if cost_gate_ok(entry, sig.stop):
            out.append(sig)
    return out


def _structure_stop(entry: float, side: int, structure_px: float) -> float | None:
    """Closer of structure level vs 1% from entry; skip if that stop is < 0.4% of price."""
    if entry <= 0:
        return None
    if side > 0:
        cands = [entry * 0.99]
        if structure_px < entry:
            cands.append(structure_px)
        closer = max(cands)
        if (entry - closer) / entry < STOP_MIN_FRAC - 1e-12:
            return None
        return closer
    cands = [entry * 1.01]
    if structure_px > entry:
        cands.append(structure_px)
    closer = min(cands)
    if (closer - entry) / entry < STOP_MIN_FRAC - 1e-12:
        return None
    return closer


def three_day_hl_signals(
    bars: pl.DataFrame,
    lows: tuple[float | None, float | None, float | None],
    highs: tuple[float | None, float | None, float | None],
    prior_close: float | None,
) -> list[Signal]:
    """Long on three rising prior-morning lows; short on three falling highs. Mixed → silent."""
    l1, l2, l3 = lows
    h1, h2, h3 = highs
    rising = (
        l1 is not None
        and l2 is not None
        and l3 is not None
        and l1 < l2 < l3
    )
    falling = (
        h1 is not None
        and h2 is not None
        and h3 is not None
        and h1 > h2 > h3
    )
    if rising == falling:
        return []
    if prior_close is None:
        return []
    df = _t(_tradeable(bars))
    b = _bar_at(df, RTH_OPEN)
    if b is None:
        return []
    entry = float(b["open"])
    if entry <= 0:
        return []
    ts = b["bar_start"]
    sym = str(b["symbol"])
    if rising:
        if prior_close < l3:
            return []
        stop = _structure_stop(entry, 1, float(l3))
        if stop is None:
            return []
        return [Signal(ts, sym, 1, stop, None, abs(entry - stop), "three_day_hl")]
    if prior_close > h3:
        return []
    stop = _structure_stop(entry, -1, float(h3))
    if stop is None:
        return []
    return [Signal(ts, sym, -1, stop, None, abs(stop - entry), "three_day_hl")]
