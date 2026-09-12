from datetime import datetime, time
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from research.arrow19 import scan_full_rocket, snapshot_at

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
        "session_part": "pre" if hh < 9 or (hh == 9 and mm < 30) else "rth",
    }


def test_plus10_at_0512_is_launch_hour_05() -> None:
    df = _bars(
        [
            _row(4, 0, 10.00, 10.10, 9.90, 10.00, 1000),
            _row(5, 12, 10.20, 11.20, 10.10, 11.00, 2000),
            _row(15, 59, 10.80, 10.90, 10.60, 10.70, 1000),
        ]
    )
    rec = scan_full_rocket(df, prior_close=10.0, prior_vols=[1000.0] * 10)
    assert rec["status"] == "ok"
    assert rec["rocket"] is True
    assert rec["launch_hour"] == 5
    assert rec["launch_bucket"] == "pre0730"


def test_0800_snapshot_ignores_0900_print() -> None:
    df = _bars(
        [
            _row(7, 50, 10.00, 10.20, 9.90, 10.10, 1000),
            _row(8, 0, 10.10, 10.20, 10.00, 10.15, 1000),
            _row(9, 0, 11.50, 12.00, 11.40, 11.80, 5000),
        ]
    )
    rec = snapshot_at(df, prior_close=10.0, clock=time(8, 0), prior_dvs=[1_000.0] * 10)
    assert rec["status"] == "ok"
    assert rec["last_ts"].hour == 8 and rec["last_ts"].minute == 0
    assert rec["gap_so_far"] == pytest.approx(0.015)
    assert rec["already_up10"] is False


def test_rel_vol_two_priors_skipped() -> None:
    df = _bars(
        [
            _row(5, 12, 10.20, 11.20, 10.10, 11.00, 2000),
            _row(15, 59, 10.80, 10.90, 10.60, 10.70, 1000),
        ]
    )
    rec = scan_full_rocket(df, prior_close=10.0, prior_vols=[1000.0, 1000.0])
    assert rec["status"] == "skip"
    assert rec["rocket"] is False
    assert rec["rel_vol"] is None
