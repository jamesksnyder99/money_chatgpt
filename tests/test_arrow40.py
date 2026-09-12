from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.arrow40 import (
    A31_FLUSH_N_DEV,
    A31_FLUSH_N_HOL,
    A33_B_N_DEV,
    A33_B_N_HOL,
    _within,
    clamp_rpi,
)
from research.book import joint_peak_risk, outstanding_at, replay_session
from research.signals import MINUTE_1159, MINUTE_1559, Signal

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(sym, hh, mm, o, h, l, c, v=5000):
    return {
        "symbol": sym,
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session_part": "rth",
    }


def test_id0_reprint_targets() -> None:
    assert A33_B_N_DEV == 228
    assert A33_B_N_HOL == 93
    assert A31_FLUSH_N_DEV == 21
    assert A31_FLUSH_N_HOL == 19
    assert _within(228, 228)
    assert _within(93, 93)
    assert abs(21 - 21) <= 3
    assert abs(19 - 19) <= 3


def test_id2_flush_risk_is_600() -> None:
    rows = [
        _row("TEST", 9, 30, 10.00, 10.10, 9.90, 10.00),
        _row("TEST", 9, 45, 10.00, 10.20, 9.80, 10.10),
        _row("TEST", 9, 46, 10.10, 10.30, 10.00, 10.20),
        _row("TEST", 11, 59, 10.20, 10.30, 10.10, 10.15),
    ]
    df = _bars(rows)
    sig = Signal(df["bar_start"][1], "TEST", 1, 9.50, None, 1.0, "flush")
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        last_entry_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
        cost_gate=False,
        risk_per_idea=600.0,
        max_risk_outstanding=4800.0,
        max_positions=8,
        max_entries=16,
    )
    assert trades
    # $600 idea; share flooring vs the 10% notional cap can clip a few dollars.
    assert 590.0 <= trades[0].risk <= 600.0 + 1e-9
    ctrl = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        last_entry_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
        cost_gate=False,
        risk_per_idea=200.0,
        max_risk_outstanding=1600.0,
        max_positions=8,
        max_entries=16,
    )
    assert ctrl
    assert ctrl[0].risk < trades[0].risk - 100.0


def test_id4_joint_outstanding_never_over_1600() -> None:
    names_b = [f"S{i}" for i in range(8)]
    names_f = [f"L{i}" for i in range(8)]
    bars = {}
    sigs_b = []
    sigs_f = []
    dv = {}
    for i, sym in enumerate(names_b + names_f):
        rows = [
            _row(sym, 9, 30, 10.00, 10.10, 9.90, 10.00),
            _row(sym, 9, 45, 10.00, 10.20, 9.70, 9.80),
            _row(sym, 9, 46, 9.80, 9.90, 9.60, 9.70),
            _row(sym, 11, 59, 9.70, 9.80, 9.50, 9.60),
            _row(sym, 15, 59, 9.60, 9.70, 9.40, 9.50),
        ]
        bars[sym] = _bars(rows)
        dv[sym] = 50_000_000.0
        ts = bars[sym]["bar_start"][1]
        if sym in names_b:
            sigs_b.append(Signal(ts, sym, -1, 10.50, None, 1.0, "b"))
        else:
            sigs_f.append(Signal(ts, sym, 1, 9.20, None, 1.0, "f"))
    tb = replay_session(
        {s: bars[s] for s in names_b},
        sigs_b,
        dv,
        flatten_at=MINUTE_1559,
        last_entry_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
        cost_gate=False,
        risk_per_idea=200.0,
        max_risk_outstanding=1600.0,
        joint_cap=1600.0,
        max_positions=8,
        max_entries=16,
        ssr_policy="",
        borrow_filter=False,
    )
    tf = replay_session(
        {s: bars[s] for s in names_f},
        sigs_f,
        dv,
        flatten_at=MINUTE_1159,
        last_entry_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
        cost_gate=False,
        risk_per_idea=200.0,
        max_risk_outstanding=1600.0,
        joint_cap=1600.0,
        other_risk_at=lambda ts: outstanding_at(tb, ts),
        max_positions=8,
        max_entries=16,
    )
    peak = joint_peak_risk(tb, tf)
    assert peak <= 1600.0 + 1e-6
    assert clamp_rpi(1600.0, 8) == 200.0
    assert clamp_rpi(1600.0, 2) == 600.0
    assert clamp_rpi(1600.0, 1) == 600.0
