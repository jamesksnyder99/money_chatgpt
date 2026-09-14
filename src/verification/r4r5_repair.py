"""Arrow 006 acquisition repair pipeline: raw -> validated -> cache -> replay.

Authenticated request (official SDK, venue/window identical to the original ingest)
-> immutable raw parquet under data/verification/r4r5/v1/acquisition/raw
-> normalize/validate -> per-session parquet under data/verification/r4r5/v1/validated
-> summary cache invalidation -> replay consumption through the existing loader
precedence in r4r5_data.candidate_paths.

Credentials are read by src/theta/client.py from the ignored repo-root .env. No
credential value is ever printed, logged or stored here. A zero-row response is
never coverage: it is recorded as EMPTY_RESPONSE_UNRESOLVED and left unresolved.
"""
from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, time as dtime
import json
import time

import polars as pl

from ingest.bars import normalize_ohlc_full, split_sessions
from ingest.paths import REPO_ROOT, safe_symbol_filename
from ingest.theta_pool import ThetaLimiter, call_theta
from verification.r4r5_data import (
    FEATS, INDEX, VALIDATED, VERIFY_ROOT, close_time, dump_json, stamp,
)

RAW = VERIFY_ROOT / "acquisition" / "raw"
LOG = VERIFY_ROOT / "acquisition" / "requests.jsonl"
COVERAGE = VERIFY_ROOT / "acquisition" / "coverage.json"

# Identical to the original lab ingest so repaired bars are interchangeable.
VENUE = "utp_cta"
INTERVAL = "1m"
START_TIME = dtime(4, 0)
END_TIME = dtime(16, 0)
ENDPOINT = "stock_history_ohlc"
CONCURRENCY = 8

SESSION_SET = set(FEATS)


# ------------------------------------------------------------------ request planning
def month_chunks(sessions: set[date]) -> list[tuple[date, date]]:
    """Vendor bulk history is capped at one month; chunk required sessions by month."""
    by: dict[tuple[int, int], list[date]] = defaultdict(list)
    for d in sessions:
        by[(d.year, d.month)].append(d)
    return [(min(v), max(v)) for _, v in sorted(by.items())]


def plan_requests(needed: dict[str, set[date]]) -> list[dict]:
    """needed: symbol -> required trading sessions. Returns one row per vendor request."""
    out = []
    for sym in sorted(needed):
        days = {d for d in needed[sym] if d in SESSION_SET}
        for start, end in month_chunks(days):
            out.append({"symbol": sym, "start": start.isoformat(), "end": end.isoformat(),
                        "sessions": sorted(d.isoformat() for d in days if start <= d <= end)})
    return out


def logged_requests() -> dict[tuple[str, str, str], dict]:
    done = {}
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            done[(r["symbol"], r["start"], r["end"])] = r
    return done


def _log(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


# ------------------------------------------------------------------ validation
def validate_session(df: pl.DataFrame, d: date, symbol: str) -> dict:
    """Structural checks on one session. Sparse trading is legitimate, not a defect."""
    issues = []
    if df.height == 0:
        return {"status": "EMPTY_RESPONSE_UNRESOLVED", "rows": 0, "traded_bars": 0, "issues": ["no rows"]}
    if not df["bar_start"].is_sorted():
        df = df.sort("bar_start")
    dupes = df.height - df["bar_start"].n_unique()
    if dupes:
        issues.append(f"duplicate_timestamps={dupes}")
    dates = df["bar_start"].dt.date().unique().to_list()
    if dates != [d]:
        issues.append(f"session_date_mismatch={dates}")
    clock = pl.col("bar_start").dt.time()
    traded = df.filter((clock >= dtime(9, 30)) & (clock < close_time(d)) & (pl.col("volume") > 0)
                       & pl.col("open").is_finite() & pl.col("close").is_finite()
                       & (pl.col("open") > 0) & (pl.col("close") > 0))
    neg = int(df.filter(pl.col("volume") < 0).height)
    if neg:
        issues.append(f"negative_volume={neg}")
    bad = int(traded.filter((pl.col("high") < pl.col("low"))
                            | (pl.col("close") > pl.col("high") + 1e-9)
                            | (pl.col("close") < pl.col("low") - 1e-9)
                            | (pl.col("open") > pl.col("high") + 1e-9)
                            | (pl.col("open") < pl.col("low") - 1e-9)).height)
    if bad:
        issues.append(f"ohlc_inconsistent={bad}")
    out_of_window = int(df.filter((clock < dtime(4, 0)) | (clock >= dtime(16, 0))).height)
    if out_of_window:
        issues.append(f"outside_session_window={out_of_window}")
    status = "RETRIEVED_CHECKED" if traded.height else "DOCUMENTED_NO_TRADING"
    if issues:
        status = "RETRIEVED_WITH_ISSUES" if traded.height else "UNRESOLVED"
    return {"status": status, "rows": int(df.height), "traded_bars": int(traded.height),
            "issues": issues, "first_ts": str(traded["bar_start"][0]) if traded.height else None,
            "last_ts": str(traded["bar_start"][-1]) if traded.height else None}


def write_validated(part: pl.DataFrame, d: date, symbol: str) -> str:
    path = VALIDATED / d.isoformat() / (safe_symbol_filename(symbol) + ".parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    part.write_parquet(tmp)
    tmp.replace(path)
    return path.relative_to(REPO_ROOT).as_posix()


def raw_path(symbol: str, start: str, end: str):
    return RAW / safe_symbol_filename(symbol) / f"{start}_{end}.parquet"


# ------------------------------------------------------------------ acquisition
def acquire(requests: list[dict], *, concurrency: int = CONCURRENCY, client=None,
            progress_every: int = 100) -> dict:
    """Run planned requests; resume from the log; store raw then validated partitions."""
    from theta.client import get_client
    client = client or get_client()
    limiter = ThetaLimiter(max(1, min(CONCURRENCY, concurrency)))
    done = logged_requests()
    todo = [r for r in requests
            if (r["symbol"], r["start"], r["end"]) not in done
            or not done[(r["symbol"], r["start"], r["end"])].get("ok")]
    counts = {"planned": len(requests), "requested": len(todo), "resumed_ok": len(requests) - len(todo),
              "ok": 0, "empty": 0, "error": 0, "raw_bytes": 0, "validated_sessions": 0,
              "rows": 0, "statuses": defaultdict(int)}
    t0 = time.monotonic()

    def one(req):
        t = time.perf_counter()
        row = {"timestamp": stamp(), "symbol": req["symbol"], "start": req["start"], "end": req["end"],
               "endpoint": ENDPOINT, "interval": INTERVAL, "venue": VENUE,
               "window": "04:00-16:00 ET", "adjustment": "raw unadjusted prints"}
        try:
            kwargs = {"symbol": req["symbol"], "interval": INTERVAL, "start_time": START_TIME,
                      "end_time": END_TIME, "venue": VENUE}
            if req["start"] == req["end"]:
                kwargs["date"] = date.fromisoformat(req["start"])
            else:
                kwargs["start_date"] = date.fromisoformat(req["start"])
                kwargs["end_date"] = date.fromisoformat(req["end"])
            df, elapsed = call_theta(limiter, client.stock_history_ohlc, **kwargs)
            n = 0 if df is None else int(df.height)
            row.update({"ok": True, "rows": n, "elapsed_s": round(time.perf_counter() - t, 3)})
            if n:
                p = raw_path(req["symbol"], req["start"], req["end"])
                p.parent.mkdir(parents=True, exist_ok=True)
                if not p.exists():
                    tmp = p.with_suffix(".tmp")
                    df.write_parquet(tmp)
                    tmp.replace(p)
                row["raw_path"] = p.relative_to(REPO_ROOT).as_posix()
                row["raw_bytes"] = p.stat().st_size
                row["sessions"] = _validate_and_store(df, req)
            else:
                row["session_status"] = {d: "EMPTY_RESPONSE_UNRESOLVED" for d in req["sessions"]}
        except Exception as exc:  # noqa: BLE001
            row.update({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        return row

    with ThreadPoolExecutor(max_workers=limiter.concurrency) as pool:
        futures = [pool.submit(one, r) for r in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            _log(row)
            if not row.get("ok"):
                counts["error"] += 1
            elif row["rows"] == 0:
                counts["empty"] += 1
            else:
                counts["ok"] += 1
                counts["raw_bytes"] += row.get("raw_bytes", 0)
                counts["rows"] += row["rows"]
                for s in (row.get("sessions") or {}).values():
                    counts["statuses"][s["status"]] += 1
                    counts["validated_sessions"] += 1
            if n % progress_every == 0 or n == len(futures):
                el = time.monotonic() - t0
                print(f"{stamp()} acquire {n}/{len(futures)} ok={counts['ok']} empty={counts['empty']} "
                      f"err={counts['error']} {el:.0f}s ETA~{el / n * (len(futures) - n):.0f}s", flush=True)
    counts["statuses"] = dict(counts["statuses"])
    counts["elapsed_s"] = round(time.monotonic() - t0, 1)
    return counts


def _validate_and_store(df: pl.DataFrame, req: dict) -> dict:
    """Normalize the raw response, validate per session and write validated partitions."""
    sym = req["symbol"]
    norm = normalize_ohlc_full(df.rename({"timestamp": "bar_start"}) if "timestamp" in df.columns else df,
                               sym, is_warmup=False)
    wanted = {date.fromisoformat(x) for x in req["sessions"]}
    parts = split_sessions(norm, wanted)
    out = {}
    for d in sorted(wanted):
        part = parts.get(d)
        if part is None or part.height == 0:
            out[d.isoformat()] = {"status": "EMPTY_RESPONSE_UNRESOLVED", "rows": 0, "traded_bars": 0,
                                  "issues": ["session absent from response"]}
            continue
        part = part.sort("bar_start")
        v = validate_session(part, d, sym)
        if v["status"] != "EMPTY_RESPONSE_UNRESOLVED":
            v["path"] = write_validated(part, d, sym)
        out[d.isoformat()] = v
    return out


# ------------------------------------------------------------------ cache invalidation
def invalidate_summaries(sessions) -> int:
    """Drop cached summary partitions for repaired sessions so the loader rebuilds them.

    The summary cache key already tracks the resolved source file identity, so this is a
    belt-and-braces rebuild for dates whose precedence source changed.
    """
    from verification.r4r5_data import CACHE
    n = 0
    for d in sorted({x if isinstance(x, date) else date.fromisoformat(str(x)) for x in sessions}):
        p = CACHE / (d.isoformat() + ".json")
        if p.exists():
            p.unlink()
            n += 1
    return n


def session_status_map() -> dict:
    """(symbol, session iso) -> terminal vendor status, from the immutable request log."""
    out = {}
    for r in logged_requests().values():
        if not r.get("ok"):
            continue
        for iso, v in (r.get("sessions") or {}).items():
            out[(r["symbol"], iso)] = v["status"] if isinstance(v, dict) else str(v)
        for iso, v in (r.get("session_status") or {}).items():
            out.setdefault((r["symbol"], iso), v)
    return out


def coverage_report(requests: list[dict]) -> dict:
    """Terminal source status for every requested symbol-session."""
    logged = logged_requests()
    per_session = {}
    for r in requests:
        key = (r["symbol"], r["start"], r["end"])
        row = logged.get(key)
        for iso in r["sessions"]:
            if row is None:
                per_session[(r["symbol"], iso)] = {"status": "NOT_REQUESTED"}
            elif not row.get("ok"):
                per_session[(r["symbol"], iso)] = {"status": "VENDOR_ERROR_UNRESOLVED",
                                                  "error": row.get("error", "")[:120]}
            else:
                s = (row.get("sessions") or {}).get(iso) or row.get("session_status", {}).get(iso)
                per_session[(r["symbol"], iso)] = s if isinstance(s, dict) else {"status": s or "EMPTY_RESPONSE_UNRESOLVED"}
    counts = defaultdict(int)
    for v in per_session.values():
        counts[v["status"]] += 1
    out = {"timestamp": stamp(), "symbol_sessions": len(per_session), "status_counts": dict(counts),
           "unresolved": sorted([f"{s}/{d}" for (s, d), v in per_session.items()
                                 if v["status"] in {"NOT_REQUESTED", "VENDOR_ERROR_UNRESOLVED",
                                                    "EMPTY_RESPONSE_UNRESOLVED", "UNRESOLVED"}])[:500]}
    dump_json(COVERAGE, out)
    return out
