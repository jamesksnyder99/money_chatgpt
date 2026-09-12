from __future__ import annotations

import os
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl
from thetadata.errors import NoDataFoundError

from ingest.bars import normalize_ohlc, split_sessions
from ingest.calendar import (
    EOD_END,
    EOD_START,
    WARMUP_SESSIONS,
    eod_dates_for_warmup,
    sessions_frame,
    study_sessions,
)
from ingest.eligibility import build_eligibility, build_warmup_eligibility, eod_session_dates
from ingest.manifest import Manifest
from ingest.paths import (
    ARROW02_REPORT,
    BARS_DIR,
    CALENDAR,
    ELIGIBILITY,
    EOD_ROOT,
    SPLITS,
    SYMBOLS,
    bar_path,
    ensure_dirs,
    eod_path,
)
from ingest.progress import Progress
from ingest.report import write_reports
from ingest.symbols import filter_common
from ingest.theta_pool import ThetaLimiter, call_theta
from ingest.universe import (
    candidates_from_raw,
    persist_raw_symbols,
    write_universe_report,
)
from ingest.validate import validate_warmup
from theta.client import get_shared_client

STUDY_EOD_CHUNKS: tuple[tuple[date, date, str], ...] = (
    (date(2026, 5, 29), date(2026, 5, 29), "2026-05"),
    (date(2026, 6, 1), date(2026, 6, 30), "2026-06"),
    (date(2026, 7, 1), date(2026, 7, 31), "2026-07"),
    (date(2026, 8, 1), date(2026, 8, 31), "2026-08"),
)

ET = ZoneInfo("America/New_York")
VENUE = "utp_cta"
INTERVAL = "1m"
START_TIME = time(7, 30)
END_TIME = time(12, 0)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _banner(*, mode: str, workers: int, theta_concurrency: int, cpu: int) -> None:
    print(
        f"ingest start mode={mode} span=warmup:{WARMUP_SESSIONS[0]}..{WARMUP_SESSIONS[-1]} "
        f"eod={EOD_START}..{EOD_END} endpoint=stock_history_ohlc interval={INTERVAL} "
        f"venue={VENUE} window=07:30-12:00ET workers={workers} "
        f"theta_concurrency={theta_concurrency} cpu_count={cpu} "
        f"output={BARS_DIR}",
        flush=True,
    )


def write_calendar() -> pl.DataFrame:
    ensure_dirs()
    df = sessions_frame()
    df.write_parquet(CALENDAR)
    empty_splits = pl.DataFrame(
        schema={"symbol": pl.String, "ex_date": pl.Date, "factor": pl.Float64}
    )
    empty_splits.write_parquet(SPLITS)
    print(
        f"calendar rows={df.height} warmup={df.filter(pl.col('is_warmup')).height} "
        f"study={df.filter(~pl.col('is_warmup')).height} "
        f"memorial_absent={date(2026, 5, 25) not in set(df['session_date'].to_list())} "
        f"jul3_absent={date(2026, 7, 3) not in set(df['session_date'].to_list())} "
        f"n_study={len(study_sessions())} eod_priors={eod_dates_for_warmup()}",
        flush=True,
    )
    return df


def list_commons(client, limiter: ThetaLimiter, manifest: Manifest, force: bool) -> list[str]:
    if not force and SYMBOLS.exists() and manifest.already_ok(
        endpoint="stock_list_symbols",
        symbol="*",
        start_date="",
        end_date="",
    ):
        df = pl.read_parquet(SYMBOLS)
        symbols = df["symbol"].to_list()
        print(f"LIST resume commons={len(symbols)}", flush=True)
        return symbols
    df, elapsed = call_theta(limiter, client.stock_list_symbols)
    col = "symbol" if "symbol" in df.columns else df.columns[0]
    raw = [str(x) for x in df[col].to_list()]
    commons = filter_common(raw)
    pl.DataFrame({"symbol": commons}).write_parquet(SYMBOLS)
    manifest.append(
        endpoint="stock_list_symbols",
        symbol="*",
        row_count=len(commons),
        elapsed_s=elapsed,
        ok=True,
    )
    print(
        f"LIST raw={len(raw)} commons={len(commons)} elapsed={elapsed:.2f}s "
        f"first5={commons[:5]}",
        flush=True,
    )
    return commons


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
    limiter,
    manifest,
    symbol: str,
    force: bool,
    start: date = EOD_START,
    end: date = EOD_END,
    chunk: str = "warmup",
) -> tuple[str, bool, str, str, float]:
    path = eod_path(symbol, chunk)
    start_s, end_s = start.isoformat(), end.isoformat()
    if (
        not force
        and path.exists()
        and manifest.already_ok(
            endpoint="stock_history_eod",
            symbol=symbol,
            start_date=start_s,
            end_date=end_s,
        )
    ):
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
        manifest.append(
            endpoint="stock_history_eod",
            symbol=symbol,
            start_date=start_s,
            end_date=end_s,
            row_count=df.height,
            elapsed_s=elapsed,
            ok=True,
        )
        return symbol, True, "", "", elapsed
    except NoDataFoundError:
        path.parent.mkdir(parents=True, exist_ok=True)
        _empty_eod(symbol).write_parquet(path)
        manifest.append(
            endpoint="stock_history_eod",
            symbol=symbol,
            start_date=start_s,
            end_date=end_s,
            row_count=0,
            elapsed_s=0.0,
            ok=True,
        )
        return symbol, True, "", "", 0.0
    except Exception as exc:  # noqa: BLE001
        manifest.append(
            endpoint="stock_history_eod",
            symbol=symbol,
            start_date=start_s,
            end_date=end_s,
            ok=False,
            error_class=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        return symbol, False, type(exc).__name__, str(exc)[:500], 0.0


def pull_eod(
    client,
    limiter: ThetaLimiter,
    manifest: Manifest,
    symbols: list[str],
    workers: int,
    force: bool,
    start: date = EOD_START,
    end: date = EOD_END,
    chunk: str = "warmup",
) -> tuple[pl.DataFrame, list[dict]]:
    prog = Progress(len(symbols), f"eod:{chunk}")
    prog.start_heartbeat()
    failures: list[dict] = []
    print(f"EOD pulling {len(symbols)} {chunk} {start}..{end}", flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                pull_one_eod, client, limiter, manifest, sym, force, start, end, chunk
            )
            for sym in symbols
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
    files = list((EOD_ROOT / chunk).glob("*.parquet"))
    if not files:
        return pl.DataFrame(), failures
    eod = pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")
    print(f"EOD loaded rows={eod.height} files={len(files)} fails={len(failures)}", flush=True)
    return eod, failures


def load_eod_chunks(chunks: list[str] | None = None) -> pl.DataFrame:
    root = EOD_ROOT
    files: list = []
    if chunks:
        for ch in chunks:
            files.extend((root / ch).glob("*.parquet"))
    else:
        files = list(root.rglob("*.parquet"))
    if not files:
        return pl.DataFrame()
    return pl.concat([pl.read_parquet(f) for f in files], how="diagonal_relaxed")


def write_eligibility(eod: pl.DataFrame, symbols: list[str]) -> pl.DataFrame:
    elig = build_warmup_eligibility(eod, symbols)
    ELIGIBILITY.parent.mkdir(parents=True, exist_ok=True)
    elig.write_parquet(ELIGIBILITY)
    per = (
        elig.filter(pl.col("eligible"))
        .group_by("session_date")
        .len()
        .sort("session_date")
    )
    print("eligibility per session:", flush=True)
    for row in per.iter_rows(named=True):
        print(f"  {row['session_date']}: {row['len']}", flush=True)
    return elig


def _ohlc_skip(symbol: str, sessions: list[date], manifest: Manifest, force: bool) -> bool:
    if force:
        return False
    if not all(bar_path(d, symbol).exists() for d in sessions):
        return False
    start, end = min(sessions).isoformat(), max(sessions).isoformat()
    return manifest.already_ok(
        endpoint="stock_history_ohlc",
        symbol=symbol,
        start_date=start,
        end_date=end,
        interval=INTERVAL,
        venue=VENUE,
    )


def pull_one_ohlc(
    client,
    limiter,
    manifest,
    symbol: str,
    sessions: list[date],
    force: bool,
    is_warmup: bool = True,
) -> tuple[str, int, dict[date, int], bool, str, str, float]:
    sessions = sorted(sessions)
    start_d, end_d = sessions[0], sessions[-1]
    if _ohlc_skip(symbol, sessions, manifest, force):
        rows = {}
        total = 0
        for d in sessions:
            p = bar_path(d, symbol)
            n = pl.read_parquet(p).height if p.exists() else 0
            rows[d] = n
            total += n
        return symbol, total, rows, True, "", "", 0.0
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
        norm = normalize_ohlc(df, symbol, is_warmup=is_warmup)
        parts = split_sessions(norm, set(sessions))
        rows: dict[date, int] = {}
        total = 0
        for d in sessions:
            part = parts.get(d)
            path = bar_path(d, symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            if part is None or part.height == 0:
                normalize_ohlc(pl.DataFrame(), symbol, is_warmup).write_parquet(path)
                rows[d] = 0
            else:
                part.write_parquet(path)
                rows[d] = part.height
                total += part.height
        manifest.append(
            endpoint="stock_history_ohlc",
            symbol=symbol,
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            interval=INTERVAL,
            venue=VENUE,
            row_count=total,
            elapsed_s=elapsed,
            ok=True,
        )
        return symbol, total, rows, True, "", "", elapsed
    except NoDataFoundError:
        for d in sessions:
            path = bar_path(d, symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            normalize_ohlc(pl.DataFrame(), symbol, is_warmup).write_parquet(path)
        manifest.append(
            endpoint="stock_history_ohlc",
            symbol=symbol,
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            interval=INTERVAL,
            venue=VENUE,
            row_count=0,
            elapsed_s=0.0,
            ok=True,
        )
        return symbol, 0, {d: 0 for d in sessions}, True, "", "", 0.0
    except Exception as exc:  # noqa: BLE001
        manifest.append(
            endpoint="stock_history_ohlc",
            symbol=symbol,
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            interval=INTERVAL,
            venue=VENUE,
            ok=False,
            error_class=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        return symbol, 0, {}, False, type(exc).__name__, str(exc)[:500], 0.0


def month_groups(dates: list[date]) -> list[list[date]]:
    buckets: dict[tuple[int, int], list[date]] = {}
    for d in sorted(dates):
        buckets.setdefault((d.year, d.month), []).append(d)
    return [buckets[k] for k in sorted(buckets)]


def pull_bars(
    client,
    limiter: ThetaLimiter,
    manifest: Manifest,
    elig: pl.DataFrame,
    workers: int,
    force: bool,
    sessions: list[date] | None = None,
    is_warmup: bool = True,
    job_name: str = "ohlc_1m",
) -> tuple[dict[date, int], list[dict], float, int, int]:
    target = sessions or list(WARMUP_SESSIONS)
    by_sym: dict[str, list[date]] = {}
    for symbol, session in (
        elig.filter(pl.col("eligible")).select("symbol", "session_date").iter_rows()
    ):
        if session in target:
            by_sym.setdefault(str(symbol), []).append(session)
    jobs: list[tuple[str, list[date]]] = []
    for sym, dates in by_sym.items():
        for group in month_groups(dates):
            jobs.append((sym, group))
    prog = Progress(len(jobs), job_name)
    prog.start_heartbeat()
    print(
        f"BARS {len(by_sym)} symbols / {len(jobs)} month-chunks "
        f"is_warmup={is_warmup}",
        flush=True,
    )
    rows_by_session: dict[date, int] = {d: 0 for d in target}
    failures: list[dict] = []
    elapsed_sum = 0.0
    elapsed_n = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                pull_one_ohlc,
                client,
                limiter,
                manifest,
                sym,
                dates,
                force,
                is_warmup,
            )
            for sym, dates in jobs
        ]
        for i, fut in enumerate(as_completed(futs), 1):
            symbol, total, rows, ok, cls, msg, elapsed = fut.result()
            prog.mark(symbol, rows=total, elapsed_s=elapsed, ok=ok)
            if elapsed > 0:
                elapsed_sum += elapsed
                elapsed_n += 1
            if not ok:
                failures.append(
                    {
                        "symbol": symbol,
                        "session": job_name,
                        "error_class": cls,
                        "error_message": msg,
                    }
                )
            for d, n in rows.items():
                rows_by_session[d] = rows_by_session.get(d, 0) + n
            if i % 100 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    mean_s = elapsed_sum / elapsed_n if elapsed_n else 0.0
    session_ok = sum(1 for d in target if rows_by_session.get(d, 0) > 0)
    session_fail = len(target) - session_ok
    return rows_by_session, failures, mean_s, session_ok, session_fail


def run_warmup(*, workers: int, theta_concurrency: int, force: bool) -> int:
    cpu = os.cpu_count() or 1
    workers = max(1, workers)
    started = _now()
    _banner(mode="warmup", workers=workers, theta_concurrency=theta_concurrency, cpu=cpu)
    ensure_dirs()
    limiter = ThetaLimiter(theta_concurrency)
    manifest = Manifest()
    theta_start = limiter.concurrency
    failures: list[dict] = []
    extra_notes: list[str] = []

    try:
        write_calendar()
        client = get_shared_client()
        commons = list_commons(client, limiter, manifest, force)
        eod, eod_fail = pull_eod(client, limiter, manifest, commons, workers, force)
        failures.extend(eod_fail)
        elig = write_eligibility(eod, commons)
        rows_by_session, bar_fail, mean_s, sess_ok, sess_fail = pull_bars(
            client, limiter, manifest, elig, workers, force
        )
        failures.extend(bar_fail)
        issues = validate_warmup()
        extra_notes.extend(issues if issues else ["validation: no issues on warmup checks"])
        if issues:
            print("VALIDATION issues:", flush=True)
            for item in issues:
                print(f"  {item}", flush=True)
        else:
            print("VALIDATION ok", flush=True)
        ended = _now()
        write_reports(
            started=started,
            ended=ended,
            workers=workers,
            theta_concurrency_start=theta_start,
            theta_concurrency_end=limiter.concurrency,
            cpu_count=cpu,
            elig=elig,
            rows_by_session=rows_by_session,
            failures=failures,
            mean_request_s=mean_s,
            sessions_ok=sess_ok,
            sessions_fail=sess_fail,
            extra_notes=extra_notes,
        )
        print(
            f"ingest finish ok={len(failures)==0} duration={(ended-started).total_seconds():.1f}s "
            f"paths={CALENDAR}, {ELIGIBILITY}, {BARS_DIR}",
            flush=True,
        )
        return 0 if not issues else 1
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        extra_notes.append(f"fatal {type(exc).__name__}: {exc}")
        ended = _now()
        try:
            write_reports(
                started=started,
                ended=ended,
                workers=workers,
                theta_concurrency_start=theta_start,
                theta_concurrency_end=limiter.concurrency,
                cpu_count=cpu,
                elig=pl.DataFrame(
                    schema={
                        "session_date": pl.Date,
                        "symbol": pl.String,
                        "prior_close": pl.Float64,
                        "prior_volume": pl.Int64,
                        "prior_dollar_volume": pl.Float64,
                        "eligible": pl.Boolean,
                        "exclude_reason": pl.String,
                        "is_warmup": pl.Boolean,
                    }
                ),
                rows_by_session={},
                failures=failures + [
                    {
                        "symbol": "*",
                        "session": "*",
                        "error_class": type(exc).__name__,
                        "error_message": str(exc)[:500],
                    }
                ],
                mean_request_s=0.0,
                sessions_ok=0,
                sessions_fail=len(WARMUP_SESSIONS),
                extra_notes=extra_notes,
            )
        except Exception:  # noqa: BLE001
            pass
        return 1


def run_universe(*, workers: int, theta_concurrency: int, force: bool) -> tuple[int, list[str]]:
    """Optimization A+B: reserved-name retry, ETP filter, recompute warmup eligibility."""
    cpu = os.cpu_count() or 1
    workers = max(1, workers)
    _banner(mode="universe", workers=workers, theta_concurrency=theta_concurrency, cpu=cpu)
    ensure_dirs()
    limiter = ThetaLimiter(theta_concurrency)
    manifest = Manifest()
    notes: list[str] = []
    write_calendar()
    client = get_shared_client()
    raw_df, elapsed = call_theta(limiter, client.stock_list_symbols)
    persist_raw_symbols(raw_df)
    manifest.append(
        endpoint="stock_list_symbols",
        symbol="*",
        row_count=raw_df.height,
        elapsed_s=elapsed,
        ok=True,
    )
    cands, funnel, type_col = candidates_from_raw(raw_df)
    print(
        f"FUNNEL raw={funnel['raw']} regex={funnel['regex_kept']} "
        f"type_drop={funnel['type_dropped']} etp_drop={funnel['etp_dropped']} "
        f"candidates={funnel['candidates']} type_col={type_col}",
        flush=True,
    )

    reserved = ["CON", "PRN"]
    print(f"A: re-pull reserved {reserved} into {eod_path('CON').name}", flush=True)
    for sym in reserved:
        _, ok, cls, msg, _ = pull_one_eod(
            client, limiter, manifest, sym, True, EOD_START, EOD_END, "warmup"
        )
        notes.append(f"reserved {sym} eod ok={ok} file={eod_path(sym).name} {cls} {msg}".strip())
        print(notes[-1], flush=True)

    eod = load_eod_chunks(["warmup"])
    elig = build_warmup_eligibility(eod, cands)
    ELIGIBILITY.parent.mkdir(parents=True, exist_ok=True)
    elig.write_parquet(ELIGIBILITY)
    per = (
        elig.filter(pl.col("eligible"))
        .group_by("session_date")
        .len()
        .sort("session_date")
    )
    print("eligibility per session (tighter universe):", flush=True)
    for row in per.iter_rows(named=True):
        print(f"  {row['session_date']}: {row['len']}", flush=True)

    mean_n = (
        float(per["len"].mean()) if per.height else 0.0
    )
    if mean_n > 2500:
        notes.append(
            f"eligible mean {mean_n:.1f} still near Arrow 1 2757 — denylist too weak"
        )
        write_universe_report(funnel=funnel, type_col=type_col, elig=elig, notes=notes)
        return 2, cands

    # 1m for CON/PRN if they became eligible
    reserved_elig = elig.filter(
        pl.col("eligible") & pl.col("symbol").is_in(reserved)
    )
    if reserved_elig.height:
        pull_bars(
            client, limiter, manifest, reserved_elig, workers, True,
            sessions=list(WARMUP_SESSIONS), is_warmup=True, job_name="ohlc_reserved",
        )
        notes.append(f"pulled warmup 1m for eligible reserved names n={reserved_elig.height}")

    write_universe_report(funnel=funnel, type_col=type_col, elig=elig, notes=notes)
    pl.DataFrame({"symbol": cands}).write_parquet(SYMBOLS)
    return 0, cands


def run_study(*, workers: int, theta_concurrency: int, force: bool) -> int:
    cpu = os.cpu_count() or 1
    workers = max(1, workers)
    started = _now()
    study = study_sessions()
    assert date(2026, 7, 3) not in study
    assert date(2026, 6, 19) not in study
    print(
        f"ingest start mode=study span={study[0]}..{study[-1]} n={len(study)} "
        f"(no 2026-07-03, no 2026-06-19) endpoint=stock_history_ohlc interval={INTERVAL} "
        f"venue={VENUE} window=07:30-12:00ET workers={workers} "
        f"theta_concurrency={theta_concurrency} cpu_count={cpu} output={BARS_DIR}",
        flush=True,
    )
    ensure_dirs()
    limiter = ThetaLimiter(theta_concurrency)
    manifest = Manifest()
    theta_start = limiter.concurrency
    failures: list[dict] = []
    extra_notes: list[str] = []
    try:
        write_calendar()
        client = get_shared_client()
        if not SYMBOLS.exists():
            raise RuntimeError("run --mode universe first (missing symbols_common.parquet)")
        cands = pl.read_parquet(SYMBOLS)["symbol"].to_list()
        print(f"study candidates={len(cands)}", flush=True)
        for start, end, chunk in STUDY_EOD_CHUNKS:
            _, fails = pull_eod(
                client, limiter, manifest, cands, workers, force, start, end, chunk
            )
            failures.extend(fails)
        eod = load_eod_chunks(["warmup", "2026-05", "2026-06", "2026-07", "2026-08"])
        study_elig = build_eligibility(eod, cands, study, is_warmup=False)
        warmup_elig = (
            pl.read_parquet(ELIGIBILITY)
            if ELIGIBILITY.exists()
            else build_warmup_eligibility(eod, cands)
        )
        # keep warmup rows; replace/add study rows
        combined = pl.concat(
            [
                warmup_elig.filter(pl.col("session_date").is_in(list(WARMUP_SESSIONS))),
                study_elig,
            ],
            how="diagonal_relaxed",
        )
        combined.write_parquet(ELIGIBILITY)
        per = (
            study_elig.filter(pl.col("eligible"))
            .group_by("session_date")
            .len()
            .sort("session_date")
        )
        print("study eligibility per session:", flush=True)
        for row in per.iter_rows(named=True):
            print(f"  {row['session_date']}: {row['len']}", flush=True)

        rows_by_session, bar_fail, mean_s, sess_ok, sess_fail = pull_bars(
            client,
            limiter,
            manifest,
            study_elig,
            workers,
            force,
            sessions=study,
            is_warmup=False,
            job_name="ohlc_1m_study",
        )
        failures.extend(bar_fail)
        extra_notes.append("did not pull 2026-07-03 or 2026-06-19 (full closes)")
        extra_notes.append("zero-volume 1m minutes stored as Theta sent them; not trades")
        issues = validate_warmup()
        extra_notes.extend(issues if issues else ["validation: no issues"])
        if date(2026, 7, 3) in rows_by_session:
            extra_notes.append("ERROR: July 3 bars present")
        ended = _now()
        write_reports(
            started=started,
            ended=ended,
            workers=workers,
            theta_concurrency_start=theta_start,
            theta_concurrency_end=limiter.concurrency,
            cpu_count=cpu,
            elig=study_elig,
            rows_by_session=rows_by_session,
            failures=failures,
            mean_request_s=mean_s,
            sessions_ok=sess_ok,
            sessions_fail=sess_fail,
            extra_notes=extra_notes,
            title="Arrow 2 — study pull timing (Jun–Aug 2026)",
            report_path=ARROW02_REPORT,
            sessions_attempted=len(study),
        )
        extra = [
            "",
            "comparison to Arrow 1 1.54h estimate:",
            f"  wall_hours={((ended-started).total_seconds()/3600):.4f} vs est 1.54h "
            "(estimate included warmup+study; this run is study EOD+1m only)",
        ]
        text = ARROW02_REPORT.read_text(encoding="utf-8") + "\n".join(extra) + "\n"
        ARROW02_REPORT.write_text(text, encoding="utf-8")
        from ingest.paths import INGEST_REPORT

        INGEST_REPORT.write_text(text, encoding="utf-8")
        print("\n".join(extra), flush=True)
        print(
            f"ingest finish study duration={(ended-started).total_seconds():.1f}s",
            flush=True,
        )
        return 0 if not issues else 1
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL {type(exc).__name__}: {exc}", flush=True)
        traceback.print_exc()
        return 1


def run_arrow2(*, workers: int, theta_concurrency: int, force: bool) -> int:
    code, _cands = run_universe(
        workers=workers, theta_concurrency=theta_concurrency, force=force
    )
    if code != 0:
        print("universe failed or denylist too weak; not starting study pull", flush=True)
        return code
    return run_study(workers=workers, theta_concurrency=theta_concurrency, force=force)

