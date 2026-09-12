import math
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session, ssr_active, ssr_blocks_short
from research.combine import combine_books
from research.grid import is_structural, structural_grid_row
from research.signals import MINUTE_1159, MINUTE_1300, MINUTE_1559, Signal

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(sym, hh, mm, o, h, l, c, v, day=1):
    return {
        "symbol": sym,
        "bar_start": datetime(2026, 6, day, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "pre" if hh < 9 else "rth",
    }


def test_r1_session_low_trips_ssr() -> None:
    assert ssr_active(17.80, 20.0) is True
    assert ssr_active(18.20, 20.0) is False


def test_r1_prior_session_low_trips_ssr() -> None:
    assert ssr_active(19.50, 20.0, prior_session_low=17.80, prior_session_prior_close=20.0) is True
    assert ssr_active(19.50, 20.0, prior_session_low=19.00, prior_session_prior_close=20.0) is False


def test_r1_session_low_rejects_when_close_does_not() -> None:
    """Low ≤ 0.90×prior_close even if last close is above the old A18 last-close proxy."""
    assert ssr_blocks_short(18.20, 20.0) is False
    assert ssr_active(17.80, 20.0) is True
    rows = [
        _row("TEST", 9, 30, 19.00, 19.10, 17.80, 18.20, 1000),
        _row("TEST", 9, 31, 18.20, 18.30, 18.10, 18.25, 1000),
        _row("TEST", 11, 59, 18.20, 18.30, 18.10, 18.20, 1000),
    ]
    df = _bars(rows)
    sig = Signal(df["bar_start"][0], "TEST", -1, 19.50, None, 1.0, "test")
    blocked = replay_session(
        {"TEST": df},
        [sig],
        {"TEST": 50_000_000.0},
        prior_close={"TEST": 20.0},
        ssr_filter=True,
    )
    assert blocked == []


def test_combine_uncorrelated_std_is_hypot() -> None:
    rng = random.Random(17)
    n = 2000
    a = {f"d{i}": rng.gauss(0.0, 1.0) for i in range(n)}
    b = {f"d{i}": rng.gauss(0.0, 2.0) for i in range(n)}
    comb = combine_books(a, b)
    xs = list(a.values())
    ys = list(b.values())
    std_a = math.sqrt(sum((x - sum(xs) / n) ** 2 for x in xs) / (n - 1))
    std_b = math.sqrt(sum((y - sum(ys) / n) ** 2 for y in ys) / (n - 1))
    expect = math.hypot(std_a, std_b)
    assert abs(comb["std_day"] / expect - 1.0) < 0.08


def test_combine_missing_day_is_zero_not_drop() -> None:
    a = {"d1": 10.0, "d2": 20.0, "d3": 30.0}
    b = {"d1": 5.0, "d3": 7.0}
    comb = combine_books(a, b)
    assert comb["n"] == 3
    by = dict(zip(comb["sessions"], comb["daily"]))
    assert abs(by["d2"] - 20.0) < 1e-12
    assert abs(by["d1"] - 15.0) < 1e-12
    assert abs(by["d3"] - 37.0) < 1e-12


def test_r2_giveback_flat1159_is_structural() -> None:
    assert is_structural(MINUTE_1159, MINUTE_1300) is True
    assert structural_grid_row("giveback", MINUTE_1159) is True
    assert structural_grid_row("giveback", MINUTE_1559) is False
    assert structural_grid_row("flush", MINUTE_1159) is False


def test_r4_untradeable_flatten_uses_close() -> None:
    """A33: 11:59 untradeable, no later print → mark 11:58 close, tag unresolved."""
    df = _bars(
        [
            _row("TEST", 9, 30, 10.00, 10.20, 9.90, 10.10, 1000),
            _row("TEST", 9, 31, 10.10, 10.20, 10.00, 10.15, 1000),
            _row("TEST", 11, 58, 10.20, 10.40, 9.80, 10.18, 1000),
            _row("TEST", 11, 59, 10.30, 10.35, 10.25, 10.32, 0),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", 1, 9.50, None, 1.0, "test")
    st = {}
    trades = replay_session({"TEST": df}, [sig], {"TEST": 50_000_000.0}, stats=st)
    assert len(trades) == 1
    assert abs(trades[0].exit_px - 10.18) < 1e-9
    assert trades[0].tag == "unresolved"
    assert trades[0].exit_ts.hour == 11 and trades[0].exit_ts.minute == 58
    assert st.get("unresolved_flatten", 0) >= 1
