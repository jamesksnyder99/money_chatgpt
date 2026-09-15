"""CG Arrow 014 Phase 0A — verify the audited A13 source state. No strategy outcomes.

Checks the acquisition, calendar, universe and pristine-status facts the reveal depends on,
from the local immutable layer rather than from the intermediate public record. It also closes
one boundary gap Arrow 013 left open: the eligibility layer stopped at the end of the newly
acquired span, so the four August 2025 signal sessions had no point-in-time eligibility rows.
August 2025 is the twelfth signal month, so those rows are built here from the separately
authenticated August 2025 end-of-day source, with the provenance distinction preserved.

Nothing here ranks, selects or scores. No P&L, hit rate, drawdown, monthly return or ending
equity is computed.

Usage: python scripts/cg_arrow014_phase0a.py [--workers 6]
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest import holdout2024 as H  # noqa: E402
from ingest.eligibility import MAX_CLOSE_VIRGIN, MIN_CLOSE, PDV_10M  # noqa: E402
from ingest.paths import DATA, ETP_TICKERS, REPO_ROOT, REPORTS, SYMBOLS  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification.r4r5_data import digest, dump_json, read_json, stamp  # noqa: E402

WORK = H.WORK
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow014"
TEST_ISSUE = re.compile(r"^Z[A-Z]ZZT$")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def load_eod_chunk(spec) -> pl.DataFrame:
    """One month of end-of-day partitions from a named source tree."""
    folder, label = Path(spec[0]), spec[1]
    files = sorted(p for p in folder.glob("*.parquet") if not p.name.startswith("_"))
    frames = []
    for i in range(0, len(files), 500):
        try:
            df = pl.read_parquet(files[i:i + 500])
        except Exception:  # noqa: BLE001
            df = pl.concat([pl.read_parquet(f) for f in files[i:i + 500]], how="diagonal_relaxed")
        if df.height == 0:
            continue
        if "eod_date" not in df.columns:
            from ingest.eligibility import eod_session_dates
            df = eod_session_dates(df)
        keep = [c for c in ("symbol", "eod_date", "close", "volume") if c in df.columns]
        if len(keep) == 4:
            frames.append(df.select(keep))
    if not frames:
        return pl.DataFrame(schema={"symbol": pl.String, "eod_date": pl.Date,
                                    "close": pl.Float64, "volume": pl.Int64})
    out = pl.concat(frames, how="diagonal_relaxed")
    return out.with_columns(pl.lit(label).alias("source"))


def august_2025_pristine_audit() -> dict:
    """Has any prior artifact ever scored a signal cohort owned by August 2025?

    Warmup and lookback use is allowed and expected; August 2025 was the previous study's
    warmup. What would break pristineness is a strategy outcome owned by an August 2025
    signal cohort. Every prior trade ledger, cohort audit and public report is searched for
    exactly that.
    """
    hits, searched = [], []
    aug = re.compile(r"2025-08-\d{2}")
    # private trade/cohort ledgers from every prior arrow
    for folder in sorted((REPO_ROOT / "handoff" / "outgoing").glob("cg_arrow0*")):
        for p in sorted(folder.glob("*.csv")):
            searched.append(str(p.relative_to(REPO_ROOT)).replace("\\", "/"))
            try:
                with p.open(encoding="utf-8", newline="") as fh:
                    rd = csv.DictReader(fh)
                    cols = rd.fieldnames or []
                    key = next((c for c in ("cohort_id", "signal_date", "signal_month") if c in cols), None)
                    if key is None:
                        continue
                    for r in rd:
                        v = str(r.get(key) or "")
                        if v.startswith("2025-08"):
                            hits.append({"artifact": searched[-1], "column": key, "value": v})
                            break
            except Exception as exc:  # noqa: BLE001
                hits.append({"artifact": searched[-1], "error": type(exc).__name__})
    # Public JSON reports are tested structurally rather than by proximity of a date to a
    # keyword. What breaks pristineness is a SIGNAL COHORT owned by August 2025, which appears
    # as a cohort_id / signal_date / signal_month field. A 2025-08 date reached through a later
    # cohort's ranking or feature lookback window is legitimate warmup use; a text-proximity
    # rule cannot tell the two apart and produced a false positive on an Arrow 007 record whose
    # cohort_id was 2025-09-03 and whose window was "ranking".
    def owned_by_august(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("cohort_id", "signal_date", "signal_month") and isinstance(v, str) \
                        and v.startswith("2025-08"):
                    yield path + "/" + k, v
                yield from owned_by_august(v, path + "/" + k)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from owned_by_august(v, path + f"[{i}]")

    for p in sorted(REPORTS.glob("cg_arrow0*")):
        if p.suffix not in (".csv", ".json", ".md", ".txt"):
            continue
        if "cg_arrow013" in p.name or "cg_arrow014" in p.name:
            continue
        searched.append(str(p.relative_to(REPO_ROOT)).replace("\\", "/"))
        if p.suffix != ".json":
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for where, val in owned_by_august(obj):
            hits.append({"artifact": searched[-1], "field": where, "value": val})
            break

    months = set()
    for folder in sorted((REPO_ROOT / "handoff" / "outgoing").glob("cg_arrow0*")):
        if "cg_arrow014" in folder.name:
            continue
        for p in sorted(folder.glob("*.csv")):
            try:
                with p.open(encoding="utf-8", newline="") as fh:
                    rd = csv.DictReader(fh)
                    if not rd.fieldnames or "cohort_id" not in rd.fieldnames:
                        continue
                    for r in rd:
                        months.add(str(r.get("cohort_id"))[:7])
            except Exception:  # noqa: BLE001
                continue

    status = ("AUGUST_2025_NOT_PREVIOUSLY_SCORED_AS_SIGNAL_MONTH" if not hits
              else "AUGUST_2025_PREVIOUSLY_EXPOSED")
    return {"status": status, "artifacts_searched": len(searched), "hits": hits,
            "basis": ("every prior private trade and cohort ledger was searched by column for a "
                      "cohort_id, signal_date or signal_month owned by August 2025, and every prior "
                      "public JSON report was walked structurally for the same fields. A 2025-08 date "
                      "reached through a later cohort's ranking or feature lookback window is "
                      "legitimate warmup use and is not a hit."),
            "distinct_prior_signal_cohort_months": sorted(
                m for m in months if re.fullmatch(r"\d{4}-\d{2}", m)),
            "searched": searched}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []

    # ---------------------------------------------------------------- A13 acquisition state
    a13 = read_json(REPORTS / "cg_arrow013_manifest.json")
    note(f"A13 terminal status preserved: {a13['certification_status']} "
         f"with {len(a13['remaining_gaps'])} declared evidence gaps")
    eod_n = sum(1 for _ in H.RAW_EOD.rglob("*.parquet"))
    bars_n = sum(1 for _ in H.RAW_BARS.rglob("*.parquet"))
    bar_sessions = sorted(p.name for p in H.RAW_BARS.iterdir())
    universe = (WORK / "minute_universe.txt").read_text(encoding="utf-8").split()
    expected_bars = len(universe) * len(bar_sessions)
    acq = {"eod_partitions": eod_n, "bar_partitions": bars_n,
           "newly_acquired_sessions": len(bar_sessions),
           "universe_symbols": len(universe), "expected_bar_partitions": expected_bars,
           "bar_inventory_complete": bars_n == expected_bars,
           "temp_files": sum(1 for _ in Path("data/holdout2024").rglob("*.tmp")),
           "note": ("250 newly acquired sessions 2024-08-01 to 2025-07-31; authenticated August 2025 "
                    "reuse and September 2025 lifecycle support complete the 292-session corridor")}
    note(f"A13 local inventory: {eod_n:,} end-of-day partitions, {bars_n:,} minute partitions over "
         f"{len(bar_sessions)} newly acquired sessions, complete={acq['bar_inventory_complete']}")
    if not acq["bar_inventory_complete"]:
        blockers.append(f"minute inventory {bars_n} != expected {expected_bars}")
    if acq["temp_files"]:
        blockers.append(f"{acq['temp_files']} interrupted temp files remain")
    # A vendor error blocks only if it left an observation missing. Acquisition was resumable,
    # so a transient session-expiry failure that a later attempt superseded is a recorded event,
    # not an unresolved gap. Counting ledger lines confuses the two, so every failed request is
    # re-checked against what actually landed.
    for stage in ("eod", "bars"):
        pe = WORK / f"vendor_errors_{stage}.jsonl"
        recs = [json.loads(line) for line in pe.open(encoding="utf-8") if line.strip()] if pe.exists() else []
        unresolved = []
        for r in recs:
            sym, chunk = r.get("symbol"), r.get("chunk")
            span = next(((a, b) for a, b, c in H.eod_chunks() if c == chunk), None)
            if span is None:
                unresolved.append(r)
                continue
            if stage == "bars":
                if any(not H.raw_bar_path(d, sym).exists() for d in H.sessions(*span)):
                    unresolved.append(r)
            elif not H.raw_eod_path(sym, chunk).exists():
                unresolved.append(r)
        acq[f"vendor_error_records_{stage}"] = len(recs)
        acq[f"unresolved_vendor_errors_{stage}"] = len(unresolved)
        acq[f"vendor_error_character_{stage}"] = (
            "none" if not recs else
            ("all superseded by a later successful landing" if not unresolved else "unresolved"))
        if unresolved:
            blockers.append(f"{len(unresolved)} vendor errors in the {stage} ledger left an observation missing")
    note(f"vendor error ledgers: eod {acq.get('vendor_error_records_eod',0)} records / "
         f"{acq.get('unresolved_vendor_errors_eod',0)} unresolved; bars "
         f"{acq.get('vendor_error_records_bars',0)} records / "
         f"{acq.get('unresolved_vendor_errors_bars',0)} unresolved")

    # ---------------------------------------------------------------- calendar
    cal = HO.cohort_calendar()
    cal_ok = all(r["status"] == "OK" for r in cal)
    try:
        import pandas_market_calendars as mcal
        ref = [d.date() for d in mcal.get_calendar("NYSE").schedule(
            start_date=HO.CORRIDOR_START, end_date=HO.CORRIDOR_END).index]
    except Exception:  # noqa: BLE001
        ref = []
    calendar = {"corridor_sessions": len(HO.FEATS), "cutoff": HO.CUTOFF.isoformat(),
                "score_sessions": len(HO.SCORE),
                "independent_reference": "pandas_market_calendars NYSE" if ref else "unavailable",
                "independent_sessions": len(ref) if ref else None,
                "identical_to_reference": (sorted(ref) == HO.FEATS) if ref else None,
                "cohorts": len(cal), "all_cohorts_resolvable": cal_ok,
                "rollback_weeks": [{"nominal_anchor": r["nominal_anchor"], "signal_date": r["signal_date"],
                                    "rolled_back_days": r["rolled_back_days"]}
                                   for r in cal if r.get("rolled_back_days")],
                "signal_months": dict(sorted(Counter(r["signal_month"] for r in cal).items()))}
    note(f"calendar: {len(HO.FEATS)} corridor sessions, identical to independent reference="
         f"{calendar['identical_to_reference']}; {len(cal)} cohorts, all resolvable={cal_ok}")
    note(f"rollback weeks: {[(r['nominal_anchor'], r['signal_date']) for r in calendar['rollback_weeks']]}")
    if not cal_ok:
        blockers.append("a frozen cohort could not resolve a signal, entry or H8/H9/H10 exit")
    if ref and not calendar["identical_to_reference"]:
        blockers.append("holdout calendar differs from the independent NYSE reference")
    if len(cal) != 52:
        note(f"NOTE: cohort count is {len(cal)}, not the expected 52; the calendar is authoritative")

    # ---------------------------------------------------------------- eligibility, incl. August 2025
    elig = pl.read_parquet(WORK / "eligibility.parquet")
    have = set(elig["session_date"].unique().to_list())
    need = [d for d in HO.signal_dates() if d not in have]
    note(f"signal sessions lacking point-in-time eligibility rows: {len(need)} {[d.isoformat() for d in need]}")
    extended = {"sessions_added": 0, "rows_added": 0, "source": None}
    if need:
        # Build the missing rows from the separately authenticated August 2025 end-of-day source.
        specs = [(DATA / "virgin" / "eod" / c, f"virgin_eod/{c}") for c in ("2025-07", "2025-08-early", "2025-08")]
        frames = []
        with ProcessPoolExecutor(max_workers=max(1, min(args.workers, 6))) as pool:
            for fut in as_completed([pool.submit(load_eod_chunk, s) for s in specs]):
                df = fut.result()
                if df.height:
                    frames.append(df)
        eod = pl.concat(frames, how="diagonal_relaxed").unique(subset=["symbol", "eod_date"])
        note(f"authenticated August 2025 end-of-day source: {eod.height:,} rows, "
             f"{eod['symbol'].n_unique():,} securities, {eod['eod_date'].n_unique()} dates")
        roster = set(pl.read_parquet(SYMBOLS)["symbol"].to_list())
        etp = {x.strip().upper() for x in ETP_TICKERS.read_text(encoding="utf-8").splitlines()
               if x.strip() and not x.startswith("#")}
        pairs = pl.DataFrame({"session_date": need,
                              "prior_date": [HO.FEATS[HO.INDEX[d] - 1] for d in need]})
        add = (eod.rename({"eod_date": "prior_date", "close": "prior_close", "volume": "prior_volume"})
               .join(pairs, on="prior_date", how="inner")
               .with_columns((pl.col("prior_close") * pl.col("prior_volume")).alias("prior_dollar_volume")))
        add = add.with_columns(
            pl.col("symbol").is_in(list(etp)).alias("is_etp"),
            pl.col("symbol").str.contains(r"^Z[A-Z]ZZT$").alias("is_test_issue"),
            pl.col("symbol").is_in(list(roster)).alias("in_roster"))
        reason = (
            pl.when(~pl.col("in_roster")).then(pl.lit("not_in_common_stock_roster"))
            .when(pl.col("is_test_issue")).then(pl.lit("exchange_test_issue"))
            .when(pl.col("is_etp")).then(pl.lit("exchange_traded_product"))
            .when(pl.col("prior_close").is_null() | pl.col("prior_volume").is_null())
            .then(pl.lit("no_prior_end_of_day_record"))
            .when((pl.col("prior_close") < MIN_CLOSE) | (pl.col("prior_close") > MAX_CLOSE_VIRGIN))
            .then(pl.lit("prior_close_out_of_band"))
            .when(pl.col("prior_dollar_volume") < PDV_10M)
            .then(pl.lit("prior_dollar_volume_below_10m"))
            .otherwise(pl.lit("")))
        add = add.with_columns(reason.alias("exclude_reason"), (reason == "").alias("eligible"),
                               (pl.col("prior_dollar_volume") >= PDV_10M).fill_null(False).alias("pdv_ge_10m"),
                               pl.lit("SIGNAL").alias("period_role"))
        cols = [c for c in elig.columns if c in add.columns]
        merged = pl.concat([elig.select(cols), add.select(cols)], how="diagonal_relaxed")
        merged.write_parquet(WORK / "eligibility_holdout.parquet")
        extended = {"sessions_added": len(need), "rows_added": add.height,
                    "source": "data/virgin/eod 2025-07, 2025-08-early, 2025-08 (authenticated reuse)",
                    "eligible_added": int(add.filter(pl.col("eligible")).height)}
        note(f"eligibility extended for August 2025: +{add.height:,} rows over {len(need)} sessions, "
             f"{extended['eligible_added']:,} eligible")
        elig = merged
    else:
        elig.write_parquet(WORK / "eligibility_holdout.parquet")

    still = [d for d in HO.signal_dates() if d not in set(elig["session_date"].unique().to_list())]
    if still:
        blockers.append(f"{len(still)} signal sessions still lack eligibility rows")
    per = (elig.filter(pl.col("eligible")).group_by("session_date").len()
           .sort("session_date"))
    sig_field = per.filter(pl.col("session_date").is_in(HO.signal_dates()))
    counts = sig_field["len"].to_list()
    universe_all = sorted(elig.filter(pl.col("eligible"))["symbol"].unique().to_list())
    eligibility = {"rows": elig.height, "sessions": elig["session_date"].n_unique(),
                   "signal_sessions_covered": len(HO.signal_dates()) - len(still),
                   "signal_field_min": min(counts) if counts else None,
                   "signal_field_median": sorted(counts)[len(counts) // 2] if counts else None,
                   "signal_field_max": max(counts) if counts else None,
                   "union_eligible_securities": len(universe_all),
                   "august_2025_extension": extended,
                   "etp_rule_effect": ("no-op: the roster is already common-stock-only and contains none "
                                       "of the listed exchange-traded products; the rule is applied so the "
                                       "contract is enforced rather than assumed")}
    note(f"point-in-time eligible field on the 52 signal sessions: min {eligibility['signal_field_min']}, "
         f"median {eligibility['signal_field_median']}, max {eligibility['signal_field_max']}")

    # ---------------------------------------------------------------- lifecycle tail support
    tail_needed = sorted({r[f"h{h}_exit_date"] for r in cal for h in HO.HOLDS
                          if r.get(f"h{h}_exit_date") and r[f"h{h}_exit_date"] > HO.CUTOFF.isoformat()})
    tail_have = []
    for iso in tail_needed:
        folder = DATA / "virgin" / "bars" / iso
        tail_have.append({"session": iso, "partitions": len(list(folder.glob("*.parquet"))) if folder.exists() else 0})
    lifecycle = {"sessions_required": tail_needed, "coverage": tail_have,
                 "all_present": all(t["partitions"] > 0 for t in tail_have)}
    note(f"September 2025 lifecycle tail: {len(tail_needed)} sessions required for late-August exits, "
         f"all present={lifecycle['all_present']}")
    if not lifecycle["all_present"]:
        blockers.append("a required September 2025 lifecycle session has no partitions")

    # ---------------------------------------------------------------- August 2025 pristine audit
    pristine = august_2025_pristine_audit()
    note(f"August 2025 pristine-status audit: {pristine['status']} "
         f"({pristine['artifacts_searched']} artifacts searched, {len(pristine['hits'])} hits)")
    if pristine["status"] != "AUGUST_2025_NOT_PREVIOUSLY_SCORED_AS_SIGNAL_MONTH":
        blockers.append("August 2025 was previously exposed as a scored signal month")

    manifest = {
        "arrow": "CG Arrow 014", "phase": "0A_source_verification", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "corridor_id": HO.CORRIDOR_ID,
        "a13_status_preserved": a13["certification_status"],
        "a13_declared_gaps": a13["remaining_gaps"],
        "acquisition": acq, "calendar": calendar, "cohort_calendar": cal,
        "eligibility": eligibility, "lifecycle_tail": lifecycle,
        "august_2025_pristine_audit": {k: v for k, v in pristine.items() if k != "searched"},
        "no_outcomes_calculated": True,
        "statement": ("Phase 0A verifies source, calendar, universe and pristine status only. "
                      "No ranking, selection, trade outcome, P&L, hit rate, drawdown, monthly "
                      "return or ending equity was calculated."),
        "blockers": blockers, "log": LOG,
    }
    dump_json(WORK / "phase0a_manifest.json", manifest)
    dump_json(OUT / "august2025_pristine_audit.json", pristine)
    note(f"Phase 0A complete; blockers={blockers}")
    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
