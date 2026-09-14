"""Arrow 011 — interpretable comparison statistics for the anatomy study.

Everything here is a small, transparent calculation: rank correlations, tercile contrasts,
within-cohort concordance, cohort-equal-weight means, leave-one-out ranges and cohort-block
resampling. No fitted model, no coefficient mining. Cohorts and securities are never treated
as independent replications; the diagnostics report support counts alongside every effect.
"""
from __future__ import annotations

from collections import defaultdict
import math
import random
import statistics


def num(x):
    if x in ("", None):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def ranks(values: list[float]) -> list[float]:
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
    if len(x) < 4:
        return None
    rx, ry = ranks(x), ranks(y)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / math.sqrt(sxx * syy)


def tercile_cuts(values: list[float]) -> tuple[float, float]:
    s = sorted(values)
    n = len(s)
    return s[n // 3], s[(2 * n) // 3]


def tercile_of(v: float, cuts: tuple[float, float]) -> str:
    return "T1_low" if v < cuts[0] else ("T3_high" if v >= cuts[1] else "T2_mid")


def summarize_group(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0, "mean": None, "median": None, "hit_rate": None}
    return {"n": len(vals), "mean": statistics.mean(vals), "median": statistics.median(vals),
            "hit_rate": sum(1 for v in vals if v > 0) / len(vals)}


def relationship(rows: list[dict], feature: str, outcome: str, cuts: tuple[float, float] | None = None) -> dict:
    """Pooled, within-cohort and between-cohort views of one feature against one outcome.

    rows need 'cohort_id', 'symbol', feature, outcome. Rows with either value missing are
    excluded and counted. Tercile cuts may be supplied (frozen) or learned from these rows.
    """
    ok = [r for r in rows if num(r.get(feature)) is not None and num(r.get(outcome)) is not None]
    missing = len(rows) - len(ok)
    if len(ok) < 8:
        return {"feature": feature, "outcome": outcome, "n": len(ok), "missing": missing, "insufficient": True}
    x = [num(r[feature]) for r in ok]
    y = [num(r[outcome]) for r in ok]
    cuts = cuts or tercile_cuts(x)
    groups = defaultdict(list)
    for xi, yi in zip(x, y):
        groups[tercile_of(xi, cuts)].append(yi)
    t1, t3 = summarize_group(groups["T1_low"]), summarize_group(groups["T3_high"])
    # within-cohort: demean both inside each cohort, then concordance per cohort
    by_c = defaultdict(list)
    for r, xi, yi in zip(ok, x, y):
        by_c[r["cohort_id"]].append((xi, yi))
    per_cohort_rho, halves = [], []
    for cid, pairs in by_c.items():
        if len(pairs) < 4:
            continue
        rho = spearman([p[0] for p in pairs], [p[1] for p in pairs])
        if rho is not None:
            per_cohort_rho.append(rho)
        srt = sorted(pairs, key=lambda p: p[0])
        k = len(srt) // 2
        lo = statistics.mean(p[1] for p in srt[:k])
        hi = statistics.mean(p[1] for p in srt[-k:])
        halves.append(hi - lo)
    # between-cohort: cohort means
    cm_x = [statistics.mean(p[0] for p in pairs) for pairs in by_c.values()]
    cm_y = [statistics.mean(p[1] for p in pairs) for pairs in by_c.values()]
    # cohort-equal-weight tercile contrast: average within-cohort difference of feature terciles
    return {
        "feature": feature, "outcome": outcome, "n": len(ok), "missing": missing,
        "cohorts": len(by_c), "securities": len({r["symbol"] for r in ok}),
        "months": len({r["cohort_id"][:7] for r in ok}),
        "pooled_spearman": spearman(x, y),
        "tercile_cuts": list(cuts),
        "t1_low": t1, "t3_high": t3, "t3_minus_t1_mean": (t3["mean"] - t1["mean"]) if t1["n"] and t3["n"] else None,
        "t3_minus_t1_hit": (t3["hit_rate"] - t1["hit_rate"]) if t1["n"] and t3["n"] else None,
        "within_cohort_mean_spearman": statistics.mean(per_cohort_rho) if per_cohort_rho else None,
        "within_cohort_positive_share": (sum(1 for r in per_cohort_rho if r > 0) / len(per_cohort_rho)) if per_cohort_rho else None,
        "within_cohort_cohorts": len(per_cohort_rho),
        "within_cohort_top_half_minus_bottom_half": statistics.mean(halves) if halves else None,
        "within_cohort_halves_positive_share": (sum(1 for h in halves if h > 0) / len(halves)) if halves else None,
        "between_cohort_spearman": spearman(cm_x, cm_y) if len(cm_x) >= 4 else None,
    }


def leave_one_out(rows: list[dict], feature: str, outcome: str, key: str, cuts) -> dict:
    """Range of the within-cohort half-contrast when each cohort (or security) is left out."""
    keys = sorted({r[key] for r in rows})
    vals = []
    for k in keys:
        sub = [r for r in rows if r[key] != k]
        rel = relationship(sub, feature, outcome, cuts)
        v = rel.get("within_cohort_top_half_minus_bottom_half")
        if v is not None:
            vals.append(v)
    if not vals:
        return {"loo_key": key, "n_left_out": 0}
    return {"loo_key": key, "n_left_out": len(vals), "loo_min": min(vals), "loo_max": max(vals),
            "loo_all_same_sign": all(v > 0 for v in vals) or all(v < 0 for v in vals)}


def cohort_block_bootstrap(rows: list[dict], feature: str, outcome: str, cuts, n_boot: int = 300, seed: int = 11) -> dict:
    """Resample whole cohorts with replacement; a dependence-aware spread, not a proof."""
    rng = random.Random(seed)
    by_c = defaultdict(list)
    for r in rows:
        by_c[r["cohort_id"]].append(r)
    ids = sorted(by_c)
    stats = []
    for _ in range(n_boot):
        pick = [rng.choice(ids) for _ in ids]
        sub = []
        for n, cid in enumerate(pick):
            for r in by_c[cid]:
                sub.append({**r, "cohort_id": f"{cid}#{n}"})
        rel = relationship(sub, feature, outcome, cuts)
        v = rel.get("within_cohort_top_half_minus_bottom_half")
        if v is not None:
            stats.append(v)
    if not stats:
        return {"boot_n": 0}
    s = sorted(stats)
    return {"boot_n": len(s), "boot_p05": s[int(0.05 * len(s))], "boot_p50": s[len(s) // 2],
            "boot_p95": s[min(len(s) - 1, int(0.95 * len(s)))],
            "boot_share_positive": sum(1 for v in s if v > 0) / len(s)}


def group_table(rows: list[dict], group: str, outcome: str, weight: str | None = None) -> list[dict]:
    """Per-group outcome summary with cohort-equal-weight mean and support counts."""
    by = defaultdict(list)
    for r in rows:
        if num(r.get(outcome)) is None:
            continue
        by[r.get(group) or "MISSING"].append(r)
    out = []
    for g, rs in sorted(by.items()):
        vals = [num(r[outcome]) for r in rs]
        cm = defaultdict(list)
        for r in rs:
            cm[r["cohort_id"]].append(num(r[outcome]))
        cew = statistics.mean(statistics.mean(v) for v in cm.values())
        row = {"group": g, "n": len(rs), "cohorts": len(cm), "securities": len({r["symbol"] for r in rs}),
               "months": len({r["cohort_id"][:7] for r in rs}),
               "mean": statistics.mean(vals), "median": statistics.median(vals),
               "hit_rate": sum(1 for v in vals if v > 0) / len(vals),
               "cohort_equal_weight_mean": cew,
               "p25": sorted(vals)[len(vals) // 4], "p75": sorted(vals)[(3 * len(vals)) // 4]}
        if weight:
            w = [num(r.get(weight)) for r in rs]
            row["sum_" + weight] = sum(v for v in w if v is not None)
        out.append(row)
    return out


def cohort_centered(rows: list[dict], outcome: str) -> dict:
    """outcome minus its cohort mean, per ticket id."""
    by = defaultdict(list)
    for r in rows:
        v = num(r.get(outcome))
        if v is not None:
            by[r["cohort_id"]].append(v)
    means = {c: statistics.mean(v) for c, v in by.items()}
    return {r["ticket_id"]: num(r[outcome]) - means[r["cohort_id"]]
            for r in rows if num(r.get(outcome)) is not None}
