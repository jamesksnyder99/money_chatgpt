"""CG Arrow 014 Phase 0B — memberships and the corridor census. Identification only, no outcomes.

Runs only after LOCK 1. Its job is to find out exactly which corporate-action, security-identity,
feature, causal-entry and H8/H9/H10 lifecycle observations have to be certified before the reveal
may run, and to take every material one to documented dated evidence. It never turns an exit
price into a return.

Three stages:

  screen    Whole-field discontinuity screen over the corridor's independent end-of-day series,
            producing the census case set.
  rank      Mechanical ranking of the point-in-time eligible field under the current documented
            action table, giving the frozen top eight and the rank 9-20 control candidates.
  certify   Per-name certification of every observation the selected lifecycle depends on,
            failing closed on anything materially unresolved.

The screen deliberately does not inherit Arrow 007's top-25 shortlist. A shortlist ordered by
unadjusted return can only see events that inflated a candidate's measured return; a forward
split depresses it, so the candidate a correction would lift into the top eight is exactly the
one a shortlist hides. The corridor's end-of-day layer covers the whole universe on every
session, so here the screen simply runs over all of it.

Usage:
  python scripts/cg_arrow014_phase0b.py --stage screen  [--threshold 1.2]
  python scripts/cg_arrow014_phase0b.py --stage rank    [--workers 8]
  python scripts/cg_arrow014_phase0b.py --stage certify [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    digest, dump_json, features, history, load_summaries, present, read_json, stamp,
)

WORK = H.WORK
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow014"
LOOKBACK = 15            # ranking return horizon, frozen
FEATURE_WINDOW = 20      # R4/R5 volume baseline, frozen
DEPTH = 20               # ranks 9-20 supply the C2/C3 substitution pool
LOG: list[str] = []
T0 = time.monotonic()

ACTION_TABLE = REPORTS / "cg_arrow014_corporate_actions.json"
EMPTY_TABLE = WORK / "actions_holdout_empty.json"
EOD_CORRIDOR = WORK / "eod_corridor.parquet"
CASES = WORK / "phase0b_event_cases.json"
MEMBERSHIP = WORK / "phase0b_membership.json"
FIELD = WORK / "phase0b_field.json"


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def action_table() -> Path:
    """The holdout's own table, or an empty one while its evidence is still being assembled."""
    if ACTION_TABLE.exists():
        return ACTION_TABLE
    if not EMPTY_TABLE.exists():
        dump_json(EMPTY_TABLE, {"events": [], "security_identity": [], "trading_events": [],
                                "non_comparable_events": [],
                                "note": ("no corporate action is assumed for the pristine corridor "
                                         "until its own dated evidence is assembled")})
    return EMPTY_TABLE


def require_lock1() -> tuple[str, dict]:
    freeze = read_json(REPORTS / "cg_arrow014_reveal_freeze.json")
    committed = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "reports/cg_arrow014_reveal_freeze.json"],
        cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    if not committed:
        raise SystemExit("LOCK 1 is not committed; membership generation is not permitted")
    drift = {p: digest(REPO_ROOT / p) == h for p, h in freeze.get("code_hashes", {}).items()
             if (REPO_ROOT / p).exists()}
    note(f"LOCK 1 committed at {committed[:7]}; frozen code hashes still matching: "
         f"{sum(drift.values())}/{len(drift)}")
    return committed, drift


def eligible_pairs() -> pl.DataFrame:
    elig = pl.read_parquet(WORK / "eligibility_holdout.parquet")
    return elig.filter(pl.col("eligible") & pl.col("session_date").is_in(HO.signal_dates()))


def candidate_field(pairs: pl.DataFrame) -> dict:
    out: dict = defaultdict(dict)
    for d, sym, pc, pdv in pairs.select(
            ["session_date", "symbol", "prior_close", "prior_dollar_volume"]).iter_rows():
        out[d.isoformat()][sym] = {"prior_close": pc, "prior_dollar_volume": pdv}
    return dict(out)


# ---------------------------------------------------------------------------- screen
def stage_screen(args) -> int:
    """Whole-field end-of-day discontinuity screen; writes the census case set."""
    if not EOD_CORRIDOR.exists():
        raise SystemExit(f"{EOD_CORRIDOR} is missing; build the corridor end-of-day series first")
    eod = pl.read_parquet(EOD_CORRIDOR)
    note(f"corridor end-of-day series: {eod.height:,} rows, {eod['symbol'].n_unique():,} securities, "
         f"{eod['eod_date'].n_unique()} sessions")

    pairs = eligible_pairs()
    # The window a cohort actually depends on: the ranking lookback through the signal, and the
    # fill session through the longest hold.
    covered: dict[str, set] = defaultdict(set)
    for d, sym in pairs.select(["session_date", "symbol"]).unique().iter_rows():
        i = HO.INDEX[d]
        for j in range(max(0, i - LOOKBACK - 1), min(len(HO.FEATS), i + 1 + max(HO.HOLDS) + 1)):
            covered[sym].add(HO.FEATS[j])
    note(f"securities eligible on at least one signal session: {len(covered):,}; "
         f"lifecycle-covered observations: {sum(len(v) for v in covered.values()):,}")

    df = (eod.filter(pl.col("close").is_finite() & (pl.col("close") > 0))
             .sort(["symbol", "eod_date"])
             .with_columns(prev=pl.col("close").shift(1).over("symbol"),
                           prev_date=pl.col("eod_date").shift(1).over("symbol"),
                           prev_volume=pl.col("volume").shift(1).over("symbol"))
             .filter(pl.col("prev").is_not_null())
             .with_columns(ratio=pl.col("close") / pl.col("prev")))
    df = df.with_columns(mag=pl.max_horizontal(pl.col("ratio"), 1 / pl.col("ratio")))
    hits = df.filter((pl.col("mag") >= args.threshold) & pl.col("symbol").is_in(list(covered)))
    note(f"session-to-session observations screened: {df.height:,}; ratio magnitude >= "
         f"{args.threshold}: {hits.height:,} before the lifecycle restriction")

    # A ratio screen cannot see a ticker that was reassigned to a different issuer whose price
    # happens to sit near the old one. What it does leave behind is a break in the series, so
    # every multi-session trading gap inside a lifecycle window is an identity case in its own
    # right. This is the evidence that closes the point-in-time identity question rather than
    # assuming the vendor's symbol meant one security for the whole corridor.
    gap_cases = {}
    for sym, grp in (eod.filter(pl.col("symbol").is_in(list(covered)))
                        .sort(["symbol", "eod_date"])
                        .group_by("symbol", maintain_order=True)):
        sym = sym[0] if isinstance(sym, tuple) else sym
        seen = set(grp["eod_date"].to_list())
        window = sorted(covered[sym])
        run, run_start = 0, None
        for d in window:
            if d in seen:
                if run >= args.gap_sessions and run_start is not None:
                    gap_cases[f"{sym}|{d.isoformat()}"] = {
                        "symbol": sym, "date": d.isoformat(),
                        "gap_sessions": run, "gap_start": run_start.isoformat(),
                        "kind": "TRADING_GAP_THEN_RESUMPTION",
                        "source": "independent corridor end-of-day layer"}
                run, run_start = 0, None
            else:
                run += 1
                run_start = run_start or d
    note(f"multi-session trading gaps ({args.gap_sessions}+ sessions) inside a lifecycle window: "
         f"{len(gap_cases):,} across {len({c['symbol'] for c in gap_cases.values()}):,} securities")

    cases = {}
    for sym, d, prev_d, close, prev, ratio, vol, prev_vol in hits.select(
            ["symbol", "eod_date", "prev_date", "close", "prev", "ratio",
             "volume", "prev_volume"]).iter_rows():
        if d not in covered[sym]:
            continue
        cases[f"{sym}|{d.isoformat()}"] = {
            "symbol": sym, "date": d.isoformat(), "prior_session": prev_d.isoformat(),
            "close_before": prev, "close_at": close, "ratio": ratio,
            "magnitude": max(ratio, 1 / ratio), "volume_before": prev_vol, "volume_at": vol,
            "kind": "PRICE_DISCONTINUITY",
            "source": "independent corridor end-of-day layer, unadjusted"}
    for key, case in gap_cases.items():
        if key in cases:
            cases[key].update({k: v for k, v in case.items() if k not in cases[key]})
            cases[key]["kind"] = "PRICE_DISCONTINUITY_AFTER_TRADING_GAP"
        else:
            cases[key] = case
    dump_json(CASES, cases)
    syms = sorted({c["symbol"] for c in cases.values()})
    note(f"census case set: {len(cases):,} symbol-session investigations across "
         f"{len(syms):,} securities")
    (WORK / "phase0b_census_symbols.txt").write_text("\n".join(syms) + "\n", encoding="utf-8")

    buckets: dict = defaultdict(int)
    for c in cases.values():
        if "magnitude" not in c:
            continue
        for lo, hi, label in ((1.95, 2.05, "near 2:1"), (2.9, 3.1, "near 3:1"),
                              (3.9, 4.1, "near 4:1"), (4.85, 5.15, "near 5:1"),
                              (9.7, 10.3, "near 10:1"), (1.45, 1.55, "near 3:2"),
                              (1.3, 1.37, "near 4:3")):
            if lo <= c["magnitude"] <= hi:
                buckets[label] += 1
    note("cases sitting on a common split ratio: " +
         (", ".join(f"{k}={v}" for k, v in sorted(buckets.items())) or "none"))

    dump_json(WORK / "phase0b_screen_manifest.json", {
        "arrow": "CG Arrow 014", "stage": "screen", "timestamp": stamp(),
        "threshold": args.threshold, "screened_observations": df.height,
        "securities_screened": int(eod["symbol"].n_unique()),
        "securities_in_lifecycle": len(covered),
        "hits_before_restriction": hits.height, "cases": len(cases),
        "gap_sessions_threshold": args.gap_sessions,
        "price_discontinuity_cases": sum(1 for c in cases.values()
                                         if c["kind"] == "PRICE_DISCONTINUITY"),
        "trading_gap_cases": sum(1 for c in cases.values()
                                 if c["kind"] == "TRADING_GAP_THEN_RESUMPTION"),
        "both_cases": sum(1 for c in cases.values()
                          if c["kind"] == "PRICE_DISCONTINUITY_AFTER_TRADING_GAP"),
        "case_securities": len(syms), "split_ratio_buckets": dict(buckets),
        "scope": ("every security in the corridor, restricted to the sessions its own cohorts "
                  "depend on; no shortlist by measured return"),
        "no_outcomes_calculated": True, "log": LOG})
    return 0


# ---------------------------------------------------------------------------- rank
def stage_rank(args) -> int:
    """Mechanical membership under the current documented action table."""
    committed, drift = require_lock1()
    table = action_table()
    info = HO.activate(action_path=table)
    note(f"corridor active: {info['sessions']} sessions, cutoff {info['cutoff']}, action table "
         f"{table.relative_to(REPO_ROOT).as_posix()}")

    field = candidate_field(eligible_pairs())
    # The reveal has to rebuild exactly this field, so it is written down rather than rederived
    # from an eligibility file that a later pass could touch.
    dump_json(FIELD, field)
    note(f"point-in-time eligible field on {len(field)} signal sessions; sizes "
         f"{min(len(v) for v in field.values())}..{max(len(v) for v in field.values())}")

    endpoints = set()
    for iso, cands in field.items():
        back = HO.FEATS[HO.INDEX[date.fromisoformat(iso)] - LOOKBACK].isoformat()
        for s in cands:
            endpoints.add((iso, s))
            endpoints.add((back, s))
    note(f"loading {len(endpoints):,} ranking endpoint observations with {args.workers} workers")
    summaries = load_summaries(endpoints, args.workers)
    status = HO.observation_status(summaries)
    no_trade = sum(1 for v in status.values() if v == "DOCUMENTED_NO_TRADING")
    note(f"non-present endpoint observations: {no_trade:,} documented no-trading, "
         f"{len(status) - no_trade:,} without retrieval evidence")

    ranked, unresolved = {}, []
    for iso, cands in sorted(field.items()):
        res = rank.rank_cohort(date.fromisoformat(iso), cands, summaries, status)
        ranked[iso] = res
        unresolved.extend([{"cohort_id": iso, **u} for u in res["unrankable"]
                           if u["classification"] == "UNRESOLVED_OBSERVATION"])
    top8 = {iso: [h["symbol"] for h in r["rows"][:8]] for iso, r in ranked.items()}
    deeper = {iso: [h["symbol"] for h in r["rows"][8:DEPTH]] for iso, r in ranked.items()}

    prior = read_json(MEMBERSHIP) if MEMBERSHIP.exists() else None
    changed = prior is not None and prior.get("top8") != top8
    membership = {"top8": top8, "ranks_9_20": deeper,
                  "action_table": table.relative_to(REPO_ROOT).as_posix(),
                  "action_table_sha256": digest(table), "membership_sha256": sha_obj(top8),
                  "timestamp": stamp(), "lock1_commit": committed}
    dump_json(MEMBERSHIP, membership)
    dump_json(OUT / "membership.json", membership)

    note(f"mechanical membership over {len(top8)} cohorts: {sum(len(v) for v in top8.values())} "
         f"selected slots, {sum(len(v) for v in deeper.values())} rank 9-{DEPTH} controls, "
         f"{len({s for v in top8.values() for s in v})} distinct selected securities")
    note(f"candidates unrankable on an unresolved observation: {len(unresolved)}")
    note("membership hash " + membership["membership_sha256"][:12] +
         (" (CHANGED from the previous iteration; the fixed point is not yet reached)" if changed
          else " (unchanged from the previous iteration)" if prior else " (first iteration)"))

    dump_json(WORK / "phase0b_rank_manifest.json", {
        "arrow": "CG Arrow 014", "stage": "rank", "timestamp": stamp(),
        "lock1_commit": committed, "lock1_code_hashes_match": drift, "corridor": info,
        "action_table": membership["action_table"],
        "action_table_sha256": membership["action_table_sha256"],
        "cohorts": len(top8), "selected_slots": sum(len(v) for v in top8.values()),
        "control_candidates": sum(len(v) for v in deeper.values()),
        "distinct_selected_securities": len({s for v in top8.values() for s in v}),
        "field_min": min(len(v) for v in field.values()),
        "field_max": max(len(v) for v in field.values()),
        "ranking_scope": {iso: r["ranking_scope"] for iso, r in ranked.items()},
        "unrankable_unresolved": len(unresolved), "unrankable_unresolved_detail": unresolved[:50],
        "membership_sha256": membership["membership_sha256"],
        "membership_changed_from_previous": bool(changed),
        "fixed_point_reached": bool(prior is not None and not changed),
        "no_outcomes_calculated": True, "log": LOG})
    return 0


def investigation_resolutions() -> dict:
    """(symbol, session) -> what the primary-source investigation actually established.

    A discontinuity the screen found is not resolved by asserting it was a price move. It is
    resolved when a search capable of finding a corporate action was carried out and did not find
    one. Capability is the whole point, and it is exactly what Arrow 013 could not achieve: if the
    ticker never resolved to an issuer, no filing was ever read, and the observation stays
    unresolved no matter how ordinary the move looks.

    So a resolution is granted only where the identity was established point-in-time AND that
    issuer's filings around the date were searched. Where a documented action was found, it is in
    the action table and the engine has already normalised the price; anything still discontinuous
    after that is reported, not excused.
    """
    path = WORK / "identity_investigation.json"
    if not path.exists():
        return {}
    cases = read_json(CASES)
    investigated = read_json(path)
    applied = {(e["symbol"], e["effective_session"])
               for e in read_json(ACTION_TABLE).get("events", [])} if ACTION_TABLE.exists() else set()
    out = {}
    for case in cases.values():
        sym, iso = case["symbol"], case["date"]
        rec = investigated.get(sym)
        if not rec:
            continue
        ident = rec.get("identity") or {}
        acts = rec.get("actions") or {}
        if not ident.get("cik"):
            continue                      # never reached the issuer; nothing is established
        if (sym, iso) in applied:
            continue                      # the engine normalised it; no resolution needed here
        if acts.get("status") not in ("FILING_EVIDENCE_FOUND", "UNRESOLVED_NO_FILING_EVIDENCE"):
            continue                      # the search did not complete
        out[(sym, iso)] = (
            "INVESTIGATED_NO_DOCUMENTED_UNIT_CHANGE: identity resolved point-in-time to "
            f"CIK {ident['cik']} and that issuer's filings around this session were searched "
            f"({acts.get('filings_in_neighbourhood', 0)} in the neighbourhood, "
            f"{acts.get('filings_scanned', 0)} documents read); no split or consolidation "
            "statement covers it, so the level change is a price move")
    return out


# ---------------------------------------------------------------------------- certify
def stage_certify(args) -> int:
    """Certify every observation the selected lifecycle depends on. Fails closed."""
    committed, _ = require_lock1()
    table = action_table()
    info = HO.activate(action_path=table)
    membership = read_json(MEMBERSHIP)
    top8, deeper = membership["top8"], membership["ranks_9_20"]
    note(f"certifying the corridor behind {sum(len(v) for v in top8.values())} selected slots "
         f"and {sum(len(v) for v in deeper.values())} control candidates")

    needs = set()
    for iso in top8:
        i = HO.INDEX[date.fromisoformat(iso)]
        for sym in top8[iso] + deeper[iso]:
            for j in range(max(0, i - FEATURE_WINDOW - 1),
                           min(len(HO.FEATS), i + 1 + max(HO.HOLDS) + 1)):
                needs.add((HO.FEATS[j].isoformat(), sym))
    note(f"corridor observations required: {len(needs):,}")
    summaries = load_summaries(needs, args.workers)

    resolutions = investigation_resolutions()
    note(f"investigated resolutions available for {len(resolutions):,} symbol-sessions")
    rows, exceptions = [], []
    for iso in sorted(top8):
        d = date.fromisoformat(iso)
        entry = HO.entry_for(d)
        for grp, syms, base in (("TOP8", top8[iso], 1), ("CONTROL_9_20", deeper[iso], 9)):
            for pos, sym in enumerate(syms, base):
                hist = history(sym, HO.FEATS[HO.INDEX[d] - FEATURE_WINDOW: HO.INDEX[d] + 1],
                               d, summaries)
                f = features(hist)
                erec = summaries.get((entry.isoformat(), sym)) if entry else None
                lb = rank.lookback_integrity(d, sym, summaries, resolutions)
                row = {"cohort_id": iso, "group": grp, "rank": pos, "symbol": sym,
                       "signal_date": iso, "entry_date": entry.isoformat() if entry else None,
                       "feature_sessions_present": f["history_sessions"],
                       "feature_sessions_required": FEATURE_WINDOW + 1,
                       "ret3_present": f["ret3"] is not None,
                       "volume_ratio_present": f["volume_ratio"] is not None,
                       "causal_preorder_present": bool(present(erec)
                                                       and erec.get("preorder") is not None),
                       "entry_execution_present": bool(present(erec)
                                                       and erec.get("exec_px") is not None),
                       "entry_execution_field": erec.get("exec_field") if present(erec) else None,
                       "lookback_flag": lb["lookback_flag"],
                       "lookback_resolution": lb["lookback_resolution"],
                       "lookback_max_ratio": lb["lookback_max_ratio"]}
                for h in HO.HOLDS:
                    x = HO.exit_for(entry, h) if entry else None
                    xr = summaries.get((x.isoformat(), sym)) if x else None
                    row[f"h{h}_exit_date"] = x.isoformat() if x else None
                    row[f"h{h}_exit_observed"] = bool(present(xr)
                                                      and xr.get("exec_px") is not None)
                    hd = (rank.holding_integrity(entry, x, sym, summaries, resolutions)
                          if entry and x else {"holding_flag": "NO_EXIT_SESSION",
                                               "holding_resolution": "NO_EXIT_SESSION"})
                    row[f"h{h}_holding_flag"] = hd["holding_flag"]
                    row[f"h{h}_holding_resolution"] = hd["holding_resolution"]
                rows.append(row)

    exp.write_csv(OUT / "selected_corridor_state.csv", rows)
    t8 = [r for r in rows if r["group"] == "TOP8"]

    def flag(rs, label, why):
        if rs:
            exceptions.append({"exception": label, "count": len(rs), "why": why,
                               "examples": [{"cohort_id": r["cohort_id"], "rank": r["rank"],
                                             "symbol": r["symbol"]} for r in rs[:10]]})
        return len(rs)

    counts = {
        "feature_history_incomplete": flag(
            [r for r in t8 if r["feature_sessions_present"] < r["feature_sessions_required"]],
            "FEATURE_HISTORY_INCOMPLETE", "an R4/R5 sizing input rests on a short history"),
        "momentum_feature_missing": flag(
            [r for r in t8 if not r["ret3_present"]], "MOMENTUM_FEATURE_MISSING",
            "the R5 momentum tier cannot be determined"),
        "volume_feature_missing": flag(
            [r for r in t8 if not r["volume_ratio_present"]], "VOLUME_FEATURE_MISSING",
            "the R4/R5 volume tier cannot be determined"),
        "causal_preorder_missing": flag(
            [r for r in t8 if not r["causal_preorder_present"]], "CAUSAL_PREORDER_MISSING",
            "the causal pre-order observation that sets the quantity is absent"),
        "entry_execution_missing": flag(
            [r for r in t8 if not r["entry_execution_present"]], "ENTRY_EXECUTION_MISSING",
            "the fill cannot be observed"),
        "ranking_window_unexplained": flag(
            [r for r in t8 if r["lookback_resolution"]
             == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"],
            "RANKING_WINDOW_DISCONTINUITY_UNEXPLAINED",
            "the 15-session ranking return may not rest on one share unit, and no search "
            "capable of settling it has been completed for this security"),
    }
    for h in HO.HOLDS:
        counts[f"h{h}_exit_missing"] = flag(
            [r for r in t8 if not r[f"h{h}_exit_observed"]], f"H{h}_EXIT_MISSING",
            f"the {h}-session hold cannot be closed on an observed price")
        counts[f"h{h}_holding_unexplained"] = flag(
            [r for r in t8 if r[f"h{h}_holding_resolution"]
             == "UNEXPLAINED_HOLDING_WINDOW_DISCONTINUITY"],
            f"H{h}_HOLDING_WINDOW_DISCONTINUITY_UNEXPLAINED",
            f"the {h}-session holding path may cross a share-unit change")
    note("selected-corridor exceptions: " +
         (", ".join(f"{k}={v}" for k, v in counts.items() if v) or "none"))

    material = sum(counts.values())
    dump_json(WORK / "phase0b_certify_manifest.json", {
        "arrow": "CG Arrow 014", "stage": "certify", "timestamp": stamp(),
        "lock1_commit": committed, "corridor": info,
        "action_table": table.relative_to(REPO_ROOT).as_posix(),
        "membership_sha256": membership["membership_sha256"],
        "rows": len(rows), "selected_rows": len(t8), "observations_required": len(needs),
        "exception_counts": counts, "exceptions": exceptions,
        "unresolved_material_exceptions": material,
        "gate": "READY_FOR_LOCK_2" if material == 0 else "BLOCKED",
        "no_outcomes_calculated": True, "log": LOG})
    note(f"unresolved material exceptions on frozen scored cells: {material} -> "
         f"{'ready for LOCK 2' if material == 0 else 'BLOCKED'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("screen", "rank", "certify"), required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--threshold", type=float, default=1.2)
    ap.add_argument("--gap-sessions", type=int, default=3,
                    help="consecutive absent sessions that make a symbol an identity case")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    return {"screen": stage_screen, "rank": stage_rank, "certify": stage_certify}[args.stage](args)


if __name__ == "__main__":
    sys.exit(main())
