"""CG Arrow 012 Phase A — regenerate the Arrow 011 relationships under repaired statistics.

Reads the Arrow 011 private atlas and its committed freeze, recomputes every registered
feature relationship with the order-invariant statistics, compares each prior label against
the repaired view, runs the dependence diagnostics, and writes the Arrow 012 repair outputs.

No Arrow 011 artifact is written. No frozen trade, quantity or account is touched.

Usage: python scripts/cg_arrow012_repair.py
"""
from __future__ import annotations

import csv
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_repaired_stats as rs  # noqa: E402
from verification.r4r5_data import VERIFY_ROOT, digest, dump_json, read_json, stamp  # noqa: E402

A11 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011"
ATLAS = A11 / "trade_atlas.csv"
CACHE = VERIFY_ROOT / "a12"
PRIMARY = "oc_price_return_10"
SECOND = "oc_net_per_entry_dollar"
FROZEN_52 = None  # set in main from the Arrow 008 membership


def load(p):
    with Path(p).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def label_change(prior_status: str, rep: dict) -> tuple[str, str]:
    """Compare an Arrow 011 status against the repaired within-cohort view.

    The repaired evidence is the pairwise directional effect, which never depends on row
    order, together with the share of cohorts on one side. A prior claim survives when the
    repaired effect keeps its sign and at least 62% of scorable cohorts agree, matching the
    Arrow 011 leading rule applied to the repaired statistic.
    """
    eff = rep.get("pairwise_directional_effect")
    share = rep.get("pairwise_positive_share")
    scored = rep.get("pairwise_cohorts_scored") or 0
    if eff is None or share is None or scored < 15:
        return "UNSCORABLE_AFTER_REPAIR", f"pairwise cohorts scored {scored}"
    one_sided = share >= 0.62 or share <= 0.38
    was_leading = prior_status in ("REPLICATED", "SAME_SIGN_WEAKER")
    if was_leading and one_sided:
        return "SURVIVES_REPAIR", f"pairwise effect {eff:+.4f}, one-sided share {share:.2f}"
    if was_leading and not one_sided:
        return "WEAKENS_AFTER_REPAIR", f"pairwise effect {eff:+.4f}, share {share:.2f} inside the 0.38-0.62 band"
    if not was_leading and one_sided:
        return "APPEARS_ONLY_AFTER_REPAIR", f"pairwise effect {eff:+.4f}, share {share:.2f}; not claimed on IS"
    return "STILL_NO_SIGNAL", f"pairwise effect {eff:+.4f}, share {share:.2f}"


def main() -> int:
    t0 = time.monotonic()
    CACHE.mkdir(parents=True, exist_ok=True)
    freeze11 = read_json(REPORTS / "cg_arrow011_hypothesis_freeze.json")
    a8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    rows = load(ATLAS)
    frozen = sorted({r["cohort_id"] for r in rows})
    assert len(frozen) == 52, len(frozen)
    assert digest(ATLAS) == freeze11["input_hashes"]["trade_atlas.csv"], "atlas drifted from the Arrow 011 freeze"
    print(f"{stamp()} atlas rows={len(rows)} cohorts={len(frozen)}; Arrow 011 freeze hash matches", flush=True)

    isr = [r for r in rows if r["split"] == "IS"]
    oos = [r for r in rows if r["split"] == "OOS"]
    a11_conf = {r["comparison"][8:]: r for r in load(REPORTS / "cg_arrow011_confirmation.csv")
                if r["kind"] == "continuous_feature"}
    features = sorted(freeze11["frozen_definitions"]["tercile_cuts"])

    out_rows, verdicts = [], {}
    for f in features:
        reps = {s: rs.relationship(sel, f, PRIMARY) for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows))}
        prior = a11_conf.get(f, {})
        status, basis = label_change(prior.get("status", ""), reps["IS"])
        verdicts[f] = status
        for split, rep in reps.items():
            a11_val = float(prior["is_value"]) if split == "IS" and prior.get("is_value") not in (None, "") else (
                float(prior["oos_value"]) if split == "OOS" and prior.get("oos_value") not in (None, "") else None)
            out_rows.append({
                "feature": f, "cutoff": "PRE_ORDER" if f.startswith("po_") else "SIGNAL_CLOSE", "split": split,
                "outcome": PRIMARY, "stats_version": rs.STATS_VERSION,
                "n": rep.get("n"), "missing": rep.get("missing"), "cohorts": rep.get("cohorts"),
                "securities": rep.get("securities"), "months": rep.get("months"),
                "a11_half_split_value": a11_val,
                "a11_status": prior.get("status") if split in ("IS", "OOS") else None,
                "repaired_strict_half_contrast": rep.get("strict_half_contrast"),
                "strict_half_cohorts_scored": rep.get("strict_half_cohorts_scored"),
                "strict_half_cohorts_tie_excluded": rep.get("strict_half_cohorts_tie_excluded"),
                "strict_half_positive_share": rep.get("strict_half_positive_share"),
                "repaired_pairwise_effect": rep.get("pairwise_directional_effect"),
                "pairwise_cohorts_scored": rep.get("pairwise_cohorts_scored"),
                "pairwise_total_pairs": rep.get("pairwise_total_pairs"),
                "pairwise_positive_share": rep.get("pairwise_positive_share"),
                "within_cohort_mean_spearman": rep.get("within_cohort_mean_spearman"),
                "within_cohort_spearman_cohorts": rep.get("within_cohort_spearman_cohorts"),
                "cohorts_constant_feature": rep.get("cohorts_constant_feature"),
                "cohorts_below_min_rows": rep.get("cohorts_below_min_rows"),
                "pooled_spearman": rep.get("pooled_spearman"),
                "between_cohort_spearman": rep.get("between_cohort_spearman"),
                "repair_verdict": status if split == "IS" else None,
                "repair_basis": basis if split == "IS" else None,
                "units": rep.get("units")})
    exp.write_csv(REPORTS / "cg_arrow012_repaired_relationships.csv", out_rows)

    # ---- A3 dependence diagnostics on the relationships Arrow 011 led with
    leading = [f for f, s in ((k, v.get("status")) for k, v in a11_conf.items()) if s == "REPLICATED"]
    diag = {}
    for f in sorted(leading):
        diag[f] = {
            "blocks": {str(b): rs.moving_block_resample(isr, f, PRIMARY, block=b) for b in (1, 2, 4)},
            "repeated_security": rs.repeated_security_sensitivity(isr, f, PRIMARY),
        }
    print(f"{stamp()} dependence diagnostics for {len(diag)} replicated relationships", flush=True)

    # ---- the direct rank-one group result, checked independently of any within-cohort statistic
    def group(sel, key, val):
        v = [rs.num(r[PRIMARY]) for r in sel if r[key] == val and rs.num(r.get(PRIMARY)) is not None]
        import statistics as stx
        return {"n": len(v), "mean": stx.mean(v) if v else None, "median": stx.median(v) if v else None,
                "hit_rate": (sum(1 for x in v if x > 0) / len(v)) if v else None}
    rank_one = {s: {"rank1": group(sel, "cx_rank_in_eight", "1"),
                    "ranks2_8": {"n": sum(1 for r in sel if r["cx_rank_in_eight"] != "1"),
                                 **{k: v for k, v in group([r for r in sel if r["cx_rank_in_eight"] != "1"], "split", s).items() if k != "n"}}}
                for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows))}

    # ---- overall verdict
    counts = {}
    for v in verdicts.values():
        counts[v] = counts.get(v, 0) + 1
    survived = [f for f, v in verdicts.items() if v == "SURVIVES_REPAIR"]
    weakened = [f for f, v in verdicts.items() if v == "WEAKENS_AFTER_REPAIR"]
    a11_replicated = set(leading)
    lost = sorted(a11_replicated - set(survived))
    if not a11_replicated:
        verdict = "A11_RELATIONSHIP_INVALIDATED_BY_REPAIR"
    elif len(lost) == 0:
        verdict = "A11_RELATIONSHIP_SURVIVES_REPAIR"
    elif len(lost) < len(a11_replicated) / 2:
        verdict = "A11_RELATIONSHIP_WEAKENS_AFTER_REPAIR"
    else:
        verdict = "A11_RELATIONSHIP_INVALIDATED_BY_REPAIR"

    manifest = {
        "arrow": "CG Arrow 012", "phase": "A_repair", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "stats_version": rs.STATS_VERSION, "frozen_cohorts": frozen,
        "a11_freeze_hash_ok": True, "a11_atlas_sha256": digest(ATLAS),
        "a8_membership_sha256": a8["membership_sha256"],
        "verdicts": verdicts, "verdict_counts": counts, "overall_verdict": verdict,
        "a11_replicated": sorted(a11_replicated), "survived": sorted(survived),
        "weakened": sorted(weakened), "lost_after_repair": lost,
        "dependence": diag, "rank_one_direct_group": rank_one,
        "elapsed_minutes": (time.monotonic() - t0) / 60,
    }
    dump_json(CACHE / "repair_manifest.json", manifest)
    print(f"{stamp()} repair verdict: {verdict}; counts {counts}", flush=True)
    print(f"{stamp()} lost after repair: {lost}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
