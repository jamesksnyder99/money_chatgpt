from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import Book, Position, _update_trail, replay_session
from research.signals import MINUTE_1159, MINUTE_1330, MINUTE_1559, Signal
from research.strategies15 import control_c5_ema9

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


def test_id0_short_only() -> None:
    df = _bars(
        [
            _row(9, 30, 10.0, 10.2, 9.9, 10.1),
            _row(9, 45, 10.0, 10.1, 9.8, 9.85),
            _row(9, 49, 9.85, 9.90, 9.70, 9.72),
            _row(11, 59, 9.70, 9.80, 9.60, 9.65),
        ]
    )
    sigs = control_c5_ema9(df, [], 10.2)
    assert all(s.side == -1 for s in sigs)
    sig = Signal(df["bar_start"][0], "TEST", -1, 10.50, None, 1.0, "c5")
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert trades
    assert all(t.side == -1 for t in trades)


def test_id2_flattens_03r_holds_07r() -> None:
    def _mk(hh, mm, o, h, l, c):
        return _row(hh, mm, o, h, l, c)

    sig = Signal(
        datetime(2026, 6, 1, 9, 30, tzinfo=ET), "TEST", -1, 10.50, None, 1.0, "hold05"
    )
    df_cut = _bars(
        [
            _mk(9, 30, 10.00, 10.10, 9.95, 10.00),
            _mk(9, 31, 10.00, 10.05, 9.90, 9.95),
            _mk(11, 59, 9.85, 9.90, 9.80, 9.84),
            _mk(15, 59, 9.40, 9.50, 9.30, 9.35),
        ]
    )
    cut = replay_session(
        {"TEST": df_cut},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        hold_plus_r=0.5,
        late_flatten_at=MINUTE_1559,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert cut
    assert cut[-1].tag == "time"
    assert cut[-1].exit_ts.hour == 11

    df_hold = _bars(
        [
            _mk(9, 30, 10.00, 10.10, 9.95, 10.00),
            _mk(9, 31, 10.00, 10.05, 9.90, 9.95),
            _mk(11, 59, 9.65, 9.70, 9.60, 9.64),
            _mk(15, 59, 9.40, 9.50, 9.30, 9.35),
        ]
    )
    held = replay_session(
        {"TEST": df_hold},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        hold_plus_r=0.5,
        late_flatten_at=MINUTE_1559,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert held
    assert held[-1].tag == "time"
    assert held[-1].exit_ts.hour == 15


def test_id4_flattens_at_1330() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(9, 31, 10.00, 10.05, 9.90, 9.95),
            _row(13, 30, 9.80, 9.85, 9.70, 9.75),
            _row(15, 59, 9.40, 9.50, 9.30, 9.35),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", -1, 10.50, None, 1.0, "flat1330")
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1330,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert trades
    assert trades[-1].tag == "time"
    assert trades[-1].exit_ts.hour == 13
    assert trades[-1].exit_ts.minute == 30


def test_id3_trail_never_loosens_against_short() -> None:
    ts = datetime(2026, 6, 1, 9, 31, tzinfo=ET)
    pos = Position(
        symbol="TEST",
        side=-1,
        shares=100,
        entry_px=10.0,
        stop=10.5,
        target=None,
        entry_ts=ts,
        risk=50.0,
        tag="atr",
        initial_r=0.5,
        atr=0.20,
        favorable_extreme=10.0,
    )
    book = Book(prior_dv={}, atr_trail=True)
    _update_trail(pos, 10.10, 9.40, 9.40, book)
    assert pos.trail_armed
    s0 = pos.stop
    _update_trail(pos, 9.90, 9.50, 9.70, book)
    assert pos.stop <= s0 + 1e-12
    _update_trail(pos, 9.85, 9.55, 9.60, book)
    assert pos.stop <= s0 + 1e-12
