"""CG Arrow 013 — the public certification report.

Reads the computed artifacts and states what was acquired, what was reused, what was verified,
what remains, and the single certification status. It names no security and reports no
strategy outcome.

Usage: python scripts/cg_arrow013_report.py
"""
from __future__ import annotations

import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification.r4r5_data import read_json, stamp  # noqa: E402


def load(p):
    return list(csv.DictReader(Path(p).open(encoding="utf-8")))


def m(x, d=0):
    return "n/a" if x in (None, "") else f"{float(x):,.{d}f}"


def main() -> int:
    mf = read_json(REPORTS / "cg_arrow013_manifest.json")
    defn = read_json(REPORTS / "cg_arrow013_holdout_definition.json")
    cov = load(REPORTS / "cg_arrow013_coverage_summary.csv")
    cal = load(REPORTS / "cg_arrow013_calendar_audit.csv")
    ovl = load(REPORTS / "cg_arrow013_overlap_authentication.csv")
    exc = load(REPORTS / "cg_arrow013_exception_summary.csv")
    auth, calm, elig = mf["authentication"], mf["calendar"], mf["eligibility"]
    integ, cvg, recon = mf["minute_integrity"], mf["coverage"], mf["aggregation_reconciliation"]

    L = []
    P = L.append
    P("# CG Arrow 013 — acquisition and certification of the pristine September 2024 to August 2025 holdout")
    P("")
    P(f"Executor: Opus in Claude Code. Run head `{mf['head_at_run'][:7]}`. This arrow acquires, authenticates, "
      "normalizes and certifies data. It runs no strategy.")
    P("")
    P("## The frozen period, fixed before any data were touched")
    P("")
    P("| Boundary | Value |")
    P("|---|---|")
    P(f"| Pristine out-of-sample signal months | {defn['pristine_oos_signal_months'][0]} through "
      f"{defn['pristine_oos_signal_months'][-1]}, {defn['signal_month_count']} consecutive months |")
    P(f"| August 2024 | warmup only: ranking and feature history, creates no positions, owns no signal |")
    P(f"| August 2025 | the twelfth and final signal month, not warmup |")
    P(f"| New bulk acquisition | {defn['new_bulk_acquisition']['start']} through {defn['new_bulk_acquisition']['end']} |")
    P(f"| Lifecycle tail | {defn['lifecycle_tail']['start']} through {defn['lifecycle_tail']['end']}, "
      "ten-session completion for late-August 2025 cohorts only |")
    P(f"| Future reveal account | starts fresh at ${defn['future_reveal_account']['starting_equity']:,.0f} "
      "before the first September 2024 cohort |")
    P("")
    P("The definition was committed before acquisition began and has not been altered since.")
    P("")
    P("## Authentication and provenance, before any bulk retrieval")
    P("")
    P("| Check | Result |")
    P("|---|---|")
    P(f"| Repository and remote | {auth['repo_root']}, {auth['remote']} |")
    P(f"| Credential file git-ignored | {auth['env_git_ignored']} |")
    P(f"| Credential handling | resolved by name only; no value is read, printed, logged, serialized, staged or committed |")
    P(f"| Vendor SDK | official ThetaData Python SDK {auth['versions'].get('thetadata')}, Python {auth['versions'].get('python')} |")
    P(f"| Entitlement | {auth['vendor_contract']['entitlement']} |")
    P(f"| Endpoints | {', '.join(auth['vendor_contract']['endpoints'])}, interval {auth['vendor_contract']['interval']}, venue {auth['vendor_contract']['venue']} |")
    P(f"| Terminal launched / subscription changed / options / sub-minute | "
      f"{auth['vendor_contract']['terminal_launched']} / {auth['vendor_contract']['subscription_changed']} / "
      f"{auth['vendor_contract']['options_used']} / {auth['vendor_contract']['sub_minute_used']} |")
    P(f"| Concurrency cap | {auth['vendor_contract']['max_concurrency']} requests across the process tree |")
    sm = mf["authentication_smoke"]
    P(f"| Authenticated smoke query | {sm['rows_first']} bars returned, {len(sm['schema'])} schema fields, "
      f"timestamps unique {sm.get('timestamps_unique')}, monotonic {sm.get('timestamps_monotonic')}, "
      f"inside the declared window {sm.get('timestamps_inside_window')} |")
    P(f"| Repeat-query reproducibility | identical: {sm['repeat_identical']} |")
    P(f"| Empty success treated as data | no; an empty success is a failure |")
    P("")
    P("Two vendor conventions were discovered and recorded rather than smoothed over. Timestamps arrive at "
      "millisecond precision in New York time while the lab's landed partitions hold microseconds, so the two "
      "are cast to one explicit unit before any comparison; after the cast the instants must be identical, "
      "which is a unit alignment and not a tolerance. A minute in which a security did not trade returns "
      "not-a-number prices with zero volume, which is a real vendor state distinct from a missing bar and from "
      "a halt; the comparison treats absence on both sides as a match and absence on one side as a discrepancy, "
      "and the three states are never merged.")
    P("")
    P("## What was newly downloaded and what was reused")
    P("")
    P("| Layer | Source | Scope |")
    P("|---|---|---|")
    new_sessions = sum(1 for r in cov if r["source"] == "NEW_BULK_ACQUISITION")
    reuse_sessions = sum(1 for r in cov if r["source"] == "EXISTING_AUTHENTICATED_REUSE")
    tail_sessions = sum(1 for r in cov if r["source"] == "EXISTING_LIFECYCLE_TAIL")
    P(f"| End of day, full roster | newly downloaded | {m(elig.get('eod_rows'))} symbol-sessions across "
      f"{m(elig.get('eod_securities'))} securities and {elig.get('eod_dates')} dates, 2024-08-01 to 2025-07-31 |")
    P(f"| One-minute bars | newly downloaded | {cvg['sessions_with_minute_layer']} of {new_sessions} "
      "new-acquisition sessions carry a landed minute layer |")
    P(f"| August 2025 | reused after authentication | {reuse_sessions} sessions, already held from the previous "
      "study's warmup, re-verified against a fresh stratified vendor sample |")
    P(f"| September 2025 lifecycle tail | reused after verification | {tail_sessions} sessions, required only to "
      "complete ten-session holds opened in late August 2025 |")
    P("")
    P("## Certification gate")
    P("")
    P("### Trading-calendar integrity")
    P("")
    P(f"The lab calendar previously covered 2025 and 2026 only. The 2024 closures and early closes were added "
      f"for this holdout. The addition is purely additive: no 2024 date falls inside any window a prior arrow "
      f"froze, and a test asserts every frozen session list is unchanged.")
    P("")
    P("| Calendar check | Result |")
    P("|---|---|")
    P(f"| Sessions in the window {calm['window'][0]} to {calm['window'][1]} | {calm['lab_sessions']} |")
    P(f"| Independent reference | {calm['independent_reference']} |")
    P(f"| Reference sessions | {calm.get('independent_sessions')} |")
    P(f"| Session lists identical | {calm.get('identical')} |")
    P(f"| Closures inside the window | {len(calm['closures_in_window'])}, each absent from the session list |")
    P(f"| Early closes | {', '.join(calm['early_closes'])}, each carrying 210 regular-hours minutes rather than 390 |")
    P("")
    P("Both New York daylight-saving transitions inside the window are covered, and landed partitions on the "
      "sessions following them carry local-time bars inside the declared schedule.")
    P("")
    P("### Timestamp and minute-bar integrity")
    P("")
    if integ:
        P("| Programmatic check | Partitions failing |")
        P("|---|---:|")
        for key, label in (("dup_timestamp_partitions", "Duplicate timestamps within a symbol-session"),
                           ("unordered_partitions", "Timestamps not monotonically ordered"),
                           ("outside_window_partitions", "Bars outside the declared 04:00 to close window"),
                           ("ohlc_inconsistent_partitions", "Open or close outside the bar's high-low range"),
                           ("negative_volume_partitions", "Negative share volume"),
                           ("nonfinite_price_partitions", "Non-positive or non-finite traded price"),
                           ("rth_bar_over_expected", "More regular-hours bars than the session schedule allows"),
                           ("unreadable", "Landed partition that could not be read back")):
            P(f"| {label} | {integ.get(key, 0):,} |")
        P("")
        P(f"Inventory covers {m(integ.get('partitions'))} landed partitions holding {m(integ.get('rows'))} "
          f"minute rows, of which {m(integ.get('traded_minutes'))} regular-hours minutes carried a trade and "
          f"{m(integ.get('no_trade_minutes'))} did not. A no-trade minute is inventoried as such and is never "
          "forward-filled into an execution.")
    else:
        P("The minute layer had not landed when this inventory ran; see the coverage section.")
    P("")
    P("### Full-universe and ranking-field completeness")
    P("")
    P("| Universe contract | Value |")
    P("|---|---:|")
    P(f"| Common-stock roster | {m(elig.get('roster'))} |")
    P(f"| Exchange-traded products excluded | {m(elig.get('etp_excluded'))} |")
    P(f"| Exchange test issues excluded | {len(elig.get('test_issues_excluded') or [])} |")
    P(f"| Eligibility rows, point in time | {m(elig.get('eligibility_rows'))} across {elig.get('sessions')} sessions |")
    P(f"| Eligible field per session, minimum | {m(elig.get('eligible_field_min'))} |")
    P(f"| Eligible field per session, median | {m(elig.get('eligible_field_median'))} |")
    P(f"| Eligible field per session, maximum | {m(elig.get('eligible_field_max'))} |")
    P(f"| Union of the eligible field across the window | {m(elig.get('minute_universe_size'))} securities |")
    P("")
    P("Eligibility is point in time by construction: a session is judged on the prior session's official "
      "end-of-day close and dollar volume, never on a later or present-day state. The per-session expected "
      "field size is published for every session in the coverage inventory, so a security cannot be dropped "
      "silently. No return is computed and nothing is ranked.")
    P("")
    P("### Volume integrity and aggregation reconciliation")
    P("")
    if recon.get("compared"):
        P("| Reconciliation | Value |")
        P("|---|---:|")
        P(f"| Deterministic symbol-session samples compared | {recon['compared']} of {recon['sampled']} |")
        P(f"| Regular-hours minute volume over end-of-day volume, median | {recon['volume_ratio_median']} |")
        P(f"| Same ratio, minimum and maximum | {recon['volume_ratio_min']} to {recon['volume_ratio_max']} |")
        P(f"| Last traded minute close versus end-of-day close, median absolute difference | "
          f"{recon.get('close_delta_median')} |")
        P("")
        P(recon["tolerance_note"][0].upper() + recon["tolerance_note"][1:] + ".")
    else:
        P("Aggregation reconciliation requires the minute layer; it had not landed when this inventory ran.")
    P("")
    P("### Corporate actions and point-in-time identity")
    P("")
    act = mf["corporate_actions_and_identity"]
    P(f"**{act['basis']}**")
    P("")
    P(act["consequence"])
    P("")
    P(f"Staged procedure: {act['staged_procedure']}")
    P("")
    P("### Exceptions and the fail-closed policy")
    P("")
    P("| Exception code | Meaning | Count | Blocks certification |")
    P("|---|---|---:|---|")
    by_code = {}
    for r in exc:
        k = r["code"]
        by_code.setdefault(k, {"n": 0, "blocks": r["blocks_certification"], "cause": r["cause"]})
        by_code[k]["n"] += 1
    labels = {"CAL": "calendar", "TS": "timestamp", "OHLC": "bar consistency", "VOL": "volume",
              "PX": "price", "IO": "partition readability", "COV": "coverage",
              "ACT": "corporate action evidence", "ID": "security identity"}
    for k, v in sorted(by_code.items()):
        P(f"| {k} | {labels.get(k, k)} | {v['n']} | {v['blocks']} |")
    P("")
    P(f"Every exception carries a stable identifier, cause, source evidence, repair status and whether it "
      f"blocks certification. {mf['exceptions']['total']} exceptions are recorded and "
      f"{mf['exceptions']['blocking']} block certification. Nothing was repaired because it produced a more "
      "convenient answer, no security was dropped without a record, and no vendor failure was reinterpreted "
      "as a market event.")
    P("")
    P("## Reproducibility and hashes")
    P("")
    P("| Authentication check | Sampled | Matched | Result |")
    P("|---|---:|---:|---|")
    for r in ovl:
        P(f"| {r['check'].replace('_', ' ')} | {r['sampled']} | {r['matched']} | {r['result']} |")
    P("")
    P(f"The manifest carries a SHA-256 for each of {len(mf['certification_artifacts'])} certification artifacts "
      f"and a partition-listing digest for each of {len(mf['raw_partition_groups'])} raw partition groups. Raw "
      "vendor partitions are immutable after landing; a resume skips only a partition that already exists and "
      "reads back cleanly, and writes are atomic so an interrupted run cannot leave a half-written file.")
    P("")
    P("## What remains")
    P("")
    for g in mf["remaining_gaps"]:
        P(f"- {g}")
    P("")
    P("## Certification status")
    P("")
    P(f"**{mf['certification_status']}**")
    P("")
    if mf["certification_status"] != "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL":
        P("The gaps above are named exactly rather than estimated. The corporate-action and identity layer is "
          "the substantive one: a price-discontinuity screen is triage and is explicitly not proof that no "
          "action occurred, so no corridor in this window is certified for unit integrity until documented "
          "dated evidence is assembled. Declaring full certification without it would be the precise mistake "
          "this gate exists to prevent.")
        P("")
    P("**NO STRATEGY PERFORMANCE WAS SCORED OR REVEALED IN ARROW 013.** No strategy was replayed, no ranking "
      "or selection was produced or inspected, no security that the frozen models would choose was named, and "
      "no trade outcome, hit rate, drawdown, monthly return or ending equity was calculated on the "
      "September 2024 to August 2025 period. The holdout remains pristine.")
    P("")
    P("No model is recommended here, because none was permitted to be tested.")
    (REPORTS / "cg_arrow013_data_certification.md").write_text("\n".join(L) + "\n",
                                                               encoding="utf-8", newline="\n")
    print(f"{stamp()} certification report written: {mf['certification_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
