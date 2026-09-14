"""CG Arrow 012 Phase B preflight — certify original ranks 9-20 and write the challenger freeze.

Reproduces the frozen controls, reconstructs the corrected original rank order through rank 20
under the unchanged R2 rules, certifies every rank 9-20 name the frozen substitution rule
could actually choose, resolves the deterministic substitution plan per cohort, and writes
reports/cg_arrow012_challenger_freeze.json plus the private candidate audit.

No challenger economics are computed here. The freeze must be committed before scoring.

Usage: python scripts/cg_arrow012_candidates.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_anatomy as an  # noqa: E402
from verification import r4r5_challenger as ch  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    ACTION_PATH, CUTOFF, FEATS, INDEX, LOCAL_TAPE_END, VERIFY_ROOT, action_events, digest,
    dump_json, features, halted, history, present, read_json, resolved_symbol, spans_non_comparable,
    set_vendor_status, stamp,
)
from verification.r4r5_replay import COMPLETED, TEST_SYMBOL, load_field, replay, sizing  # noqa: E402
from cg_arrow007_run import candidate_meta  # noqa: E402
from cg_arrow010_run import build_substrate  # noqa: E402

OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow012"
CACHE = VERIFY_ROOT / "a12"
A8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
A10 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow010"
HOLD = 10
DEPTH = ch.SUBSTITUTION_SEARCH_DEPTH
LOG: list[str] = []
T0 = time.monotonic()

CONTROLS = {
    "r5_r2_h10_causal_preorder_eventual_completed_trade_pnl": 128864.62,
    "r5_r2_h10_causal_preorder_marked_account_pnl_at_cutoff": 128986.40,
    "a10_equity_scaled_marked_account_pnl_at_cutoff": 230719.74,
    "a10_equity_scaled_ending_marked_equity": 330719.74,
    "a10_equity_scaled_eventual_completed_trade_pnl": 230566.36,
}


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def num(x):
    return None if x in ("", None) else float(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []

    a8m = read_json(REPORTS / "cg_arrow008_manifest.json")
    a10m = read_json(REPORTS / "cg_arrow010_manifest.json")
    a11f = read_json(REPORTS / "cg_arrow011_hypothesis_freeze.json")
    threshold = a11f["frozen_definitions"]["close_vs_high20_is_median"]
    note(f"Arrow 011 frozen off-high threshold M = {threshold!r}")

    # ---------------------------------------------------------------- frozen cohort membership
    a11_atlas = list(csv.DictReader((REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011" / "trade_atlas.csv").open(encoding="utf-8")))
    FROZEN = sorted({r["cohort_id"] for r in a11_atlas})
    assert len(FROZEN) == 52, len(FROZEN)
    note(f"frozen cohort membership: {len(FROZEN)} cohorts, {FROZEN[0]} .. {FROZEN[-1]} (holdout embargo: nothing outside this set)")

    # ---------------------------------------------------------------- substrate and controls
    corrected, summaries, coverage = build_substrate(args.workers)
    corrected = [c for c in corrected if c["signal_iso"] in set(FROZEN)]
    if len(corrected) != 52:
        blockers.append(f"substrate produced {len(corrected)} frozen cohorts, expected 52")
    membership = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in corrected}
    if sha_obj(membership) != a8m["membership_sha256"]:
        blockers.append("membership hash does not match Arrow 008")
    note(f"membership hash matches Arrow 008: {sha_obj(membership) == a8m['membership_sha256']}")

    a8_rows = list(csv.DictReader((A8 / "r4r5_verified_trades.csv").open(encoding="utf-8")))
    a10_rows = list(csv.DictReader((A10 / "r4r5_verified_trades.csv").open(encoding="utf-8")))
    books = {}
    for r in a8_rows + a10_rows:
        books.setdefault((r["model"], r["replay_stage"]), []).append(r)
    pre = books[("R5", "R2_CAUSAL_PREORDER_QTY")]
    scaled = books[("R5", "R5_EQUITY_SCALED")]
    a10acc = a10m["accounts"]
    observed = {
        "r5_r2_h10_causal_preorder_eventual_completed_trade_pnl": sum(num(r["modeled_net"]) for r in pre if r["status"] in COMPLETED),
        "r5_r2_h10_causal_preorder_marked_account_pnl_at_cutoff": a10acc["R5_FIXED_DOLLAR_CONTROL/ALL"]["B_marked_account_pnl_at_cutoff"],
        "a10_equity_scaled_marked_account_pnl_at_cutoff": a10acc["R5_EQUITY_SCALED/ALL"]["B_marked_account_pnl_at_cutoff"],
        "a10_equity_scaled_ending_marked_equity": 100000.0 + a10acc["R5_EQUITY_SCALED/ALL"]["B_marked_account_pnl_at_cutoff"],
        "a10_equity_scaled_eventual_completed_trade_pnl": sum(num(r["modeled_net"]) for r in scaled if r["status"] in COMPLETED),
    }
    control_check = {k: {"expected": v, "observed": observed[k], "difference": observed[k] - v,
                         "ok": abs(observed[k] - v) < 0.005} for k, v in CONTROLS.items()}
    for k, v in control_check.items():
        note(f"control {k}: expected {v['expected']:,.2f} observed {v['observed']:,.2f} ok={v['ok']}")
    if not all(v["ok"] for v in control_check.values()):
        blockers.append("a frozen economic control did not reproduce")
    census = {}
    for key in (("R5", "R2_CAUSAL_PREORDER_QTY"), ("R5", "R5_EQUITY_SCALED"), ("R5", "R2_LEGACY_FILL_QTY")):
        rows = books[key]
        census["/".join(key)] = {"cohorts": len({r["cohort_id"] for r in rows}), "intended": len(rows),
                                 "completed": sum(1 for r in rows if r["status"] in COMPLETED),
                                 "open_documented": sum(1 for r in rows if r["status"] == "OPEN_AT_BOUNDARY_DOCUMENTED_HALT")}
        c = census["/".join(key)]
        if (c["cohorts"], c["intended"], c["completed"], c["open_documented"]) != (52, 416, 415, 1):
            blockers.append(f"{'/'.join(key)} census is not 52/416/415/1: {c}")
    note(f"principal-book census: {census[list(census)[0]]}")
    if blockers:
        dump_json(CACHE / "candidates_manifest.json", {"blockers": blockers, "control_check": control_check, "log": LOG})
        note("STOPPED: " + "; ".join(blockers))
        return 1

    # ---------------------------------------------------------------- rank order through 20
    cohort_field = read_json(VERIFY_ROOT / "work" / "cohort_field.json")
    meta = candidate_meta(sorted(cohort_field))
    status_map = rep.session_status_map()
    set_vendor_status(status_map)
    deep = {}
    for c in corrected:
        iso = c["signal_iso"]
        cands = {s: meta[iso][s] for s in cohort_field[iso]["rule_field"] if s in meta[iso]}
        deep[iso] = rank.rank_cohort(c["signal"], cands, summaries, status_map)["rows"][:DEPTH]
    # the reconstructed top eight must equal the frozen selection exactly
    mismatch = [iso for iso in membership if [h["symbol"] for h in deep[iso][:8]] != membership[iso]]
    note(f"reconstructed rank order reproduces the frozen top eight: {not mismatch}")
    if mismatch:
        blockers.append(f"rank reconstruction differs from frozen membership on {mismatch[:3]}")
        dump_json(CACHE / "candidates_manifest.json", {"blockers": blockers, "log": LOG})
        return 1

    # ---------------------------------------------------------------- observations for ranks 1-20
    need = set()
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in deep[c["signal_iso"]]:
            for d in FEATS[max(0, i - 22): fi + HOLD + 1]:
                need.add((d.isoformat(), h["symbol"]))
            for d in FEATS[fi + HOLD + 1:]:
                if d <= LOCAL_TAPE_END:
                    need.add((d.isoformat(), h["symbol"]))
    from verification.r4r5_data import load_summaries
    note(f"loading {len(need - set(summaries))} additional observations for ranks 9-{DEPTH}")
    summaries.update(load_summaries(need - set(summaries), args.workers))

    # ---------------------------------------------------------------- certify every rank 9-20 name
    resolutions = {}
    material = read_json(VERIFY_ROOT / "work" / "a8_material_ledger.json")
    for r in material:
        if r["final_state"] != "UNRESOLVED":
            resolutions[(r["symbol"], r["session"])] = r["final_state"]
    for x in read_json(ACTION_PATH).get("screen_resolutions", []):
        resolutions[(x["symbol"], x.get("date"))] = x["resolution"]

    audit_rows, off_high, certified = [], {}, {}
    for c in corrected:
        iso, signal, fill = c["signal_iso"], c["signal"], c["fill"]
        fi = INDEX[fill]
        exit_d = FEATS[fi + HOLD]
        certified[iso] = set()
        for h in deep[iso]:
            sym = h["symbol"]
            f = an.signal_close_features(sym, signal, summaries)
            off_high[(iso, sym)] = f["close_vs_high20"]
            frozen_feats = features(history(sym, FEATS[INDEX[signal] - 20: INDEX[signal] + 1], signal, summaries))
            amount, tier, vm, mm = sizing("R5", frozen_feats)
            entry_rec = summaries.get((fill.isoformat(), sym))
            exit_rec = summaries.get((exit_d.isoformat(), sym))
            lb = rank.lookback_integrity(signal, sym, summaries, resolutions)
            hd = rank.holding_integrity(fill, exit_d, sym, summaries, resolutions)
            checks = {
                "identity_not_test_symbol": not TEST_SYMBOL.match(sym),
                "identity_point_in_time_stable": resolved_symbol(sym, signal) == resolved_symbol(sym, exit_d),
                "rule_eligible_point_in_time": sym in cohort_field[iso]["rule_field"],
                "ranking_window_comparable": spans_non_comparable(sym, FEATS[INDEX[signal] - 15], signal) is None,
                "feature_history_complete": f["history_sessions_present"] == 21,
                "momentum_feature_present": frozen_feats["ret3"] is not None,
                "volume_feature_present": frozen_feats["volume_ratio"] is not None,
                "off_high_feature_present": f["close_vs_high20"] is not None,
                "lookback_action_units_resolved": lb.get("lookback_resolution") != "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY",
                "holding_action_units_resolved": hd.get("holding_resolution") != "UNEXPLAINED_HOLDING_WINDOW_DISCONTINUITY",
                "causal_preorder_entry_observation": bool(present(entry_rec) and entry_rec.get("preorder")),
                "h10_exit_or_documented_event": bool((present(exit_rec) and exit_rec.get("exec_px") is not None)
                                                     or halted(sym, exit_d) is not None),
            }
            ok = all(checks.values())
            if h["rank"] > 8 and ok:
                certified[iso].add(sym)
            audit_rows.append({
                "cohort_id": iso, "signal_date": iso, "entry_date": fill.isoformat(), "split": c["split"],
                "original_rank": h["rank"], "symbol": sym, "in_frozen_top8": h["rank"] <= 8,
                "ret15_ranking_return": h["raw_return"], "signal_close": f["signal_close"],
                "close_vs_high20": f["close_vs_high20"],
                "off_high_side": None if f["close_vs_high20"] is None else (f["close_vs_high20"] < threshold),
                "r5_tier": tier, "r5_base_notional": amount,
                "ret3": frozen_feats["ret3"], "volume_ratio": frozen_feats["volume_ratio"],
                "history_sessions_present": f["history_sessions_present"],
                "preorder_price": (entry_rec or {}).get("preorder"),
                "exit_observation": bool(present(exit_rec) and exit_rec.get("exec_px") is not None),
                "documented_halt_at_exit": halted(sym, exit_d) is not None,
                "lookback_resolution": lb.get("lookback_resolution"), "holding_resolution": hd.get("holding_resolution"),
                **{f"check_{k}": v for k, v in checks.items()},
                "certified_for_substitution": ok and h["rank"] > 8,
                "certification_failures": "; ".join(k for k, v in checks.items() if not v) or None})
    exp.write_csv(OUT / "top20_candidate_audit.csv", audit_rows)
    deep_rows = [r for r in audit_rows if not r["in_frozen_top8"]]
    note(f"ranks 9-{DEPTH}: {len(deep_rows)} name-cohorts; certified {sum(1 for r in deep_rows if r['certified_for_substitution'])}; "
         f"off-high side {sum(1 for r in deep_rows if r['off_high_side'])}")
    fails = Counter(x for r in deep_rows if r["certification_failures"] for x in r["certification_failures"].split("; "))
    note(f"rank 9-{DEPTH} certification failure reasons: {dict(fails)}")

    # ---------------------------------------------------------------- deterministic substitution plan
    plans, plan_rows = {}, []
    for c in corrected:
        iso = c["signal_iso"]
        top8 = deep[iso][:8]
        deeper = deep[iso][8:]
        oh = {h["symbol"]: off_high[(iso, h["symbol"])] for h in deep[iso]}
        plan = ch.substitution_plan(top8, deeper, oh, threshold, certified[iso])
        plans[iso] = plan
        if not plan["unique"]:
            blockers.append(f"{iso} substituted lineup is not eight unique names")
        for a, b in zip(plan["outgoing"], plan["incoming"]):
            plan_rows.append({"cohort_id": iso, "split": c["split"],
                              "outgoing_symbol": a["symbol"], "outgoing_original_rank": a["rank"],
                              "outgoing_close_vs_high20": oh[a["symbol"]],
                              "incoming_symbol": b["symbol"], "incoming_original_rank": b["rank"],
                              "incoming_close_vs_high20": oh[b["symbol"]],
                              "outgoing_ret15": a["raw_return"], "incoming_ret15": b["raw_return"],
                              "threshold_M": threshold})
    exp.write_csv(OUT / "substitution_pairs.csv", plan_rows)
    ks = Counter(p["k"] for p in plans.values())
    note(f"substitution plan: cohorts by number of swaps {dict(sorted(ks.items()))}; total swaps {sum(p['k'] for p in plans.values())}")
    # A data failure must never become a strategy choice. A rank 9-20 name that is on the
    # off-high side but not certified is excluded from the candidate set by the frozen rule;
    # where that exclusion actually changed the lineup, either by admitting a worse-ranked
    # replacement or by reducing k, the cohort's substitution rests on missing evidence rather
    # than on the rule. Those cohorts are named here, before any economics, and a pre-declared
    # sensitivity reverts them to the incumbent lineup so the conclusion can be tested against
    # them rather than quietly carrying them.
    by_cohort_deep = {}
    for r in deep_rows:
        by_cohort_deep.setdefault(r["cohort_id"], []).append(r)
    evidence_affected = {}
    for iso, p in plans.items():
        blocked = [int(r["original_rank"]) for r in by_cohort_deep.get(iso, [])
                   if r["off_high_side"] and not r["certified_for_substitution"]]
        if not blocked:
            continue
        used = [h["rank"] for h in p["incoming"]]
        worst_used = max(used) if used else None
        admitted_worse = sorted(b for b in blocked if worst_used is not None and b < worst_used)
        shrank = p["k"] < p["removable"]
        if admitted_worse or shrank:
            evidence_affected[iso] = {
                "blocked_off_high_ranks": sorted(blocked),
                "incoming_ranks_used": sorted(used), "removable": p["removable"], "k": p["k"],
                "worse_replacement_admitted": admitted_worse,
                "swaps_reduced_by_missing_evidence": shrank,
                "failures": sorted({f for r in by_cohort_deep.get(iso, [])
                                    if r["off_high_side"] and not r["certified_for_substitution"]
                                    and r["certification_failures"]
                                    for f in r["certification_failures"].split("; ")})}
    note(f"cohorts whose substitution was changed by unresolved candidate evidence: {len(evidence_affected)} "
         f"{sorted(evidence_affected)}")

    # ---------------------------------------------------------------- freeze
    frozen_plan = {iso: {"k": p["k"], "removable": p["removable"], "eligible": p["eligible"],
                         "outgoing_ranks": [h["rank"] for h in p["outgoing"]],
                         "incoming_ranks": [h["rank"] for h in p["incoming"]],
                         "lineup_original_ranks": sorted(h["rank"] for h in p["lineup"])}
                   for iso, p in plans.items()}
    freeze = {
        "arrow": "CG Arrow 012", "stage": "challenger_freeze", "timestamp": stamp(),
        "head_at_freeze": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "config_version": ch.CONFIG_VERSION,
        "holdout_embargo": {
            "declaration": ("Arrow 012 scores only the frozen 52 signal cohorts from 2025-09 through 2026-08. "
                            "No signal cohort outside this set is read, ranked, featurized, scored or summarized, "
                            "even if new files appear locally. Lookback and lifecycle observations required by the "
                            "frozen 52 remain permitted."),
            "frozen_cohort_ids": FROZEN, "frozen_cohort_count": len(FROZEN),
            "membership_sha256": sha_obj(membership),
            "enforcement": "scripts assert every scored cohort id is in this list; tests/test_cg_arrow012.py checks it"},
        "incumbent": {"family": "R5", "replay": "R2", "hold": HOLD, "quantity": "CAUSAL_PREORDER_QTY",
                      "equity_rule": "Arrow 010 causal signal-close marked equity over 100,000",
                      "tiers": {"FULL": 8300.0, "HALF": 4150.0, "QUARTER": 2075.0}},
        "challengers": {
            "C0": {"name": "Incumbent Momentum+Volume equity-scaled R5", "lineup": "original corrected top eight",
                   "allocation": "frozen R5 tier notionals", "reproduces": "Arrow 010 exactly"},
            "C1": {"name": "Rank-one 1.50x reallocation", "multiplier": ch.RANK_ONE_MULTIPLIER,
                   "formula": ("rank1_target = 1.50 * b1; other_scale = (T - rank1_target) / sum(b2..b8); "
                               "rank one gets rank1_target, each rank 2-8 gets bi * other_scale; sum equals T "
                               "to full precision before integer-share flooring"),
                   "failure_rule": "a nonpositive other_scale fails the cohort; no cap is invented",
                   "lineup": "all eight original names retained"},
            "C2": {"name": "Off-high substitution from original ranks 9-20", "threshold_M": threshold,
                   "threshold_source": "reports/cg_arrow011_hypothesis_freeze.json frozen_definitions.close_vs_high20_is_median",
                   "search_depth": DEPTH,
                   "formula": ("rank one protected; removable = original ranks 2-8 with close_vs_high20 >= M; "
                               "eligible = original ranks 9-20 with close_vs_high20 < M, certified, not already held; "
                               "k = min(removable, eligible); remove the k worst original ranks (8 first), add the k "
                               "best original ranks (9 first); exactly eight unique names"),
                   "sizing": ("compute the frozen R5 tier for every name in the new lineup from its own pre-entry "
                              "features, then budget_scale = T / S so the cohort base total equals the incumbent T"),
                   "missing_data_rule": ("a name with a missing off-high value is neither removable nor eligible; a "
                                         "replacement whose evidence is incomplete is not certified and cannot be chosen; "
                                         "the rule never keeps the original silently nor skips to the next name for a data failure")},
            "C3": {"name": "Combined rank-one reallocation and off-high substitution",
                   "formula": ("start from the C2 substituted lineup and its budget-normalized allocations summing to T; "
                               "apply the C1 1.50x reallocation to the original protected rank-one name, reducing the "
                               "other seven proportionally so the total is still T"),
                   "independence": "built as its own chronological account, never inferred from C1 and C2"}},
        "scoring": {"primary": "complete equity-scaled chronological account from 100,000 with each challenger's own causal signal-close equity path",
                    "secondary": "causal fixed-dollar account with the same base allocations",
                    "splits": "odd-month IS, even-month internal confirmation, ALL; even months are not pristine",
                    "interaction": "interaction = C3 - C1 - C2 + C0 on additive quantities only"},
        # symbol-level candidate identity stays private; the public freeze carries counts and a
        # hash so the certified set is pinned without publishing proprietary selections
        "certified_ranks_9_20_counts": {iso: len(v) for iso, v in sorted(certified.items())},
        "certified_ranks_9_20_sha256": sha_obj({iso: sorted(v) for iso, v in certified.items()}),
        "certified_ranks_9_20_detail": "handoff/outgoing/cg_arrow012/certified_candidates.json (git-ignored)",
        "substitution_plan": frozen_plan,
        "evidence_affected_cohorts": evidence_affected,
        "evidence_sensitivity": {
            "declared": "before any challenger economics were computed",
            "rule": ("C2R and C3R are C2 and C3 with every cohort in evidence_affected_cohorts reverted to "
                     "the incumbent top-eight lineup and incumbent allocations. They exist so the C2/C3 "
                     "conclusion can be tested without the cohorts whose substitution depended on a data "
                     "failure. If the sign of the C2 or C3 conclusion depends on those cohorts, the "
                     "challenger is reported inconclusive rather than scored through them."),
            "cohorts": sorted(evidence_affected)},
        "substitution_totals": {"cohorts_with_swaps": sum(1 for p in plans.values() if p["k"] > 0),
                                "total_swaps": sum(p["k"] for p in plans.values()),
                                "by_k": {str(k): v for k, v in sorted(ks.items())}},
        "frozen_controls": control_check, "book_census": census,
        "input_hashes": {"a8_manifest": digest(REPORTS / "cg_arrow008_manifest.json"),
                         "a10_manifest": digest(REPORTS / "cg_arrow010_manifest.json"),
                         "a11_freeze": digest(REPORTS / "cg_arrow011_hypothesis_freeze.json"),
                         "a11_trade_atlas": digest(REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011" / "trade_atlas.csv"),
                         "action_table": digest(ACTION_PATH),
                         "a8_trades": digest(A8 / "r4r5_verified_trades.csv"),
                         "a10_trades": digest(A10 / "r4r5_verified_trades.csv"),
                         "top20_candidate_audit": digest(OUT / "top20_candidate_audit.csv"),
                         "substitution_pairs": digest(OUT / "substitution_pairs.csv")},
        "code_hashes": {p: digest(REPO_ROOT / p) for p in (
            "src/verification/r4r5_challenger.py", "src/verification/r4r5_repaired_stats.py",
            "src/verification/r4r5_replay.py", "src/verification/r4r5_equity.py",
            "src/verification/r4r5_anatomy.py", "src/verification/r4r5_data.py",
            "scripts/cg_arrow012_candidates.py")},
        "post_freeze_rule": "no threshold, multiplier, search depth, lineup rule or budget rule may change after this commit",
        "blockers": blockers,
    }
    dump_json(OUT / "certified_candidates.json", {"threshold_M": threshold, "search_depth": DEPTH,
                                                  "certified": {iso: sorted(v) for iso, v in sorted(certified.items())},
                                                  "substitution_plan_symbols": {
                                                      iso: {"outgoing": [h["symbol"] for h in p["outgoing"]],
                                                            "incoming": [h["symbol"] for h in p["incoming"]],
                                                            "lineup": [h["symbol"] for h in p["lineup"]]}
                                                      for iso, p in plans.items()}})
    dump_json(REPORTS / "cg_arrow012_challenger_freeze.json", freeze)
    dump_json(CACHE / "candidates_manifest.json", {
        "timestamp": stamp(), "control_check": control_check, "census": census,
        "certified_counts": {iso: len(v) for iso, v in certified.items()},
        "off_high": {f"{k[0]}/{k[1]}": v for k, v in off_high.items()},
        "plans": frozen_plan, "blockers": blockers, "coverage": coverage, "log": LOG})
    note(f"challenger freeze written; blockers={blockers}")
    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
