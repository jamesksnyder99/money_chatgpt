"""CG Arrow 014 LOCK 1 — the immutable reveal specification.

Written and committed before any holdout membership is generated and long before any outcome
is calculated. Once this is committed, nothing in the Arrow 014 strategy or reporting
definition may change on the basis of anything learned from the pristine year.

It carries the exact cohort calendar, every model and account formula, the frozen Arrow 011
and Arrow 012 provenance, the metric and output schemas, and the code and input hashes that
bind it to the machinery that will execute it.

No strategy outcome exists when this runs, and none is computed here.

Usage: python scripts/cg_arrow014_lock1.py
"""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_challenger as ch  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification import r4r5_monthly as mon  # noqa: E402
from verification.r4r5_data import digest, dump_json, read_json, stamp  # noqa: E402
from verification.r4r5_replay import COMMISSION, FAMILIES  # noqa: E402

FOOTNOTE = ("Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific "
            "locate/HTB charges, dividends, financing, forced-close effects, taxes and other "
            "execution items are excluded. Historical fills and availability are modeled, not broker "
            "execution guarantees.")


def cells() -> list[dict]:
    """The complete predeclared reveal matrix. Nothing may be added after this commit."""
    out = []

    def add(n, model, legacy, view, hold, role, note=None):
        out.append({"cell": n, "model": model, "legacy_id": legacy, "account_view": view,
                    "hold": hold, "quantity_convention": "CAUSAL_PREORDER_QTY", "role": role,
                    **({"note": note} if note else {})})

    for h in (8, 9, 10):
        add(len(out) + 1, "Volume-Sized Short", "R4", "FIXED_DOLLAR", h, "principal")
    for h in (8, 9, 10):
        add(len(out) + 1, "Momentum+Volume-Sized Short", "R5", "FIXED_DOLLAR", h, "principal")
    for h in (8, 9, 10):
        add(len(out) + 1, "Momentum+Volume-Sized Short", "R5", "EQUITY_SCALED", h, "principal")
    for h in (8, 9, 10):
        add(len(out) + 1, "Rank-One 1.50x Reallocation", "C1", "EQUITY_SCALED", h, "principal challenger")
    add(len(out) + 1, "Equal-Dollar Short", "PARENT", "FIXED_DOLLAR", 10, "diagnostic control")
    add(len(out) + 1, "Rank-One 1.50x Reallocation", "C1", "FIXED_DOLLAR", 10, "mandatory diagnostic",
        "Addendum 1 section 3: separates the reallocation effect from equity compounding")
    add(len(out) + 1, "Off-High Substitution", "C2", "FIXED_DOLLAR", 10, "falsification control")
    add(len(out) + 1, "Off-High Substitution", "C2", "EQUITY_SCALED", 10, "falsification control")
    add(len(out) + 1, "Combined Reallocation and Substitution", "C3", "FIXED_DOLLAR", 10, "falsification control")
    add(len(out) + 1, "Combined Reallocation and Substitution", "C3", "EQUITY_SCALED", 10, "falsification control")
    return out


def main() -> int:
    a11 = read_json(REPORTS / "cg_arrow011_hypothesis_freeze.json")
    a12 = read_json(REPORTS / "cg_arrow012_challenger_freeze.json")
    a13 = read_json(REPORTS / "cg_arrow013_manifest.json")
    p0a = read_json(H.WORK / "phase0a_manifest.json")
    if p0a.get("blockers"):
        raise SystemExit(f"Phase 0A has open blockers: {p0a['blockers']}")

    cal = HO.cohort_calendar()
    matrix = cells()
    threshold = a12["challengers"]["C2"]["threshold_M"]

    freeze = {
        "arrow": "CG Arrow 014", "stage": "LOCK_1_reveal_specification", "timestamp": stamp(),
        "head_at_freeze": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "corridor_id": HO.CORRIDOR_ID,
        "immutability": ("This specification is immutable from the moment it is committed. No model, "
                         "horizon, multiplier, threshold, filter, substitution rule, sizing rule, "
                         "timing rule, cost convention, metric or output schema may change on the "
                         "basis of anything learned from the pristine year."),
        "no_outcome_declaration": ("No September 2024 to August 2025 strategy outcome has been "
                                   "calculated at the time of this freeze. No ranking or membership "
                                   "for the holdout has been generated yet. Phase 0A verified source, "
                                   "calendar, universe and pristine status only."),

        # ---------------- period and calendar
        "period": {
            "pristine_oos_signal_months": [f"{y}-{m:02d}" for y, m in
                                           [(2024, 9), (2024, 10), (2024, 11), (2024, 12)] +
                                           [(2025, m) for m in range(1, 9)]],
            "warmup": {"start": "2024-08-01", "end": "2024-08-30",
                       "role": "ranking and feature history only; owns no signal cohort"},
            "signal_period": {"start": HO.SIGNAL_START.isoformat(), "end": HO.SIGNAL_END.isoformat()},
            "cutoff": HO.CUTOFF.isoformat(),
            "cutoff_basis": "last exchange close of August 2025, proved from the calendar",
            "lifecycle_tail": {"start": "2025-09-01", "end": "2025-09-30",
                               "role": "H8/H9/H10 completion for late-August 2025 cohorts only; owns no signal"},
            "corridor_sessions": len(HO.FEATS),
            "account_sessions": len(HO.SCORE),
            "starting_equity": HO.STARTING_EQUITY,
        },
        "calendar_rule": {
            "rule_id": "cg_arrow007_weekly_wednesday_rollback_v1",
            "statement": ("nominal Wednesday signal anchor; if closed, roll backward one calendar day "
                          "at a time to the most recent exchange session; entry is the first valid "
                          "exchange session strictly after the signal; Hn exits n exchange sessions "
                          "after the actual fill; early closes keep their own final regular-hours "
                          "minute; the nominal anchor never moves"),
            "cohort_count": len(cal),
            "cohort_count_basis": "derived from the exchange calendar, not assumed",
            "rollback_weeks": [{"nominal_anchor": r["nominal_anchor"], "signal_date": r["signal_date"],
                                "rolled_back_days": r["rolled_back_days"]}
                               for r in cal if r.get("rolled_back_days")],
            "cohort_calendar": cal,
        },

        # ---------------- models
        "models": {
            "universe": {"prior_close_band": [10.0, 80.0], "min_prior_dollar_volume": 10_000_000.0,
                         "basis": "session D uses the official end-of-day record of session D-1",
                         "exclusions": "exchange-traded products and exchange test issues",
                         "etp_rule_effect": "no-op on this roster; applied so the contract is enforced"},
            "ranking": {"rule": "15-session corporate-action-adjusted return, descending, ties by symbol",
                        "slots": 8},
            "PARENT": {"name": "Equal-Dollar Short", "base_notional": FAMILIES["PARENT"],
                       "rule": "flat ticket, no multiplier"},
            "R4": {"name": "Volume-Sized Short", "base_notional": FAMILIES["R4"],
                   "rule": "half ticket when the signal-session volume ratio exceeds 1"},
            "R5": {"name": "Momentum+Volume-Sized Short", "base_notional": FAMILIES["R5"],
                   "rule": ("independent halving when the three-session return exceeds 0 and when the "
                            "signal-session volume ratio exceeds 1; operators are strictly > 0 and > 1; "
                            "a missing feature leaves its own multiplier at 1 and is never a favorable state"),
                   "volume_ratio": "signal-session share volume over the arithmetic mean of the prior 20 "
                                   "regular-hours sessions, all 21 sessions required, split-consistent units"},
            "C1": {"name": "Rank-One 1.50x Reallocation", "multiplier": ch.RANK_ONE_MULTIPLIER,
                   "formula": ("rank1_target = 1.50 * b1; other_scale = (T - rank1_target) / sum(b2..b8); "
                               "all eight names retained; the cohort base total T is unchanged to full "
                               "precision before integer-share flooring"),
                   "failure_rule": "a nonpositive other_scale fails the cohort; no cap is invented",
                   "provenance": "Arrow 012 frozen definition; no other multiplier is tested"},
            "C2": {"name": "Off-High Substitution", "threshold_M": threshold,
                   "threshold_provenance": ("reports/cg_arrow011_hypothesis_freeze.json "
                                            "frozen_definitions.close_vs_high20_is_median"),
                   "search_depth": ch.SUBSTITUTION_SEARCH_DEPTH,
                   "formula": a12["challengers"]["C2"]["formula"],
                   "sizing": a12["challengers"]["C2"]["sizing"],
                   "missing_data_rule": a12["challengers"]["C2"]["missing_data_rule"]},
            "C3": {"name": "Combined Reallocation and Substitution",
                   "formula": a12["challengers"]["C3"]["formula"],
                   "independence": "built as its own chronological account, never inferred from C1 and C2"},
        },
        "account_conventions": {
            "quantity": "CAUSAL_PREORDER_QTY; integer shares floored from the last completed pre-order bar",
            "fixed_dollar": "base allocations at 100,000 equity, no compounding",
            "equity_scaling": {"rule_id": "cg_arrow010_causal_signal_close_equity_scaling_v1",
                               "reference": "that account's own marked equity at the signal-session close",
                               "scale": "reference equity / 100,000",
                               "separation": "each equity-scaled book uses its own causal path, never another book's"},
            "costs": {"commission_per_share_per_side": COMMISSION,
                      "spread_proxy": "max(0.01, 0.001 * price) per side",
                      "excluded": "no generic 10%/30% borrow haircut in headline tables"},
            "identity": "daily account equity is cash minus short liability at the last available minute close",
            "footnote": FOOTNOTE,
        },
        "reveal_matrix": {"cells": matrix, "cell_count": len(matrix),
                          "closed": "no cell may be added, removed or redefined after this commit"},

        # ---------------- reporting
        "reporting": {
            "monthly_standard": mon.STANDARD_ID,
            "monthly_applies_to": "every scored complete account, all twelve months, none omitted",
            "outcome_lenses": {
                "sizing_neutral": "1 - P1 / (F * P0) where F is the action factor over the hold",
                "fixed_dollar_contribution": "modeled net under fixed base allocations",
                "equity_scaled_contribution": "modeled net under that book's own causal equity path"},
            "separate_quantities": ["eventual completed-trade P&L", "marked account P&L at the cutoff",
                                    "post-cutoff incremental runoff", "open documented obligations"],
            "cohort_pnl_basis": "eventual modeled P&L owned by the original signal cohort",
            "public_outputs": ["cg_arrow014_certification_gate.md", "cg_arrow014_reveal_freeze.json",
                               "cg_arrow014_headline_matrix.csv", "cg_arrow014_account_summary.csv",
                               "cg_arrow014_monthly_account.csv", "cg_arrow014_cohort_fixed_matrix.csv",
                               "cg_arrow014_cohort_equity_matrix.csv", "cg_arrow014_cohort_breadth.csv",
                               "cg_arrow014_mechanism_confirmation.csv", "cg_arrow014_horizon_attribution.csv",
                               "cg_arrow014_drawdown_episodes.csv", "cg_arrow014_historical_vs_pristine.csv",
                               "cg_arrow014_rank_by_rank.csv", "cg_arrow014_reveal.md",
                               "cg_arrow014_manifest.json", "cg_arrow014_commands.txt"],
        },
        "mechanism_panel": {
            "provenance": "Arrow 011 and Arrow 012 frozen definitions only; no threshold is learned here",
            "checks": [
                {"id": "M1", "name": "rank-one effect",
                 "test": "rank one versus ranks 2-8 on sizing-neutral H10 return: mean, median, hit rate, cohort support"},
                {"id": "M2", "name": "rank-one gap and extremeness",
                 "feature": "cx_gap_to_next_rank", "test": "frozen continuous within-cohort relationship"},
                {"id": "M3", "name": "off-high among ranks 2-8", "feature": "sc_close_vs_high20",
                 "cuts": "exact Arrow 011 frozen tercile cuts and median; no refit"},
                {"id": "M4", "name": "price-band by off-high state map",
                 "cuts": f"frozen bands [10,20) [20,40) [40,80) and the A11 median {threshold}"},
                {"id": "M5", "name": "wide-range and volatility descriptors",
                 "features": ["sc_mean_range_pct_10", "sc_logret_std_15", "sc_signal_day_range_pct",
                              "po_partial_range_pct"]},
                {"id": "M6", "name": "episodic-advance descriptors",
                 "features": ["sc_up_sessions_15", "sc_top3_sessions_share_of_advance"]},
                {"id": "M7", "name": "R5 three-session momentum sign", "feature": "sc_ret3",
                 "test": "frozen sign split; sizing is not altered by the result"},
                {"id": "M8", "name": "pre-order incremental information",
                 "features": ["po_signal_close_to_preorder", "po_preorder_location_in_partial_range",
                              "po_overnight_gap_vs_signal_close"]},
                {"id": "M9", "name": "repeat-selection episode effect", "feature": "ep_episode"},
                {"id": "M10", "name": "holding-path anatomy",
                 "test": "rank one and ranks 2-8 close-only sizing-neutral paths at ages 1..10, H8/H9/H10 marked"},
            ],
            "classifications": ["PRISTINE_REPLICATION", "SAME_DIRECTION_WEAKER", "NOT_REPLICATED",
                                "INCONCLUSIVE_SPARSE", "DATA_LIMIT"],
            "a11_frozen_cuts": a11["frozen_definitions"]["tercile_cuts"],
            "a11_off_high_median": a11["frozen_definitions"]["close_vs_high20_is_median"],
        },
        "rank_by_rank_diagnostic": {
            "provenance": "Addendum 2 section 3",
            "historical_reference_h10_mean": {"1": 0.272, "2": 0.073, "3": 0.039, "4": 0.027,
                                              "5": 0.092, "6": 0.026, "7": -0.015, "8": 0.013},
            "historical_reference_h10_hit": {"1": 0.83, "2": 0.58, "3": 0.52, "4": 0.50,
                                             "5": 0.62, "6": 0.49, "7": 0.46, "8": 0.46},
            "status": ("diagnostic only; it may not create a top-five book, drop ranks 6-8, change the "
                       "C1 multiplier or introduce any allocation rule on this holdout"),
        },

        # ---------------- binding hashes
        "input_hashes": {
            "a11_freeze": digest(REPORTS / "cg_arrow011_hypothesis_freeze.json"),
            "a12_freeze": digest(REPORTS / "cg_arrow012_challenger_freeze.json"),
            "a13_manifest": digest(REPORTS / "cg_arrow013_manifest.json"),
            "a13_holdout_definition": digest(REPORTS / "cg_arrow013_holdout_definition.json"),
            "phase0a_manifest": digest(H.WORK / "phase0a_manifest.json"),
            "eligibility_holdout": digest(H.WORK / "eligibility_holdout.parquet"),
            "minute_universe": digest(H.WORK / "minute_universe.txt"),
        },
        "code_hashes": {p: digest(REPO_ROOT / p) for p in (
            "src/verification/r4r5_holdout.py", "src/verification/r4r5_replay.py",
            "src/verification/r4r5_equity.py", "src/verification/r4r5_challenger.py",
            "src/verification/r4r5_rank.py", "src/verification/r4r5_data.py",
            "src/verification/r4r5_accounting.py", "src/verification/r4r5_metrics.py",
            "src/verification/r4r5_monthly.py", "src/verification/r4r5_anatomy.py",
            "src/verification/r4r5_oracle.py", "src/ingest/holdout2024.py",
            "scripts/cg_arrow014_phase0a.py", "scripts/cg_arrow014_lock1.py")},
        "a13_status_preserved": a13["certification_status"],
        "a13_declared_gaps": a13["remaining_gaps"],
        "lock2_binding": {
            "artifact": "reports/cg_arrow014_certification_gate.md",
            "manifest": "reports/cg_arrow014_manifest.json",
            "required_status": "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL",
            "rule": ("LOCK 2 references and hashes this immutable freeze. This freeze is never "
                     "rewritten to insert the certification digest."),
        },
    }
    dump_json(REPORTS / "cg_arrow014_reveal_freeze.json", freeze)
    print(f"{stamp()} LOCK 1 written: {len(matrix)} cells, {len(cal)} cohorts, "
          f"{len(freeze['mechanism_panel']['checks'])} mechanism checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
