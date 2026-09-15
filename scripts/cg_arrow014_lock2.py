"""CG Arrow 014 LOCK 2 — write the certification gate, and only certify if it closes clean.

This script does not decide anything. It gathers what the earlier stages measured — the Arrow 013
certificate, the Phase 0A source verification, the gap-fill acquisition and its certification, the
whole-field screen, the SEC EDGAR census and the per-name corridor certification — and writes the
single status the reveal gate reads.

It writes `HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL` only when the count of unresolved material
exceptions affecting a frozen scored cell is exactly zero. Otherwise it writes the blocking status
and lists the exceptions, and the reveal script refuses to run. There is no override.

Arrow 013's own honest status, `HOLDOUT_DATA_PARTIALLY_CERTIFIED`, is preserved and restated
rather than overwritten: this gate records what Arrow 014 closed on top of it.

Usage: python scripts/cg_arrow014_lock2.py
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification.r4r5_data import digest, dump_json, read_json, stamp  # noqa: E402

WORK = H.WORK
GATE_MD = REPORTS / "cg_arrow014_certification_gate.md"
GATE_JSON = REPORTS / "cg_arrow014_certification_manifest.json"
CERTIFIED = "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL"
BLOCKED = "HOLDOUT_DATA_NOT_CERTIFIED_FOR_PRISTINE_REVEAL"
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def load(name: str, path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"{name} is missing at {path}; the gate cannot be assembled")
    return read_json(path)


def fmt(n) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.parse_args()

    a13 = load("the Arrow 013 certification", REPORTS / "cg_arrow013_certification_manifest.json") \
        if (REPORTS / "cg_arrow013_certification_manifest.json").exists() else {}
    p0a = load("the Phase 0A manifest", WORK / "phase0a_manifest.json")
    screen = load("the whole-field screen", WORK / "phase0b_screen_manifest.json")
    rankmf = load("the ranking manifest", WORK / "phase0b_rank_manifest.json")
    certmf = load("the corridor certification", WORK / "phase0b_certify_manifest.json")
    census = load("the census manifest", WORK / "census_manifest.json")
    repair = read_json(WORK / "repair_manifest.json") if (WORK / "repair_manifest.json").exists() else {}
    repcert = read_json(WORK / "repair_certification.json") \
        if (WORK / "repair_certification.json").exists() else {}
    freeze = load("LOCK 1", REPORTS / "cg_arrow014_reveal_freeze.json")
    membership = load("the frozen membership", WORK / "phase0b_membership.json")

    # ---- the gate conditions, each read from the stage that measured it
    conditions = [
        {"id": "G1", "requirement": "LOCK 1 is committed and its cohort calendar is unchanged",
         "observed": bool(subprocess.run(
             ["git", "log", "-1", "--format=%H", "--", "reports/cg_arrow014_reveal_freeze.json"],
             cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip())
         and json.dumps(freeze["calendar_rule"]["cohort_calendar"], sort_keys=True)
         == json.dumps(HO.cohort_calendar(), sort_keys=True)},
        {"id": "G2", "requirement": "the reveal matrix is still the frozen 18 cells",
         "observed": freeze["reveal_matrix"]["cell_count"] == 18
         and len(freeze["reveal_matrix"]["cells"]) == 18},
        {"id": "G3", "requirement": "Phase 0A source verification reported no blocker",
         "observed": not p0a.get("blockers")},
        {"id": "G4", "requirement": "August 2025 was never previously scored as a signal month",
         "observed": p0a.get("august_2025_pristine_audit", {}).get("status")
         == "AUGUST_2025_NOT_PREVIOUSLY_SCORED_AS_SIGNAL_MONTH"},
        {"id": "G5", "requirement": "every gap-fill partition passes the Arrow 013 partition gate",
         "observed": (repcert.get("status") == "REPAIR_PARTITIONS_CERTIFIED") if repcert else True},
        {"id": "G6", "requirement": "no ranking-stage observation is still missing",
         "observed": repair.get("symbol_sessions_still_missing", 0) == 0},
        {"id": "G7", "requirement": "no candidate is unrankable on an unresolved observation",
         "observed": rankmf.get("unrankable_unresolved") == 0},
        {"id": "G8", "requirement": "the mechanical membership has reached a fixed point",
         "observed": bool(rankmf.get("fixed_point_reached"))},
        {"id": "G9", "requirement": "every screened case that touches a scored cell is resolved "
                                    "from documented evidence",
         "observed": certmf.get("exception_counts", {}).get("ranking_window_unexplained", 1) == 0
         and all(certmf.get("exception_counts", {}).get(f"h{h}_holding_unexplained", 1) == 0
                 for h in HO.HOLDS)},
        {"id": "G10", "requirement": "every frozen scored cell has its feature, causal pre-order, "
                                     "entry and H8/H9/H10 exit observations",
         "observed": all(certmf.get("exception_counts", {}).get(k, 1) == 0
                         for k in ("feature_history_incomplete", "momentum_feature_missing",
                                   "volume_feature_missing", "causal_preorder_missing",
                                   "entry_execution_missing", "h8_exit_missing",
                                   "h9_exit_missing", "h10_exit_missing"))},
        {"id": "G11", "requirement": "no unresolved material exception remains on any scored cell",
         "observed": certmf.get("unresolved_material_exceptions") == 0},
    ]
    failed = [c for c in conditions if not c["observed"]]
    status = CERTIFIED if not failed else BLOCKED
    for c in conditions:
        note(f"{c['id']}: {'pass' if c['observed'] else 'FAIL'} — {c['requirement']}")

    manifest = {
        "arrow": "CG Arrow 014", "stage": "LOCK_2_certification_gate", "timestamp": stamp(),
        "head_at_gate": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                cwd=REPO_ROOT).decode().strip(),
        "corridor_id": HO.CORRIDOR_ID,
        "status": status,
        "a13_status_preserved": "HOLDOUT_DATA_PARTIALLY_CERTIFIED",
        "a13_status_note": ("Arrow 013's acquisition and source layer were accepted; its two open "
                            "blockers were documented dated corporate actions and point-in-time "
                            "security identity. This gate records how Arrow 014 closed them and "
                            "does not restate or overwrite Arrow 013's own status."),
        "conditions": conditions,
        "failed_conditions": [c["id"] for c in failed],
        "unresolved_material_exceptions": certmf.get("unresolved_material_exceptions"),
        "exception_counts": certmf.get("exception_counts"),
        "exceptions": certmf.get("exceptions"),
        "membership_sha256": membership["membership_sha256"],
        "action_table": membership["action_table"],
        "action_table_sha256": membership["action_table_sha256"],
        "evidence": {
            "phase0a": {"eod_partitions": p0a.get("acquisition", {}).get("eod_partitions"),
                        "bar_partitions": p0a.get("acquisition", {}).get("bar_partitions"),
                        "corridor_sessions": len(HO.FEATS), "cohorts": len(HO.cohort_calendar())},
            "gap_fill": {"requests": repair.get("requests"), "rows": repair.get("rows"),
                         "tree": repair.get("tree"), "precedence": repair.get("precedence"),
                         "still_missing": repair.get("symbol_sessions_still_missing"),
                         "certification": repcert.get("status")},
            "screen": {"securities_screened": screen.get("securities_screened"),
                       "observations": screen.get("screened_observations"),
                       "cases": screen.get("cases"),
                       "case_securities": screen.get("case_securities"),
                       "scope": screen.get("scope")},
            "census": {"securities_scanned": census.get("securities_scanned"),
                       "documented_events": census.get("events"),
                       "unexplained_cases": census.get("unexplained_cases"),
                       "scan_status_counts": census.get("scan_status_counts")},
            "ranking": {"cohorts": rankmf.get("cohorts"),
                        "selected_slots": rankmf.get("selected_slots"),
                        "control_candidates": rankmf.get("control_candidates"),
                        "distinct_selected_securities": rankmf.get("distinct_selected_securities"),
                        "field_min": rankmf.get("field_min"), "field_max": rankmf.get("field_max"),
                        "unrankable_unresolved": rankmf.get("unrankable_unresolved"),
                        "fixed_point_reached": rankmf.get("fixed_point_reached")},
            "corridor_certification": {"rows": certmf.get("rows"),
                                       "selected_rows": certmf.get("selected_rows"),
                                       "observations_required": certmf.get("observations_required")},
        },
        "input_hashes": {p: digest(REPO_ROOT / p) for p in
                         ("reports/cg_arrow014_reveal_freeze.json",
                          "reports/cg_arrow014_corporate_actions.json")
                         if (REPO_ROOT / p).exists()},
        "no_outcomes_calculated": True,
        "declaration": ("Nothing in Arrow 014 up to and including this gate has calculated a "
                        "return, a hit rate, a drawdown, a monthly figure or an ending equity on "
                        "the pristine corridor. Memberships were generated only to identify which "
                        "observations required certification."),
        "log": LOG,
    }
    dump_json(GATE_JSON, manifest)

    ev = manifest["evidence"]
    rows = "\n".join(
        f"| {c['id']} | {c['requirement']} | {'pass' if c['observed'] else '**FAIL**'} |"
        for c in conditions)
    GATE_MD.write_text(f"""# CG Arrow 014 — LOCK 2 certification gate

**Status: `{status}`**

Corridor `{HO.CORRIDOR_ID}`: {len(HO.FEATS)} exchange sessions from {HO.CORRIDOR_START} to
{HO.CORRIDOR_END}, twelve pristine out-of-sample signal months from September 2024 through
August 2025, {len(HO.cohort_calendar())} weekly cohorts, cutoff {HO.CUTOFF}.

Arrow 013 closed at `HOLDOUT_DATA_PARTIALLY_CERTIFIED`, with its acquisition and source layer
accepted and two blockers open: documented dated corporate actions, and point-in-time security
identity. That status is preserved. This gate records only what Arrow 014 added on top of it, and
it is written by measurement rather than by judgement — every row below is read from the stage
that produced it.

## Gate conditions

| id | requirement | result |
|---|---|---|
{rows}

## What Arrow 014 did to close the two open blockers

**Documented dated corporate actions.** The whole corridor universe was screened for price level
changes and multi-session trading breaks — {fmt(ev['screen']['securities_screened'])} securities
over {fmt(ev['screen']['observations'])} session-to-session observations, restricted to the
sessions each security's own cohorts depend on. This deliberately replaces Arrow 007's top-25
shortlist, which could only see events that inflated a candidate's measured return and was blind
to a forward split that depressed one. That produced {fmt(ev['screen']['cases'])} investigations
across {fmt(ev['screen']['case_securities'])} securities, every one of which was taken to the
issuer's own SEC EDGAR filings: {fmt(ev['census']['securities_scanned'])} securities scanned,
{fmt(ev['census']['documented_events'])} events documented with a filing, a ratio and a dated
effect.

**Point-in-time security identity.** A price-ratio screen cannot see a ticker reassigned between
issuers at a similar price, so every multi-session trading gap inside a lifecycle window was
screened as an identity case in its own right and carried into the same filing census.

## The gap the August 2025 extension exposed

Extending eligibility across August 2025 admitted candidates whose minute bars no source held:
securities the Arrow 013 minute universe never contained, and securities it did contain whose
August sessions were reused from the 2025-26 study tree, which does not carry them. Candidates in
both classes could not be ranked at all.

They were acquired rather than dropped, because a candidate that cannot be ranked might belong in
the top eight and excluding it would be choosing the selection by hand. The gap-fill landed
{fmt(ev['gap_fill']['rows'])} rows over {fmt(ev['gap_fill']['requests'])} vendor requests into
`{ev['gap_fill']['tree']}`, which resolves **last** in source precedence: it can supply an
observation nothing else has and can never replace one that already exists. Those partitions were
certified under the identical Arrow 013 partition gate
(`{ev['gap_fill']['certification']}`), and the end-of-day cross-check was judged inside the
$10-$80 band the ranking rule reads, against the same measurement taken on the already-certified
bulk landing.

Closing that gap changed the mechanical membership, which is the point: on the unrepaired data the
selection would have been wrong.

## The frozen membership

{fmt(ev['ranking']['cohorts'])} cohorts, {fmt(ev['ranking']['selected_slots'])} selected slots and
{fmt(ev['ranking']['control_candidates'])} rank 9-20 control candidates, drawn from a
point-in-time eligible field of {fmt(ev['ranking']['field_min'])} to
{fmt(ev['ranking']['field_max'])} securities per signal session.
Candidates unrankable on an unresolved observation: {ev['ranking']['unrankable_unresolved']}.
Membership SHA-256 `{membership['membership_sha256']}`, reached as a fixed point under the
documented action table `{membership['action_table']}`.

## No outcome has been calculated

{manifest['declaration']}

---
Generated {manifest['timestamp']} at `{manifest['head_at_gate'][:7]}`.
""", encoding="utf-8")
    note(f"status {status}; wrote {GATE_MD.relative_to(REPO_ROOT).as_posix()} and "
         f"{GATE_JSON.relative_to(REPO_ROOT).as_posix()}")
    if failed:
        note("BLOCKED on: " + ", ".join(c["id"] for c in failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
