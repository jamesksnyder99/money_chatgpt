from __future__ import annotations

from datetime import datetime

from research.signals import Signal
from research.strategies20 import STOP_MIN_FRAC, gap_and_go_long

PRE_DV_MIN = 400_000.0
PRE_DV_REL_MIN = 3.0
EXT_LO = 0.02
EXT_HI = 0.10
EXT6_HI = 0.06
PRE_DV_750K = 750_000.0
HOT_CLUSTER = 15


def hot_gate_0800(
    *,
    pre_dv: float | None,
    pre_dv_rel: float | None,
    ext_0800: float | None,
) -> bool:
    """08:00 point-in-time hot engine: 3x 04:00-08:00 $vol, +2% to <+10%, $400k floor."""
    if pre_dv is None or pre_dv < PRE_DV_MIN - 1e-9:
        return False
    if pre_dv_rel is None or pre_dv_rel < PRE_DV_REL_MIN - 1e-12:
        return False
    if ext_0800 is None:
        return False
    return EXT_LO - 1e-12 <= float(ext_0800) < EXT_HI


def skip_cluster(n_hot: int, cap: int = HOT_CLUSTER) -> bool:
    """True iff the session is too crowded to trade (id 6)."""
    return int(n_hot) > cap


def open_longs_0800(
    hots: list[dict],
    *,
    pre_dv_min: float = PRE_DV_MIN,
    ext_hi: float = EXT_HI,
    skip_if_cluster: bool = False,
    cluster_cap: int = HOT_CLUSTER,
) -> list[Signal]:
    """Long-only 08:00 next-open entries. Stop = session low through 08:00."""
    if skip_if_cluster and skip_cluster(len(hots), cluster_cap):
        return []
    out: list[Signal] = []
    for h in hots:
        if h.get("pre_dv") is None or float(h["pre_dv"]) < pre_dv_min - 1e-9:
            continue
        ext = h.get("ext_0800")
        if ext is None or not (EXT_LO - 1e-12 <= float(ext) < ext_hi):
            continue
        last_ts: datetime = h["last_ts"]
        for sig in gap_and_go_long(
            last_ts,
            str(h["symbol"]),
            float(h["sess_low"]),
            float(h["last_px"]),
            float(h["pre_dv_rel"]),
            tag="hot0800",
        ):
            if sig.side == 1:
                out.append(sig)
    return out


__all__ = (
    "EXT6_HI",
    "EXT_HI",
    "EXT_LO",
    "HOT_CLUSTER",
    "PRE_DV_750K",
    "PRE_DV_MIN",
    "PRE_DV_REL_MIN",
    "STOP_MIN_FRAC",
    "hot_gate_0800",
    "open_longs_0800",
    "skip_cluster",
)
