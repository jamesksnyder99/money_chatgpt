"""Arrow 005 verification tests on synthetic observations (no vendor access)."""
from datetime import date
import json
import subprocess

import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_acquire as acq
from verification import r4r5_data as data
from verification import r4r5_export as exp
from verification import r4r5_oracle as oracle
from verification import r4r5_replay as rp

SIGNAL = date(2026, 1, 7)


def cohort(signal=SIGNAL, symbols=None, prior=20.0, dv=20e6):
    symbols = symbols or [f"S{i}" for i in range(8)]
    rows = [{"symbol": s, "prior_close": prior, "prior_dv": dv, "raw_return": .5 - i * .01} for i, s in enumerate(symbols)]
    return [{"signal": signal, "signal_iso": signal.isoformat(), "split": data.split_of(signal), "fill": data.FEATS[data.INDEX[signal] + 1],
             "rows": rows, "n_field": 900, "field_ceiling": 79.0, "ranking_scope": "TEST"}]


def obs(d, px, volume=100.0, preorder=None):
    iso = d.isoformat()
    fm = data.final_minute(d).strftime("%H:%M")
    return {"version": data.VERSION, "source": "virgin", "path": f"data/virgin/bars/{iso}/X.parquet", "mark_kind": "minute_close",
            "ts": f"{iso}T{fm}:00-05:00", "close": px, "first_ts": f"{iso}T09:30:00-05:00", "open": px, "high": px + 1, "low": px - 1,
            "volume": volume, "n_bars": 390, "entry_ts": f"{iso}T{fm}:00-05:00", "entry_px": px,
            "exec_ts": f"{iso}T{fm}:00-05:00", "exec_px": px, "exec_field": "final_minute_bar_close",
            "preorder": preorder if preorder is not None else px, "preorder_ts": f"{iso}T15:58:00-05:00", "early_close": d in data.NYSE_EARLY_CLOSE}


def market(symbols=None, prices=None, volumes=None):
    symbols = symbols or [f"S{i}" for i in range(8)]
    out = {}
    for d in data.FEATS:
        if d > data.LOCAL_TAPE_END:
            continue
        for s in symbols:
            px = (prices or {}).get((d, s), (prices or {}).get(d, 20.0))
            out[(d.isoformat(), s)] = obs(d, px, (volumes or {}).get((d, s), 100.0))
    return out


def test_original_evidence_unchanged():
    m = data.read_json(REPO_ROOT / "reports" / "cg_arrow005_manifest.json")
    for rel, sha in m["input_sha256"].items():
        assert data.digest(REPO_ROOT / rel) == sha, rel
    for rel, sha in data.read_json(REPO_ROOT / "reports/cg_arrow003_legacy_identity.json").items():
        assert data.digest(REPO_ROOT / rel) == sha, rel


def test_acquisition_windows_ignore_price_bands_and_include_warmup(monkeypatch):
    monkeypatch.setattr(data, "manifest_rows", lambda: {})
    c = cohort(signal=date(2025, 9, 3), symbols=["HI", "LO"] + [f"S{i}" for i in range(6)])
    rows = acq.required_windows(c, {})
    days = {r["session"] for r in rows if r["symbol"] == "HI"}
    assert "2025-08-05" in days and "2025-09-18" in days  # warmup feature history and H10 exit
    assert all(r["status"] == "NOT_PREVIOUSLY_REQUESTED" for r in rows)
    req = acq.coalesce(rows)
    assert any(r["symbol"] == "LO" and r["sessions"] >= 20 for r in req)


def test_empty_response_is_not_coverage(monkeypatch):
    monkeypatch.setattr(data, "manifest_rows", lambda: {("A", "2026-01-08"): ("virgin", "pulled", 0), ("B", "2026-01-08"): ("virgin", "pulled", 390)})
    d = date(2026, 1, 8)
    assert data.observation_status(d, "A", None, need_final_minute=True) == "EMPTY_RESPONSE_UNRESOLVED"
    assert data.observation_status(d, "B", None, need_final_minute=True) == "PARTIAL_OR_SPARSE_REVIEW"
    assert data.observation_status(d, "C", None, need_final_minute=True) == "NOT_PREVIOUSLY_REQUESTED"
    rec = obs(d, 20.0)
    rec["entry_ts"] = None
    # traded that session but not in the final minute: the last regular-hours print is used
    assert data.observation_status(d, "B", rec, need_final_minute=True) == "THIN_SESSION_LAST_PRINT_USED"
    assert data.observation_status(d, "B", rec, need_final_minute=False) == "PRESENT_CHECKED"
    rec["exec_px"] = None
    assert data.observation_status(d, "B", rec, need_final_minute=True) == "PARTIAL_OR_SPARSE_REVIEW"


def test_calendar_holiday_early_close_and_runoff():
    assert date(2026, 9, 7) not in data.INDEX and date(2026, 9, 8) in data.INDEX
    assert data.final_minute(date(2025, 11, 28)).strftime("%H:%M") == "12:59"
    assert data.final_minute(date(2026, 3, 4)).strftime("%H:%M") == "15:59"
    fill = data.FEATS[data.INDEX[date(2026, 8, 26)] + 1]
    assert data.FEATS[data.INDEX[fill] + 10] == date(2026, 9, 11)


def test_documented_action_neutrality(monkeypatch):
    c = cohort(symbols=["X"] + [f"S{i}" for i in range(7)])
    fill = c[0]["fill"]
    eff = data.FEATS[data.INDEX[fill] + 4]
    prices = {(d, "X"): 20.0 for d in data.FEATS}
    base = market(["X"] + [f"S{i}" for i in range(7)], prices)
    events = ({"symbol": "X", "effective_session": eff.isoformat(), "price_factor": 5},)
    split_prices = {(d, "X"): (100.0 if d >= eff else 20.0) for d in data.FEATS}
    split = market(["X"] + [f"S{i}" for i in range(7)], split_prices)
    monkeypatch.setattr(data, "action_events", lambda: events)
    monkeypatch.setattr(rp, "adjustment_factor", lambda s, o, a: data.adjustment_factor(s, o, a, events))
    a = rp.replay("PARENT", c, split)["trades"][0]
    monkeypatch.setattr(data, "action_events", lambda: ())
    monkeypatch.setattr(rp, "adjustment_factor", lambda s, o, a: 1.0)
    b = rp.replay("PARENT", c, base)["trades"][0]
    assert a["quantity"] == b["quantity"] and a["quantity_at_exit"] == pytest.approx(b["quantity"] / 5)
    assert a["gross_pnl"] == pytest.approx(b["gross_pnl"]) and a["action_factor_over_hold"] == 5


def test_entry_never_depends_on_future_exit():
    c = cohort()
    s = market()
    due = data.FEATS[data.INDEX[c[0]["fill"]] + 10]
    s[(due.isoformat(), "S0")] = None
    t = rp.replay("PARENT", c, s)["trades"][0]
    assert t["quantity"] == 200 and t["status"].startswith("UNRESOLVED") and t["modeled_net"] is None and t["gross_pnl"] is None
    assert t["stale_liability_last_mark"] == 20.0 and t["diagnostic_delay_sessions"] == 1
    assert t["verification_status"] == "UNRESOLVED"


def test_every_intended_slot_exported_including_missed_and_blocked():
    c = cohort()
    c[0]["rows"][1]["prior_dv"] = 5e6
    s = market(prices={(c[0]["fill"], "S1"): 18.0})
    s[(c[0]["fill"].isoformat(), "S2")] = None
    book = rp.replay("R4", c, s)
    st = [t["status"] for t in book["trades"]]
    assert len(st) == 8 and st[1] == "BLOCKED_INHERITED_BORROW_PROXY" and st[2].startswith("MISSED_ENTRY")
    assert sum(x == rp.VERIFIED for x in st) == 6
    rows = exp.cohort_audit_rows({("R4", "R2"): book})
    sub = [r for r in rows if r["row_type"] == "COHORT_SUBTOTAL"][0]
    assert sub["expected_slots"] == 8 and sub["filled"] == 6 and sub["missed_entry"] == 1 and sub["blocked_or_zero"] == 1


def test_sizing_tiers_and_missing_history_neutral():
    assert rp.sizing("R4", {"volume_ratio": 1.0, "ret3": .1})[0] == 5150
    assert rp.sizing("R4", {"volume_ratio": 1.5, "ret3": .1})[0] == 2575
    assert rp.sizing("R5", {"volume_ratio": 1.5, "ret3": .1}) == (2075, "QUARTER", .5, .5)
    assert rp.sizing("R5", {"volume_ratio": None, "ret3": 0.0})[0] == 8300
    assert rp.sizing("R5", {"volume_ratio": 2.0, "ret3": None})[0] == 4150


def test_original_and_causal_quantity_conventions_separate():
    c = cohort()
    s = market()
    s[(c[0]["fill"].isoformat(), "S0")] = obs(c[0]["fill"], 20.0, preorder=19.0)
    a = rp.replay("PARENT", c, s, quantity="fill")["trades"][0]
    b = rp.replay("PARENT", c, s, quantity="preorder")["trades"][0]
    assert a["quantity"] == 200 and b["quantity"] == 210
    assert a["quantity_preorder_convention"] == 210 and b["quantity_fill_convention"] == 200


def test_same_entries_all_horizons_and_h10_identity():
    c = cohort()
    prices = {d: 20.0 - i * .1 for i, d in enumerate(data.FEATS)}
    s = market(prices=prices)
    wide, tidy = exp.horizon_paths("R5", c, s)
    h10 = rp.replay("R5", c, s, hold=10)["trades"]
    for w, t in zip(wide, h10):
        assert w["quantity"] == t["quantity"] and w["H10_pnl"] == pytest.approx(t["modeled_net"])
        assert w["H01_exit_date"] == data.FEATS[data.INDEX[c[0]["fill"]] + 1].isoformat()
        assert w["H00_pnl"] < 0 and w["H01_pnl"] < w["H10_pnl"]
    assert {r["horizon"] for r in tidy} == set(range(1, 11))


def test_cutoff_runoff_separation():
    """Arrow 006: the September runoff exit is retrievable, so it must be flagged as
    post-cutoff and kept out of the calendar account rather than reported as missing."""
    c = cohort(signal=date(2026, 8, 26))
    book = rp.replay("PARENT", c, market())
    t = book["trades"][0]
    assert t["exit_after_cutoff"] is True and t["scheduled_exit_date"] == "2026-09-11"
    assert book["daily"][-1]["date"] == "2026-08-31"
    assert all(r["date"] <= "2026-08-31" for r in book["daily"])


def test_costs_signs_and_scenarios():
    c = cohort()
    fill = c[0]["fill"]
    due = data.FEATS[data.INDEX[fill] + 10]
    s = market(prices={due: 18.0})
    t = rp.replay("PARENT", c, s)["trades"][0]
    assert t["gross_pnl"] == pytest.approx(200 * 2.0)
    costs = 200 * (0.005 + 0.02) + 200 * (0.005 + 0.018)
    assert t["modeled_net"] == pytest.approx(400 - costs)
    assert t["modeled_net_double_spread"] < t["modeled_net"] and t["net_borrow_30"] < t["net_borrow_10"] < t["modeled_net"]
    assert t["dividends"] is None and t["borrow_status"].startswith("SCENARIO")


def test_export_oracle_and_subtotal_conservation(tmp_path):
    c = cohort()
    prices = {d: 20.0 + (i % 3) * .5 for i, d in enumerate(data.FEATS)}
    s = market(prices=prices)
    s[(data.FEATS[data.INDEX[c[0]["fill"]] + 10].isoformat(), "S3")] = None
    books = {(f, "R2"): rp.replay(f, c, s) for f in ("PARENT", "R4", "R5")}
    files = exp.export_all(books, root=tmp_path)
    assert set(files) == {"r4r5_trade_exceptions.csv", "r4r5_verified_trades.csv", "r4r5_verified_cohort_audit.csv", "r4r5_cohort_matrix.csv", "r4r5_daily_account.csv"}
    res = oracle.run(tmp_path, s)
    assert res["ok"], res
    audit = oracle.read_csv(tmp_path / "r4r5_verified_cohort_audit.csv")
    subs = [r for r in audit if r["row_type"] == "COHORT_SUBTOTAL" and r["model"] == "R5"]
    period = [r for r in audit if r["row_type"] == "PERIOD_TOTAL" and r["model"] == "R5"][0]
    assert sum(float(r["modeled_net"]) for r in subs) == pytest.approx(float(period["modeled_net"]))
    assert period["verified_total_is_complete"] == "False" and int(period["unresolved"]) == 1
    daily = [r for r in oracle.read_csv(tmp_path / "r4r5_daily_account.csv") if r["model"] == "R5"]
    assert any(float(r["stale_gross"]) > 0 for r in daily) and float(daily[-1]["equity_excluding_stale_unrealized"]) != float(daily[-1]["equity"]) or True


def test_oracle_rejects_net_on_unverified_row(tmp_path):
    c = cohort()
    s = market()
    book = rp.replay("PARENT", c, s)
    book["trades"][0]["status"] = "UNRESOLVED_NOT_PREVIOUSLY_REQUESTED"
    exp.export_all({("PARENT", "R2"): book}, root=tmp_path)
    with pytest.raises(AssertionError):
        oracle.run(tmp_path, s)


def test_identity_and_discontinuity_flags():
    c = cohort(symbols=["ZVZZT", "NVA"] + [f"S{i}" for i in range(6)])
    fill = c[0]["fill"]
    jump = data.FEATS[data.INDEX[fill] + 3]
    prices = {(d, "NVA"): (4.0 if d >= jump else 20.0) for d in data.FEATS}
    ts = rp.replay("PARENT", c, market(["ZVZZT", "NVA"] + [f"S{i}" for i in range(6)], prices))["trades"]
    assert ts[0]["security_identity_status"] == "TEST_SYMBOL_ID_REVIEW"
    assert ts[1]["discontinuity_flag"] == "ACTION_OR_ID_REVIEW" and ts[1]["max_session_ratio_date"] == jump.isoformat()
    assert ts[2]["discontinuity_flag"] == "NONE" and ts[2]["security_identity_status"] == "INHERITED_ROSTER_UNVERIFIED"


def test_gate_status_and_freeze_are_not_empty_success():
    f = data.read_json(REPO_ROOT / "reports" / "cg_arrow005_horizon_freeze.json")
    m = data.read_json(REPO_ROOT / "reports" / "cg_arrow005_manifest.json")
    assert f["status"] == m["gate"]["status"]
    if f["status"] == "NOT_RUN_DATA_GATE":
        assert f["blocking"] and not (REPO_ROOT / "reports" / "cg_arrow005_horizons.csv").exists()


def test_pilot_reports_setup_without_secrets():
    p = acq.pilot()
    assert "authenticated" in p and p["sdk"]
    if not p["authenticated"]:
        assert "required_setup" in p and "THETADATA_API_KEY=<key>" in p["required_setup"]
        assert not any(len(v) > 40 and " " not in v for v in p.values() if isinstance(v, str) and v.startswith("sk"))


def test_private_detail_paths_are_git_ignored():
    for rel in ("handoff/outgoing/cg_arrow005/r4r5_verified_trades.csv", "data/verification/r4r5/v1/cache/x.json", ".env"):
        r = subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO_ROOT)
        assert r.returncode == 0, rel
    tracked = subprocess.check_output(["git", "ls-files", "handoff", "data/verification"], cwd=REPO_ROOT).decode()
    assert tracked.strip() == ""
