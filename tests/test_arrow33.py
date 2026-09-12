from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.signals import MINUTE_1159, Signal

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


def _tape(sym: str) -> pl.DataFrame:
    return _bars(
        [
            _row(sym, 9, 30, 10.00, 10.10, 9.95, 10.00),
            _row(sym, 9, 31, 10.00, 10.05, 9.90, 9.95),
            _row(sym, 11, 59, 9.70, 9.80, 9.60, 9.65),
        ]
    )


def test_id0_reprints_a32_conj_n() -> None:
    from research.arrow33 import A32_CONJ_N_DEV, A32_CONJ_N_HOL, CONTROL_ID

    assert A32_CONJ_N_DEV == 244
    assert A32_CONJ_N_HOL == 98
    assert CONTROL_ID == "B|conj|atr1559|lock"


def test_unresolved_never_entry_px() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.10, 9.95, 10.00),
            _row("TEST", 9, 31, 10.00, 10.05, 9.90, 9.95),
            _row("TEST", 11, 50, 9.80, 9.85, 9.75, 9.78),
            _row("TEST", 11, 59, 9.70, 9.75, 9.65, 9.68, 0),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", -1, 10.50, None, 1.0, "t")
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1159,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert trades
    assert trades[0].tag == "unresolved"
    assert abs(trades[0].exit_px - trades[0].entry_px) > 1e-9
    assert abs(trades[0].exit_px - 9.78) < 1e-9


def test_id1_cap12_admits_ninth() -> None:
    syms = [f"N{i}" for i in range(9)]
    bars = {s: _tape(s) for s in syms}
    ts = bars[syms[0]]["bar_start"][0]
    sigs = [Signal(ts, s, -1, 10.50, None, 1.0 - i * 0.01, "c") for i, s in enumerate(syms)]
    dv = {s: 50_000_000.0 for s in syms}
    trades = replay_session(
        bars,
        sigs,
        dv,
        flatten_at=MINUTE_1159,
        last_entry_at=MINUTE_1159,
        max_positions=12,
        max_entries=24,
        max_risk_outstanding=2400.0,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert len({t.symbol for t in trades}) == 9


def test_id3_fills_larger_gaps_first() -> None:
    ts = datetime(2026, 6, 1, 9, 30, tzinfo=ET)
    bars = {"SMALL": _tape("SMALL"), "BIG": _tape("BIG"), "MID": _tape("MID")}
    sigs = [
        Signal(ts, "SMALL", -1, 10.50, None, 0.015, "g"),
        Signal(ts, "BIG", -1, 10.50, None, 0.050, "g"),
        Signal(ts, "MID", -1, 10.50, None, 0.025, "g"),
    ]
    dv = {s: 50_000_000.0 for s in bars}
    trades = replay_session(
        bars,
        sigs,
        dv,
        flatten_at=MINUTE_1159,
        last_entry_at=MINUTE_1159,
        max_positions=1,
        max_entries=2,
        max_risk_outstanding=200.0,
        harness_stop=False,
        min_stop_frac=0.0,
    )
    assert trades
    assert {t.symbol for t in trades} == {"BIG"}
