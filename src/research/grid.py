from __future__ import annotations

from datetime import time

from research.signals import (
    MINUTE_0935,
    MINUTE_0945,
    MINUTE_1159,
    MINUTE_1300,
    RTH_OPEN,
)

# Earliest clock a door can enter. Flatten at or before this is STRUCTURAL (silent n=0).
DOOR_EARLIEST_ENTRY = {
    "launch": MINUTE_0945,
    "volfirst": MINUTE_0935,
    "flush": RTH_OPEN,
    "giveback": MINUTE_1300,
    "c5_ema9": MINUTE_0945,
}


def is_structural(flatten_at: time, earliest_entry: time) -> bool:
    """True iff flatten_at ≤ earliest entry clock — a silent n=0 test, not a book."""
    return flatten_at <= earliest_entry


def structural_grid_row(door: str, flatten_at: time) -> bool:
    earliest = DOOR_EARLIEST_ENTRY.get(door)
    if earliest is None:
        return False
    return is_structural(flatten_at, earliest)


def exclude_from_both_green(door: str, flatten_at: time) -> bool:
    return structural_grid_row(door, flatten_at)
