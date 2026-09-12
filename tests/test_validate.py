from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.bars import normalize_ohlc
from ingest.calendar import MEMORIAL_DAY, WARMUP_SESSIONS, sessions_frame

ET = ZoneInfo("America/New_York")


def test_normalize_drops_bars_outside_window() -> None:
    rows = [
        {
            "timestamp": datetime(2026, 5, 15, 7, 29, tzinfo=ET),
            "open": 1,
            "high": 1,
            "low": 1,
            "close": 1,
            "volume": 1,
            "count": 1,
        },
        {
            "timestamp": datetime(2026, 5, 15, 7, 30, tzinfo=ET),
            "open": 2,
            "high": 2,
            "low": 2,
            "close": 2,
            "volume": 2,
            "count": 2,
        },
        {
            "timestamp": datetime(2026, 5, 15, 11, 59, tzinfo=ET),
            "open": 3,
            "high": 3,
            "low": 3,
            "close": 3,
            "volume": 3,
            "count": 3,
        },
        {
            "timestamp": datetime(2026, 5, 15, 12, 0, tzinfo=ET),
            "open": 4,
            "high": 4,
            "low": 4,
            "close": 4,
            "volume": 4,
            "count": 4,
        },
    ]
    out = normalize_ohlc(pl.DataFrame(rows), "AAPL", True)
    times = out["bar_start"].dt.time().to_list()
    assert all(t.hour > 7 or (t.hour == 7 and t.minute >= 30) for t in times)
    assert all(t.hour < 12 for t in times)
    assert out.height == 2
    pre = out.filter(pl.col("bar_start").dt.time() < datetime(2026, 5, 15, 9, 30).time())
    assert pre["session"].to_list() == ["pre"]


def test_calendar_contract_warmup_window() -> None:
    df = sessions_frame()
    dates = set(df["session_date"].to_list())
    assert MEMORIAL_DAY not in dates
    assert set(WARMUP_SESSIONS).issubset(dates)
