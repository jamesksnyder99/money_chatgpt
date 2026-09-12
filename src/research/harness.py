from __future__ import annotations

import math
import statistics
from datetime import datetime, time

import polars as pl

from research.costs import cost_per_share
from research.fills import is_tradeable
from research.signals import RTH_OPEN, Signal, bar_time
from research.strategies15 import resample_5m

N_MINUTES = 720  # 04:00-15:59
CLOCK_OPEN = time(4, 0)
CONFIRM_CLOSE = 1.10
CONFIRM_HOLD = 1.08
STOP_FLOOR_FRAC = 0.006
COST_GATE_FRAC = 0.20
ATR_BARS = 6
PRICE_FLOOR = 3.0
PRICE_FLOOR_PX5 = 5.0
CLUSTER_CAP = 15
LAUNCH_REL_MIN = 5.0
VOLFIRST_REL_MIN = 8.0


def minute_idx(ts: datetime | time) -> int:
    t = bar_time(ts) if isinstance(ts, datetime) else ts
    return t.hour * 60 + t.minute - (4 * 60)


def cum_dv_array(pack: dict) -> list[float]:
    """Forward-filled typical*vol from 04:00 through each minute."""
    out = [0.0] * N_MINUTES
    run = 0.0
    last_i = -1
    times = pack["ts"]
    for i, ts in enumerate(times):
        idx = minute_idx(ts)
        if idx < 0 or idx >= N_MINUTES:
            continue
        h, l, c, v = pack["high"][i], pack["low"][i], pack["close"][i], pack["vol"][i]
        run += (h + l + c) / 3.0 * v
        if last_i >= 0:
            for j in range(last_i + 1, idx):
                out[j] = out[last_i]
        out[idx] = run
        last_i = idx
    if last_i >= 0:
        for j in range(last_i + 1, N_MINUTES):
            out[j] = out[last_i]
    return out


def _median_prior(prior_vols: list[float], *, min_n: int = 5, lookback: int = 10) -> float | None:
    if len(prior_vols) < min_n:
        return None
    use = [float(v) for v in prior_vols[-lookback:]]
    if len(use) < min_n:
        return None
    med = float(statistics.median(use))
    if med <= 0:
        return None
    return med


def calendar_prior_dvs(
    values_by_iso: dict[str, float],
    session_iso: str,
    calendar: list[str],
    *,
    lookback: int = 10,
) -> dict:
    """A6: last `lookback` exchange sessions before session_iso.

    Present name-days contribute their value (explicit zero stays zero).
    Missing name-days are not silently dropped from the window; they are
    counted as missing and excluded from the median.
    """
    prev = [s for s in calendar if s < session_iso][-lookback:]
    values: list[float] = []
    n_zero = 0
    n_missing = 0
    for iso in prev:
        if iso in values_by_iso:
            v = float(values_by_iso[iso])
            values.append(v)
            if v <= 1e-12:
                n_zero += 1
        else:
            n_missing += 1
    return {
        "values": values,
        "n_window": len(prev),
        "n_present": len(values),
        "n_zero": n_zero,
        "n_missing": n_missing,
        "calendar_enforced": True,
    }


def run_rel_vol(cum_dv_now: float | None, prior_window_dvs: list[float]) -> float | None:
    """Today's 04:00→stamp dollar volume / median of prior 10 same windows.

    Pass calendar-assembled values (zeros included, missings omitted) from
    calendar_prior_dvs so the window is last ten exchange sessions, not last
    ten retained rows.
    """
    if cum_dv_now is None:
        return None
    med = _median_prior(prior_window_dvs)
    if med is None:
        return None
    return float(cum_dv_now) / med


def run_rel_vol_at(cumdv: list[float], ts: datetime, prior_arrays: list[list[float]]) -> float | None:
    idx = minute_idx(ts)
    if idx < 0 or idx >= N_MINUTES:
        return None
    today = cumdv[idx] if idx < len(cumdv) else 0.0
    priors = []
    for arr in prior_arrays:
        if arr and idx < len(arr):
            priors.append(arr[idx])
    return run_rel_vol(today, priors)


def confirmed_launch(pack: dict, prior_close: float) -> dict:
    """First 1-min close >= 1.10*pc whose next tradeable bar low >= 1.08*pc.

    confirm_ts is the next-bar timestamp (confirmation known at that bar).
    launch_close_ts is the close that tagged +10%.
    """
    out = {
        "confirmed": False,
        "confirm_ts": None,
        "launch_close_ts": None,
        "confirm_low": None,
        "launch_close": None,
    }
    if pack is None or prior_close is None or prior_close <= 0:
        return out
    thresh = CONFIRM_CLOSE * float(prior_close)
    hold = CONFIRM_HOLD * float(prior_close)
    times, closes, lows = pack["ts"], pack["close"], pack["low"]
    pending = None
    for i in range(len(times)):
        if pending is not None:
            if float(lows[i]) >= hold - 1e-12:
                out["confirmed"] = True
                out["confirm_ts"] = times[i]
                out["launch_close_ts"] = times[pending]
                out["confirm_low"] = float(lows[i])
                out["launch_close"] = float(closes[pending])
                return out
            pending = None
        if pending is None and float(closes[i]) >= thresh - 1e-12:
            pending = i
    return out


def atr_last6_5m(bars: pl.DataFrame, asof: datetime) -> float:
    """Mean true range of last six completed 5-min bars with last_ts <= asof."""
    bars5 = resample_5m(bars)
    done = [b for b in bars5 if b["last_ts"] <= asof]
    if not done:
        return 0.0
    use = done[-ATR_BARS:]
    trs = []
    prev_c = None
    # need prev close from the bar before `use` when possible
    start = max(0, len(done) - ATR_BARS - 1)
    window = done[start:]
    for b in window:
        h, l, c = b["high"], b["low"], b["close"]
        if prev_c is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        prev_c = c
        trs.append(tr)
    trs = trs[-ATR_BARS:]
    if not trs:
        return 0.0
    return float(sum(trs) / len(trs))


def harness_stop_distance(
    px: float,
    structure_stop: float | None,
    atr: float,
    side: int,
    *,
    use_structure: bool = True,
) -> float:
    """max(structure, 1.0*ATR, 0.6% of price)."""
    if px is None or px <= 0:
        return 0.0
    floor = STOP_FLOOR_FRAC * float(px)
    atr_v = max(0.0, float(atr or 0.0))
    struct = 0.0
    if use_structure and structure_stop is not None:
        struct = abs(float(px) - float(structure_stop))
    return max(struct, atr_v, floor)


def harness_stop_px(
    px: float,
    structure_stop: float | None,
    atr: float,
    side: int,
    *,
    use_structure: bool = True,
) -> tuple[float, float]:
    dist = harness_stop_distance(px, structure_stop, atr, side, use_structure=use_structure)
    stop = float(px) - int(side) * dist
    return stop, dist


def cost_gate_blocks(entry_px: float, stop_distance: float) -> bool:
    """True iff 2 * cost_per_share(entry) > 0.20 * stop_distance."""
    if entry_px is None or stop_distance is None or stop_distance <= 0:
        return True
    return 2.0 * cost_per_share(float(entry_px)) > COST_GATE_FRAC * float(stop_distance) + 1e-12


def halt_windows(bars: pl.DataFrame) -> list[tuple[datetime, datetime]]:
    """RTH: >=5 consecutive zero-volume minutes after >=15 minutes with prints."""
    if bars is None or bars.height == 0:
        return []
    df = bars.sort("bar_start")
    times = df["bar_start"].to_list()
    vols = df["volume"].to_list()
    prints = 0
    dead_start = None
    dead_n = 0
    out: list[tuple[datetime, datetime]] = []
    for ts, v in zip(times, vols):
        if bar_time(ts) < RTH_OPEN:
            continue
        vol = float(v or 0.0)
        if vol > 0:
            if dead_n >= 5 and dead_start is not None and prints >= 15:
                out.append((dead_start, ts))
            dead_start = None
            dead_n = 0
            prints += 1
            continue
        if prints < 15:
            continue
        if dead_start is None:
            dead_start = ts
            dead_n = 1
        else:
            dead_n += 1
    if dead_n >= 5 and dead_start is not None and prints >= 15:
        last = times[-1]
        out.append((dead_start, last))
    return out


def classify_fly_fail(
    *,
    confirmed: bool,
    tagged_10: bool,
    max_ext: float | None,
    still_10_1559: bool | None,
    minutes_to_peak: float | None,
    gave_back: bool | None,
) -> str:
    """FLY / FAIL / other. Confirmed launch plus extension rules."""
    mx = float(max_ext) if max_ext is not None else None
    mins = float(minutes_to_peak) if minutes_to_peak is not None else None
    still = bool(still_10_1559)
    gb = bool(gave_back)
    if confirmed and mx is not None:
        if mx >= 0.20 - 1e-12:
            return "FLY"
        if still and mins is not None and mins >= 60.0 - 1e-12:
            return "FLY"
    if tagged_10 and not confirmed:
        return "FAIL"
    if confirmed and gb and mx is not None and mx < 0.15 - 1e-12:
        return "FAIL"
    return "other"


def attach_atr(sig: Signal, bars: pl.DataFrame) -> Signal:
    atr = atr_last6_5m(bars, sig.signal_ts)
    return Signal(
        signal_ts=sig.signal_ts,
        symbol=sig.symbol,
        side=sig.side,
        stop=sig.stop,
        target=sig.target,
        score=sig.score,
        tag=sig.tag,
        stop_from_entry=sig.stop_from_entry,
        overnight=sig.overnight,
        atr=float(atr),
    )
