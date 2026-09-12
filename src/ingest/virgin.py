"""Arrow 41 — virgin ingest Dec 2025 warmup + Jan–May 2026 study. Ingest only."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import polars as pl
from thetadata.errors import NoDataFoundError

from ingest.bars import normalize_ohlc_full, split_sessions
from ingest.calendar import (
    ARROW61_END,
    ARROW61_EXPECTED,
    ARROW61_START,
    ARROW67_END,
    ARROW67_LABOR_DAY,
    ARROW67_START,
    ARROW67_THANKSGIVING,
    ARROW69_END,
    ARROW69_START,
    arrow61_prior_calendar,
    is_nyse_session,
    arrow61_sessions,
    arrow67_non_sessions,
    arrow67_prior_calendar,
    arrow67_sessions,
    arrow69_non_sessions,
    arrow69_prior_calendar,
    arrow69_sessions,
    december_2025_sessions,
    virgin_prior_calendar,
    virgin_sessions,
    virgin_study_sessions,
    virgin_warmup_sessions,
)
from ingest.eligibility import (
    MAX_CLOSE_VIRGIN,
    build_eligibility,
    eod_session_dates,
    with_pdv_10m_flag,
)
from ingest.paths import (
    BARS_DIR,
    FULL_BARS,
    REPORTS,
    SYMBOLS,
    VIRGIN_BARS,
    VIRGIN_ELIGIBILITY,
    VIRGIN_EOD,
    VIRGIN_IWM,
    VIRGIN_MANIFEST,
    VIRGIN_ROOT,
    ensure_virgin_dirs,
    virgin_bar_path,
    virgin_eod_path,
    virgin_iwm_path,
)
from ingest.progress import Progress
from ingest.run import month_groups
from ingest.theta_pool import ThetaLimiter, call_theta
from theta.client import get_shared_client

ET = ZoneInfo("America/New_York")
VENUE = "utp_cta"
INTERVAL = "1m"
START_TIME = dtime(4, 0)
END_TIME = dtime(16, 0)
PRE_CUT = dtime(7, 30)

VIRGIN_EOD_CHUNKS: tuple[tuple[date, date, str], ...] = (
    (date(2025, 12, 16), date(2025, 12, 31), "2025-12"),
    (date(2026, 1, 1), date(2026, 1, 31), "2026-01"),
    (date(2026, 2, 1), date(2026, 2, 28), "2026-02"),
    (date(2026, 3, 1), date(2026, 3, 31), "2026-03"),
    (date(2026, 4, 1), date(2026, 4, 30), "2026-04"),
    (date(2026, 5, 1), date(2026, 5, 29), "2026-05"),
)
ARROW61_EOD_CHUNKS: tuple[tuple[date, date, str], ...] = (
    (date(2025, 11, 28), date(2025, 11, 28), "2025-11"),
    (date(2025, 12, 1), date(2025, 12, 15), "2025-12-early"),
)
ARROW67_EOD_CHUNKS: tuple[tuple[date, date, str], ...] = (
    (date(2025, 8, 29), date(2025, 8, 29), "2025-08"),
    (date(2025, 9, 1), date(2025, 9, 30), "2025-09"),
    (date(2025, 10, 1), date(2025, 10, 31), "2025-10"),
    (date(2025, 11, 1), date(2025, 11, 26), "2025-11-early"),
)
ARROW69_EOD_CHUNKS: tuple[tuple[date, date, str], ...] = (
    (date(2025, 7, 31), date(2025, 7, 31), "2025-07"),
    (date(2025, 8, 1), date(2025, 8, 28), "2025-08-early"),
)


def _assert_virgin_tree() -> None:
    root = VIRGIN_ROOT.resolve()
    if FULL_BARS.resolve() == root or BARS_DIR.resolve() == root:
        raise RuntimeError("virgin output collided with data/full or Lab A data/bars")
    if FULL_BARS in (VIRGIN_BARS, VIRGIN_EOD, VIRGIN_IWM):
        raise RuntimeError("virgin paths must not alias data/full")


def sessions_to_pull(symbol: str, dates: list[date], *, force: bool = False) -> list[date]:
    """Resume: skip name-days whose virgin parquet already exists unless force."""
    if force:
        return list(dates)
    return [d for d in dates if not virgin_bar_path(d, symbol).exists()]


def _as_date(x) -> date:
    if isinstance(x, datetime):
        return x.date()
    return x


def manifest_session_dates(path=None) -> set[date]:
    p = path or VIRGIN_MANIFEST
    if not p.exists():
        return set()
    man = pl.read_parquet(p, columns=["session_date"])
    return {_as_date(x) for x in man["session_date"].to_list()}


def ohlc_dates_to_pull(
    target: list[date],
    already: set[date],
    *,
    force: bool = False,
    start: date = ARROW61_START,
    end: date = ARROW61_END,
) -> list[date]:
    """Arrow 61 window only. Dates already in the virgin manifest are skipped unless force."""
    out: list[date] = []
    for d in target:
        if d < start or d > end:
            continue
        if not is_nyse_session(d):
            continue
        if not force and d in already:
            continue
        out.append(d)
    return out


def arrow61_output_roots():
    return (VIRGIN_BARS, VIRGIN_EOD, VIRGIN_IWM, VIRGIN_ELIGIBILITY, VIRGIN_MANIFEST)


def arrow67_output_roots():
    return arrow61_output_roots()


def arrow69_output_roots():
    return arrow61_output_roots()


def _empty_full_frame(symbol: str, is_warmup: bool) -> pl.DataFrame:
    return normalize_ohlc_full(pl.DataFrame(), symbol, is_warmup)


def _empty_eod(symbol: str) -> pl.DataFrame:
    return pl.DataFrame(
        schema={
            "symbol": pl.String,
            "eod_date": pl.Date,
            "close": pl.Float64,
            "volume": pl.Int64,
        }
    ).with_columns(pl.lit(symbol).alias("symbol"))


def pull_one_eod(
    client,
    limiter: ThetaLimiter,
    symbol: str,
    start: date,
    end: date,
    chunk: str,
    force: bool,
) -> tuple[str, bool, str, str, float]:
    path = virgin_eod_path(symbol, chunk)
    if not force and path.exists():
        return symbol, True, "", "", 0.0
    try:
        df, elapsed = call_theta(
            limiter,
            client.stock_history_eod,
            symbol=symbol,
            start_date=start,
            end_date=end,
        )
        df = df.with_columns(pl.lit(symbol).alias("symbol"))
        df = eod_session_dates(df)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(path)
        return symbol, True, "", "", elapsed
    except NoDataFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        _empty_eod(symbol).write_parquet(path)
        return symbol, True, "", "", 0.0
    except Exception as exc:  # noqa: BLE001
        return symbol, False, type(exc).__name__, str(exc)[:500], 0.0


def _concat_chunk(chunk: str) -> None:
    folder = VIRGIN_EOD / chunk
    if not folder.exists():
        return
    files = [p for p in folder.glob("*.parquet") if not p.name.startswith("_")]
    dest = folder / "_all.parquet"
    if not files:
        return
    with ThreadPoolExecutor(max_workers=8) as pool:
        frames = list(pool.map(pl.read_parquet, files))
    pl.concat(frames, how="diagonal_relaxed").write_parquet(dest)


def pull_eod(
    client,
    limiter: ThetaLimiter,
    symbols: list[str],
    workers: int,
    force: bool,
    chunks: tuple[tuple[date, date, str], ...] | None = None,
) -> tuple[pl.DataFrame, list[dict]]:
    failures: list[dict] = []
    for start, end, chunk in chunks or VIRGIN_EOD_CHUNKS:
        (VIRGIN_EOD / chunk).mkdir(parents=True, exist_ok=True)
        need = [
            s
            for s in symbols
            if force or not virgin_eod_path(s, chunk).exists()
        ]
        print(
            f"EOD chunk={chunk} {start}..{end} symbols={len(symbols)} need={len(need)}",
            flush=True,
        )
        if need:
            prog = Progress(len(need), f"virgin_eod:{chunk}")
            prog.start_heartbeat()
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = [
                    pool.submit(pull_one_eod, client, limiter, sym, start, end, chunk, force)
                    for sym in need
                ]
                for i, fut in enumerate(as_completed(futs), 1):
                    symbol, ok, cls, msg, elapsed = fut.result()
                    prog.mark(symbol, ok=ok, elapsed_s=elapsed)
                    if not ok:
                        failures.append(
                            {
                                "symbol": symbol,
                                "session": f"eod:{chunk}",
                                "error_class": cls,
                                "error_message": msg,
                            }
                        )
                    if i % 250 == 0:
                        prog.heartbeat()
            prog.stop_heartbeat()
            prog.heartbeat()
        print(f"concat EOD chunk={chunk}", flush=True)
        _concat_chunk(chunk)
    eod = load_virgin_eod()
    print(f"EOD loaded rows={eod.height} fails={len(failures)}", flush=True)
    return eod, failures


def load_virgin_eod() -> pl.DataFrame:
    files = sorted(VIRGIN_EOD.glob("*/_all.parquet"))
    if not files:
        files = [p for p in VIRGIN_EOD.rglob("*.parquet") if not p.name.startswith("_")]
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(p) for p in files], how="diagonal_relaxed")


def build_virgin_eligibility(eod: pl.DataFrame, symbols: list[str]) -> pl.DataFrame:
    if eod.height == 0:
        raise FileNotFoundError(f"no virgin EOD under {VIRGIN_EOD}")
    if "eod_date" not in eod.columns:
        eod = eod_session_dates(eod)
    prior_cal = virgin_prior_calendar()
    warm = build_eligibility(
        eod,
        symbols,
        virgin_warmup_sessions(),
        is_warmup=True,
        max_close=MAX_CLOSE_VIRGIN,
        sessions_for_prior=prior_cal,
    )
    study = build_eligibility(
        eod,
        symbols,
        virgin_study_sessions(),
        is_warmup=False,
        max_close=MAX_CLOSE_VIRGIN,
        sessions_for_prior=prior_cal,
    )
    elig = with_pdv_10m_flag(pl.concat([warm, study], how="vertical_relaxed"))
    keep = elig.select(
        "symbol",
        "session_date",
        "prior_close",
        "prior_volume",
        "prior_dollar_volume",
        "eligible",
        "exclude_reason",
        "is_warmup",
        "pdv_ge_10m",
    )
    VIRGIN_ELIGIBILITY.parent.mkdir(parents=True, exist_ok=True)
    keep.write_parquet(VIRGIN_ELIGIBILITY)
    n_ok = keep.filter(pl.col("eligible")).height
    n_sym = keep.filter(pl.col("eligible"))["symbol"].n_unique()
    n_10m = keep.filter(pl.col("eligible") & pl.col("pdv_ge_10m")).height
    n_gt50 = keep.filter(pl.col("eligible") & (pl.col("prior_close") > 50)).height
    print(
        f"virgin eligibility name-days={keep.height} eligible={n_ok} unique={n_sym} "
        f"max_close={MAX_CLOSE_VIRGIN} pdv_ge_10m={n_10m} prior_close_gt_50={n_gt50} "
        f"wrote={VIRGIN_ELIGIBILITY}",
        flush=True,
    )
    return keep


def pull_one_ohlc(
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
            p = virgin_bar_path(d, symbol)
            rows += pl.read_parquet(p).height if p.exists() else 0
        return {
            "symbol": symbol,
            "ok": True,
            "skipped": True,
            "rows": rows,
            "elapsed_s": 0.0,
            "error_class": "",
            "error_message": "",
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
        total = 0
        for d in need:
            part = parts.get(d)
            path = virgin_bar_path(d, symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            if part is None or part.height == 0:
                _empty_full_frame(symbol, is_warmup).write_parquet(path)
            else:
                part.write_parquet(path)
                total += part.height
        return {
            "symbol": symbol,
            "ok": True,
            "skipped": False,
            "rows": total,
            "elapsed_s": elapsed,
            "error_class": "",
            "error_message": "",
        }
    except NoDataFoundError:
        for d in need:
            path = virgin_bar_path(d, symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            _empty_full_frame(symbol, is_warmup).write_parquet(path)
        return {
            "symbol": symbol,
            "ok": True,
            "skipped": False,
            "rows": 0,
            "elapsed_s": 0.0,
            "error_class": "",
            "error_message": "",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "symbol": symbol,
            "ok": False,
            "skipped": False,
            "rows": 0,
            "elapsed_s": 0.0,
            "error_class": type(exc).__name__,
            "error_message": str(exc)[:500],
        }


def _jobs_for(
    elig: pl.DataFrame,
    target: list[date],
    *,
    warmup: set[date] | None = None,
) -> list[tuple[str, list[date], bool]]:
    want = set(target)
    warmup = set(warmup) if warmup is not None else set(virgin_warmup_sessions())
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
            pool.submit(pull_one_ohlc, client, limiter, sym, dates, force, is_w)
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


def pull_iwm(
    *,
    client,
    limiter: ThetaLimiter,
    force: bool = False,
    sessions: list[date] | None = None,
    warmup: set[date] | None = None,
) -> tuple[int, int]:
    sessions = list(sessions) if sessions is not None else virgin_sessions()
    VIRGIN_IWM.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    n_fail = 0
    warmup = set(warmup) if warmup is not None else set(virgin_warmup_sessions())
    for group in month_groups(sessions):
        need = [d for d in group if force or not virgin_iwm_path(d).exists()]
        if not need:
            n_ok += len(group)
            continue
        start_d, end_d = need[0], need[-1]
        kwargs = {
            "symbol": "IWM",
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
        try:
            df, _elapsed = call_theta(limiter, client.stock_history_ohlc, **kwargs)
            is_w = all(d in warmup for d in need)
            norm = normalize_ohlc_full(df, "IWM", is_warmup=is_w)
            parts = split_sessions(norm, set(need))
            for d in need:
                part = parts.get(d)
                path = virgin_iwm_path(d)
                if part is None or part.height == 0:
                    _empty_full_frame("IWM", is_w).write_parquet(path)
                else:
                    part.write_parquet(path)
                n_ok += 1
            print(f"IWM wrote {start_d}..{end_d} days={len(need)} dir={VIRGIN_IWM}", flush=True)
        except NoDataFoundError:
            for d in need:
                _empty_full_frame("IWM", False).write_parquet(virgin_iwm_path(d))
            print(f"IWM no data {start_d}..{end_d}", flush=True)
        except Exception as exc:  # noqa: BLE001
            n_fail += 1
            print(f"IWM pull failed {start_d}..{end_d}: {type(exc).__name__}", flush=True)
    print(f"IWM sessions on disk={n_ok}/{len(sessions)} dir={VIRGIN_IWM}", flush=True)
    return n_ok, n_fail


def _scan_one(item: tuple[str, date]) -> dict:
    sym, d = item
    p = virgin_bar_path(d, sym)
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
    VIRGIN_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    man.write_parquet(VIRGIN_MANIFEST)
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
    iwm_ok: int,
    iwm_fail: int,
) -> None:
    ok = elig.filter(pl.col("eligible"))
    n_elig = ok.height
    n_sess = ok["session_date"].n_unique()
    n_rows = int(man["rows"].sum()) if man.height else 0
    n_pulled = man.filter(pl.col("status") == "pulled").height
    n_empty = man.filter(pl.col("status") == "empty").height
    n_miss = man.filter(pl.col("status") == "missing").height
    mean_bars = n_rows / n_elig if n_elig else 0.0
    n_10m = int(ok.filter(pl.col("pdv_ge_10m")).height) if "pdv_ge_10m" in ok.columns else 0
    n_gt50 = int(ok.filter(pl.col("prior_close") > 50).height)
    warm = virgin_warmup_sessions()
    study = virgin_study_sessions()
    iwm_disk = len(list(VIRGIN_IWM.glob("*.parquet"))) if VIRGIN_IWM.exists() else 0
    lines = [
        "Arrow 41 — virgin 04:00-16:00 1-minute tape (ingest, not a book)",
        "No fills. No $200 verdict. Did not score engines. Did not touch data/full or Lab A data/bars. No Arrow 42.",
        f"venue={VENUE} interval={INTERVAL} window=04:00-16:00ET last_bar=15:59",
        "eligibility: common stock + ETP denylist, prior_close [$1, $80], prior DV >= $1M, "
        "$10M is a filter column not an ingest wall, no 400 cap",
        f"warmup n={len(warm)} {warm[0]}..{warm[-1]} (last 10 NYSE 2025; not scored)",
        f"study n={len(study)} {study[0]}..{study[-1]} (first 2026 session through last full May; all of January in study)",
        f"workers={workers} theta_concurrency={theta_n} cpu_count={cpu}",
        f"output bars={VIRGIN_BARS} eligibility={VIRGIN_ELIGIBILITY} manifest={VIRGIN_MANIFEST} iwm={VIRGIN_IWM}",
        "",
        f"sessions_attempted={n_sess}",
        f"name_days_eligible={n_elig}",
        f"unique_symbols={ok['symbol'].n_unique()}",
        f"1m_rows={n_rows}",
        f"mean_bars_per_name_day={mean_bars:.1f}",
        f"name_days_pdv_ge_10m={n_10m}",
        f"name_days_prior_close_gt_50={n_gt50}",
        f"manifest pulled={n_pulled} empty={n_empty} missing={n_miss}",
        f"failures={len(failures)}",
        f"iwm_sessions_on_disk={iwm_disk} iwm_ok={iwm_ok} iwm_fail={iwm_fail}",
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
                f"  {rec.get('symbol')} {rec.get('error_class')} {rec.get('error_message', '')[:120]}"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "tape41_ingest.txt"
    out.write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {out}", flush=True)


def run_arrow41(*, workers: int | None = None, theta_concurrency: int = 8, force: bool = False) -> int:
    _assert_virgin_tree()
    ensure_virgin_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    theta_n = max(1, min(8, int(theta_concurrency)))
    t0 = time.monotonic()
    warm = virgin_warmup_sessions()
    study = virgin_study_sessions()
    first5 = study[:5]
    rest = list(warm) + study[5:]
    print(
        f"ingest start mode=arrow41 span=warmup:{warm[0]}..{warm[-1]} "
        f"study={study[0]}..{study[-1]} endpoint=stock_history_ohlc interval={INTERVAL} "
        f"venue={VENUE} window=04:00-16:00ET workers={workers} "
        f"theta_concurrency={theta_n} cpu_count={cpu} output={VIRGIN_BARS} "
        f"do_not_touch=data/full,data/bars no_arrow_42",
        flush=True,
    )
    if not SYMBOLS.exists():
        raise FileNotFoundError(f"missing {SYMBOLS}; reuse Lab A common list, do not overwrite")
    symbols = pl.read_parquet(SYMBOLS)["symbol"].to_list()
    print(f"commons={len(symbols)} from {SYMBOLS} (read-only)", flush=True)
    client = get_shared_client()
    limiter = ThetaLimiter(theta_n)

    eod, eod_fail = pull_eod(client, limiter, symbols, workers, force)
    elig = build_virgin_eligibility(eod, symbols)

    print("pull IWM 04:00-16:00 into data/virgin/bench (not data/full/bench)", flush=True)
    iwm_ok, iwm_fail = pull_iwm(client=client, limiter=limiter, force=force)

    jobs5 = _jobs_for(elig, first5)
    print(f"phase 1: first 5 study sessions {first5[0]}..{first5[-1]} jobs={len(jobs5)}", flush=True)
    t1 = time.monotonic()
    rows5, ok5, fail5, fail_a = _run_jobs(
        jobs5, client=client, limiter=limiter, workers=workers, force=force, job_name="virgin_first5"
    )
    elapsed5 = time.monotonic() - t1
    n5 = elig.filter(pl.col("eligible") & pl.col("session_date").is_in(first5)).height
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
        jobs_rest, client=client, limiter=limiter, workers=workers, force=force, job_name="virgin_rest"
    )
    failures = eod_fail + fail_a + fail_b
    print(
        f"pull done rows={rows5 + rows_r} ok_jobs={ok5 + ok_r} fail_jobs={fail5 + fail_r} "
        f"eod_fail={len(eod_fail)}",
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
        iwm_ok=iwm_ok,
        iwm_fail=iwm_fail,
    )
    return 0


def _append_eligibility(new_elig: pl.DataFrame) -> pl.DataFrame:
    new_dates = {_as_date(x) for x in new_elig["session_date"].to_list()} if new_elig.height else set()
    if VIRGIN_ELIGIBILITY.exists() and new_dates:
        old = pl.read_parquet(VIRGIN_ELIGIBILITY)
        old = old.filter(~pl.col("session_date").is_in(list(new_dates)))
        keep = pl.concat([old, new_elig], how="diagonal_relaxed")
    else:
        keep = new_elig
    VIRGIN_ELIGIBILITY.parent.mkdir(parents=True, exist_ok=True)
    keep.write_parquet(VIRGIN_ELIGIBILITY)
    return keep


def _append_manifest(new_elig: pl.DataFrame, workers: int) -> tuple[pl.DataFrame, int, int]:
    old = pl.read_parquet(VIRGIN_MANIFEST) if VIRGIN_MANIFEST.exists() else None
    new_man, n_0400, n_after = _write_manifest(new_elig, workers)
    new_dates = {_as_date(x) for x in new_elig["session_date"].to_list()} if new_elig.height else set()
    if old is not None and new_dates:
        old = old.filter(~pl.col("session_date").is_in(list(new_dates)))
        man = pl.concat([old, new_man], how="diagonal_relaxed")
        VIRGIN_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        man.write_parquet(VIRGIN_MANIFEST)
        return man, n_0400, n_after
    return new_man, n_0400, n_after


def _write_report_61(
    *,
    target: list[date],
    pulled: list[date],
    skipped_disk: list[date],
    skipped_not_session: list[date],
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
    iwm_ok: int,
    iwm_fail: int,
    holes: list[date],
) -> None:
    ok = elig.filter(pl.col("eligible"))
    n_elig = ok.height
    n_sess = ok["session_date"].n_unique() if n_elig else 0
    n_rows = int(man["rows"].sum()) if man.height else 0
    n_pulled = man.filter(pl.col("status") == "pulled").height if man.height else 0
    n_empty = man.filter(pl.col("status") == "empty").height if man.height else 0
    n_miss = man.filter(pl.col("status") == "missing").height if man.height else 0
    mean_bars = n_rows / n_elig if n_elig else 0.0
    n_10m = int(ok.filter(pl.col("pdv_ge_10m")).height) if n_elig and "pdv_ge_10m" in ok.columns else 0
    iwm_disk = len([d for d in target if virgin_iwm_path(d).exists()])
    pulled_s = ", ".join(d.isoformat() for d in pulled) if pulled else "none"
    skip_disk_s = ", ".join(d.isoformat() for d in skipped_disk) if skipped_disk else "none"
    skip_ns_s = ", ".join(d.isoformat() for d in skipped_not_session) if skipped_not_session else "none"
    if holes:
        dec_line = "December 2025 on virgin has holes: " + ", ".join(d.isoformat() for d in holes)
    else:
        dec_line = (
            "December 2025 on virgin is now complete "
            "(first December session 2025-12-01 through 2025-12-31)."
        )
    lines = [
        "Arrow 61 — rest of December 2025 into data/virgin/ (ingest, not a book)",
        "No fills. No $200 verdict. Did not score engines. Did not touch data/full or Lab A data/bars. "
        "Did not rebuild 2025-12-17..2025-12-31. No Arrow 62.",
        f"venue={VENUE} interval={INTERVAL} window=04:00-16:00ET last_bar=15:59",
        "eligibility: common stock + ETP denylist, prior_close [$1, $80], prior DV >= $1M, "
        "$10M is a filter column not an ingest wall, no 400 cap",
        f"window NYSE {ARROW61_START}..{ARROW61_END} sessions={len(target)} "
        f"{target[0] if target else 'none'}..{target[-1] if target else 'none'} (not scored)",
        f"dates_pulled={pulled_s}",
        f"dates_skipped_already_on_disk={skip_disk_s}",
        f"dates_skipped_not_a_session={skip_ns_s}",
        f"workers={workers} theta_concurrency={theta_n} cpu_count={cpu}",
        f"output bars={VIRGIN_BARS} eligibility={VIRGIN_ELIGIBILITY} manifest={VIRGIN_MANIFEST} iwm={VIRGIN_IWM}",
        "",
        f"sessions_attempted={n_sess}",
        f"name_days_eligible={n_elig}",
        f"unique_symbols={ok['symbol'].n_unique() if n_elig else 0}",
        f"1m_rows={n_rows}",
        f"mean_bars_per_name_day={mean_bars:.1f}",
        f"name_days_pdv_ge_10m={n_10m}",
        f"manifest pulled={n_pulled} empty={n_empty} missing={n_miss}",
        f"failures={len(failures)}",
        f"iwm_sessions={iwm_disk} iwm_ok={iwm_ok} iwm_fail={iwm_fail}",
        f"wall_s={wall_s:.1f} wall_min={wall_s / 60:.1f}",
        first5_note,
        f"name_days_with_04:00_print={n_0400}",
        f"name_days_first_print_after_07:30={n_after}",
        dec_line,
        "",
    ]
    if failures:
        lines.append("failure sample (up to 20):")
        for rec in failures[:20]:
            lines.append(
                f"  {rec.get('symbol')} {rec.get('error_class')} {rec.get('error_message', '')[:120]}"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "tape61_ingest.txt"
    out.write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {out}", flush=True)


def run_arrow61(*, workers: int | None = None, theta_concurrency: int = 8, force: bool = False) -> int:
    _assert_virgin_tree()
    ensure_virgin_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    theta_n = max(1, min(8, int(theta_concurrency)))
    t0 = time.monotonic()
    target = arrow61_sessions()
    expected = list(ARROW61_EXPECTED)
    skipped_not_session = [d for d in expected if d not in set(target)]
    extra = [d for d in target if d not in set(expected)]
    already = manifest_session_dates()
    pulled = ohlc_dates_to_pull(target, already, force=force)
    skipped_disk = [d for d in target if d in already and d not in pulled]
    print(
        f"ingest start mode=arrow61 span={ARROW61_START}..{ARROW61_END} "
        f"sessions={len(target)} to_pull={len(pulled)} skipped_disk={len(skipped_disk)} "
        f"skipped_not_session={len(skipped_not_session)} "
        f"endpoint=stock_history_ohlc interval={INTERVAL} venue={VENUE} "
        f"window=04:00-16:00ET workers={workers} theta_concurrency={theta_n} "
        f"cpu_count={cpu} output={VIRGIN_BARS} do_not_touch=data/full,data/bars "
        f"do_not_rebuild=2025-12-17..2025-12-31 no_arrow_62",
        flush=True,
    )
    if extra:
        print(f"NYSE sessions in window not in expected list: {extra}", flush=True)
    if skipped_not_session:
        print(
            f"expected dates that are not NYSE sessions (skipped): {skipped_not_session}",
            flush=True,
        )
    if not SYMBOLS.exists():
        raise FileNotFoundError(f"missing {SYMBOLS}; reuse Lab A common list, do not overwrite")
    symbols = pl.read_parquet(SYMBOLS)["symbol"].to_list()
    print(f"commons={len(symbols)} from {SYMBOLS} (read-only)", flush=True)
    client = get_shared_client()
    limiter = ThetaLimiter(theta_n)

    eod, eod_fail = pull_eod(
        client, limiter, symbols, workers, force, chunks=ARROW61_EOD_CHUNKS
    )
    eod_all = load_virgin_eod()
    if eod_all.height == 0:
        eod_all = eod
    new_elig = with_pdv_10m_flag(
        build_eligibility(
            eod_all,
            symbols,
            target,
            is_warmup=True,
            max_close=MAX_CLOSE_VIRGIN,
            sessions_for_prior=arrow61_prior_calendar(),
        )
    )
    _append_eligibility(new_elig)
    n_ok = new_elig.filter(pl.col("eligible")).height
    print(
        f"arrow61 eligibility name-days={new_elig.height} eligible={n_ok} "
        f"sessions={len(target)} wrote={VIRGIN_ELIGIBILITY}",
        flush=True,
    )

    print("pull IWM 04:00-16:00 for 2025-12-01..16 into data/virgin/bench", flush=True)
    iwm_ok, iwm_fail = pull_iwm(
        client=client,
        limiter=limiter,
        force=force,
        sessions=target,
        warmup=set(target),
    )

    first5 = pulled[:5]
    rest = pulled[5:]
    jobs5 = _jobs_for(new_elig, first5, warmup=set(target)) if first5 else []
    print(
        f"phase 1: first sessions {first5[0] if first5 else 'none'}.."
        f"{first5[-1] if first5 else 'none'} jobs={len(jobs5)}",
        flush=True,
    )
    t1 = time.monotonic()
    rows5, ok5, fail5, fail_a = _run_jobs(
        jobs5, client=client, limiter=limiter, workers=workers, force=force, job_name="arrow61_first"
    )
    elapsed5 = time.monotonic() - t1
    n5 = new_elig.filter(pl.col("eligible") & pl.col("session_date").is_in(first5)).height if first5 else 0
    remain_nd = new_elig.filter(pl.col("eligible") & pl.col("session_date").is_in(rest)).height if rest else 0
    eta_s = (elapsed5 / n5 * remain_nd) if n5 else 0.0
    first5_note = (
        f"after_first_5_sessions elapsed_s={elapsed5:.1f} name_days={n5} rows={rows5} "
        f"remaining_name_days={remain_nd} eta_min={eta_s / 60:.1f} (estimate)"
    )
    print(first5_note, flush=True)

    jobs_rest = _jobs_for(new_elig, rest, warmup=set(target)) if rest else []
    print(f"phase 2: remaining arrow61 jobs={len(jobs_rest)}", flush=True)
    rows_r, ok_r, fail_r, fail_b = _run_jobs(
        jobs_rest, client=client, limiter=limiter, workers=workers, force=force, job_name="arrow61_rest"
    )
    failures = eod_fail + fail_a + fail_b
    print(
        f"pull done rows={rows5 + rows_r} ok_jobs={ok5 + ok_r} fail_jobs={fail5 + fail_r} "
        f"eod_fail={len(eod_fail)}",
        flush=True,
    )
    print("append manifest + 04:00 stats for new dates only", flush=True)
    man_new, n_0400, n_after = _append_manifest(new_elig, workers)
    ok_new = new_elig.filter(pl.col("eligible"))
    man_slice = man_new
    if man_new.height and ok_new.height:
        new_dates = list({_as_date(x) for x in ok_new["session_date"].to_list()})
        man_slice = man_new.filter(pl.col("session_date").is_in(new_dates))
    dec_all = december_2025_sessions()
    holes = []
    for d in dec_all:
        folder = VIRGIN_BARS / d.isoformat()
        if not folder.exists() or not any(folder.glob("*.parquet")):
            holes.append(d)
    wall = time.monotonic() - t0
    _write_report_61(
        target=target,
        pulled=pulled,
        skipped_disk=skipped_disk,
        skipped_not_session=skipped_not_session,
        elig=new_elig,
        man=man_slice,
        workers=workers,
        theta_n=limiter.concurrency,
        cpu=cpu,
        wall_s=wall,
        failures=failures,
        n_0400=n_0400,
        n_after=n_after,
        first5_note=first5_note,
        iwm_ok=iwm_ok,
        iwm_fail=iwm_fail,
        holes=holes,
    )
    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 61",
        "",
        "Ingest only. Rest of December 2025 (2025-12-01..2025-12-16) into data/virgin/.",
        f"Sessions={len(target)} pulled={len(pulled)} skipped_disk={len(skipped_disk)} "
        f"skipped_not_session={len(skipped_not_session)}.",
        "Did not score engines. Did not touch data/full or Lab A data/bars. "
        "Did not rebuild 2025-12-17..2025-12-31. No Arrow 62.",
        f"eligible name-days={n_ok} failures={len(failures)} wall_min={wall / 60:.1f}.",
        (
            "December 2025 on virgin is complete."
            if not holes
            else "December 2025 holes: " + ", ".join(d.isoformat() for d in holes)
        ),
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0


def _write_report_67(
    *,
    target: list[date],
    pulled: list[date],
    skipped_disk: list[date],
    skipped_not_session: list[date],
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
    iwm_ok: int,
    iwm_fail: int,
    holes: list[date],
    cover_ok: bool,
) -> None:
    ok = elig.filter(pl.col("eligible"))
    n_elig = ok.height
    n_sess = ok["session_date"].n_unique() if n_elig else 0
    n_rows = int(man["rows"].sum()) if man.height else 0
    n_pulled = man.filter(pl.col("status") == "pulled").height if man.height else 0
    n_empty = man.filter(pl.col("status") == "empty").height if man.height else 0
    n_miss = man.filter(pl.col("status") == "missing").height if man.height else 0
    mean_bars = n_rows / n_elig if n_elig else 0.0
    n_10m = int(ok.filter(pl.col("pdv_ge_10m")).height) if n_elig and "pdv_ge_10m" in ok.columns else 0
    iwm_disk = len([d for d in target if virgin_iwm_path(d).exists()])
    pulled_s = ", ".join(d.isoformat() for d in pulled) if pulled else "none"
    skip_disk_s = ", ".join(d.isoformat() for d in skipped_disk) if skipped_disk else "none"
    skip_ns_s = ", ".join(d.isoformat() for d in skipped_not_session) if skipped_not_session else "none"
    if holes:
        cover_line = "Sep–Nov 2025 on virgin has holes: " + ", ".join(d.isoformat() for d in holes)
    elif cover_ok:
        cover_line = (
            "virgin+full now cover 2025-09 through 2026-08 "
            "(Sep–Nov 2025 + Dec 2025 + Jan–May 2026 on virgin; Jun–Aug 2026 on data/full)."
        )
    else:
        cover_line = (
            "Sep–Nov 2025 on virgin is complete; check Dec 2025 / 2026 study / full Jun–Aug for holes."
        )
    lines = [
        "Arrow 67 — September–November 2025 into data/virgin/ (ingest, not a book)",
        "No fills. No $200 verdict. Did not score engines. Did not touch data/full or Lab A data/bars. "
        "Did not rebuild December 2025 or January–May 2026 already on virgin. No Arrow 68.",
        f"venue={VENUE} interval={INTERVAL} window=04:00-16:00ET last_bar=15:59",
        "eligibility: common stock + ETP denylist, prior_close [$1, $80], prior DV >= $1M, "
        "$10M is a filter column not an ingest wall, no 400 cap",
        f"window NYSE {ARROW67_START}..{ARROW67_END} sessions={len(target)} "
        f"{target[0] if target else 'none'}..{target[-1] if target else 'none'} (not scored)",
        f"dates_pulled={pulled_s}",
        f"dates_skipped_already_on_disk={skip_disk_s}",
        f"dates_skipped_not_a_session={skip_ns_s}",
        f"labor_day={ARROW67_LABOR_DAY.isoformat()} thanksgiving={ARROW67_THANKSGIVING.isoformat()} "
        "(not sessions; not pulled)",
        f"workers={workers} theta_concurrency={theta_n} cpu_count={cpu}",
        f"output bars={VIRGIN_BARS} eligibility={VIRGIN_ELIGIBILITY} manifest={VIRGIN_MANIFEST} iwm={VIRGIN_IWM}",
        "",
        f"sessions_attempted={n_sess}",
        f"name_days_eligible={n_elig}",
        f"unique_symbols={ok['symbol'].n_unique() if n_elig else 0}",
        f"1m_rows={n_rows}",
        f"mean_bars_per_name_day={mean_bars:.1f}",
        f"name_days_pdv_ge_10m={n_10m}",
        f"manifest pulled={n_pulled} empty={n_empty} missing={n_miss}",
        f"failures={len(failures)}",
        f"iwm_sessions={iwm_disk} iwm_ok={iwm_ok} iwm_fail={iwm_fail}",
        f"wall_s={wall_s:.1f} wall_min={wall_s / 60:.1f}",
        first5_note,
        f"name_days_with_04:00_print={n_0400}",
        f"name_days_first_print_after_07:30={n_after}",
        cover_line,
        "",
    ]
    if failures:
        lines.append("failure sample (up to 20):")
        for rec in failures[:20]:
            lines.append(
                f"  {rec.get('symbol')} {rec.get('error_class')} {rec.get('error_message', '')[:120]}"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "tape67_ingest.txt"
    out.write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {out}", flush=True)


def _folder_has_bars(root, d: date) -> bool:
    folder = root / d.isoformat()
    return folder.exists() and any(folder.glob("*.parquet"))


def run_arrow67(*, workers: int | None = None, theta_concurrency: int = 8, force: bool = False) -> int:
    _assert_virgin_tree()
    ensure_virgin_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    theta_n = max(1, min(8, int(theta_concurrency)))
    t0 = time.monotonic()
    target = arrow67_sessions()
    skipped_not_session = list(arrow67_non_sessions())
    already = manifest_session_dates()
    pulled = ohlc_dates_to_pull(
        target, already, force=force, start=ARROW67_START, end=ARROW67_END
    )
    skipped_disk = [d for d in target if d in already and d not in pulled]
    print(
        f"ingest start mode=arrow67 span={ARROW67_START}..{ARROW67_END} "
        f"sessions={len(target)} to_pull={len(pulled)} skipped_disk={len(skipped_disk)} "
        f"skipped_not_session={len(skipped_not_session)} "
        f"endpoint=stock_history_ohlc interval={INTERVAL} venue={VENUE} "
        f"window=04:00-16:00ET workers={workers} theta_concurrency={theta_n} "
        f"cpu_count={cpu} output={VIRGIN_BARS} do_not_touch=data/full,data/bars "
        f"do_not_rebuild=2025-12,2026-01..05 no_arrow_68",
        flush=True,
    )
    if skipped_not_session:
        print(
            f"weekdays in window that are not NYSE sessions (skipped): {skipped_not_session}",
            flush=True,
        )
    print(
        f"not pulled: labor_day={ARROW67_LABOR_DAY} thanksgiving={ARROW67_THANKSGIVING} "
        f"dec_or_later>={date(2025, 12, 1)} before_window<={date(2025, 8, 29)}",
        flush=True,
    )
    if not SYMBOLS.exists():
        raise FileNotFoundError(f"missing {SYMBOLS}; reuse Lab A common list, do not overwrite")
    symbols = pl.read_parquet(SYMBOLS)["symbol"].to_list()
    print(f"commons={len(symbols)} from {SYMBOLS} (read-only)", flush=True)
    client = get_shared_client()
    limiter = ThetaLimiter(theta_n)

    eod, eod_fail = pull_eod(
        client, limiter, symbols, workers, force, chunks=ARROW67_EOD_CHUNKS
    )
    eod_all = load_virgin_eod()
    if eod_all.height == 0:
        eod_all = eod
    new_elig = with_pdv_10m_flag(
        build_eligibility(
            eod_all,
            symbols,
            target,
            is_warmup=True,
            max_close=MAX_CLOSE_VIRGIN,
            sessions_for_prior=arrow67_prior_calendar(),
        )
    )
    _append_eligibility(new_elig)
    n_ok = new_elig.filter(pl.col("eligible")).height
    print(
        f"arrow67 eligibility name-days={new_elig.height} eligible={n_ok} "
        f"sessions={len(target)} wrote={VIRGIN_ELIGIBILITY}",
        flush=True,
    )

    print("pull IWM 04:00-16:00 for 2025-09-02..11-28 into data/virgin/bench", flush=True)
    iwm_ok, iwm_fail = pull_iwm(
        client=client,
        limiter=limiter,
        force=force,
        sessions=target,
        warmup=set(target),
    )

    first5 = pulled[:5]
    rest = pulled[5:]
    jobs5 = _jobs_for(new_elig, first5, warmup=set(target)) if first5 else []
    print(
        f"phase 1: first sessions {first5[0] if first5 else 'none'}.."
        f"{first5[-1] if first5 else 'none'} jobs={len(jobs5)}",
        flush=True,
    )
    t1 = time.monotonic()
    rows5, ok5, fail5, fail_a = _run_jobs(
        jobs5, client=client, limiter=limiter, workers=workers, force=force, job_name="arrow67_first"
    )
    elapsed5 = time.monotonic() - t1
    n5 = new_elig.filter(pl.col("eligible") & pl.col("session_date").is_in(first5)).height if first5 else 0
    remain_nd = new_elig.filter(pl.col("eligible") & pl.col("session_date").is_in(rest)).height if rest else 0
    eta_s = (elapsed5 / n5 * remain_nd) if n5 else 0.0
    first5_note = (
        f"after_first_5_sessions elapsed_s={elapsed5:.1f} name_days={n5} rows={rows5} "
        f"remaining_name_days={remain_nd} eta_min={eta_s / 60:.1f} (estimate)"
    )
    print(first5_note, flush=True)

    jobs_rest = _jobs_for(new_elig, rest, warmup=set(target)) if rest else []
    print(f"phase 2: remaining arrow67 jobs={len(jobs_rest)}", flush=True)
    rows_r, ok_r, fail_r, fail_b = _run_jobs(
        jobs_rest, client=client, limiter=limiter, workers=workers, force=force, job_name="arrow67_rest"
    )
    failures = eod_fail + fail_a + fail_b
    print(
        f"pull done rows={rows5 + rows_r} ok_jobs={ok5 + ok_r} fail_jobs={fail5 + fail_r} "
        f"eod_fail={len(eod_fail)}",
        flush=True,
    )
    print("append manifest + 04:00 stats for new dates only", flush=True)
    man_new, n_0400, n_after = _append_manifest(new_elig, workers)
    ok_new = new_elig.filter(pl.col("eligible"))
    man_slice = man_new
    if man_new.height and ok_new.height:
        new_dates = list({_as_date(x) for x in ok_new["session_date"].to_list()})
        man_slice = man_new.filter(pl.col("session_date").is_in(new_dates))
    holes = []
    for d in target:
        if not _folder_has_bars(VIRGIN_BARS, d):
            holes.append(d)
    cover_ok = (
        not holes
        and _folder_has_bars(VIRGIN_BARS, date(2025, 12, 1))
        and _folder_has_bars(VIRGIN_BARS, date(2025, 12, 31))
        and _folder_has_bars(VIRGIN_BARS, date(2026, 1, 2))
        and _folder_has_bars(VIRGIN_BARS, date(2026, 5, 29))
        and _folder_has_bars(FULL_BARS, date(2026, 6, 1))
        and _folder_has_bars(FULL_BARS, date(2026, 8, 31))
    )
    wall = time.monotonic() - t0
    _write_report_67(
        target=target,
        pulled=pulled,
        skipped_disk=skipped_disk,
        skipped_not_session=skipped_not_session,
        elig=new_elig,
        man=man_slice,
        workers=workers,
        theta_n=limiter.concurrency,
        cpu=cpu,
        wall_s=wall,
        failures=failures,
        n_0400=n_0400,
        n_after=n_after,
        first5_note=first5_note,
        iwm_ok=iwm_ok,
        iwm_fail=iwm_fail,
        holes=holes,
        cover_ok=cover_ok,
    )
    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 67",
        "",
        "Ingest only. September–November 2025 (2025-09-02..2025-11-28) into data/virgin/.",
        f"Sessions={len(target)} pulled={len(pulled)} skipped_disk={len(skipped_disk)} "
        f"skipped_not_session={len(skipped_not_session)}.",
        "Did not score engines. Did not touch data/full or Lab A data/bars. "
        "Did not rebuild December 2025 or January–May 2026. No Arrow 68.",
        f"eligible name-days={n_ok} failures={len(failures)} wall_min={wall / 60:.1f}.",
        (
            "virgin+full now cover 2025-09 through 2026-08."
            if cover_ok and not holes
            else (
                "Sep–Nov holes: " + ", ".join(d.isoformat() for d in holes)
                if holes
                else "Sep–Nov 2025 on virgin is complete."
            )
        ),
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0


def _write_report_69(
    *,
    target: list[date],
    pulled: list[date],
    skipped_disk: list[date],
    skipped_not_session: list[date],
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
    iwm_ok: int,
    iwm_fail: int,
    holes: list[date],
) -> None:
    ok = elig.filter(pl.col("eligible"))
    n_elig = ok.height
    n_sess = ok["session_date"].n_unique() if n_elig else 0
    n_rows = int(man["rows"].sum()) if man.height else 0
    n_pulled = man.filter(pl.col("status") == "pulled").height if man.height else 0
    n_empty = man.filter(pl.col("status") == "empty").height if man.height else 0
    n_miss = man.filter(pl.col("status") == "missing").height if man.height else 0
    mean_bars = n_rows / n_elig if n_elig else 0.0
    n_10m = int(ok.filter(pl.col("pdv_ge_10m")).height) if n_elig and "pdv_ge_10m" in ok.columns else 0
    iwm_disk = len([d for d in target if virgin_iwm_path(d).exists()])
    pulled_s = ", ".join(d.isoformat() for d in pulled) if pulled else "none"
    skip_disk_s = ", ".join(d.isoformat() for d in skipped_disk) if skipped_disk else "none"
    skip_ns_s = ", ".join(d.isoformat() for d in skipped_not_session) if skipped_not_session else "none"
    if holes:
        cover_line = "August 2025 on virgin has holes: " + ", ".join(d.isoformat() for d in holes)
    else:
        cover_line = (
            "August 2025 warmup is on virgin so September 2025 leftover lookback is complete."
        )
    lines = [
        "Arrow 69 — August 2025 warmup into data/virgin/ (ingest, not a book)",
        "No fills. No $200 verdict. Did not score engines. Did not touch data/full or Lab A data/bars. "
        "Did not rebuild September 2025 or later. No Arrow 70.",
        f"venue={VENUE} interval={INTERVAL} window=04:00-16:00ET last_bar=15:59",
        "eligibility: common stock + ETP denylist, prior_close [$1, $80], prior DV >= $1M, "
        "$10M is a filter column not an ingest wall, no 400 cap",
        f"window NYSE {ARROW69_START}..{ARROW69_END} sessions={len(target)} "
        f"{target[0] if target else 'none'}..{target[-1] if target else 'none'} (not scored)",
        f"dates_pulled={pulled_s}",
        f"dates_skipped_already_on_disk={skip_disk_s}",
        f"dates_skipped_not_a_session={skip_ns_s}",
        f"workers={workers} theta_concurrency={theta_n} cpu_count={cpu}",
        f"output bars={VIRGIN_BARS} eligibility={VIRGIN_ELIGIBILITY} manifest={VIRGIN_MANIFEST} iwm={VIRGIN_IWM}",
        "",
        f"sessions_attempted={n_sess}",
        f"name_days_eligible={n_elig}",
        f"unique_symbols={ok['symbol'].n_unique() if n_elig else 0}",
        f"1m_rows={n_rows}",
        f"mean_bars_per_name_day={mean_bars:.1f}",
        f"name_days_pdv_ge_10m={n_10m}",
        f"manifest pulled={n_pulled} empty={n_empty} missing={n_miss}",
        f"failures={len(failures)}",
        f"iwm_sessions={iwm_disk} iwm_ok={iwm_ok} iwm_fail={iwm_fail}",
        f"wall_s={wall_s:.1f} wall_min={wall_s / 60:.1f}",
        first5_note,
        f"name_days_with_04:00_print={n_0400}",
        f"name_days_first_print_after_07:30={n_after}",
        cover_line,
        "",
    ]
    if failures:
        lines.append("failure sample (up to 20):")
        for rec in failures[:20]:
            lines.append(
                f"  {rec.get('symbol')} {rec.get('error_class')} {rec.get('error_message', '')[:120]}"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / "tape69_ingest.txt"
    out.write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {out}", flush=True)


def run_arrow69(*, workers: int | None = None, theta_concurrency: int = 8, force: bool = False) -> int:
    _assert_virgin_tree()
    ensure_virgin_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    theta_n = max(1, min(8, int(theta_concurrency)))
    t0 = time.monotonic()
    target = arrow69_sessions()
    skipped_not_session = list(arrow69_non_sessions())
    already = manifest_session_dates()
    pulled = ohlc_dates_to_pull(
        target, already, force=force, start=ARROW69_START, end=ARROW69_END
    )
    skipped_disk = [d for d in target if d in already and d not in pulled]
    print(
        f"ingest start mode=arrow69 span={ARROW69_START}..{ARROW69_END} "
        f"sessions={len(target)} to_pull={len(pulled)} skipped_disk={len(skipped_disk)} "
        f"skipped_not_session={len(skipped_not_session)} "
        f"endpoint=stock_history_ohlc interval={INTERVAL} venue={VENUE} "
        f"window=04:00-16:00ET workers={workers} theta_concurrency={theta_n} "
        f"cpu_count={cpu} output={VIRGIN_BARS} do_not_touch=data/full,data/bars "
        f"do_not_rebuild=2025-09.. later no_arrow_70",
        flush=True,
    )
    if skipped_not_session:
        print(
            f"weekdays in window that are not NYSE sessions (skipped): {skipped_not_session}",
            flush=True,
        )
    print(
        f"not pulled: sep_or_later>={date(2025, 9, 2)} before_window<={date(2025, 7, 31)}",
        flush=True,
    )
    if not SYMBOLS.exists():
        raise FileNotFoundError(f"missing {SYMBOLS}; reuse Lab A common list, do not overwrite")
    symbols = pl.read_parquet(SYMBOLS)["symbol"].to_list()
    print(f"commons={len(symbols)} from {SYMBOLS} (read-only)", flush=True)
    client = get_shared_client()
    limiter = ThetaLimiter(theta_n)

    eod, eod_fail = pull_eod(
        client, limiter, symbols, workers, force, chunks=ARROW69_EOD_CHUNKS
    )
    eod_all = load_virgin_eod()
    if eod_all.height == 0:
        eod_all = eod
    new_elig = with_pdv_10m_flag(
        build_eligibility(
            eod_all,
            symbols,
            target,
            is_warmup=True,
            max_close=MAX_CLOSE_VIRGIN,
            sessions_for_prior=arrow69_prior_calendar(),
        )
    )
    _append_eligibility(new_elig)
    n_ok = new_elig.filter(pl.col("eligible")).height
    print(
        f"arrow69 eligibility name-days={new_elig.height} eligible={n_ok} "
        f"sessions={len(target)} wrote={VIRGIN_ELIGIBILITY}",
        flush=True,
    )

    print("pull IWM 04:00-16:00 for 2025-08-01..08-29 into data/virgin/bench", flush=True)
    iwm_ok, iwm_fail = pull_iwm(
        client=client,
        limiter=limiter,
        force=force,
        sessions=target,
        warmup=set(target),
    )

    first5 = pulled[:5]
    rest = pulled[5:]
    jobs5 = _jobs_for(new_elig, first5, warmup=set(target)) if first5 else []
    print(
        f"phase 1: first sessions {first5[0] if first5 else 'none'}.."
        f"{first5[-1] if first5 else 'none'} jobs={len(jobs5)}",
        flush=True,
    )
    t1 = time.monotonic()
    rows5, ok5, fail5, fail_a = _run_jobs(
        jobs5, client=client, limiter=limiter, workers=workers, force=force, job_name="arrow69_first"
    )
    elapsed5 = time.monotonic() - t1
    n5 = new_elig.filter(pl.col("eligible") & pl.col("session_date").is_in(first5)).height if first5 else 0
    remain_nd = new_elig.filter(pl.col("eligible") & pl.col("session_date").is_in(rest)).height if rest else 0
    eta_s = (elapsed5 / n5 * remain_nd) if n5 else 0.0
    first5_note = (
        f"after_first_5_sessions elapsed_s={elapsed5:.1f} name_days={n5} rows={rows5} "
        f"remaining_name_days={remain_nd} eta_min={eta_s / 60:.1f} (estimate)"
    )
    print(first5_note, flush=True)

    jobs_rest = _jobs_for(new_elig, rest, warmup=set(target)) if rest else []
    print(f"phase 2: remaining arrow69 jobs={len(jobs_rest)}", flush=True)
    rows_r, ok_r, fail_r, fail_b = _run_jobs(
        jobs_rest, client=client, limiter=limiter, workers=workers, force=force, job_name="arrow69_rest"
    )
    failures = eod_fail + fail_a + fail_b
    print(
        f"pull done rows={rows5 + rows_r} ok_jobs={ok5 + ok_r} fail_jobs={fail5 + fail_r} "
        f"eod_fail={len(eod_fail)}",
        flush=True,
    )
    print("append manifest + 04:00 stats for new dates only", flush=True)
    man_new, n_0400, n_after = _append_manifest(new_elig, workers)
    ok_new = new_elig.filter(pl.col("eligible"))
    man_slice = man_new
    if man_new.height and ok_new.height:
        new_dates = list({_as_date(x) for x in ok_new["session_date"].to_list()})
        man_slice = man_new.filter(pl.col("session_date").is_in(new_dates))
    holes = []
    for d in target:
        if not _folder_has_bars(VIRGIN_BARS, d):
            holes.append(d)
    wall = time.monotonic() - t0
    _write_report_69(
        target=target,
        pulled=pulled,
        skipped_disk=skipped_disk,
        skipped_not_session=skipped_not_session,
        elig=new_elig,
        man=man_slice,
        workers=workers,
        theta_n=limiter.concurrency,
        cpu=cpu,
        wall_s=wall,
        failures=failures,
        n_0400=n_0400,
        n_after=n_after,
        first5_note=first5_note,
        iwm_ok=iwm_ok,
        iwm_fail=iwm_fail,
        holes=holes,
    )
    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 69",
        "",
        "Ingest only. August 2025 warmup (2025-08-01..2025-08-29) into data/virgin/.",
        f"Sessions={len(target)} pulled={len(pulled)} skipped_disk={len(skipped_disk)} "
        f"skipped_not_session={len(skipped_not_session)}.",
        "Did not score engines. Did not touch data/full or Lab A data/bars. "
        "Did not rebuild September 2025 or later. No Arrow 70.",
        f"eligible name-days={n_ok} failures={len(failures)} wall_min={wall / 60:.1f}.",
        (
            "August 2025 warmup is on virgin so September 2025 leftover lookback is complete."
            if not holes
            else "August 2025 holes: " + ", ".join(d.isoformat() for d in holes)
        ),
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0


