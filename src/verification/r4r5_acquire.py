"""Arrow 005 acquisition: request manifest, authentication pilot and resumable runner.

Nothing here infers that the vendor holds an observation. The pilot performs a real
authentication attempt through the installed official SDK and records the exact
outcome without printing secret values. The runner stores raw responses immutably
under data/verification/r4r5/v1/acquisition/raw before any transformation, uses at
most eight concurrent requests with bounded backoff, and resumes from the request
log rather than from file existence. An empty response is EMPTY_RESPONSE_UNRESOLVED.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
from pathlib import Path
import time

from ingest.paths import REPO_ROOT, safe_symbol_filename
from ingest.theta_pool import ThetaLimiter, call_theta
from verification.r4r5_data import VERIFY_ROOT, FEATS, INDEX, LOCAL_TAPE_END, dump_json, observation_status, present, stamp

RAW = VERIFY_ROOT / "acquisition" / "raw"
LOG = VERIFY_ROOT / "acquisition" / "requests.jsonl"
PILOT_CASES = (("SNDK", date(2025, 9, 25)), ("DNTH", date(2026, 4, 2)), ("AAPL", date(2026, 3, 4)))


def required_windows(cohort_list, summaries, hold: int = 10) -> list[dict]:
    """One row per symbol-session the ledger needs, with the evidence status it has now."""
    rows = []
    seen = set()
    for c in cohort_list:
        i = INDEX[c["signal"]]
        for h in c["rows"]:
            sym = h["symbol"]
            spans = [("feature", FEATS[max(0, i - 20): i + 1]), ("entry", [FEATS[i + 1]]),
                     ("hold_marks_and_exits", FEATS[i + 2: i + 2 + hold])]
            for role, days in spans:
                for d in days:
                    if (sym, d) in seen:
                        continue
                    seen.add((sym, d))
                    rec = summaries.get((d.isoformat(), sym))
                    rows.append({"symbol": sym, "session": d.isoformat(), "role": role, "cohort_id": c["signal_iso"],
                                 "status": observation_status(d, sym, rec, need_final_minute=role != "feature"),
                                 "source": rec.get("path") if rec else None, "beyond_local_tape": d > LOCAL_TAPE_END,
                                 "endpoint": "stock_history_ohlc", "interval": "1m", "adjustment": "unadjusted raw prints",
                                 "session_convention": "RTH 09:30-close ET, final-minute bar close for executions"})
    return rows


def coalesce(rows: list[dict]) -> list[dict]:
    """Symbol/date-window requests for everything not PRESENT_CHECKED."""
    need = sorted({(r["symbol"], r["session"]) for r in rows if r["status"] != "PRESENT_CHECKED"})
    out = []
    for sym, iso in need:
        d = date.fromisoformat(iso)
        if out and out[-1]["symbol"] == sym and INDEX[date.fromisoformat(out[-1]["end"])] + 1 == INDEX[d]:
            out[-1]["end"] = iso
            out[-1]["sessions"] += 1
        else:
            out.append({"symbol": sym, "start": iso, "end": iso, "sessions": 1})
    return out


def pilot() -> dict:
    """Real authentication and retrieval attempt; never prints credentials."""
    result = {"timestamp": stamp(), "sdk": None, "auth_mode": None, "authenticated": False, "cases": [], "error": None}
    try:
        import thetadata
        from importlib.metadata import version
        result["sdk"] = version("thetadata")
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"SDK import failed: {type(exc).__name__}"
        return result
    try:
        from theta.client import auth_mode, get_client
        result["auth_mode"] = auth_mode()
        client = get_client()
        result["authenticated"] = True
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        result["required_setup"] = ("Create C:/Users/james/money_chatgpt/.env (ignored by Git) containing THETADATA_API_KEY=<key> "
                                    "or THETADATA_EMAIL/THETADATA_PASSWORD, then rerun scripts/cg_arrow005_run.py --acquire.")
        return result
    limiter = ThetaLimiter(1)
    for sym, d in PILOT_CASES:
        case = {"symbol": sym, "date": d.isoformat()}
        try:
            df, elapsed = call_theta(limiter, client.stock_history_ohlc, symbol=sym, start_date=d, end_date=d, interval="1m")
            case.update({"rows": int(df.height) if df is not None else 0, "elapsed_s": round(elapsed, 3),
                         "columns": list(df.columns) if df is not None else []})
        except Exception as exc:  # noqa: BLE001
            case["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        result["cases"].append(case)
    return result


def _log(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")


def completed_requests() -> set[tuple[str, str, str]]:
    done = set()
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("ok") and r.get("rows", 0) > 0:
                done.add((r["symbol"], r["start"], r["end"]))
    return done


def acquire(requests: list[dict], concurrency: int = 8) -> dict:
    """Run coalesced requests; raw parquet is written once per symbol/window and never rewritten."""
    from theta.client import get_client
    client = get_client()
    limiter = ThetaLimiter(max(1, min(8, concurrency)))
    done = completed_requests()
    todo = [r for r in requests if (r["symbol"], r["start"], r["end"]) not in done]
    counts = {"requested": len(todo), "ok": 0, "empty": 0, "error": 0, "bytes": 0}

    def one(r):
        t0 = time.perf_counter()
        row = {"timestamp": stamp(), **r, "endpoint": "stock_history_ohlc", "interval": "1m"}
        try:
            df, elapsed = call_theta(limiter, client.stock_history_ohlc, symbol=r["symbol"],
                                     start_date=date.fromisoformat(r["start"]), end_date=date.fromisoformat(r["end"]), interval="1m")
            n = int(df.height) if df is not None else 0
            row.update({"ok": True, "rows": n, "elapsed_s": round(time.perf_counter() - t0, 3)})
            if n:
                p = RAW / r["symbol"] / f"{r['start']}_{r['end']}.parquet"
                p.parent.mkdir(parents=True, exist_ok=True)
                if not p.exists():
                    tmp = p.with_suffix(".tmp")
                    df.write_parquet(tmp)
                    tmp.replace(p)
                row["raw_path"] = p.relative_to(REPO_ROOT).as_posix()
                row["bytes"] = p.stat().st_size
        except Exception as exc:  # noqa: BLE001
            row.update({"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
        return row

    with ThreadPoolExecutor(max_workers=limiter.concurrency) as pool:
        for fut in as_completed([pool.submit(one, r) for r in todo]):
            row = fut.result()
            _log(row)
            if not row["ok"]:
                counts["error"] += 1
            elif row["rows"] == 0:
                counts["empty"] += 1
            else:
                counts["ok"] += 1
                counts["bytes"] += row.get("bytes", 0)
    return counts
