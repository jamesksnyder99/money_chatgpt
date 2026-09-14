"""Arrow 008 invariants: evidence states, account identities, bridge reconciliation."""
from datetime import date
import json
import re
import subprocess
import sys

import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_accounting as acct
from verification import r4r5_data as data
from verification import r4r5_replay as rp

from test_cg_arrow005 import cohort, market, obs  # shared synthetic fixtures

sys.path.insert(0, str(REPO_ROOT / "scripts"))
REPORTS = REPO_ROOT / "reports"
WORK = data.VERIFY_ROOT / "work"
HANDOFF8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
ADEQUATE = {"PRIMARY_VERIFIED_ACTION", "ADEQUATELY_REVIEWED_MARKET_MOVE",
            "DOCUMENTED_TRADING_EVENT", "NON_COMPARABLE_REORGANIZATION"}


# ------------------------------------------------------------------ Repair 1
def test_no_material_event_is_unresolved_or_heuristic():
    p = WORK / "a8_material_ledger.json"
    if not p.exists():
        pytest.skip("material event review not run in this checkout")
    led = data.read_json(p)
    assert led, "the material event ledger must not be empty"
    bad = [r for r in led if r["final_state"] not in ADEQUATE]
    assert not bad, f"{len(bad)} material events lack an adequate evidence state: " \
                    f"{[(r['symbol'], r['session'], r['final_state']) for r in bad[:5]]}"
    assert not any("HEURISTIC" in r["final_state"] for r in led)


def test_every_adequate_market_move_names_its_evidence():
    p = WORK / "a8_material_ledger.json"
    if not p.exists():
        pytest.skip("material event review not run")
    for r in data.read_json(p):
        if r["final_state"] != "ADEQUATELY_REVIEWED_MARKET_MOVE":
            continue
        assert r["basis"], r
        # either a dated authoritative explanation, or a searched issuer record
        assert r.get("source") or (r["issuer_documents_read"] >= 8 and r["cik"]), r


def test_every_primary_verified_action_has_ratio_and_date():
    actions = data.read_json(REPORTS / "cg_arrow008_corporate_actions.json")
    for e in actions["events"]:
        assert e.get("price_factor"), e
        assert e.get("effective_session"), e
        assert str(e.get("source", "")).startswith("http"), e
        date.fromisoformat(e["effective_session"])


# ------------------------------------------------------------------ Repair 2
def _synthetic_runoff_book():
    c = cohort(signal=date(2026, 8, 26))
    s = market()
    return rp.replay("PARENT", c, s), s


def test_account_identities_hold_on_a_runoff_book():
    book, s = _synthetic_runoff_book()
    v = acct.account_view(book, s, "synthetic")
    assert v["identities_hold"], v["identity_checks"]
    assert v["runoff_trade_count"] > 0
    # A = through-cutoff + eventual runoff
    assert v["A_completed_trade_pnl_all_cohorts"] == pytest.approx(
        v["completed_trades_exiting_through_cutoff"] + v["D_eventual_pnl_of_runoff_trades"])
    # D = marked at cutoff + post-cutoff increment
    assert v["D_eventual_pnl_of_runoff_trades"] == pytest.approx(
        v["runoff_marked_pnl_at_cutoff"] + v["C_post_cutoff_incremental_runoff_pnl"])


def test_marked_account_pnl_is_not_the_eventual_completed_pnl():
    """The cutoff account state and the eventual completed P&L are different quantities."""
    book, s = _synthetic_runoff_book()
    v = acct.account_view(book, s, "synthetic")
    assert v["B_marked_account_pnl_at_cutoff"] != v["A_completed_trade_pnl_all_cohorts"]
    assert v["C_post_cutoff_incremental_runoff_pnl"] != 0.0


def test_per_session_field_names_numerator_and_denominator():
    book, s = _synthetic_runoff_book()
    v = acct.account_view(book, s, "synthetic")
    basis = v["per_session_basis"]
    assert "numerator" in basis and "denominator" in basis
    assert "marked account P&L" in basis
    # the per-session numerator must be the cutoff account figure, never eventual runoff P&L
    assert v["marked_account_pnl_per_account_session"] == pytest.approx(
        v["B_marked_account_pnl_at_cutoff"] / v["account_sessions_to_cutoff"])


def test_published_baseline_rows_carry_the_distinct_quantities():
    p = REPORTS / "cg_arrow008_certified_baseline.csv"
    if not p.exists():
        pytest.skip("baseline not built")
    import csv
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    assert rows
    for r in rows:
        for col in ("completed_trade_pnl_all_cohorts", "marked_account_pnl_at_2026_08_31",
                    "post_cutoff_incremental_runoff_pnl", "eventual_pnl_of_runoff_trades",
                    "open_documented_obligations", "stale_gross_in_calendar_equity",
                    "per_session_basis"):
            assert col in r, col
        assert r["identities_hold"] == "True"
        assert "numerator" in r["per_session_basis"]
    # no borrow stress in the headline table
    assert not any("borrow" in c.lower() for c in rows[0])


# ------------------------------------------------------------------ Repair 3
def test_bridge_identity_reconciles_on_synthetic_books():
    c = cohort()
    s = market(prices={d: 20.0 + (i % 4) * 0.3 for i, d in enumerate(data.FEATS)})
    r1 = rp.replay("PARENT", c, s)
    c2 = cohort(symbols=["S0", "S1", "S2", "S3", "X4", "X5", "X6", "X7"])
    s2 = market(symbols=[f"S{i}" for i in range(4)] + [f"X{i}" for i in range(4, 8)],
                prices={d: 20.0 + (i % 4) * 0.3 for i, d in enumerate(data.FEATS)})
    s2.update({k: v for k, v in s.items() if k[1] in {"S0", "S1", "S2", "S3"}})
    r2 = rp.replay("PARENT", c2, s2)
    b = acct.bridge(r1, r2, "synthetic")
    assert b["reconciles"], b
    assert b["difference"] == pytest.approx(
        b["COMMON_REVALUATION"] + b["ADDED_R2_PNL"] - b["DROPPED_R1_PNL"])
    assert b["dropped_tickets"] == 4 and b["added_tickets"] == 4


def test_dropped_sign_convention_is_explicit_and_signed():
    """A dropped losing ticket must raise the bridge, because the identity subtracts its P&L."""
    c1 = cohort(symbols=["KEEP", "LOSER"] + [f"S{i}" for i in range(6)])
    syms = ["KEEP", "LOSER"] + [f"S{i}" for i in range(6)]
    fill = c1[0]["fill"]
    due = data.FEATS[data.INDEX[fill] + 10]
    prices = {(d, "LOSER"): (40.0 if d >= due else 20.0) for d in data.FEATS}
    s1 = market(syms, prices)
    r1 = rp.replay("PARENT", c1, s1)
    c2 = cohort(symbols=["KEEP"] + [f"S{i}" for i in range(7)])
    s2 = market(["KEEP"] + [f"S{i}" for i in range(7)])
    r2 = rp.replay("PARENT", c2, s2)
    b = acct.bridge(r1, r2, "synthetic")
    assert b["DROPPED_R1_PNL"] < 0            # the dropped ticket lost money inside R1
    assert b["reconciles"]
    assert -b["DROPPED_R1_PNL"] > 0           # subtracting it raises the bridge


def test_published_bridge_reconciles():
    p = REPORTS / "cg_arrow008_r1_r2_bridge.csv"
    if not p.exists():
        pytest.skip("bridge not built")
    import csv
    for r in csv.DictReader(p.open(encoding="utf-8")):
        assert r["reconciles"] == "True", r
        assert abs(float(r["reconciliation_residual"])) < 1e-6
        lhs = float(r["R2_total"]) - float(r["R1_total"])
        rhs = float(r["COMMON_REVALUATION"]) + float(r["ADDED_R2_PNL"]) - float(r["DROPPED_R1_PNL"])
        assert lhs == pytest.approx(rhs, abs=0.02)


# ------------------------------------------------------------------ Repair 4 and gate
def test_h10_reproduces_the_certified_baseline():
    p = REPORTS / "cg_arrow008_manifest.json"
    if not p.exists():
        pytest.skip("Arrow 008 not run")
    m = data.read_json(p)
    assert m["h10_reproduces_baseline"] is True


def test_certification_verdict_is_binary_and_supported():
    p = REPORTS / "cg_arrow008_manifest.json"
    if not p.exists():
        pytest.skip("Arrow 008 not run")
    m = data.read_json(p)
    v = m["certification"]["verdict"]
    assert v in ("CERTIFIED", "NOT CERTIFIED")
    if v == "CERTIFIED":
        assert m["certification"]["blockers"] == []
        assert m["rerank_stable"] is True
        assert m["oracle"]["ok"] is True
        assert m["material_event_states"].get("UNRESOLVED", 0) == 0
        assert all(a["identities_hold"] for a in m["accounts"].values())
        assert all(b["reconciles"] for b in m["bridges"].values())
    else:
        assert m["certification"]["blockers"]


def test_headline_tables_carry_the_standard_footnote_and_no_borrow_stress():
    for name in ("cg_arrow008_certified_baseline.csv", "cg_arrow008_horizons.csv"):
        p = REPORTS / name
        if not p.exists():
            pytest.skip("outputs not built")
        text = p.read_text(encoding="utf-8")
        assert "Alpaca ETB securities currently carry $0 locate and borrow fees" in text
        assert "net_borrow_10" not in text and "net_borrow_30" not in text


def test_arrow007_artifacts_are_preserved():
    for name in ("cg_arrow007_verification.md", "cg_arrow007_manifest.json",
                 "cg_arrow007_horizon_freeze.json", "cg_arrow007_corporate_actions.json"):
        assert (REPORTS / name).is_file(), name
    out = subprocess.check_output(["git", "status", "--porcelain", "reports/"],
                                  cwd=REPO_ROOT).decode()
    assert not any(line.split()[-1].startswith("reports/cg_arrow007") and line.startswith(" M")
                   for line in out.splitlines() if line.strip())


def test_private_and_public_separation_holds():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    for rel in ("handoff/outgoing/cg_arrow008/certified_trade_audit.csv",
                "handoff/outgoing/cg_arrow008/material_event_audit.csv"):
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO_ROOT).returncode == 0, rel
    assert subprocess.check_output(["git", "ls-files", "handoff", "data/verification"],
                                   cwd=REPO_ROOT).decode().strip() == ""
    secret = re.compile(r"(THETADATA_API_KEY|ASKEDGAR_API_KEY)\s*=\s*(?!<)[A-Za-z0-9_\-]{8,}")
    for p in list(REPORTS.glob("cg_arrow008*")) + list((REPO_ROOT / "scripts").glob("cg_arrow008*.py")):
        assert not secret.search(p.read_text(encoding="utf-8")), p

def test_published_risk_columns_come_from_split_owned_books():
    """IS and OOS risk must not be copied from the all-cohort account."""
    p = REPORTS / "cg_arrow008_certified_baseline.csv"
    if not p.exists():
        pytest.skip("baseline not built")
    import csv
    rows = [r for r in csv.DictReader(p.open(encoding="utf-8"))
            if r["quantity_panel"] == "LEGACY_FILL_QTY"]
    by = {(r["legacy_id"], r["split"]): r for r in rows}
    for fam in ("PARENT", "R4", "R5"):
        is_row, oos_row, all_row = by[(fam, "IS")], by[(fam, "OOS")], by[(fam, "ALL")]
        assert is_row["max_drawdown_dollars"] != oos_row["max_drawdown_dollars"], fam
        assert is_row["peak_gross_exposure"] != all_row["peak_gross_exposure"], fam
        assert float(is_row["peak_gross_exposure"]) < float(all_row["peak_gross_exposure"]), fam
        assert int(is_row["completed_trades"]) + int(oos_row["completed_trades"]) ==             int(all_row["completed_trades"]), fam
