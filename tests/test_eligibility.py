from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.eligibility import build_warmup_eligibility, evaluate_session

ET = ZoneInfo("America/New_York")


def _eod() -> pl.DataFrame:
    # Prior for 2026-05-15 is 2026-05-14.
    rows = [
        {
            "symbol": "CHEAP",
            "created": datetime(2026, 5, 14, 17, 15, tzinfo=ET),
            "close": 5.0,
            "volume": 300_000,
        },
        {
            "symbol": "EXPENSIVE",
            "created": datetime(2026, 5, 14, 17, 15, tzinfo=ET),
            "close": 40.0,
            "volume": 1_000_000,
        },
        {
            "symbol": "ILLIQUID",
            "created": datetime(2026, 5, 14, 17, 15, tzinfo=ET),
            "close": 10.0,
            "volume": 10,
        },
        {
            "symbol": "SAMEDAY",
            "created": datetime(2026, 5, 15, 17, 15, tzinfo=ET),
            "close": 8.0,
            "volume": 500_000,
        },
    ]
    return pl.DataFrame(rows)


def test_price_and_dollar_volume_filters() -> None:
    from ingest.eligibility import eod_session_dates

    eod = eod_session_dates(_eod())
    out = evaluate_session(eod, date(2026, 5, 15), is_warmup=True)
    by = {r["symbol"]: r for r in out.iter_rows(named=True)}
    assert by["CHEAP"]["eligible"] is True
    assert by["CHEAP"]["prior_dollar_volume"] == 1_500_000.0
    assert by["EXPENSIVE"]["eligible"] is False
    assert by["EXPENSIVE"]["exclude_reason"] == "prior_close_out_of_range"
    assert by["ILLIQUID"]["eligible"] is False
    assert by["ILLIQUID"]["exclude_reason"] == "prior_dollar_volume_low"


def test_does_not_use_same_day_close() -> None:
    from ingest.eligibility import eod_session_dates

    eod = eod_session_dates(_eod())
    out = evaluate_session(eod, date(2026, 5, 15), is_warmup=True)
    assert "SAMEDAY" not in out["symbol"].to_list()


def test_warmup_eligibility_fills_missing_prior() -> None:
    from ingest.eligibility import eod_session_dates

    eod = eod_session_dates(_eod())
    all_rows = build_warmup_eligibility(eod, ["CHEAP", "GHOST"])
    ghost = all_rows.filter(
        (pl.col("symbol") == "GHOST") & (pl.col("session_date") == date(2026, 5, 15))
    )
    assert ghost.height == 1
    assert ghost["eligible"][0] is False
    assert ghost["exclude_reason"][0] == "no_prior_eod"
