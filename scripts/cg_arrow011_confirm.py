"""CG Arrow 011 — stage 4: one confirmation batch on OOS, then the all-year retrospective.

Requires reports/cg_arrow011_hypothesis_freeze.json to be committed. Checks that the atlas and
the analysis code still match the frozen hashes, applies every frozen definition to the OOS
cohorts exactly once, reports every registered comparison including non-replications, then
completes the all-year cohort atlas and the public summaries. Nothing is re-fitted.

Usage: python scripts/cg_arrow011_confirm.py
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_anatomy_stats as st  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification.r4r5_data import VERIFY_ROOT, digest, dump_json, read_json, stamp  # noqa: E402

OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011"
ATLAS = OUT / "trade_atlas.csv"
PATHS = OUT / "trade_path_atlas.csv"
CACHE = VERIFY_ROOT / "a11"
FREEZE = REPORTS / "cg_arrow011_hypothesis_freeze.json"
PRIMARY = "oc_price_return_10"
SECOND = "oc_net_per_entry_dollar"
DOLLAR = "lens_fixed_causal_net"
SCALED = "lens_equity_scaled_net"
LOG: list[str] = []
T0 = time.monotonic()


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def load(path):
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def fmt(x, d=3):
    return "n/a" if x is None else f"{x:+.{d}f}"


def cew(rows, outcome):
    by = defaultdict(list)
    for r in rows:
        v = st.num(r.get(outcome))
        if v is not None:
            by[r["cohort_id"]].append(v)
    return statistics.mean(statistics.mean(v) for v in by.values()) if by else None


def subset_stats(rows, label):
    v = [st.num(r[PRIMARY]) for r in rows if st.num(r.get(PRIMARY)) is not None]
    expo = sum(st.num(r["oc_entry_exposure_dollars"]) or 0 for r in rows)
    net = sum(st.num(r[DOLLAR]) or 0 for r in rows)
    return {"subset": label, "n": len(rows), "completed": len(v), "cohorts": len({r["cohort_id"] for r in rows}),
            "securities": len({r["symbol"] for r in rows}),
            "mean_price_return": statistics.mean(v) if v else None, "median_price_return": statistics.median(v) if v else None,
            "hit_rate": (sum(1 for x in v if x > 0) / len(v)) if v else None, "cohort_equal_weight_mean": cew(rows, PRIMARY),
            "entry_exposure": expo, "fixed_dollar_net": net, "net_per_entry_dollar": (net / expo) if expo else None}


def probe_mask(pid, r, med_off):
    band = r["sc_signal_close_band"]
    off = st.num(r.get("sc_close_vs_high20"))
    ret3 = st.num(r.get("sc_ret3"))
    if pid == "P1":
        return r["cx_rank_in_eight"] == "1"
    if pid == "P2":
        return band == "10-20" and off is not None and off < med_off
    if pid == "P3":
        return not (band in ("20-40", "40-80") and off is not None and off >= med_off)
    if pid == "P4":
        return ret3 is not None and ret3 <= 0
    raise KeyError(pid)


def path_table(rows, prows, split, condition):
    ids = {r["ticket_id"] for r in rows}
    sub = [p for p in prows if p["ticket_id"] in ids]
    out = []
    for a in range(0, 11):
        vals = [st.num(p[f"age{a:02d}_short_return"]) for p in sub]
        obs = sorted(v for v in vals if v is not None)
        out.append({"split": split, "condition": condition, "age": a, "tickets": len(sub), "observed": len(obs),
                    "stale_or_absent": len(vals) - len(obs),
                    "mean": statistics.mean(obs) if obs else None, "median": statistics.median(obs) if obs else None,
                    "p10": obs[int(0.1 * len(obs))] if obs else None, "p25": obs[len(obs) // 4] if obs else None,
                    "p75": obs[(3 * len(obs)) // 4] if obs else None, "p90": obs[min(len(obs) - 1, int(0.9 * len(obs)))] if obs else None,
                    "favorable_share": (sum(1 for v in obs if v > 0) / len(obs)) if obs else None,
                    "basis": "close-only sizing-neutral short return at each age; age 0 and 10 use the execution reference"})
    arch = Counter(p["path_archetype"] for p in sub)
    for k, v in sorted(arch.items()):
        out.append({"split": split, "condition": condition, "age": None, "tickets": len(sub), "observed": v,
                    "stale_or_absent": None, "mean": None, "median": None, "p10": None, "p25": None, "p75": None, "p90": None,
                    "favorable_share": None, "basis": f"archetype count: {k}"})
    for a in range(1, 11):
        d = [st.num(p[f"age{a:02d}_short_return"]) - st.num(p[f"age{a-1:02d}_short_return"]) for p in sub
             if st.num(p[f"age{a:02d}_short_return"]) is not None and st.num(p[f"age{a-1:02d}_short_return"]) is not None]
        out.append({"split": split, "condition": condition, "age": a, "tickets": len(sub), "observed": len(d),
                    "stale_or_absent": len(sub) - len(d), "mean": statistics.mean(d) if d else None,
                    "median": statistics.median(d) if d else None, "p10": None, "p25": None, "p75": None, "p90": None,
                    "favorable_share": (sum(1 for v in d if v > 0) / len(d)) if d else None,
                    "basis": f"incremental {a-1}->{a} session return"})
    return out


def main() -> int:
    freeze = read_json(FREEZE)
    isres = read_json(CACHE / "is_results.json")
    build = read_json(CACHE / "build_manifest.json")
    bridge = read_json(CACHE / "bridge_manifest.json")
    # ------------------------------------------------------------ hash gate before the reveal
    drift = {}
    for name, h in freeze["input_hashes"].items():
        p = {"trade_atlas.csv": ATLAS, "trade_path_atlas.csv": PATHS, "is_results.json": CACHE / "is_results.json",
             "build_manifest.json": CACHE / "build_manifest.json", "arrow008_manifest": REPORTS / "cg_arrow008_manifest.json",
             "arrow010_manifest": REPORTS / "cg_arrow010_manifest.json"}[name]
        drift[name] = {"frozen": h, "now": digest(p), "ok": digest(p) == h}
    for path, h in freeze["code_hashes"].items():
        drift[path] = {"frozen": h, "now": digest(REPO_ROOT / path), "ok": digest(REPO_ROOT / path) == h}
    bad = [k for k, v in drift.items() if not v["ok"]]
    committed = subprocess.run(["git", "log", "-1", "--format=%H", "--", str(FREEZE)], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    note(f"freeze committed at {committed[:7]}; hash drift since freeze: {bad}")
    if bad or not committed:
        dump_json(CACHE / "confirm_manifest.json", {"blockers": [f"drift {bad}", f"freeze committed={bool(committed)}"]})
        return 1

    rows = load(ATLAS)
    prows = load(PATHS)
    isr = [r for r in rows if r["split"] == "IS"]
    oos = [r for r in rows if r["split"] == "OOS"]
    cuts = {k: tuple(v) for k, v in freeze["frozen_definitions"]["tercile_cuts"].items()}
    med_off = freeze["frozen_definitions"]["close_vs_high20_is_median"]
    note(f"reveal: OOS rows={len(oos)} cohorts={len({r['cohort_id'] for r in oos})}")

    # ------------------------------------------------------------ registered feature relationships, three splits
    summary_rows, conf_rows = [], []
    rels = {}
    for f in cuts:
        rel_is = isres["relationships"][f][PRIMARY]
        rel_oos = st.relationship(oos, f, PRIMARY, cuts[f])
        rel_all = st.relationship(rows, f, PRIMARY, cuts[f])
        rel_oos2 = st.relationship(oos, f, SECOND, cuts[f])
        rels[f] = {"IS": rel_is, "OOS": rel_oos, "ALL": rel_all}
        for split, rel in (("IS", rel_is), ("OOS", rel_oos), ("ALL", rel_all)):
            summary_rows.append({"feature": f, "cutoff": "PRE_ORDER" if f.startswith("po_") else "SIGNAL_CLOSE", "split": split,
                                 "outcome": PRIMARY, "n": rel.get("n"), "missing": rel.get("missing"), "cohorts": rel.get("cohorts"),
                                 "securities": rel.get("securities"), "months": rel.get("months"),
                                 "pooled_spearman": rel.get("pooled_spearman"), "tercile_cut_low": cuts[f][0], "tercile_cut_high": cuts[f][1],
                                 "t1_mean": (rel.get("t1_low") or {}).get("mean"), "t3_mean": (rel.get("t3_high") or {}).get("mean"),
                                 "t3_minus_t1_mean": rel.get("t3_minus_t1_mean"), "t3_minus_t1_hit": rel.get("t3_minus_t1_hit"),
                                 "within_cohort_mean_spearman": rel.get("within_cohort_mean_spearman"),
                                 "within_cohort_halves_positive_share": rel.get("within_cohort_halves_positive_share"),
                                 "within_cohort_top_half_minus_bottom_half": rel.get("within_cohort_top_half_minus_bottom_half"),
                                 "within_cohort_cohorts": rel.get("within_cohort_cohorts"),
                                 "between_cohort_spearman": rel.get("between_cohort_spearman"),
                                 "leading_on_is": bool(rel_is.get("leading")), "cuts_learned_on": "IS"})
        share_is, share_oos = rel_is.get("within_cohort_halves_positive_share"), rel_oos.get("within_cohort_halves_positive_share")
        c_is, c_oos = rel_is.get("within_cohort_top_half_minus_bottom_half"), rel_oos.get("within_cohort_top_half_minus_bottom_half")
        if rel_is.get("leading"):
            expected = "same sign within-cohort contrast; one-sided share >= 0.62"
            met_flag = (c_is is not None and c_oos is not None and (c_is > 0) == (c_oos > 0)
                        and (share_oos >= 0.62 if c_is > 0 else share_oos <= 0.38))
            status = "REPLICATED" if met_flag else ("SAME_SIGN_WEAKER" if c_is is not None and c_oos is not None and (c_is > 0) == (c_oos > 0) else "NOT_REPLICATED")
        else:
            expected = "no separation expected (not leading on IS)"
            met_flag = share_oos is not None and 0.38 < share_oos < 0.62
            status = "NO_SIGNAL_CONFIRMED" if met_flag else "SEPARATION_APPEARED_POST_HOC"
        conf_rows.append({"comparison": f"feature:{f}", "kind": "continuous_feature", "cutoff": "PRE_ORDER" if f.startswith("po_") else "SIGNAL_CLOSE",
                          "is_value": c_is, "is_share": share_is, "is_n": rel_is.get("n"), "is_cohorts": rel_is.get("within_cohort_cohorts"),
                          "oos_value": c_oos, "oos_share": share_oos, "oos_n": rel_oos.get("n"), "oos_cohorts": rel_oos.get("within_cohort_cohorts"),
                          "oos_net_per_dollar_contrast": rel_oos2.get("within_cohort_top_half_minus_bottom_half"),
                          "expected": expected, "met": met_flag, "status": status,
                          "value_basis": "within-cohort mean of (top half minus bottom half by feature) of the ten-session short price return; frozen IS tercile cuts"})

    # ------------------------------------------------------------ groups, three splits
    groups = {}
    for g in ("sc_four_state", "sc_signal_close_band", "ep_episode", "cx_rank_in_eight", "po_preorder_price_band"):
        groups[g] = {s: st.group_table(sel, g, PRIMARY, weight=DOLLAR) for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows))}
        for s in ("IS", "OOS", "ALL"):
            for row in groups[g][s]:
                summary_rows.append({"feature": f"group:{g}={row['group']}", "cutoff": "PRE_ORDER" if g.startswith("po_") else "SIGNAL_CLOSE",
                                     "split": s, "outcome": PRIMARY, "n": row["n"], "missing": None, "cohorts": row["cohorts"],
                                     "securities": row["securities"], "months": row["months"], "pooled_spearman": None,
                                     "tercile_cut_low": None, "tercile_cut_high": None, "t1_mean": None, "t3_mean": None,
                                     "t3_minus_t1_mean": row["mean"], "t3_minus_t1_hit": row["hit_rate"],
                                     "within_cohort_mean_spearman": None, "within_cohort_halves_positive_share": None,
                                     "within_cohort_top_half_minus_bottom_half": row["cohort_equal_weight_mean"],
                                     "within_cohort_cohorts": row["cohorts"], "between_cohort_spearman": None,
                                     "leading_on_is": None, "cuts_learned_on": "frozen rule"})

    def gval(g, s, name, key="cohort_equal_weight_mean"):
        for row in groups[g][s]:
            if row["group"] == name:
                return row.get(key)
        return None

    def cell_rows(sel, band_set, off_side):
        return [r for r in sel if r["sc_signal_close_band"] in band_set and st.num(r.get("sc_close_vs_high20")) is not None
                and ((st.num(r["sc_close_vs_high20"]) < med_off) if off_side == "off_high" else (st.num(r["sc_close_vs_high20"]) >= med_off))]

    state_map = {}
    for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows)):
        state_map[s] = {}
        for bl, bands in (("10-20", ("10-20",)), (">=20", ("20-40", "40-80"))):
            for side in ("off_high", "near_high"):
                state_map[s][f"{bl} x {side}"] = subset_stats(cell_rows(sel, bands, side), f"{bl} x {side}")
    ranks28 = lambda sel: [r for r in sel if r["cx_rank_in_eight"] != "1"]  # noqa: E731
    off28 = {s: st.relationship(ranks28(sel), "sc_close_vs_high20", PRIMARY, cuts["sc_close_vs_high20"]) for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows))}

    # ------------------------------------------------------------ claims C1..C10, coded
    claims = []

    def claim(cid, text, is_v, oos_v, expected, met_flag, basis):
        claims.append({"comparison": f"claim:{cid}", "kind": "claim", "cutoff": "SIGNAL_CLOSE" if cid != "C8" else "PRE_ORDER",
                       "is_value": is_v, "is_share": None, "is_n": None, "is_cohorts": None, "oos_value": oos_v, "oos_share": None,
                       "oos_n": None, "oos_cohorts": None, "oos_net_per_dollar_contrast": None, "expected": expected, "met": met_flag,
                       "status": "REPLICATED" if met_flag else "NOT_REPLICATED", "value_basis": f"{text}; {basis}"})

    r1 = {s: gval("cx_rank_in_eight", s, "1") for s in ("IS", "OOS")}
    r1hit = {s: gval("cx_rank_in_eight", s, "1", "hit_rate") for s in ("IS", "OOS")}
    r28 = {s: cew([r for r in sel if r["cx_rank_in_eight"] != "1"], PRIMARY) for s, sel in (("IS", isr), ("OOS", oos))}
    gap = rels["cx_gap_to_next_rank"]
    claim("C1", "rank-1 minus ranks 2-8, cohort-equal-weight", r1["IS"] - r28["IS"], r1["OOS"] - r28["OOS"],
          "difference > 0.10, rank-1 hit > 0.65, gap share >= 0.62",
          (r1["OOS"] - r28["OOS"] > 0.10) and r1hit["OOS"] > 0.65 and gap["OOS"]["within_cohort_halves_positive_share"] >= 0.62,
          f"rank-1 hit IS {r1hit['IS']:.2f} OOS {r1hit['OOS']:.2f}; gap share IS {gap['IS']['within_cohort_halves_positive_share']:.2f} OOS {gap['OOS']['within_cohort_halves_positive_share']:.2f}")
    claim("C2", "ranks 2-8: T1 minus T3 of close_vs_high20", -off28["IS"]["t3_minus_t1_mean"], -off28["OOS"]["t3_minus_t1_mean"],
          "positive; within share <= 0.38", (-off28["OOS"]["t3_minus_t1_mean"] > 0) and off28["OOS"]["within_cohort_halves_positive_share"] <= 0.38,
          f"within share IS {off28['IS']['within_cohort_halves_positive_share']:.2f} OOS {off28['OOS']['within_cohort_halves_positive_share']:.2f}")
    rng = rels["sc_mean_range_pct_10"]
    claim("C3", "sc_mean_range_pct_10 within-cohort half contrast", rng["IS"]["within_cohort_top_half_minus_bottom_half"], rng["OOS"]["within_cohort_top_half_minus_bottom_half"],
          "positive; share >= 0.62", rng["OOS"]["within_cohort_top_half_minus_bottom_half"] > 0 and rng["OOS"]["within_cohort_halves_positive_share"] >= 0.62,
          f"share IS {rng['IS']['within_cohort_halves_positive_share']:.2f} OOS {rng['OOS']['within_cohort_halves_positive_share']:.2f}")
    b = {s: {k: gval("sc_signal_close_band", s, k) for k in ("10-20", "20-40", "40-80")} for s in ("IS", "OOS")}
    claim("C4", "band 10-20 minus max(20-40, 40-80), cohort-equal-weight", b["IS"]["10-20"] - max(b["IS"]["20-40"], b["IS"]["40-80"]),
          b["OOS"]["10-20"] - max(b["OOS"]["20-40"], b["OOS"]["40-80"]), "positive",
          b["OOS"]["10-20"] > max(b["OOS"]["20-40"], b["OOS"]["40-80"]),
          f"OOS bands {b['OOS']}")
    weak = {s: cew([r for r in sel if st.num(r.get("sc_ret3")) is not None and st.num(r["sc_ret3"]) <= 0], PRIMARY) for s, sel in (("IS", isr), ("OOS", oos))}
    strong = {s: cew([r for r in sel if st.num(r.get("sc_ret3")) is not None and st.num(r["sc_ret3"]) > 0], PRIMARY) for s, sel in (("IS", isr), ("OOS", oos))}
    s1, s2, s3 = [{s: gval("sc_four_state", s, k) for s in ("IS", "OOS")} for k in ("S1_FULL_weak_quiet", "S2_HALF_weak_loud", "S3_HALF_strong_quiet")]
    s2n = gval("sc_four_state", "OOS", "S2_HALF_weak_loud", "n")
    halves_differ_oos = (s2["OOS"] is not None and s3["OOS"] is not None and s1["OOS"] is not None
                         and abs(s2["OOS"] - s1["OOS"]) < abs(s2["OOS"] - s3["OOS"]))
    claim("C5", "ret3<=0 minus ret3>0, cohort-equal-weight; S2 closer to S1 than to S3", weak["IS"] - strong["IS"], weak["OOS"] - strong["OOS"],
          "positive; S2 nearer S1 (S2 sparse)", (weak["OOS"] - strong["OOS"]) > 0 and halves_differ_oos,
          f"OOS S1 {fmt(s1['OOS'])} S2 {fmt(s2['OOS'])} (n={s2n}) S3 {fmt(s3['OOS'])}")
    ep = {s: {k: gval("ep_episode", s, k) for k in ("FIRST", "OVERLAPPING_REPEAT")} for s in ("IS", "OOS")}
    claim("C6", "FIRST minus OVERLAPPING_REPEAT, cohort-equal-weight", ep["IS"]["FIRST"] - ep["IS"]["OVERLAPPING_REPEAT"],
          ep["OOS"]["FIRST"] - ep["OOS"]["OVERLAPPING_REPEAT"], "positive, modest", (ep["OOS"]["FIRST"] - ep["OOS"]["OVERLAPPING_REPEAT"]) > 0, "")
    up = rels["sc_up_sessions_15"]
    t3s = rels["sc_top3_sessions_share_of_advance"]
    claim("C7", "up_sessions within contrast (expect negative); top3 share within contrast (expect positive)",
          up["IS"]["within_cohort_top_half_minus_bottom_half"], up["OOS"]["within_cohort_top_half_minus_bottom_half"],
          "up_sessions negative and top3 share positive",
          up["OOS"]["within_cohort_top_half_minus_bottom_half"] < 0 and t3s["OOS"]["within_cohort_top_half_minus_bottom_half"] > 0,
          f"top3 share contrast IS {fmt(t3s['IS']['within_cohort_top_half_minus_bottom_half'])} OOS {fmt(t3s['OOS']['within_cohort_top_half_minus_bottom_half'])}")
    po1, po2 = rels["po_signal_close_to_preorder"], rels["po_preorder_location_in_partial_range"]
    claim("C8", "pre-order features within-cohort share (expect between 0.38 and 0.62)",
          po1["IS"]["within_cohort_halves_positive_share"], po1["OOS"]["within_cohort_halves_positive_share"], "no separation",
          0.38 < po1["OOS"]["within_cohort_halves_positive_share"] < 0.62 and 0.38 < po2["OOS"]["within_cohort_halves_positive_share"] < 0.62,
          f"location share IS {po2['IS']['within_cohort_halves_positive_share']:.2f} OOS {po2['OOS']['within_cohort_halves_positive_share']:.2f}")
    sm = state_map
    best_is = max(sm["IS"], key=lambda k: sm["IS"][k]["cohort_equal_weight_mean"] or -9)
    worst_oos = min(sm["OOS"], key=lambda k: sm["OOS"][k]["cohort_equal_weight_mean"] if sm["OOS"][k]["cohort_equal_weight_mean"] is not None else 9)
    best_oos = max(sm["OOS"], key=lambda k: sm["OOS"][k]["cohort_equal_weight_mean"] or -9)
    claim("C9", "2x2 state map: best and worst cell", sm["IS"]["10-20 x off_high"]["cohort_equal_weight_mean"], sm["OOS"]["10-20 x off_high"]["cohort_equal_weight_mean"],
          "best = 10-20 x off_high, worst = >=20 x near_high", best_oos == "10-20 x off_high" and worst_oos == ">=20 x near_high",
          f"IS best {best_is}; OOS best {best_oos}, worst {worst_oos}")
    arch_oos = Counter(p["path_archetype"] for p in prows if p["ticket_id"] in {r["ticket_id"] for r in oos})
    age_oos = path_table(oos, prows, "OOS", "all")
    m2 = next(r["mean"] for r in age_oos if r["age"] == 2 and r["basis"].startswith("close-only"))
    m10 = next(r["mean"] for r in age_oos if r["age"] == 10 and r["basis"].startswith("close-only"))
    s1_oos = [r for r in oos if r["sc_four_state"] == "S1_FULL_weak_quiet"]
    s1_tab = path_table(s1_oos, prows, "OOS", "S1")
    s1_5 = next(r["mean"] for r in s1_tab if r["age"] == 5 and r["basis"].startswith("close-only"))
    s1_10 = next(r["mean"] for r in s1_tab if r["age"] == 10 and r["basis"].startswith("close-only"))
    claim("C10", "IMMEDIATE_FADE most common; age-2 mean at least half of age-10 mean; S1 accrues from age 5 to 10",
          None, m2 / m10 if m10 else None, "archetype and accrual shape",
          arch_oos.most_common(1)[0][0] == "IMMEDIATE_FADE" and (m10 > 0 and m2 >= 0.5 * m10) and (s1_10 > s1_5),
          f"OOS archetypes {dict(arch_oos)}; OOS mean age2 {fmt(m2)} age10 {fmt(m10)}; S1 age5 {fmt(s1_5)} age10 {fmt(s1_10)}")
    conf_rows.extend(claims)
    note("claims: " + ", ".join(f"{c['comparison'][6:]}={'yes' if c['met'] else 'NO'}" for c in claims))

    # ------------------------------------------------------------ probes, exposure-matched, no compounding
    probe_rows = []
    for p in freeze["frozen_definitions"]["probes"]:
        for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows)):
            inside = [r for r in sel if probe_mask(p["id"], r, med_off)]
            outside = [r for r in sel if not probe_mask(p["id"], r, med_off)]
            full = subset_stats(sel, "full book")
            a, bb = subset_stats(inside, p["name"]), subset_stats(outside, "complement")
            for lab, x in (("probe", a), ("complement", bb), ("full_book", full)):
                probe_rows.append({"probe": p["id"], "name": p["name"], "split": s, "set": lab, **x,
                                   "hypothetical_net_at_full_book_exposure": (x["net_per_entry_dollar"] * full["entry_exposure"]) if x["net_per_entry_dollar"] is not None else None,
                                   "exposure_share_of_full_book": (x["entry_exposure"] / full["entry_exposure"]) if full["entry_exposure"] else None,
                                   "basis": "research-only subset of the certified trades; unused exposure idle; hypothetical figure applies the subset's net per entry dollar to the full book's entry exposure; no compounded equity, no account drawdown"})
            met_flag = (a["net_per_entry_dollar"] or -9) > (full["net_per_entry_dollar"] or -9) and (a["hit_rate"] or 0) > (full["hit_rate"] or 0)
            if p["id"] == "P3":
                met_flag = (bb["net_per_entry_dollar"] or 9) < (a["net_per_entry_dollar"] or -9)
            if s == "OOS":
                conf_rows.append({"comparison": f"probe:{p['id']}", "kind": "probe", "cutoff": "SIGNAL_CLOSE",
                                  "is_value": None, "is_share": None, "is_n": None, "is_cohorts": None,
                                  "oos_value": a["net_per_entry_dollar"], "oos_share": a["hit_rate"], "oos_n": a["n"], "oos_cohorts": a["cohorts"],
                                  "oos_net_per_dollar_contrast": (a["net_per_entry_dollar"] or 0) - (full["net_per_entry_dollar"] or 0),
                                  "expected": p["expected"], "met": met_flag, "status": "REPLICATED" if met_flag else "NOT_REPLICATED",
                                  "value_basis": f"{p['name']}: net per entry dollar and hit rate vs the full book; exposure share {a['entry_exposure'] / full['entry_exposure']:.2f}"})
    for r in probe_rows:
        conf_iss = [c for c in conf_rows if c["comparison"] == f"probe:{r['probe']}"]
        r["oos_status"] = conf_iss[0]["status"] if conf_iss else None
    exp.write_csv(REPORTS / "cg_arrow011_probes.csv", probe_rows)
    exp.write_csv(REPORTS / "cg_arrow011_confirmation.csv", conf_rows)
    exp.write_csv(REPORTS / "cg_arrow011_within_cohort_summary.csv", summary_rows)

    # ------------------------------------------------------------ holding paths, all splits and conditions
    path_rows = []
    for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows)):
        path_rows += path_table(sel, prows, s, "all")
        for state in sorted({r["sc_four_state"] for r in rows}):
            path_rows += path_table([r for r in sel if r["sc_four_state"] == state], prows, s, f"state={state}")
        path_rows += path_table([r for r in sel if r["cx_rank_in_eight"] == "1"], prows, s, "rank=1")
        path_rows += path_table([r for r in sel if r["cx_rank_in_eight"] != "1"], prows, s, "rank=2-8")
        for f in ("sc_close_vs_high20", "sc_mean_range_pct_10"):
            for t in ("T1_low", "T3_high"):
                path_rows += path_table([r for r in sel if st.num(r.get(f)) is not None and st.tercile_of(st.num(r[f]), cuts[f]) == t], prows, s, f"{f}={t}")
    exp.write_csv(REPORTS / "cg_arrow011_holding_path_summary.csv", path_rows)

    # ------------------------------------------------------------ hypotheses.csv from the registry plus OOS outcome
    hyp_rows = []
    feat_conf = {c["comparison"][8:]: c for c in conf_rows if c["kind"] == "continuous_feature"}
    for h in freeze["registry"]:
        f = h["feature"].split(",")[0].strip()
        c = feat_conf.get(f)
        cl = next((x for x in claims if h["id"] in " ".join(str(v) for v in freeze["claims_to_confirm"] if h["id"] in v["registered"]) or False), None)
        oos_status = c["status"] if c else None
        for x in freeze["claims_to_confirm"]:
            if h["id"] in x["registered"]:
                cc = next(k for k in claims if k["comparison"] == f"claim:{x['id']}")
                oos_status = f"{x['id']}:{cc['status']}"
        hyp_rows.append({"id": h["id"], "lane": h["lane"], "parent": h.get("parent"), "cutoff": h["cutoff"], "feature": h["feature"],
                         "question": h["question"], "test": h["test"], "prediction": h.get("prediction"),
                         "why_distinct": h.get("why_distinct"), "information_value": h.get("information_value"),
                         "is_status": h["is_status"], "is_basis": h.get("is_basis"),
                         "is_within_contrast": (c["is_value"] if c else None), "oos_within_contrast": (c["oos_value"] if c else None),
                         "oos_status": oos_status, "sample": "IS 25 cohorts / 200 tickets; OOS 27 cohorts / 216 tickets",
                         "counterexamples": "see hypothesis_casebook.md (private) and the anatomy report"})
    exp.write_csv(REPORTS / "cg_arrow011_hypotheses.csv", hyp_rows)

    # ------------------------------------------------------------ private: cohort atlas and casebook
    write_cohort_atlas(rows, med_off, cuts)
    write_casebook(rows, isr, oos, cuts, med_off)

    # ------------------------------------------------------------ all-year census and manifest
    census = {}
    for s, sel in (("IS", isr), ("OOS", oos), ("ALL", rows)):
        by = defaultdict(list)
        for r in sel:
            by[r["cohort_id"]].append(st.num(r.get(PRIMARY)))
        k = Counter()
        for vals in by.values():
            if any(v is None for v in vals):
                k["PARTLY_CENSORED"] += 1
            elif all(v > 0 for v in vals):
                k["ALL_WIN"] += 1
            elif all(v <= 0 for v in vals):
                k["ALL_LOSS"] += 1
            else:
                k["MIXED"] += 1
        census[s] = dict(k)
    manifest = {
        "arrow": "CG Arrow 011", "stage": "confirmation_and_retrospective", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "freeze_commit": committed, "hash_drift_since_freeze": drift,
        "oos_rows": len(oos), "oos_cohorts": len({r["cohort_id"] for r in oos}), "cohort_census": census,
        "claims": [{k: c[k] for k in ("comparison", "is_value", "oos_value", "expected", "met", "status", "value_basis")} for c in claims],
        "claims_met": sum(1 for c in claims if c["met"]), "claims_total": len(claims),
        "feature_confirmation_counts": dict(Counter(c["status"] for c in conf_rows if c["kind"] == "continuous_feature")),
        "probe_oos": {c["comparison"]: c["status"] for c in conf_rows if c["kind"] == "probe"},
        "state_map": state_map, "groups": groups, "off_high_ranks_2_8": off28,
        "build": {k: build[k] for k in ("hash_checks", "counts", "control_checks", "fresh_replay_mismatches", "oracle_a8_r2", "oracle_a10", "feature_state_disagreements", "pre_order_available", "atlas_rows")},
        "bridge": {k: bridge[k] for k in ("per_share_path_reconciliation", "net_per_share_identity_worst", "monthly_marked_reconciliation_worst", "identity_worst", "decomposition_order")},
        "monthly_reconciliation": bridge["monthly_reconciliation"],
        "local_files": {p.name: digest(p) for p in sorted(OUT.glob("*")) if p.is_file()},
        "public_files": {p.name: digest(p) for p in sorted(REPORTS.glob("cg_arrow011_*")) if p.is_file()},
        "log": LOG,
    }
    dump_json(CACHE / "confirm_manifest.json", manifest)
    note(f"confirmation complete: {manifest['claims_met']}/{manifest['claims_total']} claims met; features {manifest['feature_confirmation_counts']}")
    return 0


def write_cohort_atlas(rows, med_off, cuts):
    by = defaultdict(list)
    for r in rows:
        by[r["cohort_id"]].append(r)
    L = ["# CG Arrow 011 — cohort atlas (private)", "",
         "One dossier per weekly cohort of the certified Corrected-Universe Momentum+Volume-Sized Short, causal pre-order quantities. "
         "Pre-entry columns are SIGNAL_CLOSE features; outcome columns are the ten-session sizing-neutral short return, modeled net per "
         "entry dollar, and dollar contribution under the fixed-dollar and equity-scaled books. Commentary is mechanical: it names which "
         "slots carried the cohort and whether the frozen IS patterns held in that basket. No catalyst narratives are asserted.", ""]
    for cid in sorted(by):
        rs = sorted(by[cid], key=lambda r: int(r["cx_rank_in_eight"]))
        prs = [st.num(r[PRIMARY]) for r in rs]
        done = [v for v in prs if v is not None]
        fixed = sum(st.num(r[DOLLAR]) or 0 for r in rs)
        scaled = sum(st.num(r[SCALED]) or 0 for r in rs)
        kind = ("PARTLY_CENSORED" if len(done) < len(prs) else "ALL_WIN" if all(v > 0 for v in done) else "ALL_LOSS" if all(v <= 0 for v in done) else "MIXED")
        L.append(f"## Cohort {cid} — {rs[0]['split']} — {kind} — mean short return {fmt(statistics.mean(done)) if done else 'n/a'}, "
                 f"fixed-dollar net {fixed:,.0f}, equity-scaled net {scaled:,.0f} (scale {st.num(rs[0]['lens_equity_scale_factor']):.2f}x)")
        L.append("")
        L.append("| Rank | Symbol | Band | ret15 | Gap to next | Off high20 | Range10 | State | Episode | Ret10 | Net/$ | Fixed $ | Scaled $ | Path |")
        L.append("|---:|---|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|")
        for r in rs:
            L.append(f"| {r['cx_rank_in_eight']} | {r['symbol']} | {r['sc_signal_close_band']} | {fmt(st.num(r['sc_ret15']),2)} | "
                     f"{fmt(st.num(r['cx_gap_to_next_rank']),2)} | {fmt(st.num(r['sc_close_vs_high20']),2)} | {fmt(st.num(r['sc_mean_range_pct_10']),3)} | "
                     f"{r['sc_four_state'][:2]} | {r['ep_episode'][:5]} | {fmt(st.num(r[PRIMARY]))} | {fmt(st.num(r[SECOND]))} | "
                     f"{(st.num(r[DOLLAR]) or 0):,.0f} | {(st.num(r[SCALED]) or 0):,.0f} | {r['path_archetype']} |")
        top = max(rs, key=lambda r: st.num(r[DOLLAR]) or -1e9)
        bot = min(rs, key=lambda r: st.num(r[DOLLAR]) or 1e9)
        r1 = rs[0]
        r1v = st.num(r1[PRIMARY])
        off = [r for r in rs[1:] if st.num(r.get("sc_close_vs_high20")) is not None and st.num(r["sc_close_vs_high20"]) < med_off]
        near = [r for r in rs[1:] if st.num(r.get("sc_close_vs_high20")) is not None and st.num(r["sc_close_vs_high20"]) >= med_off]
        off_m = statistics.mean(st.num(r[PRIMARY]) for r in off if st.num(r[PRIMARY]) is not None) if any(st.num(r[PRIMARY]) is not None for r in off) else None
        near_m = statistics.mean(st.num(r[PRIMARY]) for r in near if st.num(r[PRIMARY]) is not None) if any(st.num(r[PRIMARY]) is not None for r in near) else None
        L.append("")
        L.append(f"Largest fixed-dollar contributor: {top['symbol']} ({(st.num(top[DOLLAR]) or 0):,.0f}); largest detractor: {bot['symbol']} "
                 f"({(st.num(bot[DOLLAR]) or 0):,.0f}). Rank-1 {r1['symbol']} short return {fmt(r1v)} "
                 f"({'faded' if r1v is not None and r1v > 0 else 'did not fade' if r1v is not None else 'open'}). "
                 f"Ranks 2-8 off-high mean {fmt(off_m)} (n={len(off)}) versus near-high {fmt(near_m)} (n={len(near)}): "
                 f"{'pattern held' if off_m is not None and near_m is not None and off_m > near_m else 'pattern did not hold' if off_m is not None and near_m is not None else 'not testable'}.")
        L.append("")
    (OUT / "cohort_atlas.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


def write_casebook(rows, isr, oos, cuts, med_off):
    L = ["# CG Arrow 011 — hypothesis casebook (private)", "",
         "Supporting examples and counterexamples for the leading IS patterns. Every feature named is a SIGNAL_CLOSE pre-entry value; "
         "the short return is the retrospective outcome. Examples are chosen mechanically (largest and smallest outcomes inside the "
         "pattern's cell), never for narrative fit.", ""]

    def show(r):
        return (f"{r['cohort_id']} {r['symbol']} ({r['split']}): band {r['sc_signal_close_band']}, ret15 {fmt(st.num(r['sc_ret15']),2)}, "
                f"gap {fmt(st.num(r['cx_gap_to_next_rank']),2)}, off-high {fmt(st.num(r['sc_close_vs_high20']),2)}, range10 {fmt(st.num(r['sc_mean_range_pct_10']),3)}, "
                f"state {r['sc_four_state']}, episode {r['ep_episode']} -> short return {fmt(st.num(r[PRIMARY]))}, path {r['path_archetype']}")

    def block(title, sel, key=PRIMARY):
        L.append(f"## {title}")
        L.append("")
        sel = [r for r in sel if st.num(r.get(key)) is not None]
        sup = sorted(sel, key=lambda r: -st.num(r[key]))[:3]
        con = sorted(sel, key=lambda r: st.num(r[key]))[:3]
        L.append(f"Cell size {len(sel)}; hit rate {sum(1 for r in sel if st.num(r[key]) > 0) / len(sel):.2f}" if sel else "Cell empty")
        L.append("")
        L.append("Supporting (largest fades):")
        for r in sup:
            L.append(f"- {show(r)}")
        L.append("")
        L.append("Counterexamples (did not fade):")
        for r in con:
            L.append(f"- {show(r)}")
        L.append("")

    for s, sel in (("IS", isr), ("OOS (post-reveal, descriptive)", oos)):
        block(f"C1 rank-1 extremeness — {s}", [r for r in sel if r["cx_rank_in_eight"] == "1"])
        block(f"C2 ranks 2-8 already off the high (T1 of close_vs_high20) — {s}",
              [r for r in sel if r["cx_rank_in_eight"] != "1" and st.num(r.get("sc_close_vs_high20")) is not None and st.tercile_of(st.num(r["sc_close_vs_high20"]), cuts["sc_close_vs_high20"]) == "T1_low"])
        block(f"C2 contrast: ranks 2-8 near the high (T3) — {s}",
              [r for r in sel if r["cx_rank_in_eight"] != "1" and st.num(r.get("sc_close_vs_high20")) is not None and st.tercile_of(st.num(r["sc_close_vs_high20"]), cuts["sc_close_vs_high20"]) == "T3_high"])
        block(f"C9 best cell 10-20 x off-high — {s}", [r for r in sel if r["sc_signal_close_band"] == "10-20" and st.num(r.get("sc_close_vs_high20")) is not None and st.num(r["sc_close_vs_high20"]) < med_off])
        block(f"C9 worst cell >=20 x near-high — {s}", [r for r in sel if r["sc_signal_close_band"] in ("20-40", "40-80") and st.num(r.get("sc_close_vs_high20")) is not None and st.num(r["sc_close_vs_high20"]) >= med_off])
        block(f"C5 weak momentum (S1, S2) — {s}", [r for r in sel if r["sc_four_state"] in ("S1_FULL_weak_quiet", "S2_HALF_weak_loud")])
        block(f"C6 overlapping repeats — {s}", [r for r in sel if r["ep_episode"] == "OVERLAPPING_REPEAT"])
    (OUT / "hypothesis_casebook.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
