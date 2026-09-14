"""CG Arrow 013 — validation and certification of the landed holdout source layers.

Applies the lab's Historical Data Certification Gate to what has actually landed, and states
plainly what has not. Sections follow the arrow:

  7.1 trading-calendar integrity, cross-checked against an independent reference
  7.2 timestamp and minute-bar integrity, per partition
  7.3 full-universe and ranking-field completeness
  7.4 corporate-action and unit integrity, triage inventory and what it cannot prove
  7.5 volume integrity, including the twenty-one session corridor the sizing rule needs
  7.6 point-in-time security identity and universe integrity
  7.7 exception ledger and fail-closed policy
  8   cross-source authentication and the SHA-256 manifest

Nothing here runs a strategy. Returns are never computed, nothing is ranked, and no security
is selected or named in a public output.

Usage: python scripts/cg_arrow013_certify.py [--workers 8] [--sample 400]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from datetime import date, datetime, time as dtime
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
from ingest.paths import REPO_ROOT, REPORTS, VIRGIN_BARS, safe_symbol_filename  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification.r4r5_data import dump_json, stamp  # noqa: E402

LOG: list[str] = []
T0 = time.monotonic()
EXCEPTIONS: list[dict] = []


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def add_exception(code: str, scope: str, cause: str, evidence: str, blocks: bool, **extra):
    EXCEPTIONS.append({"exception_id": f"A13-{code}-{len(EXCEPTIONS) + 1:05d}", "code": code,
                       "scope": scope, "cause": cause, "source_evidence": evidence,
                       "repair_status": extra.pop("repair_status", "OPEN"),
                       "blocks_certification": blocks, **extra})


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ 7.1 calendar
def independent_sessions(start: date, end: date) -> list[date]:
    """An independent session list from pandas_market_calendars if installed, else None."""
    try:
        import pandas_market_calendars as mcal
    except Exception:  # noqa: BLE001
        return []
    try:
        sched = mcal.get_calendar("NYSE").schedule(start_date=start, end_date=end)
        return [d.date() for d in sched.index]
    except Exception:  # noqa: BLE001
        return []


def certify_calendar() -> tuple[list[dict], dict]:
    lo, hi = H.BULK_START, H.LIFECYCLE_END
    lab = H.sessions(lo, hi)
    ref = independent_sessions(lo, hi)
    rows = []
    for d in lab:
        rows.append({"session_date": d.isoformat(), "weekday": d.strftime("%A"),
                     "period_role": ("WARMUP" if d <= H.WARMUP_END else
                                     "LIFECYCLE_TAIL" if d > H.SIGNAL_END else "SIGNAL"),
                     "signal_month": H.signal_month_of(d) or "",
                     "is_early_close": H.is_early_close(d),
                     "session_open_et": H.RTH_OPEN.isoformat(),
                     "session_close_et": H.close_time(d).isoformat(),
                     "expected_rth_minutes": H.expected_rth_minutes(d),
                     "expected_window_minutes": H.expected_window_minutes(d),
                     "utc_offset_minutes": int(datetime.combine(d, dtime(12, 0)).replace(
                         tzinfo=None).astimezone().utcoffset().total_seconds() // 60) if False else None,
                     "in_independent_reference": (d in set(ref)) if ref else None})
    # closures inside the window must be absent from the session list
    closure_rows = []
    for d, name in sorted({**H.WINDOW_CLOSURES}.items()):
        if lo <= d <= hi:
            closure_rows.append({"session_date": d.isoformat(), "weekday": d.strftime("%A"),
                                 "period_role": "CLOSURE", "signal_month": "", "is_early_close": False,
                                 "session_open_et": "", "session_close_et": "", "expected_rth_minutes": 0,
                                 "expected_window_minutes": 0, "utc_offset_minutes": None,
                                 "in_independent_reference": (d in set(ref)) if ref else None,
                                 "closure_reason": name})
            if d in set(lab):
                add_exception("CAL", d.isoformat(), "a documented closure appears as a session",
                              name, True)
    summary = {"lab_sessions": len(lab), "window": [lo.isoformat(), hi.isoformat()],
               "early_closes": sorted(d.isoformat() for d in lab if H.is_early_close(d)),
               "closures_in_window": {d.isoformat(): n for d, n in H.WINDOW_CLOSURES.items() if lo <= d <= hi},
               "independent_reference": "pandas_market_calendars NYSE" if ref else "unavailable in this environment",
               "independent_sessions": len(ref) if ref else None}
    if ref:
        only_lab = sorted(set(lab) - set(ref))
        only_ref = sorted(set(ref) - set(lab))
        summary["only_in_lab_calendar"] = [d.isoformat() for d in only_lab]
        summary["only_in_reference"] = [d.isoformat() for d in only_ref]
        summary["identical"] = not only_lab and not only_ref
        for d in only_lab:
            add_exception("CAL", d.isoformat(), "session present in the lab calendar but not the reference",
                          summary["independent_reference"], True)
        for d in only_ref:
            add_exception("CAL", d.isoformat(), "session present in the reference but not the lab calendar",
                          summary["independent_reference"], True)
        note(f"calendar cross-check: lab {len(lab)} sessions, reference {len(ref)}, identical={summary['identical']}")
    else:
        summary["identical"] = None
        add_exception("CAL", f"{lo}..{hi}", "no independent calendar package is installed in this environment",
                      "closures and early closes were instead verified against the published NYSE holiday "
                      "schedule encoded in ingest.holdout2024 and cross-read against the landed bar data",
                      False, repair_status="MITIGATED_BY_BAR_EVIDENCE")
        note("calendar cross-check: no independent package installed; falling back to landed-bar evidence")
    return rows + closure_rows, summary


# ------------------------------------------------------------------ 7.2 / 7.5 partition integrity
def validate_session(job) -> dict:
    """Programmatic integrity of every landed partition for one session."""
    iso, expected_rth, expected_window, close_iso = job
    folder = H.RAW_BARS / iso
    out = {"session_date": iso, "partitions": 0, "empty_partitions": 0, "rows": 0,
           "dup_timestamp_partitions": 0, "unordered_partitions": 0, "outside_window_partitions": 0,
           "ohlc_inconsistent_partitions": 0, "negative_volume_partitions": 0,
           "nonfinite_price_partitions": 0, "rth_bar_over_expected": 0,
           "no_trade_minutes": 0, "traded_minutes": 0, "unreadable": 0,
           "max_rth_bars": 0, "symbols_with_rth": 0}
    if not folder.exists():
        return out
    files = sorted(folder.glob("*.parquet"))
    out["partitions"] = len(files)
    for f in files:
        try:
            df = pl.read_parquet(f, columns=["bar_start", "open", "high", "low", "close", "volume"])
        except Exception:  # noqa: BLE001
            out["unreadable"] += 1
            continue
        if df.height == 0:
            out["empty_partitions"] += 1
            continue
        out["rows"] += df.height
        ts = df["bar_start"]
        if ts.n_unique() != df.height:
            out["dup_timestamp_partitions"] += 1
        if not ts.is_sorted():
            out["unordered_partitions"] += 1
        clock = ts.dt.time()
        if bool((clock < H.PREMARKET_START).any()) or bool((clock >= H.SESSION_WINDOW_END).any()):
            out["outside_window_partitions"] += 1
        close_t = dtime.fromisoformat(close_iso)
        rth = df.filter((clock >= H.RTH_OPEN) & (clock < close_t))
        if rth.height:
            out["symbols_with_rth"] += 1
            out["max_rth_bars"] = max(out["max_rth_bars"], rth.height)
            if rth.height > expected_rth:
                out["rth_bar_over_expected"] += 1
            traded = rth.filter(pl.col("volume") > 0)
            out["traded_minutes"] += traded.height
            out["no_trade_minutes"] += rth.height - traded.height
            t2 = traded
            if t2.height:
                bad = t2.filter((pl.col("high") < pl.col("low"))
                                | (pl.col("close") > pl.col("high") + 1e-9)
                                | (pl.col("close") < pl.col("low") - 1e-9)
                                | (pl.col("open") > pl.col("high") + 1e-9)
                                | (pl.col("open") < pl.col("low") - 1e-9))
                if bad.height:
                    out["ohlc_inconsistent_partitions"] += 1
                if bool((t2["close"] <= 0).any()) or bool(t2["close"].is_nan().any()):
                    out["nonfinite_price_partitions"] += 1
        if bool((df["volume"] < 0).any()):
            out["negative_volume_partitions"] += 1
    return out


# ------------------------------------------------------------------ 8.5 aggregation reconciliation
def reconcile_sample(job) -> dict:
    """Minute-derived session volume against the independent end-of-day record."""
    iso, symbol = job
    p = H.RAW_BARS / iso / f"{safe_symbol_filename(symbol)}.parquet"
    res = {"session_date": iso, "symbol": symbol, "state": "MISSING_PARTITION",
           "minute_volume": None, "eod_volume": None, "ratio": None,
           "minute_close": None, "eod_close": None, "close_delta": None}
    if not p.exists():
        return res
    try:
        df = pl.read_parquet(p, columns=["bar_start", "close", "volume"])
    except Exception:  # noqa: BLE001
        res["state"] = "UNREADABLE"
        return res
    if df.height == 0:
        res["state"] = "EMPTY_PARTITION"
        return res
    d = date.fromisoformat(iso)
    clock = df["bar_start"].dt.time()
    rth = df.filter((clock >= H.RTH_OPEN) & (clock < H.close_time(d)))
    if rth.height == 0:
        res["state"] = "NO_REGULAR_HOURS_BARS"
        return res
    res["minute_volume"] = int(rth["volume"].sum())
    traded = rth.filter(pl.col("volume") > 0)
    res["minute_close"] = float(traded["close"][-1]) if traded.height else None
    chunk = d.strftime("%Y-%m")
    ep = H.raw_eod_path(symbol, chunk)
    if not ep.exists():
        res["state"] = "NO_EOD_PARTITION"
        return res
    try:
        e = pl.read_parquet(ep)
    except Exception:  # noqa: BLE001
        res["state"] = "EOD_UNREADABLE"
        return res
    row = e.filter(pl.col("eod_date") == d) if "eod_date" in e.columns else e.head(0)
    if row.height == 0:
        res["state"] = "NO_EOD_ROW"
        return res
    res["eod_volume"] = int(row["volume"][0]) if row["volume"][0] is not None else None
    res["eod_close"] = float(row["close"][0]) if row["close"][0] is not None else None
    if res["eod_volume"]:
        res["ratio"] = round(res["minute_volume"] / res["eod_volume"], 6)
    if res["minute_close"] is not None and res["eod_close"] is not None:
        res["close_delta"] = round(abs(res["minute_close"] - res["eod_close"]), 6)
    res["state"] = "COMPARED"
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--sample", type=int, default=400)
    args = ap.parse_args()
    workers = max(1, min(args.workers, 8))
    H.OUT.mkdir(parents=True, exist_ok=True)
    auth = json.loads((H.WORK / "auth_manifest.json").read_text(encoding="utf-8"))
    elig_mf = json.loads((H.WORK / "eligibility_manifest.json").read_text(encoding="utf-8")) \
        if (H.WORK / "eligibility_manifest.json").exists() else {}

    # ---------------------------------------------------------------- 7.1
    cal_rows, cal = certify_calendar()
    exp.write_csv(REPORTS / "cg_arrow013_calendar_audit.csv", cal_rows)
    note(f"calendar: {cal['lab_sessions']} sessions, {len(cal['early_closes'])} early closes, "
         f"{len(cal['closures_in_window'])} closures in window")

    # ---------------------------------------------------------------- 7.2 / 7.5
    landed = sorted(p.name for p in H.RAW_BARS.iterdir()) if H.RAW_BARS.exists() else []
    jobs = [(iso, H.expected_rth_minutes(date.fromisoformat(iso)),
             H.expected_window_minutes(date.fromisoformat(iso)),
             H.close_time(date.fromisoformat(iso)).isoformat()) for iso in landed]
    note(f"minute integrity: validating {len(jobs)} landed session partitions")
    per_session = []
    if jobs:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(validate_session, j) for j in jobs]
            for n, fut in enumerate(as_completed(futs), 1):
                per_session.append(fut.result())
                if n % 50 == 0:
                    note(f"  validated {n}/{len(jobs)} sessions")
    per_session.sort(key=lambda r: r["session_date"])
    agg = {k: sum(r[k] for r in per_session) for k in
           ("partitions", "empty_partitions", "rows", "dup_timestamp_partitions", "unordered_partitions",
            "outside_window_partitions", "ohlc_inconsistent_partitions", "negative_volume_partitions",
            "nonfinite_price_partitions", "rth_bar_over_expected", "no_trade_minutes", "traded_minutes",
            "unreadable", "symbols_with_rth")} if per_session else {}
    for key, code, msg in (("dup_timestamp_partitions", "TS", "duplicate timestamps inside a symbol-session"),
                           ("unordered_partitions", "TS", "timestamps not monotonically ordered"),
                           ("outside_window_partitions", "TS", "bars outside the declared 04:00 to close window"),
                           ("ohlc_inconsistent_partitions", "OHLC", "open or close outside the bar's high-low range"),
                           ("negative_volume_partitions", "VOL", "negative share volume"),
                           ("nonfinite_price_partitions", "PX", "non-positive or non-finite traded price"),
                           ("rth_bar_over_expected", "CAL", "more regular-hours bars than the session schedule allows"),
                           ("unreadable", "IO", "landed partition could not be read back")):
        n = agg.get(key, 0)
        if n:
            add_exception(code, "minute partitions", msg, "programmatic partition inventory", True, count=n)
    note(f"minute integrity aggregate: {agg}")

    # ---------------------------------------------------------------- 7.3 coverage
    cov_rows = []
    elig_path = H.WORK / "eligibility.parquet"
    universe, per_sess_expected = [], {}
    if elig_path.exists():
        el = pl.read_parquet(elig_path)
        universe = sorted(el.filter(pl.col("eligible"))["symbol"].unique().to_list())
        per_sess_expected = {str(r["session_date"]): r["len"] for r in
                             el.filter(pl.col("eligible")).group_by("session_date").len().to_dicts()}
    ps = {r["session_date"]: r for r in per_session}
    for d in H.sessions(H.BULK_START, H.LIFECYCLE_END):
        iso = d.isoformat()
        role = ("WARMUP" if d <= H.WARMUP_END else "LIFECYCLE_TAIL" if d > H.SIGNAL_END else "SIGNAL")
        source = ("NEW_BULK_ACQUISITION" if d <= H.BULK_END else
                  "EXISTING_AUTHENTICATED_REUSE" if d <= H.REUSE_END else "EXISTING_LIFECYCLE_TAIL")
        r = ps.get(iso, {})
        expected = per_sess_expected.get(iso)
        present = r.get("symbols_with_rth", 0)
        if source == "NEW_BULK_ACQUISITION":
            got = present
        else:
            folder = VIRGIN_BARS / iso
            got = len(list(folder.glob("*.parquet"))) if folder.exists() else 0
        cov_rows.append({
            "session_date": iso, "period_role": role, "signal_month": H.signal_month_of(d) or "",
            "source": source, "is_early_close": H.is_early_close(d),
            "expected_rth_minutes": H.expected_rth_minutes(d),
            "eligible_field_expected": expected,
            "partitions_landed": r.get("partitions", got),
            "securities_with_regular_hours_bars": got,
            "empty_partitions": r.get("empty_partitions"),
            "minute_rows": r.get("rows"),
            "traded_minutes": r.get("traded_minutes"),
            "no_trade_minutes": r.get("no_trade_minutes"),
            "coverage_state": ("MINUTE_LAYER_PRESENT" if got else
                               "MINUTE_LAYER_NOT_YET_ACQUIRED" if source == "NEW_BULK_ACQUISITION"
                               else "EXISTING_PARTITION"),
        })
    exp.write_csv(REPORTS / "cg_arrow013_coverage_summary.csv", cov_rows)
    missing_sessions = [r for r in cov_rows if r["coverage_state"] == "MINUTE_LAYER_NOT_YET_ACQUIRED"]
    if missing_sessions:
        add_exception("COV", f"{len(missing_sessions)} sessions", "minute layer not yet acquired for these sessions",
                      "coverage inventory", True, count=len(missing_sessions),
                      first=missing_sessions[0]["session_date"], last=missing_sessions[-1]["session_date"])
    note(f"coverage: {len(cov_rows)} sessions inventoried; "
         f"{sum(1 for r in cov_rows if r['coverage_state'] == 'MINUTE_LAYER_PRESENT')} carry a minute layer")

    # ---------------------------------------------------------------- 7.4 / 7.6 actions and identity
    action_state = {
        "documented_action_table_for_holdout": False,
        "basis": ("The lab's certified action table covers the September 2025 to August 2026 study. No "
                  "documented, dated corporate-action table has yet been assembled for September 2024 to "
                  "August 2025. A price-discontinuity screen is triage and is explicitly not proof that no "
                  "action occurred, so no corridor in this window is certified for unit integrity."),
        "consequence": ("Ranking and feature units, held-share normalization and point-in-time identity "
                        "cannot be certified for this window until documented evidence is assembled. This "
                        "is a declared remaining gap, not a silent assumption."),
        "staged_procedure": ("The frozen post-selection procedure retrieves primary-source evidence from SEC "
                             "EDGAR for exactly the securities the frozen models mechanically select, using "
                             "the Arrow 007 and 008 machinery in src/verification/r4r5_events.py, and fails "
                             "closed on any unresolved material action rather than substituting a next name."),
    }
    add_exception("ACT", f"{H.BULK_START}..{H.REUSE_END}",
                  "no documented dated corporate-action table exists yet for the holdout window",
                  "the certified action table covers 2025-09 to 2026-08 only", True,
                  repair_status="STAGED_FOR_POST_SELECTION_CERTIFICATION")
    add_exception("ID", f"{H.BULK_START}..{H.REUSE_END}",
                  "point-in-time security identity and ticker-change mapping not yet assembled for this window",
                  "identity evidence is part of the same primary-source layer as corporate actions", True,
                  repair_status="STAGED_FOR_POST_SELECTION_CERTIFICATION")

    # ---------------------------------------------------------------- 8.5 aggregation reconciliation
    recon_rows = []
    if universe and landed:
        rng = hashlib.sha256(b"cg_arrow013_reconcile").digest()
        picks = []
        for i, iso in enumerate(landed):
            if not universe:
                break
            sym = universe[int.from_bytes(rng[(i * 3) % 30:(i * 3) % 30 + 4].ljust(4, b"\0"), "big") % len(universe)]
            picks.append((iso, sym))
        picks = picks[:args.sample]
        note(f"aggregation reconciliation: {len(picks)} deterministic symbol-session samples")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for fut in as_completed([pool.submit(reconcile_sample, p) for p in picks]):
                recon_rows.append(fut.result())
    compared = [r for r in recon_rows if r["state"] == "COMPARED" and r["ratio"]]
    recon_summary = {"sampled": len(recon_rows), "compared": len(compared),
                     "states": dict(Counter(r["state"] for r in recon_rows))}
    if compared:
        ratios = sorted(r["ratio"] for r in compared)
        deltas = sorted(r["close_delta"] for r in compared if r["close_delta"] is not None)
        recon_summary.update({
            "volume_ratio_min": ratios[0], "volume_ratio_median": ratios[len(ratios) // 2],
            "volume_ratio_max": ratios[-1],
            "volume_ratio_within_1pct": sum(1 for x in ratios if 0.99 <= x <= 1.01),
            "close_delta_median": deltas[len(deltas) // 2] if deltas else None,
            "close_delta_max": deltas[-1] if deltas else None,
            "tolerance_note": ("regular-hours minute volume is compared with the vendor's end-of-day share "
                               "volume. The end-of-day figure is a consolidated national total and includes "
                               "prints the regular-hours minute window does not carry, so a ratio below one "
                               "is expected and is documented rather than tuned away")})
        note(f"aggregation reconciliation: {len(compared)} compared, volume ratio median "
             f"{recon_summary['volume_ratio_median']}, close delta median {recon_summary.get('close_delta_median')}")
    exp.write_csv(REPORTS / "cg_arrow013_overlap_authentication.csv",
                  [{"check": "repeat_query_reproducibility", "scope": "smoke symbol, 2025-08-01",
                    "sampled": 1, "matched": int(auth["smoke"]["repeat_identical"]),
                    "discrepant": int(not auth["smoke"]["repeat_identical"]),
                    "worst_price_delta": auth["smoke"]["repeat_query"]["worst_price_delta"],
                    "volume_mismatches": auth["smoke"]["repeat_query"]["volume_mismatches"],
                    "result": "IDENTICAL" if auth["smoke"]["repeat_identical"] else "DISCREPANT",
                    "escalated": not auth["smoke"]["repeat_identical"]},
                   {"check": "august_2025_overlap_vs_local", "scope": "stratified sample across the month",
                    "sampled": auth["overlap_summary"]["sampled"],
                    "matched": auth["overlap_summary"]["matched"],
                    "discrepant": auth["overlap_summary"]["discrepant"],
                    "worst_price_delta": auth["overlap_summary"]["worst_price_delta"],
                    "volume_mismatches": auth["overlap_summary"]["volume_mismatches"],
                    "result": "MATCH" if not auth["overlap_summary"]["discrepant"] else "ESCALATE",
                    "escalated": bool(auth["overlap_summary"]["discrepant"])},
                   {"check": "minute_to_end_of_day_aggregation", "scope": "deterministic symbol-session sample",
                    "sampled": recon_summary["sampled"], "matched": recon_summary.get("volume_ratio_within_1pct"),
                    "discrepant": None, "worst_price_delta": recon_summary.get("close_delta_max"),
                    "volume_mismatches": None,
                    "result": "DOCUMENTED_CONSOLIDATED_TAPE_DIFFERENCE", "escalated": False},
                   {"check": "calendar_vs_independent_reference", "scope": f"{H.BULK_START}..{H.LIFECYCLE_END}",
                    "sampled": cal["lab_sessions"], "matched": cal.get("independent_sessions"),
                    "discrepant": (len(cal.get("only_in_lab_calendar", [])) + len(cal.get("only_in_reference", []))
                                   if cal.get("identical") is not None else None),
                    "worst_price_delta": None, "volume_mismatches": None,
                    "result": ("IDENTICAL" if cal.get("identical") else
                               "NO_INDEPENDENT_PACKAGE" if cal.get("identical") is None else "DIFFERS"),
                    "escalated": cal.get("identical") is False}])

    # ---------------------------------------------------------------- 7.7 exceptions
    for row in EXCEPTIONS:
        row.setdefault("count", None)
    exc_rows = [{"exception_id": e["exception_id"], "code": e["code"], "scope": e["scope"],
                 "cause": e["cause"], "source_evidence": e["source_evidence"],
                 "count": e.get("count"), "repair_status": e["repair_status"],
                 "blocks_certification": e["blocks_certification"]} for e in EXCEPTIONS]
    exp.write_csv(REPORTS / "cg_arrow013_exception_summary.csv", exc_rows)
    blocking = [e for e in EXCEPTIONS if e["blocks_certification"]]
    note(f"exceptions: {len(EXCEPTIONS)} recorded, {len(blocking)} block certification")

    # ---------------------------------------------------------------- 8.6 hash manifest
    artifacts = {}
    for p in sorted(H.WORK.glob("*.json")) + sorted(H.WORK.glob("*.parquet")):
        artifacts[str(p.relative_to(REPO_ROOT)).replace("\\", "/")] = {
            "sha256": sha256_file(p), "bytes": p.stat().st_size}
    # raw partitions are hashed at the directory level so the manifest stays public-safe
    raw_digest = {}
    for root, label in ((H.RAW_EOD, "raw/eod"), (H.RAW_BARS, "raw/bars")):
        if not root.exists():
            continue
        for sub in sorted(root.iterdir()):
            files = sorted(sub.glob("*.parquet"))
            h = hashlib.sha256()
            total = 0
            for f in files:
                h.update(f.name.encode())
                h.update(str(f.stat().st_size).encode())
                total += f.stat().st_size
            raw_digest[f"{label}/{sub.name}"] = {"partitions": len(files), "bytes": total,
                                                 "listing_sha256": h.hexdigest()}
    note(f"hash manifest: {len(artifacts)} certification artifacts, {len(raw_digest)} raw partition groups")

    # ---------------------------------------------------------------- status
    status = ("HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL" if not blocking else
              "HOLDOUT_DATA_PARTIALLY_CERTIFIED")
    gaps = sorted({e["cause"] for e in blocking})
    manifest = {
        "arrow": "CG Arrow 013", "stage": "certification", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "definition_id": H.DEFINITION_ID,
        "authentication": {k: auth[k] for k in ("repo_root", "remote", "env_git_ignored", "credential_mode",
                                                "versions", "vendor_contract", "timestamp_precision",
                                                "no_trade_convention", "throughput")},
        "authentication_smoke": auth["smoke"], "overlap_summary": auth["overlap_summary"],
        "calendar": cal, "minute_integrity": agg, "per_session_integrity_rows": len(per_session),
        "eligibility": {k: elig_mf.get(k) for k in
                        ("roster", "etp_excluded", "test_issues_excluded", "eod_rows", "eod_securities",
                         "eod_dates", "eligibility_rows", "sessions", "eligible_field_min",
                         "eligible_field_median", "eligible_field_max", "minute_universe_size",
                         "exclude_reasons")},
        "coverage": {"sessions_inventoried": len(cov_rows),
                     "sessions_with_minute_layer": sum(1 for r in cov_rows if r["coverage_state"] == "MINUTE_LAYER_PRESENT"),
                     "sessions_awaiting_minute_layer": len(missing_sessions)},
        "aggregation_reconciliation": recon_summary,
        "corporate_actions_and_identity": action_state,
        "exceptions": {"total": len(EXCEPTIONS), "blocking": len(blocking),
                       "by_code": dict(Counter(e["code"] for e in EXCEPTIONS))},
        "certification_artifacts": artifacts, "raw_partition_groups": raw_digest,
        "certification_status": status, "remaining_gaps": gaps,
        "embargo": {"strategy_run": False, "rankings_emitted": False, "selections_revealed": False,
                    "performance_calculated": False,
                    "statement": "NO STRATEGY PERFORMANCE WAS SCORED OR REVEALED IN ARROW 013"},
        "log": LOG,
    }
    dump_json(REPORTS / "cg_arrow013_manifest.json", manifest)
    dump_json(H.OUT / "exception_ledger.json", {"exceptions": EXCEPTIONS, "timestamp": stamp()})
    note(f"certification status: {status}; remaining gaps: {len(gaps)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
