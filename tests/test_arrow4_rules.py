from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.signals import Signal
from research.strategies import or_break_signals, swing_signals

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(d, hh, mm, o, h, l, c, v, symbol="TEST"):
    return {
        "symbol": symbol,
        "bar_start": datetime(2026, 6, d, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "rth",
    }


def test_or_break_does_not_fire_before_0945() -> None:
    # 09:30–09:44 range 10–11. Close 11.5 at 09:44 must not signal.
    rows = []
    for m in range(30, 45):
        rows.append(_row(1, 9, m, 10.5, 11.0, 10.0, 10.5, 1000))
    rows.append(_row(1, 9, 44, 10.5, 11.0, 10.0, 11.5, 1000))  # close beyond high but 09:44
    rows.append(_row(1, 9, 45, 11.6, 11.7, 11.5, 11.6, 1000))
    rows.append(_row(1, 11, 59, 11.0, 11.1, 10.9, 11.0, 1000))
    df = _bars(rows)
    # If we only have 09:44 beyond, no signal after filtering >= 09:45 with close>11
    early = df.filter(pl.col("bar_start").dt.time() <= datetime(2026, 6, 1, 9, 44).time())
    assert or_break_signals(early) == []
    sigs = or_break_signals(df)
    assert sigs, "expected break after 09:45"
    assert sigs[0].signal_ts.hour == 9 and sigs[0].signal_ts.minute >= 45
    assert sigs[0].side == 1


def test_swing_no_trade_without_next_session() -> None:
    rows = [_row(1, 9, 30, 10.0, 10.2, 9.9, 10.1, 5000)]
    for m in range(30, 51):
        rows.append(_row(1, 11, m, 10.3, 10.4, 10.2, 10.35, 5000))
    rows.append(_row(1, 11, 59, 10.3, 10.4, 10.2, 10.3, 1000))
    day1 = _bars(rows)
    sigs = swing_signals(day1, session_vol_so_far=80_000, median_full_vol=10_000)
    assert sigs and sigs[0].overnight
    # same-day replay must not fill overnight signals
    trades = replay_session({"TEST": day1}, sigs, {"TEST": 50_000_000})
    assert trades == []


def test_swing_fills_next_session_open_not_signal_day() -> None:
    sig_rows = [_row(1, 9, 30, 10.0, 10.1, 9.9, 10.05, 4000)]
    for m in range(30, 51):
        sig_rows.append(_row(1, 11, m, 10.3, 10.5, 10.2, 10.40, 4000))
    sig_rows.append(_row(1, 11, 59, 10.4, 10.5, 10.3, 10.4, 1000))
    day1 = _bars(sig_rows)
    sigs = swing_signals(day1, session_vol_so_far=80_000, median_full_vol=10_000)
    assert sigs
    nxt_rows = [
        _row(2, 9, 30, 10.50, 10.6, 10.4, 10.55, 3000),
        _row(2, 9, 31, 10.55, 10.6, 10.5, 10.52, 2000),
        _row(2, 11, 59, 10.40, 10.45, 10.35, 10.40, 2000),
    ]
    day2 = _bars(nxt_rows)
    trades = replay_session(
        {"TEST": day2},
        [],
        {"TEST": 50_000_000},
        rth_open_entries=sigs,
    )
    assert trades
    tr = trades[0]
    assert tr.entry_ts.day == 2
    assert tr.entry_ts.hour == 9 and tr.entry_ts.minute == 30
    assert tr.entry_px == 10.50
    assert tr.exit_ts.day == 2
    assert not (tr.exit_ts.day == 1)
