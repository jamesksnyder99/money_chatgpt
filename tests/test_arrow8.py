from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.strategies8 import (
    filter_breadth,
    orb_wide_signals,
    three_day_hl_signals,
)

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


def test_orb_wide_silent_outside_1_to_4_percent() -> None:
    narrow = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.04, 9.99, 10.02, 1000),
            _row("TEST", 9, 44, 10.02, 10.05, 10.00, 10.03, 1000),  # W ~ 0.6%
            _row("TEST", 9, 45, 10.05, 10.20, 10.04, 10.15, 1000),  # close beyond high
            _row("TEST", 11, 59, 10.10, 10.12, 10.08, 10.10, 1000),
        ]
    )
    wide = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.60, 10.10, 1000),
            _row("TEST", 9, 44, 10.10, 10.50, 9.50, 10.00, 1000),  # W ~ 10%
            _row("TEST", 9, 45, 10.00, 10.70, 9.90, 10.60, 1000),
            _row("TEST", 11, 59, 10.10, 10.12, 10.08, 10.10, 1000),
        ]
    )
    assert orb_wide_signals(narrow) == []
    assert orb_wide_signals(wide) == []


def test_2r_target_is_twice_opening_range_height() -> None:
    # OR high=10.20 low=9.80, range=0.40, W=4%
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.90, 10.10, 5000),
            _row("TEST", 9, 44, 10.10, 10.15, 9.80, 10.00, 5000),
            _row("TEST", 9, 45, 10.10, 10.30, 10.05, 10.25, 5000),  # close > 10.20
            _row("TEST", 9, 46, 10.20, 10.25, 10.15, 10.22, 5000),  # fill at OR high
            _row("TEST", 9, 47, 10.22, 11.05, 10.20, 10.80, 5000),  # hits 2R=11.00
            _row("TEST", 9, 48, 11.00, 11.10, 10.90, 11.00, 5000),
            _row("TEST", 11, 59, 10.50, 10.60, 10.40, 10.50, 5000),
        ]
    )
    sigs = orb_wide_signals(df)
    assert len(sigs) == 1
    assert sigs[0].side == 1
    assert abs(sigs[0].stop - 9.80) < 1e-9
    trades = replay_session({"TEST": df}, sigs, {"TEST": 50_000_000.0}, take_2r=True)
    assert trades
    tr = trades[0]
    rng = 10.20 - 9.80
    assert abs((tr.exit_px - tr.entry_px) - 2.0 * rng) < 1e-9
    assert tr.tag == "target"


def test_breadth_blocks_long_vs_negative_book_median() -> None:
    test = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row("TEST", 9, 44, 10.10, 10.15, 9.80, 10.00, 1000),
            _row("TEST", 9, 45, 10.20, 10.35, 10.15, 10.30, 1000),  # long, ret +3%
            _row("TEST", 11, 59, 10.10, 10.12, 10.08, 10.10, 1000),
        ]
    )
    book1 = _bars(
        [
            _row("B1", 9, 30, 10.00, 10.05, 9.90, 9.95, 1000),
            _row("B1", 9, 44, 9.80, 9.85, 9.70, 9.75, 1000),
            _row("B1", 9, 45, 9.70, 9.75, 9.45, 9.50, 1000),  # ret -5%
            _row("B1", 11, 59, 9.50, 9.55, 9.45, 9.50, 1000),
        ]
    )
    book2 = _bars(
        [
            _row("B2", 9, 30, 10.00, 10.05, 9.90, 9.95, 1000),
            _row("B2", 9, 44, 9.85, 9.90, 9.70, 9.80, 1000),
            _row("B2", 9, 45, 9.70, 9.75, 9.50, 9.60, 1000),  # ret -4%
            _row("B2", 11, 59, 9.60, 9.65, 9.55, 9.60, 1000),
        ]
    )
    sigs = orb_wide_signals(test)
    assert len(sigs) == 1
    assert sigs[0].side == 1
    kept = filter_breadth(sigs, {"TEST": test, "B1": book1, "B2": book2})
    assert kept == []


def test_three_day_hl_silent_on_mixed_lows() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.50, 10.60, 10.40, 10.55, 1000),
            _row("TEST", 11, 59, 10.50, 10.55, 10.45, 10.50, 1000),
        ]
    )
    sigs = three_day_hl_signals(
        df,
        lows=(10.0, 9.0, 10.5),  # not L1 < L2 < L3
        highs=(12.0, 12.2, 12.1),  # not H1 > H2 > H3
        prior_close=10.8,
    )
    assert sigs == []
