from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.signals import MINUTE_1130, Signal
from research.strategies10 import or15_break_short
from research.strategies11 import short_kernel_pop
from research.strategies12 import bearish_or

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(sym, hh, mm, o, h, l, c, v, day=1):
    return {
        "symbol": sym,
        "bar_start": datetime(2026, 6, day, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "pre" if hh < 9 else "rth",
    }


def test_helpers_emit_only_shorts() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.50, 10.00, 1000),
            _row("TEST", 9, 44, 10.00, 10.40, 9.50, 9.90, 1000),
            _row("TEST", 9, 45, 9.40, 9.50, 9.20, 9.30, 1000),
            _row("TEST", 11, 59, 9.20, 9.30, 9.10, 9.20, 1000),
        ]
    )
    sigs = or15_break_short(df)
    assert sigs
    assert all(s.side == -1 for s in sigs)


def test_bearish_or_rejects_top_half_close() -> None:
    top = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.60, 10.10, 1000),
            _row("TEST", 9, 44, 10.20, 10.40, 10.00, 10.30, 1000),  # close in top half of 9.60-10.40
            _row("TEST", 9, 45, 10.30, 10.35, 10.20, 10.25, 1000),
        ]
    )
    low = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.60, 10.10, 1000),
            _row("TEST", 9, 44, 9.80, 9.90, 9.60, 9.70, 1000),  # close in lower half
            _row("TEST", 9, 45, 9.70, 9.80, 9.50, 9.60, 1000),
        ]
    )
    assert bearish_or(top) is False
    assert bearish_or(low) is True


def test_flatten_1130_closes_before_1159() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.80, 10.10, 5000),
            _row("TEST", 9, 31, 10.10, 10.20, 10.00, 10.15, 5000),
            _row("TEST", 11, 30, 9.90, 10.00, 9.80, 9.85, 5000),
            _row("TEST", 11, 59, 9.50, 9.60, 9.40, 9.50, 5000),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", -1, 10.50, None, 1.0, "test")
    trades = replay_session(
        {"TEST": df}, [sig], {"TEST": 50_000_000.0}, flatten_at=MINUTE_1130
    )
    assert trades
    tr = trades[0]
    assert tr.exit_ts == df["bar_start"][2]
    assert tr.exit_ts != df["bar_start"][3]
    assert tr.tag == "time"


def test_gap15_accepts_1p6_rejects_1p0() -> None:
    kwargs = {"dv_min": 0.80, "gap_min": 0.015, "or_w_min": 0.025}
    assert short_kernel_pop(0.95, -0.016, 0.03, **kwargs) is True
    assert short_kernel_pop(0.95, -0.010, 0.03, **kwargs) is False
