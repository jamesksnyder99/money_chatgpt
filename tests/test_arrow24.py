from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.harness import (
    confirmed_launch,
    cost_gate_blocks,
    halt_windows,
    harness_stop_distance,
)
from research.strategies24 import DOORS, GRID_IDS, door_side, grid_ids

ET = ZoneInfo("America/New_York")


def _pack_from_rows(rows: list[dict]) -> dict:
    return {
        "ts": [r["bar_start"] for r in rows],
        "open": [r["open"] for r in rows],
        "high": [r["high"] for r in rows],
        "low": [r["low"] for r in rows],
        "close": [r["close"] for r in rows],
        "vol": [r["volume"] for r in rows],
    }


def _row(hh, mm, o, h, l, c, v):
    return {
        "symbol": "TEST",
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session_part": "pre" if hh < 9 or (hh == 9 and mm < 30) else "rth",
    }


def test_confirmed_launch_rejects_wick_close() -> None:
    pc = 10.0
    rows = [
        _row(9, 30, 10.20, 11.20, 10.10, 10.60, 1000),  # +12% wick, close +6%
        _row(9, 31, 10.60, 10.70, 10.50, 10.65, 1000),
    ]
    rec = confirmed_launch(_pack_from_rows(rows), pc)
    assert rec["confirmed"] is False


def test_confirmed_launch_holds_next_bar() -> None:
    pc = 10.0
    rows = [
        _row(9, 45, 10.80, 11.20, 10.70, 11.10, 1000),  # close +11%
        _row(9, 46, 11.10, 11.30, 10.85, 11.20, 1000),  # low +8.5% >= +8%
    ]
    rec = confirmed_launch(_pack_from_rows(rows), pc)
    assert rec["confirmed"] is True
    assert rec["confirm_ts"].minute == 46


def test_atr_floor_widens_tiny_structure_stop() -> None:
    # 0.2% structure at $10 is $0.02; ATR of 0.15 5-min ranges should widen
    dist = harness_stop_distance(10.0, 9.98, atr=0.15, side=1, use_structure=True)
    assert dist >= 0.15 - 1e-12
    assert dist > 0.02


def test_cost_gate_skips_2_dollar_3pct_stop() -> None:
    assert cost_gate_blocks(2.0, 0.06) is True
    # a wide stop on a $10 name should pass
    assert cost_gate_blocks(10.0, 0.50) is False


def test_halt_helper_needs_five_dead_minutes() -> None:
    rows = []
    for mm in range(30, 46):
        rows.append(_row(9, mm, 10.0, 10.1, 9.9, 10.0, 1000))
    for mm in range(46, 50):
        rows.append(_row(9, mm, 10.0, 10.0, 10.0, 10.0, 0))
    df = pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )
    assert halt_windows(df) == []
    rows.append(_row(9, 50, 10.0, 10.0, 10.0, 10.0, 0))
    df5 = pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )
    wins = halt_windows(df5)
    assert wins
    assert (wins[0][1] - wins[0][0]).total_seconds() >= 4 * 60


def test_grid_has_100_ids() -> None:
    ids = grid_ids()
    assert len(ids) == 100
    assert len(set(ids)) == 100
    assert ids == GRID_IDS


def test_shorts_only_from_giveback() -> None:
    assert door_side("giveback") == -1
    for d in DOORS:
        if d == "giveback":
            assert all(i.startswith("giveback|") and door_side(d) == -1 for i in GRID_IDS if i.startswith(d))
        else:
            assert door_side(d) == 1
    assert sum(1 for i in GRID_IDS if i.startswith("giveback|")) == 25
    assert sum(1 for i in GRID_IDS if door_side(i.split("|")[0]) == -1) == 25
