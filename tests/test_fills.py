from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.costs import round_trip_cost, signed_pnl
from research.fills import is_tradeable, next_tradeable_row
from research.signals import Signal

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(pl.col("bar_start").dt.replace_time_zone("America/New_York"))


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


def test_zero_volume_is_not_tradeable() -> None:
    assert is_tradeable(10.0, 10.1, 0) is False
    assert is_tradeable(10.0, 10.1, None) is False
    assert is_tradeable(float("nan"), 10.1, 100) is False
    assert is_tradeable(10.0, 10.1, 100) is True


def test_next_bar_open_not_same_bar() -> None:
    df = _bars(
        [
            _row(9, 30, 10.0, 10.5, 9.9, 10.4, 1000),
            _row(9, 31, 10.4, 10.6, 10.3, 10.5, 1000),
            _row(9, 32, 10.5, 10.7, 10.4, 10.6, 1000),
            _row(11, 59, 10.2, 10.3, 10.1, 10.2, 1000),
        ]
    )
    nxt = next_tradeable_row(df, 0)
    assert nxt == 1
    assert df["open"][nxt] == 10.4
    assert df["open"][nxt] != df["open"][0]


def test_fill_skips_zero_volume_bar() -> None:
    df = _bars(
        [
            _row(9, 30, 10.0, 10.2, 9.9, 10.1, 1000),
            _row(9, 31, 10.1, 10.3, 10.0, 10.2, 1000),
            _row(9, 32, 99.0, 99.0, 99.0, 99.0, 0),  # not a trade
            _row(9, 33, 10.25, 10.4, 10.2, 10.3, 800),
            _row(11, 59, 10.0, 10.1, 9.9, 10.0, 500),
        ]
    )
    sig = Signal(
        signal_ts=df["bar_start"][1],
        symbol="TEST",
        side=1,
        stop=9.50,
        target=None,
        score=1.0,
        tag="test",
    )
    trades = replay_session({"TEST": df}, [sig], {"TEST": 5_000_000})
    assert trades, "expected a fill"
    tr = trades[0]
    assert tr.entry_px == 10.25
    assert tr.entry_px != 99.0
    assert tr.entry_ts == df["bar_start"][3]


def test_same_bar_high_is_not_entry() -> None:
    df = _bars(
        [
            _row(9, 30, 10.0, 12.0, 9.5, 11.0, 1000),
            _row(9, 31, 10.2, 10.3, 10.1, 10.2, 1000),
            _row(11, 59, 10.0, 10.1, 9.9, 10.0, 1000),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", 1, 9.0, None, 1.0, "test")
    trades = replay_session({"TEST": df}, [sig], {"TEST": 5_000_000})
    assert trades
    assert trades[0].entry_px == 10.2
    assert trades[0].entry_px != 12.0
    assert trades[0].entry_px != 10.0


def test_round_trip_costs_both_sides() -> None:
    c = round_trip_cost(100, 10.0, 11.0)
    # 0.005 + max(0.01, 0.001*px) each side
    assert c == 100 * ((0.005 + 0.01) + (0.005 + 0.011))
    pnl = signed_pnl(1, 100, 10.0, 11.0)
    assert pnl == 100.0 - c
