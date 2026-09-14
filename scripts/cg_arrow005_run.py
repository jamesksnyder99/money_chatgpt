"""CG Arrow 005 orchestration: R0 reproduction, pilot, R1/R2 replays, exports, oracle, gate.

Usage: python scripts/cg_arrow005_run.py [--workers 8] [--acquire]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_acquire as acq  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    HANDOFF, LOCAL_TAPE_END, RANKS_PATH, VERIFY_ROOT, digest, dump_json, load_summaries, present, read_json, stamp,
)
from verification.r4r5_replay import VERIFIED, cohorts, load_field, needs_for, replay  # noqa: E402

FROZEN = REPO_ROOT / "data" / "tmp" / "cg_arrow003"
FAMS = ("PARENT", "R4", "R5")


def r0_reproduction() -> dict:
    """Read-only reproduction of the frozen Arrow 003 control records."""
    out = {"source": "data/tmp/cg_arrow003/results and details (frozen, read-only)", "books": {}}
    for fam in FAMS:
        for mode in ("IS", "OOS", "ALL"):
            p = FROZEN / "results" / f"{fam}_{mode}.json"
            r = read_json(p)
            m = r["metrics"]
            det = read_json(REPO_ROOT / r["detail_path"])
            assert digest(REPO_ROOT / r["detail_path"]) == r["detail_sha256"], "frozen detail hash"
            legs = Counter()
            for leg in det["legs"]:
                legs[leg["reason"]] += leg["pnl"]
            out["books"][f"{fam}_{mode}"] = {
                "total_pnl": m["total_pnl"], "per_day": m["per_day"], "trades": m["trades"], "exit_legs": m["exit_legs"],
                "terminal_tickets": m["terminal_tickets"], "terminal_net_mtm": m["terminal_net_mtm"],
                "terminal_stale_gross": m["terminal_stale_gross"], "legs_by_reason": dict(legs),
                "counters": m["counters"], "result_sha256": digest(p), "detail_sha256": r["detail_sha256"]}
    rep = read_json(REPORTS / "cg_arrow003_repair_metrics.json")["reconciliation"]
    out["legacy_is"] = {fam: {"legacy": rep[fam]["legacy"]["total_pnl"], "accounting_only": rep[fam]["accounting_only"]["total_pnl"],
                              "working": rep[fam]["working"]["total_pnl"]} for fam in FAMS}
    out["record_types"] = {"PARENT/R4/R5 frozen books": "original fixed-ticket H10, Arrow 003 working convention (fill-close quantity, delayed backstop at later open, stale marks in totals)",
                           "Arrow 004 BRIDGE_R4/R5": "timing bridge (open prices, preorder quantity) — not replayed in this pass",
                           "Arrow 004 S0_R4/R5": "equity-budgeted variant — not replayed in this pass"}
    return out


def recorded_positions(fam: str) -> dict:
    det = read_json(FROZEN / "details" / f"{fam}_ALL.json")
    return {p["id"]: p for p in det["positions"]}


def reconcile_r0_r1(fam: str, book: dict, r0: dict) -> dict:
    det = read_json(FROZEN / "details" / f"{fam}_ALL.json")
    frozen_ids = {p["id"] for p in det["positions"]}
    mine = {t["ticket_id"]: t for t in book["trades"]}
    filled = {k for k, t in mine.items() if t.get("quantity")}
    scheduled_legs = {leg["ticket_id"]: leg for leg in det["legs"] if leg["reason"] == "backstop"}
    delayed = sum(leg["pnl"] for leg in det["legs"] if leg["reason"] == "delayed_backstop")
    verified = {k: t for k, t in mine.items() if t["status"] == VERIFIED}
    diff = 0.0
    n_match = 0
    for k, t in verified.items():
        leg = scheduled_legs.get(k)
        if leg is None:
            diff += abs(t["modeled_net"])
            continue
        n_match += 1
        diff = max(diff, abs(leg["pnl"] - t["modeled_net"]), abs(leg["shares"] - t["quantity_at_exit"]), abs(leg["exit"] - t["exit_price"]))
    qty_mismatch = sum(1 for k in filled & frozen_ids if mine[k]["quantity"] != recorded_positions(fam)[k]["original_shares"])
    return {"frozen_positions": len(frozen_ids), "r1_filled": len(filled), "identity_equal": filled == frozen_ids,
            "missing_from_r1": sorted(frozen_ids - filled), "extra_in_r1": sorted(filled - frozen_ids),
            "quantity_mismatches": qty_mismatch, "verified_scheduled_exits": len(verified), "frozen_scheduled_legs": len(scheduled_legs),
            "matched_scheduled_legs": n_match, "max_abs_leg_difference": diff,
            "waterfall": {"R0_total": r0["books"][f"{fam}_ALL"]["total_pnl"],
                          "R0_scheduled_exit_legs": sum(l["pnl"] for l in scheduled_legs.values()),
                          "R0_delayed_backstop_legs_diagnostic": delayed,
                          "R0_terminal_mtm_incl_stale": r0["books"][f"{fam}_ALL"]["terminal_net_mtm"],
                          "R1_verified_scheduled_exits_net": sum(t["modeled_net"] for t in verified.values()),
                          "R1_unresolved_slots": sum(t["status"].startswith("UNRESOLVED") for t in mine.values()),
                          "R1_missed_entries": sum(t["status"].startswith("MISSED_ENTRY") for t in mine.values()),
                          "R1_blocked_or_zero": sum(t["status"] in {"BLOCKED_INHERITED_BORROW_PROXY", "ZERO_SHARE_ORDER"} for t in mine.values())}}


def compare_r1_r2(r1: dict, r2: dict, r2c: dict) -> dict:
    a = {t["ticket_id"]: t for t in r1["trades"]}
    b = {t["ticket_id"]: t for t in r2["trades"]}
    c = {t["ticket_id"]: t for t in r2c["trades"]}
    feat = size = qty = 0
    for k in a:
        if abs((a[k].get("volume_ratio") or 0) - (b[k].get("volume_ratio") or 0)) > 1e-9 or abs((a[k].get("ret3") or 0) - (b[k].get("ret3") or 0)) > 1e-9:
            feat += 1
        if abs(a[k]["intended_size"] - b[k]["intended_size"]) > 1e-9:
            size += 1
        if a[k].get("quantity") != b[k].get("quantity"):
            qty += 1
    vb = sum(t["modeled_net"] for t in b.values() if t["status"] == VERIFIED)
    va = sum(t["modeled_net"] for t in a.values() if t["status"] == VERIFIED)
    vc = sum(t["modeled_net"] for t in c.values() if t["status"] == VERIFIED)
    return {"membership_equal": set(a) == set(b), "feature_differences": feat, "size_differences": size, "quantity_differences": qty,
            "R1_verified_net": va, "R2_verified_net": vb, "R2_causal_preorder_verified_net": vc,
            "causal_quantity_changes": sum(1 for k in b if b[k].get("quantity") and c[k].get("quantity") and b[k]["quantity"] != c[k]["quantity"]),
            "note": "R2 uses the same local field as R1; complete-field reconstruction is blocked by acquisition (see ranking_scope)"}


def eod_corroboration(books: dict) -> dict:
    out = Counter()
    worst = []
    for (fam, stage), book in books.items():
        if stage != "R2":
            continue
        for t in book["trades"]:
            for side in ("entry", "exit"):
                px, ref = t.get(f"{side}_price"), t.get(f"{side}_eod_reference")
                if px is None:
                    continue
                if ref is None:
                    out[f"{side}_no_same_vendor_eod"] += 1
                    continue
                rel = abs(ref / px - 1)
                out[f"{side}_eod_within_1pct" if rel <= 0.01 else f"{side}_eod_over_1pct"] += 1
                if rel > 0.01:
                    worst.append({"symbol": t["symbol"], "date": t[f"scheduled_{side}_date"], "relative_difference": rel})
        break
    return {"counts": dict(out), "flagged": sorted(worst, key=lambda x: -x["relative_difference"])[:25],
            "scope": "same-vendor national 17:15 EOD versus final-minute RTH close; corroboration, not an independent vendor; June-August 2026 has no local EOD partition"}


def gate(books: dict, field_scope: Counter) -> dict:
    reasons = []
    for (fam, stage), book in books.items():
        if stage != "R2":
            continue
        unresolved = [t for t in book["trades"] if t["status"].startswith("UNRESOLVED")]
        missed = [t for t in book["trades"] if t["status"].startswith("MISSED_ENTRY")]
        if unresolved:
            reasons.append(f"{fam}: {len(unresolved)} scheduled H10 exits unresolved locally")
        if missed:
            reasons.append(f"{fam}: {len(missed)} intended entries missing the final-minute observation")
    flagged = [t for (fam, stage), b in books.items() if stage == "R2" and fam == "PARENT" for t in b["trades"]
               if t.get("discontinuity_flag") == "ACTION_OR_ID_REVIEW" or t.get("security_identity_status") == "TEST_SYMBOL_ID_REVIEW"]
    if flagged:
        reasons.append(f"{len(flagged)} slots carry an unresolved action/identity review flag (>=2x session gap or test symbol)")
    if field_scope.get("RANKING_SCOPE_UNVERIFIED_CEILING_50"):
        reasons.append(f"{field_scope['RANKING_SCOPE_UNVERIFIED_CEILING_50']} cohorts ranked on a $50-ceiling field (rule requires $10-$80)")
    reasons.append("no independent second vendor; loans/dividends unknown (does not by itself block a conditional model-cost study)")
    blocking = [r for r in reasons if "unresolved" in r or "missing the final" in r or "ceiling" in r or "review flag" in r]
    return {"status": "NOT_RUN_DATA_GATE" if blocking else "OPEN", "blocking": blocking, "disclosed": reasons}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--acquire", action="store_true")
    args = ap.parse_args()
    t0 = time.monotonic()
    VERIFY_ROOT.mkdir(parents=True, exist_ok=True)
    state = {"start_utc": stamp(), "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip()}
    log = []

    def note(msg):
        line = f"{stamp()} +{(time.monotonic() - t0) / 60:.1f}m {msg}"
        print(line, flush=True)
        log.append(line)

    r0 = r0_reproduction()
    note("R0 frozen reproduction read: " + ", ".join(f"{k}={v['total_pnl']:.2f}" for k, v in r0["books"].items() if k.endswith("_ALL")))
    field = load_field()
    cl = cohorts(field)
    scope = Counter(c["ranking_scope"] for c in cl)
    note(f"cohorts={len(cl)} slots={sum(len(c['rows']) for c in cl)} ranking scope={dict(scope)}")
    needs = needs_for(cl)
    note(f"observations required (incl. post-due sessions)={len(needs)}")
    summaries = load_summaries(needs, args.workers)
    note(f"summaries loaded: present={sum(present(v) for v in summaries.values())} missing={sum(not present(v) for v in summaries.values())}")
    pilot = acq.pilot()
    dump_json(VERIFY_ROOT / "pilot.json", pilot)
    note(f"vendor pilot: authenticated={pilot['authenticated']} error={pilot.get('error')}")
    req_rows = acq.required_windows(cl, summaries)
    requests = acq.coalesce(req_rows)
    req_status = Counter(r["status"] for r in req_rows)
    dump_json(VERIFY_ROOT / "required_manifest.json", {"rows": req_rows, "requests": requests, "status_counts": dict(req_status)})
    note(f"required manifest: {dict(req_status)}; coalesced requests={len(requests)}")
    acquired = None
    if args.acquire and pilot["authenticated"]:
        acquired = acq.acquire(requests, 8)
        note(f"acquisition {acquired}")
        summaries = load_summaries(needs, args.workers)

    books = {}
    for fam in FAMS:
        rec = recorded_positions(fam)
        books[(fam, "R1")] = replay(fam, cl, summaries, hold=10, quantity="fill", stage="R1", recorded=rec)
        books[(fam, "R2")] = replay(fam, cl, summaries, hold=10, quantity="fill", stage="R2")
        books[(fam, "R2_CAUSAL")] = replay(fam, cl, summaries, hold=10, quantity="preorder", stage="R2_CAUSAL")
        note(f"{fam}: " + " ".join(f"{s}={Counter(t['status'] for t in books[(fam, s)]['trades']).get(VERIFIED, 0)}verified" for s in ("R1", "R2", "R2_CAUSAL")))
    initial_path = HANDOFF / "r4r5_trade_exceptions_initial.csv"
    if not initial_path.exists():
        exp.write_csv(initial_path, exp.exceptions_rows(books))
    files = exp.export_all(books)
    files["r4r5_trade_exceptions_initial.csv"] = {"path": initial_path.as_posix(), "sha256": digest(initial_path), "bytes": initial_path.stat().st_size}
    note("CSVs exported")
    orc = oracle.run(HANDOFF, summaries)
    note(f"oracle ok={orc['ok']} trades={orc['trades']} cohorts={orc['cohorts']}")
    recon = {fam: reconcile_r0_r1(fam, books[(fam, "R1")], r0) for fam in FAMS}
    r12 = {fam: compare_r1_r2(books[(fam, "R1")], books[(fam, "R2")], books[(fam, "R2_CAUSAL")]) for fam in FAMS}
    corr = eod_corroboration(books)
    g = gate(books, scope)
    note(f"gate={g['status']} blocking={g['blocking']}")
    summary = {}
    for (fam, stage), book in books.items():
        ts = book["trades"]
        st = Counter(t["status"] for t in ts)
        ver = [t for t in ts if t["status"] == VERIFIED]
        by_split = defaultdict(float)
        for t in ver:
            by_split[t["split"]] += t["modeled_net"]
        wins = sum(t["modeled_net"] > 0 for t in ver)
        summary[f"{fam}/{stage}"] = {"intended_slots": len(ts), "status_counts": dict(st), "verified_gross": sum(t["gross_pnl"] for t in ver),
                                     "verified_modeled_net": sum(t["modeled_net"] for t in ver), "verified_net_by_split": dict(by_split),
                                     "verified_net_excluding_action_review": sum(t["modeled_net"] for t in ver if t.get("discontinuity_flag") != "ACTION_OR_ID_REVIEW" and t.get("security_identity_status") != "TEST_SYMBOL_ID_REVIEW"),
                                     "action_review_flagged_verified": sum(1 for t in ver if t.get("discontinuity_flag") == "ACTION_OR_ID_REVIEW"),
                                     "large_move_flagged_verified": sum(1 for t in ver if t.get("discontinuity_flag") == "LARGE_MOVE_REVIEW"),
                                     "test_symbol_slots": sum(1 for t in ts if t.get("security_identity_status") == "TEST_SYMBOL_ID_REVIEW"),
                                     "verified_wins": wins, "verified_losses": sum(t["modeled_net"] < 0 for t in ver), "verified_flats": sum(t["modeled_net"] == 0 for t in ver),
                                     "net_double_spread": sum(t["modeled_net_double_spread"] for t in ver),
                                     "net_borrow_10": sum(t["net_borrow_10"] for t in ver), "net_borrow_30": sum(t["net_borrow_30"] for t in ver),
                                     "tier_contribution": {k: sum(t["modeled_net"] for t in ver if t["size_tier"] == k) for k in ("FULL", "HALF", "QUARTER")},
                                     "unresolved_stale_liability_last_marks": sum((t.get("stale_liability_last_mark") or 0) * (t.get("quantity") or 0) for t in ts if t["status"].startswith("UNRESOLVED")),
                                     "aug31_equity": book["daily"][-1]["equity"], "aug31_open_tickets": book["daily"][-1]["open_tickets"],
                                     "aug31_stale_gross": book["daily"][-1]["stale_gross"], "aug31_overdue_gross": book["daily"][-1]["overdue_gross"],
                                     "peak_gross": max(r["gross_exposure"] for r in book["daily"]),
                                     "mean_gross": sum(r["gross_exposure"] for r in book["daily"]) / len(book["daily"]),
                                     "min_equity": min(r["equity"] for r in book["daily"])}
    manifest = {"timestamp": stamp(), "elapsed_minutes": (time.monotonic() - t0) / 60, "head_at_run": state["head"],
                "code_sha256": {p: digest(REPO_ROOT / p) for p in ("src/verification/r4r5_data.py", "src/verification/r4r5_replay.py", "src/verification/r4r5_export.py",
                                                                    "src/verification/r4r5_oracle.py", "src/verification/r4r5_acquire.py", "scripts/cg_arrow005_run.py")},
                "input_sha256": {"data/tmp/cg_arrow002r/ranks_ALL_wed.json": digest(RANKS_PATH),
                                 **{f"data/tmp/cg_arrow003/results/{f}_ALL.json": digest(FROZEN / "results" / f"{f}_ALL.json") for f in FAMS}},
                "calendar": {"features_start": "2025-08-01", "score_end": LOCAL_TAPE_END.isoformat(), "runoff_through": "2026-09-30",
                             "holidays_2026_in_window": ["2026-09-07"], "early_closes": ["2025-11-28", "2025-12-24"]},
                "action_identity_review": [{"cohort_id": t["cohort_id"], "symbol": t["symbol"], "flag": t.get("discontinuity_flag"), "identity": t.get("security_identity_status"),
                                            "ratio": t.get("max_session_ratio_in_hold"), "date": t.get("max_session_ratio_date"), "status": t["status"]}
                                           for t in books[("PARENT", "R2")]["trades"] if t.get("discontinuity_flag") in {"ACTION_OR_ID_REVIEW", "LARGE_MOVE_REVIEW"} or t.get("security_identity_status") == "TEST_SYMBOL_ID_REVIEW"],
                "r0": r0, "r0_r1_reconciliation": recon, "r1_r2_comparison": r12, "eod_corroboration": corr,
                "pilot": pilot, "required_observations": dict(req_status), "coalesced_requests": len(requests), "acquired": acquired,
                "summary": summary, "oracle": orc, "gate": g, "local_csvs": files, "log": log}
    dump_json(REPORTS / "cg_arrow005_manifest.json", manifest)
    dump_json(REPORTS / "cg_arrow005_horizon_freeze.json", {"status": g["status"], "timestamp": stamp(), "blocking": g["blocking"],
                                                               "note": "Horizon census not run; exporter tested on synthetic data only"})
    note("manifest written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
