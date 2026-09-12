from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.costs import MORNING_DV_NOTIONAL_FRAC, position_shares
from research.signals import MINUTE_0929
from research.strategies22 import (
    hot_gate_0800,
    open_longs_0800,
    skip_cluster,
)

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(sym, hh, mm, o, h, l, c, v):
    return {
        "symbol": sym,
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session_part": "pre" if hh < 9 or (hh == 9 and mm < 30) else "rth",
    }


def _hot(sym: str, *, last_px=10.50, sess_low=10.00, pre_dv=500_000.0, rel=4.0, ext=0.05):
    return {
        "symbol": sym,
        "last_ts": datetime(2026, 6, 1, 8, 0, tzinfo=ET),
        "last_px": last_px,
        "sess_low": sess_low,
        "pre_dv": pre_dv,
        "pre_dv_rel": rel,
        "ext_0800": ext,
    }


def test_gate_rejects_ext_15_and_predv_200k() -> None:
    assert hot_gate_0800(pre_dv=500_000.0, pre_dv_rel=3.0, ext_0800=0.15) is False
    assert hot_gate_0800(pre_dv=200_000.0, pre_dv_rel=5.0, ext_0800=0.05) is False
    assert hot_gate_0800(pre_dv=400_000.0, pre_dv_rel=3.0, ext_0800=0.02) is True
    assert hot_gate_0800(pre_dv=400_000.0, pre_dv_rel=3.0, ext_0800=0.10) is False
    assert hot_gate_0800(pre_dv=400_000.0, pre_dv_rel=3.0, ext_0800=0.099) is True
    assert hot_gate_0800(pre_dv=400_000.0, pre_dv_rel=2.9, ext_0800=0.05) is False


def test_notional_cannot_exceed_5pct_of_predv_0800() -> None:
    morning = 100_000.0
    shares = position_shares(0.10, 10.0, 50_000_000.0, morning_dv=morning)
    assert shares >= 1
    assert shares * 10.0 <= MORNING_DV_NOTIONAL_FRAC * morning + 1e-9
    uncapped = position_shares(0.10, 10.0, 50_000_000.0)
    assert uncapped * 10.0 > MORNING_DV_NOTIONAL_FRAC * morning


def test_id1_flattens_by_0929() -> None:
    df = _bars(
        [
            _row("TEST", 8, 0, 10.40, 10.60, 10.20, 10.50, 1000),
            _row("TEST", 8, 1, 10.52, 10.70, 10.40, 10.55, 1000),
            _row("TEST", 9, 29, 10.80, 10.90, 10.70, 10.85, 1000),
            _row("TEST", 11, 59, 11.00, 11.10, 10.90, 11.00, 1000),
        ]
    )
    sigs = open_longs_0800([_hot("TEST")])
    assert sigs
    assert all(s.side == 1 for s in sigs)
    trades = replay_session(
        {"TEST": df},
        sigs,
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_0929,
        morning_dv={"TEST": 500_000.0},
        allow_premarket=True,
        max_positions=8,
        max_entries=16,
        max_risk_outstanding=1600.0,
        min_stop_frac=0.004,
    )
    assert trades
    assert trades[0].exit_ts == df["bar_start"][2]
    assert trades[0].tag == "time"
    assert trades[0].exit_ts != df["bar_start"][3]


def test_id6_silent_on_20_hot_session() -> None:
    hots = [_hot(f"S{i}", rel=float(20 - i)) for i in range(20)]
    assert skip_cluster(20) is True
    assert skip_cluster(15) is False
    assert open_longs_0800(hots, skip_if_cluster=True) == []
    assert len(open_longs_0800(hots, skip_if_cluster=False)) == 20
    bars = {}
    for i in range(20):
        sym = f"S{i}"
        bars[sym] = _bars(
            [
                _row(sym, 8, 0, 10.40, 10.60, 10.20, 10.50, 1000),
                _row(sym, 8, 1, 10.52, 10.70, 10.40, 10.55, 1000),
                _row(sym, 9, 29, 10.80, 10.90, 10.70, 10.85, 1000),
            ]
        )
    trades = replay_session(
        bars,
        open_longs_0800(hots, skip_if_cluster=True),
        {s: 50_000_000.0 for s in bars},
        flatten_at=MINUTE_0929,
        morning_dv={s: 500_000.0 for s in bars},
        allow_premarket=True,
        max_positions=8,
        max_entries=16,
        max_risk_outstanding=1600.0,
    )
    assert trades == []
