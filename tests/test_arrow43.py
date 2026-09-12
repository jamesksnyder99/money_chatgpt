from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import virgin_warmup_sessions
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow43 import first_rth, last_rth, on_fill, rth_fill
from research.clock import (
    combined_study_sessions,
    entry_split,
    is_is_session,
    is_oos_session,
    next_session,
    split_is_oos,
    tape_root,
)
from research.signals import MINUTE_1559, RTH_OPEN

ET = ZoneInfo("America/New_York")


def _row(sym, d, hh, mm, o, h, l, c, v=5000):
    return {
        "symbol": sym,
        "bar_start": datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
    }


def _df(rows):
    return pl.DataFrame(rows).with_columns(pl.col("bar_start").dt.replace_time_zone("America/New_York"))


def test_warmup_dates_produce_no_fills() -> None:
    study = set(combined_study_sessions())
    for d in virgin_warmup_sessions():
        assert d not in study
        assert d.year == 2025


def test_even_month_entry_is_not_is() -> None:
    is_sess, oos_sess = split_is_oos()
    assert date(2026, 2, 2) in oos_sess
    assert date(2026, 2, 2) not in is_sess
    assert entry_split(date(2026, 2, 2)) == "OOS"
    assert is_oos_session(date(2026, 4, 1))
    assert not is_is_session(date(2026, 4, 1))
    assert entry_split(date(2026, 1, 31)) == "IS"
    assert entry_split(date(2026, 7, 31)) == "IS"
    assert entry_split(date(2026, 8, 3)) == "OOS"


def test_on_long_entry_is_1559_not_0930() -> None:
    d0 = date(2026, 1, 2)
    d1 = date(2026, 1, 5)
    today = _df(
        [
            _row("AAA", d0, 9, 30, 10.0, 10.2, 9.9, 10.1),
            _row("AAA", d0, 15, 59, 10.4, 10.5, 10.3, 10.45),
        ]
    )
    nxt = _df([_row("AAA", d1, 9, 30, 10.6, 10.7, 10.5, 10.65)])
    last = last_rth(today, d0)
    assert last is not None
    assert last["bar_start"].timetz().replace(tzinfo=None) == MINUTE_1559
    first = first_rth(today)
    assert first["bar_start"].timetz().replace(tzinfo=None) == RTH_OPEN
    tr = on_fill(today, nxt, d0, d1, 1, 10.0, 20_000_000.0, "AAA")
    assert tr is not None
    assert tr["entry_ts"].timetz().replace(tzinfo=None) == MINUTE_1559
    assert tr["entry_ts"].timetz().replace(tzinfo=None) != RTH_OPEN
    assert tr["entry_px"] == 10.45
    assert tr["exit_px"] == 10.6


def test_rth_long_pnl_excludes_overnight_gap() -> None:
    d = date(2026, 1, 5)
    # Prior close 10, next open 12 would be a +20% gap; rth_long must not see it.
    today = _df(
        [
            _row("BBB", d, 9, 30, 12.0, 12.2, 11.9, 12.1),
            _row("BBB", d, 15, 59, 12.4, 12.5, 12.3, 12.45),
        ]
    )
    tr = rth_fill(today, d, 20_000_000.0, "BBB")
    assert tr is not None
    assert tr["entry_px"] == 12.0
    assert tr["exit_px"] == 12.45
    assert tr["entry_ts"].timetz().replace(tzinfo=None) == RTH_OPEN
    shares = tr["shares"]
    # Gross move is 12.45-12.00, not 12.45-10 (overnight).
    assert abs((tr["exit_px"] - tr["entry_px"]) - 0.45) < 1e-9
    assert shares * 0.45 > 0


def test_july_from_full_january_from_virgin() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 5, 29)) == VIRGIN_BARS
    assert tape_root(date(2026, 6, 1)) == FULL_BARS
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
    assert tape_root(date(2026, 1, 2)) != BARS_DIR
    assert tape_root(date(2026, 7, 1)) != BARS_DIR
    assert next_session(date(2026, 5, 29)) == date(2026, 6, 1)
    assert tape_root(next_session(date(2026, 5, 29))) == FULL_BARS
