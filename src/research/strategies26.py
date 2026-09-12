from __future__ import annotations

from research.signals import MINUTE_0950
from research.strategies25 import fly_cell_ok, flush_ring_long, score_flush

RANGE_ACCEL = 1.2
DECEL_HL = 0.8
VOL_ACCEL = 1.3
SLOW_WASH_MIN = 15.0
MAX_UNDERCUT = 0.06

__all__ = (
    "RANGE_ACCEL",
    "DECEL_HL",
    "VOL_ACCEL",
    "SLOW_WASH_MIN",
    "MAX_UNDERCUT",
    "MINUTE_0950",
    "fly_cell_ok",
    "flush_ring_long",
    "score_flush",
)
