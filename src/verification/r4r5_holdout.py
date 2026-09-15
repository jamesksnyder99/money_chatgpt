"""Arrow 014 — bind the frozen engine to the pristine September 2024 to August 2025 corridor.

The Winner-Fade engine was written against the 2025-26 study and binds its session index,
cutoff and tape end at import time. Re-pointing it at the holdout therefore needs an explicit,
asserted rebinding rather than a hopeful monkeypatch: every module that imported those names by
value gets its own copy replaced, and `activate()` verifies each one afterwards.

Nothing about the strategy changes. The ranking rule, the R4/R5 sizing rules, the causal
pre-order convention, the integer-share flooring, the cost model and the account identities are
the same objects the historical study used. Only the calendar window, the source tree for bars
and the corporate-action table are holdout-specific.

Corridor facts, proved in Phase 0A rather than assumed:

  warmup            2024-08-01 .. 2024-08-30, owns no signal
  signal months     2024-09 .. 2025-08, twelve months
  cutoff            the last exchange close of August 2025
  lifecycle tail    September 2025, supports late-August H8/H9/H10 only

This module calculates no outcome. It supplies dates, paths and bindings.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

CORRIDOR_START = date(2024, 8, 1)
CORRIDOR_END = date(2025, 9, 30)
WARMUP_END = date(2024, 8, 30)
SIGNAL_START = date(2024, 9, 1)
SIGNAL_END = date(2025, 8, 31)
NOMINAL_WEEKDAY = 2                      # Wednesday
MAX_ROLLBACK_DAYS = 6
HOLDS = (8, 9, 10)
STARTING_EQUITY = 100000.0
CORRIDOR_ID = "cg_arrow014_pristine_sep2024_aug2025_v1"

_ACTIVE = False


# ----------------------------------------------------------------- calendar
def _sessions(start: date, end: date) -> list[date]:
    from ingest import holdout2024 as H
    return H.sessions(start, end)


FEATS: list[date] = _sessions(CORRIDOR_START, CORRIDOR_END)
INDEX: dict = {d: i for i, d in enumerate(FEATS)}
CUTOFF: date = max(d for d in FEATS if d <= SIGNAL_END)
SCORE: list[date] = [d for d in FEATS if date(2024, 9, 1) <= d <= CUTOFF]
LOCAL_TAPE_END: date = CORRIDOR_END


def nominal_anchors(first: date = SIGNAL_START, last: date = SIGNAL_END) -> list[date]:
    """Every nominal Wednesday whose week belongs to the signal period."""
    d = first + timedelta(days=(NOMINAL_WEEKDAY - first.weekday()) % 7)
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=7)
    return out


def signal_for(anchor: date) -> date | None:
    """Roll backward from the nominal Wednesday to the most recent exchange session.

    A closed Wednesday never deletes the week and never shifts later weeks, because the
    nominal anchor sequence is independent of the resolved signal dates.
    """
    from ingest import holdout2024 as H
    if anchor.weekday() != NOMINAL_WEEKDAY:
        raise ValueError("anchor must be a nominal Wednesday")
    d = anchor
    for _ in range(MAX_ROLLBACK_DAYS + 1):
        if H.is_session(d):
            return d
        d -= timedelta(days=1)
    return None


def entry_for(signal: date) -> date | None:
    i = INDEX.get(signal)
    return FEATS[i + 1] if i is not None and i + 1 < len(FEATS) else None


def exit_for(fill: date, hold: int) -> date | None:
    i = INDEX.get(fill)
    return FEATS[i + hold] if i is not None and i + hold < len(FEATS) else None


def cohort_calendar() -> list[dict]:
    """The frozen pristine cohort list, derived from the calendar rather than assumed."""
    out = []
    for anchor in nominal_anchors():
        s = signal_for(anchor)
        if s is None:
            out.append({"nominal_anchor": anchor.isoformat(), "signal": None, "entry": None,
                        "status": "NO_SESSION_IN_ROLLBACK_WINDOW"})
            continue
        e = entry_for(s)
        row = {"nominal_anchor": anchor.isoformat(), "signal_date": s.isoformat(),
               "entry_date": e.isoformat() if e else None,
               "rolled_back_days": (anchor - s).days,
               "signal_month": s.strftime("%Y-%m"),
               "status": "OK" if e else "NO_ENTRY_SESSION"}
        for h in HOLDS:
            x = exit_for(e, h) if e else None
            row[f"h{h}_exit_date"] = x.isoformat() if x else None
            if x is None:
                row["status"] = f"NO_H{h}_EXIT_SESSION"
        out.append(row)
    return out


def signal_dates() -> list[date]:
    return [date.fromisoformat(r["signal_date"]) for r in cohort_calendar() if r.get("signal_date")]


# ----------------------------------------------------------------- source tree
def holdout_candidate_paths(d: date, symbol: str):
    """Bar partitions for a corridor session, newest-acquisition tree first.

    Sessions from 2024-08-01 to 2025-07-31 were newly acquired by Arrow 013 into the immutable
    holdout tree. August 2025 and the September 2025 lifecycle tail come from the previously
    held, separately authenticated study partitions. Both are read-only here.
    """
    from ingest.paths import DATA, safe_symbol_filename
    from ingest import holdout2024 as H
    fn = safe_symbol_filename(symbol) + ".parquet"
    return [("holdout_raw", H.RAW_BARS / d.isoformat() / fn),
            ("virgin", DATA / "virgin" / "bars" / d.isoformat() / fn),
            ("full", DATA / "full" / "bars" / d.isoformat() / fn)]


# ----------------------------------------------------------------- activation
_TARGETS = {
    "verification.r4r5_data": ("FEATS", "INDEX", "SCORE", "CUTOFF", "LOCAL_TAPE_END"),
    "verification.r4r5_replay": ("FEATS", "INDEX", "SCORE", "CUTOFF", "LOCAL_TAPE_END"),
    "verification.r4r5_accounting": ("SCORE", "CUTOFF"),
    "verification.r4r5_oracle": ("SCORE",),
    "verification.r4r5_rank": ("FEATS", "INDEX"),
    "verification.r4r5_anatomy": ("FEATS", "INDEX"),
    "verification.r4r5_equity": ("SCORE",),
    "verification.r4r5_repair": ("FEATS", "INDEX"),
}
_VALUES = {"FEATS": None, "INDEX": None, "SCORE": None, "CUTOFF": None, "LOCAL_TAPE_END": None}


def activate(action_path: Path | None = None) -> dict:
    """Rebind the engine to the holdout corridor, then verify every binding actually moved.

    `action_path` points the corporate-action / identity layer at the holdout's own documented
    table. Until Arrow 014 assembles that table the caller passes the empty holdout table, so
    no 2025-26 event can silently normalize a 2024-25 price.
    """
    import importlib
    global _ACTIVE
    _VALUES.update({"FEATS": FEATS, "INDEX": INDEX, "SCORE": SCORE,
                    "CUTOFF": CUTOFF, "LOCAL_TAPE_END": LOCAL_TAPE_END})
    applied = {}
    for mod_name, names in _TARGETS.items():
        mod = importlib.import_module(mod_name)
        for n in names:
            if not hasattr(mod, n):
                raise RuntimeError(f"{mod_name} has no attribute {n}; engine layout changed")
            setattr(mod, n, _VALUES[n])
            applied[f"{mod_name}.{n}"] = True

    data = importlib.import_module("verification.r4r5_data")
    data.candidate_paths = holdout_candidate_paths
    rank = importlib.import_module("verification.r4r5_rank")
    if hasattr(rank, "candidate_paths"):
        rank.candidate_paths = holdout_candidate_paths
    if action_path is not None:
        data.ACTION_PATH = Path(action_path)
    for fn in ("action_events", "identity_events", "trading_events", "non_comparable_events"):
        getattr(data, fn).cache_clear()
    data._safe_dir.cache_clear()
    data.manifest_rows.cache_clear()

    # verify rather than assume
    bad = []
    for mod_name, names in _TARGETS.items():
        mod = importlib.import_module(mod_name)
        for n in names:
            if getattr(mod, n) is not _VALUES[n]:
                bad.append(f"{mod_name}.{n}")
    if data.candidate_paths is not holdout_candidate_paths:
        bad.append("verification.r4r5_data.candidate_paths")
    if bad:
        raise RuntimeError(f"holdout activation did not take effect for: {bad}")
    _ACTIVE = True
    return {"corridor_id": CORRIDOR_ID, "bindings_applied": len(applied),
            "sessions": len(FEATS), "score_sessions": len(SCORE),
            "cutoff": CUTOFF.isoformat(), "local_tape_end": LOCAL_TAPE_END.isoformat(),
            "action_path": str(action_path) if action_path else None}


def assert_active() -> None:
    if not _ACTIVE:
        raise RuntimeError("holdout corridor is not active; call activate() first")
    import importlib
    replay = importlib.import_module("verification.r4r5_replay")
    if replay.CUTOFF != CUTOFF or replay.FEATS is not FEATS:
        raise RuntimeError("holdout corridor binding was lost")
