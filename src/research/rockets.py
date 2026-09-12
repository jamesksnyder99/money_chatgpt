from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _read_session_bars, _split_by_symbol
from research.arrow4 import _filter_track_a, _filter_track_b
from research.fills import tradeable_mask
from research.signals import MINUTE_0944, MINUTE_1159, RTH_OPEN, bar_time
from research.split import develop_holdout

ET = ZoneInfo("America/New_York")

PRICE_LO = 1.0
PRICE_HI = 20.0
ROCKET_MULT = 1.10
MIN_PRIORS = 5
LOOKBACK = 10


def median_prior_window(prior_vols: list[float], *, min_n: int = MIN_PRIORS, lookback: int = LOOKBACK) -> float | None:
    """Median of up to `lookback` prior same-window volumes. None if fewer than min_n."""
    if len(prior_vols) < min_n:
        return None
    use = [float(v) for v in prior_vols[-lookback:]]
    if len(use) < min_n:
        return None
    med = float(statistics.median(use))
    if med <= 0:
        return None
    return med


def window_tradeable(bars: pl.DataFrame) -> pl.DataFrame:
    if bars.height == 0:
        return bars
    return bars.filter(tradeable_mask(bars)).sort("bar_start")


def window_volume(bars: pl.DataFrame) -> float:
    ok = window_tradeable(bars)
    if ok.height == 0:
        return 0.0
    return float(ok["volume"].fill_null(0).sum())


def _launch_bucket(ts: datetime) -> str:
    t = bar_time(ts)
    if t < RTH_OPEN:
        return "pre"
    if t <= MINUTE_0944:
        return "first15"
    return "after0945"


def scan_name_day(
    bars: pl.DataFrame,
    prior_close: float,
    prior_vols: list[float],
) -> dict:
    """Classify one name-day. status skip if <5 prior window volumes (no invented rel vol)."""
    out = {
        "status": "skip",
        "rocket": False,
        "max_ext": None,
        "launch_ts": None,
        "launch_hour": None,
        "launch_bucket": None,
        "peak_ts": None,
        "minutes_to_peak": None,
        "end_ext": None,
        "gave_back": None,
        "still_10": None,
        "rel_vol": None,
        "today_vol": 0.0,
    }
    med = median_prior_window(prior_vols)
    if med is None:
        return out
    if prior_close is None or prior_close <= 0:
        return out

    ok = window_tradeable(bars)
    today_vol = float(ok["volume"].fill_null(0).sum()) if ok.height else 0.0
    rel = today_vol / med
    out["status"] = "ok"
    out["today_vol"] = today_vol
    out["rel_vol"] = rel
    if ok.height == 0:
        return out

    times = ok["bar_start"].to_list()
    highs = [float(x) for x in ok["high"].to_list()]
    closes = [float(x) for x in ok["close"].to_list()]
    session_high = max(highs)
    max_ext = session_high / float(prior_close) - 1.0
    out["max_ext"] = max_ext
    thresh = ROCKET_MULT * float(prior_close)
    launch_ts = None
    for ts, h in zip(times, highs):
        if h >= thresh - 1e-12:
            launch_ts = ts
            break
    peak_ts = None
    for ts, h in zip(times, highs):
        if h >= session_high - 1e-12:
            peak_ts = ts
            break
    end_close = closes[-1]
    for ts, c in zip(reversed(times), reversed(closes)):
        if bar_time(ts) == MINUTE_1159:
            end_close = c
            break
    end_ext = end_close / float(prior_close) - 1.0
    out["end_ext"] = end_ext
    out["still_10"] = end_ext >= 0.10 - 1e-12
    out["gave_back"] = 1 if end_ext < 0.5 * max_ext - 1e-12 else 0

    rocket = session_high >= thresh - 1e-12
    out["rocket"] = rocket
    if rocket and launch_ts is not None:
        out["launch_ts"] = launch_ts
        out["launch_hour"] = bar_time(launch_ts).hour
        out["launch_bucket"] = _launch_bucket(launch_ts)
        out["peak_ts"] = peak_ts
        if peak_ts is not None:
            delta = (peak_ts - launch_ts).total_seconds() / 60.0
            out["minutes_to_peak"] = max(0.0, delta)
    return out


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = (p / 100.0) * (len(ys) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    w = pos - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def _fmt_f(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _vol_one(d: date) -> tuple[str, dict[str, float]]:
    df = _read_session_bars(d)
    iso = d.isoformat()
    if df.height == 0:
        return iso, {}
    ok = df.filter(tradeable_mask(df))
    if ok.height == 0:
        return iso, {}
    g = ok.group_by("symbol").agg(pl.col("volume").fill_null(0).sum().alias("v"))
    return iso, {str(r["symbol"]): float(r["v"]) for r in g.iter_rows(named=True)}


def _scan_one(args: tuple) -> list[dict]:
    session_iso, elig_rows, vol_hist, track_a, track_b = args
    session = date.fromisoformat(session_iso)
    bars = _read_session_bars(session)
    if bars.height == 0 or not elig_rows:
        return []
    keep = {r["symbol"] for r in elig_rows}
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    out: list[dict] = []
    for rec in elig_rows:
        sym = rec["symbol"]
        prior_c = rec["prior_close"]
        hist = vol_hist.get(sym) or []
        prior_vols = [v for iso, v in hist if iso < session_iso]
        sdf = by_sym.get(sym, pl.DataFrame())
        row = scan_name_day(sdf, float(prior_c), prior_vols)
        row["session"] = session_iso
        row["symbol"] = sym
        row["prior_close"] = float(prior_c)
        row["prior_dv"] = float(rec["prior_dv"] or 0.0)
        row["track_a"] = (session_iso, sym) in track_a
        row["track_b"] = (session_iso, sym) in track_b
        out.append(row)
    return out


def _keys(df: pl.DataFrame) -> set[tuple[str, str]]:
    if df.height == 0:
        return set()
    out = set()
    for rec in df.select("session_date", "symbol").iter_rows(named=True):
        d = rec["session_date"]
        iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        out.add((iso, str(rec["symbol"])))
    return out


def _slice_rows(rows: list[dict], sessions: set[str]) -> list[dict]:
    return [r for r in rows if r["session"] in sessions]


def _block(title: str, rows: list[dict]) -> list[str]:
    ok = [r for r in rows if r["status"] == "ok"]
    skipped = [r for r in rows if r["status"] == "skip"]
    n_ok = len(ok)
    rockets = [r for r in ok if r["rocket"]]
    r3 = [r for r in rockets if (r["rel_vol"] or 0) >= 3.0 - 1e-12]
    r5 = [r for r in rockets if (r["rel_vol"] or 0) >= 5.0 - 1e-12]
    v3 = [r for r in ok if (r["rel_vol"] or 0) >= 3.0 - 1e-12]
    v5 = [r for r in ok if (r["rel_vol"] or 0) >= 5.0 - 1e-12]

    def _n_pct(n: int) -> str:
        if n_ok <= 0:
            return f"{n} (n/a)"
        return f"{n} ({100.0 * n / n_ok:.2f}%)"

    def _ext_count(thr: float) -> int:
        return sum(1 for r in ok if r["max_ext"] is not None and r["max_ext"] >= thr - 1e-12)

    hours = {h: 0 for h in range(7, 12)}
    buckets = {"pre": 0, "first15": 0, "after0945": 0}
    for r in r3:
        h = r["launch_hour"]
        if h in hours:
            hours[h] += 1
        b = r["launch_bucket"]
        if b in buckets:
            buckets[b] += 1

    def _dist(label: str, xs: list[float]) -> str:
        return (
            f"  {label}: n={len(xs)} median={_fmt_f(statistics.median(xs) if xs else None)} "
            f"p90={_fmt_f(_percentile(xs, 90))}"
        )

    def _rocket_stats(label: str, rs: list[dict]) -> list[str]:
        maxs = [float(r["max_ext"]) for r in rs if r["max_ext"] is not None]
        mins = [float(r["minutes_to_peak"]) for r in rs if r["minutes_to_peak"] is not None]
        ends = [float(r["end_ext"]) for r in rs if r["end_ext"] is not None]
        still = sum(1 for r in rs if r["still_10"])
        gave = sum(1 for r in rs if r["gave_back"] == 1)
        n = len(rs)
        frac_s = f"{still / n:.3f}" if n else "n/a"
        frac_g = f"{gave / n:.3f}" if n else "n/a"
        return [
            f"{label}:",
            _dist("max_ext", maxs),
            _dist("minutes_to_peak", mins),
            _dist("end_ext", ends),
            f"  still >= +10% at 11:59: {still}/{n} ({frac_s})",
            f"  gave_back (end_ext < 0.5*max_ext): {gave}/{n} ({frac_g})",
        ]

    ta = sum(1 for r in r3 if r["track_a"])
    tb = sum(1 for r in r3 if r["track_b"])
    lines = [
        title,
        f"eligible $1-$20 name-days with enough history (>=5 prior windows): {n_ok}",
        f"skipped for <5 prior sessions (no invented rel vol): {len(skipped)}",
        f"max_ext >= 10%: {_n_pct(_ext_count(0.10))}",
        f"max_ext >= 15%: {_n_pct(_ext_count(0.15))}",
        f"max_ext >= 20%: {_n_pct(_ext_count(0.20))}",
        f"max_ext >= 50%: {_n_pct(_ext_count(0.50))}",
        f"rel_vol >= 3x (among enough-history): {len(v3)}",
        f"rel_vol >= 5x (among enough-history): {len(v5)}",
        f"rocket ∩ rel_vol>=3x: {len(r3)}",
        f"rocket ∩ rel_vol>=5x: {len(r5)}",
        "",
        "launch-clock histogram (rockets ∩ rel_vol>=3x):",
    ]
    for h in range(7, 12):
        lines.append(f"  {h:02d}: {hours[h]}")
    lines.append("pre / 09:30-09:44 / after 09:45 (rockets ∩ rel_vol>=3x):")
    lines.append(f"  pre: {buckets['pre']}")
    lines.append(f"  first15: {buckets['first15']}")
    lines.append(f"  after0945: {buckets['after0945']}")
    lines.append("")
    lines.extend(_rocket_stats("all rockets (max_ext>=10%)", rockets))
    lines.append("")
    lines.extend(_rocket_stats("rockets ∩ rel_vol>=3x", r3))
    n3 = len(r3)
    lines.append(
        f"Track A gate (prior_close $10-30, $5M ADV, eligible): {ta}/{n3} of >=3x rockets"
    )
    lines.append(
        f"Track B gate (prior_close $10-50, $5M ADV, 400/day cap): {tb}/{n3} of >=3x rockets"
    )
    return lines


def _paragraph(study: list[dict], develop: list[dict], holdout: list[dict]) -> str:
    ok = [r for r in study if r["status"] == "ok"]
    rockets = [r for r in ok if r["rocket"]]
    r3 = [r for r in rockets if (r["rel_vol"] or 0) >= 3.0 - 1e-12]
    n_ok = len(ok)
    n_r = len(rockets)
    n3 = len(r3)
    hours = {h: 0 for h in range(7, 12)}
    buckets = {"pre": 0, "first15": 0, "after0945": 0}
    for r in r3:
        if r["launch_hour"] in hours:
            hours[r["launch_hour"]] += 1
        if r["launch_bucket"] in buckets:
            buckets[r["launch_bucket"]] += 1
    peak_hour = max(hours, key=hours.get) if n3 else None
    ta = sum(1 for r in r3 if r["track_a"])
    tb = sum(1 for r in r3 if r["track_b"])
    dev_r = sum(1 for r in develop if r["status"] == "ok" and r["rocket"])
    hol_r = sum(1 for r in holdout if r["status"] == "ok" and r["rocket"])
    dev_ok = sum(1 for r in develop if r["status"] == "ok")
    hol_ok = sum(1 for r in holdout if r["status"] == "ok")
    loc = (
        f"The >=3x rockets launch mostly in hour {peak_hour:02d} ET "
        f"(pre={buckets['pre']}, 09:30-09:44={buckets['first15']}, after 09:45={buckets['after0945']})"
        if n3
        else "No >=3x rockets printed in-window"
    )
    pct = f"{100.0 * n_r / n_ok:.2f}%" if n_ok else "n/a"
    return (
        f"They are in the file: {n_r} name-days ({pct} of {n_ok} $1-$20 eligible with "
        f">=5 prior windows) print a session high >= +10% vs prior close between 07:30 and 11:59, "
        f"and {n3} of those also print >=3x relative volume. {loc}. "
        f"Develop (through 2026-07-30) has {dev_r} rockets / {dev_ok} name-days; "
        f"holdout (from 2026-07-31) has {hol_r} / {hol_ok}. "
        f"Lab tracks delete most of this field: Track A keeps {ta}/{n3} of the >=3x rockets "
        f"and Track B's $10+/ $5M / 400-cap keeps {tb}/{n3} — the rest are under $10 or lack ADV, "
        f"which is why Arrow 3-15 never saw them. This is a count, not a book."
    )


def run_rockets(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    study = study_sessions()
    print(
        f"research start mode=rockets workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "diagnostic only; not Arrow 16; no fills; no 12:00-16:00; no new pull. "
        "universe=eligibility.parquet prior_close[$1,$20].",
        flush=True,
    )
    elig = pl.read_parquet(ELIGIBILITY)
    px = elig.filter(
        pl.col("eligible")
        & pl.col("prior_close").is_not_null()
        & (pl.col("prior_close") >= PRICE_LO)
        & (pl.col("prior_close") <= PRICE_HI)
    )
    study_set = {d.isoformat() for d in study}
    a_path = ELIGIBILITY.parent / "eligibility_a.parquet"
    b_path = ELIGIBILITY.parent / "eligibility_b.parquet"
    if a_path.exists():
        track_a_df = pl.read_parquet(a_path)
    else:
        track_a_df = _filter_track_a(elig)
    if b_path.exists():
        track_b_df = pl.read_parquet(b_path)
    else:
        track_b_df, _capped = _filter_track_b(elig)
    track_a = _keys(track_a_df)
    track_b = _keys(track_b_df)

    print("pass 1: window volumes 07:30-11:59 over warmup+study", flush=True)
    vol_by_session: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "rockets_vol")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_vol_one, d): d for d in all_sess}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            vol_by_session[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    vol_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [d.isoformat() for d in all_sess]:
        for sym, v in vol_by_session.get(iso, {}).items():
            vol_hist.setdefault(sym, []).append((iso, v))

    by_session_elig: dict[str, list[dict]] = {}
    for rec in px.select("session_date", "symbol", "prior_close", "prior_dollar_volume").iter_rows(
        named=True
    ):
        d = rec["session_date"]
        iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if iso not in study_set:
            continue
        by_session_elig.setdefault(iso, []).append(
            {
                "symbol": str(rec["symbol"]),
                "prior_close": rec["prior_close"],
                "prior_dv": rec["prior_dollar_volume"],
            }
        )

    jobs = []
    for d in study:
        iso = d.isoformat()
        jobs.append((iso, by_session_elig.get(iso, []), vol_hist, track_a, track_b))

    print(f"pass 2: scan {len(jobs)} study sessions for rockets", flush=True)
    prog2 = Progress(len(jobs), "rockets_scan")
    prog2.start_heartbeat()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_scan_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk)
            last = chunk[0]["session"] if chunk else ""
            prog2.mark(last, rows=len(chunk))
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    _write_report(rows, workers, cpu, develop, holdout, study)
    return 0


def _write_report(rows, workers, cpu, develop, holdout, study) -> None:
    dev_set = {d.isoformat() for d in develop}
    hol_set = {d.isoformat() for d in holdout}
    study_set = {d.isoformat() for d in study}
    study_rows = _slice_rows(rows, study_set)
    dev_rows = _slice_rows(rows, dev_set)
    hol_rows = _slice_rows(rows, hol_set)

    lines = [
        "Rocket scan — diagnostic (not a book, not Arrow 16, not a $200 pass/fail)",
        f"account n/a  no fills  no cap8  no shorts  no 12:00-16:00  no new pull",
        f"universe: eligibility.parquet (full file, not Track A/B)",
        f"price: prior_close in [${PRICE_LO:.0f}, ${PRICE_HI:.0f}]",
        f"rocket: tradeable session high 07:30-11:59 >= {ROCKET_MULT:.2f} * prior_close",
        f"rel_vol: today 07:30-11:59 volume / median of that window over prior {LOOKBACK} sessions on disk; "
        f"skip if fewer than {MIN_PRIORS} priors",
        f"study n={len(study)} {study[0]}..{study[-1]}",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "",
    ]
    lines.extend(_block("STUDY-WIDE", study_rows))
    lines.append("")
    lines.extend(_block("DEVELOP (through 2026-07-30)", dev_rows))
    lines.append("")
    lines.extend(_block("HOLDOUT (from 2026-07-31)", hol_rows))
    lines.append("")
    lines.append("Are they in the file, and when do they launch in our window:")
    lines.append(_paragraph(study_rows, dev_rows, hol_rows))
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "rockets_scan.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
