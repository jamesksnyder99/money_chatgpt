from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.signals import MINUTE_1000
from research.strategies25 import fly_cell_ok, flush_ring_long

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


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


def _flush_sequence(*, undercut_low: float, hl_close: float, flush_hh=9, flush_mm=50, hl_mm=55):
    """08:00 last_px=10, undercut bar then higher-low strong close."""
    return _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
            _row(flush_hh, flush_mm, 9.90, 9.95, undercut_low, 9.80, 1000),
            _row(flush_hh, hl_mm, 9.85, hl_close, 9.78, hl_close, 1000),
        ]
    )


def test_id6_rejects_7pct_undercut() -> None:
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.30, hl_close=9.92)  # 7%
    assert flush_ring_long(df, last_px, max_undercut=0.06) == []
    df_ok = _flush_sequence(undercut_low=9.50, hl_close=9.92)  # 5%
    sigs = flush_ring_long(df_ok, last_px, max_undercut=0.06)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id7_silent_if_close_never_reclaims_0800_px() -> None:
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.70, hl_close=9.88)  # close_loc high, not reclaim
    assert flush_ring_long(df, last_px, min_close_loc=0.85, reclaim_0800=True) == []
    df_ok = _flush_sequence(undercut_low=9.70, hl_close=10.05)
    sigs = flush_ring_long(df_ok, last_px, min_close_loc=0.85, reclaim_0800=True)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id8_silent_on_0950_only_flush() -> None:
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.70, hl_close=9.92, flush_hh=9, flush_mm=50, hl_mm=55)
    assert flush_ring_long(df, last_px, flush_after=MINUTE_1000) == []
    df_ok = _flush_sequence(undercut_low=9.70, hl_close=9.92, flush_hh=10, flush_mm=0, hl_mm=5)
    sigs = flush_ring_long(df_ok, last_px, flush_after=MINUTE_1000)
    assert sigs


def test_id10_may_fire_when_or_width_is_3pct() -> None:
    assert fly_cell_ok(0.03, 200_000.0, 0.05) is False
    assert fly_cell_ok(0.051, 98_000.0, 0.034) is True
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.70, hl_close=9.92)
    sigs = flush_ring_long(df, last_px)
    assert sigs
    assert all(s.side == 1 for s in sigs)
