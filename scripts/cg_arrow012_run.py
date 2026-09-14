"""CG Arrow 012 Phase B — score C0/C1/C2/C3 as complete chronological accounts.

Every challenger is replayed independently under the unchanged engine: same universe, ranking
rule, entry and exit sessions, causal pre-order prices, integer-share flooring and costs. Only
the lineup (C2, C3) and the relative base allocation (C1, C3) move, and cohort base capital T
is identical in all four. The equity-scaled account is primary and uses each challenger's own
causal signal-close equity path; the fixed-dollar account is the non-compounded diagnostic.

Usage: python scripts/cg_arrow012_run.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_accounting as acct  # noqa: E402
from verification import r4r5_anatomy as an  # noqa: E402
from verification import r4r5_challenger as ch  # noqa: E402
from verification import r4r5_equity as eq  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_metrics as met  # noqa: E402
from verification import r4r5_monthly as mon  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    FEATS, INDEX, VERIFY_ROOT, digest, dump_json, features, history, read_json,
    set_vendor_status, stamp,
)
from verification.r4r5_replay import COMPLETED, replay, sizing  # noqa: E402
from cg_arrow007_run import candidate_meta  # noqa: E402
from cg_arrow010_run import build_substrate  # noqa: E402

OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow012"
CACHE = VERIFY_ROOT / "a12"
HOLD = 10
START = 100000.0
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
          "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
NAMES = {"C0": "Incumbent Momentum+Volume R5", "C1": "Rank-one 1.50x reallocation",
         "C2": "Off-high substitution", "C3": "Combined reallocation and substitution",
         "C2R": "Off-high substitution, evidence-affected cohorts reverted",
         "C3R": "Combined, evidence-affected cohorts reverted"}
FOOTNOTE = ("Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, "
            "dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills "
            "and availability are modeled, not broker execution guarantees.")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []
    freeze = read_json(REPORTS / "cg_arrow012_challenger_freeze.json")
    FROZEN = set(freeze["holdout_embargo"]["frozen_cohort_ids"])
    threshold = freeze["challengers"]["C2"]["threshold_M"]
    affected = set(freeze["evidence_sensitivity"]["cohorts"])
    priv = read_json(OUT / "certified_candidates.json")
    certified = {k: set(v) for k, v in priv["certified"].items()}

    # ---- freeze integrity before scoring
    drift = {p: {"frozen": h, "now": digest(REPO_ROOT / p), "ok": digest(REPO_ROOT / p) == h}
             for p, h in freeze["code_hashes"].items()}
    committed = subprocess.run(["git", "log", "-1", "--format=%H", "--", "reports/cg_arrow012_challenger_freeze.json"],
                               cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    bad = [k for k, v in drift.items() if not v["ok"]]
    note(f"freeze committed at {committed[:7]}; code drift since freeze: {bad or 'none'}")
    if not committed:
        blockers.append("the challenger freeze is not committed")

    corrected, summaries, coverage = build_substrate(args.workers)
    corrected = [c for c in corrected if c["signal_iso"] in FROZEN]
    assert len(corrected) == 52
    cohort_field = read_json(VERIFY_ROOT / "work" / "cohort_field.json")
    meta = candidate_meta(sorted(cohort_field))
    status_map = rep.session_status_map()
    set_vendor_status(status_map)
    deep = {}
    for c in corrected:
        iso = c["signal_iso"]
        cands = {s: meta[iso][s] for s in cohort_field[iso]["rule_field"] if s in meta[iso]}
        deep[iso] = rank.rank_cohort(c["signal"], cands, summaries, status_map)["rows"][:ch.SUBSTITUTION_SEARCH_DEPTH]

    # ---- observations for every rank 1-20 name (cached from the candidate run)
    from verification.r4r5_data import load_summaries, LOCAL_TAPE_END
    need = set()
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in deep[c["signal_iso"]]:
            for d in FEATS[max(0, i - 22): fi + HOLD + 1]:
                need.add((d.isoformat(), h["symbol"]))
            for d in FEATS[fi + HOLD + 1:]:
                if d <= LOCAL_TAPE_END:
                    need.add((d.isoformat(), h["symbol"]))
    summaries.update(load_summaries(need - set(summaries), args.workers))

    # ---- per-cohort features, base notionals, off-high, lineups and allocations
    feats, off_high = {}, {}
    for c in corrected:
        iso, signal = c["signal_iso"], c["signal"]
        for h in deep[iso]:
            sym = h["symbol"]
            feats[(iso, sym)] = features(history(sym, FEATS[INDEX[signal] - 20: INDEX[signal] + 1], signal, summaries))
            off_high[(iso, sym)] = an.signal_close_features(sym, signal, summaries)["close_vs_high20"]

    lineups: dict[str, list[dict]] = {k: [] for k in ("C0", "C1", "C2", "C3", "C2R", "C3R")}
    alloc: dict[str, dict] = {k: {} for k in ("C0", "C1", "C2", "C3", "C2R", "C3R")}
    alloc_rows, plan_detail = [], {}
    for c in corrected:
        iso = c["signal_iso"]
        top8 = deep[iso][:8]
        f8 = {h["symbol"]: feats[(iso, h["symbol"])] for h in top8}
        base8 = ch.base_notionals(top8, f8)
        T = sum(v["base"] for v in base8.values())
        protected = sorted(top8, key=lambda h: h["rank"])[0]["symbol"]

        c0 = ch.cohort_with_rows(c, top8)
        lineups["C0"].append(c0)
        for s, v in base8.items():
            alloc["C0"][f"{iso}/{s}"] = v["base"]

        r1 = ch.c1_allocation(top8, base8)
        if not r1["ok"]:
            blockers.append(f"C1 failed cohort {iso}: {r1['reason']}")
            continue
        lineups["C1"].append(c0)
        for s, v in r1["allocation"].items():
            alloc["C1"][f"{iso}/{s}"] = v

        oh = {h["symbol"]: off_high[(iso, h["symbol"])] for h in deep[iso]}
        plan = ch.substitution_plan(top8, deep[iso][8:], oh, threshold, certified.get(iso, set()))
        if not plan["unique"]:
            blockers.append(f"C2 lineup for {iso} is not eight unique names")
            continue
        fnew = {h["symbol"]: feats[(iso, h["symbol"])] for h in plan["lineup"]}
        base_new = ch.base_notionals(plan["lineup"], fnew)
        r2 = ch.c2_allocation(plan["lineup"], base_new, T)
        if not r2["ok"]:
            blockers.append(f"C2 failed cohort {iso}: {r2['reason']}")
            continue
        c2c = ch.cohort_with_rows(c, plan["lineup"])
        lineups["C2"].append(c2c)
        for s, v in r2["allocation"].items():
            alloc["C2"][f"{iso}/{s}"] = v

        r3 = ch.c3_allocation(plan["lineup"], r2["allocation"], protected)
        if not r3["ok"]:
            blockers.append(f"C3 failed cohort {iso}: {r3['reason']}")
            continue
        lineups["C3"].append(c2c)
        for s, v in r3["allocation"].items():
            alloc["C3"][f"{iso}/{s}"] = v

        # pre-declared sensitivity: evidence-affected cohorts revert to the incumbent lineup
        if iso in affected:
            lineups["C2R"].append(c0)
            lineups["C3R"].append(c0)
            for s, v in base8.items():
                alloc["C2R"][f"{iso}/{s}"] = v["base"]
            for s, v in r1["allocation"].items():
                alloc["C3R"][f"{iso}/{s}"] = v
        else:
            lineups["C2R"].append(c2c)
            lineups["C3R"].append(c2c)
            for s, v in r2["allocation"].items():
                alloc["C2R"][f"{iso}/{s}"] = v
            for s, v in r3["allocation"].items():
                alloc["C3R"][f"{iso}/{s}"] = v

        plan_detail[iso] = plan
        for cfg, a in (("C0", {s: v["base"] for s, v in base8.items()}), ("C1", r1["allocation"]),
                       ("C2", r2["allocation"]), ("C3", r3["allocation"])):
            for s, v in a.items():
                row = next((h for h in (plan["lineup"] if cfg in ("C2", "C3") else top8) if h["symbol"] == s), None)
                alloc_rows.append({"config": cfg, "cohort_id": iso, "split": c["split"], "symbol": s,
                                   "original_rank": row["rank"] if row else None,
                                   "is_protected_rank_one": s == protected,
                                   "base_notional": v, "cohort_total_T": T,
                                   "incumbent_base_notional": base8.get(s, {}).get("base"),
                                   "r5_tier": (base8.get(s) or base_new.get(s, {})).get("tier"),
                                   "substituted_in": cfg in ("C2", "C3") and s not in base8})
    if blockers:
        dump_json(CACHE / "run_manifest.json", {"blockers": blockers, "log": LOG})
        note("STOPPED: " + "; ".join(blockers[:3]))
        return 1
    for cfg in ("C0", "C1", "C2", "C3"):
        tot = defaultdict(float)
        for tid, v in alloc[cfg].items():
            tot[tid.split("/")[0]] += v
        base_tot = defaultdict(float)
        for tid, v in alloc["C0"].items():
            base_tot[tid.split("/")[0]] += v
        worst = max(abs(tot[k] - base_tot[k]) for k in base_tot)
        note(f"{cfg}: cohort base capital T preserved on all 52 cohorts, worst deviation {worst:.2e}")
        if worst > 1e-6:
            blockers.append(f"{cfg} does not preserve cohort base capital")
    exp.write_csv(OUT / "cohort_allocation_audit.csv", alloc_rows)

    # ---- replay every configuration: equity-scaled primary, fixed-dollar diagnostic
    books = {}
    for cfg in ("C0", "C1", "C2", "C3", "C2R", "C3R"):
        a = None if cfg == "C0" else alloc[cfg]
        books[(cfg, "EQUITY_SCALED")] = eq.causal_book("R5", lineups[cfg], summaries, hold=HOLD,
                                                       stage=f"{cfg}_EQUITY_SCALED", scaled=True, allocation=a)
        books[(cfg, "FIXED_DOLLAR")] = eq.causal_book("R5", lineups[cfg], summaries, hold=HOLD,
                                                      stage=f"{cfg}_FIXED_DOLLAR", scaled=False, allocation=a)
        for view in ("EQUITY_SCALED", "FIXED_DOLLAR"):
            b = books[(cfg, view)]
            done = [t for t in b["trades"] if t["status"] in COMPLETED]
            note(f"{cfg}/{view}: {len(done)}/{len(b['trades'])} completed, eventual "
                 f"{sum(t['modeled_net'] for t in done):,.2f}, ending equity {b['daily'][-1]['equity']:,.2f}")
    # holdout guard
    scored = {t["cohort_id"] for b in books.values() for t in b["trades"]}
    if scored != FROZEN:
        blockers.append(f"scored cohorts are not exactly the frozen 52: extra {sorted(scored - FROZEN)[:3]}")
    note(f"holdout guard: scored cohort ids == frozen 52: {scored == FROZEN}")

    # ---- C0 must reproduce Arrow 010 exactly
    a10 = read_json(REPORTS / "cg_arrow010_manifest.json")
    c0e = books[("C0", "EQUITY_SCALED")]
    c0f = books[("C0", "FIXED_DOLLAR")]
    repro = {
        "equity_scaled_eventual": {"expected": 230566.36,
                                   "observed": sum(t["modeled_net"] for t in c0e["trades"] if t["status"] in COMPLETED)},
        "equity_scaled_ending_equity": {"expected": 330719.74, "observed": c0e["daily"][-1]["equity"]},
        "fixed_dollar_eventual": {"expected": 128864.62,
                                  "observed": sum(t["modeled_net"] for t in c0f["trades"] if t["status"] in COMPLETED)},
        "fixed_dollar_ending_equity": {"expected": 228986.40, "observed": c0f["daily"][-1]["equity"]},
    }
    for k, v in repro.items():
        v["ok"] = abs(v["observed"] - v["expected"]) < 0.005
        note(f"C0 reproduces Arrow 010 {k}: expected {v['expected']:,.2f} observed {v['observed']:,.2f} ok={v['ok']}")
    if not all(v["ok"] for v in repro.values()):
        blockers.append("C0 does not reproduce Arrow 010")
        dump_json(CACHE / "run_manifest.json", {"blockers": blockers, "c0_reproduction": repro, "log": LOG})
        return 1

    # ---- accounts, metrics, monthly
    accounts, headline, monthly, recon = {}, {}, {}, {}
    split_books = {}
    for (cfg, view), b in books.items():
        key = f"{cfg}/{view}"
        accounts[key] = acct.account_view(b, summaries, f"{NAMES[cfg]} / {view}")
        headline[key] = met.headline(b, accounts[key], START)
        table = mon.monthly_account(b["daily"], START)
        monthly[key] = table
        recon[key] = mon.reconcile(table, accounts[key]["B_marked_account_pnl_at_cutoff"], START)
        if [r["month"] for r in table] != MONTHS or not recon[key]["reconciles"]:
            blockers.append(f"{key} monthly table does not reconcile")
    for cfg in ("C0", "C1", "C2", "C3"):
        for split in ("IS", "OOS"):
            subset = [c for c in lineups[cfg] if c["split"] == split]
            a = None if cfg == "C0" else alloc[cfg]
            sb = eq.causal_book("R5", subset, summaries, hold=HOLD, stage=f"{cfg}_{split}", scaled=True, allocation=a)
            split_books[(cfg, split)] = sb
            accounts[f"{cfg}/EQUITY_SCALED/{split}"] = acct.account_view(sb, summaries, f"{NAMES[cfg]} / {split}")
            headline[f"{cfg}/EQUITY_SCALED/{split}"] = met.headline(sb, accounts[f"{cfg}/EQUITY_SCALED/{split}"], START)
    bad_id = [k for k, v in accounts.items() if not v["identities_hold"]]
    note(f"account identities hold: {len(accounts) - len(bad_id)}/{len(accounts)}; monthly reconcile: "
         f"{sum(1 for v in recon.values() if v['reconciles'])}/{len(recon)}")
    if bad_id:
        blockers.append(f"account identities fail for {bad_id[:3]}")

    # ---- private ledgers and the independent oracle
    export = {("R5", f"{cfg}_{view}"): b for (cfg, view), b in books.items()}
    files = exp.export_all(export, root=OUT)
    orc = oracle.run(OUT, summaries)
    note(f"independent oracle on all challenger ledgers: ok={orc['ok']} trades={orc['trades']['checked']} "
         f"max_err={orc['trades']['max_abs_error']:.1e} daily_books={len(orc['daily'])}")
    if not orc["ok"]:
        blockers.append("the independent oracle did not reconcile a challenger ledger")
    # independent recomputation of allocation and shares from stored inputs
    stored = oracle.read_csv(OUT / "r4r5_verified_trades.csv")
    alloc_check = {"checked": 0, "errors": 0, "max_share_error": 0.0, "failures": []}
    import math as _m
    for r in stored:
        cfg = r["replay_stage"].rsplit("_", 2)[0]
        if cfg not in alloc or r["replay_stage"].endswith("_IS") or r["replay_stage"].endswith("_OOS"):
            continue
        want = alloc[cfg].get(r["ticket_id"]) if cfg != "C0" else alloc["C0"].get(r["ticket_id"])
        pre, q = r.get("preorder_price"), r.get("quantity")
        if want is None or not pre or q in ("", None):
            continue
        f = float(r["sizing_scale_factor"])
        expect = _m.floor(want * f / float(pre))
        alloc_check["checked"] += 1
        err = abs(expect - float(q))
        alloc_check["max_share_error"] = max(alloc_check["max_share_error"], err)
        if err > 0:
            alloc_check["errors"] += 1
            alloc_check["failures"].append(f"{r['replay_stage']}/{r['ticket_id']} {q} vs {expect}")
    alloc_check["failures"] = alloc_check["failures"][:8]
    alloc_check["ok"] = alloc_check["errors"] == 0
    note(f"independent allocation/share recomputation: {alloc_check['checked']} tickets, "
         f"{alloc_check['errors']} disagreements, max share error {alloc_check['max_share_error']}")
    if not alloc_check["ok"]:
        blockers.append("independent share recomputation disagrees with the challenger engine")

    # ---- public tables
    acc_rows = []
    for key in sorted(accounts):
        cfg = key.split("/")[0]
        view = key.split("/")[1]
        split = key.split("/")[2] if key.count("/") == 2 else "ALL"
        # a split row must read its own split-owned book, never the all-cohort one, so its
        # intended/completed/open counts and risk metrics describe that split's positions
        b = books.get((cfg, view)) if split == "ALL" else split_books.get((cfg, split))
        if b is None:
            continue
        h = headline[key]
        v = accounts[key]
        done = [t for t in b["trades"] if t["status"] in COMPLETED]
        wins = [t["modeled_net"] for t in done if t["modeled_net"] > 0]
        losses = [t["modeled_net"] for t in done if t["modeled_net"] < 0]
        by_sym = defaultdict(float)
        r1_net = 0.0
        for t in b["trades"]:
            if t["status"] in COMPLETED:
                by_sym[t["symbol"]] += t["modeled_net"]
                if t["rank"] == 1:
                    r1_net += t["modeled_net"]
        gross_tot = sum(t["quantity"] * t["entry_price"] for t in b["trades"] if t.get("quantity") and t.get("entry_price"))
        r1_expo = sum(t["quantity"] * t["entry_price"] for t in b["trades"]
                      if t["rank"] == 1 and t.get("quantity") and t.get("entry_price"))
        acc_rows.append({
            "config": cfg, "config_name": NAMES[cfg], "view": view, "split": split,
            "intended": len(b["trades"]), "filled": sum(1 for t in b["trades"] if t.get("quantity")),
            "completed": len(done), "open_documented": v["E_open_documented_obligations"],
            "starting_equity": START, "ending_marked_equity": round(h["ending_marked_equity_at_cutoff"], 2),
            "marked_account_pnl_at_2026_08_31": round(v["B_marked_account_pnl_at_cutoff"], 2),
            "eventual_completed_trade_pnl": round(v["A_completed_trade_pnl_all_cohorts"], 2),
            "return_on_starting_equity_pct": round(h["return_on_starting_equity_pct"], 2),
            "wins": len(wins), "losses": len(losses), "flats": len(done) - len(wins) - len(losses),
            "hit_rate": round(len(wins) / len(done), 4) if done else None,
            "avg_winner": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loser": round(sum(losses) / len(losses), 2) if losses else None,
            "payoff_ratio": round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else None,
            "profit_factor": round(sum(wins) / -sum(losses), 4) if losses else None,
            "max_drawdown_dollars": round(h["max_drawdown_dollars"], 2),
            "max_drawdown_pct_of_peak": round(h["max_drawdown_pct_of_peak"], 2),
            "worst_day": round(h["worst_day"], 2), "time_underwater_pct": round(h["time_underwater_pct"], 2),
            "mean_gross_exposure": round(h["mean_gross_exposure"], 2),
            "peak_gross_exposure": round(h["peak_gross_exposure"], 2),
            "mean_gross_over_marked_equity": round(h["mean_gross_over_marked_equity"], 4),
            "p95_gross_over_marked_equity": round(h["p95_gross_over_marked_equity"], 4),
            "peak_gross_over_marked_equity": round(h["peak_gross_over_marked_equity"], 4),
            "turnover_entry_notional": round(h["turnover_entry_notional"], 2),
            "rank_one_entry_notional_share": round(r1_expo / gross_tot, 4) if gross_tot else None,
            "rank_one_pnl_share": round(r1_net / v["A_completed_trade_pnl_all_cohorts"], 4) if v["A_completed_trade_pnl_all_cohorts"] else None,
            "largest_single_name_pnl_share": round(max(by_sym.values()) / v["A_completed_trade_pnl_all_cohorts"], 4) if by_sym and v["A_completed_trade_pnl_all_cohorts"] else None,
            "distinct_securities": len(by_sym),
            "positive_months": h["positive_months"], "red_months": h["red_months"],
            "flat_months": 12 - h["positive_months"] - h["red_months"],
            "sum_of_red_months": round(h["sum_of_red_months"], 2),
            "worst_month": round(h["worst_month"], 2), "best_month": round(h["best_month"], 2),
            "median_month": round(h["median_month"], 2),
            "runoff_trade_count": v["runoff_trade_count"],
            "post_cutoff_incremental_runoff_pnl": round(v["C_post_cutoff_incremental_runoff_pnl"], 2),
            "eventual_pnl_of_runoff_trades": round(v["D_eventual_pnl_of_runoff_trades"], 2),
            "stale_gross_at_boundary": round(v["F_stale_gross_in_calendar_equity"], 2),
            "identities_hold": v["identities_hold"],
            "monthly_reconciles": recon.get(key, {}).get("reconciles"),
            "footnote": FOOTNOTE})
    exp.write_csv(REPORTS / "cg_arrow012_account_summary.csv", acc_rows)

    monthly_rows = []
    for key in sorted(monthly):
        cfg, view = key.split("/")
        prior = START
        for r in monthly[key]:
            end = round(r["month_end_equity"], 2)
            pnl = round(end - prior, 2)
            monthly_rows.append({"month": r["month"], "config": cfg, "config_name": NAMES[cfg], "view": view,
                                 "monthly_pnl": pnl, "monthly_return_pct": round(pnl / prior * 100, 4),
                                 "month_end_equity": end, "prior_month_end_equity": prior,
                                 "reporting_standard": mon.STANDARD_ID, "footnote": FOOTNOTE})
            prior = end
    exp.write_csv(REPORTS / "cg_arrow012_monthly_account.csv", monthly_rows)

    # ---- substitution attribution
    sub_rows, pair_rows = [], []
    c0_by = {t["ticket_id"]: t for t in books[("C0", "FIXED_DOLLAR")]["trades"]}
    c2_by = {t["ticket_id"]: t for t in books[("C2", "FIXED_DOLLAR")]["trades"]}
    out_ret, in_ret, out_dist, in_dist, out_net, in_net = [], [], [], [], [], []
    for iso, plan in plan_detail.items():
        for a, b in zip(plan["outgoing"], plan["incoming"]):
            ta, tb = c0_by.get(f"{iso}/{a['symbol']}"), c2_by.get(f"{iso}/{b['symbol']}")
            ra = an.sizing_neutral_outcome(ta)["price_return_10"] if ta else None
            rb = an.sizing_neutral_outcome(tb)["price_return_10"] if tb else None
            na = ta["modeled_net"] if ta and ta["status"] in COMPLETED else None
            nb = tb["modeled_net"] if tb and tb["status"] in COMPLETED else None
            if ra is not None:
                out_ret.append(ra)
            if rb is not None:
                in_ret.append(rb)
            out_dist.append(off_high[(iso, a["symbol"])])
            in_dist.append(off_high[(iso, b["symbol"])])
            if na is not None:
                out_net.append(na)
            if nb is not None:
                in_net.append(nb)
            pair_rows.append({"cohort_id": iso, "outgoing_symbol": a["symbol"], "outgoing_rank": a["rank"],
                              "incoming_symbol": b["symbol"], "incoming_rank": b["rank"],
                              "outgoing_close_vs_high20": off_high[(iso, a["symbol"])],
                              "incoming_close_vs_high20": off_high[(iso, b["symbol"])],
                              "outgoing_price_return_10": ra, "incoming_price_return_10": rb,
                              "outgoing_fixed_net": na, "incoming_fixed_net": nb})
    exp.write_csv(OUT / "substitution_paired_outcomes.csv", pair_rows)
    ks = Counter(p["k"] for p in plan_detail.values())
    sub_rows.append({
        "metric": "cohorts_by_substitution_count", "value": json.dumps({str(k): v for k, v in sorted(ks.items())}),
        "basis": "number of cohorts making 0,1,2,... swaps"})
    for label, val, basis in (
        ("total_swaps", sum(p["k"] for p in plan_detail.values()), "outgoing/incoming pairs across all cohorts"),
        ("mean_outgoing_original_rank", statistics.mean(p["outgoing_rank"] for p in pair_rows), "original rank of removed names"),
        ("mean_incoming_original_rank", statistics.mean(p["incoming_rank"] for p in pair_rows), "original rank of added names"),
        ("mean_outgoing_close_vs_high20", statistics.mean(out_dist), "distance from the 20-session high, removed"),
        ("median_outgoing_close_vs_high20", statistics.median(out_dist), "distance from the 20-session high, removed"),
        ("mean_incoming_close_vs_high20", statistics.mean(in_dist), "distance from the 20-session high, added"),
        ("median_incoming_close_vs_high20", statistics.median(in_dist), "distance from the 20-session high, added"),
        ("mean_outgoing_price_return_10", statistics.mean(out_ret), "sizing-neutral ten-session short return, removed"),
        ("mean_incoming_price_return_10", statistics.mean(in_ret), "sizing-neutral ten-session short return, added"),
        ("median_outgoing_price_return_10", statistics.median(out_ret), "sizing-neutral, removed"),
        ("median_incoming_price_return_10", statistics.median(in_ret), "sizing-neutral, added"),
        ("outgoing_hit_rate", sum(1 for x in out_ret if x > 0) / len(out_ret), "share of removed names that faded"),
        ("incoming_hit_rate", sum(1 for x in in_ret if x > 0) / len(in_ret), "share of added names that faded"),
        ("profit_forfeited_on_outgoing_winners", sum(x for x in out_net if x > 0), "fixed-dollar net of removed names that won"),
        ("loss_avoided_on_outgoing_losers", -sum(x for x in out_net if x < 0), "fixed-dollar net avoided on removed names that lost"),
        ("profit_gained_on_incoming_winners", sum(x for x in in_net if x > 0), "fixed-dollar net of added names that won"),
        ("loss_added_on_incoming_losers", sum(x for x in in_net if x < 0), "fixed-dollar net lost on added names that lost"),
        ("net_fixed_dollar_swap_effect", sum(in_net) - sum(out_net), "added minus removed, fixed-dollar, at equalized cohort budget"),
    ):
        sub_rows.append({"metric": label, "value": round(val, 6) if isinstance(val, float) else val, "basis": basis})
    for cfg in ("C2", "C2R", "C3", "C3R"):
        for view in ("FIXED_DOLLAR", "EQUITY_SCALED"):
            d = accounts[f"{cfg}/{view}"]["B_marked_account_pnl_at_cutoff"] - accounts[f"C0/{view}"]["B_marked_account_pnl_at_cutoff"]
            sub_rows.append({"metric": f"{cfg}_minus_C0_marked_pnl_{view}", "value": round(d, 2),
                             "basis": "complete account marked P&L at 2026-08-31 minus the incumbent"})
    exp.write_csv(REPORTS / "cg_arrow012_substitution_summary.csv", sub_rows)

    # ---- interaction
    inter_rows = []
    for view in ("FIXED_DOLLAR", "EQUITY_SCALED"):
        for label, field in (("eventual_completed_trade_pnl", "A_completed_trade_pnl_all_cohorts"),
                             ("marked_account_pnl_at_cutoff", "B_marked_account_pnl_at_cutoff")):
            v = {c: accounts[f"{c}/{view}"][field] for c in ("C0", "C1", "C2", "C3")}
            inter = v["C3"] - v["C1"] - v["C2"] + v["C0"]
            inter_rows.append({"view": view, "quantity": label, "additive": True,
                               "C0": round(v["C0"], 2), "C1": round(v["C1"], 2), "C2": round(v["C2"], 2), "C3": round(v["C3"], 2),
                               "C1_minus_C0": round(v["C1"] - v["C0"], 2), "C2_minus_C0": round(v["C2"] - v["C0"], 2),
                               "C3_minus_C0": round(v["C3"] - v["C0"], 2),
                               "sum_of_parts_C1_plus_C2_minus_C0": round(v["C1"] + v["C2"] - v["C0"], 2),
                               "interaction_C3_minus_C1_minus_C2_plus_C0": round(inter, 2),
                               "basis": "interaction = C3 - C1 - C2 + C0 on an additive quantity"})
        for label, field in (("max_drawdown_dollars", "max_drawdown_dollars"),
                             ("max_drawdown_pct_of_peak", "max_drawdown_pct_of_peak"),
                             ("worst_day", "worst_day"), ("peak_gross_over_marked_equity", "peak_gross_over_marked_equity"),
                             ("mean_gross_over_marked_equity", "mean_gross_over_marked_equity"),
                             ("hit_rate", "hit_rate")):
            v = {c: headline[f"{c}/{view}"][field] for c in ("C0", "C1", "C2", "C3")}
            inter_rows.append({"view": view, "quantity": label, "additive": False,
                               "C0": round(v["C0"], 4), "C1": round(v["C1"], 4), "C2": round(v["C2"], 4), "C3": round(v["C3"], 4),
                               "C1_minus_C0": None, "C2_minus_C0": None, "C3_minus_C0": None,
                               "sum_of_parts_C1_plus_C2_minus_C0": None, "interaction_C3_minus_C1_minus_C2_plus_C0": None,
                               "basis": "nonlinear risk metric: four actual values side by side, no additive decomposition"})
    exp.write_csv(REPORTS / "cg_arrow012_interaction.csv", inter_rows)

    # ---- rank-one reallocation attribution
    r1_rows = []
    for view in ("FIXED_DOLLAR", "EQUITY_SCALED"):
        b0, b1 = books[("C0", view)], books[("C1", view)]
        n0 = {t["ticket_id"]: t for t in b0["trades"]}
        n1 = {t["ticket_id"]: t for t in b1["trades"]}
        r1_extra = sum((n1[k]["modeled_net"] or 0) - (n0[k]["modeled_net"] or 0)
                       for k in n0 if n0[k]["rank"] == 1 and n0[k]["status"] in COMPLETED)
        rest = sum((n1[k]["modeled_net"] or 0) - (n0[k]["modeled_net"] or 0)
                   for k in n0 if n0[k]["rank"] != 1 and n0[k]["status"] in COMPLETED)
        worst0 = min((n0[k]["modeled_net"] for k in n0 if n0[k]["rank"] == 1 and n0[k]["status"] in COMPLETED), default=0.0)
        worst1 = min((n1[k]["modeled_net"] for k in n1 if n1[k]["rank"] == 1 and n1[k]["status"] in COMPLETED), default=0.0)
        r1_rows.append({"view": view,
                        "extra_pnl_from_larger_rank_one": round(r1_extra, 2),
                        "pnl_change_from_reducing_ranks_2_8": round(rest, 2),
                        "net_change_vs_incumbent": round(r1_extra + rest, 2),
                        "account_marked_pnl_change": round(accounts[f"C1/{view}"]["B_marked_account_pnl_at_cutoff"]
                                                           - accounts[f"C0/{view}"]["B_marked_account_pnl_at_cutoff"], 2),
                        "worst_rank_one_loss_incumbent": round(worst0, 2),
                        "worst_rank_one_loss_challenger": round(worst1, 2),
                        "rank_one_entry_notional_share_incumbent": next(r["rank_one_entry_notional_share"] for r in acc_rows if r["config"] == "C0" and r["view"] == view and r["split"] == "ALL"),
                        "rank_one_entry_notional_share_challenger": next(r["rank_one_entry_notional_share"] for r in acc_rows if r["config"] == "C1" and r["view"] == view and r["split"] == "ALL"),
                        "max_drawdown_incumbent": round(headline[f"C0/{view}"]["max_drawdown_dollars"], 2),
                        "max_drawdown_challenger": round(headline[f"C1/{view}"]["max_drawdown_dollars"], 2),
                        "worst_day_incumbent": round(headline[f"C0/{view}"]["worst_day"], 2),
                        "worst_day_challenger": round(headline[f"C1/{view}"]["worst_day"], 2),
                        "mean_gross_over_equity_incumbent": round(headline[f"C0/{view}"]["mean_gross_over_marked_equity"], 4),
                        "mean_gross_over_equity_challenger": round(headline[f"C1/{view}"]["mean_gross_over_marked_equity"], 4),
                        "basis": "trade-level differences use the same ticket ids; the account row is the complete rebuilt account"})
    exp.write_csv(REPORTS / "cg_arrow012_rank_one_attribution.csv", r1_rows)

    # ---- why C2 moves: removed, added and retained-but-resized tickets, exactly
    c2_decomp = {}
    for view in ("FIXED_DOLLAR", "EQUITY_SCALED"):
        b0 = {t["ticket_id"]: t for t in books[("C0", view)]["trades"]}
        b2 = {t["ticket_id"]: t for t in books[("C2", view)]["trades"]}
        net = lambda t: (t["modeled_net"] or 0.0) if t and t["status"] in COMPLETED else 0.0  # noqa: E731
        removed, added, kept = sorted(set(b0) - set(b2)), sorted(set(b2) - set(b0)), sorted(set(b0) & set(b2))
        rp = -sum(net(b0[k]) for k in removed)
        ap = sum(net(b2[k]) for k in added)
        kp = sum(net(b2[k]) - net(b0[k]) for k in kept)
        q0 = sum((b0[k]["quantity"] or 0) * (b0[k]["entry_price"] or 0) for k in kept)
        q2 = sum((b2[k]["quantity"] or 0) * (b2[k]["entry_price"] or 0) for k in kept)
        c2_decomp[view] = {
            "removed_tickets": len(removed), "added_tickets": len(added), "retained_tickets": len(kept),
            "pnl_removed_forgone": round(rp, 2), "pnl_added_gained": round(ap, 2),
            "pnl_retained_resized": round(kp, 2),
            "total": round(sum(net(t) for t in b2.values()) - sum(net(t) for t in b0.values()), 2),
            "residual": round(sum(net(t) for t in b2.values()) - sum(net(t) for t in b0.values()) - (rp + ap + kp), 6),
            "retained_entry_notional_C0": round(q0, 2), "retained_entry_notional_C2": round(q2, 2),
            "retained_notional_change_pct": round((q2 / q0 - 1) * 100, 2) if q0 else None,
            "basis": ("removed and added are the 141 swapped tickets; retained are the 275 names in both lineups "
                      "whose only change is the budget-neutral rescaling, so their P&L change is pure resizing")}
        note(f"C2 decomposition {view}: removed {rp:,.0f}, added {ap:,.0f}, retained resized {kp:,.0f}, "
             f"retained notional {c2_decomp[view]['retained_notional_change_pct']:+.2f}%")
    # rank-one base allocation dilution under each challenger
    r1_ratio = {}
    for cfg in ("C1", "C2", "C3"):
        ratios = []
        for c in lineups["C0"]:
            iso = c["signal_iso"]
            protected = sorted(c["rows"], key=lambda h: h["original_rank"])[0]["symbol"]
            b = alloc["C0"][f"{iso}/{protected}"]
            ratios.append(alloc[cfg][f"{iso}/{protected}"] / b)
        r1_ratio[cfg] = {"n": len(ratios), "min": min(ratios), "median": statistics.median(ratios),
                         "max": max(ratios), "mean": statistics.mean(ratios)}
    note(f"rank-one base allocation versus incumbent: "
         + ", ".join(f"{k} median {v['median']:.3f}" for k, v in r1_ratio.items()))

    manifest = {
        "arrow": "CG Arrow 012", "phase": "B_challengers", "timestamp": stamp(),
        "c2_decomposition": c2_decomp, "rank_one_allocation_ratio": r1_ratio,
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "freeze_commit": committed, "code_drift_since_freeze": drift,
        "config_version": ch.CONFIG_VERSION, "holdout_guard_ok": scored == FROZEN,
        "scored_cohort_count": len(scored), "c0_reproduction": repro,
        "accounts": accounts, "headline": headline,
        "monthly_reconciliation": recon, "oracle": orc, "allocation_recomputation": alloc_check,
        "local_files": files, "blockers": blockers, "coverage": coverage, "log": LOG,
    }
    dump_json(CACHE / "run_manifest.json", manifest)
    note(f"challenger scoring complete; blockers={blockers}")
    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
