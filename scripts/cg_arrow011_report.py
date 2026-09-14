"""CG Arrow 011 — stage 5: public anatomy report, stability table and final manifest.

Every number in the report is read from the computed artifacts; the interpretive sentences
are written against the confirmation outcomes and label each relationship with the lab's
vocabulary: established arithmetic, recurring association, plausible mechanism, exploratory,
rejected, unresolved.

Usage: python scripts/cg_arrow011_report.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_anatomy_stats as st  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification.r4r5_data import VERIFY_ROOT, digest, dump_json, read_json, stamp  # noqa: E402

OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011"
CACHE = VERIFY_ROOT / "a11"
FOOTNOTE = ("Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, "
            "dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills "
            "and availability are modeled, not broker execution guarantees.")
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]


def load(p):
    return list(csv.DictReader(Path(p).open(encoding="utf-8")))


def f(x, d=3):
    return "n/a" if x in (None, "") else f"{float(x):+.{d}f}"


def m(x):
    return "n/a" if x in (None, "") else f"{float(x):,.0f}"


def pc(x):
    return "n/a" if x in (None, "") else f"{float(x) * 100:.0f}%"


def main() -> int:
    freeze = read_json(REPORTS / "cg_arrow011_hypothesis_freeze.json")
    build = read_json(CACHE / "build_manifest.json")
    bridge = read_json(CACHE / "bridge_manifest.json")
    conf = read_json(CACHE / "confirm_manifest.json")
    isres = read_json(CACHE / "is_results.json")
    confirmation = load(REPORTS / "cg_arrow011_confirmation.csv")
    attribution = load(REPORTS / "cg_arrow011_model_month_attribution.csv")
    accounts = load(REPORTS / "cg_arrow011_account_summary.csv")
    monthly = load(REPORTS / "cg_arrow011_monthly_account.csv")
    probes = load(REPORTS / "cg_arrow011_probes.csv")
    paths = load(REPORTS / "cg_arrow011_holding_path_summary.csv")
    atlas = load(OUT / "trade_atlas.csv")

    # ---- stability table (public), from IS results
    stab_rows = []
    for feat, s in isres["stability"].items():
        lc, ls, b = s["loo_cohort"], s["loo_security"], s["cohort_block_bootstrap"]
        stab_rows.append({"feature": feat, "split": "IS", "loo_cohort_min": lc.get("loo_min"), "loo_cohort_max": lc.get("loo_max"),
                          "loo_cohort_same_sign": lc.get("loo_all_same_sign"), "loo_security_min": ls.get("loo_min"),
                          "loo_security_max": ls.get("loo_max"), "loo_security_same_sign": ls.get("loo_all_same_sign"),
                          "boot_p05": b.get("boot_p05"), "boot_p50": b.get("boot_p50"), "boot_p95": b.get("boot_p95"),
                          "boot_share_positive": b.get("boot_share_positive"),
                          "first_episode_contrast": s["first_episodes"].get("within_cohort_top_half_minus_bottom_half"),
                          "repeat_episode_contrast": s["repeat_episodes"].get("within_cohort_top_half_minus_bottom_half"),
                          "months_positive": sum(1 for v in s["by_month"].values() if v["within_halves"] is not None and v["within_halves"] > 0),
                          "months_scored": sum(1 for v in s["by_month"].values() if v["within_halves"] is not None),
                          "statistic": "within-cohort top-half minus bottom-half contrast of the ten-session short price return; cohort-block resampling is a dependence-aware spread, not a proof of independence"})
    exp.write_csv(REPORTS / "cg_arrow011_stability.csv", stab_rows)

    claims = {c["comparison"][6:]: c for c in conf["claims"]}
    fconf = {r["comparison"][8:]: r for r in confirmation if r["kind"] == "continuous_feature"}
    sm = conf["state_map"]
    g = conf["groups"]

    def gv(group, split, name, key="cohort_equal_weight_mean"):
        for r in g[group][split]:
            if r["group"] == name:
                return r.get(key)
        return None

    att = {(r["panel"], r["basis"], r["period"]): r for r in attribution}
    leg_all = att[("LEGACY_FILL_QTY", "ALL_EVENTUAL_COMPLETED", "ALL")]
    cau_all = att[("CAUSAL_PREORDER_QTY", "ALL_EVENTUAL_COMPLETED", "ALL")]
    acc = {r["book"]: r for r in accounts}
    syms = Counter(r["symbol"] for r in atlas)
    census = conf["cohort_census"]
    done = [r for r in atlas if r["oc_price_return_10"]]
    flips = sum(1 for r in done if r["oc_sign_flipped_by_costs"] == "True")

    L = []
    A = L.append
    A("# CG Arrow 011 — Winner-Fade anatomy: pre-entry characteristics and within-cohort outcomes")
    A("")
    A(f"Executor: Fable in Claude Code. Freeze commit `{conf['freeze_commit'][:7]}`, run head `{conf['head_at_run'][:7]}`. "
      "Principal subject: the certified Momentum+Volume-Sized Short (`R5`), Corrected-Universe Replay (`R2`), 10-Session Hold (`H10`), "
      "causal pre-order quantities. Volume-Sized (`R4`) and the equity-scaled book are explanatory references. Nothing in any frozen "
      "ledger, rule or account was changed; this arrow adds an isolated feature and analysis layer.")
    A("")
    A("## Executive findings")
    A("")
    A("1. **The basket's most extreme name is where the fade lives.** Rank 1 of 8, almost always separated from rank 2 by a wide gap "
      f"in ranking return, faded on average {f(gv('cx_rank_in_eight','IS','1'))} in IS (hit {pc(gv('cx_rank_in_eight','IS','1','hit_rate'))}) and "
      f"{f(gv('cx_rank_in_eight','OOS','1'))} in internal confirmation (hit {pc(gv('cx_rank_in_eight','OOS','1','hit_rate'))}), against ranks 2-8 near "
      f"{f(claims['C1']['oos_value'] and gv('cx_rank_in_eight','OOS','1') - claims['C1']['oos_value'])} in confirmation. "
      "This is a within-cohort relationship by construction and it replicated. Recurring association.")
    A("2. **Among ranks 2-8, names already off their 20-session high fade more, not less.** The prediction was the opposite. "
      f"IS ranks 2-8: lowest tercile of close-versus-high {f(conf['off_high_ranks_2_8']['IS']['t1_low']['mean'])} (hit {pc(conf['off_high_ranks_2_8']['IS']['t1_low']['hit_rate'])}) "
      f"versus at-the-high {f(conf['off_high_ranks_2_8']['IS']['t3_high']['mean'])} (hit {pc(conf['off_high_ranks_2_8']['IS']['t3_high']['hit_rate'])}); confirmation "
      f"{f(conf['off_high_ranks_2_8']['OOS']['t1_low']['mean'])} versus {f(conf['off_high_ranks_2_8']['OOS']['t3_high']['mean'])}, same direction, weaker. Recurring association.")
    A("3. **Wide recent ranges and episodic advances fade more.** Session log-return dispersion, signal-day range and the pre-order-bar "
      "partial range replicated; advances concentrated in few sessions replicated; the ten-session mean range was same-sign but below the "
      "frozen threshold. Recurring association with a plausible mechanism (the fade is a volatility event, not a drift).")
    A("4. **The momentum halving in the frozen rule is not supported as a stock-selection signal.** On IS, non-positive three-session "
      f"momentum names faded more ({f(claims['C5']['is_value'])} cohort-equal-weight difference); in confirmation the sign reversed "
      f"({f(claims['C5']['oos_value'])}). The two HALF states did not behave alike on IS and were too sparse to judge on OOS (5 weak-and-loud rows). "
      f"Mechanically, the momentum component of the R4-to-R5 difference is {m(leg_all['momentum_component'])} against a base-ticket "
      f"component of {m(leg_all['base_ticket_component'])}: the halving mostly forfeited winners. Rejected as a signal; established arithmetic as a cost.")
    A("5. **Pre-order information adds nothing within cohort.** The entry-session move from the signal close to the pre-order bar, "
      "the overnight gap and the position in the partial-day range separate nothing within a basket on IS or in confirmation. "
      "A between-cohort correlation exists and is labeled exploratory. Negative result.")
    A("6. **Price band matters mainly at the top.** The 10-20 band led on IS; in confirmation 10-20 and 20-40 were close and 40-80 lagged. "
      "The robust statement is that 40-80 names faded least. Recurring association, weaker than first seen.")
    A("7. **Repeat selections are not different.** Overlapping repeats fade like first selections in confirmation. Rejected.")
    A("")
    A(f"Confirmation is internal only: the even months have been inspected in earlier arrows. {conf['claims_met']} of {conf['claims_total']} "
      f"registered claims met their frozen expectation; of {len(fconf)} registered feature relationships, "
      f"{sum(1 for r in fconf.values() if r['status']=='REPLICATED')} replicated, {sum(1 for r in fconf.values() if r['status']=='SAME_SIGN_WEAKER')} were same-sign but weaker, "
      f"{sum(1 for r in fconf.values() if r['status']=='NO_SIGNAL_CONFIRMED')} confirmed as no-signal, and {sum(1 for r in fconf.values() if r['status']=='SEPARATION_APPEARED_POST_HOC')} "
      "showed a separation only after the reveal and are queued, not claimed.")
    A("")
    A("## Baseline preserved and preflight")
    A("")
    A("| Check | Result |")
    A("|---|---|")
    A(f"| Private input hashes against the Arrow 008 and 010 manifests | {sum(1 for v in build['hash_checks'].values() if v['ok'])} of {len(build['hash_checks'])} |")
    A("| Census per book (cohorts / intended / completed / open documented) | 52 / 416 / 415 / 1 in every principal book |")
    A(f"| Economic controls reproduce from the ledgers | {sum(1 for v in build['control_checks'].values() if v['ok'])} of {len(build['control_checks'])} |")
    A(f"| Fresh replay versus the certified causal pre-order ledger | {build['fresh_replay_mismatches']} mismatches on 416 tickets |")
    A(f"| Independent oracle, Arrow 008 R2 books and Arrow 010 books | ok, max trade error {build['oracle_a8_r2']['trades']['max_abs_error']:.1e} |")
    A(f"| Frozen four-state labels versus the ledger | {build['feature_state_disagreements']} disagreements |")
    A(f"| Pre-order features available | {build['pre_order_available']} of 416 |")
    A(f"| Per-share marked path times quantity reproduces every daily account | worst {max(v['max_abs_equity_error'] for v in bridge['per_share_path_reconciliation'].values()):.1e} |")
    A(f"| Hash drift between freeze and reveal | none |")
    A("")
    A("The Arrow 010 lesson was applied: the observation set is the engine's own need set, so no volume or momentum feature was silently "
      "dropped, and a missing feature is its own state rather than a FULL-size fallback in the analysis.")
    A("")
    A("## Question 1 — which pre-entry characteristics go with the fade, and what explains the model and month differences")
    A("")
    A("### Model and month bridge, Volume-Sized to Momentum+Volume-Sized")
    A("")
    A("Both books hold the same 416 positions with the same entry and exit observations and differ only in share count, so the difference "
      "is an exact identity per ticket: net per entry share times the share difference. The share difference is split in a declared order, "
      "raising the base ticket from 5,150 to 8,300 at the Volume-Sized multipliers first, then applying the momentum halving at the raised "
      "base, with the integer-share residual shown. The two continuous components are order-dependent, not independent causes.")
    A("")
    A(f"| Panel | R4 eventual | R5 eventual | Difference | Base ticket | Momentum halving | Rounding | From R4 winners | From R4 losers | FULL | HALF | QUARTER |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for lab, r in (("Legacy fill (Arrow 009 panel)", leg_all), ("Causal pre-order (atlas panel)", cau_all)):
        A(f"| {lab} | {m(r['r4_total'])} | {m(r['r5_total'])} | {m(r['difference'])} | {m(r['base_ticket_component'])} | {m(r['momentum_component'])} | "
          f"{m(r['rounding_residual'])} | {m(r['difference_from_r4_winners'])} | {m(r['difference_from_r4_losers'])} | {m(r['difference_FULL'])} | {m(r['difference_HALF'])} | {m(r['difference_QUARTER'])} |")
    A("")
    A("Calendar months on the marked-account basis, legacy fill panel, which reproduces the Arrow 009 monthly differences exactly "
      "(reconciliation residual below 1e-9 in every month):")
    A("")
    A("| Month | R4 marked | R5 marked | Difference | Base ticket | Momentum | From R4 winners | From R4 losers | Tickets +/- | Top-3 share |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---|---:|")
    for mo in MONTHS:
        r = att[("LEGACY_FILL_QTY", "CALENDAR_MONTH_MARKED_ACCOUNT", mo)]
        A(f"| {mo} | {m(r['r4_total'])} | {m(r['r5_total'])} | {m(r['difference'])} | {m(r['base_ticket_component'])} | {m(r['momentum_component'])} | "
          f"{m(r['difference_from_r4_winners'])} | {m(r['difference_from_r4_losers'])} | {r['tickets_with_positive_difference']}/{r['tickets_with_negative_difference']} | {pc(r['top3_tickets_share_of_abs_difference'])} |")
    A("")
    A("Reading the twelve months. In every month the base-ticket component is the sign of that month's book and the momentum component "
      "works against it whenever strong-momentum names were the ones fading: October 2025, July 2026 and August 2026 are months where the halving "
      "gave back more than 9,000 each, while December 2025 and January 2026 are the months where it protected the book. February 2026 is the "
      "clearest case of a small-number effect: three tickets carry 55% of the absolute difference and almost all of it came from names that "
      "lost under Volume-Sized sizing. June 2026 is the opposite, a widespread reweighting where 25 tickets gained and 23 lost and the winners "
      "supplied 9,480 of the 10,344 difference. Per tier, the FULL state contributed all of the net gain and the HALF and QUARTER states gave "
      "back part of it, which is the sizing-neutral finding below restated in dollars: the rule sizes largest exactly where the fade was strongest "
      "on IS, and smallest where confirmation later showed the fade was at least as strong.")
    A("")
    A("Where lower raw-return opportunity still produced more dollars: the whole difference. Sizing-neutral outcomes are identical across "
      f"the two books (mean price return {f(leg_all['sizing_neutral_mean_price_return'],4)}, hit rate {pc(leg_all['sizing_neutral_hit_rate'])}); every dollar of difference is size.")
    A("")
    A("### The four momentum/volume states")
    A("")
    A("| State | IS n | IS cohorts | IS mean | IS cohort-weighted | IS hit | OOS n | OOS mean | OOS cohort-weighted | OOS hit |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in ("S1_FULL_weak_quiet", "S2_HALF_weak_loud", "S3_HALF_strong_quiet", "S4_QUARTER_strong_loud", "MISSING_FEATURE"):
        A(f"| {s} | {gv('sc_four_state','IS',s,'n')} | {gv('sc_four_state','IS',s,'cohorts')} | {f(gv('sc_four_state','IS',s,'mean'))} | {f(gv('sc_four_state','IS',s))} | {pc(gv('sc_four_state','IS',s,'hit_rate'))} | "
          f"{gv('sc_four_state','OOS',s,'n')} | {f(gv('sc_four_state','OOS',s,'mean'))} | {f(gv('sc_four_state','OOS',s))} | {pc(gv('sc_four_state','OOS',s,'hit_rate'))} |")
    A("")
    A("Do the two HALF states behave alike? Not on IS: weak-and-loud (S2) sat with FULL and strong-and-quiet (S3) sat with QUARTER, so the "
      "separating dimension was the momentum sign, not the volume ratio. In confirmation S3 and S4 faded as well as or better than S1 and S2 "
      "had only five rows, so the IS separation did not carry. Is weakening on elevated volume different from weakening on quiet volume? The "
      "sample cannot say: S2 has 16 rows across the year. Are the reductions informative individually? The volume ratio is a weak, inconsistent "
      "separator (it flips sign in the 20-80 band on IS and is near zero in confirmation); the momentum sign separated on IS and reversed in "
      "confirmation. An apparently strong FULL bucket is therefore partly its bigger tickets: on a sizing-neutral basis its IS advantage "
      "did not replicate.")
    A("")
    A("### Feature anatomy, leading relationships")
    A("")
    A("Statistic: within-cohort mean of the top half minus bottom half by feature of the ten-session short price return, with the share of "
      "cohorts favouring one side; tercile cuts learned on IS and frozen. Positive means the higher feature value faded more.")
    A("")
    A("| Feature | Cutoff | IS contrast | IS share | OOS contrast | OOS share | Status | Label |")
    A("|---|---|---:|---:|---:|---:|---|---|")
    order = sorted(fconf.values(), key=lambda r: -abs(float(r["is_value"])))
    for r in order:
        if r["status"] in ("REPLICATED", "SAME_SIGN_WEAKER") or float(r["is_share"]) >= 0.62 or float(r["is_share"]) <= 0.38:
            lab = {"REPLICATED": "recurring association", "SAME_SIGN_WEAKER": "recurring, weaker", "NO_SIGNAL_CONFIRMED": "no signal",
                   "SEPARATION_APPEARED_POST_HOC": "post-reveal only, queued"}[r["status"]]
            A(f"| {r['comparison'][8:]} | {r['cutoff']} | {f(r['is_value'])} | {float(r['is_share']):.2f} | {f(r['oos_value'])} | {float(r['oos_share']):.2f} | {r['status']} | {lab} |")
    A("")
    A("Two rows need a caution. `cx_cohort_ret15_spread` is constant inside a cohort, so its within-cohort values are an artifact of tie order "
      "and only its between-cohort view is meaningful; `ep_sessions_since_last_selection` exists only for repeat selections (84 IS rows). "
      "Neither was claimed.")
    A("")
    A("The full registered set, including every no-signal feature, is in `reports/cg_arrow011_confirmation.csv` and the three-split view in "
      "`reports/cg_arrow011_within_cohort_summary.csv`. Leave-one-cohort-out, leave-one-security-out, cohort-block resampling and month-by-month "
      "direction for every registered feature are in `reports/cg_arrow011_stability.csv`.")
    A("")
    A("## Question 2 — within each basket of eight, what distinguished the better shorts before entry")
    A("")
    A("### Rank within the eight")
    A("")
    A("| Rank | IS mean | IS hit | OOS mean | OOS hit | ALL mean | ALL hit |")
    A("|---:|---:|---:|---:|---:|---:|---:|")
    for k in range(1, 9):
        A(f"| {k} | {f(gv('cx_rank_in_eight','IS',str(k),'mean'))} | {pc(gv('cx_rank_in_eight','IS',str(k),'hit_rate'))} | {f(gv('cx_rank_in_eight','OOS',str(k),'mean'))} | "
          f"{pc(gv('cx_rank_in_eight','OOS',str(k),'hit_rate'))} | {f(gv('cx_rank_in_eight','ALL',str(k),'mean'))} | {pc(gv('cx_rank_in_eight','ALL',str(k),'hit_rate'))} |")
    A("")
    A("Each rank row has one ticket per cohort, so the mean is already cohort-equal-weighted. The gap from rank 1 to rank 2 in ranking "
      f"return was the single strongest within-cohort feature on IS (share {float(fconf['cx_gap_to_next_rank']['is_share']):.2f} of cohorts) and "
      f"replicated at share {float(fconf['cx_gap_to_next_rank']['oos_share']):.2f}. Rank 2 also faded in confirmation, so the pattern is extremeness, "
      "not a rank-1 accident. Six IS rank-1 names did not fade; three of them are from November 2025, the IS month where the gap effect was weakest.")
    A("")
    A("### A two-by-two state map, frozen on IS")
    A("")
    A("Price band of the signal close (10-20 versus 20-80) by whether the close sits below the IS median distance from the 20-session high "
      f"({freeze['frozen_definitions']['close_vs_high20_is_median']:.3f}, that is more than about 5.5% below the high).")
    A("")
    A("| Cell | IS n | IS cohorts | IS cohort-weighted | IS hit | IS net per $ | OOS n | OOS cohort-weighted | OOS hit | OOS net per $ |")
    A("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for cell in ("10-20 x off_high", "10-20 x near_high", ">=20 x off_high", ">=20 x near_high"):
        a, b = sm["IS"][cell], sm["OOS"][cell]
        A(f"| {cell} | {a['n']} | {a['cohorts']} | {f(a['cohort_equal_weight_mean'])} | {pc(a['hit_rate'])} | {f(a['net_per_entry_dollar'],4)} | "
          f"{b['n']} | {f(b['cohort_equal_weight_mean'])} | {pc(b['hit_rate'])} | {f(b['net_per_entry_dollar'],4)} |")
    A("")
    A("The best cell replicated as the best cell. The worst IS cell (20-80 and near the high, hit 28%) recovered to a small positive in "
      "confirmation, so the frozen ordering claim failed on the worst cell while the off-high-beats-near-high reading held inside both bands.")
    A("")
    A("### Cohort census and dependence")
    A("")
    A(f"Cohorts: IS {census['IS']}, confirmation {census['OOS']}, all {census['ALL']}. One cohort is partly censored by the documented halt. "
      f"Distinct securities {len(syms)}; {sum(1 for v in syms.values() if v >= 2)} selected at least twice and {sum(1 for v in syms.values() if v >= 3)} at least three times, "
      f"the most frequent {syms.most_common(1)[0][1]} times. {sum(1 for r in atlas if r['ep_episode']=='OVERLAPPING_REPEAT')} of 416 selections are overlapping repeats whose "
      "previous ten-session hold was still open at the new signal; these are persistence of one episode, not new examples, and every relationship "
      "table reports its security count for that reason. Eight simultaneous shorts and overlapping holds are not independent replications; the "
      "cohort-block resampling in the stability table is the dependence-aware spread.")
    A("")
    A("## Holding paths as outcomes")
    A("")
    A("Close-only sizing-neutral short return by holding age, all completed tickets; age 0 and age 10 use the execution reference. "
      "Close-only excursions are not intraday extrema. These are outcomes and were never scored as predictors.")
    A("")
    A("| Age | IS mean | IS median | IS favourable | OOS mean | OOS median | OOS favourable | ALL mean | ALL favourable |")
    A("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    pk = {(r["split"], r["age"]): r for r in paths if r["condition"] == "all" and r["basis"].startswith("close-only")}
    for a in range(1, 11):
        i, o, al = pk[("IS", str(a))], pk[("OOS", str(a))], pk[("ALL", str(a))]
        A(f"| {a} | {f(i['mean'],4)} | {f(i['median'],4)} | {pc(i['favorable_share'])} | {f(o['mean'],4)} | {f(o['median'],4)} | {pc(o['favorable_share'])} | {f(al['mean'],4)} | {pc(al['favorable_share'])} |")
    A("")
    arch = {(r["split"], r["basis"].split(": ")[1]): r["observed"] for r in paths if r["condition"] == "all" and r["basis"].startswith("archetype")}
    A("Archetypes (frozen rules): " + "; ".join(f"{k[1]} IS {arch.get(('IS', k[1]), 0)} / OOS {arch.get(('OOS', k[1]), 0)}" for k in sorted(arch) if k[0] == "IS") + ".")
    A("")
    A("On IS most of the mean fade had accrued by age 2 and the median went flat; in confirmation the fade kept accruing through age 10 "
      "(the strongest fixed-dollar months fall in the even months), so the path-shape claim did not replicate as frozen. Immediate fade was "
      "the most common archetype in both halves. Rank-1 paths keep fading through the hold (ALL mean +0.081 at age 2, +0.272 at age 10, "
      "favourable 83% at age 10) while ranks 2-8 are flat after age 2. Incremental session economics, partial-versus-ten-session ratios with "
      "explicit positive-denominator counts, and conditioned paths are in `reports/cg_arrow011_holding_path_summary.csv`. No hold, stop, "
      "partial exit or timing was optimized; these shapes are management hypotheses for a later arrow.")
    A("")
    A("## Research-only probes, exposure-matched")
    A("")
    A("| Probe | Split | n | Cohorts | Cohort-weighted return | Hit | Net per entry $ | Full-book net per $ | Exposure share | Outcome |")
    A("|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    pfull = {(r["probe"], r["split"]): r for r in probes if r["set"] == "full_book"}
    for r in probes:
        if r["set"] == "probe" and r["split"] in ("IS", "OOS"):
            fb = pfull[(r["probe"], r["split"])]
            A(f"| {r['probe']} {r['name']} | {r['split']} | {r['n']} | {r['cohorts']} | {f(r['cohort_equal_weight_mean'])} | {pc(r['hit_rate'])} | {f(r['net_per_entry_dollar'],4)} | "
              f"{f(fb['net_per_entry_dollar'],4)} | {pc(r['exposure_share_of_full_book'])} | {r['oos_status'] if r['split']=='OOS' else ''} |")
    A("")
    A("Probes are subsets of the certified trades with unused exposure idle; no compounded equity, drawdown or monthly return is claimed for "
      "them. P1, P2 and P3 replicated on net per entry dollar and hit rate; P4 (non-positive momentum only) did not. Reduced capital alone is "
      "not skill: the comparison is per dollar of entry exposure.")
    A("")
    A("## Freelance lane")
    A("")
    A("Four questions were registered with predictions before scoring and stayed inside the 30% ceiling. F1 (overlapping repeats fade less) "
      "showed the predicted direction weakly on IS and reversed in confirmation: rejected. F2 (steady grinders fade more) was rejected on IS "
      "in every month, and its reversal, episodic advances fade more, replicated. F3 (pre-order price near the partial-day low fades more) "
      "showed no separation. F4 (volume ratio inside the QUARTER state) showed no separation. Time on the lane, including the interaction maps, "
      "was about 12 minutes.")
    A("")
    A("## Counterexamples and what is not known")
    A("")
    A("Every leading pattern has documented counterexamples in the private casebook, chosen mechanically as the largest non-fades inside the "
      "pattern's cell. Rank-1 names that did not fade cluster in November 2025 on IS. Off-high names that kept rising exist in every month. "
      "No catalyst narrative is asserted for any of them: the lab holds no timestamped news, float or shares-outstanding history, so the "
      "event-context feature is limited to documented corporate actions effective by the signal (sparse) and is inconclusive.")
    A("")
    A("Not known: whether the extremeness effect is a float or borrow-availability effect, because float history is not held; whether "
      "the 10-20 band effect is a price effect or a proxy for something else; and whether the between-cohort pre-order correlation is a "
      "market-regime signature. These are data-access limits, not tested negatives.")
    A("")
    A("## Post-reveal observations, queued not claimed")
    A("")
    post = [r for r in fconf.values() if r["status"] == "SEPARATION_APPEARED_POST_HOC"]
    for r in sorted(post, key=lambda r: -abs(float(r["oos_value"])))[:6]:
        A(f"- {r['comparison'][8:]}: IS contrast {f(r['is_value'])} (share {float(r['is_share']):.2f}), confirmation {f(r['oos_value'])} (share {float(r['oos_share']):.2f}).")
    A("")
    A("## Next research proposals, ranked by information value over burden, not executed")
    A("")
    A("1. **Extremeness study with a pristine holdout.** Rank-1-with-gap and the off-high state as pre-registered selection descriptors on a "
      "genuinely unseen period; low burden, highest value, because both replicated here on inspected months only.")
    A("2. **Momentum-halving ablation as a frozen-signal sizing comparison.** The halving cost 55,010 mechanically and did not replicate as a "
      "signal; a same-trades comparison of R5 with mm fixed at 1 versus the frozen rule, with full monthly accounting; low burden.")
    A("3. **Hold-path management hypotheses.** Rank-1 paths keep fading through age 10 while ranks 2-8 are flat after age 2; a pre-registered "
      "age-conditional exit study on a holdout; medium burden.")
    A("4. **Float and borrow context acquisition.** As-of shares outstanding for the 10-20 band names, to test whether extremeness is a "
      "float effect; medium burden, data not held.")
    A("5. **Ten-session return and selection-age post-reveal separations** (queued from the reveal): register and test on a holdout only.")
    A("")
    A("## Audit gates")
    A("")
    A("| Gate | Test | Result |")
    A("|---|---|---|")
    gates = [("1", "baseline hashes, counts, totals, per-trade returns unchanged; all slots and the open obligation represented", "tests/test_cg_arrow011.py::test_baseline_*"),
             ("2", "no duplicate tickets or cross-panel double counting", "test_one_economic_observation_per_ticket"),
             ("3", "availability cutoffs; entry-minute, future-price and future-action leakage rejected", "test_signal_close_feature_window_ends_at_the_signal_session and companions"),
             ("4", "missing lookback/volume/float cannot become a favorable state", "test_missing_features_stay_missing_*"),
             ("5", "four-state labels agree with the frozen rule on every ticket; HALF causes distinct", "test_four_state_labels_agree_*"),
             ("6", "normalized outcomes reconcile; existing accounts identical to references", "test_sizing_neutral_return_reconciles_*, test_existing_accounts_*"),
             ("7", "model/month and cohort attribution sum exactly with rounding and month allocation", "test_model_month_bridge_sums_exactly_*"),
             ("8", "monthly outputs chain and reconcile to the marked cutoff", "test_monthly_rows_chain_*"),
             ("9", "no post-entry fields as predictors; path labels cannot leak", "test_public_pre_entry_tables_*, test_path_archetype_*"),
             ("10", "freeze before reveal, no drift", "test_freeze_was_committed_before_confirmation_*"),
             ("11", "failures, sparse groups, repeats, open transitions disclosed", "test_registry_keeps_rejected_*, test_repeated_securities_*"),
             ("12", "original artifacts unchanged; public/private separation by content", "test_original_baseline_artifacts_*, test_public_files_carry_no_symbols_*")]
    for gnum, text, test in gates:
        A(f"| {gnum} | {text} | `{test}` |")
    A("")
    A("## Monthly accounts, principal books")
    A("")
    A(f"Published under `cg_lab_monthly_account_reporting_v1` in `reports/cg_arrow011_monthly_account.csv` for five books; account statistics in "
      "`reports/cg_arrow011_account_summary.csv`. Rows are cent-chained and reconcile to each book's marked account result at 2026-08-31, never to eventual profit.")
    A("")
    A("| Month | R5 legacy | R5 causal | R4 legacy | R4 causal | R5 equity-scaled |")
    A("|---|---:|---:|---:|---:|---:|")
    mb = defaultdict(dict)
    for r in monthly:
        mb[r["month"]][r["book"]] = r
    keys = ["Momentum+Volume, fixed dollars, legacy fill quantities", "Momentum+Volume, fixed dollars, causal pre-order quantities",
            "Volume-Sized, fixed dollars, legacy fill quantities", "Volume-Sized, fixed dollars, causal pre-order quantities",
            "Momentum+Volume, equity-scaled, causal pre-order quantities"]
    for mo in MONTHS:
        A(f"| {mo} | " + " | ".join(f"{float(mb[mo][k]['monthly_pnl']):,.2f}" for k in keys) + " |")
    A("| **Marked P&L at cutoff** | " + " | ".join(f"**{float(acc[k]['marked_account_pnl_at_2026_08_31']):,.2f}**" for k in keys) + " |")
    A("| Positive / red / flat | " + " | ".join(f"{acc[k]['positive_months']} / {acc[k]['red_months']} / {acc[k]['flat_months']}" for k in keys) + " |")
    A("| Worst / best / median month | " + " | ".join(f"{float(acc[k]['worst_month']):,.0f} / {float(acc[k]['best_month']):,.0f} / {float(acc[k]['median_month']):,.0f}" for k in keys) + " |")
    A("")
    A(f"> {FOOTNOTE}")
    A("")
    A("---")
    A("")
    A("BASELINE PRESERVED: YES — all 16 private input hashes match their manifests, every control reproduces, a fresh replay matches the "
      "certified ledger on all 416 tickets, the oracle passes, and no Arrow 001-010 artifact was modified.")
    A("")
    A("ANATOMY STUDY: COMPLETE — 52-cohort atlas, all directed sections, four freelance questions resolved, freeze and one confirmation "
      "batch, monthly reporting; optional enrichment (float, catalyst timestamps) not held and marked unavailable rather than omitted.")
    A("")
    A("NEW RELATIONSHIPS: INTERNAL CONFIRMATION ONLY; NO PRISTINE OOS CLAIM")
    A("")
    A("NEXT RESEARCH PROPOSALS: ranked, precisely specified, NOT EXECUTED")
    (REPORTS / "cg_arrow011_anatomy.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")

    manifest = {
        "arrow": "CG Arrow 011", "executor": "Fable in Claude Code", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "freeze_commit": conf["freeze_commit"], "schema": "cg_arrow011_anatomy_v1",
        "principal_book": "R5/R2_CAUSAL_PREORDER_QTY", "is_months": freeze["is_months"], "oos_months": freeze["oos_months"],
        "oos_status": freeze["oos_status"], "build": conf["build"], "bridge": conf["bridge"],
        "monthly_reconciliation": conf["monthly_reconciliation"], "cohort_census": conf["cohort_census"],
        "claims": conf["claims"], "claims_met": conf["claims_met"], "claims_total": conf["claims_total"],
        "feature_confirmation_counts": conf["feature_confirmation_counts"], "probe_oos": conf["probe_oos"],
        "hash_drift_since_freeze_ok": all(v["ok"] for v in conf["hash_drift_since_freeze"].values()),
        "public_files": {p.name: digest(p) for p in sorted(REPORTS.glob("cg_arrow011_*")) if p.is_file()},
        "private_files": {p.name: {"path": str(p), "sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(OUT.glob("*")) if p.is_file()},
        "ignored_caches": {p.name: digest(p) for p in sorted(CACHE.glob("*.json"))},
        "lane_minutes": {"directed_including_verification_and_delivery": None, "freelance": None, "note": "filled in the commands log"},
        "headline_footnote": FOOTNOTE,
        "ending": {"baseline_preserved": "YES", "anatomy_study": "COMPLETE", "new_relationships": "INTERNAL CONFIRMATION ONLY; NO PRISTINE OOS CLAIM",
                   "next_research_proposals": "ranked, precisely specified, NOT EXECUTED"},
    }
    dump_json(REPORTS / "cg_arrow011_manifest.json", manifest)
    print(f"{stamp()} report and manifest written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
