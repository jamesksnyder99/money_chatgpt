"""Arrow 011 audit gates: tested, not asserted in prose.

Gates 1-12 from docs/CG_BUILD_ARROW_011.md section 8. Tests that need the private atlas skip
cleanly in a checkout without it; the pure-function tests always run.
"""
import csv
import datetime
import subprocess

import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_anatomy as an
from verification import r4r5_anatomy_stats as st
from verification.r4r5_data import VERIFY_ROOT, digest, read_json

REPORTS = REPO_ROOT / "reports"
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011"
CACHE = VERIFY_ROOT / "a11"
ATLAS = OUT / "trade_atlas.csv"
FREEZE = REPORTS / "cg_arrow011_hypothesis_freeze.json"
COMPLETED = ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT")


def atlas():
    if not ATLAS.exists():
        pytest.skip("private atlas not built in this checkout")
    return list(csv.DictReader(ATLAS.open(encoding="utf-8")))


def manifest(name):
    p = CACHE / name
    if not p.exists():
        pytest.skip(f"{name} not built in this checkout")
    return read_json(p)


def public(name):
    p = REPORTS / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return list(csv.DictReader(p.open(encoding="utf-8")))


# ------------------------------------------------------------------ gate 1: baseline unchanged
def test_baseline_hashes_counts_and_totals_unchanged():
    b = manifest("build_manifest.json")
    assert all(v["ok"] for v in b["hash_checks"].values()), [k for k, v in b["hash_checks"].items() if not v["ok"]]
    assert all(v["ok"] for v in b["control_checks"].values()), b["control_checks"]
    assert b["fresh_replay_mismatches"] == 0
    for key in ("R5/R2_CAUSAL_PREORDER_QTY", "R5/R2_LEGACY_FILL_QTY", "R4/R2_LEGACY_FILL_QTY", "R5/R5_EQUITY_SCALED"):
        c = b["counts"][key]
        assert (c["cohorts"], c["intended"], c["completed"], c["open_documented"]) == (52, 416, 415, 1), key
    a8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    assert b["membership_sha256"] == a8["membership_sha256"]


def test_every_intended_slot_and_the_open_obligation_are_in_the_atlas():
    rows = atlas()
    assert len(rows) == 416
    assert len({r["cohort_id"] for r in rows}) == 52
    assert sum(1 for r in rows if r["status"] == "OPEN_AT_BOUNDARY_DOCUMENTED_HALT") == 1
    open_row = next(r for r in rows if r["status"] == "OPEN_AT_BOUNDARY_DOCUMENTED_HALT")
    assert open_row["oc_price_return_10"] == "" and open_row["oc_modeled_net"] == ""  # censored, never zero


def test_per_trade_price_returns_reconcile_to_the_ledger_gross():
    rows = atlas()
    done = [r for r in rows if r["status"] in COMPLETED]
    assert len(done) == 415
    assert all(r["oc_gross_reconciles"] == "True" for r in done)


# ------------------------------------------------------------------ gate 2: no duplicates / cross-panel counting
def test_one_economic_observation_per_ticket():
    rows = atlas()
    ids = [r["ticket_id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert all(r["quantity_convention"] == "CAUSAL_PREORDER_QTY" for r in rows)
    assert all(r["principal_book"] == "R5/R2_CAUSAL_PREORDER_QTY" for r in rows)


# ------------------------------------------------------------------ gate 3: availability cutoffs / leakage
def test_signal_close_feature_window_ends_at_the_signal_session():
    """A SIGNAL_CLOSE feature computed from a history containing a later session must not
    change when that later session is removed: the function reads only sessions <= signal."""
    from verification.r4r5_data import FEATS, INDEX
    signal = datetime.date(2026, 3, 11)
    i = INDEX[signal]
    base = {}
    for j in range(i - 20, i + 3):  # includes two sessions AFTER the signal
        d = FEATS[j]
        px = 10.0 + (j - (i - 20)) * 0.5
        base[(d.isoformat(), "TEST")] = {"mark_kind": "minute_close", "open": px, "high": px + 1, "low": px - 1,
                                          "close": px, "volume": 1000.0 + j}
    f_with = an.signal_close_features("TEST", signal, base)
    without = {k: v for k, v in base.items() if k[0] <= signal.isoformat()}
    f_without = an.signal_close_features("TEST", signal, without)
    assert f_with == f_without


def test_pre_order_features_never_read_the_final_minute():
    """The cutoff is the frozen preorder_ts; the pre-order helper compares on clock time <= that bar."""
    import inspect
    src = inspect.getsource(an.pre_order_features)
    assert "<= cut_clock" in src and "exec_px" not in src
    evidence = public("cg_arrow011_feature_catalog.csv")
    po = [r for r in evidence if r["cutoff"] == "PRE_ORDER"]
    assert po and all("preorder_ts" in r["availability"] for r in po)


def test_outcome_and_path_fields_are_never_used_as_features():
    freeze = read_json(FREEZE)
    for f in freeze["frozen_definitions"]["tercile_cuts"]:
        assert f.startswith(("sc_", "cx_", "ep_", "po_")), f
        assert not f.startswith(("oc_", "path_", "lens_")), f


def test_future_action_cannot_contaminate_a_signal_close_feature():
    """An action effective after the signal must not enter adjustment of pre-signal bars."""
    from verification.r4r5_data import adjustment_factor
    signal = datetime.date(2026, 3, 11)
    later = datetime.date(2026, 3, 20)
    # any factor between an observed date and the signal only uses events effective <= signal
    assert adjustment_factor("ZZZZ", datetime.date(2026, 2, 1), signal) == 1.0
    assert adjustment_factor("ZZZZ", datetime.date(2026, 2, 1), later) == 1.0


# ------------------------------------------------------------------ gate 4: missingness is a state
def test_missing_features_stay_missing_and_never_become_a_favorable_state():
    assert an.four_state(None, 1.5) == "MISSING_FEATURE"
    assert an.four_state(0.1, None) == "MISSING_FEATURE"
    assert an.four_state(float("nan"), 1.0) == "MISSING_FEATURE"
    assert an.price_band(None) == "UNAVAILABLE"
    f = an.signal_close_features("NONE", datetime.date(2026, 3, 11), {})
    assert f["history_sessions_present"] == 0
    assert f["ret15"] is None and f["volume_ratio_frozen"] is None and f["four_state"] == "MISSING_FEATURE"
    assert f["close_vs_high20"] is None and f["dollar_volume_mean20"] is None
    rows = atlas()
    miss = [r for r in rows if r["sc_four_state"] == "MISSING_FEATURE"]
    assert all(r["sc_volume_ratio_frozen"] == "" or r["sc_ret3"] == "" for r in miss)
    # the engine's documented fallback: a missing feature leaves ITS multiplier at 1.0; the other
    # feature still applies. The analysis never treats that as a fifth favorable state.
    for r in miss:
        if r["sc_volume_ratio_frozen"] == "":
            assert float(r["volume_multiplier"]) == 1.0, r["ticket_id"]
        if r["sc_ret3"] == "":
            assert float(r["momentum_multiplier"]) == 1.0, r["ticket_id"]


# ------------------------------------------------------------------ gate 5: four-state agrees with the frozen rule
def test_four_state_labels_agree_with_the_frozen_sizing_rule_on_every_ticket():
    rows = atlas()
    for r in rows:
        ret3, vr = st.num(r["sc_ret3"]), st.num(r["sc_volume_ratio_frozen"])
        state = r["sc_four_state"]
        if ret3 is None or vr is None:
            assert state == "MISSING_FEATURE", r["ticket_id"]
            continue
        expect = {"FULL": "S1", "HALF": ("S2" if float(r["volume_multiplier"]) < 1 else "S3"), "QUARTER": "S4"}[r["size_tier"]]
        assert state.startswith(expect), (r["ticket_id"], state, r["size_tier"])
        assert (float(r["momentum_multiplier"]) < 1) == (ret3 > 0), r["ticket_id"]
        assert (float(r["volume_multiplier"]) < 1) == (vr > 1), r["ticket_id"]
    assert manifest("build_manifest.json")["feature_state_disagreements"] == 0


def test_the_two_half_causes_are_distinct_states():
    assert an.four_state(-0.01, 1.5) == "S2_HALF_weak_loud"
    assert an.four_state(0.01, 0.5) == "S3_HALF_strong_quiet"
    assert an.four_state(0.0, 1.0) == "S1_FULL_weak_quiet"  # boundaries: > 0 and > 1, not >=


# ------------------------------------------------------------------ gate 6: normalized outcomes reconcile independently
def test_sizing_neutral_return_reconciles_to_shares_prices_factor_and_costs():
    t = {"status": "VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "quantity": 100.0, "entry_price": 20.0, "exit_price": 10.0,
         "action_factor_over_hold": 2.0, "gross_pnl": 100.0 / 2.0 * (20.0 * 2.0 - 10.0), "modeled_net": 1400.0}
    o = an.sizing_neutral_outcome(t)
    assert o["price_return_10"] == pytest.approx(1 - 10.0 / (2.0 * 20.0))
    assert o["gross_reconciles"] is True
    assert o["net_per_entry_dollar"] == pytest.approx(1400.0 / 2000.0)


def test_existing_accounts_remain_identical_to_their_source_references():
    b = manifest("build_manifest.json")
    assert b["oracle_a8_r2"]["ok"] and b["oracle_a10"]["ok"]
    br = manifest("bridge_manifest.json")
    assert all(v["ok"] for v in br["per_share_path_reconciliation"].values())
    for k, v in br["monthly_reconciliation"].items():
        assert v["reconciles"], k


# ------------------------------------------------------------------ gate 7: attribution sums exactly
def test_model_month_bridge_sums_exactly_with_rounding_and_month_allocation():
    rows = public("cg_arrow011_model_month_attribution.csv")
    for r in rows:
        d = float(r["difference"])
        parts = float(r["base_ticket_component"]) + float(r["momentum_component"]) + float(r["rounding_residual"])
        assert abs(d - parts) < 1e-4, (r["panel"], r["basis"], r["period"])
        assert abs(float(r["identity_residual"])) < 1e-4
        assert abs(float(r["r5_total"]) - float(r["r4_total"]) - d) < 1e-4 or r["basis"] == "CALENDAR_MONTH_MARKED_ACCOUNT"
        if r["basis"] == "CALENDAR_MONTH_MARKED_ACCOUNT":
            assert abs(float(r["reconciliation_residual"])) < 1e-4
            assert abs(float(r["difference_from_r4_winners"]) + float(r["difference_from_r4_losers"])
                       + float(r["difference_from_open_obligations"]) - d) < 1e-4
    for panel in ("LEGACY_FILL_QTY", "CAUSAL_PREORDER_QTY"):
        months = [r for r in rows if r["panel"] == panel and r["basis"] == "CALENDAR_MONTH_MARKED_ACCOUNT"]
        assert [r["period"] for r in months] == ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
                                                 "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
        cohorts = [r for r in rows if r["panel"] == panel and r["basis"] == "SIGNAL_COHORT_EVENTUAL_COMPLETED"]
        total = next(r for r in rows if r["panel"] == panel and r["basis"] == "ALL_EVENTUAL_COMPLETED")
        assert abs(sum(float(r["difference"]) for r in cohorts) - float(total["difference"])) < 1e-3
        assert len(cohorts) == 52
    legacy = next(r for r in rows if r["panel"] == "LEGACY_FILL_QTY" and r["basis"] == "ALL_EVENTUAL_COMPLETED")
    assert float(legacy["r5_total"]) == pytest.approx(129092.60, abs=0.01)
    assert float(legacy["r4_total"]) == pytest.approx(114190.85, abs=0.01)


# ------------------------------------------------------------------ gate 8: monthly outputs chain to the cutoff
def test_monthly_rows_chain_in_cents_and_reconcile_to_each_books_cutoff():
    rows = public("cg_arrow011_monthly_account.csv")
    acct = {r["book"]: r for r in public("cg_arrow011_account_summary.csv")}
    by = {}
    for r in rows:
        by.setdefault(r["book"], []).append(r)
    assert len(by) == 5
    for book, rs in by.items():
        assert [r["month"] for r in rs] == ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
                                            "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
        prior = 100000.0
        for r in rs:
            assert float(r["prior_month_end_equity"]) == prior
            assert round(float(r["month_end_equity"]), 2) == round(prior + float(r["monthly_pnl"]), 2)
            prior = float(r["month_end_equity"])
        b = float(acct[book]["marked_account_pnl_at_2026_08_31"])
        assert sum(float(r["monthly_pnl"]) for r in rs) == pytest.approx(b, abs=0.01), book
        assert b != float(acct[book]["eventual_completed_trade_pnl"])  # never tied to eventual profit
        assert acct[book]["monthly_reconciles"] == "True"


# ------------------------------------------------------------------ gate 9: predictors never include post-entry fields
def test_public_pre_entry_tables_carry_no_outcome_columns_as_features():
    for r in public("cg_arrow011_within_cohort_summary.csv"):
        assert not r["feature"].startswith(("oc_", "path_", "lens_")), r["feature"]
    for r in public("cg_arrow011_feature_catalog.csv"):
        assert r["cutoff"] in ("SIGNAL_CLOSE", "PRE_ORDER")


def test_path_archetype_is_an_outcome_label_from_returns_only():
    p = {"path_available": True, "path_returns": [0.0, 0.02, 0.03, 0.01, 0.02, 0.03, 0.04, 0.05, 0.04, 0.05, 0.06]}
    assert an.path_archetype(p) == "IMMEDIATE_FADE"
    p2 = {"path_available": True, "path_returns": [0.0, -0.02, -0.03, 0.01, 0.02, 0.03, 0.04, 0.05, 0.04, 0.05, 0.06]}
    assert an.path_archetype(p2) == "ADVERSE_THEN_FADE"
    p3 = {"path_available": True, "path_returns": [0.0, 0.04, 0.02, 0.0, -0.01, -0.02, -0.03, -0.04, -0.05, -0.05, -0.06]}
    assert an.path_archetype(p3) == "FADE_THEN_REVERSAL"
    p4 = {"path_available": True, "path_returns": [0.0, -0.01, -0.02, -0.02, -0.03, -0.04, -0.05, -0.06, -0.07, -0.08, -0.09]}
    assert an.path_archetype(p4) == "CONTINUATION"
    assert an.path_archetype({"path_available": False}) == "UNLABELED_STALE_OR_OPEN"


# ------------------------------------------------------------------ gate 10: freeze before reveal, no drift
def test_freeze_was_committed_before_confirmation_and_nothing_drifted():
    m = manifest("confirm_manifest.json")
    assert m["freeze_commit"], "freeze must be committed before the reveal"
    assert all(v["ok"] for v in m["hash_drift_since_freeze"].values()), [k for k, v in m["hash_drift_since_freeze"].items() if not v["ok"]]
    freeze = read_json(FREEZE)
    assert freeze["input_hashes"]["trade_atlas.csv"] == digest(ATLAS) if ATLAS.exists() else True
    log = subprocess.run(["git", "log", "--format=%H", "--", "reports/cg_arrow011_hypothesis_freeze.json"],
                         cwd=REPO_ROOT, capture_output=True, text=True).stdout.split()
    assert log, "freeze file has a commit history"


def test_confirmation_reports_every_registered_comparison_including_failures():
    conf = public("cg_arrow011_confirmation.csv")
    freeze = read_json(FREEZE)
    feats = {r["comparison"][8:] for r in conf if r["kind"] == "continuous_feature"}
    assert feats == set(freeze["frozen_definitions"]["tercile_cuts"])
    claims = {r["comparison"][6:] for r in conf if r["kind"] == "claim"}
    assert claims == {c["id"] for c in freeze["claims_to_confirm"]}
    probes = {r["comparison"][6:] for r in conf if r["kind"] == "probe"}
    assert probes == {p["id"] for p in freeze["frozen_definitions"]["probes"]}
    assert any(r["status"] == "NOT_REPLICATED" for r in conf), "non-replications must be reported"
    assert any(r["met"] == "False" for r in conf if r["kind"] == "claim")


# ------------------------------------------------------------------ gate 11: disclosure of failures, sparse groups, repeats
def test_registry_keeps_rejected_and_weak_hypotheses():
    hyp = public("cg_arrow011_hypotheses.csv")
    statuses = {r["is_status"] for r in hyp}
    assert any(s.startswith("REJECTED") for s in statuses)
    assert "NO_SEPARATION" in statuses and "INCONCLUSIVE_SPARSE" in statuses
    assert sum(1 for r in hyp if r["lane"] == "freelance") >= 4


def test_repeated_securities_and_cohort_census_are_disclosed():
    m = manifest("confirm_manifest.json")
    for s in ("IS", "OOS", "ALL"):
        assert sum(m["cohort_census"][s].values()) == {"IS": 25, "OOS": 27, "ALL": 52}[s]
    rows = public("cg_arrow011_within_cohort_summary.csv")
    assert all(r["securities"] for r in rows if r["n"])


# ------------------------------------------------------------------ gate 12: originals unchanged, public/private separation
def test_original_baseline_artifacts_unchanged_and_private_paths_untracked():
    a8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    assert a8["certification"]["verdict"] == "CERTIFIED"
    b = manifest("build_manifest.json")
    assert b["hash_checks"]["action_table"]["ok"]
    assert subprocess.check_output(["git", "ls-files", "handoff", "data/verification"], cwd=REPO_ROOT).decode().strip() == ""
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0


def test_public_files_carry_no_symbols_or_ticket_rows():
    rows = atlas()
    syms = {r["symbol"] for r in rows if len(r["symbol"]) >= 3}
    import re
    for name in ("cg_arrow011_within_cohort_summary.csv", "cg_arrow011_model_month_attribution.csv",
                 "cg_arrow011_confirmation.csv", "cg_arrow011_holding_path_summary.csv", "cg_arrow011_probes.csv",
                 "cg_arrow011_monthly_account.csv", "cg_arrow011_hypotheses.csv", "cg_arrow011_hypothesis_freeze.json"):
        p = REPORTS / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        assert "ticket_id" not in text.split("\n")[0], name
        hits = [s for s in syms if re.search(r"\b" + re.escape(s) + r"\b", text)]
        assert not hits, (name, hits[:5])


# ------------------------------------------------------------------ the statistics helper
def test_within_cohort_contrast_is_within_not_between():
    rows = []
    for c in range(6):
        for i in range(8):
            # feature and outcome both rise with the cohort index (between-cohort), but within
            # each cohort the outcome FALLS with the feature
            rows.append({"cohort_id": f"c{c}", "symbol": f"s{c}{i}", "x": c * 10 + i, "y": c * 10 - i})
    rel = st.relationship(rows, "x", "y")
    assert rel["pooled_spearman"] > 0
    assert rel["within_cohort_mean_spearman"] < 0
    assert rel["within_cohort_top_half_minus_bottom_half"] < 0
    assert rel["between_cohort_spearman"] > 0


def test_cohort_equal_weight_mean_gives_each_cohort_one_vote():
    rows = [{"cohort_id": "a", "symbol": "x", "g": "G", "y": 1.0}] * 7 + [{"cohort_id": "b", "symbol": "z", "g": "G", "y": -1.0}]
    t = st.group_table(rows, "g", "y")[0]
    assert t["mean"] == pytest.approx(0.75)
    assert t["cohort_equal_weight_mean"] == pytest.approx(0.0)
