from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.bars import normalize_ohlc_full
from ingest.full import sessions_to_pull
from ingest.paths import full_bar_path, safe_symbol_filename

ET = ZoneInfo("America/New_York")


def test_session_part_pre_rth_and_afternoon_kept() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2026, 6, 1, 4, 15, tzinfo=ET),
                datetime(2026, 6, 1, 9, 30, tzinfo=ET),
                datetime(2026, 6, 1, 12, 5, tzinfo=ET),
                datetime(2026, 6, 1, 3, 59, tzinfo=ET),
                datetime(2026, 6, 1, 16, 0, tzinfo=ET),
            ],
            "open": [1.0] * 5,
            "high": [1.0] * 5,
            "low": [1.0] * 5,
            "close": [1.0] * 5,
            "volume": [100] * 5,
        }
    )
    out = normalize_ohlc_full(df, "TEST", is_warmup=False)
    times = [t.replace(tzinfo=None) if t.tzinfo else t for t in out["bar_start"].dt.time().to_list()]
    parts = dict(zip(times, out["session_part"].to_list()))
    from datetime import time as dtime

    assert parts[dtime(4, 15)] == "pre"
    assert parts[dtime(9, 30)] == "rth"
    assert dtime(12, 5) in parts
    assert parts[dtime(12, 5)] == "rth"
    assert dtime(3, 59) not in parts
    assert dtime(16, 0) not in parts


def test_safe_symbol_con_maps_underscore() -> None:
    assert safe_symbol_filename("CON") == "_CON"
    p = full_bar_path(date(2026, 6, 1), "CON")
    assert p.name == "_CON.parquet"
    assert "2026-06-01" in str(p)
    assert "data" in str(p) and "full" in str(p) and "bars" in str(p)


def test_resume_skips_already_written_name_day(monkeypatch) -> None:
    class _P:
        def __init__(self, exists: bool) -> None:
            self._exists = exists

        def exists(self) -> bool:
            return self._exists

    def fake_path(session_date, symbol: str):
        return _P(session_date == date(2026, 6, 1) and symbol == "AAPL")

    monkeypatch.setattr("ingest.full.full_bar_path", fake_path)
    d = date(2026, 6, 1)
    need = sessions_to_pull("AAPL", [d, date(2026, 6, 2)], force=False)
    assert d not in need
    assert date(2026, 6, 2) in need
    assert sessions_to_pull("AAPL", [d], force=True) == [d]
