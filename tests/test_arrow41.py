from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.bars import normalize_ohlc_full
from ingest.calendar import (
    virgin_prior_calendar,
    virgin_study_sessions,
    virgin_warmup_sessions,
)
from ingest.eligibility import (
    MAX_CLOSE_VIRGIN,
    PDV_10M,
    eod_session_dates,
    evaluate_session,
    with_pdv_10m_flag,
)
from ingest.paths import (
    BARS_DIR,
    FULL_BARS,
    VIRGIN_BARS,
    VIRGIN_IWM,
    safe_symbol_filename,
    virgin_bar_path,
    virgin_iwm_path,
)
from ingest.virgin import sessions_to_pull

ET = ZoneInfo("America/New_York")


def test_warmup_is_last_ten_nyse_2025() -> None:
    warm = virgin_warmup_sessions()
    assert len(warm) == 10
    assert warm[0] == date(2025, 12, 17)
    assert warm[-1] == date(2025, 12, 31)
    assert date(2025, 12, 25) not in warm
    assert date(2025, 12, 24) in warm
    assert all(d.year == 2025 for d in warm)


def test_study_is_all_january_through_may_2026() -> None:
    study = virgin_study_sessions()
    assert study[0] == date(2026, 1, 2)
    assert study[-1] == date(2026, 5, 29)
    assert date(2026, 1, 1) not in study
    assert date(2026, 1, 5) in study
    assert date(2026, 1, 16) in study
    assert date(2026, 1, 19) not in study
    assert date(2026, 2, 16) not in study
    assert date(2026, 4, 3) not in study
    assert date(2026, 5, 25) not in study
    jan = [d for d in study if d.month == 1]
    assert len(jan) == 20


def test_prior_of_first_2026_session_is_2025_12_31() -> None:
    from ingest.calendar import prior_session

    cal = virgin_prior_calendar()
    assert prior_session(date(2026, 1, 2), cal) == date(2025, 12, 31)
    assert prior_session(date(2025, 12, 17), cal) == date(2025, 12, 16)
    assert prior_session(date(2025, 12, 26), cal) == date(2025, 12, 24)


def test_virgin_paths_are_not_lab_a_or_full() -> None:
    p = virgin_bar_path(date(2026, 1, 2), "CON")
    assert p.name == "_CON.parquet"
    assert "virgin" in p.parts
    assert "bars" in p.parts
    assert FULL_BARS not in p.parents and p != FULL_BARS
    assert BARS_DIR not in p.parents
    assert "full" not in p.parts
    iwm = virgin_iwm_path(date(2026, 1, 2))
    assert iwm.parent == VIRGIN_IWM
    assert "virgin" in iwm.parts
    assert "full" not in iwm.parts
    assert VIRGIN_BARS != FULL_BARS
    assert safe_symbol_filename("CON") == "_CON"


def test_ten_million_is_column_not_wall() -> None:
    eod = eod_session_dates(
        pl.DataFrame(
            {
                "symbol": ["MID", "RICH", "PRICEY", "FIFTY"],
                "created": [datetime(2025, 12, 31, 17, 0, tzinfo=ET)] * 4,
                "close": [20.0, 20.0, 85.0, 55.0],
                "volume": [100_000, 1_000_000, 100_000, 20_000],
            }
        )
    )
    cal = virgin_prior_calendar()
    out = with_pdv_10m_flag(
        evaluate_session(
            eod,
            date(2026, 1, 2),
            is_warmup=False,
            max_close=MAX_CLOSE_VIRGIN,
            sessions=cal,
        )
    )
    by = {r["symbol"]: r for r in out.iter_rows(named=True)}
    assert by["MID"]["eligible"] is True
    assert by["MID"]["prior_dollar_volume"] == 2_000_000.0
    assert by["MID"]["pdv_ge_10m"] is False
    assert by["RICH"]["eligible"] is True
    assert by["RICH"]["prior_dollar_volume"] >= PDV_10M
    assert by["RICH"]["pdv_ge_10m"] is True
    assert by["PRICEY"]["eligible"] is False
    assert by["PRICEY"]["exclude_reason"] == "prior_close_out_of_range"
    assert by["FIFTY"]["eligible"] is True
    assert by["FIFTY"]["prior_close"] == 55.0


def test_session_part_pre_rth_afternoon_on_virgin_window() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2026, 1, 2, 4, 15, tzinfo=ET),
                datetime(2026, 1, 2, 9, 30, tzinfo=ET),
                datetime(2026, 1, 2, 12, 5, tzinfo=ET),
                datetime(2026, 1, 2, 3, 59, tzinfo=ET),
                datetime(2026, 1, 2, 16, 0, tzinfo=ET),
            ],
            "open": [1.0] * 5,
            "high": [1.0] * 5,
            "low": [1.0] * 5,
            "close": [1.0] * 5,
            "volume": [100] * 5,
        }
    )
    out = normalize_ohlc_full(df, "TEST", is_warmup=False)
    from datetime import time as dtime

    times = out["bar_start"].dt.time().to_list()
    parts = dict(zip(times, out["session_part"].to_list()))
    assert parts[dtime(4, 15)] == "pre"
    assert parts[dtime(9, 30)] == "rth"
    assert dtime(12, 5) in parts
    assert dtime(3, 59) not in parts
    assert dtime(16, 0) not in parts


def test_resume_skips_already_written_virgin_name_day(monkeypatch) -> None:
    class _P:
        def __init__(self, exists: bool) -> None:
            self._exists = exists

        def exists(self) -> bool:
            return self._exists

    def fake_path(session_date, symbol: str):
        return _P(session_date == date(2026, 1, 2) and symbol == "AAPL")

    monkeypatch.setattr("ingest.virgin.virgin_bar_path", fake_path)
    d = date(2026, 1, 2)
    need = sessions_to_pull("AAPL", [d, date(2026, 1, 5)], force=False)
    assert d not in need
    assert date(2026, 1, 5) in need
    assert sessions_to_pull("AAPL", [d], force=True) == [d]
