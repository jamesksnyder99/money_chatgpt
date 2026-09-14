"""Arrow 009 invariants: the frozen monthly account reporting standard."""
import csv
import subprocess

import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_data as data
from verification import r4r5_monthly as mon

REPORTS = REPO_ROOT / "reports"
CSV = REPORTS / "cg_arrow009_monthly_account.csv"
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
          "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
LEGACY = ("PARENT", "R4", "R5")
START = 100000.0
TOL = 1e-6


def rows():
    if not CSV.exists():
        pytest.skip("Arrow 009 export not built in this checkout")
    return list(csv.DictReader(CSV.open(encoding="utf-8")))


def by_strategy():
    out = {}
    for r in rows():
        out.setdefault(r["legacy_id"], []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r["month"])
    return out


# ------------------------------------------------------------------ 1 and 2
def test_exactly_twelve_months_per_strategy():
    g = by_strategy()
    assert set(g) == set(LEGACY), sorted(g)
    for fam, rs in g.items():
        assert [r["month"] for r in rs] == MONTHS, fam


def test_exactly_the_three_certified_r2_h10_legacy_fill_books():
    for r in rows():
        assert r["replay"] == "Corrected-Universe Replay (R2)", r
        assert r["horizon"] == "10-Session Hold (H10)", r
        assert r["quantity_panel"] == "LEGACY_FILL_QTY", r
    assert {r["legacy_id"] for r in rows()} == set(LEGACY)


# ------------------------------------------------------------------ 3 to 7
def test_monthly_pnl_sums_to_certified_marked_account_pnl():
    a8 = data.read_json(REPORTS / "cg_arrow008_manifest.json")
    for fam, rs in by_strategy().items():
        b = a8["accounts"][f"{fam}/LEGACY_FILL_QTY/ALL"]["B_marked_account_pnl_at_cutoff"]
        total = sum(float(r["monthly_pnl"]) for r in rs)
        assert total == pytest.approx(b, abs=0.01), (fam, total, b)  # cent rounding only


def test_month_end_equity_chains_from_prior_month():
    for fam, rs in by_strategy().items():
        prior = START
        for r in rs:
            assert float(r["prior_month_end_equity"]) == prior, (fam, r)
            # published rows are stated in whole cents and must chain exactly
            assert round(float(r["month_end_equity"]), 2) == round(
                prior + float(r["monthly_pnl"]), 2), (fam, r)
            prior = float(r["month_end_equity"])


def test_september_starts_from_one_hundred_thousand():
    for fam, rs in by_strategy().items():
        assert rs[0]["month"] == "2025-09"
        assert float(rs[0]["prior_month_end_equity"]) == pytest.approx(START, abs=0.01), fam


def test_august_month_end_equity_is_start_plus_certified_b():
    a8 = data.read_json(REPORTS / "cg_arrow008_manifest.json")
    for fam, rs in by_strategy().items():
        b = a8["accounts"][f"{fam}/LEGACY_FILL_QTY/ALL"]["B_marked_account_pnl_at_cutoff"]
        assert rs[-1]["month"] == "2026-08"
        assert float(rs[-1]["month_end_equity"]) == pytest.approx(START + b, abs=0.01), fam


def test_return_denominator_is_prior_month_end_equity():
    for fam, rs in by_strategy().items():
        for r in rs:
            expect = float(r["monthly_pnl"]) / float(r["prior_month_end_equity"]) * 100.0
            assert float(r["monthly_return_pct"]) == pytest.approx(expect, abs=0.01), (fam, r)


# ------------------------------------------------------------------ 8 to 10
def test_no_certified_hash_changed():
    a8 = data.read_json(REPORTS / "cg_arrow008_manifest.json")
    a9 = data.read_json(REPORTS / "cg_arrow009_manifest.json")
    c = a9["certified_inputs"]
    assert c["arrow008_membership_sha256"] == a8["membership_sha256"]
    assert c["arrow008_entry_ledger_sha256"] == a8["r2_entry_ledger_sha256"]
    assert c["arrow008_action_table_sha256"] == a8["action_table_sha256"]
    assert c["arrow008_certification"] == "CERTIFIED"


def test_arrow008_certified_results_survive_the_clerical_repair():
    """Arrow 009 only corrected the prose test count; every certified figure is intact."""
    text = (REPORTS / "cg_arrow008_verification.md").read_text(encoding="utf-8")
    assert "629 passed, 1 skipped" in text and "628 passed" not in text
    assert "HISTORICAL BASELINE CERTIFICATION: CERTIFIED" in text
    for certified in ("106,392.41", "114,655.18", "129,202.83",
                      "e51a07d60312", "071bb7e13dfa", "32 of 32", "415 of 416"):
        assert certified in text, certified


def test_public_private_separation_holds():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    assert subprocess.check_output(["git", "ls-files", "handoff", "data/verification"],
                                   cwd=REPO_ROOT).decode().strip() == ""
    text = CSV.read_text(encoding="utf-8")
    for leak in ("entry_price", "exit_price", "ticket_id", "share_qty", "symbol"):
        assert leak not in text, leak


# ------------------------------------------------------------------ the standard itself
def test_standard_helper_builds_months_from_a_daily_path():
    daily = [{"date": "2025-09-02", "equity": 100500.0}, {"date": "2025-09-30", "equity": 101000.0},
             {"date": "2025-10-31", "equity": 99000.0}]
    t = mon.monthly_account(daily)
    assert [r["month"] for r in t] == ["2025-09", "2025-10"]
    assert t[0]["monthly_pnl"] == pytest.approx(1000.0)
    assert t[1]["monthly_pnl"] == pytest.approx(-2000.0)
    assert t[1]["monthly_return_pct"] == pytest.approx(-2000.0 / 101000.0 * 100.0)
    r = mon.reconcile(t, -1000.0)
    assert r["reconciles"], r
    s = mon.summarize(t)
    assert s["positive_months"] == 1 and s["red_months"] == 1


def test_standard_detects_a_table_missing_required_fields():
    assert mon.missing_standard_fields([]) == list(mon.REQUIRED_FIELDS)
    assert "monthly_return_pct" in mon.missing_standard_fields([{"month": "2025-09"}])
    assert mon.missing_standard_fields(rows()) == []


def test_reconciliation_target_is_the_marked_account_result_not_eventual_pnl():
    """The 12 months must tie to B, never to A, which contains post-August exits."""
    a8 = data.read_json(REPORTS / "cg_arrow008_manifest.json")
    a9 = data.read_json(REPORTS / "cg_arrow009_manifest.json")
    for fam in LEGACY:
        acct = a8["accounts"][f"{fam}/LEGACY_FILL_QTY/ALL"]
        assert a9["reconciliation"][fam]["expected_period_marked_pnl"] == pytest.approx(
            acct["B_marked_account_pnl_at_cutoff"])
        assert a9["reconciliation"][fam]["expected_period_marked_pnl"] != pytest.approx(
            acct["A_completed_trade_pnl_all_cohorts"])
        assert a9["reconciliation"][fam]["reconciles"] is True
