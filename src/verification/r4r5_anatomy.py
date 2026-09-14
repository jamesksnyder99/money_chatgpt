"""Arrow 011 — Winner-Fade anatomy: pre-entry features, sizing-neutral outcomes, holding paths.

An isolated analysis layer over the frozen Arrow 008/010 ledgers. It changes no engine rule
and no ledger. Three schemas are kept physically separate:

  SIGNAL_CLOSE features  information available at the signal session's regular-hours close
  PRE_ORDER features     information available strictly before the next-session order, i.e.
                         through the last fully completed pre-order minute bar
  OUTCOMES               entry/exit prices, holding paths and P&L, never used as predictors

Units. Every SIGNAL_CLOSE feature is stated in signal-session units: earlier observations are
converted with only the corporate actions effective on or before the signal session. Every
PRE_ORDER feature is stated in entry-session units. Outcome price returns are stated in exit
units through the frozen ledger's action factor F (old shares per new share), so that the
comparable ten-session short price return is 1 - P1 / (F * P0).

Missingness is a state, never a value: a feature that cannot be computed is None and the
row carries an explicit coverage flag.
"""
from __future__ import annotations

from datetime import date, datetime, time
import math
import statistics

import polars as pl

from verification.r4r5_data import (
    FEATS, INDEX, action_events, adjustment_factor, features, history, present, read_bars,
)

SCHEMA_VERSION = "cg_arrow011_anatomy_v1"
HOLD = 10
PRICE_BANDS = (("10-20", 10.0, 20.0), ("20-40", 20.0, 40.0), ("40-80", 40.0, 80.0))
FOUR_STATES = {(False, False): "S1_FULL_weak_quiet", (False, True): "S2_HALF_weak_loud",
               (True, False): "S3_HALF_strong_quiet", (True, True): "S4_QUARTER_strong_loud"}


# ----------------------------------------------------------------------------- helpers
def _lr(a: float | None, b: float | None) -> float | None:
    """log(a / b) when both are positive finite numbers."""
    if a is None or b is None or a <= 0 or b <= 0 or not (math.isfinite(a) and math.isfinite(b)):
        return None
    return math.log(a / b)


def _ret(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b <= 0 or not (math.isfinite(a) and math.isfinite(b)):
        return None
    return a / b - 1


def price_band(px: float | None) -> str:
    """Non-overlapping bands: lower bound inclusive, upper bound exclusive."""
    if px is None or not math.isfinite(px):
        return "UNAVAILABLE"
    for name, lo, hi in PRICE_BANDS:
        if lo <= px < hi:
            return name
    return "OUTSIDE_10_80"


def four_state(ret3: float | None, volume_ratio: float | None) -> str:
    """The frozen R5 rule's four states, with missing values as their own state.

    Exact operators from verification.r4r5_replay.sizing: momentum halves when ret3 > 0,
    volume halves when volume_ratio > 1. Either feature missing is MISSING, never a state.
    """
    if ret3 is None or volume_ratio is None or not (math.isfinite(ret3) and math.isfinite(volume_ratio)):
        return "MISSING_FEATURE"
    return FOUR_STATES[(ret3 > 0, volume_ratio > 1)]


# ----------------------------------------------------------------------------- SIGNAL_CLOSE
def signal_close_features(symbol: str, signal: date, summaries: dict) -> dict:
    """Daily-bar features in signal-session units from the 21 sessions ending at the signal.

    The window is the frozen feature window (20 sessions of history plus the signal). Each
    feature declares what it needs; when a needed session is absent the feature is None.
    """
    i = INDEX[signal]
    days = FEATS[i - 20: i + 1]
    hist = history(symbol, days, signal, summaries)
    frozen = features(hist)
    closes = [h["close"] if h else None for h in hist]
    opens = [h["open"] if h else None for h in hist]
    highs = [h["high"] if h else None for h in hist]
    lows = [h["low"] if h else None for h in hist]
    vols = [h["volume"] if h else None for h in hist]
    n_present = sum(1 for h in hist if h)
    c0 = closes[-1]
    out = {"schema": SCHEMA_VERSION, "cutoff": "SIGNAL_CLOSE", "signal_date": signal.isoformat(),
           "history_sessions_present": n_present, "history_sessions_required": 21,
           "signal_close": c0, "signal_close_band": price_band(c0),
           "ret3_frozen": frozen["ret3"], "volume_ratio_frozen": frozen["volume_ratio"],
           "four_state": four_state(frozen["ret3"], frozen["volume_ratio"])}
    # --- run-up shape
    for k in (1, 3, 5, 10, 15):
        out[f"ret{k}"] = _ret(c0, closes[-1 - k]) if len(closes) > k else None
    out["ret15_to_5"] = _ret(closes[-6], closes[-16]) if closes[-6] and closes[-16] else None
    out["recent_minus_earlier"] = (out["ret5"] - out["ret15_to_5"]
                                   if out["ret5"] is not None and out["ret15_to_5"] is not None else None)
    r_prev3 = _ret(closes[-4], closes[-7]) if closes[-4] and closes[-7] else None
    out["acceleration_3"] = (out["ret3"] - r_prev3) if out["ret3"] is not None and r_prev3 is not None else None
    # session log returns over the 15-session ranking window
    lrs = []
    for t in range(-15, 0):
        lrs.append(_lr(closes[t + len(closes)], closes[t - 1 + len(closes)]) if closes[t + len(closes)] and closes[t - 1 + len(closes)] else None)
    valid = [x for x in lrs if x is not None]
    out["window_sessions_present"] = len(valid)
    if len(valid) == 15:
        total = sum(valid)
        biggest = max(valid)
        out["max_session_logret_15"] = biggest
        out["largest_session_share_of_advance"] = (biggest / total) if total > 0 else None
        top3 = sum(sorted(valid, reverse=True)[:3])
        out["top3_sessions_share_of_advance"] = (top3 / total) if total > 0 else None
        out["up_sessions_15"] = sum(1 for x in valid if x > 0)
        out["logret_std_15"] = statistics.pstdev(valid)
        out["mean_abs_logret_10"] = statistics.mean(abs(x) for x in valid[-10:])
        # gap versus continuous-session contribution, in consistent adjusted units
        gaps, intra = [], []
        for t in range(-15, 0):
            j = t + len(closes)
            g = _lr(opens[j], closes[j - 1]) if opens[j] and closes[j - 1] else None
            s = _lr(closes[j], opens[j]) if closes[j] and opens[j] else None
            if g is None or s is None:
                gaps = None
                break
            gaps.append(g)
            intra.append(s)
        if gaps is not None:
            out["gap_logret_sum_15"] = sum(gaps)
            out["intraday_logret_sum_15"] = sum(intra)
            out["gap_share_of_advance"] = (sum(gaps) / total) if total > 0 else None
        else:
            out["gap_logret_sum_15"] = out["intraday_logret_sum_15"] = out["gap_share_of_advance"] = None
    else:
        for k in ("max_session_logret_15", "largest_session_share_of_advance", "top3_sessions_share_of_advance",
                  "up_sessions_15", "logret_std_15", "mean_abs_logret_10", "gap_logret_sum_15",
                  "intraday_logret_sum_15", "gap_share_of_advance"):
            out[k] = None
    # --- price location
    h20 = [x for x in highs if x is not None]
    l20 = [x for x in lows if x is not None]
    c20 = [x for x in closes if x is not None]
    if c0 and len(c20) == 21 and len(h20) == 21 and len(l20) == 21:
        out["close_vs_high20"] = c0 / max(h20) - 1
        out["close_vs_low20"] = c0 / min(l20) - 1
        out["close_vs_max_close15"] = c0 / max(c20[-16:]) - 1
        rng = max(h20) - min(l20)
        out["position_in_range20"] = ((c0 - min(l20)) / rng) if rng > 0 else None
        dh, dl = highs[-1], lows[-1]
        out["close_location_signal_day"] = ((c0 - dl) / (dh - dl)) if dh and dl and dh > dl else None
        out["signal_day_range_pct"] = ((dh - dl) / c0) if dh and dl else None
        out["mean_range_pct_10"] = statistics.mean((highs[t] - lows[t]) / closes[t] for t in range(-10, 0))
        out["sessions_since_max_close15"] = 20 - max(range(6, 21), key=lambda t: closes[t])
    else:
        for k in ("close_vs_high20", "close_vs_low20", "close_vs_max_close15", "position_in_range20",
                  "close_location_signal_day", "signal_day_range_pct", "mean_range_pct_10",
                  "sessions_since_max_close15"):
            out[k] = None
    # --- volume and liquidity
    v = [x for x in vols if x is not None]
    if len(v) == 21 and c0:
        prior20 = vols[:-1]
        out["volume_ratio_recomputed"] = vols[-1] / statistics.mean(prior20) if statistics.mean(prior20) > 0 else None
        out["volume_trend_5_vs_15"] = (statistics.mean(prior20[-5:]) / statistics.mean(prior20[:15])
                                       if statistics.mean(prior20[:15]) > 0 else None)
        out["dollar_volume_signal_day"] = vols[-1] * c0
        dv = [vols[t] * closes[t] for t in range(21)]
        out["dollar_volume_mean20"] = statistics.mean(dv[:-1])
        out["dollar_volume_cv20"] = (statistics.pstdev(dv[:-1]) / statistics.mean(dv[:-1])
                                     if statistics.mean(dv[:-1]) > 0 else None)
        vol15 = sum(vols[-15:])
        base = statistics.mean(vols[:6]) if statistics.mean(vols[:6]) > 0 else None
        out["volume_expansion_15"] = (vol15 / 15 / base) if base else None
        out["move_per_volume_unit"] = (abs(out["ret15"]) / out["volume_expansion_15"]
                                       if out["ret15"] is not None and out["volume_expansion_15"] else None)
    else:
        for k in ("volume_ratio_recomputed", "volume_trend_5_vs_15", "dollar_volume_signal_day",
                  "dollar_volume_mean20", "dollar_volume_cv20", "volume_expansion_15", "move_per_volume_unit"):
            out[k] = None
    # --- event context known by the signal close
    acts = [e for e in action_events() if e["symbol"] == symbol
            and FEATS[max(0, i - 60)].isoformat() <= e["effective_session"] <= signal.isoformat()]
    out["documented_action_within_60_sessions"] = len(acts)
    out["documented_action_within_lookback15"] = sum(
        1 for e in acts if FEATS[i - 15].isoformat() < e["effective_session"] <= signal.isoformat())
    return out


# ----------------------------------------------------------------------------- PRE_ORDER
def _rth_frame(d: date, symbol: str):
    df, _, path, _ = read_bars(d, symbol)
    return df, path


def pre_order_features(symbol: str, signal: date, entry: date, preorder_ts: str | None,
                       summaries: dict, comparison_sessions: int = 5) -> dict:
    """Entry-session information through the last fully completed pre-order bar.

    The cutoff is the frozen ledger's `preorder_ts`: the bar that starts one minute before
    the final regular-hours minute, on that session's actual schedule. A bar with
    bar_start <= preorder_ts is complete before the order. Nothing from the final minute,
    the session's final range or its full-session volume is used.

    Partial-session volume is compared only with the same elapsed window on the preceding
    sessions, never with a full-session average.
    """
    out = {"schema": SCHEMA_VERSION, "cutoff": "PRE_ORDER", "entry_date": entry.isoformat(),
           "preorder_ts": preorder_ts, "preorder_bars_present": None}
    if preorder_ts is None:
        out["pre_order_available"] = False
        return out
    # preorder_ts is the frozen ledger's New York wall-clock bar start; compare on clock time
    # so the bar's own timezone and resolution never matter
    cut = datetime.fromisoformat(preorder_ts)
    cut_clock = cut.time()
    df, path = _rth_frame(entry, symbol)
    if df is None:
        out["pre_order_available"] = False
        return out
    part = df.filter(pl.col("bar_start").dt.time() <= cut_clock)
    if part.is_empty():
        out["pre_order_available"] = False
        return out
    fac = adjustment_factor(symbol, signal, entry)
    sig = summaries.get((signal.isoformat(), symbol))
    sig_close = sig["close"] * fac if present(sig) else None
    p_open = float(part["open"][0])
    p_last = float(part["close"][-1])
    p_high = float(part["high"].max())
    p_low = float(part["low"].min())
    p_vol = float(part["volume"].sum())
    out.update({"pre_order_available": True, "preorder_bars_present": int(part.height),
                "entry_source_path": path,
                "preorder_price": p_last, "preorder_price_band": price_band(p_last),
                "overnight_gap_vs_signal_close": _ret(p_open, sig_close),
                "signal_close_to_preorder": _ret(p_last, sig_close),
                "open_to_preorder": _ret(p_last, p_open),
                "preorder_location_in_partial_range": ((p_last - p_low) / (p_high - p_low)) if p_high > p_low else None,
                "partial_range_pct": (p_high - p_low) / p_last if p_last > 0 else None,
                "preorder_vs_partial_high": p_last / p_high - 1 if p_high > 0 else None,
                "partial_volume_shares": p_vol})
    # same elapsed window on preceding sessions, in entry-session share units
    j = INDEX[entry]
    comps = []
    for k in range(1, comparison_sessions + 1):
        d = FEATS[j - k]
        prior, _ = _rth_frame(d, symbol)
        if prior is None:
            continue
        window = prior.filter(pl.col("bar_start").dt.time() <= cut_clock)
        if window.is_empty():
            continue
        f = adjustment_factor(symbol, d, entry)
        comps.append(float(window["volume"].sum()) / f)
    out["elapsed_window_comparison_sessions"] = len(comps)
    out["partial_volume_vs_elapsed_window_mean"] = (p_vol / statistics.mean(comps)
                                                    if comps and statistics.mean(comps) > 0 else None)
    out["partial_volume_basis"] = ("entry-session volume through the pre-order bar divided by the "
                                   "mean volume through the same clock time on the preceding "
                                   f"{comparison_sessions} sessions; never a full-session average")
    return out


# ----------------------------------------------------------------------------- OUTCOMES
def sizing_neutral_outcome(t: dict) -> dict:
    """Corporate-action-adjusted ten-session short price return and net per entry dollar.

    F is the frozen ledger's action_factor_over_hold, P0 the entry price in entry units and
    P1 the exit price in exit units: comparable short return = 1 - P1 / (F * P0). Reconciles
    to the ledger, whose gross P&L is (Q / F) * (P0 * F - P1).
    """
    out = {"status": t["status"], "completed": t["status"] in
           ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT")}
    q, p0, p1, f = t.get("quantity"), t.get("entry_price"), t.get("exit_price"), t.get("action_factor_over_hold")
    if out["completed"] and q and p0 and p1 and f:
        pr = 1 - p1 / (f * p0)
        gross = q * p0 * pr
        out.update({"price_return_10": pr,
                    "entry_exposure_dollars": q * p0,
                    "gross_pnl_reconstructed": gross,
                    "gross_pnl_ledger": t["gross_pnl"],
                    "gross_reconciles": abs(gross - t["gross_pnl"]) < 1e-6,
                    "modeled_net": t["modeled_net"],
                    "net_per_entry_dollar": t["modeled_net"] / (q * p0),
                    "cost_drag_per_entry_dollar": (t["gross_pnl"] - t["modeled_net"]) / (q * p0),
                    "price_winner": pr > 0, "net_winner": t["modeled_net"] > 0,
                    "sign_flipped_by_costs": (pr > 0) != (t["modeled_net"] > 0),
                    "exit_units_factor": f})
    else:
        out.update({"price_return_10": None, "entry_exposure_dollars": (q * p0) if q and p0 else None,
                    "modeled_net": None, "net_per_entry_dollar": None, "price_winner": None,
                    "net_winner": None, "sign_flipped_by_costs": None, "exit_units_factor": f,
                    "gross_reconciles": None})
    return out


def holding_path(t: dict, summaries: dict, hold: int = HOLD) -> dict:
    """Close-only path of the sizing-neutral short return at every age 0..hold.

    Age a is the session `a` sessions after the fill. The mark is that session's minute-close
    in that session's units; the entry price is carried into those units through the actions
    effective by then. Absent sessions are stale (None) and counted, never filled forward
    silently. These are OUTCOMES.
    """
    if not t.get("entry_price") or "scheduled_entry_date" not in t:
        return {"path_available": False}
    sym = t["symbol"]
    fill = date.fromisoformat(t["scheduled_entry_date"])
    fi = INDEX[fill]
    p0 = t["entry_price"]
    rets, stale = [], []
    for a in range(0, hold + 1):
        if fi + a >= len(FEATS):
            rets.append(None)
            stale.append(True)
            continue
        d = FEATS[fi + a]
        rec = summaries.get((d.isoformat(), sym))
        if present(rec):
            f = adjustment_factor(sym, fill, d)
            mark = rec["exec_px"] if a in (0, hold) and rec.get("exec_px") else rec["close"]
            rets.append(1 - mark / (f * p0))
            stale.append(False)
        else:
            rets.append(None)
            stale.append(True)
    obs = [(a, r) for a, r in enumerate(rets) if r is not None and a >= 1]
    out = {"path_available": True, "path_ages_observed": len(obs), "path_ages_stale": sum(stale[1:]),
           "path_returns": rets}
    if obs:
        best = max(obs, key=lambda x: x[1])
        worst = min(obs, key=lambda x: x[1])
        out.update({"mfe_close_only": best[1], "mfe_age": best[0],
                    "mae_close_only": worst[1], "mae_age": worst[0],
                    "first_favorable_age": next((a for a, r in obs if r > 0), None),
                    "first_adverse_age": next((a for a, r in obs if r < 0), None),
                    "excursion_basis": "close-only marks at each age; not true intraday extrema"})
    for a in (3, 5, 7, 10):
        out[f"ret_age{a}"] = rets[a] if a < len(rets) else None
    return out


def path_archetype(path: dict, hold: int = HOLD) -> str:
    """Simple, frozen path descriptions from close-only returns. OUTCOME labels only.

    IMMEDIATE_FADE      favorable at age 1 and favorable at the end
    ADVERSE_THEN_FADE   adverse at age 1 or 2 (worst before age 5 below zero), favorable at the end
    FADE_THEN_REVERSAL  favorable at some age before 5 by at least 3% then adverse at the end
    CONTINUATION        adverse at the end, never favorable by 3% on any close
    OTHER               anything else, including partly stale paths
    """
    r = path.get("path_returns") if path.get("path_available") else None
    if not r or r[hold] is None or r[1] is None:
        return "UNLABELED_STALE_OR_OPEN"
    end = r[hold]
    early = [x for x in r[1:5] if x is not None]
    if end > 0 and r[1] > 0:
        return "IMMEDIATE_FADE"
    if end > 0 and early and min(early) < 0:
        return "ADVERSE_THEN_FADE"
    if end <= 0 and early and max(early) >= 0.03:
        return "FADE_THEN_REVERSAL"
    if end <= 0 and all(x < 0.03 for x in r[1:] if x is not None):
        return "CONTINUATION"
    return "OTHER"


# ----------------------------------------------------------------------------- cohort context
def cohort_context(rows: list[dict], full_field: list[dict]) -> dict:
    """Within-eight and field context from the certified ranking rows. SIGNAL_CLOSE.

    rows: the eight selected ranking rows (with raw_return and rank). full_field: every
    ranked row of that cohort's candidate field. Only ranking returns are used.
    """
    rets = [h["raw_return"] for h in rows]
    med = statistics.median(rets)
    spread = max(rets) - min(rets)
    field = sorted((h["raw_return"] for h in full_field), reverse=True)
    ninth = field[8] if len(field) > 8 else None
    out = {}
    for h in rows:
        r = h["rank"]
        nxt = rets[r] if r < len(rets) else ninth
        prev = rets[r - 2] if r >= 2 else None
        out[h["symbol"]] = {
            "rank_in_eight": r, "ret15_rank_return": h["raw_return"],
            "ret15_minus_cohort_median": h["raw_return"] - med,
            "gap_to_next_rank": (h["raw_return"] - nxt) if nxt is not None else None,
            "gap_from_prior_rank": (prev - h["raw_return"]) if prev is not None else None,
            "cohort_ret15_spread": spread, "cohort_ret15_median": med,
            "field_size": len(field), "rank8_minus_rank9": (rets[-1] - ninth) if ninth is not None else None,
            "ret15_field_percentile": (sum(1 for x in field if x < h["raw_return"]) / len(field)) if field else None,
        }
    return out


def selection_episodes(cohort_rows: dict) -> dict:
    """Prior-selection history per ticket from the frozen membership only. SIGNAL_CLOSE.

    cohort_rows: signal_iso -> list of symbols selected. Returns per (signal_iso, symbol):
    number of earlier selections, sessions since the last one, and whether the previous
    selection's ten-session hold was still open at this signal (overlap).
    """
    seen: dict[str, list[str]] = {}
    out = {}
    for iso in sorted(cohort_rows):
        for sym in cohort_rows[iso]:
            prior = seen.get(sym, [])
            last = prior[-1] if prior else None
            gap = (INDEX[date.fromisoformat(iso)] - INDEX[date.fromisoformat(last)]) if last else None
            out[(iso, sym)] = {"prior_selections": len(prior), "sessions_since_last_selection": gap,
                               "previous_hold_still_open": (gap is not None and gap <= HOLD),
                               "episode": "FIRST" if not prior else ("OVERLAPPING_REPEAT" if gap <= HOLD else "LATER_REPEAT")}
            seen.setdefault(sym, []).append(iso)
    return out
