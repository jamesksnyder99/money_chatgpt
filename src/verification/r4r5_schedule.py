"""Arrow 007 weekly schedule helper — frozen before any scoring.

The rule, fixed by the user for all future work:

1. Each weekly cohort has a nominal Wednesday signal anchor.
2. If that Wednesday is not an exchange session, roll backward one calendar day at a
   time to the most recent valid exchange session. A closed Wednesday never deletes the
   week.
3. Entry is the first valid exchange session strictly after the signal session.
4. Hn exits are n exchange sessions after the actual fill session.
5. Early-close sessions use their own final regular-hours minute.
6. The nominal weekly anchor never moves: a holiday cannot create two cohorts in one
   week, and it cannot permanently shift later weeks.
"""
from __future__ import annotations

from datetime import date, timedelta

from ingest.calendar import is_nyse_session
from verification.r4r5_data import FEATS, INDEX

RULE_ID = "cg_arrow007_weekly_wednesday_rollback_v1"
NOMINAL_WEEKDAY = 2  # Wednesday


def nominal_anchors(first: date, last: date) -> list[date]:
    """Every nominal Wednesday in [first, last], regardless of exchange status."""
    d = first + timedelta(days=(NOMINAL_WEEKDAY - first.weekday()) % 7)
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out


def signal_for(anchor: date, *, max_rollback: int = 6) -> date | None:
    """Roll backward from the nominal anchor to the most recent exchange session."""
    if anchor.weekday() != NOMINAL_WEEKDAY:
        raise ValueError("anchor must be a nominal Wednesday")
    d = anchor
    for _ in range(max_rollback + 1):
        if is_nyse_session(d):
            return d
        d -= timedelta(days=1)
    return None


def entry_for(signal: date) -> date | None:
    """First valid exchange session strictly after the signal session."""
    i = INDEX.get(signal)
    if i is None or i + 1 >= len(FEATS):
        return None
    return FEATS[i + 1]


def exit_for(fill: date, hold: int) -> date | None:
    i = INDEX.get(fill)
    if i is None or i + hold >= len(FEATS):
        return None
    return FEATS[i + hold]


def weekly_schedule(first: date, last: date) -> list[dict]:
    """One row per nominal week with the resolved signal and entry sessions."""
    out = []
    for anchor in nominal_anchors(first, last):
        signal = signal_for(anchor)
        if signal is None:
            out.append({"nominal_anchor": anchor, "signal": None, "entry": None,
                        "rolled_back_days": None, "status": "NO_SESSION_IN_ROLLBACK_WINDOW"})
            continue
        entry = entry_for(signal)
        out.append({"nominal_anchor": anchor, "signal": signal, "entry": entry,
                    "rolled_back_days": (anchor - signal).days,
                    "status": "OK" if entry is not None else "NO_ENTRY_SESSION_AVAILABLE"})
    return out


def schedule_diff(existing_signals: list[date], first: date, last: date) -> dict:
    """Compare the frozen rule against the signal dates the study currently uses."""
    rows = weekly_schedule(first, last)
    derived = [r["signal"] for r in rows if r["signal"] is not None]
    cur = sorted(existing_signals)
    rolled = [r for r in rows if r["rolled_back_days"]]
    return {"rule_id": RULE_ID, "weeks": len(rows), "derived_signals": len(derived),
            "existing_signals": len(cur), "identical": derived == cur,
            "only_in_derived": [d.isoformat() for d in sorted(set(derived) - set(cur))],
            "only_in_existing": [d.isoformat() for d in sorted(set(cur) - set(derived))],
            "weeks_requiring_rollback": [{"nominal_anchor": r["nominal_anchor"].isoformat(),
                                          "signal": r["signal"].isoformat(),
                                          "rolled_back_days": r["rolled_back_days"]} for r in rolled],
            "entry_is_next_session_for_all": all(
                r["entry"] == entry_for(r["signal"]) for r in rows if r["signal"] and r["entry"])}
