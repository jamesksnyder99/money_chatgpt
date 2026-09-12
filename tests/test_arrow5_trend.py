from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.strategies5 import gap_with_trend_signals, trend_open_signals, trend_pullback_signals
from research.trend import Trend, classify_trend

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(hh, mm, o, h, l, c, v, symbol="TEST"):
    return {
        "symbol": symbol,
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "rth",
    }


def _up() -> Trend:
    return Trend(side="up", c1=10.0, c10=12.0, mean=11.0, score=0.2)


def _down() -> Trend:
    return Trend(side="down", c1=12.0, c10=10.0, mean=11.0, score=0.2)


def _flat() -> Trend:
    return Trend(side="flat", c1=10.0, c10=10.1, mean=10.2, score=0.01)


def test_classify_trend() -> None:
    up = [10, 10.2, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 11.0, 12.0]
    assert classify_trend(up) == "up"
    down = [12, 11.8, 11.6, 11.4, 11.2, 11.0, 10.8, 10.6, 10.4, 10.0]
    assert classify_trend(down) == "down"
    flat = [10, 11, 10, 11, 10, 11, 10, 11, 10, 10.2]
    assert classify_trend(flat) == "flat"


def test_flat_trend_no_trend_open() -> None:
    df = _bars([_row(9, 30, 10.0, 10.2, 9.9, 10.1, 1000)])
    assert trend_open_signals(df, _flat()) == []
    assert trend_open_signals(df, _up())


def test_gap_with_trend_ignores_counter_trend() -> None:
    # 09:30 open 9.0 vs prior 10 = -10% gap; up trend must ignore
    df = _bars(
        [
            _row(9, 30, 9.0, 9.1, 8.9, 9.05, 2000),
            _row(9, 31, 9.05, 9.1, 9.0, 9.08, 1000),
        ]
    )
    assert gap_with_trend_signals(df, _up(), prior_close=10.0) == []
    # +2% gap with up trend fires
    df2 = _bars(
        [
            _row(9, 30, 10.20, 10.3, 10.1, 10.22, 2000),
            _row(9, 31, 10.22, 10.3, 10.2, 10.25, 1000),
        ]
    )
    sigs = gap_with_trend_signals(df2, _up(), prior_close=10.0)
    assert sigs and sigs[0].side == 1
    # +2% gap with down trend ignored
    assert gap_with_trend_signals(df2, _down(), prior_close=10.0) == []


def test_pullback_not_before_1000() -> None:
    rows = [_row(9, 30, 10.0, 10.5, 9.9, 10.4, 1000)]
    # 09:50: 2% off the high — too early
    rows.append(_row(9, 50, 10.3, 10.35, 10.2, 10.25, 1000))
    df_early = _bars(rows)
    assert trend_pullback_signals(df_early, _up()) == []
    rows.append(_row(10, 1, 10.2, 10.25, 10.1, 10.15, 1000))
    df = _bars(rows)
    sigs = trend_pullback_signals(df, _up())
    assert sigs
    assert sigs[0].signal_ts.hour > 9 or sigs[0].signal_ts.minute >= 0
    assert not (sigs[0].signal_ts.hour == 9 and sigs[0].signal_ts.minute < 60)
    assert sigs[0].signal_ts.hour >= 10
