from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from research.rockets import scan_name_day

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(hh, mm, o, h, l, c, v):
    return {
        "symbol": "TEST",
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "pre" if hh < 9 else "rth",
    }


def test_rocket_counted_launch_hour_10() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row(10, 3, 10.80, 11.20, 10.70, 11.00, 2000),
            _row(11, 59, 10.80, 10.90, 10.60, 10.70, 1000),
        ]
    )
    rec = scan_name_day(df, prior_close=10.0, prior_vols=[1000.0] * 10)
    assert rec["status"] == "ok"
    assert rec["rocket"] is True
    assert rec["launch_hour"] == 10
    assert rec["rel_vol"] == 4.0
    assert rec["max_ext"] == pytest.approx(0.12)


def test_plus8_not_a_rocket() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row(10, 3, 10.40, 10.80, 10.30, 10.50, 2000),
            _row(11, 59, 10.40, 10.50, 10.20, 10.30, 1000),
        ]
    )
    rec = scan_name_day(df, prior_close=10.0, prior_vols=[1000.0] * 10)
    assert rec["status"] == "ok"
    assert rec["rocket"] is False
    assert rec["max_ext"] == pytest.approx(0.08)
    assert rec["launch_hour"] is None


def test_rel_vol_two_priors_skipped() -> None:
    df = _bars(
        [
            _row(9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row(10, 3, 10.80, 11.20, 10.70, 11.00, 2000),
            _row(11, 59, 10.80, 10.90, 10.60, 10.70, 1000),
        ]
    )
    rec = scan_name_day(df, prior_close=10.0, prior_vols=[1000.0, 1000.0])
    assert rec["status"] == "skip"
    assert rec["rocket"] is False
    assert rec["rel_vol"] is None
