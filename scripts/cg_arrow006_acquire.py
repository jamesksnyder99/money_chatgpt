"""CG Arrow 006 acquisition driver: end-to-end repair proof, lifecycle and field restoration.

Stages (resumable, each skippable):
  proof      end-to-end raw->validated->cache->replay proof on a known unresolved case
  lifecycle  every observation the PARENT/R4/R5 selected-trade ledgers require
  field      the corrected $10-$80 point-in-time candidate field for every cohort
  selected   lifecycle for names newly selected by the corrected R2 ranking

Usage: python scripts/cg_arrow006_acquire.py <stage> [--workers 8]
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest.paths import ETP_TICKERS, REPO_ROOT  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    CACHE, FEATS, INDEX, VERIFY_ROOT, dump_json, load_summaries, present, read_json, stamp,
)
from verification.r4r5_replay import cohorts, load_field  # noqa: E402

WORK = VERIFY_ROOT / "work"
NASDAQ_TEST = re.compile(r"^Z[A-Z]ZZT$")
VIRGIN_END = date(2026, 5, 29)
FEATURE_LOOKBACK = 20
HOLD = 10


def note(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


# ------------------------------------------------------------------ universe rule
def test_issues(roster: set[str]) -> list[str]:
    """Documented Nasdaq/UTP test issues (ZXZZT family). Not tradable securities."""
    return sorted(s for s in roster if NASDAQ_TEST.match(s))


def tradable_universe() -> tuple[set[str], set[str], list[str]]:
    roster = set(pl.read_parquet(REPO_ROOT / "data/ref/symbols_common.parquet")["symbol"].to_list())
    etp = {x.strip().upper() for x in ETP_TICKERS.read_text(encoding="utf-8").splitlines()
           if x.strip() and not x.startswith("#")} if ETP_TICKERS.exists() else set()
    tests = test_issues(roster)
    return roster, etp, tests


def eligible_field(signal: date, roster: set[str], etp: set[str], tests: set[str]) -> pl.DataFrame:
    """Unchanged point-in-time rule: common stock, not ETP, not a test issue,
    prior close in [$10, $80], prior-day dollar volume >= $10M."""
    tree = "virgin" if signal <= VIRGIN_END else "full"
    e = pl.read_parquet(REPO_ROOT / f"data/{tree}/eligibility.parquet")
    day = e.filter((pl.col("session_date") == signal)
                   & (pl.col("prior_close") >= 10.0) & (pl.col("prior_close") <= 80.0)
                   & (pl.col("prior_dollar_volume") >= 1e7))
    keep = (roster - etp - set(tests))
    return day.filter(pl.col("symbol").is_in(list(keep))).select(
        "symbol", "prior_close", "prior_dollar_volume").unique(subset=["symbol"])


# ------------------------------------------------------------------ stages
def stage_proof(args) -> int:
    """One previously unresolved scheduled exit must become priced; selection untouched."""
    sym, d = "SNDK", date(2025, 9, 25)
    before_path = CACHE / (d.isoformat() + ".json")
    before = read_json(before_path).get(sym) if before_path.exists() else None
    note(f"PROOF before: {sym} {d} -> " + json.dumps(
        {k: (before or {}).get(k) for k in ("source", "path", "missing", "entry_px")}))
    reqs = rep.plan_requests({sym: {d}})
    counts = rep.acquire(reqs, progress_every=1)
    note(f"PROOF acquire: {json.dumps({k: v for k, v in counts.items() if k != 'statuses'})} "
         f"statuses={counts['statuses']}")
    n = rep.invalidate_summaries([d])
    note(f"PROOF cache partitions invalidated: {n}")
    after = load_summaries({(d.isoformat(), sym)}, 1)[(d.isoformat(), sym)]
    note("PROOF after: " + json.dumps({k: after.get(k) for k in
                                       ("source", "path", "entry_ts", "entry_px", "n_bars", "close")}))
    ok = present(after) and after.get("entry_px") is not None and after.get("source") == "validated"
    dump_json(VERIFY_ROOT / "proof_end_to_end.json",
              {"timestamp": stamp(), "case": f"{sym}/{d.isoformat()}",
               "before": {k: (before or {}).get(k) for k in ("source", "path", "missing", "entry_px")},
               "after": {k: after.get(k) for k in ("source", "path", "entry_ts", "entry_px", "n_bars")},
               "cache_partitions_invalidated": n, "pipeline_ok": bool(ok),
               "pipeline": "authenticated request -> immutable raw parquet -> normalize/validate -> "
                           "per-session validated partition -> summary cache invalidation -> replay loader"})
    note(f"PROOF pipeline_ok={ok}")
    return 0 if ok else 1


def lifecycle_needs() -> dict:
    cl = cohorts(load_field())
    needed = {}
    for c in cl:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        span = FEATS[i - FEATURE_LOOKBACK: fi + HOLD + 1]
        for h in c["rows"]:
            needed.setdefault(h["symbol"], set()).update(span)
    return needed


def stage_lifecycle(args) -> int:
    needed = lifecycle_needs()
    pairs = {(d.isoformat(), s) for s, ds in needed.items() for d in ds}
    note(f"lifecycle: {len(pairs)} symbol-sessions across {len(needed)} selected names")
    sums = load_summaries(pairs, args.workers)
    missing = {}
    for (iso, s), v in sums.items():
        if not present(v):
            missing.setdefault(s, set()).add(date.fromisoformat(iso))
    note(f"lifecycle: missing locally {sum(len(v) for v in missing.values())} across {len(missing)} names")
    reqs = rep.plan_requests(missing)
    dump_json(WORK / "lifecycle_requests.json", reqs)
    note(f"lifecycle: {len(reqs)} planned requests")
    counts = rep.acquire(reqs, concurrency=args.workers)
    note(f"lifecycle acquire: {json.dumps(counts)}")
    rep.invalidate_summaries({d for ds in missing.values() for d in ds})
    cov = rep.coverage_report(reqs)
    note(f"lifecycle coverage: {cov['status_counts']} unresolved={len(cov['unresolved'])}")
    return 0


def stage_field(args) -> int:
    """Acquire the ranking endpoints and feature history for every rule-eligible candidate."""
    roster, etp, tests = tradable_universe()
    note(f"universe: roster={len(roster)} etp={len(etp)} documented_test_issues={tests}")
    ranks = read_json(REPO_ROOT / "data/tmp/cg_arrow002r/ranks_ALL_wed.json")
    cohort_field = {}
    needed = {}
    for iso in sorted(ranks):
        signal = date.fromisoformat(iso)
        field = eligible_field(signal, roster, etp, tests)
        syms = set(field["symbol"].to_list())
        cached = {h["symbol"] for h in ranks[iso]["rows"]}
        cohort_field[iso] = {"rule_field": sorted(syms), "cached": sorted(cached),
                             "missing": sorted(syms - cached), "cached_not_eligible": sorted(cached - syms)}
        i = INDEX[signal]
        span = FEATS[i - FEATURE_LOOKBACK: i + 1]
        for s in syms - cached:
            needed.setdefault(s, set()).update(span)
    dump_json(WORK / "cohort_field.json", cohort_field)
    total_missing = sum(len(v["missing"]) for v in cohort_field.values())
    note(f"field: {total_missing} missing candidate rows, {len(needed)} unique symbols")
    pairs = {(d.isoformat(), s) for s, ds in needed.items() for d in ds}
    note(f"field: {len(pairs)} symbol-sessions required for ranking/features")
    sums = load_summaries(pairs, args.workers)
    gaps = {}
    for (iso, s), v in sums.items():
        if not present(v):
            gaps.setdefault(s, set()).add(date.fromisoformat(iso))
    note(f"field: {sum(len(v) for v in gaps.values())} not present locally across {len(gaps)} names")
    reqs = rep.plan_requests(gaps)
    dump_json(WORK / "field_requests.json", reqs)
    note(f"field: {len(reqs)} planned requests")
    counts = rep.acquire(reqs, concurrency=args.workers)
    note(f"field acquire: {json.dumps(counts)}")
    rep.invalidate_summaries({d for ds in gaps.values() for d in ds})
    cov = rep.coverage_report(reqs)
    note(f"field coverage: {cov['status_counts']} unresolved={len(cov['unresolved'])}")
    return 0


def stage_selected(args) -> int:
    """Lifecycle acquisition for names newly selected by the corrected ranking."""
    sel = read_json(WORK / "r2_selection.json")
    needed = {}
    for iso, rows in sel.items():
        signal = date.fromisoformat(iso)
        i = INDEX[signal]
        span = FEATS[i - FEATURE_LOOKBACK: i + 1 + HOLD + 1]
        for r in rows:
            needed.setdefault(r["symbol"], set()).update(span)
    pairs = {(d.isoformat(), s) for s, ds in needed.items() for d in ds}
    note(f"selected: {len(pairs)} symbol-sessions across {len(needed)} corrected selections")
    sums = load_summaries(pairs, args.workers)
    gaps = {}
    for (iso, s), v in sums.items():
        if not present(v):
            gaps.setdefault(s, set()).add(date.fromisoformat(iso))
    note(f"selected: missing {sum(len(v) for v in gaps.values())} across {len(gaps)} names")
    reqs = rep.plan_requests(gaps)
    dump_json(WORK / "selected_requests.json", reqs)
    counts = rep.acquire(reqs, concurrency=args.workers)
    note(f"selected acquire: {json.dumps(counts)}")
    rep.invalidate_summaries({d for ds in gaps.values() for d in ds})
    cov = rep.coverage_report(reqs)
    note(f"selected coverage: {cov['status_counts']} unresolved={len(cov['unresolved'])}")
    return 0


STAGES = {"proof": stage_proof, "lifecycle": stage_lifecycle, "field": stage_field, "selected": stage_selected}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    t0 = time.monotonic()
    rc = STAGES[args.stage](args)
    note(f"stage {args.stage} finished rc={rc} in {(time.monotonic() - t0) / 60:.1f}m")
    return rc


if __name__ == "__main__":
    sys.exit(main())
