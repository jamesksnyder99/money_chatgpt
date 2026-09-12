from datetime import datetime, time
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.harness import confirmed_launch
from research.signals import MINUTE_1559, bar_time
from research.strategies36 import WIN_AM, WIN_PM, rth_birth_long

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


def test_wick_12pct_close_6pct_is_not_a_launch() -> None:
    pc = 10.0
    rows = [
        _row(9, 45, 10.20, 11.20, 10.10, 10.60),  # +12% wick, close +6%
        _row(9, 46, 10.60, 10.70, 10.50, 10.65),
    ]
    rec = confirmed_launch(_pack_from_rows(rows), pc)
    assert rec["confirmed"] is False
    df = _bars(rows)
    assert rth_birth_long(df, _pack_from_rows(rows), pc, WIN_AM) == []


def test_0940_launch_is_not_in_id0() -> None:
    pc = 10.0
    rows = [_row(9, 25 + i, 10.0, 10.2, 9.8, 10.0) for i in range(15)]
    rows.append(_row(9, 40, 10.50, 11.30, 10.40, 11.20))  # launch close
    rows.append(_row(9, 41, 11.20, 11.40, 10.90, 11.10))  # confirm
    rows.append(_row(9, 46, 11.10, 11.20, 11.00, 11.15))
    pack = _pack_from_rows(rows)
    rec = confirmed_launch(pack, pc)
    assert rec["confirmed"] is True
    assert rec["launch_close_ts"].hour == 9
    assert rec["launch_close_ts"].minute == 40
    sigs = rth_birth_long(_bars(rows), pack, pc, WIN_AM, tag="birth|0945-1159|flat1159")
    assert sigs == []


def test_id4_never_enters_before_1200() -> None:
    pc = 10.0
    morning = [_row(9, 30 + i, 10.0, 10.2, 9.8, 10.0) for i in range(15)]
    morning.append(_row(9, 50, 10.50, 11.30, 10.40, 11.20))
    morning.append(_row(9, 51, 11.20, 11.40, 10.90, 11.10))
    morning.append(_row(12, 0, 11.10, 11.20, 11.00, 11.15))
    pack_m = _pack_from_rows(morning)
    assert confirmed_launch(pack_m, pc)["confirmed"] is True
    assert rth_birth_long(_bars(morning), pack_m, pc, WIN_PM) == []

    rows = [_row(11, 45 + i, 10.0, 10.2, 9.8, 10.0) for i in range(15)]
    rows.append(_row(12, 0, 10.50, 11.30, 10.40, 11.20))
    rows.append(_row(12, 1, 11.20, 11.40, 10.90, 11.10))
    rows.append(_row(12, 2, 11.10, 11.30, 11.00, 11.20))
    rows.append(_row(15, 59, 11.00, 11.10, 10.90, 11.00))
    pack = _pack_from_rows(rows)
    rec = confirmed_launch(pack, pc)
    assert rec["confirmed"] is True
    sigs = rth_birth_long(_bars(rows), pack, pc, WIN_PM, tag="birth|1200-1500|atr1559")
    assert sigs
    assert all(s.side == 1 for s in sigs)
    assert all(bar_time(s.signal_ts) >= time(12, 0) for s in sigs)
    trades = replay_session(
        {"TEST": _bars(rows)},
        sigs,
        {"TEST": 50_000_000.0},
        flatten_at=MINUTE_1559,
        last_entry_at=MINUTE_1559,
        harness_stop=True,
        atr_trail=True,
        min_stop_frac=0.0,
        cost_gate=False,
    )
    assert trades
    assert all(t.side == 1 for t in trades)
    assert all(bar_time(t.entry_ts) >= time(12, 0) for t in trades)


def test_birth_long_only() -> None:
    pc = 10.0
    rows = [_row(9, 30 + i, 10.0, 10.2, 9.8, 10.0) for i in range(15)]
    rows.append(_row(9, 50, 10.50, 11.30, 10.40, 11.20))
    rows.append(_row(9, 51, 11.20, 11.40, 10.90, 11.10))
    rows.append(_row(9, 52, 11.10, 11.20, 11.00, 11.15))
    sigs = rth_birth_long(_bars(rows), _pack_from_rows(rows), pc, WIN_AM)
    assert sigs
    assert all(s.side == 1 for s in sigs)
