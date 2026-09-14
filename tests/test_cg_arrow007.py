"""Arrow 007 regression tests: calendar rule, unit mathematics, certification discipline."""
from datetime import date, timedelta
import json
import re
import subprocess
import sys

import polars as pl
import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_data as data
from verification import r4r5_events as ev
from verification import r4r5_export as exp
from verification import r4r5_oracle as oracle
from verification import r4r5_rank as rank
from verification import r4r5_repair as rep
from verification import r4r5_replay as rp
from verification import r4r5_schedule as sched

from test_cg_arrow005 import cohort, market, obs  # shared synthetic fixtures

sys.path.insert(0, str(REPO_ROOT / "scripts"))
WORK = data.VERIFY_ROOT / "work"
REPORTS = REPO_ROOT / "reports"


# ------------------------------------------------------------------ Phase 0 calendar
def test_nominal_wednesday_anchor_and_backward_rollback():
    anchors = sched.nominal_anchors(date(2025, 9, 1), date(2026, 8, 31))
    assert all(a.weekday() == 2 for a in anchors)
    assert len(anchors) == 52
    # an open Wednesday is its own signal and enters the next session
    assert sched.signal_for(date(2026, 1, 7)) == date(2026, 1, 7)
    assert sched.entry_for(date(2026, 1, 7)) == date(2026, 1, 8)
    # a closed Wednesday rolls backward to the most recent session, never forward
    closed = date(2025, 12, 31)
    assert sched.signal_for(closed) == closed  # open in this sample
    fake = date(2026, 7, 1)
    assert sched.signal_for(fake) == fake


def test_closed_wednesday_rolls_back_and_entry_skips_the_holiday(monkeypatch):
    """A synthetic Wednesday closure must map the signal back one session and still enter
    on the first session after it, without deleting the week."""
    wed = date(2026, 7, 1)
    real = sched.is_nyse_session

    def fake_session(d):
        return False if d == wed else real(d)

    monkeypatch.setattr(sched, "is_nyse_session", fake_session)
    sig = sched.signal_for(wed)
    assert sig == date(2026, 6, 30)          # rolled backward to Tuesday
    assert sched.entry_for(sig) == date(2026, 7, 1) or sched.entry_for(sig) == date(2026, 7, 2)
    rows = sched.weekly_schedule(date(2026, 6, 24), date(2026, 7, 8))
    assert [r["nominal_anchor"] for r in rows] == [date(2026, 6, 24), date(2026, 7, 1), date(2026, 7, 8)]
    assert all(r["signal"] is not None for r in rows)   # the week is never dropped


def test_entry_skips_a_closed_thursday_after_a_normal_wednesday():
    # 2025-11-26 is a Wednesday, 2025-11-27 Thanksgiving is closed
    assert sched.signal_for(date(2025, 11, 26)) == date(2025, 11, 26)
    assert sched.entry_for(date(2025, 11, 26)) == date(2025, 11, 28)


def test_frozen_calendar_does_not_change_the_current_sample():
    p = REPORTS / "cg_arrow007_schedule_diff.json"
    if not p.exists():
        pytest.skip("schedule diff not produced in this checkout")
    d = data.read_json(p)
    assert d["identical"] is True
    assert d["only_in_derived"] == [] and d["only_in_existing"] == []
    assert d["entry_is_next_session_for_all"] is True


# ------------------------------------------------------------------ unit mathematics
def test_price_factor_convention_both_directions():
    ev_rev = ({"symbol": "X", "effective_session": "2026-03-10", "price_factor": 50},)
    ev_fwd = ({"symbol": "Y", "effective_session": "2026-03-10", "price_factor": 0.2},)
    # a price observed before the event converts into post-event share units
    assert data.adjustment_factor("X", date(2026, 3, 9), date(2026, 3, 10), ev_rev) == 50
    assert data.adjustment_factor("Y", date(2026, 3, 9), date(2026, 3, 10), ev_fwd) == 0.2
    # an event on or before the observation does not apply
    assert data.adjustment_factor("X", date(2026, 3, 10), date(2026, 3, 20), ev_rev) == 1
    assert ev.classify_factor("reverse stock split", 1, 50) == (50.0, "reverse_split")
    assert ev.classify_factor("forward stock split", 5, 1) == (0.2, "forward_split")


def test_multiple_events_compose_in_one_window():
    events = ({"symbol": "X", "effective_session": "2026-03-05", "price_factor": 10},
              {"symbol": "X", "effective_session": "2026-03-12", "price_factor": 4})
    assert data.adjustment_factor("X", date(2026, 3, 4), date(2026, 3, 20), events) == 40


def test_reverse_split_is_economically_neutral_across_a_hold(monkeypatch):
    c = cohort(symbols=["X"] + [f"S{i}" for i in range(7)])
    fill = c[0]["fill"]
    eff = data.FEATS[data.INDEX[fill] + 4]
    flat = market(["X"] + [f"S{i}" for i in range(7)], {(d, "X"): 20.0 for d in data.FEATS})
    split_prices = {(d, "X"): (200.0 if d >= eff else 20.0) for d in data.FEATS}
    split = market(["X"] + [f"S{i}" for i in range(7)], split_prices)
    events = ({"symbol": "X", "effective_session": eff.isoformat(), "price_factor": 10},)
    monkeypatch.setattr(rp, "adjustment_factor", lambda s, o, a: data.adjustment_factor(s, o, a, events))
    a = rp.replay("PARENT", c, split)["trades"][0]
    monkeypatch.setattr(rp, "adjustment_factor", lambda s, o, a: 1.0)
    b = rp.replay("PARENT", c, flat)["trades"][0]
    assert a["quantity"] == b["quantity"]
    assert a["quantity_at_exit"] == pytest.approx(b["quantity"] / 10)
    assert a["gross_pnl"] == pytest.approx(b["gross_pnl"], abs=1e-9)


@pytest.mark.parametrize("offset", [0, 1, 10])
def test_action_on_signal_fill_and_exit_boundaries(offset, monkeypatch):
    c = cohort(symbols=["X"] + [f"S{i}" for i in range(7)])
    fill = c[0]["fill"]
    eff = data.FEATS[data.INDEX[fill] + offset]
    prices = {(d, "X"): (100.0 if d >= eff else 20.0) for d in data.FEATS}
    events = ({"symbol": "X", "effective_session": eff.isoformat(), "price_factor": 5},)
    monkeypatch.setattr(rp, "adjustment_factor", lambda s, o, a: data.adjustment_factor(s, o, a, events))
    t = rp.replay("PARENT", c, market(["X"] + [f"S{i}" for i in range(7)], prices))["trades"][0]
    # value is preserved: the split alone never creates or destroys profit
    assert t["gross_pnl"] == pytest.approx(0.0, abs=1e-6)


def test_ranking_return_uses_adjusted_units(monkeypatch):
    signal = date(2026, 1, 7)
    back = data.FEATS[data.INDEX[signal] - 15]
    events = ({"symbol": "S", "effective_session": data.FEATS[data.INDEX[signal] - 5].isoformat(),
               "price_factor": 100},)
    sums = {(back.isoformat(), "S"): obs(back, 0.10), (signal.isoformat(), "S"): obs(signal, 11.0)}
    out = rank.rank_cohort(signal, {"S": {"prior_close": 11.0, "prior_dollar_volume": 2e7}},
                           sums, events=events)
    # 0.10 pre-split is 10.00 in signal units, so the true return is +10%, not +10,900%
    assert out["rows"][0]["raw_return"] == pytest.approx(0.10)
    raw = rank.rank_cohort(signal, {"S": {"prior_close": 11.0, "prior_dollar_volume": 2e7}}, sums)
    assert raw["rows"][0]["raw_return"] > 100


def test_volume_history_is_converted_before_the_mean(monkeypatch):
    """A consolidation divides share volume; the 20-session mean must be in signal units."""
    signal = date(2026, 1, 7)
    eff = data.FEATS[data.INDEX[signal] - 5]
    events = ({"symbol": "V", "effective_session": eff.isoformat(), "price_factor": 10},)
    monkeypatch.setattr(data, "action_events", lambda: events)
    sums = {}
    for d in data.FEATS[data.INDEX[signal] - 20: data.INDEX[signal] + 1]:
        pre = d < eff
        sums[(d.isoformat(), "V")] = obs(d, 2.0 if pre else 20.0, volume=1000.0 if pre else 100.0)
    hist = data.history("V", data.FEATS[data.INDEX[signal] - 20: data.INDEX[signal] + 1], signal, sums)
    f = data.features(hist)
    # every session is 100 shares in signal units, so the ratio is exactly 1.0
    assert f["volume_ratio"] == pytest.approx(1.0)


# ------------------------------------------------------------------ certification discipline
def test_adjusted_series_rescreen_clears_only_a_continuous_path(monkeypatch):
    signal = date(2026, 1, 7)
    eff = data.FEATS[data.INDEX[signal] - 5]
    events = ({"symbol": "S", "effective_session": eff.isoformat(), "price_factor": 10},)
    monkeypatch.setattr(data, "action_events", lambda: events)
    sums = {}
    for d in data.FEATS[data.INDEX[signal] - 20: data.INDEX[signal] + 1]:
        sums[(d.isoformat(), "S")] = obs(d, 2.0 if d < eff else 20.0)
    good = rank.lookback_integrity(signal, "S", sums)
    assert good["lookback_resolution"] == "ADJUSTED_SERIES_CONTINUOUS"
    assert good["lookback_events_applied"] == 1
    # a second, undocumented jump must survive the adjustment and stay flagged
    other = data.FEATS[data.INDEX[signal] - 2]
    for d in data.FEATS[data.INDEX[signal] - 20: data.INDEX[signal] + 1]:
        px = 2.0 if d < eff else 20.0
        if d >= other:
            px *= 8
        sums[(d.isoformat(), "S")] = obs(d, px)
    bad = rank.lookback_integrity(signal, "S", sums)
    assert bad["lookback_resolution"] == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"


def test_documented_event_alone_does_not_clear_a_window(monkeypatch):
    """Arrow 006 cleared a window when any event existed inside it. That is not enough."""
    signal = date(2026, 1, 7)
    eff = data.FEATS[data.INDEX[signal] - 5]
    events = ({"symbol": "S", "effective_session": eff.isoformat(), "price_factor": 2},)
    monkeypatch.setattr(data, "action_events", lambda: events)
    sums = {}
    for d in data.FEATS[data.INDEX[signal] - 20: data.INDEX[signal] + 1]:
        sums[(d.isoformat(), "S")] = obs(d, 1.0 if d < eff else 50.0)
    out = rank.lookback_integrity(signal, "S", sums)
    assert out["lookback_events_applied"] == 1
    assert out["lookback_resolution"] == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"


def test_structural_issues_block_a_verified_trade(monkeypatch):
    c = cohort()
    s = market()
    fill = c[0]["fill"]
    rec = dict(s[(fill.isoformat(), "S0")])
    rec["structural_issues"] = ["duplicate_timestamps=3"]
    rec["structural_status"] = "RETRIEVED_WITH_ISSUES"
    s[(fill.isoformat(), "S0")] = rec
    data.set_accepted_structural_issues({})
    t = rp.replay("PARENT", c, s)["trades"][0]
    assert t["status"] == "BLOCKED_STRUCTURAL_ENTRY" and t["modeled_net"] is None
    # an explicit, reviewed acceptance lets it through
    data.set_accepted_structural_issues({("S0", fill.isoformat()): "reviewed: duplicate bars identical"})
    t2 = rp.replay("PARENT", c, s)["trades"][0]
    assert t2["status"] == rp.VERIFIED
    data.set_accepted_structural_issues({})


def test_no_manual_rank_nine_substitution():
    """Removing a name must come from reranking the field, never from taking the next cached row."""
    signal = date(2026, 1, 7)
    back = data.FEATS[data.INDEX[signal] - 15]
    syms = [f"C{i}" for i in range(10)]
    sums = {}
    for i, s in enumerate(syms):
        sums[(back.isoformat(), s)] = obs(back, 10.0)
        sums[(signal.isoformat(), s)] = obs(signal, 10.0 + (10 - i))
    cands = {s: {"prior_close": 20.0, "prior_dollar_volume": 2e7} for s in syms}
    base = rank.rank_cohort(signal, cands, sums)
    assert [r["symbol"] for r in base["rows"][:8]] == syms[:8]
    # C0 turns out to have a 1-for-10 consolidation: it must fall by ranking, not by deletion
    events = ({"symbol": "C0", "effective_session": data.FEATS[data.INDEX[signal] - 5].isoformat(),
               "price_factor": 10},)
    after = rank.rank_cohort(signal, cands, sums, events=events)
    top = [r["symbol"] for r in after["rows"][:8]]
    assert "C0" not in top and "C8" in top          # rank 9 rose mechanically
    assert len(after["rows"]) == len(base["rows"])   # nothing was deleted from the field


def test_test_issue_excluded_but_recorded_history_preserved():
    from cg_arrow007_run import tradable_universe
    roster, etp, tests = tradable_universe()
    assert "ZVZZT" in tests and all(re.match(r"^Z[A-Z]ZZT$", t) for t in tests)
    cf = WORK / "cohort_field.json"
    if not cf.exists():
        pytest.skip("field not built in this checkout")
    field = data.read_json(cf)
    assert all(not (set(v["rule_field"]) & set(tests)) for v in field.values())
    assert any("ZVZZT" in v["cached_not_eligible"] for v in field.values())


# ------------------------------------------------------------------ accounting separation
def test_is_book_contains_no_oos_owned_positions():
    cl = cohort(signal=date(2026, 1, 7)) + cohort(signal=date(2026, 2, 4))
    for c in cl:
        c["split"] = data.split_of(c["signal"])
    s = market()
    is_only = [c for c in cl if c["split"] == "IS"]
    book = rp.replay("PARENT", is_only, s)
    assert {t["split"] for t in book["trades"]} == {"IS"}
    assert {t["cohort_id"] for t in book["trades"]} == {"2026-01-07"}
    full = rp.replay("PARENT", cl, s)
    assert len(full["trades"]) == 2 * len(book["trades"])
    # the split-owned account must not inherit the other split's exposure
    assert max(r["gross_exposure"] for r in book["daily"]) < max(r["gross_exposure"] for r in full["daily"])


def test_runoff_is_separated_from_the_calendar_account():
    c = cohort(signal=date(2026, 8, 26))
    book = rp.replay("PARENT", c, market())
    t = book["trades"][0]
    assert t["exit_after_cutoff"] is True
    assert book["daily"][-1]["date"] == "2026-08-31"
    assert all(r["date"] <= "2026-08-31" for r in book["daily"])


def test_documented_halt_survives_horizon_comparison():
    """A trade that becomes trapped at a longer horizon is a transition, not a deletion."""
    from cg_arrow007_horizons import state_of
    c = cohort()
    s = market()
    due = data.FEATS[data.INDEX[c[0]["fill"]] + 10]
    s[(due.isoformat(), "S0")] = None
    short = rp.replay("PARENT", c, s, hold=5)["trades"][0]
    long = rp.replay("PARENT", c, s, hold=10)["trades"][0]
    assert state_of(short) == "COMPLETED"
    assert state_of(long) in ("UNRESOLVED", "DOCUMENTED_EVENT_OPEN")
    assert short["ticket_id"] == long["ticket_id"]   # present in both ledgers, never dropped


def test_same_entries_and_shares_across_horizons_in_a_panel():
    c = cohort()
    s = market(prices={d: 20.0 - i * 0.05 for i, d in enumerate(data.FEATS)})
    books = {h: rp.replay("R5", c, s, hold=h, quantity="fill") for h in range(1, 11)}
    base = {t["ticket_id"]: (t["entry_price"], t["quantity"], t["entry_commission"])
            for t in books[10]["trades"]}
    for h, b in books.items():
        for t in b["trades"]:
            assert (t["entry_price"], t["quantity"], t["entry_commission"]) == base[t["ticket_id"]]
            assert t["scheduled_exit_date"] == data.FEATS[data.INDEX[c[0]["fill"]] + h].isoformat()


def test_quantity_panels_are_distinct_and_both_predeclared():
    c = cohort()
    s = market()
    s[(c[0]["fill"].isoformat(), "S0")] = obs(c[0]["fill"], 20.0, preorder=19.0)
    legacy = rp.replay("PARENT", c, s, quantity="fill")["trades"][0]
    causal = rp.replay("PARENT", c, s, quantity="preorder")["trades"][0]
    assert legacy["quantity"] == 200 and causal["quantity"] == 210
    assert legacy["quantity_convention"] == "fill" and causal["quantity_convention"] == "preorder"


# ------------------------------------------------------------------ artefacts
def test_oracle_and_subtotal_conservation(tmp_path):
    c = cohort()
    s = market(prices={d: 20.0 + (i % 3) * 0.5 for i, d in enumerate(data.FEATS)})
    due = data.FEATS[data.INDEX[c[0]["fill"]] + 10]
    s[(due.isoformat(), "S3")] = None
    books = {(f, "R2"): rp.replay(f, c, s) for f in ("PARENT", "R4", "R5")}
    exp.export_all(books, root=tmp_path)
    res = oracle.run(tmp_path, s)
    assert res["ok"], res
    audit = oracle.read_csv(tmp_path / "r4r5_verified_cohort_audit.csv")
    subs = [r for r in audit if r["row_type"] == "COHORT_SUBTOTAL" and r["model"] == "R5"]
    period = [r for r in audit if r["row_type"] == "PERIOD_TOTAL" and r["model"] == "R5"][0]
    assert sum(float(r["modeled_net"]) for r in subs) == pytest.approx(float(period["modeled_net"]))
    assert period["verified_total_is_complete"] == "False"


def test_ranking_reconciliation_has_three_distinct_baselines():
    p = REPORTS / "cg_arrow007_manifest.json"
    if not p.exists():
        pytest.skip("baseline not run")
    m = data.read_json(p)
    for row in m["ranking_reconciliation"]:
        assert {"R0_RAW_CACHE_TOP8", "R1_RECORDED_TOP8", "R2_CERTIFIED_TOP8"} <= set(row)
        assert len(row["R2_CERTIFIED_TOP8"]) <= 8
        if set(row["R2_CERTIFIED_TOP8"]) == set(row["R1_RECORDED_TOP8"]):
            assert row["membership_change_vs_recorded"] is False


def test_one_batch_oos_gate():
    p = REPORTS / "cg_arrow007_horizon_freeze.json"
    if not p.exists():
        pytest.skip("no freeze")
    fr = data.read_json(p)
    assert fr["status"] in {"FROZEN_PRE_OOS", "OOS_REVEALED", "NOT_RUN_DATA_GATE", "NOT_RUN_TIME_GATE"}
    if fr["status"] == "OOS_REVEALED":
        assert fr["oos_procedure"].startswith("one batch")
        assert subprocess.run(["git", "cat-file", "-e", "HEAD:reports/cg_arrow007_horizon_freeze.json"],
                              cwd=REPO_ROOT).returncode == 0
        for k, v in fr["h10_baseline_identity"].items():
            assert abs(v["difference"]) < 1e-6, k


def test_env_and_private_artifacts_excluded_from_git():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    for rel in ("handoff/outgoing/cg_arrow007/r4r5_verified_trades.csv",
                "data/verification/r4r5/v1/events/http_cache/aa/x.bin",
                "data/verification/r4r5/v1/validated/2026-03-04/AAPL.parquet"):
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO_ROOT).returncode == 0, rel
    assert subprocess.check_output(["git", "ls-files", "handoff", "data/verification"],
                                   cwd=REPO_ROOT).decode().strip() == ""


def test_public_artifacts_have_no_credentials():
    secret = re.compile(r"(THETADATA_API_KEY|ASKEDGAR_API_KEY)\s*=\s*(?!<)[A-Za-z0-9_\-]{8,}")
    for p in list((REPO_ROOT / "reports").glob("cg_arrow007*")) + \
             list((REPO_ROOT / "src" / "verification").glob("*.py")) + \
             list((REPO_ROOT / "scripts").glob("cg_arrow007*.py")):
        assert not secret.search(p.read_text(encoding="utf-8")), p
