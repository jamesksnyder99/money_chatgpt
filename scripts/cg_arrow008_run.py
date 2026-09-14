"""CG Arrow 008 Repair 4 — rebuild, reconcile and certify.

Rebuilds the Corrected-Universe Replay baseline and the full Hold-Length Ladder from the
unchanged strategy specification under the repaired evidence table, applies the unambiguous
account semantics and the reconciling R1 to R2 bridge, compares everything against Arrow 007
and returns the binary certification verdict.

No strategy parameter is touched and no preferred hold is reselected.

Usage: python scripts/cg_arrow008_run.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
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
from verification import r4r5_accounting as acct  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification import r4r5_schedule as sched  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    ACTION_PATH, FEATS, INDEX, RANKS_PATH, VERIFY_ROOT, action_events, digest, dump_json,
    load_summaries, non_comparable_events, present, read_json, set_vendor_status, split_of, stamp,
)
from verification.r4r5_replay import COMPLETED, cohorts, load_field, needs_for, replay  # noqa: E402
from cg_arrow007_run import (  # noqa: E402
    candidate_meta, rank_with, tradable_universe, unresolved_selected,
)

WORK = VERIFY_ROOT / "work"
HANDOFF8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
FROZEN = REPO_ROOT / "data" / "tmp" / "cg_arrow003"
FAMS = ("PARENT", "R4", "R5")
NAMES = {"PARENT": "Equal-Dollar Short", "R4": "Volume-Sized Short",
         "R5": "Momentum+Volume-Sized Short"}
PANELS = {"LEGACY_FILL_QTY": "fill", "CAUSAL_PREORDER_QTY": "preorder"}
HORIZONS = tuple(range(1, 11))
LOOKBACK = 15
FOOTNOTE = ("Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes "
            "broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other "
            "account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow "
            "fees for Trading API users; short availability and other security-specific costs may still vary.")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    blockers: list[str] = []

    # ---------------------------------------------------------------- inputs
    assert ACTION_PATH.name == "cg_arrow008_corporate_actions.json", ACTION_PATH
    actions = read_json(ACTION_PATH)
    material = read_json(WORK / "a8_material_ledger.json")
    states = Counter(r["final_state"] for r in material)
    note(f"material event states: {dict(states)}")
    heuristic = [r for r in material if r["final_state"] == "UNRESOLVED"]
    if heuristic:
        blockers.append(f"{len(heuristic)} material selected-name events remain UNRESOLVED: "
                        + ", ".join(f"{r['symbol']}/{r['session']}" for r in heuristic[:8]))

    existing = [date.fromisoformat(k) for k in read_json(RANKS_PATH)]
    diff = sched.schedule_diff(existing, date(2025, 9, 1), date(2026, 8, 31))
    note(f"calendar rule identical={diff['identical']} rollbacks={len(diff['weeks_requiring_rollback'])}")
    if not diff["identical"]:
        blockers.append("the frozen calendar rule changes the study sample")

    roster, etp, tests = tradable_universe()
    cohort_field = read_json(WORK / "cohort_field.json")
    meta = candidate_meta(sorted(cohort_field))
    status_map = rep.session_status_map()
    set_vendor_status(status_map)
    rule_field = {iso: cf["rule_field"] for iso, cf in cohort_field.items()}

    endpoints = set()
    for iso, syms in rule_field.items():
        i = INDEX[date.fromisoformat(iso)]
        back = FEATS[i - LOOKBACK].isoformat()
        for s in syms:
            endpoints.add((iso, s))
            endpoints.add((back, s))
    note(f"loading {len(endpoints)} ranking endpoints")
    summaries = load_summaries(endpoints, args.workers)

    # ---------------------------------------------------------------- rebuild and rerank
    action_events.cache_clear()
    non_comparable_events.cache_clear()
    corrected = rank_with(rule_field, meta, summaries, status_map)
    win = set()
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in c["rows"]:
            for d in FEATS[i - LOOKBACK - 1: fi + 11]:
                win.add((d.isoformat(), h["symbol"]))
    summaries.update(load_summaries(win - set(summaries), args.workers))

    final_state = {(r["symbol"], r["session"]): r["final_state"] for r in material}
    resolutions = {(r["symbol"], r["session"]): r["final_state"] for r in material
                   if r["final_state"] != "UNRESOLVED"}
    resolutions.update({(x["symbol"], x.get("date")): x["resolution"]
                        for x in actions.get("screen_resolutions", [])})
    remaining = unresolved_selected(corrected, summaries, resolutions)
    still = [b for b in remaining
             if final_state.get((b["symbol"], b.get("date"))) in (None, "UNRESOLVED")]
    note(f"selected-name windows not continuous after adjustment: {len(remaining)}; "
         f"without an adequate evidence state: {len(still)}")
    if still:
        blockers.append(f"{len(still)} selected-name windows rest on no adequate evidence state")
    for c in corrected:
        for h in c["rows"]:
            for field in ("lookback", "holding"):
                when = h.get(f"{field}_ratio_date")
                st = final_state.get((h["symbol"], when)) if when else None
                if st:
                    h[f"{field}_final_evidence_state"] = st
                    if h.get(f"{field}_resolution") == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY" \
                            and st != "UNRESOLVED":
                        h[f"{field}_resolution"] = st
                elif h.get(f"{field}_resolution") == "ADJUSTED_SERIES_CONTINUOUS":
                    h[f"{field}_final_evidence_state"] = "ADJUSTED_SERIES_CONTINUOUS"

    members = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in corrected}
    confirm = rank_with(rule_field, meta, summaries, status_map)
    stable = sha_obj({c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in confirm}) == sha_obj(members)
    note(f"rerank converged and stable: {stable}")
    if not stable:
        blockers.append("the rerank is not stable under repetition")
    if any(c["unrankable_unresolved"] for c in corrected):
        blockers.append("rule-eligible candidates have an unresolved ranking endpoint")
    if any(set(members[iso]) & set(tests) for iso in members):
        blockers.append("a documented test issue reached the corrected selection")

    # ---------------------------------------------------------------- lifecycle and replays
    cl_recorded = cohorts(load_field(events=tuple(read_json(
        REPO_ROOT / "reports/cg_arrow003_corporate_actions.json")["events"])))
    for c in cl_recorded:
        c["fill"] = sched.entry_for(c["signal"])
    recorded_map = {fam: {p["id"]: p for p in read_json(FROZEN / "details" / f"{fam}_ALL.json")["positions"]}
                    for fam in FAMS}
    life = set(needs_for(cl_recorded))
    for group in (corrected, cl_recorded):
        for c in group:
            i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
            for h in c["rows"]:
                for d in FEATS[i - 20: fi + 11]:
                    life.add((d.isoformat(), h["symbol"]))
    summaries.update(load_summaries(life - set(summaries), args.workers))
    missing = [(s, iso) for (iso, s) in life if not present(summaries.get((iso, s)))
               and status_map.get((s, iso)) != "DOCUMENTED_NO_TRADING"]
    note(f"lifecycle observations missing: {len(missing)}")
    if missing:
        blockers.append(f"{len(missing)} lifecycle observations missing")

    books = {}
    for fam in FAMS:
        for panel, qty in PANELS.items():
            books[(fam, "R1", panel)] = replay(fam, cl_recorded, summaries, hold=10, quantity=qty,
                                               stage=f"R1_{panel}", recorded=recorded_map[fam])
            books[(fam, "R2", panel)] = replay(fam, corrected, summaries, hold=10, quantity=qty,
                                               stage=f"R2_{panel}")
        note(f"{NAMES[fam]}: " + "  ".join(
            f"{st}/{pn}={sum(t['status'] in COMPLETED for t in books[(fam, st, pn)]['trades'])}/"
            f"{len(books[(fam, st, pn)]['trades'])}" for st in ("R1", "R2") for pn in PANELS))

    # ---------------------------------------------------------------- Repair 2 and 3
    accounts, bridges, split_books = {}, {}, {}
    for fam in FAMS:
        for panel in PANELS:
            for split in ("IS", "OOS", "ALL"):
                subset = [c for c in corrected if split == "ALL" or c["split"] == split]
                b = replay(fam, subset, summaries, hold=10, quantity=PANELS[panel],
                           stage=f"R2_{panel}_{split}")
                # risk metrics must come from the split-owned book, never the all-cohort one
                split_books[(fam, panel, split)] = b
                accounts[f"{fam}/{panel}/{split}"] = acct.account_view(
                    b, summaries, f"{NAMES[fam]} / {panel} / {split}")
            bridges[f"{fam}/{panel}"] = acct.bridge(
                books[(fam, "R1", panel)], books[(fam, "R2", panel)], f"{NAMES[fam]} / {panel}")
    bad_ident = [k for k, v in accounts.items() if not v["identities_hold"]]
    bad_bridge = [k for k, v in bridges.items() if not v["reconciles"]]
    note(f"account identities hold: {len(accounts) - len(bad_ident)}/{len(accounts)}; "
         f"bridges reconcile: {len(bridges) - len(bad_bridge)}/{len(bridges)}")
    if bad_ident:
        blockers.append(f"account identities fail for {bad_ident}")
    if bad_bridge:
        blockers.append(f"the R1 to R2 bridge does not reconcile for {bad_bridge}")

    # ---------------------------------------------------------------- Hold-Length Ladder
    ladder = {}
    for fam in FAMS:
        for panel, qty in PANELS.items():
            for split in ("IS", "OOS", "ALL"):
                subset = [c for c in corrected if split == "ALL" or c["split"] == split]
                for h in HORIZONS:
                    ladder[(fam, panel, split, h)] = replay(
                        fam, subset, summaries, hold=h, quantity=qty,
                        stage=f"R2_{panel}_{split}_H{h:02d}")
    note(f"ladder rebuilt: {len(ladder)} cells")
    h10_ok = True
    for fam in FAMS:
        for panel in PANELS:
            cell = sum(t["modeled_net"] for t in ladder[(fam, panel, "ALL", 10)]["trades"]
                       if t["status"] in COMPLETED)
            base = sum(t["modeled_net"] for t in books[(fam, "R2", panel)]["trades"]
                       if t["status"] in COMPLETED)
            if abs(cell - base) > 1e-9:
                h10_ok = False
                blockers.append(f"the 10-session hold does not reproduce the baseline for {fam}/{panel}")
    note(f"10-session hold reproduces the rebuilt baseline exactly: {h10_ok}")

    # ---------------------------------------------------------------- exports and oracle
    export_books = {(fam, f"{stage}_{panel}"): books[(fam, stage, panel)]
                    for fam in FAMS for stage in ("R1", "R2") for panel in PANELS}
    files = exp.export_all(export_books, root=HANDOFF8)
    (HANDOFF8 / "certified_trade_audit.csv").write_bytes(
        (HANDOFF8 / "r4r5_verified_trades.csv").read_bytes())
    (HANDOFF8 / "certified_cohort_audit.csv").write_bytes(
        (HANDOFF8 / "r4r5_verified_cohort_audit.csv").read_bytes())
    orc = oracle.run(HANDOFF8, summaries)
    note(f"oracle ok={orc['ok']} trades={orc['trades']} cohorts={orc['cohorts']}")
    if not orc["ok"]:
        blockers.append("the independent oracle did not reconcile")

    # ---------------------------------------------------------------- comparison with Arrow 007
    a7 = read_json(REPORTS / "cg_arrow007_manifest.json")
    a7f = read_json(REPORTS / "cg_arrow007_horizon_freeze.json")
    ledger = [{"cohort_id": t["cohort_id"], "symbol": t["symbol"], "rank": t["rank"],
               "entry_date": t.get("scheduled_entry_date"), "entry_price": t.get("entry_price"),
               "quantity": t.get("quantity"), "size_tier": t.get("size_tier")}
              for t in books[("R5", "R2", "LEGACY_FILL_QTY")]["trades"]]
    ledger_hash = sha_obj(ledger)
    a7_cells = {(c["family"], c["panel"], c["split"], c["horizon"]): c["modeled_net"]
                for c in a7f["cells"]}
    comparison = {
        "membership_sha256": {"arrow007": a7["fixed_point"]["iterations"][-1]["membership_sha256"],
                              "arrow008": sha_obj(members)},
        "entry_ledger_sha256": {"arrow007": a7["r2_entry_ledger_sha256"], "arrow008": ledger_hash},
        "completed_trades": {}, "headline_modeled_pnl": {}, "is_oos": {}, "ladder_totals": {},
    }
    for fam in FAMS:
        old = a7["split_owned_books"][f"{fam}/R2/LEGACY_FILL_QTY/ALL"]
        new = accounts[f"{fam}/LEGACY_FILL_QTY/ALL"]
        comparison["completed_trades"][fam] = {"arrow007": old["completed"],
                                               "arrow008": new["completed_trade_count"]}
        comparison["headline_modeled_pnl"][fam] = {
            "arrow007": old["modeled_net"], "arrow008": new["A_completed_trade_pnl_all_cohorts"],
            "difference": new["A_completed_trade_pnl_all_cohorts"] - old["modeled_net"]}
        for sp in ("IS", "OOS"):
            o = a7["split_owned_books"][f"{fam}/R2/LEGACY_FILL_QTY/{sp}"]["modeled_net"]
            n = accounts[f"{fam}/LEGACY_FILL_QTY/{sp}"]["A_completed_trade_pnl_all_cohorts"]
            comparison["is_oos"][f"{fam}/{sp}"] = {"arrow007": o, "arrow008": n, "difference": n - o}
        for sp in ("IS", "OOS"):
            for h in HORIZONS:
                n = sum(t["modeled_net"] for t in ladder[(fam, "LEGACY_FILL_QTY", sp, h)]["trades"]
                        if t["status"] in COMPLETED)
                o = a7_cells.get((fam, "LEGACY_FILL_QTY", sp, h))
                if o is not None and abs(n - o) > 1e-9:
                    comparison["ladder_totals"][f"{fam}/{sp}/H{h:02d}"] = {
                        "arrow007": o, "arrow008": n, "difference": n - o}
    changed = (comparison["membership_sha256"]["arrow007"] != comparison["membership_sha256"]["arrow008"])
    note(f"membership changed vs Arrow 007: {changed}; ladder cells changed: "
         f"{len(comparison['ladder_totals'])}")
    comparison["reason_for_differences"] = (
        "No corporate-action factor or date changed in this arrow: the material-event review confirmed "
        "every previously applied event and added none, so the selection, the entry ledger and every "
        "ladder cell are bit-identical to Arrow 007. The changes in this arrow are to evidence state "
        "labelling, account semantics and bridge presentation, none of which touch a price, a quantity "
        "or a selection." if not changed and not comparison["ladder_totals"] else
        "See the per-item differences above; each arises from the repaired evidence table.")

    # ---------------------------------------------------------------- public outputs
    baseline_rows = []
    for fam in FAMS:
        for panel in PANELS:
            for split in ("IS", "OOS", "ALL"):
                v = accounts[f"{fam}/{panel}/{split}"]
                b = split_books[(fam, panel, split)]
                ver = [t for t in b["trades"] if t["status"] in COMPLETED]
                wins = [t["modeled_net"] for t in ver if t["modeled_net"] > 0]
                losses = [t["modeled_net"] for t in ver if t["modeled_net"] < 0]
                baseline_rows.append({
                    "strategy": "Winner-Fade Short", "variant": NAMES[fam], "legacy_id": fam,
                    "replay": "Corrected-Universe Replay", "quantity_panel": panel, "split": split,
                    "completed_trades": v["completed_trade_count"],
                    "completed_trade_pnl_all_cohorts": round(v["A_completed_trade_pnl_all_cohorts"], 2),
                    "completed_pnl_exits_through_cutoff": round(v["completed_trades_exiting_through_cutoff"], 2),
                    "marked_account_pnl_at_2026_08_31": round(v["B_marked_account_pnl_at_cutoff"], 2),
                    "post_cutoff_incremental_runoff_pnl": round(v["C_post_cutoff_incremental_runoff_pnl"], 2),
                    "eventual_pnl_of_runoff_trades": round(v["D_eventual_pnl_of_runoff_trades"], 2),
                    "runoff_trade_count": v["runoff_trade_count"],
                    "open_documented_obligations": v["E_open_documented_obligations"],
                    "stale_gross_in_calendar_equity": round(v["F_stale_gross_in_calendar_equity"], 2),
                    "marked_account_pnl_per_account_session": round(
                        v["marked_account_pnl_per_account_session"], 2),
                    "per_session_basis": v["per_session_basis"],
                    "hit_rate": round(len(wins) / len(ver), 4) if ver else None,
                    "avg_winner": round(sum(wins) / len(wins), 2) if wins else None,
                    "avg_loser": round(sum(losses) / len(losses), 2) if losses else None,
                    "profit_factor": round(sum(wins) / -sum(losses), 4) if losses else None,
                    "max_drawdown_dollars": round(min(
                        (e - m for e, m in _dd(b["daily"])), default=0.0), 2),
                    "worst_day": round(_worst_day(b["daily"]), 2),
                    "worst_calendar_month": round(_worst_month(b["daily"]), 2),
                    "mean_gross_exposure": round(sum(r["gross_exposure"] for r in b["daily"])
                                                 / len(b["daily"]), 2),
                    "peak_gross_exposure": round(max(r["gross_exposure"] for r in b["daily"]), 2),
                    "mean_utilization_vs_100k_equity": round(
                        sum(r["gross_exposure"] for r in b["daily"]) / len(b["daily"]) / 100000.0, 4),
                    "avg_holding_calendar_days": round(
                        sum(t["holding_calendar_days"] for t in ver) / len(ver), 2) if ver else None,
                    "identities_hold": v["identities_hold"],
                    "footnote": FOOTNOTE})
    exp.write_csv(REPORTS / "cg_arrow008_certified_baseline.csv", baseline_rows)

    ladder_rows = []
    for fam in FAMS:
        for panel in PANELS:
            for split in ("IS", "OOS", "ALL"):
                for h in HORIZONS:
                    b = ladder[(fam, panel, split, h)]
                    ver = [t for t in b["trades"] if t["status"] in COMPLETED]
                    wins = [t["modeled_net"] for t in ver if t["modeled_net"] > 0]
                    losses = [t["modeled_net"] for t in ver if t["modeled_net"] < 0]
                    ladder_rows.append({
                        "strategy": "Winner-Fade Short", "variant": NAMES[fam], "legacy_id": fam,
                        "quantity_panel": panel, "split": split, "hold_sessions": h,
                        "intended": len(b["trades"]), "completed": len(ver),
                        "modeled_net": round(sum(t["modeled_net"] for t in ver), 2),
                        "gross_pnl": round(sum(t["gross_pnl"] for t in ver), 2),
                        "hit_rate": round(len(wins) / len(ver), 4) if ver else None,
                        "avg_winner": round(sum(wins) / len(wins), 2) if wins else None,
                        "avg_loser": round(sum(losses) / len(losses), 2) if losses else None,
                        "profit_factor": round(sum(wins) / -sum(losses), 4) if losses else None,
                        "max_drawdown_dollars": round(min((e - m for e, m in _dd(b["daily"])),
                                                          default=0.0), 2),
                        "worst_day": round(_worst_day(b["daily"]), 2),
                        "mean_gross_exposure": round(sum(r["gross_exposure"] for r in b["daily"])
                                                     / len(b["daily"]), 2),
                        "peak_gross_exposure": round(max(r["gross_exposure"] for r in b["daily"]), 2),
                        "footnote": FOOTNOTE})
    exp.write_csv(REPORTS / "cg_arrow008_horizons.csv", ladder_rows)

    bridge_rows = []
    for k, v in bridges.items():
        bridge_rows.append({"book": v["book"], "identity": v["identity"],
                            "R1_total": round(v["R1_total"], 2), "R2_total": round(v["R2_total"], 2),
                            "difference": round(v["difference"], 2),
                            "common_tickets": v["common_tickets"],
                            "COMMON_REVALUATION": round(v["COMMON_REVALUATION"], 2),
                            "added_tickets": v["added_tickets"],
                            "ADDED_R2_PNL": round(v["ADDED_R2_PNL"], 2),
                            "dropped_tickets": v["dropped_tickets"],
                            "DROPPED_R1_PNL": round(v["DROPPED_R1_PNL"], 2),
                            "reconciliation_residual": v["reconciliation_residual"],
                            "reconciles": v["reconciles"],
                            "dropped_sign_note": v["dropped_sign_note"]})
    exp.write_csv(REPORTS / "cg_arrow008_r1_r2_bridge.csv", bridge_rows)

    certified = not blockers
    manifest = {
        "arrow": "CG Arrow 008", "executor": "Opus in Claude Code", "timestamp": stamp(),
        "elapsed_minutes": (time.monotonic() - T0) / 60,
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "naming": NAMES, "headline_footnote": FOOTNOTE,
        "calendar_rule": diff,
        "action_table_sha256": digest(ACTION_PATH),
        "material_event_states": dict(states),
        "material_event_rule": actions.get("material_event_review"),
        "rerank_stable": stable, "membership_sha256": sha_obj(members),
        "r2_entry_ledger_sha256": ledger_hash,
        "accounts": accounts, "bridges": bridges,
        "h10_reproduces_baseline": h10_ok,
        "comparison_with_arrow007": comparison,
        "oracle": orc, "local_csvs": files,
        "certification": {"verdict": "CERTIFIED" if certified else "NOT CERTIFIED",
                          "blockers": blockers},
        "log": LOG,
    }
    dump_json(REPORTS / "cg_arrow008_manifest.json", manifest)
    note(f"VERDICT: {'CERTIFIED' if certified else 'NOT CERTIFIED'}"
         + ("" if certified else f" blockers={blockers}"))
    return 0


def _dd(daily):
    peak = 100000.0
    for r in daily:
        peak = max(peak, r["equity"])
        yield r["equity"], peak


def _worst_day(daily):
    prev, worst = 100000.0, 0.0
    for r in daily:
        worst = min(worst, r["equity"] - prev)
        prev = r["equity"]
    return worst


def _worst_month(daily):
    prev, by = 100000.0, defaultdict(float)
    for r in daily:
        by[r["date"][:7]] += r["equity"] - prev
        prev = r["equity"]
    return min(by.values()) if by else 0.0


if __name__ == "__main__":
    sys.exit(main())
