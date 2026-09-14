"""Arrow 013 — frozen definition, calendar extension and partition layout for the new holdout.

The pristine out-of-sample period is September 2024 through August 2025 inclusive, twelve
signal months. August 2024 is warmup only: it supplies the prior sessions the first September
2024 signals need for the frozen fifteen-session ranking return and twenty-session feature
histories, and it creates no positions. August 2025 is the twelfth and final signal month, not
warmup, even though the repository already holds it from the previous study's warmup.

Nothing here runs a strategy. This module supplies dates, partition paths and the session
schedule that the acquisition and certification stages need.

Calendar note. The lab calendar in ingest.calendar carried only 2025 and 2026. The 2024
closures and early closes below are added for this holdout. The addition is purely additive:
no 2024 date falls inside any previously frozen window, so every prior arrow's session list is
unchanged, and tests/test_cg_arrow013.py asserts that.
"""
from __future__ import annotations

from datetime import date, time, timedelta

from ingest.paths import DATA, REPO_ROOT

# ---------------------------------------------------------------- frozen period
WARMUP_START = date(2024, 8, 1)
WARMUP_END = date(2024, 8, 30)          # last session before the first signal month
SIGNAL_START = date(2024, 9, 1)
SIGNAL_END = date(2025, 8, 31)
BULK_START = date(2024, 8, 1)           # new acquisition span, inclusive
BULK_END = date(2025, 7, 31)            # new acquisition span, inclusive
REUSE_START = date(2025, 8, 1)          # already held locally; authenticate before reuse
REUSE_END = date(2025, 8, 31)
LIFECYCLE_START = date(2025, 9, 1)      # tail for late-August H10 only
LIFECYCLE_END = date(2025, 9, 30)
STARTING_EQUITY = 100000.0
DEFINITION_ID = "cg_arrow013_holdout_sep2024_aug2025_v1"

SIGNAL_MONTHS = ("2024-09", "2024-10", "2024-11", "2024-12", "2025-01", "2025-02",
                 "2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08")

# ---------------------------------------------------------------- 2024 exchange calendar
# NYSE/Nasdaq 2024 full closures. Only the four from August onward touch this holdout; the
# earlier ones are listed so the year is complete and can be cross-checked as a unit.
NYSE_CLOSED_2024 = frozenset({
    date(2024, 1, 1),    # New Year's Day
    date(2024, 1, 15),   # Martin Luther King Jr. Day
    date(2024, 2, 19),   # Washington's Birthday
    date(2024, 3, 29),   # Good Friday
    date(2024, 5, 27),   # Memorial Day
    date(2024, 6, 19),   # Juneteenth National Independence Day
    date(2024, 7, 4),    # Independence Day
    date(2024, 9, 2),    # Labor Day
    date(2024, 11, 28),  # Thanksgiving Day
    date(2024, 12, 25),  # Christmas Day
})
# 2024 early closes at 13:00 ET.
NYSE_EARLY_CLOSE_2024 = {
    date(2024, 7, 3): time(13, 0),    # day before Independence Day
    date(2024, 11, 29): time(13, 0),  # day after Thanksgiving
    date(2024, 12, 24): time(13, 0),  # Christmas Eve
}

# Closures and early closes inside the acquisition window, for the calendar audit.
WINDOW_CLOSURES = {
    date(2024, 9, 2): "Labor Day",
    date(2024, 11, 28): "Thanksgiving Day",
    date(2024, 12, 25): "Christmas Day",
    date(2025, 1, 1): "New Year's Day",
    date(2025, 1, 9): "National Day of Mourning, President Carter",
    date(2025, 1, 20): "Martin Luther King Jr. Day",
    date(2025, 2, 17): "Washington's Birthday",
    date(2025, 4, 18): "Good Friday",
    date(2025, 5, 26): "Memorial Day",
    date(2025, 6, 19): "Juneteenth National Independence Day",
    date(2025, 7, 4): "Independence Day",
    date(2025, 9, 1): "Labor Day",
}
WINDOW_EARLY_CLOSES = {
    date(2024, 11, 29): "day after Thanksgiving",
    date(2024, 12, 24): "Christmas Eve",
    date(2025, 7, 3): "day before Independence Day",
}

# ---------------------------------------------------------------- partition layout
HOLDOUT_ROOT = DATA / "holdout2024"
RAW_EOD = HOLDOUT_ROOT / "raw" / "eod"          # immutable vendor landing, per symbol-chunk
RAW_BARS = HOLDOUT_ROOT / "raw" / "bars"        # immutable vendor landing, per session-symbol
AUDIT_ROOT = HOLDOUT_ROOT / "audit"             # re-retrieval partitions, never overwrite raw
WORK = HOLDOUT_ROOT / "work"
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow013"

VENUE = "utp_cta"
INTERVAL = "1m"
RTH_OPEN = time(9, 30)
PREMARKET_START = time(4, 0)
SESSION_WINDOW_END = time(16, 0)


def eod_chunks(start: date = BULK_START, end: date = BULK_END) -> list[tuple[date, date, str]]:
    """Calendar-month chunks for the end-of-day pull; the vendor caps a request at one month."""
    out = []
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), (cur.month % 12) + 1, 1)
        lo, hi = max(cur, start), min(nxt - timedelta(days=1), end)
        out.append((lo, hi, cur.strftime("%Y-%m")))
        cur = nxt
    return out


def is_session(d: date) -> bool:
    """Exchange session test covering 2024 through 2026 under the lab calendar."""
    from ingest.calendar import NYSE_CLOSED
    return d.weekday() < 5 and d not in NYSE_CLOSED and d not in NYSE_CLOSED_2024


def sessions(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if is_session(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def close_time(d: date) -> time:
    from ingest.calendar import NYSE_EARLY_CLOSE
    return NYSE_EARLY_CLOSE_2024.get(d) or NYSE_EARLY_CLOSE.get(d) or time(16, 0)


def is_early_close(d: date) -> bool:
    return close_time(d) != time(16, 0)


def expected_rth_minutes(d: date) -> int:
    """Regular-hours minute count: 09:30 to the session close, exclusive of the close minute."""
    c = close_time(d)
    return (c.hour * 60 + c.minute) - (RTH_OPEN.hour * 60 + RTH_OPEN.minute)


def expected_window_minutes(d: date) -> int:
    """Minutes in the lab's 04:00 to close acquisition window."""
    c = close_time(d)
    return (c.hour * 60 + c.minute) - (PREMARKET_START.hour * 60 + PREMARKET_START.minute)


def signal_month_of(d: date) -> str | None:
    key = d.strftime("%Y-%m")
    return key if key in SIGNAL_MONTHS else None


def raw_eod_path(symbol: str, chunk: str):
    from ingest.paths import safe_symbol_filename
    return RAW_EOD / chunk / f"{safe_symbol_filename(symbol)}.parquet"


def raw_bar_path(session_date: date, symbol: str):
    from ingest.paths import safe_symbol_filename
    return RAW_BARS / session_date.isoformat() / f"{safe_symbol_filename(symbol)}.parquet"


def audit_bar_path(session_date: date, symbol: str, tag: str):
    from ingest.paths import safe_symbol_filename
    return AUDIT_ROOT / tag / session_date.isoformat() / f"{safe_symbol_filename(symbol)}.parquet"


def definition() -> dict:
    """The frozen boundaries, published before any data are touched."""
    return {
        "definition_id": DEFINITION_ID,
        "pristine_oos_signal_months": list(SIGNAL_MONTHS),
        "signal_month_count": len(SIGNAL_MONTHS),
        "signal_period": {"start": SIGNAL_START.isoformat(), "end": SIGNAL_END.isoformat()},
        "warmup": {"start": WARMUP_START.isoformat(), "end": WARMUP_END.isoformat(),
                   "role": "ranking and feature history only; creates no positions and owns no signal"},
        "august_2025": {"role": "twelfth and final OOS signal month, not warmup",
                        "source": "already held locally from the previous study's warmup; reusable only "
                                  "after provenance and overlap authentication against a fresh vendor sample"},
        "new_bulk_acquisition": {"start": BULK_START.isoformat(), "end": BULK_END.isoformat(),
                                 "covers": "August 2024 warmup plus the September 2024 to July 2025 signal months"},
        "lifecycle_tail": {"start": LIFECYCLE_START.isoformat(), "end": LIFECYCLE_END.isoformat(),
                           "role": "ten-session hold completion for late-August 2025 cohorts only; "
                                   "signal-month ownership stays with August 2025"},
        "future_reveal_account": {"starting_equity": STARTING_EQUITY,
                                  "note": "the reveal account starts fresh before the first September 2024 cohort"},
        "calendar_rule": ("nominal Wednesday signal; if Wednesday is closed roll backward to the most recent "
                          "exchange session; entry is the first valid exchange session after the signal; "
                          "Hn counts n exchange sessions after the actual fill; early closes preserved"),
        "authorization": ("Arrow 013 is acquisition, authentication, normalization and certification only. "
                          "No strategy is run, no ranking or selection is produced or inspected, and no "
                          "performance of any kind is calculated on this period."),
        "embargo": ("No Winner-Fade replay, no top-eight or top-twenty output, no selected-name reveal, no "
                    "C0/C1/C2/C3 scoring, no trade P&L, hit rate, drawdown, monthly return, ending equity or "
                    "rank-one outcome, and no rule tuning from this period."),
    }
