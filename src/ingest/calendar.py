from __future__ import annotations

from datetime import date, time, timedelta

import polars as pl

WARMUP_SESSIONS: tuple[date, ...] = (
    date(2026, 5, 15),
    date(2026, 5, 18),
    date(2026, 5, 19),
    date(2026, 5, 20),
    date(2026, 5, 21),
    date(2026, 5, 22),
    date(2026, 5, 26),
    date(2026, 5, 27),
    date(2026, 5, 28),
    date(2026, 5, 29),
)

STUDY_START = date(2026, 6, 1)
STUDY_END = date(2026, 8, 31)
EOD_START = date(2026, 5, 14)
EOD_END = date(2026, 5, 28)
MEMORIAL_DAY = date(2026, 5, 25)

# Official NYSE/Nasdaq 2025 full closures (Jan 9 = National Day of Mourning).
NYSE_CLOSED_2025 = frozenset(
    {
        date(2025, 1, 1),
        date(2025, 1, 9),
        date(2025, 1, 20),
        date(2025, 2, 17),
        date(2025, 4, 18),
        date(2025, 5, 26),
        date(2025, 6, 19),
        date(2025, 7, 4),
        date(2025, 9, 1),
        date(2025, 11, 27),
        date(2025, 12, 25),
    }
)
NYSE_EARLY_CLOSE_2025 = {
    date(2025, 7, 3): time(13, 0),
    date(2025, 11, 28): time(13, 0),
    date(2025, 12, 24): time(13, 0),
}

# Official NYSE/Nasdaq 2026 full closures (Jul 3 is Independence Day observed).
NYSE_CLOSED_2026 = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 4, 3),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 11, 26),
        date(2026, 12, 25),
    }
)
NYSE_EARLY_CLOSE_2026 = {
    date(2026, 11, 27): time(13, 0),
    date(2026, 12, 24): time(13, 0),
}
NYSE_CLOSED = NYSE_CLOSED_2025 | NYSE_CLOSED_2026
NYSE_EARLY_CLOSE = {**NYSE_EARLY_CLOSE_2025, **NYSE_EARLY_CLOSE_2026}

VIRGIN_STUDY_START = date(2026, 1, 2)
VIRGIN_STUDY_END = date(2026, 5, 29)
ARROW61_START = date(2025, 12, 1)
ARROW61_END = date(2025, 12, 16)
ARROW67_START = date(2025, 9, 2)
ARROW67_END = date(2025, 11, 28)
ARROW67_PRIOR_START = date(2025, 8, 29)
ARROW67_LABOR_DAY = date(2025, 9, 1)
ARROW67_THANKSGIVING = date(2025, 11, 27)
ARROW69_START = date(2025, 8, 1)
ARROW69_END = date(2025, 8, 29)
ARROW69_PRIOR_START = date(2025, 7, 31)
ARROW61_EXPECTED: tuple[date, ...] = (
    date(2025, 12, 1),
    date(2025, 12, 2),
    date(2025, 12, 3),
    date(2025, 12, 4),
    date(2025, 12, 5),
    date(2025, 12, 8),
    date(2025, 12, 9),
    date(2025, 12, 10),
    date(2025, 12, 11),
    date(2025, 12, 12),
    date(2025, 12, 15),
    date(2025, 12, 16),
)

SESSION_OPEN = time(7, 30)
WINDOW_END = time(12, 0)
REGULAR_CLOSE = time(16, 0)


def is_nyse_session(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_CLOSED


def nyse_sessions(start: date, end: date) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        if is_nyse_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def all_2026_sessions() -> list[date]:
    return nyse_sessions(date(2026, 1, 2), date(2026, 12, 31))


def prior_session(session: date, sessions: list[date] | None = None) -> date:
    seq = sessions or all_2026_sessions()
    prev = [d for d in seq if d < session]
    if not prev:
        raise ValueError(f"no prior NYSE session before {session}")
    return prev[-1]


def prior_n_sessions(session: date, n: int = 10, sessions: list[date] | None = None) -> list[date] | None:
    seq = sessions or all_2026_sessions()
    prev = [d for d in seq if d < session]
    if len(prev) < n:
        return None
    return prev[-n:]


def study_sessions() -> list[date]:
    return nyse_sessions(STUDY_START, STUDY_END)


def warmup_plus_study() -> list[date]:
    return list(WARMUP_SESSIONS) + study_sessions()


def eod_dates_for_warmup() -> list[date]:
    """Prior official EOD dates covering eligibility for the 10 warmup sessions."""
    needed = {prior_session(d) for d in WARMUP_SESSIONS}
    return sorted(needed)


def virgin_warmup_sessions() -> list[date]:
    """Last 10 NYSE sessions of 2025. On disk for priors / EMA; do not score."""
    dec = nyse_sessions(date(2025, 12, 1), date(2025, 12, 31))
    return dec[-10:]


def virgin_study_sessions() -> list[date]:
    """First 2026 NYSE session through last full May 2026 session. All of January is study."""
    return nyse_sessions(VIRGIN_STUDY_START, VIRGIN_STUDY_END)


def virgin_sessions() -> list[date]:
    return virgin_warmup_sessions() + virgin_study_sessions()


def virgin_prior_calendar() -> list[date]:
    """NYSE sessions covering the prior of first warmup through last study day."""
    return nyse_sessions(date(2025, 12, 1), VIRGIN_STUDY_END)


def arrow61_sessions() -> list[date]:
    """NYSE sessions 2025-12-01 through 2025-12-16. Arrow 61 append; not scored."""
    return nyse_sessions(ARROW61_START, ARROW61_END)


def arrow61_prior_calendar() -> list[date]:
    """Prior of 2025-12-01 (2025-11-28) through 2025-12-16."""
    return nyse_sessions(date(2025, 11, 28), ARROW61_END)


def december_2025_sessions() -> list[date]:
    return nyse_sessions(date(2025, 12, 1), date(2025, 12, 31))


def arrow67_sessions() -> list[date]:
    """NYSE sessions 2025-09-02 through 2025-11-28. Arrow 67 append; not scored."""
    return nyse_sessions(ARROW67_START, ARROW67_END)


def arrow67_prior_calendar() -> list[date]:
    """Prior of 2025-09-02 (2025-08-29) through 2025-11-28."""
    return nyse_sessions(ARROW67_PRIOR_START, ARROW67_END)


def arrow67_non_sessions() -> list[date]:
    """Weekdays in the Arrow 67 window that are not NYSE sessions."""
    out: list[date] = []
    d = ARROW67_START
    while d <= ARROW67_END:
        if d.weekday() < 5 and not is_nyse_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def arrow69_sessions() -> list[date]:
    """NYSE sessions 2025-08-01 through 2025-08-29. Arrow 69 warmup; not scored."""
    return nyse_sessions(ARROW69_START, ARROW69_END)


def arrow69_prior_calendar() -> list[date]:
    """Prior of 2025-08-01 (2025-07-31) through 2025-08-29."""
    return nyse_sessions(ARROW69_PRIOR_START, ARROW69_END)


def arrow69_non_sessions() -> list[date]:
    """Weekdays in the Arrow 69 window that are not NYSE sessions."""
    out: list[date] = []
    d = ARROW69_START
    while d <= ARROW69_END:
        if d.weekday() < 5 and not is_nyse_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def sessions_frame() -> pl.DataFrame:
    rows = []
    for d in warmup_plus_study():
        early = d in NYSE_EARLY_CLOSE_2026
        regular = NYSE_EARLY_CLOSE_2026.get(d, REGULAR_CLOSE)
        window_end = WINDOW_END
        if early and regular < WINDOW_END:
            window_end = regular
        rows.append(
            {
                "session_date": d,
                "is_warmup": d in WARMUP_SESSIONS,
                "is_early_close": early,
                "session_open_et": SESSION_OPEN,
                "window_end_et": window_end,
                "regular_close_et": regular,
            }
        )
    return pl.DataFrame(rows)
