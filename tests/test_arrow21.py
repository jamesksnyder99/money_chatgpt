from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.arrow21 import CAP3
from research.book import concurrent_stats, replay_session
from research.signals import MINUTE_1159
from research.strategies21 import fade_open_short, gap1_open_long, pullback_long, rth_open_gap_ok

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


def test_id1_silent_if_never_tags_0929_px_or_vwap() -> None:
    last_px = 10.00
    df = _bars(
        [
            _row("TEST", 9, 29, 10.00, 10.10, 9.90, 10.00, 1000),
            _row("TEST", 9, 30, 11.00, 11.20, 10.90, 11.10, 1000),
            _row("TEST", 9, 31, 11.15, 11.35, 11.12, 11.25, 1000),
            _row("TEST", 9, 32, 11.25, 11.45, 11.22, 11.35, 1000),
            _row("TEST", 11, 59, 11.35, 11.45, 11.25, 11.30, 1000),
        ]
    )
    assert pullback_long(df, last_px) == []


def test_id1_fires_when_bar_tags_0929_px() -> None:
    last_px = 10.50
    df = _bars(
        [
            _row("TEST", 9, 29, 10.40, 10.60, 10.30, 10.50, 1000),
            _row("TEST", 9, 30, 10.70, 10.80, 10.70, 10.75, 1000),
            _row("TEST", 9, 45, 10.60, 10.70, 10.45, 10.65, 1000),
            _row("TEST", 11, 59, 10.60, 10.70, 10.50, 10.55, 1000),
        ]
    )
    sigs = pullback_long(df, last_px)
    assert len(sigs) == 1
    assert sigs[0].side == 1
    assert sigs[0].tag == "hot_pullback"
    assert sigs[0].stop == 10.45


def test_id2_rejects_plus_2pct_930_gap_vs_0929() -> None:
    last_px = 10.00
    ts = datetime(2026, 6, 1, 9, 29, tzinfo=ET)
    df = _bars(
        [
            _row("TEST", 9, 29, 9.90, 10.10, 9.80, 10.00, 1000),
            _row("TEST", 9, 30, 10.20, 10.30, 10.10, 10.25, 1000),
            _row("TEST", 11, 59, 10.20, 10.30, 10.10, 10.15, 1000),
        ]
    )
    assert rth_open_gap_ok(10.20, last_px) is False
    assert gap1_open_long(df, ts, "TEST", 9.80, last_px, 4.0) == []
    df_ok = _bars(
        [
            _row("TEST", 9, 29, 9.90, 10.10, 9.80, 10.00, 1000),
            _row("TEST", 9, 30, 10.05, 10.20, 9.90, 10.10, 1000),
            _row("TEST", 11, 59, 10.10, 10.20, 10.00, 10.05, 1000),
        ]
    )
    assert rth_open_gap_ok(10.05, last_px) is True
    sigs = gap1_open_long(df_ok, ts, "TEST", 9.80, last_px, 4.0)
    assert sigs
    assert all(s.side == 1 for s in sigs)


def test_id6_emits_only_shorts() -> None:
    ts = datetime(2026, 6, 1, 9, 29, tzinfo=ET)
    sigs = fade_open_short(ts, "TEST", sess_high=11.00, last_px=10.50, score=4.0)
    assert sigs
    assert all(s.side == -1 for s in sigs)
    assert all(s.tag == "hot_fade" for s in sigs)
    assert all(s.stop == 11.00 for s in sigs)


def test_id5_never_exceeds_3_concurrent_on_10_name_fixture() -> None:
    last_px = 10.50
    bars = {}
    sigs = []
    for i in range(10):
        sym = f"S{i}"
        df = _bars(
            [
                _row(sym, 9, 29, 10.40, 10.60, 10.30, 10.50, 1000),
                _row(sym, 9, 30, 10.70, 10.80, 10.70, 10.75, 1000),
                _row(sym, 9, 45, 10.60, 10.70, 10.45, 10.65, 1000),
                _row(sym, 9, 46, 10.66, 10.70, 10.50, 10.60, 1000),
                _row(sym, 11, 59, 10.55, 10.65, 10.50, 10.58, 1000),
            ]
        )
        bars[sym] = df
        got = pullback_long(df, last_px, score=float(10 - i))
        assert got
        sigs.extend(got)
    dv = {s: 50_000_000.0 for s in bars}
    trades = replay_session(
        bars,
        sigs,
        dv,
        flatten_at=MINUTE_1159,
        **CAP3,
    )
    peak, _mean = concurrent_stats(trades)
    assert peak <= 3
    assert all(t.side == 1 for t in trades)
    assert len(trades) <= 16
