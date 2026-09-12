from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.character import dv_ranks, name_day_character, sessions_for_character
from research.strategies9 import gap_continuation_signals

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


def test_dv_rank_keeps_only_top_fifth() -> None:
    ranks = dv_ranks({"A": 1.0, "B": 2.0, "C": 3.0, "D": 4.0, "E": 5.0})
    kept = {s for s, r in ranks.items() if r >= 0.80}
    assert kept == {"E"}
    ten = {str(i): float(i) for i in range(10)}
    ranks10 = dv_ranks(ten)
    kept10 = {s for s, r in ranks10.items() if r >= 0.80}
    assert kept10 == {"8", "9"}
    assert len(kept10) == 2


def test_gap_continuation_does_not_fade() -> None:
    up = _bars(
        [
            _row("TEST", 9, 30, 10.30, 10.40, 10.20, 10.32, 5000),  # gap +3% vs 10.00
            _row("TEST", 9, 31, 10.32, 10.35, 10.25, 10.30, 5000),
            _row("TEST", 11, 59, 10.30, 10.35, 10.25, 10.30, 5000),
        ]
    )
    sigs = gap_continuation_signals(up, prior_close=10.00, min_abs_gap=0.02)
    assert len(sigs) == 1
    assert sigs[0].side == 1  # continuation, not fade
    assert sigs[0].stop == 10.20

    down = _bars(
        [
            _row("TEST", 9, 30, 9.70, 9.80, 9.60, 9.68, 5000),  # gap -3%
            _row("TEST", 9, 31, 9.68, 9.72, 9.60, 9.65, 5000),
            _row("TEST", 11, 59, 9.65, 9.70, 9.60, 9.65, 5000),
        ]
    )
    sigs_d = gap_continuation_signals(down, prior_close=10.00, min_abs_gap=0.02)
    assert len(sigs_d) == 1
    assert sigs_d[0].side == -1
    assert sigs_d[0].stop == 9.80


def test_character_helpers_restricted_to_develop_dates() -> None:
    develop = [date(2026, 6, 1), date(2026, 6, 2)]
    holdout = [date(2026, 8, 3)]
    mixed = develop + holdout
    got = sessions_for_character(mixed, develop=develop)
    assert got == develop
    assert date(2026, 8, 3) not in got
    called: list[date] = []

    def _load(d: date) -> list[dict]:
        called.append(d)
        return [{"session": d.isoformat()}]

    rows = []
    for d in sessions_for_character(mixed, develop=develop):
        rows.extend(_load(d))
    assert called == develop
    assert all(r["session"].startswith("2026-06") for r in rows)
    # name_day_character itself is date-agnostic; the date gate is sessions_for_character
    df = _bars(
        [
            _row("TEST", 9, 30, 10.0, 10.2, 9.9, 10.1, 1000),
            _row("TEST", 9, 44, 10.1, 10.15, 9.8, 10.0, 1000),
            _row("TEST", 9, 45, 10.0, 10.3, 9.9, 10.2, 1000),
            _row("TEST", 11, 59, 10.1, 10.2, 10.0, 10.1, 1000),
        ]
    )
    feat = name_day_character(df, prior_close=10.0)
    assert feat is not None
    assert feat["or_w"] is not None
    assert feat["post_or_range"] is not None
