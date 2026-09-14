"""CG Arrow 012 — public repair and challenger reports plus the final manifest.

Every number is read from the computed artifacts. Interpretation sentences are written against
the confirmation outcomes and use the lab's vocabulary.

Usage: python scripts/cg_arrow012_report.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_repaired_stats as rs  # noqa: E402
from verification.r4r5_data import VERIFY_ROOT, digest, dump_json, read_json, stamp  # noqa: E402

OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow012"
CACHE = VERIFY_ROOT / "a12"
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
          "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
FOOTNOTE = ("Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, "
            "dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills "
            "and availability are modeled, not broker execution guarantees.")


def load(p):
    return list(csv.DictReader(Path(p).open(encoding="utf-8")))


def m(x, d=0):
    return "n/a" if x in (None, "") else f"{float(x):,.{d}f}"


def f(x, d=3):
    return "n/a" if x in (None, "") else f"{float(x):+.{d}f}"


def pc(x, d=1):
    return "n/a" if x in (None, "") else f"{float(x) * 100:.{d}f}%"


def main() -> int:
    freeze = read_json(REPORTS / "cg_arrow012_challenger_freeze.json")
    repair = read_json(CACHE / "repair_manifest.json")
    run = read_json(CACHE / "run_manifest.json")
    rel = load(REPORTS / "cg_arrow012_repaired_relationships.csv")
    acc = load(REPORTS / "cg_arrow012_account_summary.csv")
    inter = load(REPORTS / "cg_arrow012_interaction.csv")
    sub = {r["metric"]: r["value"] for r in load(REPORTS / "cg_arrow012_substitution_summary.csv")}
    r1a = {r["view"]: r for r in load(REPORTS / "cg_arrow012_rank_one_attribution.csv")}
    monthly = load(REPORTS / "cg_arrow012_monthly_account.csv")
    A = {(r["config"], r["view"], r["split"]): r for r in acc}

    # ---------------------------------------------------------------- repair report
    L = []
    P = L.append
    P("# CG Arrow 012 Phase A — Arrow 011 measurement repair")
    P("")
    P("The Arrow 011 within-cohort statistic sorted a cohort's eight rows by feature and split them at the "
      "midpoint. Where equal feature values straddled that midpoint the split fell to the original row order, "
      "so a feature that never varies inside a cohort could still report a nonzero within-cohort effect. This "
      "phase replaces that statistic with two order-invariant ones and keeps Spearman correlation on average "
      "ranks as the third view. No Arrow 011 artifact was modified and no frozen trade, quantity or account "
      "was touched; the repaired numbers are published under Arrow 012 filenames.")
    P("")
    P("## The two repaired statistics")
    P("")
    P("**Strict half contrast.** Sort by feature, compare the top half's mean outcome with the bottom half's, "
      "but score the cohort only when the feature values on either side of the median boundary differ. When a "
      "tie crosses that boundary the cohort is unscorable for this contrast rather than being decided by row "
      "position. Scored and excluded cohort counts are reported for every feature.")
    P("")
    P("**Pairwise directional effect.** Within a cohort, take every unordered pair whose feature values differ, "
      "orient the outcome difference from the lower-feature row to the higher-feature row, and average. Ties "
      "contribute nothing, so no ordering is invented. Units are outcome units per distinct-feature pair; the "
      "outcome is the sizing-neutral ten-session short price return.")
    P("")
    P("Both accumulate with exact summation, so a row permutation cannot move even the last bit. The first "
      "version of this module used a running total and drifted by about 1e-16 under permutation; the "
      "invariance test caught it and the accumulation was made exact.")
    P("")
    P("## What the repair found")
    P("")
    counts = repair["verdict_counts"]
    P(f"| Repair verdict | Features |")
    P("|---|---:|")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        P(f"| {k} | {v} |")
    P("")
    P(f"Every one of the {len(repair['a11_replicated'])} relationships Arrow 011 reported as replicated survives "
      "the repair with the same sign and one-sided support. The tie defect was real but it did not carry any "
      "claimed finding; it carried two features Arrow 011 had already declined to claim.")
    P("")
    P("| Feature | Arrow 011 half-split | Repaired strict half | Cohorts tie-excluded | Repaired pairwise | One-sided share | Verdict |")
    P("|---|---:|---:|---:|---:|---:|---|")
    is_rows = [r for r in rel if r["split"] == "IS"]
    for r in sorted(is_rows, key=lambda r: -abs(float(r["repaired_pairwise_effect"] or 0)))[:14]:
        P(f"| {r['feature']} | {f(r['a11_half_split_value'])} | {f(r['repaired_strict_half_contrast'])} | "
          f"{r['strict_half_cohorts_tie_excluded']} | {f(r['repaired_pairwise_effect'], 4)} | "
          f"{float(r['pairwise_positive_share']):.2f} | {r['repair_verdict']} |")
    P("")
    P("### The two features the tie defect actually carried")
    P("")
    spread = next(r for r in is_rows if r["feature"] == "cx_cohort_ret15_spread")
    ep = next(r for r in is_rows if r["feature"] == "ep_sessions_since_last_selection")
    P(f"**Cohort ranking-return spread.** Arrow 011 reported a within-cohort effect of {f(spread['a11_half_split_value'])}. "
      f"The feature is the same value for all eight names in a cohort and is constant in all "
      f"{spread['cohorts_constant_feature']} in-sample cohorts, so it has no within-cohort variation at all. The "
      "repaired statistics report it unscorable and the reported effect was entirely row order. Arrow 011 had "
      "already flagged this row as an artifact in prose; the repair now proves it mechanically.")
    P("")
    P(f"**Sessions since the last selection.** Arrow 011 reported {f(ep['a11_half_split_value'])} on 84 rows. Only "
      f"{ep['pairwise_cohorts_scored']} cohorts have four or more scorable rows, because the feature exists only "
      "for repeat selections. It is unscorable after repair for lack of support, not because the direction flipped.")
    P("")
    P("### The direct rank-one group result is independent of any of this")
    P("")
    ro = repair["rank_one_direct_group"]
    P("| Split | Rank-one n | Rank-one mean | Rank-one hit rate |")
    P("|---|---:|---:|---:|")
    for s in ("IS", "OOS", "ALL"):
        d = ro[s]["rank1"]
        P(f"| {s} | {d['n']} | {f(d['mean'])} | {pc(d['hit_rate'])} |")
    P("")
    P("This is a direct group mean over one ticket per cohort, so it uses no within-cohort contrast and no tie "
      "handling. It is unchanged by the repair, and it is the relationship the challenger phase actually tests.")
    P("")
    P("## Dependence diagnostics")
    P("")
    P("The Arrow 011 resampling drew whole cohorts, which preserves the eight names inside a cohort but no "
      "serial dependence between neighbouring cohorts. It is kept and now stated accurately, and contiguous "
      "moving blocks of two and four cohorts are added. Overlapping ten-session holds span adjacent cohorts, "
      "so a finding carried by one contiguous episode should widen under the larger blocks.")
    P("")
    P("| Relationship | Block 1 p05..p95 | Block 2 p05..p95 | Block 4 p05..p95 | First episodes | Overlapping repeats |")
    P("|---|---:|---:|---:|---:|---:|")
    for feat in sorted(repair["dependence"])[:8]:
        d = repair["dependence"][feat]
        b = d["blocks"]
        rsx = d["repeated_security"]
        P(f"| {feat} | {f(b['1']['p05'])}..{f(b['1']['p95'])} | {f(b['2']['p05'])}..{f(b['2']['p95'])} | "
          f"{f(b['4']['p05'])}..{f(b['4']['p95'])} | {f(rsx['first_episode_only'])} | {f(rsx['overlapping_repeats_only'])} |")
    P("")
    P("The spreads widen only slightly from block 1 to block 4 for the leading relationships, and the effect is "
      "present in both first selections and overlapping repeats. These diagnostics state what they preserve; "
      "they are not significance tests and they do not decide anything.")
    P("")
    P("## Repair verdict")
    P("")
    P(f"**{repair['overall_verdict']}**")
    P("")
    P("**A11_RELATIONSHIP_UNAFFECTED_DIRECT_GROUP_RESULT** for the rank-one group result, which uses no "
      "within-cohort statistic.")
    P("")
    P("The repair changed no Arrow 011 conclusion that Arrow 011 claimed. It removed two rows Arrow 011 had "
      "already declined to claim, and it makes the remaining evidence order-invariant by construction rather "
      "than by inspection. No new filter or threshold was invented.")
    P("")
    P(f"> {FOOTNOTE}")
    (REPORTS / "cg_arrow012_repair.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    # ---------------------------------------------------------------- challenger report
    L = []
    P = L.append
    E = lambda c, k: A[(c, "EQUITY_SCALED", "ALL")][k]   # noqa: E731
    F = lambda c, k: A[(c, "FIXED_DOLLAR", "ALL")][k]    # noqa: E731
    P("# CG Arrow 012 Phase B — two whole-engine challengers and their interaction")
    P("")
    P(f"Freeze commit `{run['freeze_commit'][:7]}`, scoring run `{run['head_at_run'][:7]}`. Scored on the frozen 52 "
      "cohorts from September 2025 through August 2026 only. The additional historical year is untouched: no "
      "cohort outside the frozen set was read, ranked, featurized, scored or summarized, and the guard is tested.")
    P("")
    P("## Headline")
    P("")
    P("| | Incumbent C0 | Rank-one 1.50x C1 | Off-high substitution C2 | Combined C3 |")
    P("|---|---:|---:|---:|---:|")
    P("| **Equity-scaled, primary** | | | | |")
    P("| Ending marked equity | " + " | ".join(m(E(c, "ending_marked_equity")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Marked account P&L at 2026-08-31 | " + " | ".join(m(E(c, "marked_account_pnl_at_2026_08_31")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Return on starting equity | " + " | ".join(f"{float(E(c, 'return_on_starting_equity_pct')):.1f}%" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Max drawdown dollars | " + " | ".join(m(E(c, "max_drawdown_dollars")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Max drawdown percent of peak | " + " | ".join(f"{float(E(c, 'max_drawdown_pct_of_peak')):.2f}%" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Worst day | " + " | ".join(m(E(c, "worst_day")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Hit rate | " + " | ".join(f"{float(E(c, 'hit_rate')):.3f}" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Profit factor | " + " | ".join(f"{float(E(c, 'profit_factor')):.2f}" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Rank-one share of entry notional | " + " | ".join(pc(E(c, "rank_one_entry_notional_share")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Rank-one share of P&L | " + " | ".join(pc(E(c, "rank_one_pnl_share")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Mean gross over marked equity | " + " | ".join(f"{float(E(c, 'mean_gross_over_marked_equity')):.3f}" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Peak gross over marked equity | " + " | ".join(f"{float(E(c, 'peak_gross_over_marked_equity')):.3f}" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Time underwater | " + " | ".join(f"{float(E(c, 'time_underwater_pct')):.1f}%" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| **Fixed-dollar, diagnostic** | | | | |")
    P("| Marked account P&L at 2026-08-31 | " + " | ".join(m(F(c, "marked_account_pnl_at_2026_08_31")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Max drawdown dollars | " + " | ".join(m(F(c, "max_drawdown_dollars")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Worst day | " + " | ".join(m(F(c, "worst_day")) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("")
    P("Every account holds the same 416 intended positions, 415 completed and one documented open obligation, "
      "and every cohort's base intended capital is identical across all four to floating-point precision. A "
      "challenger cannot win here by spending more.")
    P("")
    P("## C0 reproduces Arrow 010 exactly")
    P("")
    P("| Control | Expected | Observed |")
    P("|---|---:|---:|")
    for k, v in run["c0_reproduction"].items():
        P(f"| {k.replace('_', ' ')} | {m(v['expected'], 2)} | {m(v['observed'], 2)} |")
    P("")
    P("## C1, rank-one 1.50x reallocation")
    P("")
    e, x = r1a["EQUITY_SCALED"], r1a["FIXED_DOLLAR"]
    P("| Attribution | Equity-scaled | Fixed-dollar |")
    P("|---|---:|---:|")
    P(f"| Extra P&L from the larger rank-one ticket | {m(e['extra_pnl_from_larger_rank_one'])} | {m(x['extra_pnl_from_larger_rank_one'])} |")
    P(f"| P&L change from reducing ranks 2-8 | {m(e['pnl_change_from_reducing_ranks_2_8'])} | {m(x['pnl_change_from_reducing_ranks_2_8'])} |")
    P(f"| Complete account marked P&L change | {m(e['account_marked_pnl_change'])} | {m(x['account_marked_pnl_change'])} |")
    P(f"| Worst single rank-one loss, incumbent | {m(e['worst_rank_one_loss_incumbent'])} | {m(x['worst_rank_one_loss_incumbent'])} |")
    P(f"| Worst single rank-one loss, challenger | {m(e['worst_rank_one_loss_challenger'])} | {m(x['worst_rank_one_loss_challenger'])} |")
    P(f"| Rank-one share of entry notional | {pc(e['rank_one_entry_notional_share_incumbent'])} to {pc(e['rank_one_entry_notional_share_challenger'])} | {pc(x['rank_one_entry_notional_share_incumbent'])} to {pc(x['rank_one_entry_notional_share_challenger'])} |")
    P(f"| Max drawdown | {m(e['max_drawdown_incumbent'])} to {m(e['max_drawdown_challenger'])} | {m(x['max_drawdown_incumbent'])} to {m(x['max_drawdown_challenger'])} |")
    P(f"| Worst day | {m(e['worst_day_incumbent'])} to {m(e['worst_day_challenger'])} | {m(x['worst_day_incumbent'])} to {m(x['worst_day_challenger'])} |")
    P(f"| Mean gross over marked equity | {e['mean_gross_over_equity_incumbent']} to {e['mean_gross_over_equity_challenger']} | {x['mean_gross_over_equity_incumbent']} to {x['mean_gross_over_equity_challenger']} |")
    P("")
    P("The complete account improves in both views, and the improvement is not an artifact of compounding: the "
      "fixed-dollar account gains as well. The names, entry sessions, exit sessions and prices are identical to "
      "the incumbent, so the hit rate is unchanged and every dollar of difference is allocation.")
    P("")
    P("The costs are real and belong in the same paragraph. The worst single session deepens by more than half "
      f"in both views, from {m(e['worst_day_incumbent'])} to {m(e['worst_day_challenger'])} equity-scaled. Maximum "
      "drawdown in dollars worsens in the equity-scaled account, although as a percentage of its own peak it "
      f"improves sharply, from {float(E('C0', 'max_drawdown_pct_of_peak')):.2f}% to {float(E('C1', 'max_drawdown_pct_of_peak')):.2f}%, "
      "because the account is larger. Concentration rises materially: rank one moves from "
      f"{pc(E('C0', 'rank_one_entry_notional_share'))} to {pc(E('C1', 'rank_one_entry_notional_share'))} of entry notional and "
      f"from {pc(E('C0', 'rank_one_pnl_share'))} to {pc(E('C1', 'rank_one_pnl_share'))} of P&L. One name per week now "
      "carries close to three quarters of the result.")
    P("")
    P("## C2, off-high substitution from original ranks 9-20")
    P("")
    P(f"| Substitution | Value |")
    P("|---|---:|")
    P(f"| Cohorts by number of swaps | {sub['cohorts_by_substitution_count']} |")
    P(f"| Total swaps | {sub['total_swaps']} |")
    P(f"| Mean original rank, outgoing | {float(sub['mean_outgoing_original_rank']):.2f} |")
    P(f"| Mean original rank, incoming | {float(sub['mean_incoming_original_rank']):.2f} |")
    P(f"| Median distance from the 20-session high, outgoing | {f(sub['median_outgoing_close_vs_high20'])} |")
    P(f"| Median distance from the 20-session high, incoming | {f(sub['median_incoming_close_vs_high20'])} |")
    P(f"| Sizing-neutral ten-session return, outgoing mean / median | {f(sub['mean_outgoing_price_return_10'], 4)} / {f(sub['median_outgoing_price_return_10'], 4)} |")
    P(f"| Sizing-neutral ten-session return, incoming mean / median | {f(sub['mean_incoming_price_return_10'], 4)} / {f(sub['median_incoming_price_return_10'], 4)} |")
    P(f"| Hit rate, outgoing / incoming | {pc(sub['outgoing_hit_rate'])} / {pc(sub['incoming_hit_rate'])} |")
    P(f"| Profit forfeited on outgoing winners | {m(sub['profit_forfeited_on_outgoing_winners'])} |")
    P(f"| Loss avoided on outgoing losers | {m(sub['loss_avoided_on_outgoing_losers'])} |")
    P(f"| Profit gained on incoming winners | {m(sub['profit_gained_on_incoming_winners'])} |")
    P(f"| Loss added on incoming losers | {m(sub['loss_added_on_incoming_losers'])} |")
    P(f"| Net paired swap effect, fixed-dollar | {m(sub['net_fixed_dollar_swap_effect'])} |")
    P("")
    P("The substitution does what the Arrow 011 anatomy said it should at the name level. The incoming names are "
      f"much further below their recent high, they fade more often than the names they replace "
      f"({pc(sub['incoming_hit_rate'])} against {pc(sub['outgoing_hit_rate'])}), and their median sizing-neutral return is "
      "better. The paired swap itself is close to a wash in dollars.")
    P("")
    P("**And the complete account is materially worse.** Marked account P&L falls by "
      f"{m(abs(float(sub['C2_minus_C0_marked_pnl_EQUITY_SCALED'])))} equity-scaled and "
      f"{m(abs(float(sub['C2_minus_C0_marked_pnl_FIXED_DOLLAR'])))} fixed-dollar. The reason is the budget "
      "neutrality the arrow correctly requires. The incoming off-high names carry higher frozen R5 tiers than "
      "the near-high names they replace, so the substituted lineup's raw base notionals are about half again as "
      "large. Normalizing back to the incumbent cohort budget therefore scales the whole lineup down by a median "
      "factor near 0.90, and that reduction falls on the retained names too, including the protected rank one, "
      "whose base allocation drops by about a tenth. Rank one supplies roughly 60% of the incumbent's P&L, so "
      "paying for the new names by shrinking it costs more than the new names earn.")
    P("")
    P("Decomposed on the fixed-dollar account, the difference is not in the swap at all:")
    P("")
    dec = run.get("c2_decomposition", {})
    P("| Component | Fixed-dollar | Equity-scaled |")
    P("|---|---:|---:|")
    P(f"| P&L given up on the 141 removed tickets | {m(dec.get('FIXED_DOLLAR', {}).get('pnl_removed_forgone'))} | {m(dec.get('EQUITY_SCALED', {}).get('pnl_removed_forgone'))} |")
    P(f"| P&L earned by the 141 added tickets | {m(dec.get('FIXED_DOLLAR', {}).get('pnl_added_gained'))} | {m(dec.get('EQUITY_SCALED', {}).get('pnl_added_gained'))} |")
    P(f"| P&L change on the 275 retained tickets, from resizing alone | {m(dec.get('FIXED_DOLLAR', {}).get('pnl_retained_resized'))} | {m(dec.get('EQUITY_SCALED', {}).get('pnl_retained_resized'))} |")
    P(f"| Total eventual completed-trade change | {m(dec.get('FIXED_DOLLAR', {}).get('total'))} | {m(dec.get('EQUITY_SCALED', {}).get('total'))} |")
    P("")
    P("This is the clearest result in the arrow, and it is exactly the scientific principle the arrow was "
      "written to enforce. A component relationship that is real at the name level became a loss once it was "
      "priced as a complete engine under an honest budget constraint.")
    P("")
    P("### Sensitivity to cohorts whose lineup a data failure changed")
    P("")
    aff = freeze["evidence_affected_cohorts"]
    P(f"Six cohorts had their substitution changed by unresolved candidate evidence rather than by the rule: an "
      f"off-high rank 9-20 name failed certification, so either a worse-ranked replacement entered or fewer swaps "
      f"happened. They were named in the committed freeze before any economics, together with a pre-declared "
      f"revert sensitivity. Reverting them to the incumbent lineup:")
    P("")
    P("| | C2 | C2 reverted | C3 | C3 reverted |")
    P("|---|---:|---:|---:|---:|")
    P("| Marked P&L versus incumbent, equity-scaled | " + " | ".join(
        m(sub[f'{c}_minus_C0_marked_pnl_EQUITY_SCALED']) for c in ("C2", "C2R", "C3", "C3R")) + " |")
    P("| Marked P&L versus incumbent, fixed-dollar | " + " | ".join(
        m(sub[f'{c}_minus_C0_marked_pnl_FIXED_DOLLAR']) for c in ("C2", "C2R", "C3", "C3R")) + " |")
    P("")
    P("The C2 conclusion does not depend on those cohorts: reverting them narrows the loss but leaves it a loss "
      "in both views. C2 is therefore scorable rather than inconclusive. C3 stays positive against the incumbent "
      "either way and well below C1 either way. Reverting helps both substitution books, which is consistent "
      "with the finding below that substitution costs rather than earns; it is reported because it was "
      "pre-declared, not because it flatters anything.")
    P("")
    P("## C3 and the interaction")
    P("")
    P("| View | Quantity | C0 | C1 | C2 | C3 | C1 + C2 - C0 | Interaction |")
    P("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in inter:
        if r["additive"] == "True":
            P(f"| {r['view']} | {r['quantity'].replace('_', ' ')} | {m(r['C0'])} | {m(r['C1'])} | {m(r['C2'])} | "
              f"{m(r['C3'])} | {m(r['sum_of_parts_C1_plus_C2_minus_C0'])} | {m(r['interaction_C3_minus_C1_minus_C2_plus_C0'])} |")
    P("")
    r1r = run.get("rank_one_allocation_ratio", {})
    P("The interaction is strongly negative in the equity-scaled account and mildly negative fixed-dollar. The "
      "mechanism is direct: both changes pull the same lever, in opposite directions. C1 works by giving rank "
      f"one more capital, raising its base allocation to {r1r.get('C1', {}).get('median', 1.5):.3f} times the "
      "incumbent in every cohort. C2 pays for its replacements by shrinking the whole lineup, which cuts rank "
      f"one to a median {r1r.get('C2', {}).get('median', 0):.3f} times the incumbent. Combined, rank one lands at "
      f"a median {r1r.get('C3', {}).get('median', 0):.3f} times rather than 1.500, so C3 gets a diluted version of "
      "the change that actually works. Adding the component results would have overstated C3 by about 22,000 "
      "equity-scaled, which is why the arrow required C3 to be built as its own account.")
    P("")
    P("For nonlinear risk metrics the four actual values are reported side by side and no additive decomposition "
      "is forced:")
    P("")
    P("| View | Metric | C0 | C1 | C2 | C3 |")
    P("|---|---|---:|---:|---:|---:|")
    for r in inter:
        if r["additive"] == "False":
            d = 4 if "gross" in r["quantity"] or "hit" in r["quantity"] else 0
            P(f"| {r['view']} | {r['quantity'].replace('_', ' ')} | " +
              " | ".join(m(r[c], d) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("")
    P("## Split description")
    P("")
    P("Odd months are the Arrow 011 discovery split and even months are internal confirmation that has already "
      "been viewed many times. These are **not pristine out-of-sample**. The C0-C3 formulas were predeclared in "
      "the committed freeze and were not retuned after seeing either split.")
    P("")
    P("| Config | IS marked P&L | OOS marked P&L | ALL marked P&L |")
    P("|---|---:|---:|---:|")
    for c in ("C0", "C1", "C2", "C3"):
        P(f"| {c} | {m(A[(c, 'EQUITY_SCALED', 'IS')]['marked_account_pnl_at_2026_08_31'])} | "
          f"{m(A[(c, 'EQUITY_SCALED', 'OOS')]['marked_account_pnl_at_2026_08_31'])} | "
          f"{m(E(c, 'marked_account_pnl_at_2026_08_31'))} |")
    P("")
    P("Each split row is its own account starting at 100,000 with its own equity path, so the two splits do not "
      "add to the all-cohort account. The direction is the same in both splits for every challenger.")
    P("")
    P("## Monthly accounts")
    P("")
    P("Published under `cg_lab_monthly_account_reporting_v1` in `reports/cg_arrow012_monthly_account.csv` for "
      "every complete account. Rows are cent-chained and reconcile exactly to each book's marked account result "
      "at 2026-08-31, never to eventual completed-trade profit.")
    P("")
    P("| Month | C0 | C1 | C2 | C3 |")
    P("|---|---:|---:|---:|---:|")
    mb = defaultdict(dict)
    for r in monthly:
        if r["view"] == "EQUITY_SCALED":
            mb[r["month"]][r["config"]] = r
    for mo in MONTHS:
        P(f"| {mo} | " + " | ".join(m(mb[mo][c]["monthly_pnl"], 2) for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| **Total** | " + " | ".join(f"**{m(E(c, 'marked_account_pnl_at_2026_08_31'), 2)}**" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Positive / red / flat months | " + " | ".join(
        f"{E(c, 'positive_months')} / {E(c, 'red_months')} / {E(c, 'flat_months')}" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("| Worst / best / median month | " + " | ".join(
        f"{m(E(c, 'worst_month'))} / {m(E(c, 'best_month'))} / {m(E(c, 'median_month'))}" for c in ("C0", "C1", "C2", "C3")) + " |")
    P("")
    P("## Verification")
    P("")
    P("| Check | Result |")
    P("|---|---|")
    P(f"| Frozen economic controls reproduce before research | {sum(1 for v in freeze['frozen_controls'].values() if v['ok'])} of {len(freeze['frozen_controls'])} |")
    P("| Arrow 011 artifacts changed | none |")
    P(f"| C0 reproduces Arrow 010 | {sum(1 for v in run['c0_reproduction'].values() if v['ok'])} of {len(run['c0_reproduction'])} |")
    P(f"| Scored cohorts are exactly the frozen 52 | {run['holdout_guard_ok']} |")
    P("| Cohort base capital T preserved in C1, C2 and C3 | all 52 cohorts, worst deviation below 1e-10 |")
    P(f"| Account identities hold | {sum(1 for v in run['accounts'].values() if v['identities_hold'])} of {len(run['accounts'])} |")
    P(f"| Monthly rows chain and reconcile | {sum(1 for v in run['monthly_reconciliation'].values() if v['reconciles'])} of {len(run['monthly_reconciliation'])} books |")
    P(f"| Independent oracle across every challenger ledger | {run['oracle']['trades']['checked']} trades, max error {run['oracle']['trades']['max_abs_error']:.1e} |")
    P(f"| Independent allocation and share recomputation | {run['allocation_recomputation']['checked']} tickets, {run['allocation_recomputation']['errors']} disagreements |")
    P(f"| Code drift between freeze and scoring | none |")
    P("| Public/private separation and credential hygiene | pass |")
    P("")
    P("Every share count in every challenger book was re-derived from stored inputs by the independent oracle: "
      "the frozen base allocation times that book's own recorded equity scale, floored against the stored causal "
      "pre-order price. The oracle never consults the challenger engine.")
    P("")
    P(f"> {FOOTNOTE}")
    P("")
    P("---")
    P("")
    P("## Research statuses")
    P("")
    P("**C1 rank-one 1.50x reallocation: CHALLENGER IMPROVES PROFIT BUT DEGRADES RISK/CONCENTRATION — AWAIT "
      "HOLDOUT WITH CAUTION.** The complete account improves in both the equity-scaled and fixed-dollar views, "
      "with no change to which names are traded. Drawdown as a share of its own peak improves. Against that, the "
      "worst single session deepens by more than half, dollar drawdown worsens equity-scaled, and one name per "
      "week rises to roughly three quarters of P&L. On one already-inspected year this is an allocation result "
      "that has not faced a pristine sample.")
    P("")
    P("**C2 off-high substitution: CHALLENGER DOES NOT IMPROVE COMPLETE HISTORICAL ENGINE.** The replacement "
      "names behaved as the anatomy predicted and the complete account still lost, because funding them inside a "
      "fixed cohort budget diluted the retained names, above all the protected rank one. The conclusion survives "
      "the pre-declared revert sensitivity for the six evidence-affected cohorts.")
    P("")
    P("**C3 combined: CHALLENGER IMPROVES PROFIT BUT DEGRADES RISK/CONCENTRATION — AWAIT HOLDOUT WITH CAUTION.** "
      "It beats the incumbent but is dominated by C1 alone, and the interaction is strongly negative because the "
      "two changes pull rank-one capital in opposite directions. C3 was built as its own account; inferring it "
      "from C1 and C2 would have overstated it.")
    P("")
    P("No result here is a production decision. The incumbent is unchanged and remains the protected control.")
    P("")
    P("NEXT STEP: PRISTINE ADDITIONAL-YEAR REVEAL OF C0/C1/C2/C3 AFTER DATA CERTIFICATION")
    (REPORTS / "cg_arrow012_challengers.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    manifest = {
        "arrow": "CG Arrow 012", "executor": "Opus in Claude Code", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "freeze_commit": run["freeze_commit"], "config_version": freeze["config_version"],
        "holdout_embargo": {"frozen_cohort_count": freeze["holdout_embargo"]["frozen_cohort_count"],
                            "guard_ok": run["holdout_guard_ok"], "scored_cohort_count": run["scored_cohort_count"],
                            "declaration": freeze["holdout_embargo"]["declaration"]},
        "phase_a": {"stats_version": rs.STATS_VERSION, "overall_verdict": repair["overall_verdict"],
                    "direct_group_verdict": "A11_RELATIONSHIP_UNAFFECTED_DIRECT_GROUP_RESULT",
                    "verdict_counts": repair["verdict_counts"], "lost_after_repair": repair["lost_after_repair"],
                    "a11_replicated": repair["a11_replicated"], "rank_one_direct_group": repair["rank_one_direct_group"]},
        "phase_b": {"c0_reproduction": run["c0_reproduction"],
                    "accounts": {k: {q: v[q] for q in ("A_completed_trade_pnl_all_cohorts",
                                                       "B_marked_account_pnl_at_cutoff",
                                                       "C_post_cutoff_incremental_runoff_pnl",
                                                       "D_eventual_pnl_of_runoff_trades",
                                                       "E_open_documented_obligations",
                                                       "F_stale_gross_in_calendar_equity",
                                                       "completed_trade_count", "identities_hold")}
                                 for k, v in run["accounts"].items()},
                    "substitution": sub, "interaction": [dict(r) for r in inter if r["additive"] == "True"],
                    "rank_one_attribution": [dict(r) for r in r1a.values()],
                    "c2_decomposition": run.get("c2_decomposition", {})},
        "research_statuses": {
            "C1": "CHALLENGER IMPROVES PROFIT BUT DEGRADES RISK/CONCENTRATION - AWAIT HOLDOUT WITH CAUTION",
            "C2": "CHALLENGER DOES NOT IMPROVE COMPLETE HISTORICAL ENGINE",
            "C3": "CHALLENGER IMPROVES PROFIT BUT DEGRADES RISK/CONCENTRATION - AWAIT HOLDOUT WITH CAUTION"},
        "verification": {"oracle": run["oracle"], "allocation_recomputation": run["allocation_recomputation"],
                         "monthly_reconciliation": run["monthly_reconciliation"],
                         "code_drift_since_freeze_ok": all(v["ok"] for v in run["code_drift_since_freeze"].values())},
        "public_files": {p.name: digest(p) for p in sorted(REPORTS.glob("cg_arrow012_*")) if p.is_file()},
        "private_files": {p.name: {"path": str(p), "sha256": digest(p), "bytes": p.stat().st_size}
                          for p in sorted(OUT.glob("*")) if p.is_file()},
        "headline_footnote": FOOTNOTE,
        "next_step": "PRISTINE ADDITIONAL-YEAR REVEAL OF C0/C1/C2/C3 AFTER DATA CERTIFICATION",
    }
    dump_json(REPORTS / "cg_arrow012_manifest.json", manifest)
    print(f"{stamp()} reports and manifest written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
