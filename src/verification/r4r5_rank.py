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
)

LOOKBACK = 15
SLOTS = 8


def endpoint_close(symbol: str, d: date, summaries: dict):
    rec = summaries.get((d.isoformat(), symbol))
    return rec["close"] if present(rec) else None


NO_TRADING = {"DOCUMENTED_NO_TRADING"}


def rank_cohort(signal: date, candidates: dict, summaries: dict, status: dict | None = None) -> dict:
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
        factor = adjustment_factor(sym, back, signal)
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


def lookback_integrity(signal, symbol: str, summaries: dict, resolutions: dict | None = None) -> dict:
    """Screen the 15-session ranking window for a discontinuity large enough to be a
    corporate action rather than a price move.

    A ranking return is only rule-faithful if its two endpoints are in the same price
    units. This flags candidates whose window contains a jump that an undocumented split
    would produce. It never infers a split and never changes a price: it reports whether
    the selection rests on certified units.
    """
    i = INDEX[signal]
    prev, worst, worst_date = None, 1.0, None
    for j in range(i - LOOKBACK - 1, i + 1):
        d = FEATS[j]
        rec = summaries.get((d.isoformat(), symbol))
        if not present(rec):
            continue
        if prev is not None:
            for px in (rec["open"], rec["close"]):
                ratio = px / prev
                if max(ratio, 1 / ratio) > max(worst, 1 / worst):
                    worst, worst_date = ratio, d.isoformat()
        prev = rec["close"]
    big = max(worst, 1 / worst)
    if big < 2.0:
        return {"lookback_flag": "NONE", "lookback_max_ratio": worst, "lookback_ratio_date": worst_date,
                "lookback_resolution": "NONE"}
    lo, hi = FEATS[i - LOOKBACK].isoformat(), signal.isoformat()
    documented = [e for e in action_events()
                  if e["symbol"] == symbol and lo < e["effective_session"] <= hi]
    if documented:
        res = "DOCUMENTED_ACTION_IN_RANKING_WINDOW"
    else:
        res = (resolutions or {}).get((symbol, worst_date)) or "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"
    return {"lookback_flag": "RANKING_WINDOW_DISCONTINUITY", "lookback_max_ratio": worst,
            "lookback_ratio_date": worst_date, "lookback_resolution": res}
