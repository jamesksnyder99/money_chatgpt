from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from research.book import Book, Position, _update_trail, replay_session
from research.ema15 import bar_end, completed_15m_closes, ema9_at, ema_stack
from research.signals import MINUTE_0945, MINUTE_1159, MINUTE_1559, Signal
from research.strategies13 import five_min_close_below_ema9
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long
from research.strategies30 import harvestable_altitude

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(hh, mm, o, h, l, c, v=5000, day=1):
    return {
        "symbol": "TEST",
        "bar_start": datetime(2026, 6, day, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session_part": "pre" if hh < 9 or (hh == 9 and mm < 30) else "rth",
    }


def _flush_cell_tape(*, px44: float, late_hl: bool = True):
    """Undercut 09:35, HL 09:39 (last_ts < 09:45), 09:44 close is a later 1-min.

    Optional 09:50 HL so the repaired path can still fire after the cell is known.
    """
    rows = [
        _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
        _row(9, 29, 10.10, 10.20, 10.00, 10.10, 2000),
        _row(9, 30, 9.90, 9.95, 9.60, 9.80, 1000),  # undercut 5-min
        _row(9, 35, 9.85, 9.95, 9.78, 9.92, 1000),  # HL, last_ts=09:35 < 09:45
        _row(9, 44, 10.30, 10.50, 9.70, px44, 2000),
    ]
    if late_hl:
        rows.append(_row(9, 50, 9.85, 9.96, 9.82, 9.95, 1000))
    return _bars(rows)


def _admit(df, last_px, orw, dv, ext, *, repaired: bool):
    if not fly_cell_ok(orw, dv, ext):
        return []
    kw = {"max_undercut": 0.06, "tag": "flush|max6"}
    if repaired:
        kw["signal_after"] = FLY_AVAILABLE_AT
    return flush_ring_long(df, last_px, **kw)


def test_a1_future_suffix_0944_close_flip_changes_admission() -> None:
    """09:44 close is future relative to a 09:44 flush last_ts. Repair: cell at 09:45."""
    last_px = 10.00
    pc = 10.00
    orw, dv = 0.06, 200_000.0
    df_pass = _flush_cell_tape(px44=10.40)
    df_fail = _flush_cell_tape(px44=10.20)
    ext_pass = 10.40 / pc - 1.0
    ext_fail = 10.20 / pc - 1.0
    assert fly_cell_ok(orw, dv, ext_pass) is True
    assert fly_cell_ok(orw, dv, ext_fail) is False

    old_pass = _admit(df_pass, last_px, orw, dv, ext_pass, repaired=False)
    old_fail = _admit(df_fail, last_px, orw, dv, ext_fail, repaired=False)
    assert old_pass and bar_time_naive(old_pass[0].signal_ts) < time(9, 45)
    assert old_fail == []
    # Unrepaired: 09:44 close flip changes a pre-09:45 admission (look-ahead).
    assert bool(old_pass) != bool(old_fail)

    new_pass = _admit(df_pass, last_px, orw, dv, ext_pass, repaired=True)
    new_fail = _admit(df_fail, last_px, orw, dv, ext_fail, repaired=True)
    assert all(bar_time_naive(s.signal_ts) >= time(9, 45) for s in new_pass)
    assert new_fail == []
    # After 09:45 the live HL may fire when the cell is known.
    assert new_pass
    assert new_pass[0].signal_ts.minute >= 50


def bar_time_naive(ts: datetime) -> time:
    return ts.timetz().replace(tzinfo=None)


def test_a2_15_minute_boundary() -> None:
    """Sparse 09:55 5-min is complete at 10:00, same cut as 15m ema9/9-21."""
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    stitched = [(t0 + timedelta(minutes=15 * i), 10.0) for i in range(21)]
    # 09:45 15m close dumps to 8.0; complete only at 10:00.
    b945 = datetime(2026, 6, 1, 9, 45, tzinfo=ET)
    stitched.append((b945, 8.0))
    last_ts = datetime(2026, 6, 1, 9, 55, tzinfo=ET)
    end = bar_end(datetime(2026, 6, 1, 9, 55, tzinfo=ET), 5)
    assert end == datetime(2026, 6, 1, 10, 0, tzinfo=ET)
    assert completed_15m_closes(stitched, last_ts)[-1] == 10.0
    assert completed_15m_closes(stitched, end)[-1] == 8.0
    assert ema9_at(stitched, last_ts) != ema9_at(stitched, end)

    rows = [_row(9, 30, 10.00, 10.40, 9.80, 10.10)]
    rows.append(_row(9, 44, 10.10, 10.40, 9.80, 10.00))
    rows.append(_row(9, 55, 9.20, 9.30, 9.00, 9.10, 5000))  # sparse bucket
    df = _bars(rows)
    sigs = five_min_close_below_ema9(df, stitched, or_high=10.40)
    assert sigs
    assert sigs[0].signal_ts == end
    assert ema_stack(stitched, sigs[0].signal_ts) == ema_stack(stitched, end)


def test_a3_1300_silent_when_last_entry_at_1159() -> None:
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
    full = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1559,
        last_entry_at=MINUTE_1559,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert full
    assert all(t.side == -1 for t in full)


def test_a4_crossed_ratchet_exits_next_event() -> None:
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
    crossed = _update_trail(pos, 10.10, 9.20, 9.48, book)
    assert pos.trail_armed
    # extreme 9.20 + ATR 0.20 = 9.40; close 9.48 is already through.
    assert pos.stop <= 9.40 + 1e-12
    assert crossed is True

    df = _bars(
        [
            _row(9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(9, 31, 10.00, 10.05, 9.00, 9.45),  # arm + ratchet through close
            _row(9, 32, 9.44, 9.50, 9.40, 9.42),  # next event
            _row(11, 59, 9.50, 9.60, 9.40, 9.45),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", -1, 10.50, None, 1.0, "atr")
    st = {}
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        atr_trail=True,
        harness_stop=False,
        min_stop_frac=0.0,
        stats=st,
    )
    assert trades
    assert trades[0].exit_ts.hour == 9
    assert trades[0].exit_ts.minute == 32
    assert trades[0].tag in {"trail_cross", "stop"}


def test_a5_1159_dead_is_not_1150_fill() -> None:
    df_later = _bars(
        [
            _row(9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(9, 31, 10.00, 10.05, 9.90, 9.95),
            _row(11, 50, 9.80, 9.85, 9.75, 9.78),
            _row(12, 0, 9.70, 9.75, 9.65, 9.68),
        ]
    )
    sig = Signal(df_later["bar_start"][0], "TEST", -1, 10.50, None, 1.0, "flat")
    st = {}
    trades = replay_session(
        {"TEST": df_later},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
        stats=st,
    )
    assert trades
    assert trades[0].exit_ts.hour == 12
    assert trades[0].exit_ts.minute == 0
    assert trades[0].tag == "unresolved_late"

    df_dead = _bars(
        [
            _row(9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(9, 31, 10.00, 10.05, 9.90, 9.95),
            _row(11, 50, 9.80, 9.85, 9.75, 9.78),
        ]
    )
    st2 = {}
    dead = replay_session(
        {"TEST": df_dead},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
        stats=st2,
    )
    assert st2.get("unresolved_flatten", 0) >= 1
    assert dead
    assert dead[0].tag == "unresolved"
    assert dead[0].exit_ts.hour == 11 and dead[0].exit_ts.minute == 50
    assert abs(dead[0].exit_px - 9.78) < 1e-9
    assert abs(dead[0].exit_px - dead[0].entry_px) > 1e-9


def test_cr1_1010_undercut_fires_0935_does_not_kill() -> None:
    last_px = 10.00
    early_only = _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
            _row(9, 35, 9.90, 9.95, 9.60, 9.80, 1000),
            _row(9, 40, 9.85, 9.95, 9.78, 9.92, 1000),
        ]
    )
    assert flush_ring_long(early_only, last_px, flush_after=MINUTE_0945, max_undercut=0.06) == []

    later = _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00, 1000),
            _row(9, 35, 9.90, 9.95, 9.60, 9.80, 1000),
            _row(10, 10, 9.85, 9.90, 9.55, 9.70, 1000),
            _row(10, 15, 9.75, 9.95, 9.72, 9.92, 1000),
        ]
    )
    sigs = flush_ring_long(later, last_px, flush_after=MINUTE_0945, max_undercut=0.06)
    assert sigs
    assert sigs[0].signal_ts.hour == 10
    assert sigs[0].signal_ts.minute >= 15


def test_cr7_harvestable_skips_thin_and_premarket() -> None:
    pc = 10.0
    confirm = datetime(2026, 6, 1, 8, 0, tzinfo=ET)
    pack = {
        "ts": [
            datetime(2026, 6, 1, 8, 6, tzinfo=ET),
            datetime(2026, 6, 1, 9, 45, tzinfo=ET),
            datetime(2026, 6, 1, 10, 0, tzinfo=ET),
        ],
        "open": [11.2, 11.3, 11.5],
        "high": [11.3, 11.4, 12.0],
        "low": [11.1, 11.2, 11.4],
        "close": [11.25, 11.35, 11.8],
        "vol": [5000, 500, 3000],
    }
    rec = harvestable_altitude(pack, confirm, pc, 0.006)
    assert rec["harvest_ts"].hour == 10
    assert rec["harvestable"] > 0
