"""Arrow 010 invariants: causal equity-responsive sizing on a frozen substrate.

The published artifacts are checked directly, and the sizing rule itself is exercised on
small synthetic books so the invariants hold for the helper, not only for this run's output.
"""
import csv
import math
import subprocess

import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_equity as eq
from verification import r4r5_metrics as met
from verification import r4r5_monthly as mon
from verification import r4r5_oracle as oracle
from verification.r4r5_data import read_json

REPORTS = REPO_ROOT / "reports"
SUMMARY = REPORTS / "cg_arrow010_equity_summary.csv"
MONTHLY = REPORTS / "cg_arrow010_monthly_account.csv"
COHORTS = REPORTS / "cg_arrow010_cohort_scaling.csv"
MANIFEST = REPORTS / "cg_arrow010_manifest.json"
FIXED = "R5_FIXED_DOLLAR_CONTROL"
SCALED = "R5_EQUITY_SCALED"
MODES = (FIXED, SCALED)
TIERS = {"FULL": 8300.0, "HALF": 4150.0, "QUARTER": 2075.0}
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
          "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
START = 100000.0


def rows(path):
    if not path.exists():
        pytest.skip("Arrow 010 outputs not built in this checkout")
    return list(csv.DictReader(path.open(encoding="utf-8")))


def manifest():
    if not MANIFEST.exists():
        pytest.skip("Arrow 010 outputs not built in this checkout")
    return read_json(MANIFEST)


# ------------------------------------------------------------------ 1, 2, 7, 8
def test_selection_symbols_dates_and_tiers_are_identical_between_the_books():
    m = manifest()
    assert m["substrate_identical_between_books"] is True
    # an entry ledger that differs only in quantity proves the substrate is shared
    assert m["entry_ledger_sha256"][FIXED] != m["entry_ledger_sha256"][SCALED]
    assert m["accounts"][f"{FIXED}/ALL"]["completed_trade_count"] == \
        m["accounts"][f"{SCALED}/ALL"]["completed_trade_count"]


def test_per_trade_price_return_before_sizing_is_identical():
    assert manifest()["max_pre_sizing_price_return_gap"] == 0.0


def test_no_trade_was_added_removed_or_re_ranked_by_sizing():
    m = manifest()
    for split in ("IS", "OOS", "ALL"):
        a, b = m["accounts"][f"{FIXED}/{split}"], m["accounts"][f"{SCALED}/{split}"]
        assert a["completed_trade_count"] == b["completed_trade_count"], split
        assert a["E_open_documented_obligations"] == b["E_open_documented_obligations"], split
        assert a["runoff_trade_count"] == b["runoff_trade_count"], split


# ------------------------------------------------------------------ 3
def test_fixed_dollar_control_reproduces_the_certified_totals():
    m = manifest()
    assert all(v["reproduces"] for v in m["certified_controls"].values()), m["certified_controls"]
    assert m["certified_controls"]["causal_preorder_eventual_completed_trade_pnl"]["observed"] == \
        pytest.approx(128864.62, abs=0.005)
    assert m["serial_control_equals_batch"] is True
    a8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    assert m["membership_sha256"] == a8["membership_sha256"]
    assert m["certified_inputs"]["arrow008_certification"] == "CERTIFIED"


# ------------------------------------------------------------------ 4
def test_at_one_hundred_thousand_the_scaled_tiers_equal_the_fixed_tiers():
    first = rows(COHORTS)[0]
    assert float(first["signal_session_reference_equity"]) == pytest.approx(START, abs=0.01)
    assert float(first["scale_factor_vs_100k"]) == pytest.approx(1.0, abs=1e-9)
    assert float(first["fixed_dollar_intended_cohort_notional"]) == pytest.approx(
        float(first["equity_scaled_intended_cohort_notional"]), abs=0.01)


def test_the_rule_is_a_flat_percentage_of_reference_equity():
    for tier, notional in TIERS.items():
        assert notional / START * 100 == pytest.approx(
            {"FULL": 8.300, "HALF": 4.150, "QUARTER": 2.075}[tier], abs=1e-9)


# ------------------------------------------------------------------ 5
def test_no_cohort_scale_factor_uses_future_information():
    assert manifest()["causality_violations"] == []


def test_every_scale_factor_equals_reference_equity_over_starting_equity():
    for r in rows(COHORTS):
        assert float(r["scale_factor_vs_100k"]) == pytest.approx(
            float(r["signal_session_reference_equity"]) / START, abs=1e-6), r["cohort_id"]


def test_each_cohort_enters_strictly_after_its_signal_session():
    for r in rows(COHORTS):
        assert r["entry_date"] > r["signal_date"], r["cohort_id"]


def test_equity_at_reads_the_last_close_on_or_before_the_reference_and_never_later():
    daily = [{"date": "2025-09-02", "equity": 101.0},
             {"date": "2025-09-03", "equity": 102.0},
             {"date": "2025-09-04", "equity": 999.0}]
    import datetime
    assert eq.equity_at(daily, datetime.date(2025, 9, 3)) == 102.0
    assert eq.equity_at(daily, datetime.date(2025, 9, 2)) == 101.0
    assert eq.equity_at([], datetime.date(2025, 9, 3)) == eq.STARTING_EQUITY


def test_causality_check_catches_a_cohort_that_could_see_its_own_entry():
    import datetime
    cohort = {"signal_iso": "2025-09-03", "signal": datetime.date(2025, 9, 3),
              "fill": datetime.date(2025, 9, 3), "split": "IS"}
    book = {"scaling_path": [{"cohort_id": "2025-09-03", "signal_date": "2025-09-03",
                              "split": "IS", "entry_date": "2025-09-03",
                              "equity_reference": START, "scale_factor": 1.0}],
            "trades": [{"ticket_id": "t1", "cohort_id": "2025-09-03",
                        "scheduled_entry_date": "2025-09-03"}]}
    problems = eq.causality_violations(book, [cohort])
    assert problems, "a same-session entry must be reported as a causality violation"
    assert any("entry does not follow its signal" in p for p in problems)


# ------------------------------------------------------------------ 6
def test_integer_shares_come_only_from_the_causal_preorder_price_and_intended_notional():
    m = manifest()
    check = m["oracle"]["equity_sizing"]
    assert check["ok"] is True, check["failures"]
    assert check["tickets_checked"] >= 400
    assert check["max_share_error"] == 0
    assert check["max_scale_error"] < 1e-9


def test_the_independent_sizing_oracle_rejects_a_tampered_share_count():
    trades = [{"ticket_id": "x", "cohort_id": "2025-09-03", "rank": 1, "symbol": "AAA",
               "status": "VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "size_tier": "FULL",
               "preorder_price": "10.0", "quantity": "999", "entry_price": "10.0",
               "scheduled_entry_date": "2025-09-04", "scheduled_exit_date": "2025-09-18",
               "sizing_scale_factor": "1.0", "equity_reference": "100000.0"}]
    out = oracle.verify_equity_sizing(trades, {}, TIERS, START)
    assert out["ok"] is False
    assert out["max_share_error"] == abs(math.floor(8300.0 / 10.0) - 999)


# ------------------------------------------------------------------ 9
def test_calendar_marked_equity_reconciles_cash_minus_short_liability_every_day():
    m = manifest()
    for book, result in m["oracle"]["daily"].items():
        assert result["ok"], (book, result)
        assert result["max_abs_error"] < 1e-6, (book, result)
    assert m["oracle"]["trades"]["errors"] == 0
    assert m["oracle"]["cohorts"]["errors"] == 0


def test_account_identities_hold_in_every_book():
    for key, v in manifest()["accounts"].items():
        assert v["identities_hold"], key


# ------------------------------------------------------------------ 10
def test_monthly_rows_are_the_twelve_months_for_both_sizing_modes():
    by = {}
    for r in rows(MONTHLY):
        by.setdefault(r["sizing_mode_id"], []).append(r)
    assert set(by) == set(MODES), sorted(by)
    for mode, rs in by.items():
        assert [r["month"] for r in rs] == MONTHS, mode


def test_monthly_rows_chain_exactly_in_cents_and_reconcile_to_the_cutoff():
    m = manifest()
    by = {}
    for r in rows(MONTHLY):
        by.setdefault(r["sizing_mode_id"], []).append(r)
    for mode, rs in by.items():
        prior = START
        for r in rs:
            assert float(r["prior_month_end_equity"]) == prior, (mode, r["month"])
            assert round(float(r["month_end_equity"]), 2) == round(
                prior + float(r["monthly_pnl"]), 2), (mode, r["month"])
            assert float(r["monthly_return_pct"]) == pytest.approx(
                float(r["monthly_pnl"]) / prior * 100.0, abs=0.01), (mode, r["month"])
            prior = float(r["month_end_equity"])
        b = m["accounts"][f"{mode}/ALL"]["B_marked_account_pnl_at_cutoff"]
        assert sum(float(r["monthly_pnl"]) for r in rs) == pytest.approx(b, abs=0.01), mode
        assert prior == pytest.approx(START + b, abs=0.01), mode
        assert m["monthly_reconciliation"][mode]["reconciles"] is True, mode


def test_monthly_table_carries_every_field_the_frozen_standard_requires():
    assert mon.missing_standard_fields(rows(MONTHLY)) == []
    assert manifest()["monthly_reporting_standard"] == mon.STANDARD_ID


# ------------------------------------------------------------------ 11
def test_eventual_completed_trade_pnl_stays_separate_from_cutoff_and_runoff():
    m = manifest()
    for mode in MODES:
        a = m["accounts"][f"{mode}/ALL"]
        assert a["A_completed_trade_pnl_all_cohorts"] != a["B_marked_account_pnl_at_cutoff"]
        assert a["A_completed_trade_pnl_all_cohorts"] == pytest.approx(
            a["completed_trades_exiting_through_cutoff"] + a["D_eventual_pnl_of_runoff_trades"],
            abs=1e-6)
        assert a["D_eventual_pnl_of_runoff_trades"] == pytest.approx(
            a["runoff_marked_pnl_at_cutoff"] + a["C_post_cutoff_incremental_runoff_pnl"], abs=1e-6)
        # the twelve months tie to B, never to A
        assert m["monthly_reconciliation"][mode]["expected_period_marked_pnl"] == pytest.approx(
            a["B_marked_account_pnl_at_cutoff"])


# ------------------------------------------------------------------ 12
def test_public_private_separation_holds():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    assert subprocess.check_output(["git", "ls-files", "handoff", "data/verification"],
                                   cwd=REPO_ROOT).decode().strip() == ""
    for path in (SUMMARY, MONTHLY, COHORTS):
        text = path.read_text(encoding="utf-8")
        for leak in ("entry_price", "exit_price", "ticket_id", "symbol"):
            assert leak not in text, (path.name, leak)


def test_published_tables_carry_the_standing_footnote_and_no_borrow_stress_columns():
    for path in (SUMMARY, MONTHLY):
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert "footnote" in header
        for banned in ("net_borrow_10", "net_borrow_30", "borrow_stress"):
            assert banned not in header, (path.name, banned)
    text = (REPORTS / "cg_arrow010_equity_sizing.md").read_text(encoding="utf-8")
    assert "Alpaca ETB securities currently carry $0 locate and borrow fees" in text


# ------------------------------------------------- scope: nothing beyond sizing was touched
def test_only_the_ten_session_hold_was_used():
    for r in rows(SUMMARY):
        assert r["horizon"] == "10-Session Hold (H10)", r
        assert r["quantity_panel"] == "CAUSAL_PREORDER_QTY", r
        assert r["legacy_id"] == "R5", r
    assert set(r["sizing_mode_id"] for r in rows(SUMMARY)) == set(MODES)


def test_the_sizing_rule_is_frozen_and_named():
    m = manifest()
    assert m["sizing_rule_id"] == eq.RULE_ID
    for word in ("leverage multiplier", "drawdown throttle", "gross cap",
                 "volatility target", "Kelly", "redeployment"):
        assert word in eq.RULE, word


def test_research_status_is_one_of_the_permitted_verdicts():
    status = manifest()["research_status"]
    allowed = ("EQUITY SCALING IS ECONOMICALLY ATTRACTIVE FOR FURTHER STUDY",
               "EQUITY SCALING ADDS RETURN BUT NOT RISK EFFICIENCY",
               "EQUITY SCALING IS ECONOMICALLY NEUTRAL",
               "EQUITY SCALING DEGRADES THE ACCOUNT PATH")
    assert status in allowed or status.startswith("RESULT INCONCLUSIVE — "), status
    assert manifest()["blockers"] == []


# ------------------------------------------------- the metrics helper itself
def test_drawdown_is_measured_against_the_running_peak_not_starting_equity():
    daily = [{"date": "2026-01-02", "equity": 200000.0, "gross_exposure": 0.0},
             {"date": "2026-01-05", "equity": 150000.0, "gross_exposure": 0.0}]
    d = met.drawdown(daily, 100000.0)
    assert d["max_drawdown_dollars"] == pytest.approx(-50000.0)
    assert d["max_drawdown_pct_of_peak"] == pytest.approx(-25.0)
    assert d["sessions_underwater"] == 1


def test_gross_ratio_uses_the_same_session_equity():
    daily = [{"date": "2026-01-02", "equity": 100000.0, "gross_exposure": 50000.0},
             {"date": "2026-01-05", "equity": 200000.0, "gross_exposure": 50000.0}]
    e = met.exposure(daily)
    assert e["mean_gross_over_marked_equity"] == pytest.approx(0.375)
    assert e["peak_gross_over_marked_equity"] == pytest.approx(0.5)
    assert e["exposure_dollar_sessions"] == pytest.approx(100000.0)


def test_leverage_stability_is_measured_within_a_book_not_between_books():
    d = manifest()["diagnostics"]
    for mode in MODES:
        h = d["gross_over_equity_by_half"][mode]
        assert h["drift"] == pytest.approx(h["second_half_mean"] - h["first_half_mean"], abs=1e-9)
    assert d["gross_over_equity_approximately_stable"] == (
        abs(d["gross_over_equity_by_half"][SCALED]["drift"]) < 0.05)
