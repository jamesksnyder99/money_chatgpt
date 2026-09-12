from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.arrow35 import assign_deciles
from research.harness import confirmed_launch
from research.strategies30 import harvestable_from_fillable, STOP_FLOOR_FRAC

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


def _row(hh, mm, o, h, l, c, v=5000):
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


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def test_premarket_launch_harvestable_from_0945_not_0420_peak() -> None:
    """04:05 launch peaking 04:20 has harvestable measured from 09:45."""
    pc = 10.0
    rows = [
        _row(4, 4, 10.50, 11.30, 10.40, 11.20, 5000),  # close +12%; pending confirm
        _row(4, 5, 11.20, 11.40, 10.90, 11.10, 5000),  # next low >= 1.08*pc → confirm
        _row(4, 20, 12.00, 15.00, 11.80, 14.50, 5000),  # premarket peak — must not count
        _row(9, 45, 11.00, 11.05, 10.90, 11.00, 3000),  # first fillable
        _row(10, 0, 11.10, 13.00, 11.00, 12.80, 3000),  # post-09:45 high
    ]
    pack = _pack_from_rows(rows)
    rec = confirmed_launch(pack, pc)
    assert rec["confirmed"] is True
    assert rec["confirm_ts"].hour == 4
    assert rec["confirm_ts"].minute == 5
    harv = harvestable_from_fillable(pack, rec["confirm_ts"], _bars(rows))
    assert harv["harvest_ts"] is not None
    assert harv["harvest_ts"].hour == 9
    assert harv["harvest_ts"].minute == 45
    assert abs(harv["fill_px"] - 11.00) < 1e-12
    assert abs(harv["max_high"] - 13.00) < 1e-12
    r1 = harv["r1"] if harv["r1"] is not None else STOP_FLOOR_FRAC
    expect = max(0.0, 13.00 / 11.00 - 1.0 - r1)
    assert abs(harv["harvestable"] - expect) < 1e-12
    # 04:20 high of 15 is not the denom high; sea is fillable price not prior close.
    assert harv["max_high"] < 15.0 - 1e-12
    wrong_from_peak = max(0.0, 15.00 / 11.00 - 1.0 - r1)
    assert abs(harv["harvestable"] - wrong_from_peak) > 1e-6


def test_wick_12pct_close_6pct_is_not_confirmed_launch() -> None:
    pc = 10.0
    rows = [
        _row(9, 30, 10.20, 11.20, 10.10, 10.60),  # +12% wick, close +6%
        _row(9, 31, 10.60, 10.70, 10.50, 10.65),
    ]
    rec = confirmed_launch(_pack_from_rows(rows), pc)
    assert rec["confirmed"] is False


def test_decile_n_sums_to_n_all() -> None:
    for n in (0, 1, 7, 10, 11, 23, 100):
        scores = [float(i) for i in range(n)]
        dec = assign_deciles(scores)
        assert len(dec) == n
        assert sum(1 for _ in dec) == n
        n_sum = len(dec)
        assert n_sum == n
        if n:
            assert min(dec) >= 1
            assert max(dec) <= 10
            counts = [dec.count(d) for d in range(1, 11)]
            assert sum(counts) == n
