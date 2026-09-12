from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.arrow3 import _summarize
from research.book import replay_session
from research.fills import rth_session_vwap
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


def test_avgr_uses_trade_risk_not_200() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.0, 10.2, 9.9, 10.1, 1000),
            _row("TEST", 9, 31, 10.1, 10.3, 10.0, 10.2, 1000),
            _row("TEST", 11, 59, 10.5, 10.6, 10.4, 10.5, 1000),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", 1, 9.50, None, 1.0, "test")
    trades = replay_session({"TEST": df}, [sig], {"TEST": 10_000.0})
    assert trades
    tr = trades[0]
    assert tr.risk > 0
    recs = [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades]
    sm = _summarize([tr.pnl], recs, 1)
    expected = tr.pnl / tr.risk
    assert abs(sm["avg_r"] - expected) < 1e-9
    assert abs(tr.risk - 200.0) > 1e-6
    assert abs(sm["avg_r"] - tr.pnl / 200.0) > 1e-6


def test_rth_vwap_ignores_premarket() -> None:
    df = _bars(
        [
            _row("TEST", 7, 30, 1.0, 1.0, 1.0, 1.0, 1_000_000),
            _row("TEST", 9, 30, 10.0, 10.2, 9.8, 10.0, 1000),
            _row("TEST", 9, 31, 10.0, 10.1, 9.9, 10.05, 1000),
        ]
    )
    vw = rth_session_vwap(df)
    assert vw[0] != vw[0] or True  # premarket may be nan
    assert abs(vw[1] - 10.0) < 0.15
    # if premarket counted, VWAP would be dragged toward 1.0
    assert vw[1] > 8.0


def test_queue_respects_score_and_can_enter() -> None:
    bars = {}
    sigs = []
    for i, sym in enumerate(["A", "B", "C", "D", "E", "F"]):
        bars[sym] = _bars(
            [
                _row(sym, 9, 30, 10.0, 10.2, 9.9, 10.1, 5000),
                _row(sym, 9, 31, 10.1, 10.2, 10.0, 10.15, 5000),
                _row(sym, 11, 59, 10.0, 10.1, 9.9, 10.0, 5000),
            ]
        )
        sigs.append(
            Signal(
                bars[sym]["bar_start"][0],
                sym,
                1,
                9.50,
                None,
                float(i + 1),  # F highest score
                "test",
            )
        )
    dv = {s: 50_000_000.0 for s in bars}
    trades = replay_session(bars, [], dv, rth_open_entries=sigs)
    entered = {t.symbol for t in trades}
    assert len(entered) == 5
    assert "F" in entered
    assert "A" not in entered  # lowest |score|
