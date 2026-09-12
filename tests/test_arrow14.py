from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import polars as pl

from research.book import concurrent_stats, replay_session
from research.signals import Signal
from research.strategies13 import five_min_close_below_ema9
from research.strategies14 import union_c5_or_orlow

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


def _session_bars(sym: str) -> pl.DataFrame:
    return _bars(
        [
            _row(sym, 9, 30, 10.0, 10.2, 9.9, 10.1, 5000),
            _row(sym, 9, 31, 10.1, 10.2, 10.0, 10.15, 5000),
            _row(sym, 11, 59, 10.0, 10.1, 9.9, 10.0, 5000),
        ]
    )


def _names(n: int) -> tuple[dict, list, dict]:
    bars = {}
    sigs = []
    for i in range(n):
        sym = f"S{i}"
        bars[sym] = _session_bars(sym)
        sigs.append(Signal(bars[sym]["bar_start"][0], sym, -1, 10.50, None, float(n - i), "test"))
    dv = {s: 50_000_000.0 for s in bars}
    return bars, sigs, dv


def test_cap5_never_exceeds_five_concurrent() -> None:
    bars, sigs, dv = _names(8)
    trades = replay_session(
        bars,
        sigs,
        dv,
        max_positions=5,
        max_entries=10,
        max_risk_outstanding=1000.0,
    )
    peak, _mean = concurrent_stats(trades)
    assert peak <= 5
    assert all(t.side == -1 for t in trades)


def test_cap8_reaches_six_plus_on_ten_name_fixture() -> None:
    bars, sigs, dv = _names(10)
    trades = replay_session(
        bars,
        sigs,
        dv,
        max_positions=8,
        max_entries=16,
        max_risk_outstanding=1600.0,
    )
    peak, _mean = concurrent_stats(trades)
    assert peak >= 6
    assert peak <= 8
    assert len({t.symbol for t in trades}) >= 6


def test_union_fires_on_or_low_without_ema9_cross() -> None:
    rows = [
        _row("TEST", 9, 30, 10.00, 10.40, 9.80, 10.10, 1000),
        _row("TEST", 9, 44, 10.10, 10.40, 9.80, 10.00, 1000),  # OR low=9.80
    ]
    for mm in range(45, 50):
        # 5-min close stays ~10.2, above ema9=10; 09:45 1m close punches OR low
        if mm == 45:
            rows.append(_row("TEST", 9, mm, 9.70, 9.90, 9.60, 9.70, 1000))
        else:
            rows.append(_row("TEST", 9, mm, 10.20, 10.30, 10.10, 10.25, 1000))
    rows.append(_row("TEST", 11, 59, 10.00, 10.10, 9.90, 10.00, 1000))
    df = _bars(rows)
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    stitched = [(t0 + timedelta(minutes=15 * i), 10.0) for i in range(30)]
    assert five_min_close_below_ema9(df, stitched, or_high=10.40) == []
    sigs = union_c5_or_orlow(df, stitched)
    assert sigs
    assert all(s.side == -1 for s in sigs)
    assert sigs[0].tag == "union_or_low"


def test_helpers_shorts_only() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.40, 9.50, 10.00, 1000),
            _row("TEST", 9, 44, 10.00, 10.40, 9.50, 9.90, 1000),
            _row("TEST", 9, 45, 9.40, 9.50, 9.20, 9.30, 1000),
            _row("TEST", 11, 59, 9.20, 9.30, 9.10, 9.20, 1000),
        ]
    )
    t0 = datetime(2026, 5, 29, 7, 30, tzinfo=ET)
    stitched = [(t0 + timedelta(minutes=15 * i), 10.0) for i in range(30)]
    sigs = union_c5_or_orlow(df, stitched)
    assert sigs
    assert all(s.side == -1 for s in sigs)
