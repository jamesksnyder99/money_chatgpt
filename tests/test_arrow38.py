from datetime import datetime, time
from zoneinfo import ZoneInfo

import polars as pl

from research.signals import bar_time
from research.strategies38 import DIP_CTRL, pm_reclaim_long

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


def _launch_and_open(*, dip_low: float, reclaim_hh: int, reclaim_mm: int, reclaim_close: float):
    """Premarket launch, 09:30 open under pm high 12.00, then a reclaim close."""
    rows = [
        _row(8, 0, 10.50, 12.00, 10.40, 11.20),  # launch close +12%, pm high 12.00
        _row(8, 1, 11.20, 11.40, 10.90, 11.10),  # confirm
        _row(9, 29, 11.10, 11.20, 11.00, 11.05),
        _row(9, 30, 11.00, 11.10, 10.90, 11.00),  # open 11.00 < pm high
        _row(9, 40, 10.80, 10.90, dip_low, 10.75),
        _row(9, 50, 10.80, 11.20, 10.70, 10.90),
        _row(reclaim_hh, reclaim_mm, 11.50, max(12.10, reclaim_close), 11.40, reclaim_close),
        _row(reclaim_hh, min(reclaim_mm + 1, 59), 11.60, 12.20, 11.50, 11.80),
    ]
    return rows


def test_silent_if_never_3pct_under_the_open() -> None:
    # open 11.00; 3% under = 10.67. dip_low 10.80 is only ~1.8%.
    rows = _launch_and_open(dip_low=10.80, reclaim_hh=10, reclaim_mm=5, reclaim_close=12.10)
    pack = _pack_from_rows(rows)
    assert pm_reclaim_long(_bars(rows), pack, 10.0, dip_frac=DIP_CTRL) == []


def test_silent_if_reclaim_is_rth_high_only() -> None:
    rows = _launch_and_open(dip_low=10.60, reclaim_hh=10, reclaim_mm=5, reclaim_close=11.50)
    # 11.50 reclaims a RTH high (~11.1) but not pm high 12.00
    pack = _pack_from_rows(rows)
    assert pm_reclaim_long(_bars(rows), pack, 10.0, dip_frac=DIP_CTRL) == []


def test_0950_close_above_pm_high_is_not_id0() -> None:
    rows = _launch_and_open(dip_low=10.60, reclaim_hh=9, reclaim_mm=50, reclaim_close=12.10)
    pack = _pack_from_rows(rows)
    sigs = pm_reclaim_long(_bars(rows), pack, 10.0, dip_frac=DIP_CTRL)
    assert sigs == []
    assert all(bar_time(s.signal_ts) >= time(10, 0) for s in sigs)


def test_pm_reclaim_long_only() -> None:
    rows = _launch_and_open(dip_low=10.60, reclaim_hh=10, reclaim_mm=5, reclaim_close=12.10)
    pack = _pack_from_rows(rows)
    sigs = pm_reclaim_long(_bars(rows), pack, 10.0, dip_frac=DIP_CTRL)
    assert sigs
    assert all(s.side == 1 for s in sigs)
    assert all(bar_time(s.signal_ts) >= time(10, 0) for s in sigs)
