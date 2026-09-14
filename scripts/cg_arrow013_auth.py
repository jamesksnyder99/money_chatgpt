"""CG Arrow 013 — authentication and source-provenance gate, run before any bulk retrieval.

Proves, without exposing any credential value, that:

  * the repository root and remote are the intended lab;
  * the credential file is git-ignored;
  * the official ThetaData SDK authenticates under the existing Stocks Professional entitlement;
  * the returned schema, timezone and timestamps are what the lab's contract expects;
  * an identical repeated query returns semantically identical observations;
  * a silent empty-success response is recognised as a failure, not as data;
  * a deterministic stratified August 2025 sample reproduces the already-held local partitions
    field for field, which is the overlap authentication the reuse boundary requires.

It also measures end-of-day and minute throughput so the acquisition plan rests on a measured
rate rather than a guess. No strategy, ranking or selection is computed anywhere in this file.

Usage: python scripts/cg_arrow013_auth.py [--workers 8]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dtime
import hashlib
import importlib.metadata as md
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS, VIRGIN_BARS, safe_symbol_filename  # noqa: E402
from ingest.theta_pool import ThetaLimiter, call_theta  # noqa: E402
from verification.r4r5_data import dump_json, stamp  # noqa: E402

OUT = H.OUT
WORK = H.WORK
MAX_CONCURRENCY = 8
LOG: list[str] = []
T0 = time.monotonic()


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def versions() -> dict:
    out = {"python": platform.python_version(), "platform": platform.platform()}
    for pkg in ("thetadata", "polars", "pyarrow"):
        try:
            out[pkg] = md.version(pkg)
        except Exception:  # noqa: BLE001
            out[pkg] = "unavailable"
    return out


def overlap_sample() -> list[tuple[date, str]]:
    """Deterministic stratified August 2025 sample: early, mid and late month, across liquidity.

    Symbols are chosen by a stable hash of the symbol name over the securities that actually
    have a local August 2025 partition, so the sample is reproducible and carries no strategy
    meaning. Liquidity strata come from file size, which is a proxy for bar count and is
    independent of any return or ranking.
    """
    aug = [d for d in H.sessions(date(2025, 8, 1), date(2025, 8, 31))]
    picks = [aug[1], aug[len(aug) // 2], aug[-2], aug[-1]]
    out = []
    for d in picks:
        folder = VIRGIN_BARS / d.isoformat()
        if not folder.exists():
            continue
        files = sorted(folder.glob("*.parquet"), key=lambda p: p.stat().st_size)
        if not files:
            continue
        n = len(files)
        # three liquidity strata by partition size, then a stable hash pick inside each
        for lo, hi in ((0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n)):
            band = files[lo:hi] or files
            idx = int(hashlib.sha256(f"{d}:{lo}".encode()).hexdigest(), 16) % len(band)
            out.append((d, band[idx].stem))
    return out


def fetch_minutes(client, limiter, symbol: str, d: date):
    """One session of one-minute bars, normalized through the lab's own contract.

    The vendor returns a `timestamp` column already in America/New_York. The lab's normalizer
    renames it to `bar_start` and applies the 04:00 to 16:00 window, so comparing a fresh pull
    against a landed partition compares like with like rather than raw against normalized.
    """
    from ingest.bars import normalize_ohlc_full
    df, elapsed = call_theta(
        limiter, client.stock_history_ohlc, symbol=symbol, start_date=d, end_date=d,
        interval=H.INTERVAL, venue=H.VENUE, start_time=H.PREMARKET_START, end_time=H.SESSION_WINDOW_END)
    return normalize_ohlc_full(df, symbol, False), elapsed


def compare_frames(local: pl.DataFrame, fresh: pl.DataFrame) -> dict:
    """Field-for-field comparison on the shared regular-hours window.

    Integer volume and timestamps must match exactly; prices must match to the vendor's
    declared precision. A difference in either is a discrepancy, never a tolerance.
    """
    keys = ["bar_start", "open", "high", "low", "close", "volume"]
    # The vendor delivers millisecond-precision New York timestamps; the landed partitions hold
    # microseconds. Both are cast to one explicit unit so the comparison is like for like. This
    # is a unit alignment, never a tolerance: after the cast the instants must be identical.
    unit = pl.Datetime("us", "America/New_York")
    a = local.select([c for c in keys if c in local.columns]).with_columns(
        pl.col("bar_start").cast(unit)).sort("bar_start")
    b = fresh.select([c for c in keys if c in fresh.columns]).with_columns(
        pl.col("bar_start").cast(unit)).sort("bar_start")
    ta = set(a["bar_start"].to_list()) if "bar_start" in a.columns else set()
    tb = set(b["bar_start"].to_list()) if "bar_start" in b.columns else set()
    shared = ta & tb
    res = {"local_rows": a.height, "fresh_rows": b.height,
           "timestamps_only_local": len(ta - tb), "timestamps_only_fresh": len(tb - ta),
           "shared_timestamps": len(shared), "field_mismatches": 0, "worst_price_delta": 0.0,
           "volume_mismatches": 0, "mismatch_examples": []}
    if not shared:
        return res
    aj = a.filter(pl.col("bar_start").is_in(list(shared))).sort("bar_start")
    bj = b.filter(pl.col("bar_start").is_in(list(shared))).sort("bar_start")
    # A minute in which the security did not trade comes back with NaN prices and zero volume.
    # That is a real vendor state, distinct from a missing bar and from a halt, and NaN on both
    # sides is a match. Comparing NaN with the ordinary > operator would call every no-trade
    # minute a discrepancy, so the two sides are compared as "both absent or equal".
    nan_both = {}
    for col in ("open", "high", "low", "close"):
        if col in aj.columns and col in bj.columns:
            x, y = aj[col], bj[col]
            both_absent = (x.is_nan() | x.is_null()) & (y.is_nan() | y.is_null())
            one_absent = ((x.is_nan() | x.is_null()) != (y.is_nan() | y.is_null()))
            delta = (x - y).abs()
            differs = (~both_absent) & (~one_absent) & (delta > 1e-9)
            bad = int(differs.sum()) + int(one_absent.sum())
            finite = delta.filter(~(x.is_nan() | x.is_null() | y.is_nan() | y.is_null()))
            res["worst_price_delta"] = max(res["worst_price_delta"],
                                           float(finite.max() or 0.0) if finite.len() else 0.0)
            res["field_mismatches"] += bad
            nan_both[col] = int(both_absent.sum())
            if bad and len(res["mismatch_examples"]) < 3:
                res["mismatch_examples"].append(f"{col}: {bad} bars differ")
    res["no_trade_minutes_both_sides"] = max(nan_both.values()) if nan_both else 0
    if "volume" in aj.columns and "volume" in bj.columns:
        bad = int((aj["volume"] != bj["volume"]).sum())
        res["volume_mismatches"] = bad
        res["field_mismatches"] += bad
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    workers = max(1, min(args.workers, MAX_CONCURRENCY))
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []

    # ---------------------------------------------------------------- 1-3 workspace and secrets
    remote = subprocess.check_output(["git", "remote", "get-url", "origin"], cwd=REPO_ROOT).decode().strip()
    ignored = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=REPO_ROOT).returncode == 0
    env_present = (REPO_ROOT / ".env").exists()
    note(f"repo root {REPO_ROOT}; remote {remote}; .env present={env_present} git-ignored={ignored}")
    if not remote.endswith("money_chatgpt.git") and "money_chatgpt" not in remote:
        blockers.append(f"unexpected remote {remote}")
    if not ignored:
        blockers.append(".env is not git-ignored")
    if not env_present:
        blockers.append(".env is absent; no authorized credentials available")
    v = versions()
    note(f"versions {v}")
    if blockers:
        dump_json(WORK / "auth_manifest.json", {"blockers": blockers, "log": LOG})
        note("STOPPED before any vendor call: " + "; ".join(blockers))
        return 1

    # ---------------------------------------------------------------- 4-6 authenticated smoke
    from theta.client import auth_mode, get_shared_client
    mode = auth_mode()          # returns the mode name only, never a value
    note(f"credential mode resolved: {mode} (no value is read, printed, logged or stored)")
    client = get_shared_client()
    limiter = ThetaLimiter(workers)
    known_day = date(2025, 8, 1)
    probe = sorted(p.stem for p in (VIRGIN_BARS / known_day.isoformat()).glob("*.parquet"))
    if not probe:
        blockers.append("no local August 2025 partition to authenticate against")
        dump_json(WORK / "auth_manifest.json", {"blockers": blockers, "log": LOG})
        return 1
    smoke_symbol = probe[int(hashlib.sha256(b"cg_arrow013_smoke").hexdigest(), 16) % len(probe)]
    df1, e1 = fetch_minutes(client, limiter, smoke_symbol, known_day)
    df2, e2 = fetch_minutes(client, limiter, smoke_symbol, known_day)
    schema = {c: str(t) for c, t in zip(df1.columns, df1.dtypes)}
    tzinfo = str(df1["bar_start"].dtype) if "bar_start" in df1.columns else None
    note(f"smoke query returned {df1.height} rows, schema fields {len(schema)}, bar_start dtype {tzinfo}")
    smoke = {
        "session": known_day.isoformat(), "endpoint": "stock_history_ohlc",
        "interval": H.INTERVAL, "venue": H.VENUE,
        "window": f"{H.PREMARKET_START}-{H.SESSION_WINDOW_END} America/New_York",
        "rows_first": df1.height, "rows_repeat": df2.height,
        "schema": schema, "bar_start_dtype": tzinfo,
        "elapsed_first_s": round(e1, 3), "elapsed_repeat_s": round(e2, 3),
        "empty_success_is_failure": True,
    }
    if df1.height == 0:
        blockers.append("the authenticated smoke query returned an empty success, which is a failure not data")
    repeat = compare_frames(df1, df2)
    smoke["repeat_query"] = repeat
    smoke["repeat_identical"] = (repeat["field_mismatches"] == 0
                                 and repeat["timestamps_only_local"] == 0
                                 and repeat["timestamps_only_fresh"] == 0)
    note(f"repeat-query reproducibility identical={smoke['repeat_identical']} "
         f"(shared {repeat['shared_timestamps']} timestamps, {repeat['field_mismatches']} field mismatches)")
    if not smoke["repeat_identical"]:
        blockers.append("an identical repeated query did not return semantically identical observations")
    # timestamps must sit inside the declared window and be unique and ordered
    if "bar_start" in df1.columns and df1.height:
        ts = df1["bar_start"].to_list()
        clock = [t.time() for t in ts]
        smoke["timestamps_unique"] = len(set(ts)) == len(ts)
        smoke["timestamps_monotonic"] = ts == sorted(ts)
        smoke["timestamps_inside_window"] = all(H.PREMARKET_START <= c < H.SESSION_WINDOW_END for c in clock)
        smoke["first_ts"] = str(ts[0])
        smoke["last_ts"] = str(ts[-1])
        for k in ("timestamps_unique", "timestamps_monotonic", "timestamps_inside_window"):
            if not smoke[k]:
                blockers.append(f"smoke query failed {k}")
        note(f"smoke timestamps unique={smoke['timestamps_unique']} monotonic={smoke['timestamps_monotonic']} "
             f"inside window={smoke['timestamps_inside_window']} first={smoke['first_ts']} last={smoke['last_ts']}")

    # ---------------------------------------------------------------- overlap authentication
    sample = overlap_sample()
    note(f"August 2025 overlap sample: {len(sample)} stratified symbol-sessions")
    rows, worst = [], {"field_mismatches": 0}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(fetch_minutes, client, limiter, s, d): (d, s) for d, s in sample}
        for fut in as_completed(futs):
            d, s = futs[fut]
            try:
                fresh, el = fut.result()
            except Exception as exc:  # noqa: BLE001
                rows.append({"session": d.isoformat(), "symbol_hash": hashlib.sha256(s.encode()).hexdigest()[:12],
                             "status": "VENDOR_ERROR", "error_class": type(exc).__name__,
                             "local_rows": None, "fresh_rows": None, "shared_timestamps": None,
                             "field_mismatches": None, "volume_mismatches": None, "worst_price_delta": None,
                             "escalated": True})
                blockers.append(f"overlap re-query failed for a sampled August 2025 session ({type(exc).__name__})")
                continue
            local_path = VIRGIN_BARS / d.isoformat() / f"{safe_symbol_filename(s)}.parquet"
            local = pl.read_parquet(local_path)
            cmp = compare_frames(local, fresh)
            bad = cmp["field_mismatches"] or cmp["timestamps_only_local"] or cmp["timestamps_only_fresh"]
            rows.append({"session": d.isoformat(),
                         "symbol_hash": hashlib.sha256(s.encode()).hexdigest()[:12],
                         "status": "MATCH" if not bad else "DISCREPANCY",
                         "error_class": None,
                         "local_rows": cmp["local_rows"], "fresh_rows": cmp["fresh_rows"],
                         "shared_timestamps": cmp["shared_timestamps"],
                         "timestamps_only_local": cmp["timestamps_only_local"],
                         "timestamps_only_fresh": cmp["timestamps_only_fresh"],
                         "field_mismatches": cmp["field_mismatches"],
                         "volume_mismatches": cmp["volume_mismatches"],
                         "worst_price_delta": cmp["worst_price_delta"],
                         "no_trade_minutes": cmp.get("no_trade_minutes_both_sides"),
                         "escalated": bool(bad),
                         "elapsed_s": round(el, 3)})
            if cmp["field_mismatches"] > worst["field_mismatches"]:
                worst = cmp
    matched = sum(1 for r in rows if r["status"] == "MATCH")
    discrepant = [r for r in rows if r["status"] != "MATCH"]
    note(f"overlap authentication: {matched}/{len(rows)} sampled symbol-sessions match the local partition "
         f"field for field; {len(discrepant)} require escalation")
    if discrepant:
        blockers.append(f"{len(discrepant)} August 2025 overlap discrepancies require full re-retrieval "
                        "into an audit partition before the block may be reused")

    # ---------------------------------------------------------------- throughput measurement
    thr = {}
    probe_syms = probe[:24]
    t = time.monotonic()
    ok = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(fetch_minutes, client, limiter, s, known_day) for s in probe_syms]
        for fut in as_completed(futs):
            try:
                fut.result()
                ok += 1
            except Exception:  # noqa: BLE001
                pass
    el = time.monotonic() - t
    thr["minute_requests_per_second"] = round(ok / el, 3) if el else None
    thr["minute_sample"] = {"requests": ok, "seconds": round(el, 2), "workers": workers}
    note(f"minute throughput: {ok} requests in {el:.1f}s = {thr['minute_requests_per_second']} req/s at {workers} workers")

    eod_syms = probe[:24]
    t = time.monotonic()
    ok2, eod_rows = 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(call_theta, limiter, client.stock_history_eod, symbol=s,
                            start_date=date(2025, 8, 1), end_date=date(2025, 8, 31)) for s in eod_syms]
        for fut in as_completed(futs):
            try:
                df, _ = fut.result()
                ok2 += 1
                eod_rows += df.height
            except Exception:  # noqa: BLE001
                pass
    el2 = time.monotonic() - t
    thr["eod_requests_per_second"] = round(ok2 / el2, 3) if el2 else None
    thr["eod_sample"] = {"requests": ok2, "seconds": round(el2, 2), "rows": eod_rows, "workers": workers}
    note(f"end-of-day throughput: {ok2} requests in {el2:.1f}s = {thr['eod_requests_per_second']} req/s")

    manifest = {
        "arrow": "CG Arrow 013", "stage": "authentication_gate", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "repo_root": str(REPO_ROOT), "remote": remote,
        "env_file_present": env_present, "env_git_ignored": ignored,
        "credential_mode": mode,
        "credential_handling": ("resolved by name only through theta.client; no value is printed, logged, "
                                "serialized, staged or committed anywhere in this arrow"),
        "versions": v,
        "no_trade_convention": {"vendor": "a minute with no trade returns NaN open/high/low/close with volume 0",
                                "handling": ("NaN on both sides is a match; NaN on one side only is a "
                                             "discrepancy. A no-trade minute is not a missing bar and is "
                                             "not a halt, and none of the three is silently merged")},
        "timestamp_precision": {"vendor": "milliseconds, America/New_York",
                                "landed": "microseconds, America/New_York",
                                "handling": "cast to one explicit unit before comparison; instants must then "
                                            "be identical, which is a unit alignment and not a tolerance"},
        "vendor_contract": {"sdk": "official installed ThetaData Python SDK",
                            "entitlement": "existing authorized Stocks Professional",
                            "endpoints": ["stock_history_ohlc", "stock_history_eod"],
                            "interval": H.INTERVAL, "venue": H.VENUE,
                            "window": "04:00-16:00 America/New_York, session close honoured on early closes",
                            "terminal_launched": False, "subscription_changed": False,
                            "options_used": False, "sub_minute_used": False,
                            "max_concurrency": MAX_CONCURRENCY, "workers_used": workers},
        "smoke": smoke, "overlap_rows": rows,
        "overlap_summary": {"sampled": len(rows), "matched": matched, "discrepant": len(discrepant),
                            "worst_price_delta": max((r["worst_price_delta"] or 0) for r in rows) if rows else None,
                            "volume_mismatches": sum((r["volume_mismatches"] or 0) for r in rows)},
        "throughput": thr, "blockers": blockers, "log": LOG,
    }
    dump_json(WORK / "auth_manifest.json", manifest)
    note(f"authentication gate {'PASSED' if not blockers else 'FAILED'}; blockers={blockers}")
    return 0 if not blockers else 1


if __name__ == "__main__":
    sys.exit(main())
