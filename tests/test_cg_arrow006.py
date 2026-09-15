"""Arrow 006 regression tests: acquisition repair wiring, corrected universe, gate discipline."""
from datetime import date
import json
import re
import subprocess
import sys

import polars as pl
import pytest

from ingest.paths import REPO_ROOT
from verification import r4r5_data as data
from verification import r4r5_export as exp
from verification import r4r5_oracle as oracle
from verification import r4r5_rank as rank
from verification import r4r5_repair as rep
from verification import r4r5_replay as rp

from test_cg_arrow005 import cohort, market, obs  # shared synthetic fixtures

sys.path.insert(0, str(REPO_ROOT / "scripts"))

WORK = data.VERIFY_ROOT / "work"


# ------------------------------------------------------------------ secrets and exclusions
def test_env_is_ignored_and_never_tracked():
    assert subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    tracked = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT).decode().splitlines()
    assert not any(t == ".env" or t.endswith("/.env") for t in tracked)


def test_private_and_raw_paths_excluded_from_git():
    for rel in ("data/verification/r4r5/v1/acquisition/raw/AAPL/2026-03-01_2026-03-31.parquet",
                "data/verification/r4r5/v1/validated/2026-03-04/AAPL.parquet",
                "handoff/outgoing/cg_arrow006/r4r5_verified_trades.csv",
                "data/verification/r4r5/v1/acquisition/requests.jsonl"):
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=REPO_ROOT).returncode == 0, rel
    assert subprocess.check_output(["git", "ls-files", "handoff", "data/verification"],
                                   cwd=REPO_ROOT).decode().strip() == ""


def test_public_artifacts_carry_no_credential_material():
    # a real value, never a documented placeholder such as THETADATA_API_KEY=<key>
    secret = re.compile(r"(THETADATA_API_KEY|ASKEDGAR_API_KEY)\s*=\s*(?!<)[A-Za-z0-9_\-]{8,}"
                        r"|api[_-]?key['\"]?\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")
    for p in sorted((REPO_ROOT / "reports").glob("cg_arrow006*")) + \
             sorted((REPO_ROOT / "src" / "verification").glob("*.py")) + \
             sorted((REPO_ROOT / "scripts").glob("cg_arrow006*.py")):
        assert not secret.search(p.read_text(encoding="utf-8")), p


def test_pilot_and_request_log_hold_no_secret_values():
    log = data.VERIFY_ROOT / "acquisition" / "requests.jsonl"
    if not log.exists():
        pytest.skip("no acquisition log in this checkout")
    keys = {k for k in ("THETADATA_API_KEY", "ASKEDGAR_API_KEY")}
    head = log.read_text(encoding="utf-8").splitlines()[:200]
    for line in head:
        row = json.loads(line)
        assert not (set(row) & keys)
        assert set(row) <= {"timestamp", "symbol", "start", "end", "endpoint", "interval", "venue", "window",
                            "adjustment", "ok", "rows", "elapsed_s", "raw_path", "raw_bytes", "sessions",
                            "session_status", "error"}


# ------------------------------------------------------------------ acquisition pipeline
def test_end_to_end_repair_proof_recorded():
    p = data.VERIFY_ROOT / "proof_end_to_end.json"
    if not p.exists():
        pytest.skip("proof stage not run in this checkout")
    proof = data.read_json(p)
    assert proof["pipeline_ok"] is True
    assert proof["before"]["entry_px"] is None and proof["after"]["entry_px"] is not None
    assert proof["after"]["source"] == "validated"


def test_validated_layer_takes_precedence_over_original_tree(tmp_path, monkeypatch):
    early, late, sym = date(2026, 3, 4), date(2026, 7, 1), "AAPL"
    assert [lbl for lbl, _ in data.candidate_paths(early, sym)][0] == "validated"
    assert [lbl for lbl, _ in data.candidate_paths(late, sym)][0] == "validated"
    # the repaired-tree precedence, and the virgin/full flip at the end of the virgin window
    assert [lbl for lbl, _ in data.candidate_paths(early, sym) if lbl in ("virgin", "full")]         == ["virgin", "full"]
    assert [lbl for lbl, _ in data.candidate_paths(late, sym) if lbl in ("virgin", "full")]         == ["full", "virgin"]
    first = data.candidate_paths(early, sym)[0][1]
    assert first.as_posix().endswith(f"validated/{early.isoformat()}/{sym}.parquet")


def test_holdout_tree_is_in_the_resolution_order_and_cannot_shadow_the_study():
    """Arrow 013's immutable holdout landing is a source, and its position is provably inert.

    The summary loader runs in worker processes that import the data module fresh, so the
    holdout tree has to be part of `candidate_paths` itself rather than patched in by a caller.
    That makes its ordering a real question, and the answer is that it cannot matter: the two
    landings are disjoint by session date, so no session can resolve differently because of it.
    """
    labels = [lbl for lbl, _ in data.candidate_paths(date(2026, 3, 4), "AAPL")]
    assert "holdout_raw" in labels
    holdout = {p.name for p in data.HOLDOUT_BARS.iterdir()} if data.HOLDOUT_BARS.exists() else set()
    for tree in ("virgin", "full"):
        root = data.DATA / tree / "bars"
        study = {p.name for p in root.iterdir()} if root.exists() else set()
        assert not (holdout & study), sorted(holdout & study)[:5]


def test_month_chunking_respects_vendor_one_month_limit():
    days = {d for d in data.FEATS if date(2026, 5, 1) <= d <= date(2026, 8, 31)}
    chunks = rep.month_chunks(days)
    assert len(chunks) == 4
    for start, end in chunks:
        assert start.month == end.month and start.year == end.year


def test_empty_response_is_never_coverage():
    empty = pl.DataFrame(schema={"bar_start": pl.Datetime("us", "America/New_York"), "open": pl.Float64,
                                 "high": pl.Float64, "low": pl.Float64, "close": pl.Float64, "volume": pl.Int64})
    v = rep.validate_session(empty, date(2026, 3, 4), "X")
    assert v["status"] == "EMPTY_RESPONSE_UNRESOLVED" and v["traded_bars"] == 0


def test_validation_accepts_thin_trading_and_flags_defects():
    def frame(rows):
        return pl.DataFrame(rows).with_columns(pl.col("bar_start").dt.replace_time_zone("America/New_York"))
    import datetime as dt
    thin = frame([{"bar_start": dt.datetime(2026, 3, 4, 10, 0), "open": 5.0, "high": 5.1, "low": 4.9,
                   "close": 5.0, "volume": 100}])
    assert rep.validate_session(thin, date(2026, 3, 4), "THIN")["status"] == "RETRIEVED_CHECKED"
    bad = frame([{"bar_start": dt.datetime(2026, 3, 4, 10, 0), "open": 5.0, "high": 4.0, "low": 4.9,
                  "close": 9.0, "volume": 100}])
    assert rep.validate_session(bad, date(2026, 3, 4), "BAD")["status"] == "RETRIEVED_WITH_ISSUES"
    quiet = frame([{"bar_start": dt.datetime(2026, 3, 4, 10, 0), "open": 5.0, "high": 5.0, "low": 5.0,
                    "close": 5.0, "volume": 0}])
    assert rep.validate_session(quiet, date(2026, 3, 4), "QUIET")["status"] == "DOCUMENTED_NO_TRADING"


def test_acquisition_requests_ignore_entry_price_bands():
    """A held position must be retrieved even when its later price leaves the entry band."""
    sessions = {d for d in data.FEATS if date(2026, 6, 1) <= d <= date(2026, 6, 30)}
    plan = rep.plan_requests({"ABOVE80": sessions, "BELOW10": sessions})
    assert {r["symbol"] for r in plan} == {"ABOVE80", "BELOW10"}
    assert all(len(r["sessions"]) == len(sessions) for r in plan)


# ------------------------------------------------------------------ corrected universe
def test_documented_test_issues_excluded_from_corrected_universe():
    from cg_arrow006_acquire import tradable_universe
    roster, etp, tests = tradable_universe()
    assert "ZVZZT" in roster and "ZVZZT" in tests
    assert all(re.match(r"^Z[A-Z]ZZT$", t) for t in tests)
    cf = WORK / "cohort_field.json"
    if not cf.exists():
        pytest.skip("field stage not run in this checkout")
    field = data.read_json(cf)
    for iso, v in field.items():
        assert not (set(v["rule_field"]) & set(tests)), iso
    # the historical cache did select a test issue; R1 keeps it for forensic comparison
    assert any("ZVZZT" in v["cached_not_eligible"] for v in field.values())


def test_june_august_field_restored_to_the_ten_to_eighty_rule():
    cf = WORK / "cohort_field.json"
    if not cf.exists():
        pytest.skip("field stage not run in this checkout")
    field = data.read_json(cf)
    jun = {k: v for k, v in field.items() if k >= "2026-06-01"}
    assert len(jun) == 13
    meta = pl.read_parquet(REPO_ROOT / "data/full/eligibility.parquet")
    for iso, v in jun.items():
        day = meta.filter((pl.col("session_date") == date.fromisoformat(iso))
                          & pl.col("symbol").is_in(v["rule_field"]))
        assert day["prior_close"].max() > 50.0, iso      # the $50 truncation is gone
        assert day["prior_close"].max() <= 80.0, iso     # and the rule ceiling is respected
        assert day["prior_close"].min() >= 10.0, iso
        assert day["prior_dollar_volume"].min() >= 1e7, iso
        assert len(v["missing"]) > 0, iso                # candidates were genuinely restored


def test_ranking_is_deterministic_and_uses_documented_units():
    signal = date(2026, 1, 7)
    back = data.FEATS[data.INDEX[signal] - 15]
    sums = {}
    for s, then, now in (("A", 10.0, 12.0), ("B", 10.0, 11.0), ("C", 10.0, 13.0)):
        sums[(back.isoformat(), s)] = obs(back, then)
        sums[(signal.isoformat(), s)] = obs(signal, now)
    cands = {s: {"prior_close": 20.0, "prior_dollar_volume": 2e7} for s in ("A", "B", "C", "D")}
    out = rank.rank_cohort(signal, cands, sums)
    assert [r["symbol"] for r in out["rows"]] == ["C", "A", "B"]
    assert [r["rank"] for r in out["rows"]] == [1, 2, 3]
    assert [u["symbol"] for u in out["unrankable"]] == ["D"]
    u = out["unrankable"][0]
    assert u["endpoint"] == "signal" and u["vendor_status"] == "NOT_REQUESTED"
    assert u["classification"] == "UNRESOLVED_OBSERVATION"
    assert out["ranking_scope"] == "RULE_FIELD_WITH_UNRESOLVED"
    # a genuine no-trading response is a rule-faithful exclusion, not an unresolved gap
    out2 = rank.rank_cohort(signal, cands, sums,
                            {("D", signal.isoformat()): "DOCUMENTED_NO_TRADING"})
    assert out2["unrankable"][0]["classification"] == "RULE_FAITHFUL_NO_TRADING"
    assert out2["ranking_scope"] == "CERTIFIED_RULE_FIELD_10_80"


def test_ranking_applies_documented_split_factor(monkeypatch):
    signal = date(2026, 1, 7)
    back = data.FEATS[data.INDEX[signal] - 15]
    ev = ({"symbol": "S", "effective_session": data.FEATS[data.INDEX[signal] - 5].isoformat(),
           "price_factor": 5},)
    monkeypatch.setattr(data, "action_events", lambda: ev)
    sums = {(back.isoformat(), "S"): obs(back, 2.0), (signal.isoformat(), "S"): obs(signal, 11.0)}
    out = rank.rank_cohort(signal, {"S": {"prior_close": 11.0, "prior_dollar_volume": 2e7}}, sums)
    # 2.00 pre-split is 10.00 in signal units, so the true return is +10%, not +450%
    assert out["rows"][0]["raw_return"] == pytest.approx(0.10)
    assert out["rows"][0]["documented_rank_factor"] == 5


# ------------------------------------------------------------------ baseline and horizon discipline
def test_no_stale_mark_is_ever_certified_as_an_exit():
    c = cohort()
    s = market()
    due = data.FEATS[data.INDEX[c[0]["fill"]] + 10]
    s[(due.isoformat(), "S0")] = None
    t = rp.replay("PARENT", c, s)["trades"][0]
    assert t["status"].startswith("UNRESOLVED") and t["modeled_net"] is None
    assert t["stale_liability_last_mark"] is not None
    assert t["verification_status"] == "UNRESOLVED"


def test_same_entries_and_shares_at_every_horizon():
    c = cohort()
    s = market(prices={d: 20.0 - i * 0.05 for i, d in enumerate(data.FEATS)})
    books = {h: rp.replay("R5", c, s, hold=h) for h in range(1, 11)}
    base = {t["ticket_id"]: (t["entry_price"], t["quantity"], t["entry_commission"], t["entry_spread"])
            for t in books[10]["trades"]}
    for h, b in books.items():
        for t in b["trades"]:
            assert (t["entry_price"], t["quantity"], t["entry_commission"], t["entry_spread"]) == base[t["ticket_id"]]
            assert t["scheduled_exit_date"] == data.FEATS[data.INDEX[c[0]["fill"]] + h].isoformat()


def test_h10_cell_reproduces_the_locked_baseline():
    m = REPO_ROOT / "reports" / "cg_arrow006_manifest.json"
    f = REPO_ROOT / "reports" / "cg_arrow006_horizon_freeze.json"
    if not (m.exists() and f.exists()):
        pytest.skip("baseline or horizon artefacts absent")
    fr = data.read_json(f)
    if fr.get("status") != "OOS_REVEALED":
        pytest.skip("horizon census not revealed")
    for fam, v in fr["h10_baseline_identity"].items():
        assert abs(v["difference"]) < 1e-6, fam


def test_horizon_oos_requires_a_committed_freeze():
    f = REPO_ROOT / "reports" / "cg_arrow006_horizon_freeze.json"
    if not f.exists():
        pytest.skip("no freeze")
    fr = data.read_json(f)
    assert fr["status"] in {"FROZEN_PRE_OOS", "OOS_REVEALED", "NOT_RUN_DATA_GATE", "NOT_RUN_TIME_GATE"}
    if fr["status"] == "OOS_REVEALED":
        assert fr["r2_entry_ledger_sha256"]
        assert fr["oos_procedure"].startswith("one batch")
        # the freeze must have existed in git before the reveal
        assert subprocess.run(["git", "cat-file", "-e", "HEAD:reports/cg_arrow006_horizon_freeze.json"],
                              cwd=REPO_ROOT).returncode == 0


def test_cohort_subtotal_conservation_and_open_closed_counts(tmp_path):
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
    assert int(period["unresolved"]) == 1 and period["verified_total_is_complete"] == "False"
    assert int(period["closed_verified"]) == 7


def test_manifest_reports_gate_and_unresolved_counts():
    m = REPO_ROOT / "reports" / "cg_arrow006_manifest.json"
    if not m.exists():
        pytest.skip("baseline not run")
    man = data.read_json(m)
    assert man["gate"]["status"] in {"OPEN", "NOT_RUN_DATA_GATE"}
    for fam in ("PARENT", "R4", "R5"):
        sc = man["summary"][f"{fam}/R2"]["status_counts"]
        unresolved = sum(v for k, v in sc.items() if k.startswith(("UNRESOLVED", "MISSED_ENTRY")))
        if man["gate"]["status"] == "OPEN":
            assert unresolved == 0, (fam, sc)
    assert man["universe_rule"]["prior_close"] == [10.0, 80.0]
    assert "ZVZZT" in man["universe_rule"]["test_issues_excluded"]
