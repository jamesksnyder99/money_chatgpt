"""Arrow 006 corrected point-in-time ranking: rebuild the $10-$80 field from repaired data.

The unchanged rule is applied to complete inputs: common stock, not an exchange-traded
product, not a documented Nasdaq test issue, prior close in [$10, $80] and prior-day
dollar volume >= $10M on the signal session; rank the whole field by the 15-session
regular-hours close return; take the top eight.

Ranking by raw 15-session return and by the historical IWM residual give the same
order within a session, because the benchmark term is a per-session constant. Prices
are converted into signal-session units only with dated documented events.
"""
from __future__ import annotations

from datetime import date

from verification.r4r5_data import (
    FEATS, INDEX, action_events, adjustment_factor, features, history, present,
    spans_non_comparable, unit_factor,
)

LOOKBACK = 15
SLOTS = 8


def endpoint_close(symbol: str, d: date, summaries: dict):
    rec = summaries.get((d.isoformat(), symbol))
    return rec["close"] if present(rec) else None


NO_TRADING = {"DOCUMENTED_NO_TRADING"}


def rank_cohort(signal: date, candidates: dict, summaries: dict, status: dict | None = None,
                events=None) -> dict:
    """candidates: symbol -> {prior_close, prior_dollar_volume}. Returns ranked rows plus scope.

    A candidate that genuinely did not trade at a ranking endpoint cannot be ranked under the
    unchanged rule, exactly as the original engine skipped it; that is a rule-faithful
    exclusion. A candidate whose endpoint is merely absent from our data is an unresolved
    observation and is reported as such.
    """
    status = status or {}
    back = FEATS[INDEX[signal] - LOOKBACK]
    rows, unrankable = [], []
    for sym in sorted(candidates):
        span = spans_non_comparable(sym, back, signal)
        if span is not None:
            unrankable.append({"symbol": sym, "endpoint": "window",
                               "endpoint_date": span["effective_session"],
                               "vendor_status": "DOCUMENTED_NON_COMPARABLE_EVENT",
                               "classification": "RULE_FAITHFUL_NON_COMPARABLE_UNITS",
                               "event_type": span["event_type"], "source": span["source"],
                               "signal_close_present": True, "lookback_close_present": True})
            continue
        now = endpoint_close(sym, signal, summaries)
        then = endpoint_close(sym, back, summaries)
        if now is None or then is None or then <= 0:
            missing_at = signal if now is None else back
            st = status.get((sym, missing_at.isoformat()), "NOT_REQUESTED")
            unrankable.append({"symbol": sym,
                               "endpoint": "signal" if now is None else "lookback",
                               "endpoint_date": missing_at.isoformat(),
                               "vendor_status": st,
                               "classification": "RULE_FAITHFUL_NO_TRADING" if st in NO_TRADING
                                                 else "UNRESOLVED_OBSERVATION",
                               "signal_close_present": now is not None,
                               "lookback_close_present": then is not None})
            continue
        factor = adjustment_factor(sym, back, signal, events)
        ret = now / (then * factor) - 1
        rows.append({"symbol": sym, "prior_close": candidates[sym]["prior_close"],
                     "prior_dv": candidates[sym]["prior_dollar_volume"], "raw_return": ret,
                     "documented_rank_factor": factor, "signal_close": now, "lookback_close": then,
                     "lookback_date": back.isoformat()})
    rows.sort(key=lambda h: (-h["raw_return"], h["symbol"]))
    for i, h in enumerate(rows, 1):
        h["rank"] = i
    unresolved = [u for u in unrankable if u["classification"] == "UNRESOLVED_OBSERVATION"]
    return {"signal": signal.isoformat(), "lookback_date": back.isoformat(), "rows": rows,
            "n_field": len(rows), "n_candidates": len(candidates), "unrankable": unrankable,
            "unrankable_no_trading": len(unrankable) - len(unresolved),
            "unrankable_unresolved": len(unresolved),
            "field_ceiling": max((h["prior_close"] for h in rows), default=None),
            "ranking_scope": "CERTIFIED_RULE_FIELD_10_80" if not unresolved else "RULE_FIELD_WITH_UNRESOLVED"}


def cohort_features(signal: date, rows: list[dict], summaries: dict) -> dict:
    out = {}
    for h in rows:
        hist = history(h["symbol"], FEATS[INDEX[signal] - 20: INDEX[signal] + 1], signal, summaries)
        out[h["symbol"]] = features(hist)
    return out


def corrected_cohorts(cohort_field: dict, candidate_meta: dict, summaries: dict,
                      status: dict | None = None) -> tuple[list[dict], list[dict]]:
    """Return (cohorts, reconciliation rows) for the corrected R2 selection."""
    out, recon = [], []
    for iso in sorted(cohort_field):
        signal = date.fromisoformat(iso)
        cands = {s: candidate_meta[iso][s] for s in cohort_field[iso]["rule_field"] if s in candidate_meta[iso]}
        ranked = rank_cohort(signal, cands, summaries, status)
        top = ranked["rows"][:SLOTS]
        fill = FEATS[INDEX[signal] + 1]
        out.append({"signal": signal, "signal_iso": iso, "split": "IS" if signal.month in {9, 11, 1, 3, 5, 7} else "OOS",
                    "fill": fill, "rows": top, "n_field": ranked["n_field"], "field_ceiling": ranked["field_ceiling"],
                    "ranking_scope": ranked["ranking_scope"], "unrankable": ranked["unrankable"],
                    "unrankable_unresolved": ranked["unrankable_unresolved"]})
        old = cohort_field[iso]["old_top8"]
        new = [h["symbol"] for h in top]
        old_rank = {s: i + 1 for i, s in enumerate(old)}
        recon.append({"cohort_id": iso, "old_field_size": len(cohort_field[iso]["cached"]),
                      "corrected_field_size": ranked["n_field"],
                      "restored_candidates": len(cohort_field[iso]["missing"]),
                      "removed_test_issues": len(cohort_field[iso]["cached_not_eligible"]),
                      "unrankable_no_trading": ranked["unrankable_no_trading"],
                      "unrankable_unresolved": ranked["unrankable_unresolved"],
                      "old_top8": old, "corrected_top8": new,
                      "added": [s for s in new if s not in old], "dropped": [s for s in old if s not in new],
                      "rank_changes": {s: [old_rank.get(s), i + 1] for i, s in enumerate(new)
                                       if old_rank.get(s) != i + 1},
                      "membership_changed": new != old,
                      "ranking_scope": ranked["ranking_scope"]})
    return out, recon


def adjusted_path(symbol: str, first_idx: int, last_idx: int, asof, summaries: dict) -> list[tuple]:
    """Observed closes and opens converted into as-of share units with every documented event.

    The conversion is direction-aware. A holding window is screened in fill units, so sessions
    after a consolidation effective during the hold sit on the far side of the as-of session and
    have to be divided rather than multiplied; the backward-only form silently left them
    unconverted and the screen then reported the issuer's own documented consolidation as an
    unexplained discontinuity.
    """
    out = []
    for j in range(first_idx, last_idx + 1):
        d = FEATS[j]
        rec = summaries.get((d.isoformat(), symbol))
        if not present(rec):
            continue
        f = unit_factor(symbol, d, asof)
        out.append((d, rec["open"] * f, rec["close"] * f, rec["volume"] / f if rec["volume"] else rec["volume"]))
    return out


def screen_adjusted(symbol: str, first_idx: int, last_idx: int, asof, summaries: dict,
                    threshold: float = 2.0) -> dict:
    """Rescreen the action-adjusted series. Applying some event in a window is not a clearance:
    the adjusted path itself must be continuous."""
    path = adjusted_path(symbol, first_idx, last_idx, asof, summaries)
    worst, worst_date = 1.0, None
    prev = None
    for d, op, cl, _vol in path:
        if prev is not None:
            for px in (op, cl):
                ratio = px / prev
                if max(ratio, 1 / ratio) > max(worst, 1 / worst):
                    worst, worst_date = ratio, d.isoformat()
        prev = cl
    big = max(worst, 1 / worst)
    return {"max_adjusted_ratio": worst, "max_adjusted_ratio_date": worst_date,
            "observations": len(path),
            "adjusted_discontinuity": bool(big >= threshold)}


def lookback_integrity(signal, symbol: str, summaries: dict, resolutions: dict | None = None,
                       threshold: float = 2.0) -> dict:
    """Certify that a 15-session ranking return rests on one consistent share unit.

    All documented events in the window are applied first; the adjusted path is then
    rescreened. A window is only clear when the adjusted series carries no material
    discontinuity, or when every remaining discontinuity has dated evidence that it is a
    price move rather than a unit change.
    """
    i = INDEX[signal]
    scr = screen_adjusted(symbol, i - LOOKBACK - 1, i, signal, summaries, threshold)
    lo, hi = FEATS[i - LOOKBACK].isoformat(), signal.isoformat()
    applied = [e for e in action_events() if e["symbol"] == symbol and lo < e["effective_session"] <= hi]
    if not scr["adjusted_discontinuity"]:
        return {"lookback_flag": "NONE" if not applied else "RESOLVED_BY_DOCUMENTED_ACTION",
                "lookback_max_ratio": scr["max_adjusted_ratio"],
                "lookback_ratio_date": scr["max_adjusted_ratio_date"],
                "lookback_events_applied": len(applied),
                "lookback_resolution": "ADJUSTED_SERIES_CONTINUOUS"}
    res = (resolutions or {}).get((symbol, scr["max_adjusted_ratio_date"]))
    return {"lookback_flag": "RANKING_WINDOW_DISCONTINUITY",
            "lookback_max_ratio": scr["max_adjusted_ratio"],
            "lookback_ratio_date": scr["max_adjusted_ratio_date"],
            "lookback_events_applied": len(applied),
            "lookback_resolution": res or "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"}


def holding_integrity(fill, exit_d, symbol: str, summaries: dict, resolutions: dict | None = None,
                      threshold: float = 2.0) -> dict:
    """Same rescreen across the holding window, in fill-session units."""
    scr = screen_adjusted(symbol, INDEX[fill] - 1, INDEX[exit_d], fill, summaries, threshold)
    if not scr["adjusted_discontinuity"]:
        return {"holding_flag": "NONE", "holding_max_ratio": scr["max_adjusted_ratio"],
                "holding_ratio_date": scr["max_adjusted_ratio_date"],
                "holding_resolution": "ADJUSTED_SERIES_CONTINUOUS"}
    res = (resolutions or {}).get((symbol, scr["max_adjusted_ratio_date"]))
    return {"holding_flag": "HOLDING_WINDOW_DISCONTINUITY",
            "holding_max_ratio": scr["max_adjusted_ratio"],
            "holding_ratio_date": scr["max_adjusted_ratio_date"],
            "holding_resolution": res or "UNEXPLAINED_HOLDING_WINDOW_DISCONTINUITY"}
