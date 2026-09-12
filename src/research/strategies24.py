from __future__ import annotations

from datetime import time

import polars as pl

from research.fills import is_tradeable
from research.harness import (
    CLUSTER_CAP,
    LAUNCH_REL_MIN,
    VOLFIRST_REL_MIN,
    attach_atr,
    confirmed_launch,
    run_rel_vol_at,
)
from research.signals import (
    MINUTE_0935,
    MINUTE_0945,
    MINUTE_1100,
    MINUTE_1159,
    MINUTE_1300,
    MINUTE_1559,
    RTH_OPEN,
    Signal,
    bar_time,
)
from research.strategies15 import is_weak_close, resample_5m
from research.strategies23 import afternoon_break_long, flush_higher_low_long, session_high_before

DOORS = ("launch", "volfirst", "flush", "giveback")
EXITS = ("flat1159", "flat1559", "t15R", "half1R_trail", "atr_1559")
FILTERS = ("base", "cost", "px5", "cap3", "nocluster")
GRID_IDS = tuple(f"{d}|{e}|{f}" for d in DOORS for e in EXITS for f in FILTERS)

EXIT_FLAT = {
    "flat1159": MINUTE_1159,
    "flat1559": MINUTE_1559,
    "t15R": MINUTE_1559,
    "half1R_trail": MINUTE_1559,
    "atr_1559": MINUTE_1559,
}


def grid_ids() -> tuple[str, ...]:
    return GRID_IDS


def door_side(door: str) -> int:
    return -1 if door == "giveback" else 1


def launch_long(
    bars: pl.DataFrame,
    pack: dict,
    prior_close: float,
    ext_0929: float | None,
    cumdv: list[float],
    prior_cum: list[list[float]],
    *,
    score_rel: float | None = None,
) -> list[Signal]:
    """After 09:45, confirmed launch, run_rel_vol at launch >= 5, ext_0929 in [-3%, +5%]."""
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
    stop = rec["confirm_low"]
    close_px = rec["launch_close"]
    if stop is None or close_px is None:
        return []
    sig = Signal(
        rec["confirm_ts"],
        str(bars["symbol"][0]),
        1,
        float(stop),
        None,
        float(score_rel if score_rel is not None else rel),
        "launch",
    )
    return [attach_atr(sig, bars)]


def volfirst_long(
    bars: pl.DataFrame,
    prior_close: float,
    cumdv: list[float],
    prior_cum: list[list[float]],
) -> list[Signal]:
    """After 09:35, first 5-min where run_rel_vol >= 8 and bar closes up, ext in [-2%, +5%]."""
    if prior_close is None or prior_close <= 0:
        return []
    for b in resample_5m(bars):
        if bar_time(b["start"]) < MINUTE_0935:
            continue
        if b["close"] <= b["open"] + 1e-12:
            continue
        ext = b["close"] / float(prior_close) - 1.0
        if not (-0.02 - 1e-12 <= ext <= 0.05 + 1e-12):
            continue
        rel = run_rel_vol_at(cumdv, b["last_ts"], prior_cum)
        if rel is None or rel < VOLFIRST_REL_MIN - 1e-12:
            continue
        sig = Signal(
            b["last_ts"],
            b["symbol"],
            1,
            float(b["low"]),
            None,
            float(rel),
            "volfirst",
        )
        return [attach_atr(sig, bars)]
    return []


def flush_long(bars: pl.DataFrame, last_px_0800: float | None, score: float) -> list[Signal]:
    sigs = flush_higher_low_long(bars, last_px_0800)
    out = []
    for s in sigs:
        scored = Signal(
            s.signal_ts,
            s.symbol,
            s.side,
            s.stop,
            s.target,
            float(score),
            s.tag,
        )
        out.append(attach_atr(scored, bars))
    return out


def am_high_pm_long(bars: pl.DataFrame, score: float) -> list[Signal]:
    am_high = session_high_before(bars, MINUTE_1100)
    sigs = afternoon_break_long(bars, am_high)
    out = []
    for s in sigs:
        scored = Signal(
            s.signal_ts,
            s.symbol,
            s.side,
            s.stop,
            s.target,
            float(score),
            s.tag,
        )
        out.append(attach_atr(scored, bars))
    return out


def _vwap_from(bars: pl.DataFrame, start: time) -> dict:
    df = bars.sort("bar_start")
    times = df["bar_start"].to_list()
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    opens = df["open"].to_list()
    cpv = 0.0
    cv = 0.0
    last = float("nan")
    out = {}
    for i, ts in enumerate(times):
        if bar_time(ts) < start:
            continue
        if not is_tradeable(opens[i], closes[i], vols[i]):
            out[ts] = last
            continue
        typical = (float(highs[i]) + float(lows[i]) + float(closes[i])) / 3.0
        v = float(vols[i])
        cpv += typical * v
        cv += v
        if cv > 0:
            last = cpv / cv
        out[ts] = last
    return out


def giveback_short(bars: pl.DataFrame, pack: dict, prior_close: float, score: float) -> list[Signal]:
    """ext>=15% at 11:00, by 13:00 >=5% off session high, after 13:00 5-min close below 11:00 VWAP, weak."""
    if pack is None or prior_close is None or prior_close <= 0 or bars is None:
        return []
    times, highs, closes = pack["ts"], pack["high"], pack["close"]
    hi11 = None
    px11 = None
    hi13 = None
    px13 = None
    for ts, h, c in zip(times, highs, closes):
        t = bar_time(ts)
        if t <= MINUTE_1100:
            hi11 = h if hi11 is None else max(hi11, h)
            px11 = c
        if t <= MINUTE_1300:
            hi13 = h if hi13 is None else max(hi13, h)
            px13 = c
    if hi11 is None or px13 is None or hi13 is None:
        return []
    if hi11 / float(prior_close) - 1.0 < 0.15 - 1e-12:
        return []
    if hi13 <= 0 or (hi13 - px13) / hi13 < 0.05 - 1e-12:
        return []
    vw = _vwap_from(bars, MINUTE_1100)
    for b in resample_5m(bars):
        if bar_time(b["start"]) < MINUTE_1300:
            continue
        v = vw.get(b["last_ts"])
        if v is None or v != v:
            continue
        if b["close"] >= float(v) - 1e-12:
            continue
        if not is_weak_close(b["open"], b["high"], b["low"], b["close"]):
            continue
        sig = Signal(
            b["last_ts"],
            b["symbol"],
            -1,
            float(b["high"]),
            None,
            float(score),
            "giveback",
        )
        return [attach_atr(sig, bars)]
    return []


def exit_kwargs(exit_id: str) -> dict:
    flatten = EXIT_FLAT[exit_id]
    kw: dict = {"flatten_at": flatten, "harness_stop": True}
    if exit_id == "t15R":
        kw["take_r"] = 1.5
    elif exit_id == "half1R_trail":
        kw["scale_half_at_1r"] = True
        kw["atr_trail"] = True
    elif exit_id == "atr_1559":
        kw["use_structure_stop"] = False
    return kw


def filter_kwargs(filt: str, n_raw: int) -> dict | None:
    """Replay kwargs for a filter. None means skip the session (nocluster)."""
    if filt == "nocluster" and n_raw > CLUSTER_CAP:
        return None
    cap = {
        "max_positions": 8,
        "max_entries": 16,
        "max_risk_outstanding": 1600.0,
        "min_stop_frac": 0.004,
    }
    if filt == "cap3":
        cap["max_positions"] = 3
        cap["max_risk_outstanding"] = 600.0
    cap["cost_gate"] = filt == "cost"
    return cap
