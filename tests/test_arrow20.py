from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.signals import MINUTE_1559, Signal
from research.strategies20 import gap_and_go_long, hot_gate

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(hh, mm, o, h, l, c, v):
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


def test_hot_gate_rejects_too_little_and_too_much_extension() -> None:
    assert hot_gate(pre_dv=300_000.0, pre_dv_rel=3.0, ext_0929=0.01) is False
    assert hot_gate(pre_dv=300_000.0, pre_dv_rel=3.0, ext_0929=0.20) is False
    assert hot_gate(pre_dv=300_000.0, pre_dv_rel=3.0, ext_0929=0.03) is True
    assert hot_gate(pre_dv=300_000.0, pre_dv_rel=3.0, ext_0929=0.149) is True
    assert hot_gate(pre_dv=300_000.0, pre_dv_rel=3.0, ext_0929=0.15) is False


def test_hot_gate_rejects_predv_100k() -> None:
    assert hot_gate(pre_dv=100_000.0, pre_dv_rel=5.0, ext_0929=0.05) is False
    assert hot_gate(pre_dv=250_000.0, pre_dv_rel=3.0, ext_0929=0.05) is True
    assert hot_gate(pre_dv=250_000.0, pre_dv_rel=None, ext_0929=0.05) is False


def test_id1_emits_no_shorts() -> None:
    ts = datetime(2026, 6, 1, 9, 29, tzinfo=ET)
    sigs = gap_and_go_long(ts, "TEST", sess_low=10.00, last_px=10.50, score=4.0)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_1559_flatten_on_fixture_past_noon() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row(9, 31, 10.10, 10.20, 10.00, 10.15, 1000),
            _row(12, 5, 10.20, 10.40, 10.10, 10.30, 1000),
            _row(15, 59, 10.25, 10.30, 10.20, 10.22, 1000),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", 1, 9.50, None, 1.0, "test")
    trades = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1559,
    )
    assert trades
    assert trades[0].exit_ts == df["bar_start"][3]
    assert trades[0].tag == "time"
