"""CG Arrow 011 — stage 2: IS-only discovery on the private atlas.

Reads the trade atlas, restricts every feature/outcome relationship to IS-owned cohorts
(signal months 2025-09, 2025-11, 2026-01, 2026-03, 2026-05, 2026-07), and writes the IS
results and the hypothesis registry. Predictions are recorded before scoring. Nothing here
reads an OOS outcome against a feature.

Usage: python scripts/cg_arrow011_analyze.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT  # noqa: E402
from verification import r4r5_anatomy_stats as st  # noqa: E402
from verification.r4r5_data import VERIFY_ROOT, dump_json, stamp  # noqa: E402

ATLAS = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011" / "trade_atlas.csv"
PATHS = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011" / "trade_path_atlas.csv"
CACHE = VERIFY_ROOT / "a11"
PRIMARY = "oc_price_return_10"
SECOND = "oc_net_per_entry_dollar"
DOLLAR = "lens_fixed_causal_net"
SCALED = "lens_equity_scaled_net"

SC_FEATURES = [
    "sc_ret1", "sc_ret3", "sc_ret5", "sc_ret10", "sc_ret15", "sc_ret15_to_5", "sc_recent_minus_earlier",
    "sc_acceleration_3", "sc_largest_session_share_of_advance", "sc_top3_sessions_share_of_advance",
    "sc_up_sessions_15", "sc_logret_std_15", "sc_gap_share_of_advance", "sc_close_vs_high20",
    "sc_close_vs_max_close15", "sc_sessions_since_max_close15", "sc_position_in_range20",
    "sc_close_location_signal_day", "sc_signal_day_range_pct", "sc_mean_range_pct_10",
    "sc_volume_ratio_frozen", "sc_volume_trend_5_vs_15", "sc_dollar_volume_signal_day",
    "sc_dollar_volume_mean20", "sc_dollar_volume_cv20", "sc_volume_expansion_15", "sc_move_per_volume_unit",
    "sc_signal_close", "cx_rank_in_eight", "cx_ret15_minus_cohort_median", "cx_gap_to_next_rank",
    "cx_cohort_ret15_spread", "cx_ret15_field_percentile", "ep_prior_selections",
    "ep_sessions_since_last_selection",
]
PO_FEATURES = [
    "po_overnight_gap_vs_signal_close", "po_signal_close_to_preorder", "po_open_to_preorder",
    "po_preorder_location_in_partial_range", "po_partial_range_pct",
    "po_partial_volume_vs_elapsed_window_mean", "po_preorder_price",
]
GROUPS = ["sc_four_state", "sc_signal_close_band", "po_preorder_price_band", "ep_episode", "cx_rank_in_eight",
          "sc_documented_action_within_60_sessions"]

# Declared before any result is computed. A pattern is "leading" only when the within-cohort
# view and the pooled view agree in sign, the within-cohort half-contrast favours one side in
# at least 62% of cohorts, and the mean within-cohort rank correlation is at least 0.12 in size.
LEADING_RULE = {"within_halves_share_min": 0.62, "within_spearman_abs_min": 0.12,
                "sign_agreement_required": True, "min_cohorts": 15}

# Hypotheses registered with predicted direction BEFORE scoring. Direction is the expected
# sign of (feature high minus feature low) on the ten-session short price return, where a
# positive return means the short worked.
HYPOTHESES = [
    # ---- directed D2
    {"id": "D2-1", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_four_state",
     "question": "Do the two HALF states behave alike on sizing-neutral return?",
     "test": "group table S2 vs S3, cohort-equal-weight mean and hit rate",
     "prediction": "S2 (weak, loud) and S3 (strong, quiet) differ; no direction claimed"},
    {"id": "D2-2", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_ret3",
     "question": "Is the engine shorting already-weakening winners (ret3 <= 0) more successfully than still-accelerating ones?",
     "test": "S1+S2 vs S3+S4 sizing-neutral return; continuous ret3 relationship",
     "prediction": "positive ret3 fades LESS (continuation risk): high-ret3 minus low-ret3 return negative"},
    {"id": "D2-3", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_volume_ratio_frozen",
     "question": "Does weakening on elevated volume behave differently from weakening on quiet volume?",
     "test": "S2 vs S1 within ret3 <= 0; continuous volume ratio relationship",
     "prediction": "elevated signal-day volume fades LESS (attention/participation): high minus low negative"},
    # ---- directed D3 families
    {"id": "D3-1", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_largest_session_share_of_advance",
     "question": "Episodic run-up (one session carries the advance) versus gradual ascent",
     "test": "tercile contrast and within-cohort concordance", "prediction": "episodic advances fade LESS: high minus low negative"},
    {"id": "D3-2", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_gap_share_of_advance",
     "question": "Gap-driven versus continuous-session advance", "test": "tercile contrast and within-cohort concordance",
     "prediction": "gap-driven advances fade LESS: high minus low negative"},
    {"id": "D3-3", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_close_vs_max_close15",
     "question": "Drawdown already underway at the signal versus closing at the run-up high",
     "test": "tercile contrast and within-cohort concordance",
     "prediction": "names already off their high fade LESS further: high (near high) minus low positive"},
    {"id": "D3-4", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_recent_minus_earlier",
     "question": "Late acceleration versus early front-loaded run-up", "test": "tercile contrast and within-cohort concordance",
     "prediction": "late-accelerating names fade MORE: high minus low positive"},
    {"id": "D3-5", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_dollar_volume_mean20",
     "question": "Liquidity: does dollar volume relate to the fade?", "test": "tercile contrast and within-cohort concordance",
     "prediction": "less liquid names fade MORE: high minus low negative"},
    {"id": "D3-6", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_signal_close_band",
     "question": "Price band association", "test": "group table by band", "prediction": "no direction claimed"},
    {"id": "D3-7", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "cx_rank_in_eight",
     "question": "Rank within the eight and relative extremeness", "test": "group table by rank; cx_ret15_minus_cohort_median",
     "prediction": "the most extreme (rank 1-2) fade MORE: rank-return relationship positive on extremeness"},
    {"id": "D3-8", "lane": "directed", "parent": None, "cutoff": "PRE_ORDER", "feature": "po_signal_close_to_preorder",
     "question": "Does entry-session continuation up to the pre-order bar add information beyond the signal close?",
     "test": "within-cohort concordance of the pre-order move; compared with sc_ret1 on the same rows",
     "prediction": "further rise into the order fades MORE: high minus low positive"},
    {"id": "D3-9", "lane": "directed", "parent": None, "cutoff": "PRE_ORDER", "feature": "po_partial_volume_vs_elapsed_window_mean",
     "question": "Entry-session volume through the pre-order bar versus the same elapsed window on prior sessions",
     "test": "tercile contrast and within-cohort concordance", "prediction": "elevated entry-session participation fades LESS: negative"},
    {"id": "D3-10", "lane": "directed", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_documented_action_within_60_sessions",
     "question": "Known documented corporate action before the signal as context",
     "test": "group table 0 vs >=1 actions", "prediction": "no direction claimed; sparse"},
    # ---- freelance
    {"id": "F1", "lane": "freelance", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "ep_episode",
     "question": "Overlapping repeat selection (previous hold still open) versus first selection",
     "why_distinct": "directed work covers run-up shape and volume; episode age is a membership-history feature",
     "test": "group table FIRST vs OVERLAPPING_REPEAT vs LATER_REPEAT; cohort-equal-weight",
     "prediction": "overlapping repeats fade LESS than first selections (the first fade was already captured or the move is persistent)",
     "information_value": "35% of selections are overlapping repeats; a difference would reshape how the weekly basket is read"},
    {"id": "F2", "lane": "freelance", "parent": None, "cutoff": "SIGNAL_CLOSE", "feature": "sc_up_sessions_15",
     "question": "Steady ascent (many up sessions) versus a few large jumps, holding the total advance similar",
     "why_distinct": "D3-1 measures concentration by magnitude; this measures persistence by count",
     "test": "tercile contrast and within-cohort concordance", "prediction": "steady grinders fade MORE: high minus low positive",
     "information_value": "separates squeeze-like persistence from news jumps without a catalyst narrative"},
    {"id": "F3", "lane": "freelance", "parent": "D3-8", "cutoff": "PRE_ORDER", "feature": "po_preorder_location_in_partial_range",
     "question": "Failed continuation inside the entry session: is the pre-order price near the partial-day low?",
     "why_distinct": "D3-8 is the level of the entry-day move; this is where the price sits inside the entry-day range",
     "test": "tercile contrast and within-cohort concordance", "prediction": "closing near the partial-day low fades MORE: high minus low negative",
     "information_value": "an intraday failure signature would be actionable at the same order time"},
    {"id": "F4", "lane": "freelance", "parent": "D2-1", "cutoff": "SIGNAL_CLOSE", "feature": "sc_four_state",
     "question": "Within the QUARTER state (strong and loud), does the volume ratio still separate outcomes?",
     "why_distinct": "tests whether the volume reduction is informative inside the state where it already applies",
     "test": "S4 rows only: tercile contrast of sc_volume_ratio_frozen", "prediction": "no additional separation inside S4",
     "information_value": "tells whether the two reductions are redundant or additive"},
]


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def is_rows(rows):
    return [r for r in rows if r["split"] == "IS"]


def path_summary(rows: list[dict], prows: list[dict]) -> dict:
    ids = {r["ticket_id"] for r in rows}
    sub = [p for p in prows if p["ticket_id"] in ids]
    by_age = {}
    for a in range(0, 11):
        vals = [st.num(p[f"age{a:02d}_short_return"]) for p in sub]
        obs = [v for v in vals if v is not None]
        s = sorted(obs)
        by_age[a] = {"observed": len(obs), "stale_or_absent": len(vals) - len(obs),
                     "mean": statistics.mean(obs) if obs else None, "median": statistics.median(obs) if obs else None,
                     "p10": s[int(0.1 * len(s))] if s else None, "p25": s[len(s) // 4] if s else None,
                     "p75": s[(3 * len(s)) // 4] if s else None, "p90": s[min(len(s) - 1, int(0.9 * len(s)))] if s else None,
                     "favorable_share": (sum(1 for v in obs if v > 0) / len(obs)) if obs else None}
    incr = {}
    for a in range(1, 11):
        pairs = [(st.num(p[f"age{a-1:02d}_short_return"]), st.num(p[f"age{a:02d}_short_return"])) for p in sub]
        d = [b - a0 for a0, b in pairs if a0 is not None and b is not None]
        incr[f"{a-1}->{a}"] = {"n": len(d), "mean": statistics.mean(d) if d else None,
                               "median": statistics.median(d) if d else None,
                               "positive_share": (sum(1 for v in d if v > 0) / len(d)) if d else None}
    ratios = {}
    for a in (3, 5, 7):
        pairs = [(st.num(p[f"age{a:02d}_short_return"]), st.num(p["age10_short_return"])) for p in sub]
        pos = [x / y for x, y in pairs if x is not None and y is not None and y > 0.005]
        ratios[f"age{a}_over_age10"] = {"rows_with_positive_denominator": len(pos), "rows_total": len(pairs),
                                        "median_ratio": statistics.median(pos) if pos else None,
                                        "basis": "only rows whose ten-session return exceeds 0.5%; not generalizable to the book"}
        agg_a = sum(x for x, y in pairs if x is not None and y is not None)
        agg_10 = sum(y for x, y in pairs if x is not None and y is not None)
        ratios[f"aggregate_age{a}_over_age10"] = (agg_a / agg_10) if agg_10 > 0 else None
    arch = Counter(p["path_archetype"] for p in sub)
    mfe = [st.num(r["path_mfe_close_only"]) for r in rows if st.num(r.get("path_mfe_close_only")) is not None]
    mae = [st.num(r["path_mae_close_only"]) for r in rows if st.num(r.get("path_mae_close_only")) is not None]
    ffa = [st.num(r["path_first_favorable_age"]) for r in rows if st.num(r.get("path_first_favorable_age")) is not None]
    return {"n": len(sub), "by_age": by_age, "incremental": incr, "partial_vs_ten": ratios,
            "archetypes": dict(arch),
            "mfe_close_only": {"n": len(mfe), "mean": statistics.mean(mfe) if mfe else None, "median": statistics.median(mfe) if mfe else None},
            "mae_close_only": {"n": len(mae), "mean": statistics.mean(mae) if mae else None, "median": statistics.median(mae) if mae else None},
            "first_favorable_age": {"n": len(ffa), "never_favorable": len(rows) - len(ffa),
                                    "median": statistics.median(ffa) if ffa else None, "dist": dict(Counter(int(x) for x in ffa))},
            "excursion_basis": "close-only marks at each age; not true intraday extrema"}


def cohort_outcome_census(rows: list[dict]) -> dict:
    by = defaultdict(list)
    for r in rows:
        by[r["cohort_id"]].append(r)
    kinds = Counter()
    for cid, rs in by.items():
        vals = [st.num(r[PRIMARY]) for r in rs]
        if any(v is None for v in vals):
            kinds["PARTLY_CENSORED"] += 1
        elif all(v > 0 for v in vals):
            kinds["ALL_WIN"] += 1
        elif all(v <= 0 for v in vals):
            kinds["ALL_LOSS"] += 1
        else:
            kinds["MIXED"] += 1
    return dict(kinds)


def is_leading(rel: dict) -> bool:
    if rel.get("insufficient") or rel.get("within_cohort_cohorts", 0) < LEADING_RULE["min_cohorts"]:
        return False
    share = rel.get("within_cohort_halves_positive_share")
    rho = rel.get("within_cohort_mean_spearman")
    pooled = rel.get("pooled_spearman")
    if share is None or rho is None or pooled is None:
        return False
    one_sided = share >= LEADING_RULE["within_halves_share_min"] or share <= 1 - LEADING_RULE["within_halves_share_min"]
    return one_sided and abs(rho) >= LEADING_RULE["within_spearman_abs_min"] and (rho > 0) == (pooled > 0)


def main() -> int:
    t0 = time.monotonic()
    rows = load(ATLAS)
    prows = load(PATHS)
    isr = is_rows(rows)
    print(f"{stamp()} atlas={len(rows)} IS={len(isr)}", flush=True)
    out = {"stage": "is_discovery", "timestamp": stamp(), "is_rows": len(isr), "is_cohorts": len({r['cohort_id'] for r in isr}),
           "leading_rule": LEADING_RULE, "primary_outcome": PRIMARY, "secondary_outcome": SECOND}

    # ---- D2 groups (sizing-neutral first, then dollars)
    out["groups"] = {}
    for g in GROUPS:
        out["groups"][g] = {PRIMARY: st.group_table(isr, g, PRIMARY, weight=DOLLAR),
                            SECOND: st.group_table(isr, g, SECOND),
                            DOLLAR: st.group_table(isr, g, DOLLAR), SCALED: st.group_table(isr, g, SCALED)}
    # exposure by state so a strong FULL bucket is not explained only by bigger tickets
    expo = defaultdict(float)
    for r in isr:
        v = st.num(r.get("oc_entry_exposure_dollars"))
        if v:
            expo[r["sc_four_state"]] += v
    out["groups"]["sc_four_state"]["entry_exposure_dollars"] = dict(expo)
    # F4: inside S4 only
    s4 = [r for r in isr if r["sc_four_state"] == "S4_QUARTER_strong_loud"]
    out["f4_inside_s4"] = {"volume_ratio": st.relationship(s4, "sc_volume_ratio_frozen", PRIMARY),
                           "ret3": st.relationship(s4, "sc_ret3", PRIMARY)}
    # D2-3: inside ret3 <= 0 only
    weak = [r for r in isr if st.num(r.get("sc_ret3")) is not None and st.num(r["sc_ret3"]) <= 0]
    out["d2_3_inside_weak"] = {"volume_ratio": st.relationship(weak, "sc_volume_ratio_frozen", PRIMARY),
                               "groups": st.group_table(weak, "sc_four_state", PRIMARY)}

    # ---- D3 continuous screen, pooled + within + between
    out["relationships"] = {}
    cuts = {}
    for f in SC_FEATURES + PO_FEATURES:
        rel = st.relationship(isr, f, PRIMARY)
        rel2 = st.relationship(isr, f, SECOND, tuple(rel["tercile_cuts"]) if not rel.get("insufficient") else None)
        rel["leading"] = is_leading(rel)
        out["relationships"][f] = {PRIMARY: rel, SECOND: rel2}
        if not rel.get("insufficient"):
            cuts[f] = rel["tercile_cuts"]
    out["tercile_cuts_learned_on_is"] = cuts
    leading = [f for f in SC_FEATURES + PO_FEATURES if out["relationships"][f][PRIMARY].get("leading")]
    out["leading_features"] = leading
    print(f"{stamp()} leading features on IS: {leading}", flush=True)

    # PRE_ORDER increment against SIGNAL_CLOSE on the same rows
    common = [r for r in isr if st.num(r.get("po_signal_close_to_preorder")) is not None and st.num(r.get("sc_ret1")) is not None]
    out["pre_order_increment"] = {"rows": len(common),
                                  "po_signal_close_to_preorder": st.relationship(common, "po_signal_close_to_preorder", PRIMARY),
                                  "sc_ret1_same_rows": st.relationship(common, "sc_ret1", PRIMARY),
                                  "po_overnight_gap": st.relationship(common, "po_overnight_gap_vs_signal_close", PRIMARY),
                                  "po_open_to_preorder": st.relationship(common, "po_open_to_preorder", PRIMARY)}

    # ---- D4 cohort census and cohort-centered views
    out["cohort_census"] = cohort_outcome_census(isr)
    out["cohort_count"] = len({r["cohort_id"] for r in isr})
    centered = st.cohort_centered(isr, PRIMARY)
    for r in isr:
        r["_centered"] = centered.get(r["ticket_id"])
    out["centered_groups"] = {g: st.group_table(isr, g, "_centered") for g in ("sc_four_state", "ep_episode", "cx_rank_in_eight")}

    # ---- D6 stability for leading features and registered hypotheses' features
    check = sorted(set(leading) | {h["feature"] for h in HYPOTHESES if h["feature"] in cuts})
    out["stability"] = {}
    for f in check:
        c = tuple(cuts[f])
        by_month = {}
        for m in sorted({r["cohort_id"][:7] for r in isr}):
            sub = [r for r in isr if r["cohort_id"][:7] == m]
            rel = st.relationship(sub, f, PRIMARY, c)
            by_month[m] = {"n": rel.get("n"), "within_halves": rel.get("within_cohort_top_half_minus_bottom_half"),
                           "t3_minus_t1": rel.get("t3_minus_t1_mean")}
        first = [r for r in isr if r["ep_episode"] == "FIRST"]
        rep = [r for r in isr if r["ep_episode"] != "FIRST"]
        out["stability"][f] = {
            "loo_cohort": st.leave_one_out(isr, f, PRIMARY, "cohort_id", c),
            "loo_security": st.leave_one_out(isr, f, PRIMARY, "symbol", c),
            "cohort_block_bootstrap": st.cohort_block_bootstrap(isr, f, PRIMARY, c),
            "by_month": by_month,
            "first_episodes": {k: v for k, v in st.relationship(first, f, PRIMARY, c).items()
                               if k in ("n", "cohorts", "within_cohort_top_half_minus_bottom_half", "t3_minus_t1_mean", "pooled_spearman")},
            "repeat_episodes": {k: v for k, v in st.relationship(rep, f, PRIMARY, c).items()
                                if k in ("n", "cohorts", "within_cohort_top_half_minus_bottom_half", "t3_minus_t1_mean", "pooled_spearman")},
        }

    # ---- D5 paths on IS, plus conditioned on four-state and on leading feature terciles
    out["paths"] = {"all_is": path_summary(isr, prows)}
    for state in sorted({r["sc_four_state"] for r in isr}):
        out["paths"][f"state={state}"] = path_summary([r for r in isr if r["sc_four_state"] == state], prows)
    for f in leading[:4]:
        c = tuple(cuts[f])
        for tname in ("T1_low", "T3_high"):
            sub = [r for r in isr if st.num(r.get(f)) is not None and st.tercile_of(st.num(r[f]), c) == tname]
            out["paths"][f"{f}={tname}"] = path_summary(sub, prows)

    # ---- registry with IS results attached
    registry = []
    for h in HYPOTHESES:
        entry = dict(h)
        f = h["feature"]
        if f in out["relationships"]:
            rel = out["relationships"][f][PRIMARY]
            entry["is_result"] = {k: rel.get(k) for k in ("n", "cohorts", "securities", "pooled_spearman", "t3_minus_t1_mean",
                                                          "t3_minus_t1_hit", "within_cohort_mean_spearman",
                                                          "within_cohort_halves_positive_share",
                                                          "within_cohort_top_half_minus_bottom_half", "between_cohort_spearman")}
            entry["is_leading"] = rel.get("leading")
        elif f in GROUPS:
            entry["is_result"] = out["groups"][f][PRIMARY]
        if h["id"] == "F4":
            entry["is_result"] = out["f4_inside_s4"]
        if h["id"] == "D2-3":
            entry["is_result_inside_weak"] = out["d2_3_inside_weak"]
        registry.append(entry)
    out["registry"] = registry
    out["elapsed_minutes"] = (time.monotonic() - t0) / 60
    dump_json(CACHE / "is_results.json", out)
    print(f"{stamp()} IS discovery written; {out['elapsed_minutes']:.1f} min", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
