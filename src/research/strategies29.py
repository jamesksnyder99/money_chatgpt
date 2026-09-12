from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from research.harness import LAUNCH_REL_MIN, attach_atr, confirmed_launch, run_rel_vol_at
from research.signals import MINUTE_0945, MINUTE_1159, MINUTE_1330, MINUTE_1559, Signal, bar_time
from research.strategies25 import FLUSH_UNDERCUT, flush_ring_long

CELL_REL_MIN = 3.0
FLUSH_MAX = 0.06


def forward_ext(px: float | None, origin: float | None) -> float | None:
    """Extension vs an origin close (09:44), not vs prior close."""
    if px is None or origin is None or float(origin) <= 0:
        return None
    return float(px) / float(origin) - 1.0


def fly_or_dv_ok(orw: float | None, dv0929: float | None) -> bool:
    """A24 cell without the ext_0944 cut (id 6 population)."""
    if orw is None or dv0929 is None:
        return False
    return float(orw) >= 0.051 - 1e-12 and float(dv0929) >= 98_000.0 - 1e-9


def cell_buy_gate(*, median_ext_1159: float | None, frac_1atr_before_or: float | None) -> bool:
    """Develop FLY $5–20: median ext from 09:44 to 11:59 > 0 and +1 ATR before OR-low ≥ 0.35."""
    if median_ext_1159 is None or frac_1atr_before_or is None:
        return False
    return float(median_ext_1159) > 0.0 and float(frac_1atr_before_or) >= 0.35 - 1e-12


def cell_buy_long(
    bars: pl.DataFrame,
    *,
    signal_ts: datetime | None,
    or_low: float | None,
    rel0944: float | None,
    gate: bool,
    tag: str = "cell0945",
) -> list[Signal]:
    """09:45-open long. Silent when the Part A gate is down."""
    if not gate:
        return []
    if bars is None or bars.height == 0:
        return []
    if signal_ts is None or or_low is None:
        return []
    if rel0944 is None or float(rel0944) < CELL_REL_MIN - 1e-12:
        return []
    sig = Signal(
        signal_ts,
        str(bars["symbol"][0]),
        1,
        float(or_low),
        None,
        float(rel0944),
        tag,
    )
    return [attach_atr(sig, bars)]


def flush_vs_anchor(
    bars: pl.DataFrame,
    anchor_px: float | None,
    *,
    tag: str = "flush_anchor",
) -> list[Signal]:
    """Flush of an RTH anchor (09:44 close or OR high). Never reads 08:00 last_px."""
    return flush_ring_long(
        bars,
        anchor_px,
        min_undercut=FLUSH_UNDERCUT,
        max_undercut=FLUSH_MAX,
        flush_after=MINUTE_0945,
        tag=tag,
    )


def prior_15m_low(bars: pl.DataFrame, ts: datetime) -> float | None:
    """Low of the last completed 15-min bar strictly before ts."""
    if bars is None or bars.height == 0:
        return None
    minute = ts.minute - (ts.minute % 15)
    start = ts.replace(minute=minute, second=0, microsecond=0)
    prev = start - timedelta(minutes=15)
    lo = None
    for rec in bars.sort("bar_start").iter_rows(named=True):
        bt = rec["bar_start"]
        if bt < prev:
            continue
        if bt >= start:
            break
        v = rec["low"]
        if v is None:
            continue
        lo = float(v) if lo is None else min(lo, float(v))
    return lo


def launch_compatible_long(
    bars: pl.DataFrame,
    pack: dict | None,
    prior_close: float,
    *,
    ext_0929: float | None,
    orw: float | None,
    dv0929: float | None,
    cumdv: list[float],
    prior_cum: list[list[float]],
) -> list[Signal]:
    """Confirmed launch after 09:45; stop = max(prior 15-min low, ATR via harness)."""
    if not fly_or_dv_ok(orw, dv0929):
        return []
    if ext_0929 is None or not (-0.03 - 1e-12 <= float(ext_0929) <= 0.05 + 1e-12):
        return []
    rec = confirmed_launch(pack, prior_close)
    if not rec["confirmed"] or rec["confirm_ts"] is None:
        return []
    if bar_time(rec["confirm_ts"]) < MINUTE_0945:
        return []
    rel = run_rel_vol_at(cumdv, rec["confirm_ts"], prior_cum)
    if rel is None or rel < LAUNCH_REL_MIN - 1e-12:
        return []
    struct = prior_15m_low(bars, rec["confirm_ts"])
    if struct is None:
        struct = rec["confirm_low"]
    if struct is None:
        return []
    sig = Signal(
        rec["confirm_ts"],
        str(bars["symbol"][0]),
        1,
        float(struct),
        None,
        float(rel),
        "launch_compat",
    )
    return [attach_atr(sig, bars)]


def path_from_0944(
    pack: dict,
    *,
    px44: float,
    or_low: float | None,
    atr: float,
    i44: int,
) -> dict:
    """Forward path from 09:44 close. Ext/MAE/1ATR-before-OR-low do not use prior close."""
    times, highs, lows, closes = pack["ts"], pack["high"], pack["low"], pack["close"]
    px1159 = px1330 = px1559 = None
    tagged_or = False
    hit_1atr_before_or = False
    min_low = float(px44)
    atr_v = float(atr or 0.0)
    need = float(px44) + atr_v if atr_v > 0 else None
    for i in range(i44 + 1, len(times)):
        t = bar_time(times[i])
        h, l, c = float(highs[i]), float(lows[i]), float(closes[i])
        if t <= MINUTE_1159:
            min_low = min(min_low, l)
            if or_low is not None and l <= float(or_low) + 1e-12:
                tagged_or = True
            if need is not None and h >= need - 1e-12 and not tagged_or:
                hit_1atr_before_or = True
            px1159 = c
        if t <= MINUTE_1330:
            px1330 = c
        if t <= MINUTE_1559:
            px1559 = c
    mae = (float(px44) - min_low) / atr_v if atr_v > 1e-12 else None
    return {
        "px1159": px1159,
        "px1330": px1330,
        "px1559": px1559,
        "ext1159_44": forward_ext(px1159, px44),
        "ext1330_44": forward_ext(px1330, px44),
        "ext1559_44": forward_ext(px1559, px44),
        "mae_atr_1159": mae,
        "tagged_or_low": tagged_or,
        "hit_1atr_before_or": hit_1atr_before_or,
    }
