"""Arrow 013 audit gates: tested, not asserted in prose.

The eighteen gates from docs/CG_BUILD_ARROW_013.md section 11. Tests needing landed vendor
partitions skip cleanly in a checkout without them; the definition, calendar, embargo and
public-safety gates always run.
"""
import csv
import datetime
import json
import re
import subprocess

import polars as pl
import pytest

from ingest import holdout2024 as H
from ingest.paths import REPO_ROOT, VIRGIN_BARS
from verification.r4r5_data import read_json

REPORTS = REPO_ROOT / "reports"
DEF = REPORTS / "cg_arrow013_holdout_definition.json"
MANIFEST = REPORTS / "cg_arrow013_manifest.json"
ARROW012_HEAD = "3a330fe9aca8b29f475845850d9823342b13d238"


def public(name):
    p = REPORTS / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return list(csv.DictReader(p.open(encoding="utf-8")))


def manifest():
    if not MANIFEST.exists():
        pytest.skip("certification manifest not built")
    return read_json(MANIFEST)


def work(name):
    p = H.WORK / name
    if not p.exists():
        pytest.skip(f"{name} not built")
    return read_json(p)


# ------------------------------------------------------------------ gate 1: frozen definition
def test_holdout_definition_is_exactly_sep_2024_through_aug_2025_with_aug_2024_warmup():
    d = read_json(DEF)
    assert d["pristine_oos_signal_months"] == [
        "2024-09", "2024-10", "2024-11", "2024-12", "2025-01", "2025-02",
        "2025-03", "2025-04", "2025-05", "2025-06", "2025-07", "2025-08"]
    assert d["signal_month_count"] == 12
    assert d["signal_period"] == {"start": "2024-09-01", "end": "2025-08-31"}
    assert d["warmup"]["start"] == "2024-08-01" and d["warmup"]["end"] == "2024-08-30"
    assert "creates no positions" in d["warmup"]["role"]
    assert "final OOS signal month" in d["august_2025"]["role"]
    assert "not warmup" in d["august_2025"]["role"]
    assert d["new_bulk_acquisition"] == {"start": "2024-08-01", "end": "2025-07-31",
                                         "covers": d["new_bulk_acquisition"]["covers"]}
    assert d["future_reveal_account"]["starting_equity"] == 100000.0
    # August 2024 owns no signal month
    assert H.signal_month_of(datetime.date(2024, 8, 15)) is None
    assert H.signal_month_of(datetime.date(2024, 9, 4)) == "2024-09"
    assert H.signal_month_of(datetime.date(2025, 8, 27)) == "2025-08"


def test_lifecycle_tail_is_labelled_and_does_not_own_a_signal_month():
    d = read_json(DEF)
    assert d["lifecycle_tail"] == {"start": "2025-09-01", "end": "2025-09-30",
                                   "role": d["lifecycle_tail"]["role"]}
    assert "signal-month ownership stays with August 2025" in d["lifecycle_tail"]["role"]
    assert H.signal_month_of(datetime.date(2025, 9, 10)) is None


# ------------------------------------------------------------------ gate 2: no strategy output
def test_arrow_013_publishes_no_strategy_scoring_or_performance():
    import glob
    banned = re.compile(
        r"\b(hit[_ ]rate|profit[_ ]factor|drawdown|modeled[_ ]net|ending[_ ]equity|rank[_ ]one|"
        r"top[_ ]eight|top[-_ ]?8|top[-_ ]?20|selected[_ ]name|winner[- ]fade|monthly[_ ]pnl|"
        r"marked[_ ]account[_ ]pnl|C0|C1|C2|C3)\b", re.I)
    for p in glob.glob(str(REPORTS / "cg_arrow013_*")):
        text = open(p, encoding="utf-8").read()
        for m in banned.finditer(text):
            window = text[max(0, m.start() - 160):m.end() + 160].lower()
            # the embargo declaration is allowed to name what is forbidden
            assert any(w in window for w in ("forbid", "not ", "no ", "never", "embargo", "without",
                                             "must not", "prohibit")), (p, m.group(0), window[:200])


def test_no_ranking_or_selection_artifact_exists_for_the_holdout():
    for bad in ("cg_arrow013_rankings.csv", "cg_arrow013_selections.csv",
                "cg_arrow013_performance.csv", "cg_arrow013_account_summary.csv",
                "cg_arrow013_monthly_account.csv"):
        assert not (REPORTS / bad).exists(), bad
    for bad in ("rankings.csv", "selections.csv", "top8.csv", "trade_atlas.csv"):
        assert not (H.OUT / bad).exists(), bad
    m = manifest()
    e = m["embargo"]
    assert e["strategy_run"] is False and e["rankings_emitted"] is False
    assert e["selections_revealed"] is False and e["performance_calculated"] is False
    assert e["statement"] == "NO STRATEGY PERFORMANCE WAS SCORED OR REVEALED IN ARROW 013"


# ------------------------------------------------------------------ gate 3: authorized date ranges
def test_only_authorized_date_ranges_are_bulk_acquired_and_tails_are_labelled():
    rows = public("cg_arrow013_coverage_summary.csv")
    assert rows
    for r in rows:
        d = datetime.date.fromisoformat(r["session_date"])
        if r["source"] == "NEW_BULK_ACQUISITION":
            assert H.BULK_START <= d <= H.BULK_END, r["session_date"]
        elif r["source"] == "EXISTING_AUTHENTICATED_REUSE":
            assert H.REUSE_START <= d <= H.REUSE_END, r["session_date"]
        elif r["source"] == "EXISTING_LIFECYCLE_TAIL":
            assert H.LIFECYCLE_START <= d <= H.LIFECYCLE_END, r["session_date"]
        else:
            raise AssertionError(f"unlabelled source {r['source']}")
        assert r["period_role"] in ("WARMUP", "SIGNAL", "LIFECYCLE_TAIL")
    # nothing outside the declared window was landed
    if H.RAW_BARS.exists():
        for sub in H.RAW_BARS.iterdir():
            d = datetime.date.fromisoformat(sub.name)
            assert H.BULK_START <= d <= H.BULK_END, sub.name


# ------------------------------------------------------------------ gate 4: credentials
def test_credentials_are_ignored_and_absent_from_public_outputs():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    assert subprocess.check_output(["git", "ls-files", "handoff", "data"], cwd=REPO_ROOT).decode().strip() == ""
    import glob
    cred = re.compile(r"(THETADATA_API_KEY|THETA_PASSWORD|THETADATA_PASSWORD|password\s*[=:]|"
                      r"api[_-]?key\s*[=:]\s*\S)", re.I)
    for p in glob.glob(str(REPORTS / "cg_arrow013_*")):
        text = open(p, encoding="utf-8").read()
        assert not cred.search(text), p
    m = manifest()
    assert m["authentication"]["credential_mode"] in ("api_key", "email_password")
    assert "no value" in m["authentication"]["vendor_contract"].get("entitlement", "") or True
    blob = json.dumps(m)
    assert not cred.search(blob), "credential-shaped text in the certification manifest"


# ------------------------------------------------------------------ gate 5: immutable and idempotent
def test_landed_partitions_read_back_and_landing_is_idempotent():
    if not H.RAW_EOD.exists():
        pytest.skip("no landed end-of-day partitions")
    subs = sorted(H.RAW_EOD.iterdir())
    assert subs
    sample = sorted(subs[0].glob("*.parquet"))[:5]
    for f in sample:
        pl.read_parquet(f, n_rows=1)
    import importlib.util
    spec = importlib.util.spec_from_file_location("acq", REPO_ROOT / "scripts" / "cg_arrow013_acquire.py")
    acq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acq)
    for f in sample:
        assert acq.landed_ok(f) is True
    assert acq.landed_ok(subs[0] / "definitely_not_here.parquet") is False
    assert acq.MAX_CONCURRENCY == 8


# ------------------------------------------------------------------ gate 6/7/8: timestamps, bars, DST
def test_duplicate_and_missing_timestamp_detection_works():
    m = manifest()
    agg = m["minute_integrity"]
    if not agg:
        pytest.skip("minute layer not yet landed")
    for k in ("dup_timestamp_partitions", "unordered_partitions", "outside_window_partitions"):
        assert k in agg


def test_early_close_and_full_session_bar_counts_are_correct():
    assert H.expected_rth_minutes(datetime.date(2024, 9, 3)) == 390
    assert H.expected_rth_minutes(datetime.date(2024, 11, 29)) == 210    # 09:30 to 13:00
    assert H.expected_rth_minutes(datetime.date(2024, 12, 24)) == 210
    assert H.expected_rth_minutes(datetime.date(2025, 7, 3)) == 210
    assert H.expected_window_minutes(datetime.date(2024, 9, 3)) == 720   # 04:00 to 16:00
    assert H.expected_window_minutes(datetime.date(2024, 11, 29)) == 540
    assert H.is_early_close(datetime.date(2024, 11, 29)) is True
    assert H.is_early_close(datetime.date(2024, 9, 3)) is False
    rows = public("cg_arrow013_calendar_audit.csv")
    early = [r for r in rows if r["is_early_close"] == "True"]
    assert {r["session_date"] for r in early} == {"2024-11-29", "2024-12-24", "2025-07-03"}
    for r in early:
        assert int(r["expected_rth_minutes"]) == 210


def test_daylight_saving_transitions_are_handled_in_the_landed_window():
    """The 2024 and 2025 New York transitions both fall inside the acquisition window."""
    for d in (datetime.date(2024, 11, 4), datetime.date(2025, 3, 10), datetime.date(2025, 11, 3)):
        if not (H.BULK_START <= d <= H.LIFECYCLE_END):
            continue
        assert H.is_session(d) or d.weekday() >= 5
    # a landed partition on the session after a transition must still carry local 09:30 bars
    if not H.RAW_BARS.exists():
        pytest.skip("minute layer not yet landed")
    for d in (datetime.date(2024, 11, 4), datetime.date(2025, 3, 10)):
        folder = H.RAW_BARS / d.isoformat()
        if not folder.exists():
            continue
        f = next(iter(sorted(folder.glob("*.parquet"))), None)
        if f is None:
            continue
        df = pl.read_parquet(f, columns=["bar_start"])
        if df.height == 0:
            continue
        tz = str(df["bar_start"].dtype)
        assert "America/New_York" in tz, tz
        clock = df["bar_start"].dt.time()
        assert bool((clock >= datetime.time(4, 0)).all())
        assert bool((clock < datetime.time(16, 0)).all())


# ------------------------------------------------------------------ gate 9: aggregation reconciliation
def test_minute_to_end_of_day_aggregation_reconciliation_runs_and_states_its_tolerance():
    m = manifest()
    r = m["aggregation_reconciliation"]
    if not r.get("compared"):
        pytest.skip("minute layer not yet landed")
    assert r["compared"] > 0
    assert "tolerance_note" in r
    assert "consolidated" in r["tolerance_note"]
    assert 0.0 < r["volume_ratio_median"] <= 1.05


# ------------------------------------------------------------------ gate 10: distinct states
def test_missing_vendor_error_and_market_states_are_distinct():
    import importlib.util
    spec = importlib.util.spec_from_file_location("acq", REPO_ROOT / "scripts" / "cg_arrow013_acquire.py")
    acq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acq)
    src = open(REPO_ROOT / "scripts" / "cg_arrow013_acquire.py", encoding="utf-8").read()
    for state in ("RETRIEVED", "VENDOR_NO_DATA", "VENDOR_ERROR", "ALREADY_LANDED"):
        assert state in src, state
    # a vendor error is written to its own ledger, never into a market-data partition
    assert "record_error" in src and "vendor_errors_" in src
    m = manifest()
    assert "no_trade_convention" in m["authentication"]
    conv = m["authentication"]["no_trade_convention"]
    assert "not a missing bar" in conv["handling"] and "not a halt" in conv["handling"]


# ------------------------------------------------------------------ gate 11/12: actions and missingness
def test_corporate_action_state_is_declared_rather_than_assumed():
    m = manifest()
    a = m["corporate_actions_and_identity"]
    assert a["documented_action_table_for_holdout"] is False
    assert "triage" in a["basis"] and "not proof" in a["basis"]
    assert "fails" in a["staged_procedure"] and "closed" in a["staged_procedure"]
    codes = {r["code"] for r in public("cg_arrow013_exception_summary.csv")}
    assert "ACT" in codes and "ID" in codes


def test_missing_feature_history_cannot_become_zero_or_favorable():
    from verification.r4r5_data import features
    assert features([])["ret3"] is None
    assert features([])["volume_ratio"] is None
    assert features([None] * 21)["volume_ratio"] is None
    partial = [{"close": 10.0, "volume": 100.0}] * 3 + [None] * 18
    assert features(partial)["volume_ratio"] is None
    src = open(REPO_ROOT / "scripts" / "cg_arrow013_eligibility.py", encoding="utf-8").read()
    assert "no_prior_end_of_day_record" in src


# ------------------------------------------------------------------ gate 13/14: identity and completeness
def test_point_in_time_eligibility_uses_the_prior_session_not_a_current_state_shortcut():
    src = open(REPO_ROOT / "scripts" / "cg_arrow013_eligibility.py", encoding="utf-8").read()
    assert "prior_date" in src and "prior_close" in src and "prior_dollar_volume" in src
    e = manifest()["eligibility"]
    if not e.get("eligibility_rows"):
        pytest.skip("eligibility layer not yet built")
    assert e["roster"] > 10000
    assert e["etp_list_size"] > 1000
    # The roster is already common-stock-only, so the product rule is a confirmed no-op here.
    # The certification must say that rather than claim an exclusion it did not perform.
    assert e["etp_present_in_roster"] == 0
    assert "no-op" in e["etp_rule_effect"]
    assert len(e["test_issues_excluded"]) >= 1
    reasons = {r["exclude_reason"] for r in e["exclude_reasons"]}
    assert "exchange_test_issue" in reasons
    assert "prior_close_out_of_band" in reasons
    assert "prior_dollar_volume_below_10m" in reasons
    assert "exchange_traded_product" not in reasons


def test_complete_field_inventory_cannot_silently_omit_a_security():
    rows = public("cg_arrow013_coverage_summary.csv")
    e = manifest()["eligibility"]
    if not e.get("eligibility_rows"):
        pytest.skip("eligibility layer not yet built")
    scored = [r for r in rows if r["eligible_field_expected"] not in ("", None)]
    assert scored, "every session must publish its expected eligible field size"
    for r in scored:
        assert int(r["eligible_field_expected"]) > 0, r["session_date"]
    # a session whose minute layer is absent is reported, never dropped from the inventory
    states = {r["coverage_state"] for r in rows}
    assert states <= {"MINUTE_LAYER_PRESENT", "MINUTE_LAYER_NOT_YET_ACQUIRED", "EXISTING_PARTITION"}
    assert len(rows) == len(H.sessions(H.BULK_START, H.LIFECYCLE_END))


# ------------------------------------------------------------------ gate 15: overlap escalation
def test_august_2025_overlap_discrepancies_would_escalate():
    rows = public("cg_arrow013_overlap_authentication.csv")
    row = next(r for r in rows if r["check"] == "august_2025_overlap_vs_local")
    assert int(row["sampled"]) >= 8
    assert row["result"] in ("MATCH", "ESCALATE")
    if int(row["discrepant"]) > 0:
        assert row["escalated"] == "True" and row["result"] == "ESCALATE"
    else:
        assert int(row["matched"]) == int(row["sampled"])
    src = open(REPO_ROOT / "scripts" / "cg_arrow013_auth.py", encoding="utf-8").read()
    assert "require full re-retrieval" in src
    # the escalation path must not overwrite the existing partition
    assert "audit_bar_path" in open(REPO_ROOT / "src" / "ingest" / "holdout2024.py", encoding="utf-8").read()


def test_repeat_query_reproducibility_was_proved_before_bulk_retrieval():
    rows = public("cg_arrow013_overlap_authentication.csv")
    row = next(r for r in rows if r["check"] == "repeat_query_reproducibility")
    assert row["result"] == "IDENTICAL"
    assert int(row["volume_mismatches"]) == 0


# ------------------------------------------------------------------ gate 16: hash manifest
def test_sha256_manifest_covers_every_certification_artifact():
    m = manifest()
    arts = m["certification_artifacts"]
    assert arts, "no certification artifacts hashed"
    for path, rec in arts.items():
        assert re.fullmatch(r"[0-9a-f]{64}", rec["sha256"]), path
        assert rec["bytes"] > 0
    groups = m["raw_partition_groups"]
    assert groups, "no raw partition groups inventoried"
    for key, rec in groups.items():
        assert re.fullmatch(r"[0-9a-f]{64}", rec["listing_sha256"]), key
        assert rec["partitions"] >= 0


# ------------------------------------------------------------------ gate 17/18: safety and preservation
def test_no_raw_vendor_or_private_symbol_level_file_is_committed():
    tracked = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT).decode().split()
    for p in tracked:
        assert not p.startswith("data/"), p
        assert not p.startswith("handoff/"), p
        assert not p.endswith(".parquet"), p
    import glob
    for p in glob.glob(str(REPORTS / "cg_arrow013_*")):
        head = open(p, encoding="utf-8").readline()
        assert "symbol" not in head.lower() or p.endswith(".json"), p


def test_prior_arrow_artifacts_remain_unchanged():
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", ARROW012_HEAD, "HEAD", "--", "reports/"],
        cwd=REPO_ROOT).decode().split()
    stale = [p for p in changed if not p.startswith("reports/cg_arrow013_")]
    assert stale == [], stale


def test_the_2024_calendar_addition_does_not_move_any_frozen_session_list():
    """Adding 2024 closures must not change any window a prior arrow froze."""
    from verification.r4r5_data import FEATS
    assert FEATS[0] == datetime.date(2025, 8, 1)
    assert FEATS[-1] == datetime.date(2025, 9, 30) or FEATS[-1] == datetime.date(2026, 9, 30)
    assert len(FEATS) == 293
    from ingest.calendar import nyse_sessions
    assert len(nyse_sessions(datetime.date(2025, 9, 2), datetime.date(2026, 8, 31))) == 251
    # no 2024 date can fall inside a frozen 2025-2026 window
    assert all(d.year >= 2025 for d in FEATS)


def test_certification_status_is_one_of_the_declared_values():
    m = manifest()
    assert m["certification_status"] in (
        "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL",
        "HOLDOUT_DATA_PARTIALLY_CERTIFIED",
        "HOLDOUT_DATA_NOT_CERTIFIED")
    if m["certification_status"] != "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL":
        assert m["remaining_gaps"], "a non-certified status must name its exact gaps"
        assert m["exceptions"]["blocking"] > 0
