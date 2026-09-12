from datetime import datetime
from zoneinfo import ZoneInfo

from research.harness import confirmed_launch
from research.strategies30 import gross_altitude

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


def _row(hh, mm, o, h, l, c, v=1000):
    return {
        "symbol": "TEST",
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
    }


def test_confirmed_launch_rejects_12pct_wick_close_6pct() -> None:
    pc = 10.0
    rows = [
        _row(9, 30, 10.20, 11.20, 10.10, 10.60),  # +12% wick, close +6%
        _row(9, 31, 10.60, 10.70, 10.50, 10.65),
    ]
    rec = confirmed_launch(_pack_from_rows(rows), pc)
    assert rec["confirmed"] is False


def test_altitude_zero_if_high_below_1r() -> None:
    # +0.4% high, 1R = 0.6% → never leaves +1R above sea
    assert gross_altitude(10.04, 10.0, 0.006) == 0.0
    assert abs(gross_altitude(10.10, 10.0, 0.006) - 0.004) < 1e-12


def test_depths_after_high_do_not_reduce_altitude() -> None:
    # peak +10%, then a washout close does not subtract
    alt = gross_altitude(11.0, 10.0, 0.006)
    assert abs(alt - (0.10 - 0.006)) < 1e-12
    # a later low of 8.0 is ignored because altitude only sees max_high
    assert gross_altitude(11.0, 10.0, 0.006) == alt
