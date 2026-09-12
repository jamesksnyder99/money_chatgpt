from datetime import datetime, time
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.signals import MINUTE_1559, bar_time
from research.strategies37 import noon_hold_long, power_hour_long, relaunch_long

ET = ZoneInfo("America/New_York")


def _pack_from_rows(rows: list[dict]) -> dict:
    return {
        "ts": [r["bar_start"] for r in rows],
        "open": [r["open"] for r in rows],
        "high": [r["high"] for r in rows],
        "low": [r["low"] for r in rows],
        "close": [r["close"] for r in rows],
        "vol": [r["volume"] for r in rows],
    }


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


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def test_id0_silent_if_1100_ext_is_plus_2pct() -> None:
    pc = 10.0
    rows = [_row(11, 0, 10.15, 10.25, 10.10, 10.20)]  # +2% vs pc
    for mm in range(1, 60):
        rows.append(_row(11, mm, 11.10, 11.25, 11.05, 11.20))  # +12% at 11:59, range tight
    rows.append(_row(12, 0, 11.20, 11.30, 11.15, 11.22))
    rows.append(_row(12, 1, 11.22, 11.30, 11.18, 11.25))
    pack = _pack_from_rows(rows)
    df = _bars(rows)
    assert noon_hold_long(df, pack, pc, tight=True, rvol=3.0) == []


def test_id3_silent_if_no_5pct_pullback() -> None:
    pc = 10.0
    rows = [_row(10, 0, 10.50, 11.30, 10.40, 11.20)]
    rows.append(_row(10, 1, 11.20, 11.40, 10.90, 11.10))  # confirm
    for mm in range(2, 60):
        px = 11.10 + mm * 0.01
        rows.append(_row(10, mm, px, px + 0.10, px - 0.05, px))
    # 11:xx grind, no 5% dip from running high
    for mm in range(0, 60):
        px = 11.70 + mm * 0.005
        rows.append(_row(11, mm, px, px + 0.08, px - 0.04, px))
    hi = 12.00
    rows.append(_row(12, 0, hi, hi + 0.05, hi - 0.04, hi + 0.10))  # close above pre-noon high
    rows.append(_row(12, 1, hi + 0.10, hi + 0.15, hi + 0.05, hi + 0.12))
    pack = _pack_from_rows(rows)
    assert relaunch_long(_bars(rows), pack, pc) == []


def test_id4_never_enters_before_1430() -> None:
    pc = 10.0
    rows = [_row(11, 59, 10.00, 10.20, 9.90, 10.00)]
    for mm in range(0, 60):
        rows.append(_row(12, mm, 10.50, 10.70, 10.40, 10.60))
    rows.append(_row(13, 0, 10.80, 10.90, 10.70, 10.85))
    pack_early = _pack_from_rows(rows)
    assert power_hour_long(_bars(rows), pack_early, pc) == []

    rows = [_row(11, 59, 10.00, 10.10, 9.95, 10.00)]
    rows.append(_row(12, 0, 10.00, 10.10, 9.95, 10.02))
    for mm in range(0, 30):
        rows.append(_row(13, 30 + mm if mm < 30 else 13, 10.40, 10.50, 10.35, 10.45))
    # 13:30-14:29: climb to +8% vs noon with tight range, near high
    for mm in range(0, 30):
        px = 10.70 + mm * 0.004
        rows.append(_row(14, mm, px, px + 0.03, px - 0.02, px))
    rows.append(_row(14, 30, 10.82, 10.88, 10.80, 10.85))
    rows.append(_row(14, 31, 10.85, 10.90, 10.82, 10.86))
    rows.append(_row(15, 59, 10.80, 10.85, 10.75, 10.80))
    pack = _pack_from_rows(rows)
    sigs = power_hour_long(_bars(rows), pack, pc, tag="power|1430|flat1559")
    assert sigs
    assert all(s.side == 1 for s in sigs)
    assert all(bar_time(s.signal_ts) >= time(14, 30) for s in sigs)
    trades = replay_session(
        {"TEST": _bars(rows)},
        sigs,
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1559,
        last_entry_at=MINUTE_1559,
        harness_stop=True,
        min_stop_frac=0.0,
        cost_gate=False,
    )
    assert trades
    assert all(t.side == 1 for t in trades)
    assert all(bar_time(t.entry_ts) >= time(14, 30) for t in trades)


def test_continuation_long_only() -> None:
    pc = 10.0
    rows = [_row(11, 0, 10.80, 10.90, 10.70, 10.85)]
    for mm in range(1, 60):
        rows.append(_row(11, mm, 11.10, 11.25, 11.05, 11.20))
    rows.append(_row(12, 0, 11.20, 11.30, 11.15, 11.22))
    rows.append(_row(12, 1, 11.22, 11.28, 11.18, 11.24))
    pack = _pack_from_rows(rows)
    df = _bars(rows)
    sigs = noon_hold_long(df, pack, pc, tight=True, rvol=3.0)
    assert sigs
    assert all(s.side == 1 for s in sigs)
    sigs2 = noon_hold_long(df, pack, pc, tight=False)
    assert all(s.side == 1 for s in sigs2)
