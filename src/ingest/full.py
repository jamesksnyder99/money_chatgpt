from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import polars as pl
from thetadata.errors import NoDataFoundError

from ingest.bars import normalize_ohlc_full, split_sessions
from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.eligibility import MAX_CLOSE_FULL, build_eligibility, eod_session_dates
from ingest.paths import (
    FULL_BARS,
    FULL_ELIGIBILITY,
    FULL_MANIFEST,
    REPORTS,
    SYMBOLS,
    ensure_dirs,
    full_bar_path,
)
from ingest.progress import Progress
from ingest.run import load_eod_chunks, month_groups
from ingest.theta_pool import ThetaLimiter, call_theta
from theta.client import get_shared_client

ET = ZoneInfo("America/New_York")
VENUE = "utp_cta"
INTERVAL = "1m"
START_TIME = dtime(4, 0)
END_TIME = dtime(16, 0)
PRE_CUT = dtime(7, 30)


def sessions_to_pull(symbol: str, dates: list[date], *, force: bool = False) -> list[date]:
    """Resume: skip name-days whose parquet already exists unless force."""
    if force:
        return list(dates)
    return [d for d in dates if not full_bar_path(d, symbol).exists()]


def _empty_full_frame(symbol: str, is_warmup: bool) -> pl.DataFrame:
    return normalize_ohlc_full(pl.DataFrame(), symbol, is_warmup)


def pull_one_full(
    client,
    limiter: ThetaLimiter,
    symbol: str,
    sessions: list[date],
    force: bool,
    is_warmup: bool,
) -> dict:
    sessions = sorted(sessions)
    need = sessions_to_pull(symbol, sessions, force=force)
    if not need:
        rows = 0
        for d in sessions:
            p = full_bar_path(d, symbol)
            rows += pl.read_parquet(p).height if p.exists() else 0
        return {
            "symbol": symbol,
            "ok": True,
            "skipped": True,
            "rows": rows,
            "per_day": {},
            "elapsed_s": 0.0,
            "error_class": "",
            "error_message": "",
            "sessions": sessions,
        }
    start_d, end_d = need[0], need[-1]
    try:
        kwargs = {
            "symbol": symbol,
            "interval": INTERVAL,
            "start_time": START_TIME,
            "end_time": END_TIME,
            "venue": VENUE,
        }
        if start_d == end_d:
            kwargs["date"] = start_d
        else:
            kwargs["start_date"] = start_d
            kwargs["end_date"] = end_d
        df, elapsed = call_theta(limiter, client.stock_history_ohlc, **kwargs)
        norm = normalize_ohlc_full(df, symbol, is_warmup=is_warmup)
        parts = split_sessions(norm, set(need))
        per_day: dict[date, int] = {}
        total = 0
        for d in need:
            part = parts.get(d)
            path = full_bar_path(d, symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            if part is None or part.height == 0:
                _empty_full_frame(symbol, is_warmup).write_parquet(path)
                per_day[d] = 0
            else:
                part.write_parquet(path)
                per_day[d] = part.height
                total += part.height
        return {
            "symbol": symbol,
            "ok": True,
            "skipped": False,
            "rows": total,
            "per_day": per_day,
            "elapsed_s": elapsed,
            "error_class": "",
            "error_message": "",
            "sessions": need,
        }
    except NoDataFoundError:
        for d in need:
            path = full_bar_path(d, symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            _empty_full_frame(symbol, is_warmup).write_parquet(path)
        return {
            "symbol": symbol,
            "ok": True,
            "skipped": False,
            "rows": 0,
            "per_day": {d: 0 for d in need},
            "elapsed_s": 0.0,
            "error_class": "",
            "error_message": "",
            "sessions": need,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol,
            "ok": False,
            "skipped": False,
            "rows": 0,
            "per_day": {},
            "elapsed_s": 0.0,
            "error_class": type(exc).__name__,
            "error_message": str(exc)[:500],
            "sessions": need,
        }


def _jobs_for(elig: pl.DataFrame, target: list[date]) -> list[tuple[str, list[date], bool]]:
    want = set(target)
    warmup = set(WARMUP_SESSIONS)
    by_sym: dict[str, list[date]] = {}
    for symbol, session in (
        elig.filter(pl.col("eligible")).select("symbol", "session_date").iter_rows()
    ):
        if session in want:
            by_sym.setdefault(str(symbol), []).append(session)
    jobs: list[tuple[str, list[date], bool]] = []
    for sym, dates in by_sym.items():
        for group in month_groups(dates):
            is_w = all(d in warmup for d in group)
            jobs.append((sym, group, is_w))
    return jobs


def _run_jobs(
    jobs: list[tuple[str, list[date], bool]],
    *,
    client,
    limiter: ThetaLimiter,
    workers: int,
    force: bool,
    job_name: str,
) -> tuple[int, int, int, list[dict]]:
    if not jobs:
        return 0, 0, 0, []
    prog = Progress(len(jobs), job_name)
    prog.start_heartbeat()
    rows = 0
    oks = 0
    fails = 0
    failures: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(pull_one_full, client, limiter, sym, dates, force, is_w)
            for sym, dates, is_w in jobs
        ]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            prog.mark(rec["symbol"], rows=rec["rows"], elapsed_s=rec["elapsed_s"], ok=rec["ok"])
            rows += rec["rows"]
            if rec["ok"]:
                oks += 1
            else:
                fails += 1
                failures.append(rec)
            if i % 32 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    return rows, oks, fails, failures


def build_full_eligibility() -> pl.DataFrame:
    if not SYMBOLS.exists():
        raise FileNotFoundError(f"missing {SYMBOLS}; run Lab A symbol list first")
    symbols = pl.read_parquet(SYMBOLS)["symbol"].to_list()
    eod = load_eod_chunks()
    if eod.height == 0:
        raise FileNotFoundError("no EOD parquet under data/eod; run Lab A EOD first")
    if "eod_date" not in eod.columns:
        eod = eod_session_dates(eod)
    warm = build_eligibility(
        eod, symbols, list(WARMUP_SESSIONS), is_warmup=True, max_close=MAX_CLOSE_FULL
    )
    study = build_eligibility(
        eod, symbols, study_sessions(), is_warmup=False, max_close=MAX_CLOSE_FULL
    )
    elig = pl.concat([warm, study], how="vertical_relaxed")
    keep = elig.select(
        "symbol",
        "session_date",
        "prior_close",
        "prior_dollar_volume",
        "eligible",
        "exclude_reason",
        "is_warmup",
    )
    FULL_ELIGIBILITY.parent.mkdir(parents=True, exist_ok=True)
    keep.write_parquet(FULL_ELIGIBILITY)
    n_ok = keep.filter(pl.col("eligible")).height
    n_sym = keep.filter(pl.col("eligible"))["symbol"].n_unique()
    print(
        f"full eligibility name-days={keep.height} eligible={n_ok} unique={n_sym} "
        f"max_close={MAX_CLOSE_FULL} wrote={FULL_ELIGIBILITY}",
        flush=True,
    )
    return keep


def _scan_one(item: tuple[str, date]) -> dict:
    sym, d = item
    p = full_bar_path(d, sym)
    if not p.exists():
        return {
            "symbol": sym,
            "session_date": d,
            "status": "missing",
            "rows": 0,
            "has_0400": False,
            "first_after_0730": False,
        }
    df = pl.read_parquet(p, columns=["bar_start"])
    n = df.height
    if n == 0:
        return {
            "symbol": sym,
            "session_date": d,
            "status": "empty",
            "rows": 0,
            "has_0400": False,
            "first_after_0730": False,
        }
    times = df["bar_start"].dt.time()
    first = times.min()
    return {
        "symbol": sym,
        "session_date": d,
        "status": "pulled",
        "rows": n,
        "has_0400": bool((times == START_TIME).any()),
        "first_after_0730": first is not None and first > PRE_CUT,
    }


def _write_manifest(elig: pl.DataFrame, workers: int) -> tuple[pl.DataFrame, int, int]:
    pairs = [
        (str(s), d)
        for s, d in elig.filter(pl.col("eligible")).select("symbol", "session_date").iter_rows()
    ]
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for rec in pool.map(_scan_one, pairs, chunksize=32):
            rows.append(rec)
    man = pl.DataFrame(rows)
    FULL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    man.write_parquet(FULL_MANIFEST)
    n_0400 = int(man["has_0400"].sum()) if man.height else 0
    n_after = int(man["first_after_0730"].sum()) if man.height else 0
    return man, n_0400, n_after


def _write_report(
    *,
    elig: pl.DataFrame,
    man: pl.DataFrame,
    workers: int,
    theta_n: int,
    cpu: int,
    wall_s: float,
    failures: list[dict],
    n_0400: int,
    n_after: int,
    first5_note: str,
) -> None:
    ok = elig.filter(pl.col("eligible"))
    n_elig = ok.height
    n_sess = ok["session_date"].n_unique()
    n_rows = int(man["rows"].sum()) if man.height else 0
    n_pulled = man.filter(pl.col("status") == "pulled").height
    n_empty = man.filter(pl.col("status") == "empty").height
    n_miss = man.filter(pl.col("status") == "missing").height
    mean_bars = n_rows / n_elig if n_elig else 0.0
    lines = [
        "Arrow 17 — contiguous 04:00-16:00 1-minute tape (ingest, not a book)",
        "No fills. No $200 verdict. Did not overwrite data/bars (07:30-12:00). No Arrow 18.",
        f"venue={VENUE} interval={INTERVAL} window=04:00-16:00ET last_bar=15:59",
        f"eligibility: common stock + ETP denylist, prior_close [$1, $50], prior DV >= $1M, no 400 cap",
        f"sessions warmup={len(WARMUP_SESSIONS)} {WARMUP_SESSIONS[0]}..{WARMUP_SESSIONS[-1]} "
        f"study={len(study_sessions())} {study_sessions()[0]}..{study_sessions()[-1]} "
        f"(Jul 3 closed as contract)",
        f"workers={workers} theta_concurrency={theta_n} cpu_count={cpu}",
        f"output bars={FULL_BARS} eligibility={FULL_ELIGIBILITY} manifest={FULL_MANIFEST}",
        "",
        f"sessions_attempted={n_sess}",
        f"name_days_eligible={n_elig}",
        f"unique_symbols={ok['symbol'].n_unique()}",
        f"1m_rows={n_rows}",
        f"mean_bars_per_name_day={mean_bars:.1f}",
        f"manifest pulled={n_pulled} empty={n_empty} missing={n_miss}",
        f"failures={len(failures)}",
        f"wall_s={wall_s:.1f} wall_min={wall_s / 60:.1f}",
        first5_note,
        f"name_days_with_04:00_print={n_0400}",
        f"name_days_first_print_after_07:30={n_after}",
        "",
    ]
    if failures:
        lines.append("failure sample (up to 20):")
        for rec in failures[:20]:
            lines.append(
                f"  {rec['symbol']} {rec.get('error_class')} {rec.get('error_message', '')[:120]}"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "tape17_ingest.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)


def run_arrow17(*, workers: int | None = None, theta_concurrency: int = 8, force: bool = False) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    theta_n = max(1, min(8, int(theta_concurrency)))
    t0 = time.monotonic()
    study = study_sessions()
    first5 = study[:5]
    rest = list(WARMUP_SESSIONS) + study[5:]
    print(
        f"ingest start mode=arrow17 span=warmup:{WARMUP_SESSIONS[0]}..{WARMUP_SESSIONS[-1]} "
        f"study={study[0]}..{study[-1]} endpoint=stock_history_ohlc interval={INTERVAL} "
        f"venue={VENUE} window=04:00-16:00ET workers={workers} "
        f"theta_concurrency={theta_n} cpu_count={cpu} output={FULL_BARS} "
        f"do_not_touch=data/bars",
        flush=True,
    )
    elig = build_full_eligibility()
    client = get_shared_client()
    limiter = ThetaLimiter(theta_n)

    jobs5 = _jobs_for(elig, first5)
    print(f"phase 1: first 5 study sessions {first5[0]}..{first5[-1]} jobs={len(jobs5)}", flush=True)
    t1 = time.monotonic()
    rows5, ok5, fail5, fail_a = _run_jobs(
        jobs5, client=client, limiter=limiter, workers=workers, force=force, job_name="full_first5"
    )
    elapsed5 = time.monotonic() - t1
    n5 = elig.filter(
        pl.col("eligible") & pl.col("session_date").is_in(first5)
    ).height
    remain_nd = elig.filter(pl.col("eligible") & pl.col("session_date").is_in(rest)).height
    eta_s = (elapsed5 / n5 * remain_nd) if n5 else 0.0
    first5_note = (
        f"after_first_5_study_sessions elapsed_s={elapsed5:.1f} name_days={n5} rows={rows5} "
        f"remaining_name_days={remain_nd} eta_min={eta_s / 60:.1f} (estimate)"
    )
    print(first5_note, flush=True)

    jobs_rest = _jobs_for(elig, rest)
    print(f"phase 2: remaining warmup+study jobs={len(jobs_rest)}", flush=True)
    rows_r, ok_r, fail_r, fail_b = _run_jobs(
        jobs_rest, client=client, limiter=limiter, workers=workers, force=force, job_name="full_rest"
    )
    failures = fail_a + fail_b
    print(
        f"pull done rows={rows5 + rows_r} ok_jobs={ok5 + ok_r} fail_jobs={fail5 + fail_r}",
        flush=True,
    )
    print("write manifest + 04:00 stats", flush=True)
    man, n_0400, n_after = _write_manifest(elig, workers)
    wall = time.monotonic() - t0
    _write_report(
        elig=elig,
        man=man,
        workers=workers,
        theta_n=limiter.concurrency,
        cpu=cpu,
        wall_s=wall,
        failures=failures,
        n_0400=n_0400,
        n_after=n_after,
        first5_note=first5_note,
    )
    return 0 if not failures else 0
