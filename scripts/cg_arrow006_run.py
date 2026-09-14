"""CG Arrow 006 baseline: R1/R2 reconstruction, reconciliation, CSVs and the horizon gate.

Usage: python scripts/cg_arrow006_run.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    ACTION_PATH, ACTION_PATH_V1, CUTOFF, FEATS, INDEX, LOCAL_TAPE_END, RANKS_PATH, VERIFY_ROOT,
    digest, dump_json, load_summaries, present, read_json, set_vendor_status, stamp,
)
from verification.r4r5_replay import (  # noqa: E402
    COMPLETED, VERIFIED, cohorts, load_field, needs_for, replay,
)
from cg_arrow006_acquire import VIRGIN_END, tradable_universe  # noqa: E402

WORK = VERIFY_ROOT / "work"
HANDOFF6 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow006"
FROZEN = REPO_ROOT / "data" / "tmp" / "cg_arrow003"
FAMS = ("PARENT", "R4", "R5")
CODE_FILES = ("src/verification/r4r5_data.py", "src/verification/r4r5_replay.py",
              "src/verification/r4r5_export.py", "src/verification/r4r5_oracle.py",
              "src/verification/r4r5_repair.py", "src/verification/r4r5_rank.py",
              "scripts/cg_arrow006_run.py", "scripts/cg_arrow006_acquire.py")

LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def candidate_meta(signals: list[str]) -> dict:
    """Per-cohort point-in-time prior close / prior dollar volume for every candidate."""
    out = {}
    frames = {t: pl.read_parquet(REPO_ROOT / f"data/{t}/eligibility.parquet")
              for t in ("virgin", "full")}
    for iso in signals:
        d = date.fromisoformat(iso)
        f = frames["virgin" if d <= VIRGIN_END else "full"]
        day = f.filter(pl.col("session_date") == d).unique(subset=["symbol"])
        out[iso] = {s: {"prior_close": pc, "prior_dollar_volume": dv}
                    for s, pc, dv in day.select("symbol", "prior_close", "prior_dollar_volume").iter_rows()}
    return out


def r0_reproduction() -> dict:
    out = {"source": "data/tmp/cg_arrow003 frozen records (read-only)", "books": {}}
    for fam in FAMS:
        for mode in ("IS", "OOS", "ALL"):
            p = FROZEN / "results" / f"{fam}_{mode}.json"
            r = read_json(p)
            m = r["metrics"]
            assert digest(REPO_ROOT / r["detail_path"]) == r["detail_sha256"], "frozen detail hash"
            out["books"][f"{fam}_{mode}"] = {
                "total_pnl": m["total_pnl"], "trades": m["trades"], "exit_legs": m["exit_legs"],
                "terminal_tickets": m["terminal_tickets"], "terminal_net_mtm": m["terminal_net_mtm"],
                "result_sha256": digest(p)}
    return out


def reconcile_r0_r1(fam: str, book: dict) -> dict:
    det = read_json(FROZEN / "details" / f"{fam}_ALL.json")
    frozen_ids = {p["id"] for p in det["positions"]}
    recorded = {p["id"]: p for p in det["positions"]}
    mine = {t["ticket_id"]: t for t in book["trades"]}
    filled = {k for k, t in mine.items() if t.get("quantity")}
    legs = {leg["ticket_id"]: leg for leg in det["legs"] if leg["reason"] == "backstop"}
    verified = {k: t for k, t in mine.items() if t["status"] in COMPLETED}
    diff, matched, action_legs, restored = 0.0, 0, [], []
    for k, t in verified.items():
        leg = legs.get(k)
        if leg is None:
            restored.append({"ticket_id": k, "modeled_net": t["modeled_net"],
                             "reason": "scheduled exit unpriced in the frozen book; repaired here"})
            continue
        matched += 1
        if t.get("action_factor_over_hold", 1.0) != 1.0 and abs(leg["shares"] - t["quantity_at_exit"]) > 1e-9:
            action_legs.append({"ticket_id": k, "frozen_pnl": leg["pnl"], "r1_pnl": t["modeled_net"],
                                "factor": t["action_factor_over_hold"]})
            continue
        diff = max(diff, abs(leg["pnl"] - t["modeled_net"]), abs(leg["shares"] - t["quantity_at_exit"]),
                   abs(leg["exit"] - t["exit_price"]))
    return {"frozen_positions": len(frozen_ids), "r1_filled": len(filled),
            "frozen_positions_all_present": frozen_ids <= filled,
            "identity_equal": filled == frozen_ids,
            "repaired_entries_new_in_r1": sorted(filled - frozen_ids),
            "missing_from_r1": sorted(frozen_ids - filled), "extra_in_r1": sorted(filled - frozen_ids),
            "quantity_mismatches": sum(1 for k in filled & frozen_ids
                                       if mine[k]["quantity"] != recorded[k]["original_shares"]),
            "frozen_scheduled_legs": len(legs), "matched_unchanged_legs": matched,
            "max_abs_leg_difference": diff,
            "documented_action_leg_changes": action_legs,
            "documented_action_delta": sum(x["r1_pnl"] - x["frozen_pnl"] for x in action_legs),
            "repaired_exits_new_in_r1": len(restored),
            "repaired_exit_net": sum(x["modeled_net"] for x in restored)}


def waterfall(fam: str, r0: dict, r1: dict, r2: dict, r2c: dict, recon: dict) -> dict:
    def ver(b):
        return sum(t["modeled_net"] for t in b["trades"] if t["status"] in COMPLETED)
    return {"R0_frozen_total_incl_stale_and_delayed": r0["books"][f"{fam}_ALL"]["total_pnl"],
            "R0_scheduled_exit_legs_only": sum(l["pnl"] for l in
                                               read_json(FROZEN / "details" / f"{fam}_ALL.json")["legs"]
                                               if l["reason"] == "backstop"),
            "step1_documented_action_unit_repair": recon["documented_action_delta"],
            "step2_repaired_previously_unpriced_exits": recon["repaired_exit_net"],
            "R1_verified_total": ver(r1),
            "step3_universe_test_issue_and_field_restoration": ver(r2) - ver(r1),
            "R2_verified_total": ver(r2),
            "memo_causal_preorder_quantity_bridge": ver(r2c) - ver(r2),
            "R2_causal_quantity_total": ver(r2c)}


def action_identity_review(books: dict) -> dict:
    actions = read_json(ACTION_PATH)
    resolutions = {(x["symbol"], x.get("date")): x["resolution"] for x in actions.get("screen_resolutions", [])}
    applied = {e["symbol"] for e in actions["events"]}
    rows = []
    for (fam, stage), book in books.items():
        for t in book["trades"]:
            flag = t.get("discontinuity_flag")
            ident = t.get("security_identity_status")
            if ident == "TEST_SYMBOL_ID_REVIEW":
                res = "TEST_ISSUE_EXCLUDED_FROM_R2" if stage.startswith("R2") else "TEST_ISSUE_RETAINED_IN_R1_FORENSIC"
            elif flag in {"ACTION_OR_ID_REVIEW", "LARGE_MOVE_REVIEW"}:
                if t["symbol"] in applied and t.get("action_factor_over_hold", 1.0) != 1.0:
                    res = "DOCUMENTED_ACTION_APPLIED"
                else:
                    res = resolutions.get((t["symbol"], t.get("max_session_ratio_date")))
                    if res is None:
                        res = resolutions.get((t["symbol"], None)) or (
                            "PENDING_REVIEW" if flag == "ACTION_OR_ID_REVIEW" else "LARGE_MOVE_UNREVIEWED")
            else:
                res = "NONE"
            t["action_review_resolution"] = res
            if res != "NONE":
                rows.append({"model": fam, "replay_stage": stage, "cohort_id": t["cohort_id"],
                             "symbol": t["symbol"], "flag": flag, "identity": ident,
                             "ratio": t.get("max_session_ratio_in_hold"),
                             "date": t.get("max_session_ratio_date"), "status": t["status"],
                             "resolution": res})
    unresolved = sorted({(r["symbol"], r["cohort_id"]) for r in rows
                         if r["replay_stage"] == "R2" and r["resolution"] in
                         {"PENDING_REVIEW", "TEST_ISSUE_EXCLUDED_FROM_R2"}})
    return {"rows": [r for r in rows if r["replay_stage"] in ("R1", "R2")],
            "unresolved_in_r2": [f"{s}/{c}" for s, c in unresolved],
            "counts": dict(Counter(r["resolution"] for r in rows if r["replay_stage"] == "R2"))}


def selection_integrity(books: dict) -> dict:
    """Quantify how much of each book rests on uncertified ranking units."""
    out = {}
    for (fam, stage), book in books.items():
        ts = [t for t in book["trades"] if t["status"] in COMPLETED]
        bad = [t for t in ts if t.get("lookback_resolution") == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"]
        out[f"{fam}/{stage}"] = {
            "completed": len(ts), "uncertified_rank_units": len(bad),
            "net_total": sum(t["modeled_net"] for t in ts),
            "net_from_uncertified": sum(t["modeled_net"] for t in bad),
            "net_excluding_uncertified": sum(t["modeled_net"] for t in ts) - sum(t["modeled_net"] for t in bad),
            "documented_action_in_window": sum(1 for t in ts
                                               if t.get("lookback_resolution") == "DOCUMENTED_ACTION_IN_RANKING_WINDOW"),
            "resolved_market_move_in_window": sum(1 for t in ts if t.get("lookback_resolution")
                                                  not in (None, "NONE", "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY",
                                                          "DOCUMENTED_ACTION_IN_RANKING_WINDOW"))}
    return out


def gate(books: dict, corrected: list[dict], review: dict, orc: dict) -> dict:
    blockers, disclosed = [], []
    for fam in FAMS:
        ts = books[(fam, "R2")]["trades"]
        unres = [t for t in ts if t["status"].startswith("UNRESOLVED")]
        missed = [t for t in ts if t["status"].startswith("MISSED_ENTRY")]
        events = [t for t in ts if t["status"] in ("NO_ENTRY_DOCUMENTED_TRADING_EVENT",
                                                   "OPEN_AT_BOUNDARY_DOCUMENTED_HALT")]
        carried = [t for t in ts if t["status"] == "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT"]
        if events or carried:
            disclosed.append(f"{fam}: {len(events)} slots under a documented trading event with no execution "
                             f"in the window, {len(carried)} filled by a carried order after a documented halt")
        if unres:
            blockers.append(f"{fam}: {len(unres)} scheduled H10 exits unresolved")
        if missed:
            blockers.append(f"{fam}: {len(missed)} intended entries without a final-minute observation")
    unresolved_rank = sum(c["unrankable_unresolved"] for c in corrected)
    if unresolved_rank:
        blockers.append(f"{unresolved_rank} rule-eligible candidates have an unresolved ranking endpoint")
    scopes = Counter(c["ranking_scope"] for c in corrected)
    if scopes.get("CERTIFIED_RULE_FIELD_10_80", 0) != len(corrected):
        blockers.append(f"ranking field not certified for all cohorts: {dict(scopes)}")
    if review["unresolved_in_r2"]:
        blockers.append(f"{len(review['unresolved_in_r2'])} unresolved action/identity flags in R2")
    bad_rank = sorted({(h["symbol"], c["signal_iso"]) for c in corrected for h in c["rows"]
                       if h.get("lookback_resolution") == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"})
    if bad_rank:
        blockers.append(f"{len(bad_rank)} corrected selections rest on a ranking window containing an "
                        f"undocumented discontinuity of 2x or more, so their 15-session return is not "
                        f"certified to be in consistent price units")
    if not orc["ok"]:
        blockers.append("independent oracle did not reconcile")
    disclosed.append("loan/locate/dividend history unavailable: borrow is scenario-only, so modeled net "
                     "is conditional and is not verified executable historical net profit")
    disclosed.append("single vendor: a second endpoint of the same vendor is corroboration, not independent validation")
    disclosed.append("observed bar prices are a simulation reference, not guaranteed broker fills")
    return {"status": "OPEN" if not blockers else "NOT_RUN_DATA_GATE", "blockers": blockers,
            "disclosed_limitations": disclosed}


def summarize(books: dict) -> dict:
    out = {}
    for (fam, stage), book in books.items():
        ts = book["trades"]
        ver = [t for t in ts if t["status"] in COMPLETED]
        by_split = defaultdict(float)
        for t in ver:
            by_split[t["split"]] += t["modeled_net"]
        daily = book["daily"]
        eq = [r["equity"] for r in daily]
        peak, dd = 100000.0, 0.0
        for e in eq:
            peak = max(peak, e)
            dd = min(dd, e - peak)
        wins = [t["modeled_net"] for t in ver if t["modeled_net"] > 0]
        losses = [t["modeled_net"] for t in ver if t["modeled_net"] < 0]
        out[f"{fam}/{stage}"] = {
            "intended_slots": len(ts), "status_counts": dict(Counter(t["status"] for t in ts)),
            "verified_trades": len(ver), "verified_gross": sum(t["gross_pnl"] for t in ver),
            "verified_modeled_net": sum(t["modeled_net"] for t in ver),
            "verified_net_by_split": dict(by_split),
            "wins": len(wins), "losses": len(losses), "flats": len(ver) - len(wins) - len(losses),
            "hit_rate": len(wins) / len(ver) if ver else None,
            "avg_win": sum(wins) / len(wins) if wins else None,
            "avg_loss": sum(losses) / len(losses) if losses else None,
            "profit_factor": (sum(wins) / -sum(losses)) if losses else None,
            "net_double_spread": sum(t["modeled_net_double_spread"] for t in ver),
            "net_borrow_10": sum(t["net_borrow_10"] for t in ver),
            "net_borrow_30": sum(t["net_borrow_30"] for t in ver),
            "tier_contribution": {k: sum(t["modeled_net"] for t in ver if t["size_tier"] == k)
                                  for k in ("FULL", "HALF", "QUARTER")},
            "tier_counts": dict(Counter(t["size_tier"] for t in ts)),
            "aug31_equity": daily[-1]["equity"], "aug31_open_tickets": daily[-1]["open_tickets"],
            "aug31_stale_gross": daily[-1]["stale_gross"], "aug31_overdue_gross": daily[-1]["overdue_gross"],
            "max_drawdown_dollars": dd, "worst_day": min((b - a for a, b in zip([100000.0] + eq, eq)), default=0.0),
            "peak_gross": max(r["gross_exposure"] for r in daily),
            "mean_gross": sum(r["gross_exposure"] for r in daily) / len(daily),
            "exposure_dollar_days": sum(r["gross_exposure"] for r in daily),
            "sessions_above_130k": sum(r["gross_exposure"] > 130000 for r in daily),
            "min_equity": min(eq)}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    r0 = r0_reproduction()
    note("R0 frozen books: " + ", ".join(f"{k}={v['total_pnl']:.2f}"
                                         for k, v in r0["books"].items() if k.endswith("_ALL")))

    # --- historically intended selection (R1), corrected selection (R2)
    field_v1 = load_field(events=tuple(read_json(ACTION_PATH_V1)["events"]))
    cl_v1 = cohorts(field_v1)
    cohort_field = read_json(WORK / "cohort_field.json")
    ranks = read_json(RANKS_PATH)
    for iso in cohort_field:
        cohort_field[iso]["old_top8"] = [h["symbol"] for h in
                                         sorted(ranks[iso]["rows"], key=lambda h: -h["raw_return"])[:8]]
    meta = candidate_meta(sorted(cohort_field))
    roster, etp, tests = tradable_universe()
    note(f"universe rule: roster={len(roster)} etp_excluded={len(etp)} test_issues_excluded={tests}")

    # Pass 1: only the two ranking endpoints for every rule-eligible candidate.
    endpoints = set()
    for iso, cf in cohort_field.items():
        i = INDEX[date.fromisoformat(iso)]
        back = FEATS[i - 15].isoformat()
        for s in cf["rule_field"]:
            endpoints.add((iso, s))
            endpoints.add((back, s))
    note(f"pass 1: loading {len(endpoints)} ranking endpoints "
         f"across {len({d for d, _ in endpoints})} sessions")
    summaries = load_summaries(endpoints, args.workers)
    note(f"ranking endpoints present={sum(present(v) for v in summaries.values())} "
         f"absent={sum(not present(v) for v in summaries.values())}")

    status_map = rep.session_status_map()
    set_vendor_status(status_map)
    corrected, recon_rank = rank.corrected_cohorts(cohort_field, meta, summaries, status_map)
    changed = [r for r in recon_rank if r["membership_changed"]]
    note(f"corrected ranking: {len(corrected)} cohorts, membership changed in {len(changed)}, "
         f"unrankable_no_trading={sum(len(c['unrankable']) - c['unrankable_unresolved'] for c in corrected)}, "
         f"unrankable_unresolved={sum(c['unrankable_unresolved'] for c in corrected)}, "
         f"restored candidates={sum(r['restored_candidates'] for r in recon_rank)}")

    # newly selected names need lifecycle observations
    sel = {c["signal_iso"]: [{"symbol": h["symbol"]} for h in c["rows"]] for c in corrected}
    dump_json(WORK / "r2_selection.json", sel)
    # Selection-integrity screen on the ranking window of every selected name (R1 and R2).
    win = set()
    for group in (corrected, cl_v1):
        for c in group:
            i = INDEX[c["signal"]]
            for h in c["rows"]:
                for d in FEATS[i - 16: i + 1]:
                    win.add((d.isoformat(), h["symbol"]))
    summaries.update(load_summaries(win - set(summaries), args.workers))
    resolutions = {(x["symbol"], x.get("date")): x["resolution"]
                   for x in read_json(ACTION_PATH).get("screen_resolutions", [])}
    for group in (corrected, cl_v1):
        for c in group:
            for h in c["rows"]:
                h.update(rank.lookback_integrity(c["signal"], h["symbol"], summaries, resolutions))
    flagged = {g: sum(1 for c in grp for h in c["rows"]
                      if h["lookback_resolution"] == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY")
               for g, grp in (("R2", corrected), ("R1", cl_v1))}
    note(f"ranking-window integrity: unexplained discontinuities R2={flagged['R2']} R1={flagged['R1']} "
         f"of {sum(len(c['rows']) for c in corrected)} selected rows each")

    life = set(needs_for(cl_v1))
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in c["rows"]:
            for d in FEATS[i - 20: fi + 11]:
                life.add((d.isoformat(), h["symbol"]))
    note(f"pass 2: loading {len(life - set(summaries))} selected-name lifecycle observations")
    summaries.update(load_summaries(life - set(summaries), args.workers))
    sel_life = set()
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in c["rows"]:
            for d in FEATS[i - 20: fi + 11]:
                sel_life.add((d.isoformat(), h["symbol"]))
    extra = {(s, date.fromisoformat(iso)) for (iso, s) in sel_life
             if not present(summaries.get((iso, s)))
             and status_map.get((s, iso)) != "DOCUMENTED_NO_TRADING"}
    no_trade = sum(1 for (iso, s) in sel_life
                   if not present(summaries.get((iso, s)))
                   and status_map.get((s, iso)) == "DOCUMENTED_NO_TRADING")
    note(f"selected-name sessions with a documented no-trading vendor response: {no_trade}")
    note(f"corrected selections missing lifecycle observations: {len(extra)}")
    if extra:
        dump_json(WORK / "selected_missing.json", sorted(f"{s}/{d.isoformat()}" for s, d in extra))
        note("run: python scripts/cg_arrow006_acquire.py selected   (then rerun this script)")
        return 2

    # --- replays
    books = {}
    for fam in FAMS:
        rec = {p["id"]: p for p in read_json(FROZEN / "details" / f"{fam}_ALL.json")["positions"]}
        books[(fam, "R1")] = replay(fam, cl_v1, summaries, hold=10, quantity="fill", stage="R1", recorded=rec)
        books[(fam, "R2")] = replay(fam, corrected, summaries, hold=10, quantity="fill", stage="R2")
        books[(fam, "R2_CAUSAL")] = replay(fam, corrected, summaries, hold=10, quantity="preorder", stage="R2_CAUSAL")
        note(f"{fam}: " + " ".join(
            f"{s}={sum(t['status'] in COMPLETED for t in books[(fam, s)]['trades'])}/"
            f"{len(books[(fam, s)]['trades'])}" for s in ("R1", "R2", "R2_CAUSAL")))

    review = action_identity_review(books)
    note(f"action/identity review: R2 resolutions={review['counts']} unresolved={review['unresolved_in_r2']}")

    initial = HANDOFF6 / "r4r5_trade_exceptions_initial.csv"
    if not initial.exists():
        exp.write_csv(initial, exp.exceptions_rows(books))
    files = exp.export_all(books, root=HANDOFF6)
    files["r4r5_trade_exceptions_initial.csv"] = {
        "path": initial.as_posix(), "sha256": digest(initial), "bytes": initial.stat().st_size}
    note("CSVs exported to handoff/outgoing/cg_arrow006")

    orc = oracle.run(HANDOFF6, summaries)
    note(f"oracle ok={orc['ok']} trades={orc['trades']} cohorts={orc['cohorts']}")

    recon = {fam: reconcile_r0_r1(fam, books[(fam, "R1")]) for fam in FAMS}
    wf = {fam: waterfall(fam, r0, books[(fam, "R1")], books[(fam, "R2")], books[(fam, "R2_CAUSAL")], recon[fam])
          for fam in FAMS}
    integrity = selection_integrity(books)
    for k, v in integrity.items():
        if k.endswith("/R2") or k.endswith("/R1"):
            note(f"selection integrity {k}: {v['uncertified_rank_units']} uncertified rank units carrying "
                 f"{v['net_from_uncertified']:,.2f} of {v['net_total']:,.2f}")
    g = gate(books, corrected, review, orc)
    note(f"GATE {g['status']} blockers={g['blockers']}")

    summary = summarize(books)
    entry_ledger = [{"cohort_id": t["cohort_id"], "symbol": t["symbol"], "rank": t["rank"],
                     "entry_date": t.get("scheduled_entry_date"), "entry_price": t.get("entry_price"),
                     "quantity": t.get("quantity"), "size_tier": t.get("size_tier")}
                    for t in books[("R5", "R2")]["trades"]]
    ledger_hash = digest_bytes(json.dumps(entry_ledger, sort_keys=True).encode())
    manifest = {
        "arrow": "CG Arrow 006", "executor": "Opus in Claude Code", "timestamp": stamp(),
        "elapsed_minutes": (time.monotonic() - T0) / 60,
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "code_sha256": {p: digest(REPO_ROOT / p) for p in CODE_FILES},
        "input_sha256": {"data/tmp/cg_arrow002r/ranks_ALL_wed.json": digest(RANKS_PATH),
                         "reports/cg_arrow003_corporate_actions.json": digest(ACTION_PATH_V1),
                         "reports/cg_arrow006_corporate_actions.json": digest(ACTION_PATH)},
        "universe_rule": {"roster": len(roster), "etp_excluded": len(etp), "test_issues_excluded": tests,
                          "prior_close": [10.0, 80.0], "prior_dollar_volume_min": 1e7},
        "acquisition": read_json(VERIFY_ROOT / "acquisition" / "coverage.json")
        if (VERIFY_ROOT / "acquisition" / "coverage.json").exists() else None,
        "end_to_end_proof": read_json(VERIFY_ROOT / "proof_end_to_end.json")
        if (VERIFY_ROOT / "proof_end_to_end.json").exists() else None,
        "r0": r0, "r0_r1_reconciliation": recon, "ranking_reconciliation": recon_rank,
        "waterfall": wf, "action_identity_review": review, "summary": summary,
        "selection_integrity": integrity,
        "ranking_window_flags": sorted({(h["symbol"], c["signal_iso"], h.get("lookback_max_ratio"),
                                         h.get("lookback_ratio_date"), h.get("lookback_resolution"))
                                        for c in corrected for h in c["rows"]
                                        if h.get("lookback_flag") == "RANKING_WINDOW_DISCONTINUITY"},
                                       key=lambda x: -abs((x[2] or 1) - 1)),
        "oracle": orc, "gate": g, "r2_entry_ledger_sha256": ledger_hash, "local_csvs": files,
        "log": LOG}
    dump_json(REPORTS / "cg_arrow006_manifest.json", manifest)
    dump_json(WORK / "baseline_state.json",
              {"gate": g["status"], "r2_entry_ledger_sha256": ledger_hash,
               "corrected_cohorts": [{"signal_iso": c["signal_iso"], "split": c["split"],
                                      "fill": c["fill"].isoformat(),
                                      "rows": [{k: h[k] for k in ("symbol", "prior_close", "prior_dv",
                                                                  "raw_return", "rank")} for h in c["rows"]],
                                      "n_field": c["n_field"], "field_ceiling": c["field_ceiling"],
                                      "ranking_scope": c["ranking_scope"],
                                      "unrankable_unresolved": c["unrankable_unresolved"],
                                      "unrankable": c["unrankable"]}
                                     for c in corrected]})
    note("manifest written")
    return 0


def digest_bytes(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
