"""Arrow 012 Phase A — order-invariant within-cohort statistics and dependence diagnostics.

The Arrow 011 statistic `within_cohort_top_half_minus_bottom_half` sorted a cohort's rows by
feature and split them at the midpoint. When equal feature values straddle that midpoint the
split depends on the original row order, so a feature that is constant inside a cohort could
still report a nonzero within-cohort effect. This module replaces that statistic with two
order-invariant ones and keeps Spearman correlation on average ranks as the transparent
third view.

Invariants held by every statistic here, and asserted in tests/test_cg_arrow012.py:

  * permuting a cohort's rows cannot change any reported value;
  * a feature constant inside a cohort yields no within-cohort effect and is reported as
    unscorable, never as zero-with-support;
  * reversing the row order cannot reverse an effect;
  * ties are reported as lost support, never broken by position.

Nothing here reads or changes a frozen trade, quantity, price or account.
"""
from __future__ import annotations

from collections import defaultdict
import math
import random
import statistics

STATS_VERSION = "cg_arrow012_repaired_within_cohort_v1"
MIN_ROWS_PER_COHORT = 4


def num(x):
    if x in ("", None):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def average_ranks(values: list[float]) -> list[float]:
    """Ranks with ties averaged, so equal values share one rank and order never matters."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def spearman(x: list[float], y: list[float]) -> float | None:
    if len(x) < MIN_ROWS_PER_COHORT:
        return None
    rx, ry = average_ranks(x), average_ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / math.sqrt(sxx * syy)


# ----------------------------------------------------------------- A1, statistic 1
def strict_half_contrast(pairs: list[tuple[float, float]]) -> float | None:
    """Top-half minus bottom-half mean outcome, scored only when no tie crosses the median.

    pairs: (feature, outcome). With n rows the split is at k = n // 2 from each end. If the
    feature value at the last bottom-half position equals the value at the first top-half
    position, the boundary is ambiguous and the cohort is unscorable for this contrast: the
    function returns None rather than letting row order decide. Units are outcome units.
    """
    n = len(pairs)
    if n < MIN_ROWS_PER_COHORT:
        return None
    s = sorted(pairs, key=lambda p: p[0])
    k = n // 2
    if s[k - 1][0] == s[n - k][0]:
        return None
    lo = statistics.mean(p[1] for p in s[:k])
    hi = statistics.mean(p[1] for p in s[n - k:])
    return hi - lo


# ----------------------------------------------------------------- A1, statistic 2
def pairwise_directional_effect(pairs: list[tuple[float, float]]) -> tuple[float | None, int]:
    """Mean outcome difference oriented from the lower-feature to the higher-feature row.

    Over all unordered pairs (i, j) with distinct feature values, take the outcome of the
    higher-feature row minus the outcome of the lower-feature row, and average. Pairs with
    equal feature values are excluded, so ties contribute no arbitrary ordering. Units are
    outcome units per pair. Returns (effect, number of contributing pairs); the effect is
    None when no pair has distinct feature values, which is exactly the constant-feature case.
    """
    total, count = 0.0, 0
    n = len(pairs)
    for i in range(n):
        fi, yi = pairs[i]
        for j in range(i + 1, n):
            fj, yj = pairs[j]
            if fi == fj:
                continue
            total += (yj - yi) if fj > fi else (yi - yj)
            count += 1
    return ((total / count) if count else None), count


def relationship(rows: list[dict], feature: str, outcome: str) -> dict:
    """Repaired within-cohort, pooled and between-cohort views of one feature and one outcome.

    rows need 'cohort_id', 'symbol', the feature and the outcome. Missing values on either
    side exclude a row and are counted. Cohort-level constancy is detected and reported as
    lost support rather than as a zero effect.
    """
    ok = [r for r in rows if num(r.get(feature)) is not None and num(r.get(outcome)) is not None]
    missing = len(rows) - len(ok)
    base = {"stats_version": STATS_VERSION, "feature": feature, "outcome": outcome,
            "n": len(ok), "missing": missing}
    if len(ok) < 8:
        return {**base, "insufficient": True}
    by_c: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in ok:
        by_c[r["cohort_id"]].append((num(r[feature]), num(r[outcome])))

    rhos, halves, effects, pair_counts = [], [], [], []
    constant, tie_blocked, too_small = 0, 0, 0
    for pairs in by_c.values():
        if len(pairs) < MIN_ROWS_PER_COHORT:
            too_small += 1
            continue
        if len({p[0] for p in pairs}) == 1:
            constant += 1
            continue
        rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
        if rho is not None:
            rhos.append(rho)
        h = strict_half_contrast(pairs)
        if h is None:
            tie_blocked += 1
        else:
            halves.append(h)
        eff, npairs = pairwise_directional_effect(pairs)
        if eff is not None:
            effects.append(eff)
            pair_counts.append(npairs)

    x = [num(r[feature]) for r in ok]
    y = [num(r[outcome]) for r in ok]
    cm_x = [statistics.mean(p[0] for p in v) for v in by_c.values()]
    cm_y = [statistics.mean(p[1] for p in v) for v in by_c.values()]
    return {
        **base,
        "cohorts": len(by_c), "securities": len({r["symbol"] for r in ok}),
        "months": len({r["cohort_id"][:7] for r in ok}),
        "pooled_spearman": spearman(x, y),
        "within_cohort_mean_spearman": statistics.mean(rhos) if rhos else None,
        "within_cohort_spearman_cohorts": len(rhos),
        "within_cohort_spearman_positive_share": (sum(1 for r in rhos if r > 0) / len(rhos)) if rhos else None,
        "strict_half_contrast": statistics.mean(halves) if halves else None,
        "strict_half_cohorts_scored": len(halves),
        "strict_half_cohorts_tie_excluded": tie_blocked,
        "strict_half_positive_share": (sum(1 for h in halves if h > 0) / len(halves)) if halves else None,
        "pairwise_directional_effect": statistics.mean(effects) if effects else None,
        "pairwise_cohorts_scored": len(effects),
        "pairwise_total_pairs": sum(pair_counts),
        "pairwise_positive_share": (sum(1 for e in effects if e > 0) / len(effects)) if effects else None,
        "cohorts_constant_feature": constant, "cohorts_below_min_rows": too_small,
        "between_cohort_spearman": spearman(cm_x, cm_y) if len(cm_x) >= MIN_ROWS_PER_COHORT else None,
        "units": "outcome units; the pairwise effect is per distinct-feature pair",
    }


# ----------------------------------------------------------------- A3 dependence diagnostics
def _stat(rows, feature, outcome, which):
    rel = relationship(rows, feature, outcome)
    return rel.get(which)


def moving_block_resample(rows: list[dict], feature: str, outcome: str, *, block: int,
                          which: str = "pairwise_directional_effect", n_boot: int = 300,
                          seed: int = 12) -> dict:
    """Contiguous moving-block resampling over cohorts in signal order.

    block=1 preserves the eight names inside a cohort but no serial dependence between
    neighbouring cohorts. block=2 and block=4 keep runs of adjacent cohorts together, so a
    finding carried by one contiguous episode, or by overlapping ten-session holds that span
    neighbouring cohorts, shows up as a wider spread. This states what it preserves; it is
    not a significance test and does not decide anything.
    """
    rng = random.Random(seed)
    by_c: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_c[r["cohort_id"]].append(r)
    ids = sorted(by_c)
    n = len(ids)
    if n < block or n == 0:
        return {"block": block, "boot_n": 0, "preserves": "insufficient cohorts"}
    starts = list(range(n - block + 1))
    draws = max(1, round(n / block))
    vals = []
    for _ in range(n_boot):
        sub = []
        for d in range(draws):
            s = rng.choice(starts)
            for off in range(block):
                cid = ids[s + off]
                for r in by_c[cid]:
                    sub.append({**r, "cohort_id": f"{cid}#{d}"})
        v = _stat(sub, feature, outcome, which)
        if v is not None:
            vals.append(v)
    if not vals:
        return {"block": block, "boot_n": 0, "preserves": "no scorable resample"}
    s = sorted(vals)
    return {"block": block, "statistic": which, "boot_n": len(s),
            "p05": s[int(0.05 * len(s))], "p50": s[len(s) // 2],
            "p95": s[min(len(s) - 1, int(0.95 * len(s)))],
            "share_positive": sum(1 for v in s if v > 0) / len(s),
            "preserves": (f"contiguous runs of {block} cohort(s) in signal order, and every name "
                          "inside each cohort; it does not preserve security identity across blocks")}


def repeated_security_sensitivity(rows: list[dict], feature: str, outcome: str,
                                  which: str = "pairwise_directional_effect") -> dict:
    """How much of a relationship survives when repeated securities are limited.

    Three views: all rows; first selection of each security only; and one row per security
    chosen deterministically as its earliest cohort. Overlapping episodes, where a security's
    previous ten-session hold was still open at the new signal, are reported separately.
    """
    full = _stat(rows, feature, outcome, which)
    first_only = [r for r in rows if r.get("ep_episode") == "FIRST"]
    overlapping = [r for r in rows if r.get("ep_episode") == "OVERLAPPING_REPEAT"]
    seen, unique = set(), []
    for r in sorted(rows, key=lambda r: (r["cohort_id"], r["symbol"])):
        if r["symbol"] in seen:
            continue
        seen.add(r["symbol"])
        unique.append(r)
    return {"statistic": which, "all_rows": full, "all_n": len(rows),
            "first_episode_only": _stat(first_only, feature, outcome, which), "first_n": len(first_only),
            "overlapping_repeats_only": _stat(overlapping, feature, outcome, which), "overlapping_n": len(overlapping),
            "one_row_per_security": _stat(unique, feature, outcome, which), "unique_securities": len(unique),
            "note": ("one row per security keeps each security's earliest cohort, which breaks most "
                     "cohorts below the four-row minimum, so its value is a coarse check only")}
