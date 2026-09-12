from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from research.book import Book, Position, _update_trail, replay_session
from research.ema15 import ema_stack
from research.signals import MINUTE_1159, MINUTE_1559, Signal
from research.strategies15 import control_c5_ema9
from research.strategies32 import conjunction_c5_ema9

ET = ZoneInfo("America/New_York")

A31_LOCK_N_DEV = 216
A31_LOCK_N_HOL = 94


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


def _long_then_dump() -> list:
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    stitched = [(t0 + timedelta(minutes=15 * i), 8.0 + 0.05 * i) for i in range(22)]
    stitched.append((datetime(2026, 6, 1, 9, 45, tzinfo=ET), 6.0))
    return stitched


def test_id0_control_is_a31_lock() -> None:
    from research.arrow32 import CONTROL_KW, A31_LOCK_N_DEV as n_d, A31_LOCK_N_HOL as n_h

    assert n_d == 216
    assert n_h == 94
    assert CONTROL_KW["last_entry_at"] == MINUTE_1159
    assert CONTROL_KW["flatten_at"] == MINUTE_1559
    assert CONTROL_KW["atr_trail"] is True


def test_id1_conjunction_waits_for_both() -> None:
    """09:50 below EMA9 but long regime; 10:05 both true → only conjunction emits 10:05."""
    stitched = _long_then_dump()
    rows = [
        _row(9, 30, 10.00, 10.40, 9.80, 10.10),
        _row(9, 44, 10.10, 10.40, 9.80, 10.00),
    ]
    for mm in range(45, 50):
        rows.append(_row(9, mm, 7.60, 7.80, 7.40, 7.50))
    for mm in range(0, 5):
        rows.append(_row(10, mm, 7.10, 7.30, 6.90, 7.00))
    df = _bars(rows)
    end_0950 = datetime(2026, 6, 1, 9, 50, tzinfo=ET)
    end_1005 = datetime(2026, 6, 1, 10, 5, tzinfo=ET)
    assert ema_stack(stitched, end_0950) == "long"
    assert ema_stack(stitched, end_1005) == "short"

    ctrl = control_c5_ema9(df, stitched, or_high=10.40)
    assert ctrl
    assert ctrl[0].signal_ts == end_0950

    conj, ledger = conjunction_c5_ema9(df, stitched, or_high=10.40)
    assert conj
    assert conj[0].signal_ts == end_1005
    assert all(s.side == -1 for s in conj)
    assert ledger["first_primitive"] == "close_below_ema9"
    assert ledger["veto_reason"] == "regime_not_short"
    assert ledger["conjunction_ts"] == end_1005


def test_id5_silent_if_plus1r_at_minute_15() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(9, 31, 10.00, 10.05, 9.90, 9.95),
            _row(9, 46, 9.40, 9.50, 9.30, 9.40),  # +1R (r=0.50 from stop 10.50)
            _row(9, 51, 9.42, 9.50, 9.35, 9.38),  # T+20
            _row(9, 52, 9.38, 9.45, 9.30, 9.35),
            _row(11, 59, 9.20, 9.30, 9.10, 9.15),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", -1, 10.50, None, 1.0, "lock")
    st = {}
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        last_entry_at=MINUTE_1159,
        atr_trail=True,
        unarmed_red_minutes=20,
        harness_stop=False,
        min_stop_frac=0.0,
        stats=st,
    )
    assert trades
    assert all(t.tag != "unarmed_red" for t in trades)
    assert st.get("unarmed_red_exits", 0) == 0


def test_id2_id3_trail_never_loosens() -> None:
    ts = datetime(2026, 6, 1, 9, 31, tzinfo=ET)
    for mult in (0.75, 1.5):
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
        book = Book(prior_dv={}, atr_trail=True, trail_atr_mult=mult)
        _update_trail(pos, 10.10, 9.20, 9.40, book)
        assert pos.trail_armed
        s0 = pos.stop
        _update_trail(pos, 9.90, 9.50, 9.70, book)
        assert pos.stop <= s0 + 1e-12
        _update_trail(pos, 9.85, 9.55, 9.60, book)
        assert pos.stop <= s0 + 1e-12


def test_a3_last_entry_at_blocks_1300() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(9, 31, 10.00, 10.05, 9.90, 9.95),
            _row(13, 0, 9.80, 9.85, 9.70, 9.75),
            _row(13, 1, 9.75, 9.80, 9.70, 9.72),
            _row(15, 59, 9.40, 9.50, 9.30, 9.35),
        ]
    )
    sig = Signal(
        datetime(2026, 6, 1, 13, 0, tzinfo=ET),
        "TEST",
        -1,
        10.50,
        None,
        1.0,
        "late",
    )
    locked = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1559,
        last_entry_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert locked == []
