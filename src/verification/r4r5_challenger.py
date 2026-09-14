"""Arrow 012 — challenger lineups and cohort-budget-neutral base allocations.

Four configurations over the same frozen 52 cohorts. Every one keeps the unchanged engine:
the same point-in-time universe and ranking rule, the same entry and exit sessions, the same
causal pre-order price convention, the same integer-share flooring and the same costs. Only
two things move, and only where a challenger says so:

  C0  incumbent            original corrected top eight, frozen R5 tier notionals
  C1  rank-one 1.50x       same eight names, rank one at 1.50x its base notional, funded
                           entirely by a proportional reduction of ranks 2-8
  C2  off-high substitution rank one protected; near-high names in ranks 2-8 replaced by
                           off-high names from original ranks 9-20, then the whole lineup's
                           raw R5 notionals normalized back to the incumbent cohort budget
  C3  combined             C1's reallocation applied to C2's normalized allocations

Cohort base capital T is identical in all four by construction, so no challenger can win by
spending more at the same account equity. Allocations are stated at 100,000 equity; the
account layer multiplies them by its own causal signal-close equity scale.
"""
from __future__ import annotations

import math

from verification.r4r5_replay import sizing

CONFIG_VERSION = "cg_arrow012_challengers_v1"
RANK_ONE_MULTIPLIER = 1.50
SUBSTITUTION_SEARCH_DEPTH = 20
TOL = 1e-9


def base_notionals(rows: list[dict], feats: dict, family: str = "R5") -> dict:
    """Frozen-rule base notional at 100,000 equity for each name, keyed by symbol.

    feats maps symbol -> the frozen feature dict {ret3, volume_ratio} for that name in this
    cohort. The tier comes from the name's own pre-entry features under the unchanged rule.
    """
    out = {}
    for h in rows:
        amount, tier, vm, mm = sizing(family, feats[h["symbol"]])
        out[h["symbol"]] = {"base": amount, "tier": tier, "volume_multiplier": vm,
                            "momentum_multiplier": mm}
    return out


def c1_allocation(rows: list[dict], base: dict, multiplier: float = RANK_ONE_MULTIPLIER) -> dict:
    """Rank one at `multiplier` times its base, funded proportionally by ranks 2-8.

    Returns {"allocation": symbol -> dollars, "ok": bool, "reason": str|None}. The total is the
    incumbent cohort total T to full precision. A nonpositive other-scale fails the cohort
    rather than inventing a cap.
    """
    ordered = sorted(rows, key=lambda h: h["rank"])
    syms = [h["symbol"] for h in ordered]
    b = [base[s]["base"] for s in syms]
    T = sum(b)
    target = multiplier * b[0]
    rest = sum(b[1:])
    if rest <= 0:
        return {"allocation": None, "ok": False, "reason": "ranks 2-8 have no base capital"}
    other_scale = (T - target) / rest
    if other_scale <= 0:
        return {"allocation": None, "ok": False, "reason": f"other_scale {other_scale:.6f} is not positive"}
    alloc = {syms[0]: target}
    for s, x in zip(syms[1:], b[1:]):
        alloc[s] = x * other_scale
    if abs(sum(alloc.values()) - T) > TOL * max(1.0, T):
        return {"allocation": None, "ok": False, "reason": "reallocation does not preserve T"}
    return {"allocation": alloc, "ok": True, "reason": None, "cohort_total": T,
            "other_scale": other_scale, "rank_one_target": target}


def substitution_plan(top8: list[dict], deeper: list[dict], off_high: dict, threshold: float,
                      certified: set) -> dict:
    """The deterministic Arrow 012 off-high substitution over original ranks 9-20.

    top8: the original corrected top eight ranked rows. deeper: original ranks 9-20 ranked
    rows. off_high: symbol -> close_vs_high20 at the signal close. threshold: the frozen
    Arrow 011 `close_vs_high20_is_median`. certified: symbols from ranks 9-20 whose evidence
    is complete enough to trade.

    Rank one is never removable. A removable original is a rank 2-8 name on the near-high side
    (close_vs_high20 >= threshold). An eligible replacement is a rank 9-20 name on the off-high
    side (close_vs_high20 < threshold) that is certified and not already in the lineup. With
    k = min(removable, eligible), the k worst-ranked removables leave and the k best-ranked
    eligibles enter. A name whose off-high value is missing is neither removable nor eligible:
    missing data is never a strategy condition.
    """
    ordered = sorted(top8, key=lambda h: h["rank"])
    held = {h["symbol"] for h in ordered}
    removable = [h for h in ordered[1:]
                 if off_high.get(h["symbol"]) is not None and off_high[h["symbol"]] >= threshold]
    eligible = [h for h in sorted(deeper, key=lambda h: h["rank"])
                if off_high.get(h["symbol"]) is not None and off_high[h["symbol"]] < threshold
                and h["symbol"] in certified and h["symbol"] not in held]
    k = min(len(removable), len(eligible))
    out_rows = sorted(removable, key=lambda h: -h["rank"])[:k]          # rank 8 first
    in_rows = eligible[:k]                                              # rank 9 first
    out_syms = {h["symbol"] for h in out_rows}
    lineup = [h for h in ordered if h["symbol"] not in out_syms] + in_rows
    return {"k": k, "removable": len(removable), "eligible": len(eligible),
            "outgoing": out_rows, "incoming": in_rows, "lineup": lineup,
            "unique": len({h["symbol"] for h in lineup}) == len(lineup) == 8}


def c2_allocation(lineup: list[dict], base_new: dict, incumbent_total: float) -> dict:
    """Normalize the substituted lineup's raw R5 notionals back to the incumbent budget T.

    The new lineup keeps the relative tier information of its own names; only the level is
    rescaled, so the substitution cannot win by happening to draw larger raw tiers.
    """
    S = sum(base_new[h["symbol"]]["base"] for h in lineup)
    if S <= 0:
        return {"allocation": None, "ok": False, "reason": "substituted lineup has no base capital"}
    scale = incumbent_total / S
    alloc = {h["symbol"]: base_new[h["symbol"]]["base"] * scale for h in lineup}
    if abs(sum(alloc.values()) - incumbent_total) > TOL * max(1.0, incumbent_total):
        return {"allocation": None, "ok": False, "reason": "normalization does not preserve T"}
    return {"allocation": alloc, "ok": True, "reason": None, "raw_total": S,
            "budget_scale": scale, "cohort_total": incumbent_total}


def c3_allocation(lineup: list[dict], c2_alloc: dict, protected_symbol: str,
                  multiplier: float = RANK_ONE_MULTIPLIER) -> dict:
    """C1's reallocation applied to C2's normalized allocations, on the substituted lineup.

    Rank one remains the original protected name, which C2 never removes. The other seven are
    reduced proportionally so the total is still the incumbent T.
    """
    T = sum(c2_alloc.values())
    b1 = c2_alloc[protected_symbol]
    rest = T - b1
    if rest <= 0:
        return {"allocation": None, "ok": False, "reason": "no capital outside rank one"}
    target = multiplier * b1
    other_scale = (T - target) / rest
    if other_scale <= 0:
        return {"allocation": None, "ok": False, "reason": f"other_scale {other_scale:.6f} is not positive"}
    alloc = {protected_symbol: target}
    for h in lineup:
        s = h["symbol"]
        if s == protected_symbol:
            continue
        alloc[s] = c2_alloc[s] * other_scale
    if abs(sum(alloc.values()) - T) > TOL * max(1.0, T):
        return {"allocation": None, "ok": False, "reason": "combined reallocation does not preserve T"}
    return {"allocation": alloc, "ok": True, "reason": None, "cohort_total": T,
            "other_scale": other_scale, "rank_one_target": target}


def cohort_with_rows(cohort: dict, rows: list[dict], stage_rank: bool = True) -> dict:
    """A cohort record carrying a challenger lineup, with ranks renumbered 1..8 in place.

    The engine numbers slots by position, so the lineup is ordered with the protected original
    rank one first and the rest by original rank. The original rank of every name is preserved
    on the row as `original_rank` for the audit.
    """
    out = dict(cohort)
    ordered = sorted(rows, key=lambda h: h["rank"])
    out["rows"] = [{**h, "original_rank": h["rank"]} for h in ordered]
    return out


def floor_shares(notional: float, price: float) -> int:
    return math.floor(notional / price) if price and price > 0 else 0
