"""Reusable IS/OOS clock split for Arrow 43 onward.

Odd calendar months are in-sample (IS). Even calendar months are
out-of-sample (OOS). Split on the entry session, not the exit.
Combined study calendar is virgin Jan–May 2026 plus full Jun–Aug 2026.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from ingest.calendar import (
    VIRGIN_STUDY_END,
    december_2025_sessions,
    nyse_sessions,
    study_sessions,
    virgin_study_sessions,
    virgin_warmup_sessions,
)
from ingest.paths import FULL_BARS, VIRGIN_BARS, safe_symbol_filename

IS_MONTHS = frozenset({1, 3, 5, 7, 9, 11})
OOS_MONTHS = frozenset({2, 4, 6, 8, 10, 12})


def combined_study_sessions() -> list[date]:
    """Virgin study then full study. No overlapping dates. No warmup fills."""
    return list(virgin_study_sessions()) + list(study_sessions())


def is_is_session(d: date) -> bool:
    return d.month in IS_MONTHS


def is_oos_session(d: date) -> bool:
    return d.month in OOS_MONTHS


def entry_split(d: date) -> str:
    """IS or OOS from the entry session month."""
    if is_is_session(d):
        return "IS"
    if is_oos_session(d):
        return "OOS"
    raise ValueError(f"session {d} is neither IS nor OOS")


def split_is_oos(sessions: list[date] | None = None) -> tuple[list[date], list[date]]:
    sess = list(sessions) if sessions is not None else combined_study_sessions()
    return [d for d in sess if is_is_session(d)], [d for d in sess if is_oos_session(d)]


def tape_name(d: date) -> str:
    if d <= VIRGIN_STUDY_END:
        return "virgin"
    return "full"


def tape_root(d: date) -> Path:
    if d <= VIRGIN_STUDY_END:
        return VIRGIN_BARS
    return FULL_BARS


def session_bar_path(d: date, symbol: str) -> Path:
    iso = d.isoformat()
    return tape_root(d) / iso / f"{safe_symbol_filename(symbol)}.parquet"


def next_session(d: date, sessions: list[date] | None = None) -> date | None:
    sess = sessions if sessions is not None else combined_study_sessions()
    for x in sess:
        if x > d:
            return x
    return None


def clock_frame(sessions: list[date] | None = None) -> pl.DataFrame:
    sess = list(sessions) if sessions is not None else combined_study_sessions()
    return pl.DataFrame(
        {
            "session_date": sess,
            "split": [entry_split(d) for d in sess],
            "tape": [tape_name(d) for d in sess],
        }
    )


def feature_sessions() -> list[date]:
    """Warmup + study. Warmup is lookback only; no fills."""
    seen: set[date] = set()
    out: list[date] = []
    for d in list(virgin_warmup_sessions()) + combined_study_sessions():
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def arrow62_feature_sessions() -> list[date]:
    """Full December 2025 + combined study. Does not change leftover lookback."""
    seen: set[date] = set()
    out: list[date] = []
    for d in list(december_2025_sessions()) + combined_study_sessions():
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def arrow68_feature_sessions() -> list[date]:
    """Aug 2025 through Jan 2026. Lookback + Sep–Dec signals + Dec exits.

    Does not change leftover 2026 lookback.
    """
    return nyse_sessions(date(2025, 8, 1), date(2026, 1, 31))


def arrow68_score_sessions() -> list[date]:
    """NYSE sessions 2025-09-02 through 2025-12-31. One look, not IS/OOS."""
    return nyse_sessions(date(2025, 9, 2), date(2025, 12, 31))


def arrow70_feature_sessions() -> list[date]:
    """Aug 2025 through Aug 2026. Lookback + Sep 2025–Aug 2026 signals + holds.

    Does not change leftover 2026 lookback.
    """
    return nyse_sessions(date(2025, 8, 1), date(2026, 8, 31))


def arrow70_score_sessions() -> list[date]:
    """NYSE sessions 2025-09-02 through 2026-08-31. One year look, not IS/OOS."""
    return nyse_sessions(date(2025, 9, 2), date(2026, 8, 31))


def arrow74_sessions() -> list[date]:
    """Jan–Feb 2026 on virgin. Not the shop IS/OOS year. Does not change leftover lookback."""
    return nyse_sessions(date(2026, 1, 2), date(2026, 2, 28))


def arrow74_january() -> list[date]:
    return nyse_sessions(date(2026, 1, 2), date(2026, 1, 31))


def arrow74_february() -> list[date]:
    return nyse_sessions(date(2026, 2, 1), date(2026, 2, 28))


def arrow75_feature_sessions() -> list[date]:
    """Dec 2025 through Feb 2026. 15-session left + 10-session home hour.

    Does not change leftover 2026 lookback.
    """
    return nyse_sessions(date(2025, 12, 1), date(2026, 2, 28))


def arrow76_sessions() -> list[date]:
    """Jan–Apr 2026 on virgin. Odd=IS even=OOS on this window.

    Does not change leftover 2026 lookback. Does not score May–August.
    """
    return nyse_sessions(date(2026, 1, 2), date(2026, 4, 30))


def arrow76_feature_sessions() -> list[date]:
    """Dec 2025 through Apr 2026. 15-session left.

    Does not change leftover 2026 lookback.
    """
    return nyse_sessions(date(2025, 12, 1), date(2026, 4, 30))


def month_first_last(year: int, month: int, sessions: list[date]) -> tuple[date, date] | None:
    days = [d for d in sessions if d.year == year and d.month == month]
    if not days:
        return None
    return min(days), max(days)


def session_shift(d: date, n: int, sessions: list[date] | None = None) -> date | None:
    """n sessions after d (negative = before). None if off the calendar."""
    sess = list(sessions) if sessions is not None else feature_sessions()
    try:
        i = sess.index(d)
    except ValueError:
        return None
    j = i + n
    if 0 <= j < len(sess):
        return sess[j]
    return None


def rebalance_sessions(study: list[date] | None = None) -> list[date]:
    """Last NYSE session of each calendar week that falls inside study.

    Friday, or Thursday when Friday is closed. A week whose true last
    NYSE session is off-tape (e.g. after 2026-08-31) is not a rebalance.
    """
    study_list = list(study) if study is not None else combined_study_sessions()
    study_set = set(study_list)
    if not study_list:
        return []
    cal = nyse_sessions(date(2025, 12, 1), date(2026, 9, 11))
    by: dict[tuple[int, int], list[date]] = {}
    for d in cal:
        iso = d.isocalendar()
        by.setdefault((iso[0], iso[1]), []).append(d)
    out: list[date] = []
    for key in sorted(by):
        last = max(by[key])
        if last in study_set:
            out.append(last)
    return out
