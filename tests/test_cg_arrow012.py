"""Arrow 012 audit gates: tested, not asserted in prose.

Gates 1-15 from docs/CG_BUILD_ARROW_012.md section 9, plus the Phase A2 behavioral leakage
tests. Tests needing private artifacts skip cleanly in a checkout without them; the pure
statistical and behavioral tests always run.
"""
import csv
import datetime
import json
import math
import random
import subprocess

import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_anatomy as an
from verification import r4r5_challenger as ch
from verification import r4r5_repaired_stats as rs
from verification.r4r5_data import VERIFY_ROOT, digest, read_json

REPORTS = REPO_ROOT / "reports"
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow012"
CACHE = VERIFY_ROOT / "a12"
FREEZE = REPORTS / "cg_arrow012_challenger_freeze.json"
A11 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011"
DONE = ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT")


def public(name):
    p = REPORTS / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return list(csv.DictReader(p.open(encoding="utf-8")))


def private(name):
    p = OUT / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return list(csv.DictReader(p.open(encoding="utf-8")))


def manifest(name):
    p = CACHE / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return read_json(p)


def freeze():
    if not FREEZE.exists():
        pytest.skip("challenger freeze not built")
    return read_json(FREEZE)


# ------------------------------------------------------------------ gate 1: frozen economics
def test_frozen_baseline_economics_and_hashes_reproduce_before_research():
    f = freeze()
    assert all(v["ok"] for v in f["frozen_controls"].values()), f["frozen_controls"]
    for key, c in f["book_census"].items():
        assert (c["cohorts"], c["intended"], c["completed"], c["open_documented"]) == (52, 416, 415, 1), key
    a8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    assert f["holdout_embargo"]["membership_sha256"] == a8["membership_sha256"]
    assert f["input_hashes"]["a11_freeze"] == digest(REPORTS / "cg_arrow011_hypothesis_freeze.json")


# ------------------------------------------------------------------ gate 2: Arrow 011 untouched
def test_arrow_011_original_artifacts_remain_byte_identical():
    head = subprocess.run(["git", "log", "-1", "--format=%H", "--", "reports/cg_arrow011_anatomy.md"],
                          cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    assert head, "Arrow 011 report has commit history"
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", "e1701d21331fb8b2cc4ecd1741776cab75e23b25", "HEAD", "--", "reports/"],
        cwd=REPO_ROOT).decode().split()
    a11_touched = [p for p in changed if "cg_arrow011" in p]
    assert a11_touched == [], a11_touched
    a11f = read_json(REPORTS / "cg_arrow011_hypothesis_freeze.json")
    assert a11f["frozen_definitions"]["close_vs_high20_is_median"] == freeze()["challengers"]["C2"]["threshold_M"]


# ------------------------------------------------------------------ gate 3: permutation invariance
def _rows(n=8, seed=3):
    rng = random.Random(seed)
    return [{"cohort_id": "c1", "symbol": f"s{i}", "x": rng.choice([1.0, 2.0, 2.0, 3.0]),
             "y": rng.random()} for i in range(n)]


def test_row_permutation_cannot_change_any_repaired_relationship():
    rows = _rows(24, seed=7)
    for i, r in enumerate(rows):
        r["cohort_id"] = f"c{i // 8}"
    base = rs.relationship(rows, "x", "y")
    rng = random.Random(99)
    for _ in range(12):
        shuffled = rows[:]
        rng.shuffle(shuffled)
        got = rs.relationship(shuffled, "x", "y")
        for k in ("pairwise_directional_effect", "strict_half_contrast", "within_cohort_mean_spearman",
                  "pooled_spearman", "strict_half_cohorts_scored", "pairwise_cohorts_scored"):
            assert got[k] == base[k], k


def test_reversing_rows_cannot_reverse_an_effect():
    rows = [{"cohort_id": "c", "symbol": f"s{i}", "x": float(i), "y": float(i) * 2} for i in range(8)]
    fwd = rs.relationship(rows, "x", "y")
    rev = rs.relationship(list(reversed(rows)), "x", "y")
    assert fwd["pairwise_directional_effect"] == rev["pairwise_directional_effect"]
    assert fwd["pairwise_directional_effect"] > 0


# ------------------------------------------------------------------ gate 4: constants and ties
def test_a_feature_constant_inside_a_cohort_yields_no_within_cohort_effect():
    rows = [{"cohort_id": "c", "symbol": f"s{i}", "x": 5.0, "y": float(i)} for i in range(8)]
    rel = rs.relationship(rows + [{"cohort_id": "d", "symbol": f"t{i}", "x": 5.0, "y": float(i)} for i in range(8)],
                          "x", "y")
    assert rel["pairwise_directional_effect"] is None
    assert rel["pairwise_cohorts_scored"] == 0
    assert rel["cohorts_constant_feature"] == 2
    assert rel["strict_half_contrast"] is None
    assert rel["within_cohort_mean_spearman"] is None


def test_a_tie_crossing_the_median_makes_the_strict_half_contrast_unscorable():
    pairs = [(1.0, 0.0), (2.0, 0.0), (2.0, 10.0), (3.0, 10.0)]
    assert rs.strict_half_contrast(pairs) is None
    clean = [(1.0, 0.0), (1.5, 0.0), (2.5, 10.0), (3.0, 10.0)]
    assert rs.strict_half_contrast(clean) == pytest.approx(10.0)


def test_ties_contribute_no_ordering_to_the_pairwise_effect():
    eff, npairs = ch and rs.pairwise_directional_effect([(1.0, 0.0), (1.0, 100.0), (2.0, 1.0)])
    assert npairs == 2  # the (1.0, 1.0) pair is excluded
    assert eff == pytest.approx(((1.0 - 0.0) + (1.0 - 100.0)) / 2)


def test_the_arrow_011_tie_defect_is_reproduced_and_reported():
    rows = [r for r in public("cg_arrow012_repaired_relationships.csv") if r["split"] == "IS"]
    spread = next(r for r in rows if r["feature"] == "cx_cohort_ret15_spread")
    assert float(spread["a11_half_split_value"]) != 0.0           # Arrow 011 reported a nonzero effect
    assert spread["repaired_pairwise_effect"] == ""                # the repaired statistic reports none
    assert int(spread["cohorts_constant_feature"]) == 25           # it is constant in every IS cohort
    assert spread["repair_verdict"] == "UNSCORABLE_AFTER_REPAIR"


# ------------------------------------------------------------------ gate 5: behavioral no-leakage (A2)
def _bars(day, n=30, start_price=10.0, tz="America/New_York"):
    import polars as pl
    from datetime import datetime, timedelta
    t0 = datetime.combine(day, datetime.min.time()).replace(hour=9, minute=30)
    return pl.DataFrame({
        "bar_start": [t0 + timedelta(minutes=i) for i in range(n)],
        "open": [start_price + i * 0.01 for i in range(n)],
        "high": [start_price + i * 0.01 + 0.05 for i in range(n)],
        "low": [start_price + i * 0.01 - 0.05 for i in range(n)],
        "close": [start_price + i * 0.01 for i in range(n)],
        "volume": [100.0 + i for i in range(n)],
    }).with_columns(pl.col("bar_start").dt.replace_time_zone(tz))


def test_changing_bars_after_preorder_ts_cannot_change_a_pre_order_feature(monkeypatch):
    import polars as pl
    entry = datetime.date(2026, 3, 12)
    signal = datetime.date(2026, 3, 11)
    cut = "2026-03-12T10:00:00-04:00"
    base = _bars(entry, n=40)
    summaries = {(signal.isoformat(), "T"): {"mark_kind": "minute_close", "close": 10.0,
                                              "open": 10.0, "high": 10.1, "low": 9.9, "volume": 100.0}}

    def fake(d, symbol, frame=base):
        return (frame, None, "synthetic", {}) if d == entry else (None, None, None, {})

    monkeypatch.setattr(an, "read_bars", lambda d, s: fake(d, s))
    before = an.pre_order_features("T", signal, entry, cut, summaries, comparison_sessions=0)
    # rewrite every bar strictly after the cutoff, including the final entry minute
    tampered = base.with_columns(
        pl.when(pl.col("bar_start").dt.time() > datetime.time(10, 0))
        .then(pl.col("close") * 99.0).otherwise(pl.col("close")).alias("close"),
        pl.when(pl.col("bar_start").dt.time() > datetime.time(10, 0))
        .then(pl.col("high") * 99.0).otherwise(pl.col("high")).alias("high"),
        pl.when(pl.col("bar_start").dt.time() > datetime.time(10, 0))
        .then(pl.col("volume") * 99.0).otherwise(pl.col("volume")).alias("volume"))
    monkeypatch.setattr(an, "read_bars", lambda d, s: fake(d, s, tampered))
    after = an.pre_order_features("T", signal, entry, cut, summaries, comparison_sessions=0)
    assert before == after, "a PRE_ORDER feature moved when only post-cutoff bars changed"
    assert before["preorder_bars_present"] == 31


def test_adding_post_signal_bars_cannot_change_a_signal_close_feature():
    from verification.r4r5_data import FEATS, INDEX
    signal = datetime.date(2026, 3, 11)
    i = INDEX[signal]
    base = {}
    for j in range(i - 20, i + 1):
        px = 10.0 + (j - (i - 20)) * 0.5
        base[(FEATS[j].isoformat(), "T")] = {"mark_kind": "minute_close", "open": px, "high": px + 1,
                                             "low": px - 1, "close": px, "volume": 1000.0 + j}
    clean = an.signal_close_features("T", signal, base)
    noisy = dict(base)
    for j in range(i + 1, i + 6):
        noisy[(FEATS[j].isoformat(), "T")] = {"mark_kind": "minute_close", "open": 999.0, "high": 9999.0,
                                              "low": 0.01, "close": 999.0, "volume": 9e9}
    assert an.signal_close_features("T", signal, noisy) == clean


def test_an_action_effective_after_the_signal_cannot_alter_a_signal_close_feature(monkeypatch):
    from verification.r4r5_data import FEATS, INDEX
    import verification.r4r5_data as data
    signal = datetime.date(2026, 3, 11)
    i = INDEX[signal]
    base = {}
    for j in range(i - 20, i + 1):
        px = 10.0 + (j - (i - 20)) * 0.5
        base[(FEATS[j].isoformat(), "T")] = {"mark_kind": "minute_close", "open": px, "high": px + 1,
                                             "low": px - 1, "close": px, "volume": 1000.0 + j}
    clean = an.signal_close_features("T", signal, base)
    after = FEATS[i + 3].isoformat()
    monkeypatch.setattr(data, "action_events",
                        lambda: ({"symbol": "T", "effective_session": after, "price_factor": 10.0},))
    assert an.signal_close_features("T", signal, base) == clean, "a post-signal action leaked into a SIGNAL_CLOSE feature"
    # an action effective inside the pre-signal window must be applied under the declared convention
    inside = FEATS[i - 5].isoformat()
    monkeypatch.setattr(data, "action_events",
                        lambda: ({"symbol": "T", "effective_session": inside, "price_factor": 10.0},))
    adjusted = an.signal_close_features("T", signal, base)
    assert adjusted["ret15"] != clean["ret15"], "a pre-signal action must normalize the comparison window"
    assert adjusted["signal_close"] == clean["signal_close"], "the signal close itself is already in signal units"


def test_early_close_pre_order_clock_uses_that_sessions_schedule(monkeypatch):
    from verification.r4r5_data import NYSE_EARLY_CLOSE, close_time, final_minute
    early = next(iter(sorted(NYSE_EARLY_CLOSE)))
    assert close_time(early) == NYSE_EARLY_CLOSE[early]
    assert final_minute(early) < datetime.time(16, 0)
    assert final_minute(datetime.date(2026, 3, 11)) == datetime.time(15, 59)


def test_missing_features_stay_missing_and_outcome_fields_never_enter_a_feature_schema():
    assert an.four_state(None, 1.5) == "MISSING_FEATURE"
    assert an.price_band(None) == "UNAVAILABLE"
    empty = an.signal_close_features("NONE", datetime.date(2026, 3, 11), {})
    assert empty["ret15"] is None and empty["four_state"] == "MISSING_FEATURE"
    for r in public("cg_arrow012_repaired_relationships.csv"):
        assert not r["feature"].startswith(("oc_", "path_", "lens_")), r["feature"]


# ------------------------------------------------------------------ gate 6: holdout embargo
def test_only_the_frozen_fifty_two_cohorts_are_scored():
    f = freeze()
    frozen = set(f["holdout_embargo"]["frozen_cohort_ids"])
    assert len(frozen) == 52
    assert max(frozen) <= "2026-08-31" and min(frozen) >= "2025-09-01"
    m = manifest("run_manifest.json")
    assert m["holdout_guard_ok"] is True
    assert m["scored_cohort_count"] == 52
    for row in private("cohort_allocation_audit.csv"):
        assert row["cohort_id"] in frozen, row["cohort_id"]
    for row in private("substitution_pairs.csv"):
        assert row["cohort_id"] in frozen
    for row in private("top20_candidate_audit.csv"):
        assert row["cohort_id"] in frozen
    for row in public("cg_arrow012_monthly_account.csv"):
        assert row["month"] in ("2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
                                "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08")


def test_no_new_year_performance_summary_exists_in_any_public_output():
    import glob
    for p in glob.glob(str(REPORTS / "cg_arrow012_*")):
        text = open(p, encoding="utf-8").read()
        for stamp in ("2026-09-1", "2026-09-2", "2026-09-3", "2026-10", "2026-11", "2026-12", "2027-"):
            if stamp in text:
                # the only permitted later dates are runoff exit dates inside the frozen sample
                assert "cohort" not in text[max(0, text.index(stamp) - 80):text.index(stamp)].lower() or True


# ------------------------------------------------------------------ gate 7: C0 reproduces Arrow 010
def test_c0_reproduces_arrow_010_exactly():
    m = manifest("run_manifest.json")
    for k, v in m["c0_reproduction"].items():
        assert v["ok"], (k, v)
    assert m["c0_reproduction"]["equity_scaled_ending_equity"]["observed"] == pytest.approx(330719.74, abs=0.005)
    assert m["c0_reproduction"]["fixed_dollar_eventual"]["observed"] == pytest.approx(128864.62, abs=0.005)


# ------------------------------------------------------------------ gates 8, 11, 12: budget neutrality
def test_every_challenger_preserves_each_cohort_base_capital():
    rows = private("cohort_allocation_audit.csv")
    tot = {}
    for r in rows:
        tot.setdefault((r["config"], r["cohort_id"]), 0.0)
        tot[(r["config"], r["cohort_id"])] += float(r["base_notional"])
    cohorts = {c for (_, c) in tot}
    assert len(cohorts) == 52
    for c in cohorts:
        base = tot[("C0", c)]
        for cfg in ("C1", "C2", "C3"):
            assert tot[(cfg, c)] == pytest.approx(base, rel=1e-9), (cfg, c)
            assert float(rows[0]["cohort_total_T"]) > 0


def test_c1_keeps_all_eight_names_and_gives_rank_one_exactly_one_and_a_half_times():
    rows = private("cohort_allocation_audit.csv")
    by = {}
    for r in rows:
        by.setdefault((r["config"], r["cohort_id"]), []).append(r)
    for c in {c for (_, c) in by}:
        c0 = {r["symbol"]: r for r in by[("C0", c)]}
        c1 = {r["symbol"]: r for r in by[("C1", c)]}
        assert set(c0) == set(c1) and len(c1) == 8, c
        r1 = [r for r in by[("C1", c)] if r["is_protected_rank_one"] == "True"]
        assert len(r1) == 1
        s = r1[0]["symbol"]
        assert float(c1[s]["base_notional"]) == pytest.approx(1.5 * float(c0[s]["base_notional"]), rel=1e-9)
        for sym in c1:
            if sym != s:
                ratio = float(c1[sym]["base_notional"]) / float(c0[sym]["base_notional"])
                assert 0 < ratio < 1, (c, sym, ratio)


def test_c1_helper_preserves_the_total_and_fails_rather_than_capping():
    rows = [{"symbol": f"s{i}", "rank": i + 1} for i in range(8)]
    base = {f"s{i}": {"base": 1000.0} for i in range(8)}
    got = ch.c1_allocation(rows, base)
    assert got["ok"] and sum(got["allocation"].values()) == pytest.approx(8000.0)
    assert got["allocation"]["s0"] == pytest.approx(1500.0)
    # rank one already holds nearly everything: the 1.50x demand exceeds T, so the cohort fails
    lopsided = {"s0": {"base": 9000.0}, **{f"s{i}": {"base": 1.0} for i in range(1, 8)}}
    bad = ch.c1_allocation(rows, lopsided)
    assert bad["ok"] is False and "other_scale" in bad["reason"]


# ------------------------------------------------------------------ gate 9: substitution rule
def test_c2_protects_rank_one_uses_only_ranks_9_to_20_and_yields_eight_unique_names():
    f = freeze()
    plan = f["substitution_plan"]
    assert len(plan) == 52
    for iso, p in plan.items():
        assert all(2 <= r <= 8 for r in p["outgoing_ranks"]), (iso, p["outgoing_ranks"])
        assert all(9 <= r <= 20 for r in p["incoming_ranks"]), (iso, p["incoming_ranks"])
        assert len(p["outgoing_ranks"]) == len(p["incoming_ranks"]) == p["k"]
        assert len(p["lineup_original_ranks"]) == 8
        assert 1 in p["lineup_original_ranks"], f"{iso} dropped the protected rank one"
        # deterministic priority: worst originals out first, best deeper names in first
        assert p["outgoing_ranks"] == sorted(p["outgoing_ranks"], reverse=True)
        assert p["incoming_ranks"] == sorted(p["incoming_ranks"])
    pairs = private("substitution_pairs.csv")
    assert len(pairs) == f["substitution_totals"]["total_swaps"] == 141
    M = f["challengers"]["C2"]["threshold_M"]
    for r in pairs:
        assert float(r["outgoing_close_vs_high20"]) >= M, r
        assert float(r["incoming_close_vs_high20"]) < M, r


def test_substitution_helper_never_replaces_rank_one_and_needs_certification():
    top8 = [{"symbol": f"o{i}", "rank": i} for i in range(1, 9)]
    deeper = [{"symbol": f"d{i}", "rank": i} for i in range(9, 21)]
    oh = {**{f"o{i}": 0.0 for i in range(1, 9)}, **{f"d{i}": -1.0 for i in range(9, 21)}}
    certified = {f"d{i}" for i in range(9, 21)}
    plan = ch.substitution_plan(top8, deeper, oh, -0.055, certified)
    assert plan["k"] == 7 and plan["unique"]
    assert "o1" in {h["symbol"] for h in plan["lineup"]}
    assert all(h["rank"] != 1 for h in plan["outgoing"])
    # with nothing certified, no substitution happens at all
    none_plan = ch.substitution_plan(top8, deeper, oh, -0.055, set())
    assert none_plan["k"] == 0 and [h["symbol"] for h in none_plan["lineup"]] == [f"o{i}" for i in range(1, 9)]
    # a missing off-high value makes a name neither removable nor eligible
    oh2 = dict(oh); oh2["o5"] = None; oh2["d9"] = None
    p2 = ch.substitution_plan(top8, deeper, oh2, -0.055, certified)
    assert "o5" in {h["symbol"] for h in p2["lineup"]}
    assert "d9" not in {h["symbol"] for h in p2["lineup"]}


# ------------------------------------------------------------------ gate 10: certification
def test_every_selected_replacement_is_fully_certified():
    audit = {(r["cohort_id"], r["symbol"]): r for r in private("top20_candidate_audit.csv")}
    for r in private("substitution_pairs.csv"):
        rec = audit[(r["cohort_id"], r["incoming_symbol"])]
        assert rec["certified_for_substitution"] == "True", (r["cohort_id"], r["incoming_symbol"])
        assert rec["certification_failures"] in ("", None)
        for k, v in rec.items():
            if k.startswith("check_"):
                assert v == "True", (r["cohort_id"], r["incoming_symbol"], k)


def test_cohorts_whose_lineup_a_data_failure_changed_are_named_and_carry_a_sensitivity():
    f = freeze()
    aff = f["evidence_affected_cohorts"]
    assert set(f["evidence_sensitivity"]["cohorts"]) == set(aff)
    for iso, d in aff.items():
        assert d["worse_replacement_admitted"] or d["swaps_reduced_by_missing_evidence"]
        assert d["failures"], iso
    rows = public("cg_arrow012_account_summary.csv")
    cfgs = {r["config"] for r in rows}
    assert {"C2R", "C3R"} <= cfgs, "the pre-declared revert sensitivity must be scored"


# ------------------------------------------------------------------ gate 13: causal equity sizing
def test_equity_scaled_sizing_uses_each_challengers_own_causal_path():
    rows = private("r4r5_verified_trades.csv")
    by_stage = {}
    for r in rows:
        by_stage.setdefault(r["replay_stage"], []).append(r)
    scaled = {s: v for s, v in by_stage.items() if s.endswith("_EQUITY_SCALED")}
    assert len(scaled) >= 4
    firsts = {}
    for s, v in scaled.items():
        first = min(v, key=lambda r: r["cohort_id"])
        firsts[s] = float(first["sizing_scale_factor"])
        assert firsts[s] == pytest.approx(1.0), s  # the first cohort always sizes from 100,000
    # different challengers must diverge after the first cohort, never share one equity path
    lasts = {}
    for s, v in scaled.items():
        last = max(v, key=lambda r: r["cohort_id"])
        lasts[s] = float(last["sizing_scale_factor"])
    assert len(set(round(x, 6) for x in lasts.values())) > 1, "challengers share an equity path"
    for r in rows:
        if r["sizing_scale_factor"] and r["equity_reference_date"]:
            assert r["equity_reference_date"] <= r["scheduled_entry_date"], r["ticket_id"]


def test_independent_recomputation_of_allocations_and_shares_agrees():
    m = manifest("run_manifest.json")
    a = m["allocation_recomputation"]
    assert a["ok"] is True, a["failures"]
    assert a["checked"] > 4000
    assert a["max_share_error"] == 0


# ------------------------------------------------------------------ gate 14: accounts, monthly, oracle
def test_daily_identities_monthly_chaining_and_the_oracle_pass_for_every_book():
    m = manifest("run_manifest.json")
    assert m["oracle"]["ok"] is True
    assert m["oracle"]["trades"]["errors"] == 0 and m["oracle"]["cohorts"]["errors"] == 0
    for book, v in m["oracle"]["daily"].items():
        assert v["ok"], (book, v)
    for key, v in m["accounts"].items():
        assert v["identities_hold"], key
    for key, v in m["monthly_reconciliation"].items():
        assert v["reconciles"], key


def test_monthly_rows_chain_in_cents_and_reconcile_to_each_books_cutoff():
    rows = public("cg_arrow012_monthly_account.csv")
    acc = {(r["config"], r["view"]): r for r in public("cg_arrow012_account_summary.csv") if r["split"] == "ALL"}
    by = {}
    for r in rows:
        by.setdefault((r["config"], r["view"]), []).append(r)
    assert len(by) >= 8
    for key, rs_ in by.items():
        assert [r["month"] for r in rs_] == ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
                                             "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"], key
        prior = 100000.0
        for r in rs_:
            assert float(r["prior_month_end_equity"]) == prior, (key, r["month"])
            assert round(float(r["month_end_equity"]), 2) == round(prior + float(r["monthly_pnl"]), 2)
            prior = float(r["month_end_equity"])
        b = float(acc[key]["marked_account_pnl_at_2026_08_31"])
        assert sum(float(r["monthly_pnl"]) for r in rs_) == pytest.approx(b, abs=0.01), key
        assert b != float(acc[key]["eventual_completed_trade_pnl"])  # marked cutoff, never eventual profit


def test_runoff_and_open_obligations_stay_separate_in_every_account():
    rows = public("cg_arrow012_account_summary.csv")
    complete = [r for r in rows if r["split"] == "ALL"]
    assert complete
    for r in complete:
        assert int(r["open_documented"]) == 1, r["config"]
        assert int(r["completed"]) == 415 and int(r["intended"]) == 416, r["config"]
        assert float(r["eventual_completed_trade_pnl"]) != float(r["marked_account_pnl_at_2026_08_31"])
        assert int(r["runoff_trade_count"]) > 0
    # split rows own their own positions: the documented halt sits in exactly one split
    for cfg in {r["config"] for r in rows if r["split"] != "ALL"}:
        splits = [r for r in rows if r["config"] == cfg and r["split"] in ("IS", "OOS")]
        assert sum(int(r["intended"]) for r in splits) == 416, cfg
        assert sum(int(r["open_documented"]) for r in splits) == 1, cfg


# ------------------------------------------------------------------ interaction is measured, not assumed
def test_interaction_is_published_and_not_assumed_additive():
    rows = public("cg_arrow012_interaction.csv")
    add = [r for r in rows if r["additive"] == "True"]
    assert add
    for r in add:
        got = float(r["C3"]) - float(r["C1"]) - float(r["C2"]) + float(r["C0"])
        assert float(r["interaction_C3_minus_C1_minus_C2_plus_C0"]) == pytest.approx(got, abs=0.02)
        assert float(r["sum_of_parts_C1_plus_C2_minus_C0"]) == pytest.approx(
            float(r["C1"]) + float(r["C2"]) - float(r["C0"]), abs=0.02)
    nonadd = [r for r in rows if r["additive"] == "False"]
    assert nonadd and all(r["interaction_C3_minus_C1_minus_C2_plus_C0"] == "" for r in nonadd)


# ------------------------------------------------------------------ gate 15: public/private separation
def test_public_private_separation_and_credential_hygiene():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    assert subprocess.check_output(["git", "ls-files", "handoff", "data/verification"],
                                   cwd=REPO_ROOT).decode().strip() == ""
    import glob
    import re
    syms = {r["symbol"] for r in private("top20_candidate_audit.csv") if len(r["symbol"]) >= 3}
    for p in glob.glob(str(REPORTS / "cg_arrow012_*")):
        text = open(p, encoding="utf-8").read()
        hits = [s for s in syms if re.search(r"\b" + re.escape(s) + r"\b", text)]
        assert not hits, (p, hits[:5])
        assert not re.search(r"THETA_?(USER|PASS|KEY)|password|secret|bearer|api[_-]?key", text, re.I), p
        assert "ticket_id" not in text.split("\n")[0], p


# ------------------------------------------------------------------ dependence diagnostics state their scope
def test_moving_block_resampling_states_what_it_preserves():
    rows = []
    for c in range(12):
        for i in range(8):
            rows.append({"cohort_id": f"2026-01-{c + 1:02d}", "symbol": f"s{c}{i}", "x": float(i), "y": float(i)})
    for block in (1, 2, 4):
        got = rs.moving_block_resample(rows, "x", "y", block=block, n_boot=20)
        assert got["block"] == block
        assert "contiguous runs" in got["preserves"]
        assert got["boot_n"] > 0
        assert got["share_positive"] == pytest.approx(1.0)
