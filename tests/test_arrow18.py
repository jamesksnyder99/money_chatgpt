from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import (
    borrow_blocks_short,
    replay_session,
    ssr_blocks_short,
)
from research.signals import Signal

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


def _held_to_1159(side: int, vol_1159: int) -> pl.DataFrame:
    return _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row("TEST", 9, 31, 10.10, 10.20, 10.00, 10.15, 1000),
            _row("TEST", 11, 58, 10.20, 10.40, 9.80, 10.18, 1000),
            _row("TEST", 11, 59, 10.30, 10.35, 10.25, 10.32, vol_1159),
        ]
    )


def test_flatten_zero_volume_1159_uses_1158() -> None:
    """A33: 11:59 untradeable, no later print → mark 11:58 close, tag unresolved, real ts."""
    for side, stop in ((1, 9.50), (-1, 10.50)):
        df = _held_to_1159(side, vol_1159=0)
        sig = Signal(df["bar_start"][0], "TEST", side, stop, None, 1.0, "test")
        trades = replay_session({"TEST": df}, [sig], {"TEST": 50_000_000.0})
        assert len(trades) == 1
        assert trades[0].exit_ts == df["bar_start"][2]
        assert abs(trades[0].exit_px - 10.18) < 1e-9
        assert trades[0].tag == "unresolved"
        assert abs(trades[0].exit_px - trades[0].entry_px) > 1e-9


def test_ssr_rejects_close_at_or_below_90pct() -> None:
    assert ssr_blocks_short(17.90, 20.0) is True
    assert ssr_blocks_short(18.20, 20.0) is False
    rows = [
        _row("TEST", 9, 30, 19.00, 19.10, 17.80, 17.90, 1000),
        _row("TEST", 9, 31, 17.90, 18.00, 17.80, 17.85, 1000),
        _row("TEST", 11, 59, 17.80, 17.90, 17.70, 17.80, 1000),
    ]
    df = _bars(rows)
    sig = Signal(df["bar_start"][0], "TEST", -1, 19.50, None, 1.0, "test")
    blocked = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        prior_close={"TEST": 20.0},
        ssr_filter=True,
    )
    assert blocked == []
    rows[0] = _row("TEST", 9, 30, 19.00, 19.10, 18.10, 18.20, 1000)
    df2 = _bars(rows)
    sig2 = Signal(df2["bar_start"][0], "TEST", -1, 19.50, None, 1.0, "test")
    ok = replay_session(
        {"TEST": df2},
        [sig2],
        {"TEST": 50_000_000.0},
        prior_close={"TEST": 20.0},
        ssr_filter=True,
    )
    assert ok


def test_borrow_rejects_wide_gap_thin_dv() -> None:
    assert borrow_blocks_short(-0.06, 8_000_000.0) is True
    assert borrow_blocks_short(-0.06, 20_000_000.0) is False
    rows = [
        _row("TEST", 9, 30, 18.80, 18.90, 18.70, 18.85, 1000),  # gap -6% vs 20
        _row("TEST", 9, 31, 18.85, 18.90, 18.70, 18.80, 1000),
        _row("TEST", 11, 59, 18.70, 18.80, 18.60, 18.70, 1000),
    ]
    df = _bars(rows)
    sig = Signal(df["bar_start"][0], "TEST", -1, 19.50, None, 1.0, "test")
    thin = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 8_000_000.0},
        prior_close={"TEST": 20.0},
        borrow_filter=True,
    )
    assert thin == []
    thick = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 20_000_000.0},
        prior_close={"TEST": 20.0},
        borrow_filter=True,
    )
    assert thick
