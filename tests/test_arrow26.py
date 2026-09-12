from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.signals import MINUTE_1159, MINUTE_1559, Signal
from research.strategies26 import (
    DECEL_HL,
    MAX_UNDERCUT,
    SLOW_WASH_MIN,
    flush_ring_long,
)

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


def test_id1_still_max6() -> None:
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.30, hl_close=9.92)  # 7%
    assert flush_ring_long(df, last_px, max_undercut=MAX_UNDERCUT) == []
    df_ok = _flush_sequence(undercut_low=9.50, hl_close=9.92)  # 5%
    sigs = flush_ring_long(df_ok, last_px, max_undercut=MAX_UNDERCUT)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id4_silent_if_signal_range_wider_than_flush() -> None:
    last_px = 10.00
    df = _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
            _row(9, 50, 9.90, 9.95, 9.70, 9.80, 1000),  # range 0.25
            _row(9, 55, 9.85, 10.10, 9.78, 10.10, 1000),  # range 0.32, strong
        ]
    )
    assert flush_ring_long(df, last_px, max_undercut=MAX_UNDERCUT, decel_hl=DECEL_HL) == []
    df_ok = _flush_sequence(undercut_low=9.70, hl_close=9.92)  # signal range 0.14 < 0.8*0.25
    sigs = flush_ring_long(df_ok, last_px, max_undercut=MAX_UNDERCUT, decel_hl=DECEL_HL)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id6_silent_if_drop_is_5_minutes() -> None:
    last_px = 10.00
    df = _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
            _row(9, 30, 9.90, 9.95, 9.70, 9.80, 1000),  # first tag -2%
            _row(9, 35, 9.75, 9.80, 9.60, 9.70, 1000),  # flush low, 5 min later
            _row(9, 40, 9.72, 9.95, 9.65, 9.95, 1000),  # HL + strong close
        ]
    )
    assert (
        flush_ring_long(df, last_px, max_undercut=MAX_UNDERCUT, slow_wash_min=SLOW_WASH_MIN)
        == []
    )
    df_ok = _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
            _row(9, 30, 9.90, 9.95, 9.70, 9.80, 1000),
            _row(9, 35, 9.80, 9.85, 9.72, 9.78, 1000),
            _row(9, 40, 9.78, 9.82, 9.71, 9.76, 1000),
            _row(9, 45, 9.70, 9.75, 9.55, 9.65, 1000),  # flush low, 15 min
            _row(9, 50, 9.66, 9.90, 9.60, 9.90, 1000),
        ]
    )
    sigs = flush_ring_long(
        df_ok, last_px, max_undercut=MAX_UNDERCUT, slow_wash_min=SLOW_WASH_MIN
    )
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id7_silent_after_a_single_hl() -> None:
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.70, hl_close=9.92)
    assert flush_ring_long(df, last_px, max_undercut=MAX_UNDERCUT, two_hls=True) == []
    df_ok = _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
            _row(9, 50, 9.90, 9.95, 9.70, 9.80, 1000),
            _row(9, 55, 9.85, 9.90, 9.75, 9.88, 1000),  # first HL
            _row(10, 0, 9.90, 10.05, 9.80, 10.05, 1000),  # second HL + strong close
        ]
    )
    sigs = flush_ring_long(df_ok, last_px, max_undercut=MAX_UNDERCUT, two_hls=True)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id10_silent_when_close_below_0800_px() -> None:
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.70, hl_close=9.92)
    assert flush_ring_long(df, last_px, max_undercut=MAX_UNDERCUT, reclaim_0800=True) == []
    df_ok = _flush_sequence(undercut_low=9.70, hl_close=10.05)
    sigs = flush_ring_long(df_ok, last_px, max_undercut=MAX_UNDERCUT, reclaim_0800=True)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_longs_only() -> None:
    last_px = 10.00
    df = _flush_sequence(undercut_low=9.70, hl_close=9.92)
    sigs = flush_ring_long(df, last_px, max_undercut=MAX_UNDERCUT)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id9_holds_to_1559_only_if_plus_half_r() -> None:
    def _mk(hh, mm, o, h, l, c):
        return _row(hh, mm, o, h, l, c, 5000)

    df_win = _bars(
        [
            _mk(9, 50, 10.00, 10.10, 9.95, 10.00),
            _mk(9, 51, 10.00, 10.20, 9.98, 10.10),
            _mk(11, 59, 10.60, 10.70, 10.50, 10.60),
            _mk(15, 59, 10.80, 10.90, 10.70, 10.80),
        ]
    )
    sig = Signal(df_win["bar_start"][0], "TEST", 1, 9.00, None, 1.0, "hold05")
    held = replay_session(
        {"TEST": df_win},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        hold_plus_r=0.5,
        late_flatten_at=MINUTE_1559,
        harness_stop=False,
        cost_gate=False,
        min_stop_frac=0.0,
    )
    assert held
    assert held[-1].tag == "time"
    assert held[-1].exit_ts.hour == 15

    df_lose = _bars(
        [
            _mk(9, 50, 10.00, 10.10, 9.95, 10.00),
            _mk(9, 51, 10.00, 10.20, 9.98, 10.10),
            _mk(11, 59, 10.20, 10.30, 10.10, 10.20),
            _mk(15, 59, 10.80, 10.90, 10.70, 10.80),
        ]
    )
    cut = replay_session(
        {"TEST": df_lose},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        hold_plus_r=0.5,
        late_flatten_at=MINUTE_1559,
        harness_stop=False,
        cost_gate=False,
        min_stop_frac=0.0,
    )
    assert cut
    assert cut[-1].tag == "time"
    assert cut[-1].exit_ts.hour == 11
