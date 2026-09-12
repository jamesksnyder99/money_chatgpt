from datetime import datetime, time
from zoneinfo import ZoneInfo

import polars as pl

from research.book import Book, Position, _update_trail, replay_session
from research.signals import MINUTE_0945, MINUTE_1159, MINUTE_1330, MINUTE_1559, Signal
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


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


def test_id0_n_near_a31() -> None:
    from research.arrow34 import A31_FLUSH_N_DEV, CONTROL_ID

    assert A31_FLUSH_N_DEV == 21
    assert CONTROL_ID == "flush|max6|flat1159"


def test_a1_cell_available_at_0945() -> None:
    assert FLY_AVAILABLE_AT == MINUTE_0945
    assert fly_cell_ok(0.051, 98_000.0, 0.034) is True
    last_px = 10.00
    rows = [
        _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
        _row(9, 30, 9.90, 9.95, 9.60, 9.80, 1000),
        _row(9, 35, 9.85, 9.95, 9.78, 9.92, 1000),
        _row(9, 44, 10.30, 10.50, 9.70, 10.40, 2000),
    ]
    df = _bars(rows)
    early = flush_ring_long(df, last_px, max_undercut=0.06, signal_after=FLY_AVAILABLE_AT)
    assert all(s.signal_ts.timetz().replace(tzinfo=None) >= time(9, 45) for s in early)


def test_trail_never_loosens_long() -> None:
    ts = datetime(2026, 6, 1, 9, 31, tzinfo=ET)
    for mult in (1.0, 1.5):
        pos = Position(
            symbol="TEST",
            side=1,
            shares=100,
            entry_px=10.0,
            stop=9.5,
            target=None,
            entry_ts=ts,
            risk=50.0,
            tag="atr",
            initial_r=0.5,
            atr=0.20,
            favorable_extreme=10.0,
        )
        book = Book(prior_dv={}, atr_trail=True, trail_atr_mult=mult)
        _update_trail(pos, 11.00, 10.20, 10.80, book)
        assert pos.trail_armed
        s0 = pos.stop
        _update_trail(pos, 10.70, 10.40, 10.50, book)
        assert pos.stop >= s0 - 1e-12
        _update_trail(pos, 10.60, 10.30, 10.40, book)
        assert pos.stop >= s0 - 1e-12


def test_id2_arms_at_half_r() -> None:
    ts = datetime(2026, 6, 1, 9, 31, tzinfo=ET)
    pos = Position(
        symbol="TEST",
        side=1,
        shares=100,
        entry_px=10.0,
        stop=9.5,
        target=None,
        entry_ts=ts,
        risk=50.0,
        tag="arm05",
        initial_r=0.5,
        atr=0.20,
        favorable_extreme=10.0,
    )
    full = Book(prior_dv={}, atr_trail=True, trail_arm_r=1.0)
    _update_trail(pos, 10.30, 9.90, 10.24, full)
    assert pos.trail_armed is False
    half = Book(prior_dv={}, atr_trail=True, trail_arm_r=0.5)
    _update_trail(pos, 10.30, 9.90, 10.25, half)
    assert pos.trail_armed is True


def test_id4_flattens_at_1330() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(9, 31, 10.00, 10.20, 9.95, 10.10),
            _row(13, 30, 10.40, 10.50, 10.30, 10.45),
            _row(15, 59, 10.80, 10.90, 10.70, 10.85),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", 1, 9.50, None, 1.0, "atr1330")
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1330,
        last_entry_at=MINUTE_1159,
        atr_trail=True,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert trades
    assert trades[-1].tag in {"time", "unresolved_late", "unresolved"}
    assert trades[-1].exit_ts.hour == 13
    assert trades[-1].exit_ts.minute == 30
    assert not any(t.exit_ts.hour == 15 for t in trades)
