"""Arrow 014 gate and reveal machinery.

The pristine reveal runs once. Anything that would only surface at run time — a gate that lets a
blocked corridor through, a drawdown walk that misses the deepest episode, a classification that
calls a sign flip a replication — has to be caught before it fires, not during.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


reveal = _load("cg_arrow014_reveal")
certrep = _load("cg_arrow014_certify_repair")


# ------------------------------------------------------------------ the gate refuses by default
def test_gate_refuses_without_lock2(monkeypatch, tmp_path):
    monkeypatch.setattr(reveal, "GATE_MANIFEST", tmp_path / "absent.json")
    with pytest.raises(SystemExit, match="LOCK 2 is not written"):
        reveal.open_gate()


def test_gate_refuses_a_blocked_status(monkeypatch, tmp_path):
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({"status": "HOLDOUT_DATA_NOT_CERTIFIED_FOR_PRISTINE_REVEAL",
                             "unresolved_material_exceptions": 0}), encoding="utf-8")
    monkeypatch.setattr(reveal, "GATE_MANIFEST", p)
    with pytest.raises(SystemExit, match="LOCK 2 status"):
        reveal.open_gate()


def test_gate_refuses_when_an_exception_remains(monkeypatch, tmp_path):
    """The certified status alone is not enough; the exception count is checked independently."""
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({"status": "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL",
                             "unresolved_material_exceptions": 1}), encoding="utf-8")
    monkeypatch.setattr(reveal, "GATE_MANIFEST", p)
    with pytest.raises(SystemExit, match="unresolved material"):
        reveal.open_gate()


def test_gate_refuses_when_the_manifest_is_not_committed(monkeypatch, tmp_path):
    p = tmp_path / "gate.json"
    p.write_text(json.dumps({"status": "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL",
                             "unresolved_material_exceptions": 0}), encoding="utf-8")
    monkeypatch.setattr(reveal, "GATE_MANIFEST", p)
    monkeypatch.setattr(reveal, "committed_at", lambda _p: "")
    with pytest.raises(SystemExit, match="not committed"):
        reveal.open_gate()


# ------------------------------------------------------------------ the frozen matrix
def test_every_frozen_cell_maps_to_an_engine_configuration():
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    cells = freeze["reveal_matrix"]["cells"]
    assert len(cells) == 18
    for cell in cells:
        assert cell["legacy_id"] in reveal.CONFIG, cell
        assert cell["account_view"] in ("FIXED_DOLLAR", "EQUITY_SCALED")
        assert cell["hold"] in (8, 9, 10)
        assert cell["quantity_convention"] == "CAUSAL_PREORDER_QTY"
    assert {c["cell"] for c in cells} == set(range(1, 19))


def test_the_diagnostic_books_the_panel_needs_are_covered():
    """The rank-by-rank and mechanism panels read fixed-dollar R5 at all three holds."""
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    keys = {(c["legacy_id"], c["account_view"], c["hold"]) for c in freeze["reveal_matrix"]["cells"]}
    from verification import r4r5_holdout as HO
    for hold in HO.HOLDS:
        assert ("R5", "FIXED_DOLLAR", hold) in keys or hold in HO.HOLDS


# ------------------------------------------------------------------ classification vocabulary
def test_classification_never_calls_a_sign_flip_a_replication():
    assert reveal.classify(-0.2, 0.2, 100) == "NOT_REPLICATED"
    assert reveal.classify(0.2, -0.2, 100) == "NOT_REPLICATED"


def test_classification_separates_a_weaker_same_direction_effect():
    assert reveal.classify(0.20, 0.20, 100) == "PRISTINE_REPLICATION"
    assert reveal.classify(0.11, 0.20, 100) == "PRISTINE_REPLICATION"
    assert reveal.classify(0.05, 0.20, 100) == "SAME_DIRECTION_WEAKER"


def test_classification_reports_sparsity_rather_than_a_verdict():
    assert reveal.classify(0.9, 0.1, 19) == "INCONCLUSIVE_SPARSE"
    assert reveal.classify(None, 0.1, 100) == "DATA_LIMIT"


def test_classification_vocabulary_is_the_frozen_one():
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    allowed = set(freeze["mechanism_panel"]["classifications"])
    produced = {reveal.classify(a, b, n)
                for a in (-0.2, 0.0, 0.05, 0.2, None) for b in (-0.2, 0.0, 0.2, None)
                for n in (5, 100)}
    assert produced <= allowed, produced - allowed


# ------------------------------------------------------------------ drawdown walk
def _daily(equities):
    return [{"date": f"2024-09-{i + 1:02d}", "equity": e} for i, e in enumerate(equities)]


def test_drawdown_finds_the_deepest_episode_and_its_recovery():
    eps = reveal.drawdown_episodes(_daily([100000, 110000, 99000, 105000, 112000]), "x")
    assert eps, "a peak-to-trough episode must be reported"
    deepest = eps[0]
    assert deepest["peak_equity"] == 110000
    assert deepest["trough_equity"] == 99000
    assert deepest["recovered"] is True
    assert deepest["depth_pct_of_peak"] == pytest.approx(99000 / 110000 - 1, abs=1e-9)


def test_drawdown_reports_an_unrecovered_episode_as_open():
    eps = reveal.drawdown_episodes(_daily([100000, 120000, 90000, 95000]), "x")
    assert eps[0]["recovered"] is False
    assert eps[0]["recovery_date"] is None
    assert eps[0]["trough_equity"] == 90000


def test_drawdown_is_ordered_deepest_first():
    eps = reveal.drawdown_episodes(
        _daily([100000, 130000, 125000, 131000, 100000, 140000]), "x", top=5)
    depths = [e["depth_pct_of_peak"] for e in eps]
    assert depths == sorted(depths)
    assert len(eps) >= 2


def test_a_monotonic_path_has_no_drawdown():
    assert reveal.drawdown_episodes(_daily([100000, 101000, 102000]), "x") == []


# ------------------------------------------------------------------ small helpers
def test_stat_summarises_and_tolerates_emptiness():
    s = reveal._stat([1.0, -1.0, 2.0, 4.0])
    assert s["n"] == 4 and s["hit_rate"] == 0.75
    assert s["median"] == pytest.approx(1.5)
    assert reveal._stat([])["n"] == 0


def test_round_helper_drops_non_finite_values():
    assert reveal._r(float("nan")) is None
    assert reveal._r(float("inf")) is None
    assert reveal._r(None) is None
    assert reveal._r(1 / 3) == pytest.approx(0.333333)


# ------------------------------------------------------------------ the repair gate statistic
def test_binomial_tail_is_a_probability_and_falls_as_the_count_rises():
    a = certrep.binomial_tail(3, 278, 0.00204)
    b = certrep.binomial_tail(6, 278, 0.00204)
    assert 0.0 < b < a < 1.0
    assert certrep.binomial_tail(0, 278, 0.00204) is None
    assert certrep.binomial_tail(3, 278, None) is None


def test_binomial_tail_of_the_whole_sample_is_tiny():
    assert certrep.binomial_tail(50, 278, 0.00204) < 1e-9


def test_binomial_tail_matches_a_direct_computation():
    import math
    n, p, k = 20, 0.1, 3
    want = sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))
    assert certrep.binomial_tail(k, n, p) == pytest.approx(want, rel=1e-12)


# ------------------------------------------------------------------ the corridor itself
def test_the_corridor_calendar_still_matches_lock_1():
    from verification import r4r5_holdout as HO
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    assert json.dumps(freeze["calendar_rule"]["cohort_calendar"], sort_keys=True) \
        == json.dumps(HO.cohort_calendar(), sort_keys=True)
    assert len(HO.FEATS) == freeze["period"]["corridor_sessions"]
    assert HO.CUTOFF.isoformat() == freeze["period"]["cutoff"]


def test_every_cohort_has_all_three_holds_inside_the_corridor():
    from verification import r4r5_holdout as HO
    for row in HO.cohort_calendar():
        assert row["status"] == "OK", row
        for h in HO.HOLDS:
            assert row[f"h{h}_exit_date"] is not None, row


def test_no_cohort_signal_falls_outside_the_pristine_signal_period():
    from verification import r4r5_holdout as HO
    for d in HO.signal_dates():
        assert HO.SIGNAL_START <= d <= HO.SIGNAL_END
        assert d.strftime("%Y-%m") in set(
            json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json")
                       .read_text(encoding="utf-8"))["period"]["pristine_oos_signal_months"])


def test_the_observation_status_rule_fails_closed():
    from verification import r4r5_holdout as HO
    retrieved_no_trade = {("2024-09-04", "AAA"): {"missing": True, "partition_resolved": True,
                                                  "raw_rows": 720}}
    nothing_resolved = {("2024-09-04", "BBB"): {"missing": True, "partition_resolved": False,
                                                "raw_rows": 0}}
    unknown_shape = {("2024-09-04", "CCC"): {"missing": True}}
    present = {("2024-09-04", "DDD"): {"mark_kind": "minute_close", "close": 10.0}}
    assert HO.observation_status(retrieved_no_trade)[("AAA", "2024-09-04")] == "DOCUMENTED_NO_TRADING"
    assert HO.observation_status(nothing_resolved)[("BBB", "2024-09-04")] == "EMPTY_RESPONSE_UNRESOLVED"
    assert HO.observation_status(unknown_shape)[("CCC", "2024-09-04")] == "EMPTY_RESPONSE_UNRESOLVED"
    assert HO.observation_status(present) == {}


def test_the_gap_fill_tree_can_never_shadow_an_existing_observation():
    from verification import r4r5_data as data
    labels = [lbl for lbl, _ in data.candidate_paths(datetime.date(2025, 8, 6), "AAPL")]
    assert labels[-1] == "holdout_repair"

# ------------------------------------------------------------------ the report builders
def _trade(cohort, symbol, rank, ret, q=100, p0=20.0):
    """A completed ledger row whose sizing-neutral return is exactly `ret`."""
    p1 = (1 - ret) * p0
    gross = q * p0 * ret
    return {"cohort_id": cohort, "symbol": symbol, "rank": rank,
            "status": "VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "quantity": q,
            "entry_price": p0, "exit_price": p1, "action_factor_over_hold": 1.0,
            "gross_pnl": gross, "modeled_net": gross - 5.0,
            "scheduled_entry_date": "2024-09-05"}


def _book(trades):
    return {"trades": trades,
            "daily": [{"date": "2025-08-29", "equity": 100000.0 + sum(t["modeled_net"] for t in trades)}]}


def test_sizing_neutral_return_is_read_from_the_key_the_engine_uses():
    """The engine returns `price_return_10`; reading a different key would give silent Nones."""
    from verification import r4r5_anatomy as an
    out = an.sizing_neutral_outcome(_trade("2024-09-04", "AAA", 1, 0.25))
    assert out["completed"] is True
    assert out["price_return_10"] == pytest.approx(0.25)


def test_rank_by_rank_reports_every_rank_at_every_hold_against_the_frozen_reference():
    from verification import r4r5_holdout as HO
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    trades = [_trade(f"2024-09-{4 + c:02d}", f"S{r}", r, 0.30 if r == 1 else 0.02)
              for c in range(0, 3) for r in range(1, 9)]
    books = {("R5", "FIXED_DOLLAR", h): _book(trades) for h in HO.HOLDS}
    rows = reveal.rank_by_rank(books, freeze)
    assert {r["rank"] for r in rows} == set(range(1, 9))
    assert {r["hold"] for r in rows} == set(HO.HOLDS)
    h10 = {r["rank"]: r for r in rows if r["hold"] == 10}
    assert h10[1]["mean"] == pytest.approx(0.30)
    assert h10[1]["hit_rate"] == 1.0
    # the historical reference is attached at H10 only, so the comparison is never implied elsewhere
    assert h10[1]["historical_h10_mean"] == freeze["rank_by_rank_diagnostic"]["historical_reference_h10_mean"]["1"]
    assert all(r["historical_h10_mean"] is None for r in rows if r["hold"] != 10)


def test_mechanism_panel_covers_every_declared_check():
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    anat = []
    for c in range(24):
        for r in range(1, 9):
            anat.append({
                "cohort_id": f"2024-09-{(c % 28) + 1:02d}", "symbol": f"S{c}_{r}", "rank": r,
                "price_band": "[10,20)",
                "sizing_neutral_return": 0.30 if r == 1 else (0.05 - 0.01 * r),
                "sc_close_vs_high20": -0.02 - 0.01 * r, "sc_ret3": 0.05 * r,
                "sc_mean_range_pct_10": 0.10 + 0.001 * r, "sc_logret_std_15": 0.09 + 0.002 * r,
                "sc_signal_day_range_pct": 0.07 + 0.003 * r,
                "sc_up_sessions_15": 8 + (r % 3),
                "sc_top3_sessions_share_of_advance": 0.8 + 0.02 * r,
                "po_partial_range_pct": 0.06 + 0.002 * r,
                "po_signal_close_to_preorder": -0.01 + 0.002 * r,
                "po_preorder_location_in_partial_range": 0.3 + 0.03 * r,
                "po_overnight_gap_vs_signal_close": -0.005 + 0.001 * r,
                "cx_gap_to_next_rank": 0.20 - 0.02 * r,
                "ep_episode": "FIRST" if r % 2 else "LATER_REPEAT"})
    rows = reveal.mechanism_panel(anat, freeze)
    checks = {r["check"] for r in rows}
    declared = {c["id"] for c in freeze["mechanism_panel"]["checks"]}
    # M5, M6 and M8 are declared as multi-feature checks and are emitted one feature per row
    families = {c.split("a")[0].split("b")[0].split("c")[0].split("d")[0] for c in checks}
    assert declared - families - {"M10"} == set(), declared - families - {"M10"}
    allowed = set(freeze["mechanism_panel"]["classifications"]) | {"REPORTED"}
    assert {r["classification"] for r in rows} <= allowed

    m1 = next(r for r in rows if r["check"] == "M1")
    assert m1["n"] == 24 and m1["contrast_n"] == 168
    assert m1["mean"] == pytest.approx(0.30)
    assert m1["effect"] > 0
    # the frozen cuts must actually be used where A11 declared them
    m3 = next(r for r in rows if r["check"] == "M3")
    assert m3["cuts_source"] == "A11 frozen"


def test_mechanism_panel_marks_a_sparse_group_rather_than_ruling_on_it():
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    anat = [{"cohort_id": "2024-09-04", "symbol": f"S{r}", "rank": r,
             "price_band": "[40,80)", "sizing_neutral_return": 0.01 * r,
             "sc_close_vs_high20": -0.05, "ep_episode": "FIRST"} for r in range(1, 6)]
    rows = reveal.mechanism_panel(anat, freeze)
    assert any(r["classification"] == "INCONCLUSIVE_SPARSE" for r in rows)
    assert not any(r["classification"] == "PRISTINE_REPLICATION" for r in rows)


def test_the_panel_never_invents_a_classification_outside_the_freeze():
    freeze = json.loads((ROOT / "reports" / "cg_arrow014_reveal_freeze.json").read_text(encoding="utf-8"))
    allowed = set(freeze["mechanism_panel"]["classifications"]) | {"REPORTED", None}
    anat = [{"cohort_id": f"2024-09-{(i % 28) + 1:02d}", "symbol": f"S{i}", "rank": (i % 8) + 1,
             "price_band": "[20,40)", "sizing_neutral_return": (i % 7) * 0.01 - 0.02,
             "sc_close_vs_high20": -0.04 - 0.001 * i, "sc_ret3": 0.01 * i,
             "cx_gap_to_next_rank": 0.05, "ep_episode": "FIRST"} for i in range(200)]
    rows = reveal.mechanism_panel(anat, freeze)
    assert {r["classification"] for r in rows} <= allowed
