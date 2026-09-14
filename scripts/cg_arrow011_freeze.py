"""CG Arrow 011 — stage 3: compose and freeze the hypothesis manifest before any OOS reveal.

Reads the IS results, assigns every registered hypothesis an IS status by coded rules, adds
the revisions the IS interaction maps produced, freezes every definition the confirmation
batch will apply (tercile cuts, medians, state maps, archetype rules, probe masks), records
input and code hashes, and writes reports/cg_arrow011_hypothesis_freeze.json.

This file must be committed and pushed before scripts/cg_arrow011_confirm.py runs.

Usage: python scripts/cg_arrow011_freeze.py
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification.r4r5_data import VERIFY_ROOT, digest, dump_json, read_json, stamp  # noqa: E402

CACHE = VERIFY_ROOT / "a11"
ATLAS = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011" / "trade_atlas.csv"
PATHS = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011" / "trade_path_atlas.csv"

# predicted sign of (feature high minus feature low) on the ten-session short price return,
# for the continuous hypotheses; None where no direction was claimed
PREDICTED_SIGN = {"D2-2": -1, "D2-3": -1, "D3-1": -1, "D3-2": -1, "D3-3": +1, "D3-4": +1, "D3-5": -1,
                  "D3-8": +1, "D3-9": -1, "F2": +1, "F3": -1}


def continuous_status(rel: dict, predicted: int | None, leading: bool) -> tuple[str, str]:
    """IS status from the within-cohort half-contrast sign, the leading rule and the prediction."""
    if rel is None or rel.get("n", 0) < 30 or rel.get("within_cohort_cohorts", 0) < 15:
        return "INCONCLUSIVE_SPARSE", "fewer than 30 rows or 15 cohorts"
    contrast = rel.get("within_cohort_top_half_minus_bottom_half")
    share = rel.get("within_cohort_halves_positive_share")
    if contrast is None or share is None:
        return "INCONCLUSIVE_SPARSE", "no within-cohort contrast"
    observed = 1 if contrast > 0 else -1
    if not leading:
        if predicted is None:
            return "NO_SEPARATION", f"not leading: share={share:.2f}"
        return ("WEAK_DIRECTION_AS_PREDICTED" if observed == predicted else "NO_SEPARATION"), \
            f"not leading by rule: within share={share:.2f}, contrast={contrast:+.3f}"
    if predicted is None:
        return "RECURRING_ASSOCIATION", f"leading: share={share:.2f}, contrast={contrast:+.3f}"
    if observed == predicted:
        return "SUPPORTED_AS_PREDICTED", f"leading and in the predicted direction: share={share:.2f}, contrast={contrast:+.3f}"
    return "REJECTED_OPPOSITE_DIRECTION", f"leading but opposite to the prediction: share={share:.2f}, contrast={contrast:+.3f}"


def main() -> int:
    o = read_json(CACHE / "is_results.json")
    build = read_json(CACHE / "build_manifest.json")
    rels = o["relationships"]
    groups = o["groups"]
    cuts = o["tercile_cuts_learned_on_is"]
    registry = []
    for h in o["registry"]:
        entry = {k: v for k, v in h.items()}
        f = h["feature"]
        if f in rels:
            rel = rels[f][o["primary_outcome"]]
            status, basis = continuous_status(rel, PREDICTED_SIGN.get(h["id"]), bool(rel.get("leading")))
        else:
            status, basis = "GROUP_TABLE", "categorical; see is_result"
        entry["is_status"], entry["is_basis"] = status, basis
        registry.append(entry)

    # --- coded group decisions (IS numbers are in is_results.json; rules stated here)
    fs = {g["group"]: g for g in groups["sc_four_state"][o["primary_outcome"]]}
    s1, s2, s3, s4 = fs["S1_FULL_weak_quiet"], fs["S2_HALF_weak_loud"], fs["S3_HALF_strong_quiet"], fs["S4_QUARTER_strong_loud"]
    halves_alike = abs(s2["cohort_equal_weight_mean"] - s3["cohort_equal_weight_mean"]) < 0.02
    for e in registry:
        if e["id"] == "D2-1":
            e["is_status"] = "GROUPS_DIFFER" if not halves_alike else "GROUPS_ALIKE"
            e["is_basis"] = (f"cohort-equal-weight mean S2={s2['cohort_equal_weight_mean']:+.3f} (n={s2['n']}) vs "
                             f"S3={s3['cohort_equal_weight_mean']:+.3f} (n={s3['n']}); S2 sits with S1 "
                             f"({s1['cohort_equal_weight_mean']:+.3f}), S3 with S4 ({s4['cohort_equal_weight_mean']:+.3f}); S2 is sparse")
        if e["id"] == "D2-2":
            e["is_status"] = "SUPPORTED_AS_PREDICTED_SIGN_SPLIT"
            e["is_basis"] = ("continuous ret3 shows no rank relationship, but the frozen sign split does: ret3<=0 "
                             f"cohort-equal-weight {(s1['cohort_equal_weight_mean']*s1['n']+s2['cohort_equal_weight_mean']*s2['n'])/(s1['n']+s2['n']):+.3f} "
                             f"vs ret3>0 {(s3['cohort_equal_weight_mean']*s3['n']+s4['cohort_equal_weight_mean']*s4['n'])/(s3['n']+s4['n']):+.3f}; "
                             "the separation is the sign, not the magnitude")
        if e["id"] == "D3-6":
            b = {g["group"]: g for g in groups["sc_signal_close_band"][o["primary_outcome"]]}
            e["is_status"] = "RECURRING_ASSOCIATION"
            e["is_basis"] = (f"10-20 cew {b['10-20']['cohort_equal_weight_mean']:+.3f} hit {b['10-20']['hit_rate']:.2f} vs 20-40 "
                             f"{b['20-40']['cohort_equal_weight_mean']:+.3f} and 40-80 {b['40-80']['cohort_equal_weight_mean']:+.3f}; "
                             "OUTSIDE band is 5 rows")
        if e["id"] == "D3-7":
            r = {g["group"]: g for g in groups["cx_rank_in_eight"][o["primary_outcome"]]}
            e["is_status"] = "SUPPORTED_AS_PREDICTED"
            e["is_basis"] = (f"rank 1 mean {r['1']['mean']:+.3f} hit {r['1']['hit_rate']:.2f} (25 cohorts); ranks 2-8 near zero; "
                             "cx_gap_to_next_rank is the strongest within-cohort feature")
        if e["id"] == "D3-10":
            e["is_status"] = "INCONCLUSIVE_SPARSE"
        if e["id"] == "F1":
            ep = {g["group"]: g for g in groups["ep_episode"][o["primary_outcome"]]}
            e["is_status"] = "WEAK_DIRECTION_AS_PREDICTED"
            e["is_basis"] = (f"FIRST cew {ep['FIRST']['cohort_equal_weight_mean']:+.3f} (n={ep['FIRST']['n']}), OVERLAPPING_REPEAT "
                             f"{ep['OVERLAPPING_REPEAT']['cohort_equal_weight_mean']:+.3f} (n={ep['OVERLAPPING_REPEAT']['n']}), LATER_REPEAT "
                             f"{ep['LATER_REPEAT']['cohort_equal_weight_mean']:+.3f} (n={ep['LATER_REPEAT']['n']}); modest, not leading")
        if e["id"] == "F4":
            v = o["f4_inside_s4"]["volume_ratio"]
            e["is_status"] = "NO_SEPARATION"
            e["is_basis"] = f"inside S4 the volume ratio has within-cohort rho {v.get('within_cohort_mean_spearman'):+.3f}, T3-T1 {v.get('t3_minus_t1_mean'):+.3f}"

    # --- revisions produced by the IS interaction maps (registered as children, frozen now)
    med_off = None
    import csv, statistics
    from verification import r4r5_anatomy_stats as st
    isr = [r for r in csv.DictReader(ATLAS.open(encoding="utf-8")) if r["split"] == "IS"]
    med_off = statistics.median([st.num(r["sc_close_vs_high20"]) for r in isr if st.num(r["sc_close_vs_high20"]) is not None])
    revisions = [
        {"id": "D3-7r", "lane": "directed", "parent": "D3-7", "cutoff": "SIGNAL_CLOSE", "feature": "cx_rank_in_eight, cx_gap_to_next_rank",
         "question": "Is the rank-1 fade a gap effect? Rank-1 names with a top-tercile gap to rank 2 versus everything else",
         "test": "rank-1 & gap T3 vs ranks 2-8; cohort-equal-weight", "prediction": "rank-1 with a wide gap fades most",
         "is_status": "RECURRING_ASSOCIATION",
         "is_basis": "IS: 23 of 25 rank-1 names sit in the top gap tercile, mean +0.356, hit 0.91; ranks 2-8 near zero; 3 of 6 counterexamples are November 2025"},
        {"id": "D3-3r", "lane": "directed", "parent": "D3-3", "cutoff": "SIGNAL_CLOSE", "feature": "sc_close_vs_high20",
         "question": "Reversed reading: names already off their 20-session high fade MORE, among ranks 2-8",
         "test": "tercile contrast among ranks 2-8 with IS cuts", "prediction": "T1 (furthest below the high) > T3 (at the high)",
         "is_status": "RECURRING_ASSOCIATION",
         "is_basis": "IS ranks 2-8: T1 mean +0.123 hit 0.65 vs T3 -0.074 hit 0.25; negative in every IS month; opposite to the original D3-3 prediction"},
        {"id": "D3-11", "lane": "directed", "parent": "D3-6", "cutoff": "SIGNAL_CLOSE", "feature": "sc_signal_close_band x sc_close_vs_high20",
         "question": "2x2 state map: price band 10-20 vs >=20 by off-high (below IS median close_vs_high20) vs near-high",
         "test": "four cells, cohort-equal-weight mean and hit rate",
         "prediction": "10-20 x off-high best; >=20 x near-high worst; ordering preserved",
         "is_status": "RECURRING_ASSOCIATION",
         "is_basis": "IS: 10-20 x off-high +0.203 hit 0.75 (n=44); >=20 x near-high -0.075 hit 0.28 (n=69)"},
        {"id": "D2-4", "lane": "directed", "parent": "D2-1", "cutoff": "SIGNAL_CLOSE", "feature": "sc_four_state",
         "question": "Are the two reductions informative individually? Momentum sign versus volume ratio among ranks 2-8",
         "test": "ret3 sign split and volume-ratio terciles among ranks 2-8",
         "prediction": "momentum sign separates; volume ratio separates weakly and inconsistently across bands",
         "is_status": "RECURRING_ASSOCIATION",
         "is_basis": "IS ranks 2-8: ret3<=0 +0.065 vs >0 +0.003; volume T1 +0.058 vs T3 +0.001; in band >=20 S4 (+0.019) beats S3 (-0.056), so the volume cut is not monotone across bands"},
        {"id": "F2r", "lane": "freelance", "parent": "F2", "cutoff": "SIGNAL_CLOSE", "feature": "sc_up_sessions_15, sc_top3_sessions_share_of_advance",
         "question": "Reversed reading: episodic advances (few up sessions, concentrated in three sessions) fade MORE",
         "test": "tercile contrasts with IS cuts", "prediction": "few up sessions > many; high top-3 share > low",
         "is_status": "REJECTED_OPPOSITE_DIRECTION_THEN_REVERSED",
         "is_basis": "F2 predicted steady grinders fade more; IS shows the opposite in every month (up_sessions within contrast -0.101, share 0.24)"},
        {"id": "D3-8b", "lane": "directed", "parent": "D3-8", "cutoff": "PRE_ORDER", "feature": "po_signal_close_to_preorder",
         "question": "Between-cohort only: cohorts whose names kept rising into the order did better as a whole",
         "test": "between-cohort Spearman of cohort means", "prediction": "no within-cohort effect; between-cohort positive",
         "is_status": "BETWEEN_COHORT_ONLY_EXPLORATORY",
         "is_basis": "IS within-cohort rho 0.00, between-cohort rho +0.45 on 25 cohort means; a cohort-level regime effect, not a stock-selection signal"},
    ]
    registry.extend(revisions)

    # --- frozen definitions for the confirmation batch
    probes = [
        {"id": "P1", "name": "rank-1 only", "mask": "cx_rank_in_eight == 1", "control": "ranks 2-8 and the full book",
         "expected": "higher net per entry dollar and hit rate than the full book; unused exposure idle",
         "basis": "research-only subset; no new entry, hold or sizing; no compounded equity"},
        {"id": "P2", "name": "10-20 band and off-high", "mask": f"sc_signal_close_band == '10-20' and sc_close_vs_high20 < {med_off:.6f}",
         "control": "complement and the full book", "expected": "higher net per entry dollar and hit rate", "basis": "IS 2x2 best cell"},
        {"id": "P3", "name": "exclude near-high names priced 20-80", "mask": f"not (sc_signal_close_band in ('20-40','40-80') and sc_close_vs_high20 >= {med_off:.6f})",
         "control": "the excluded cell and the full book", "expected": "the excluded cell has lower net per entry dollar than the retained set",
         "basis": "IS 2x2 worst cell removed"},
        {"id": "P4", "name": "non-positive three-session momentum only", "mask": "sc_ret3 <= 0 (states S1 and S2)", "control": "ret3 > 0 and the full book",
         "expected": "higher net per entry dollar; tests whether the frozen momentum halving points the right way on sizing-neutral grounds",
         "basis": "frozen R5 rule sign, no threshold learned"},
    ]
    claims = [
        {"id": "C1", "claim": "rank-1 extremeness", "registered": ["D3-7", "D3-7r"],
         "expected_oos": "rank-1 cohort-equal-weight return exceeds ranks 2-8 by more than 0.10 and hit rate exceeds 0.65; cx_gap_to_next_rank within-cohort positive share >= 0.62"},
        {"id": "C2", "claim": "already-off-the-high fades more (ranks 2-8)", "registered": ["D3-3r"],
         "expected_oos": "T1 minus T3 of sc_close_vs_high20 positive among ranks 2-8; within-cohort share of positive halves <= 0.38"},
        {"id": "C3", "claim": "wide recent range fades more", "registered": ["sc_mean_range_pct_10", "sc_logret_std_15", "sc_signal_day_range_pct", "po_partial_range_pct"],
         "expected_oos": "within-cohort half-contrast positive, share >= 0.62"},
        {"id": "C4", "claim": "10-20 band fades more than 20-80", "registered": ["D3-6"],
         "expected_oos": "10-20 cohort-equal-weight mean exceeds the 20-40 and 40-80 means"},
        {"id": "C5", "claim": "momentum sign separates; the two HALF states differ", "registered": ["D2-1", "D2-2", "D2-4"],
         "expected_oos": "ret3<=0 exceeds ret3>0; S2 closer to S1 than to S3 (sparse S2 may fail on count alone)"},
        {"id": "C6", "claim": "overlapping repeats fade less than first selections", "registered": ["F1"],
         "expected_oos": "FIRST cohort-equal-weight mean exceeds OVERLAPPING_REPEAT; modest"},
        {"id": "C7", "claim": "episodic advances fade more", "registered": ["F2r", "D3-1"],
         "expected_oos": "sc_up_sessions_15 within contrast negative; sc_top3_sessions_share_of_advance positive"},
        {"id": "C8", "claim": "pre-order information adds nothing within cohort", "registered": ["D3-8", "F3", "D3-9"],
         "expected_oos": "po_signal_close_to_preorder and po_preorder_location_in_partial_range within-cohort share between 0.38 and 0.62"},
        {"id": "C9", "claim": "2x2 state map ordering", "registered": ["D3-11"],
         "expected_oos": "10-20 x off-high is the best cell and >=20 x near-high the worst, by cohort-equal-weight mean"},
        {"id": "C10", "claim": "holding-path shape", "registered": ["paths"],
         "expected_oos": "IMMEDIATE_FADE the most common archetype; most of the mean fade accrues by age 2; S1 path keeps accruing through age 10"},
    ]
    freeze = {
        "arrow": "CG Arrow 011", "stage": "hypothesis_freeze", "timestamp": stamp(),
        "head_at_freeze": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "is_months": ["2025-09", "2025-11", "2026-01", "2026-03", "2026-05", "2026-07"],
        "oos_months": ["2025-10", "2025-12", "2026-02", "2026-04", "2026-06", "2026-08"],
        "oos_status": "internal confirmation only; these months have been inspected in earlier arrows and are not pristine",
        "primary_outcome": o["primary_outcome"], "secondary_outcome": o["secondary_outcome"],
        "is_rows": o["is_rows"], "is_cohorts": o["is_cohorts"], "is_cohort_census": o["cohort_census"],
        "leading_rule": o["leading_rule"], "leading_features_is": o["leading_features"],
        "frozen_definitions": {
            "tercile_cuts": cuts,
            "close_vs_high20_is_median": med_off,
            "price_bands": "[10,20) [20,40) [40,80) else OUTSIDE_10_80, on the signal close",
            "four_state": "ret3 > 0 halves (momentum), volume_ratio > 1 halves (volume); missing is its own state",
            "path_archetypes": ("IMMEDIATE_FADE: age-1 and age-10 returns > 0; ADVERSE_THEN_FADE: age-10 > 0 and some close in ages 1-4 < 0; "
                                "FADE_THEN_REVERSAL: age-10 <= 0 and some close in ages 1-4 >= 0.03; CONTINUATION: age-10 <= 0 and no close >= 0.03; "
                                "OTHER; UNLABELED_STALE_OR_OPEN. Declared in code before any data was viewed; close-only marks"),
            "within_cohort_contrast": "mean over cohorts of (top half by feature minus bottom half by feature) of the outcome, cohorts with >= 4 scored rows",
            "cohort_equal_weight_mean": "mean of per-cohort means",
            "probes": probes,
            "probe_metrics": "n, cohorts, securities, mean and median price return, hit rate, net per entry dollar, entry exposure, fixed-dollar net; "
                             "exposure-matched: probe net per entry dollar applied to the full book's entry exposure, labeled hypothetical; no compounded equity",
        },
        "registry": registry,
        "claims_to_confirm": claims,
        "reported_regardless_of_outcome": "every registered feature relationship, group table, claim and probe, including non-replications",
        "input_hashes": {"trade_atlas.csv": digest(ATLAS), "trade_path_atlas.csv": digest(PATHS),
                         "is_results.json": digest(CACHE / "is_results.json"), "build_manifest.json": digest(CACHE / "build_manifest.json"),
                         "arrow008_manifest": digest(REPORTS / "cg_arrow008_manifest.json"),
                         "arrow010_manifest": digest(REPORTS / "cg_arrow010_manifest.json")},
        "code_hashes": {p: digest(REPO_ROOT / p) for p in (
            "src/verification/r4r5_anatomy.py", "src/verification/r4r5_anatomy_stats.py", "scripts/cg_arrow011_build.py",
            "scripts/cg_arrow011_analyze.py", "scripts/cg_arrow011_freeze.py", "src/verification/r4r5_replay.py",
            "src/verification/r4r5_data.py")},
        "build_controls": build["control_checks"], "build_counts": {k: v for k, v in build["counts"].items() if k.startswith(("R5/", "R4/"))},
        "post_freeze_rule": "no new hypothesis, threshold, mask or probe after this commit; anything noticed after the reveal is labeled post-reveal and queued",
        "unstarted_queue": [
            "float / shares outstanding as-of history for the 10-20 band names (data not held)",
            "first-public-availability catalyst evidence for the top-gap rank-1 names (requires timestamped news, not held)",
            "cohort-level regime descriptor behind the between-cohort pre-order effect (D3-8b)",
        ],
    }
    dump_json(REPORTS / "cg_arrow011_hypothesis_freeze.json", freeze)
    print(f"{stamp()} freeze written: {len(registry)} registry entries, {len(claims)} claims, {len(probes)} probes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
