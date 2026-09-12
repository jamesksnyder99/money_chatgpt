from __future__ import annotations

import os
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.manifest import Manifest
from ingest.paths import BARS_DIR, ELIGIBILITY, REPORTS, bar_path, ensure_dirs
from ingest.progress import Progress
from ingest.run import month_groups, pull_one_ohlc
from ingest.theta_pool import ThetaLimiter
from research.arrow3 import (
    _build_first5_history,
    _fmt,
    _median_prior,
    _read_session_bars,
    _split_by_symbol,
    _summarize,
)
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.split import develop_holdout
from research.strategies import (
    first5_volume,
    open_drive_signals,
    or_break_signals,
    session_volume,
    swing_signals,
    vwap_reclaim_signals,
)
from theta.client import get_shared_client

ET = ZoneInfo("America/New_York")

TRACK_A_MIN_PX = 10.0
TRACK_A_MAX_PX = 30.0
TRACK_A_MIN_DV = 5_000_000.0
TRACK_B_MIN_PX = 10.0
TRACK_B_MAX_PX = 50.0
TRACK_B_MIN_DV = 5_000_000.0
TRACK_B_EXPLODE = 800
TRACK_B_CAP = 400

RULES = (
    ("cash", None),
    ("or_break", None),
    ("swing", None),
    ("open_drive", 2.0),
    ("vwap_reclaim", 10.0),
)


def _filter_track_a(elig: pl.DataFrame) -> pl.DataFrame:
    return elig.filter(
        pl.col("eligible")
        & (pl.col("prior_close") >= TRACK_A_MIN_PX)
        & (pl.col("prior_close") <= TRACK_A_MAX_PX)
        & (pl.col("prior_dollar_volume") >= TRACK_A_MIN_DV)
    )


def _filter_track_b(elig: pl.DataFrame) -> tuple[pl.DataFrame, bool]:
    raw = elig.filter(
        pl.col("prior_close").is_not_null()
        & (pl.col("prior_close") >= TRACK_B_MIN_PX)
        & (pl.col("prior_close") <= TRACK_B_MAX_PX)
        & (pl.col("prior_dollar_volume") >= TRACK_B_MIN_DV)
    )
    per = raw.group_by("session_date").len()
    max_n = int(per["len"].max()) if per.height else 0
    capped = max_n > TRACK_B_EXPLODE
    if capped:
        raw = (
            raw.sort(["session_date", "prior_dollar_volume"], descending=[False, True])
            .group_by("session_date", maintain_order=True)
            .head(TRACK_B_CAP)
        )
    return raw, capped


def _daily_counts(df: pl.DataFrame, study_only: bool = True) -> pl.DataFrame:
    x = df.filter(~pl.col("is_warmup")) if study_only and "is_warmup" in df.columns else df
    if x.height == 0:
        return pl.DataFrame({"session_date": [], "n": []})
    return x.group_by("session_date").len().rename({"len": "n"}).sort("session_date")


def pull_track_b_gaps(elig_b: pl.DataFrame, *, workers: int, theta_concurrency: int) -> dict:
    pairs: list[tuple[str, date]] = []
    for rec in elig_b.select("symbol", "session_date").iter_rows():
        sym, d = str(rec[0]), rec[1]
        if not bar_path(d, sym).exists():
            pairs.append((sym, d))
    by_sym: dict[str, list[date]] = defaultdict(list)
    for sym, d in pairs:
        by_sym[sym].append(d)
    jobs: list[tuple[str, list[date], bool]] = []
    warmup = set(WARMUP_SESSIONS)
    for sym, dates in by_sym.items():
        for group in month_groups(dates):
            is_w = all(d in warmup for d in group)
            jobs.append((sym, group, is_w))
    print(f"Track B gap 1m jobs={len(jobs)} missing_pairs={len(pairs)}", flush=True)
    if not jobs:
        return {"missing_pairs": 0, "jobs": 0, "fails": 0}
    limiter = ThetaLimiter(theta_concurrency)
    manifest = Manifest()
    client = get_shared_client()
    prog = Progress(len(jobs), "track_b_gaps")
    prog.start_heartbeat()
    fails = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                pull_one_ohlc, client, limiter, manifest, sym, dates, False, is_w
            )
            for sym, dates, is_w in jobs
        ]
        for i, fut in enumerate(as_completed(futs), 1):
            symbol, total, _rows, ok, cls, msg, elapsed = fut.result()
            prog.mark(symbol, rows=total, elapsed_s=elapsed, ok=ok)
            if not ok:
                fails += 1
                print(f"gap fail {symbol} {cls}: {msg}", flush=True)
            if i % 50 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    return {"missing_pairs": len(pairs), "jobs": len(jobs), "fails": fails}


def _session_vol_one(d: date) -> list[tuple[str, str, float]]:
    df = _read_session_bars(d)
    if df.height == 0:
        return []
    summed = df.group_by("symbol").agg(pl.col("volume").fill_null(0).sum().alias("v"))
    iso = d.isoformat()
    return [(str(r["symbol"]), iso, float(r["v"])) for r in summed.iter_rows(named=True)]


def _build_session_vol(sessions: list[date], workers: int) -> dict[str, list[tuple[str, float]]]:
    hist: dict[str, list[tuple[str, float]]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(_session_vol_one, sessions):
            for sym, iso, vol in part:
                hist.setdefault(sym, []).append((iso, vol))
    for sym in hist:
        hist[sym].sort()
    return hist


def _next_in_slice(session: date, slice_sessions: list[date]) -> date | None:
    try:
        i = slice_sessions.index(session)
    except ValueError:
        return None
    if i + 1 >= len(slice_sessions):
        return None
    return slice_sessions[i + 1]


def _replay_track_session(args: tuple) -> list[dict]:
    session_iso, track, first5, sess_vol, elig_path, slice_name = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty = [
        {"session": session_iso, "track": track, "name": n, "param": p, "pnl": 0.0, "trades": []}
        for n, p in RULES
        if n != "swing"
    ]
    if elig_df.height == 0:
        return empty
    keep = set(elig_df["symbol"].to_list())
    bars = _read_session_bars(session)
    if bars.height == 0:
        return empty
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    out = []
    for name, param in RULES:
        if name == "cash":
            out.append(
                {"session": session_iso, "track": track, "name": name, "param": param, "pnl": 0.0, "trades": []}
            )
            continue
        if name == "swing":
            continue
        sigs = []
        for sym, sdf in by_sym.items():
            m = meta.get(sym)
            if not m:
                continue
            prior = float(m["prior_close"] or 0.0)
            if name == "or_break":
                sigs.extend(or_break_signals(sdf))
            elif name == "open_drive":
                f5 = first5_volume(sdf)
                med = _median_prior(first5, sym, session)
                if med is None:
                    continue
                sigs.extend(open_drive_signals(sdf, f5, med, float(param)))
            elif name == "vwap_reclaim":
                sigs.extend(vwap_reclaim_signals(sdf, float(param), prior))
        trades = replay_session(by_sym, sigs, prior_dv)
        out.append(
            {
                "session": session_iso,
                "track": track,
                "name": name,
                "param": param,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    return out


def _swing_fill_session(args: tuple) -> dict:
    """PnL for swing fills that occur on fill_iso (signals from previous slice session)."""
    fill_iso, signal_iso, track, sess_vol, elig_path = args
    fill_d = date.fromisoformat(fill_iso)
    sig_d = date.fromisoformat(signal_iso)
    elig_sig = pl.read_parquet(elig_path).filter(pl.col("session_date") == sig_d)
    elig_fill = pl.read_parquet(elig_path).filter(pl.col("session_date") == fill_d)
    base = {
        "session": fill_iso,
        "track": track,
        "name": "swing",
        "param": None,
        "pnl": 0.0,
        "trades": [],
    }
    if elig_sig.height == 0 or elig_fill.height == 0:
        return base
    keep_fill = set(elig_fill["symbol"].to_list())
    sig_bars = _read_session_bars(sig_d)
    fill_bars = _read_session_bars(fill_d)
    if sig_bars.height == 0 or fill_bars.height == 0:
        return base
    sig_by = _split_by_symbol(sig_bars.filter(pl.col("symbol").is_in(elig_sig["symbol"].to_list())))
    fill_by = _split_by_symbol(fill_bars.filter(pl.col("symbol").is_in(list(keep_fill))))
    overnight = []
    for sym, sdf in sig_by.items():
        if sym not in keep_fill:
            continue
        so_far = session_volume(sdf, through=time(11, 50))
        med = _median_prior(sess_vol, sym, sig_d)
        overnight.extend(swing_signals(sdf, so_far, med))
    overnight = [s for s in overnight if s.symbol in fill_by]
    meta = {
        r["symbol"]: r
        for r in elig_fill.select("symbol", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    trades = replay_session(fill_by, [], prior_dv, rth_open_entries=overnight)
    return {
        "session": fill_iso,
        "track": track,
        "name": "swing",
        "param": None,
        "pnl": sum(t.pnl for t in trades),
        "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
    }


def _write_universe(track_a: pl.DataFrame, track_b: pl.DataFrame, capped: bool, pulls: dict) -> None:
    ca = _daily_counts(track_a)
    cb = _daily_counts(track_b)
    def stats(df: pl.DataFrame) -> str:
        if df.height == 0:
            return "n/a"
        n = df["n"].to_list()
        return f"mean={sum(n)/len(n):.1f} min={min(n)} max={max(n)}"
    lines = [
        "Arrow 4 — universe",
        f"Track A filter: prior_close in [10,30], prior_dollar_volume >= 5e6, existing Lab A eligible",
        f"Track A study names/day: {stats(ca)}  (Arrow 3 study mean was ~2020)",
        "Track A per session:",
    ]
    for rec in ca.iter_rows(named=True):
        lines.append(f"  {rec['session_date']}: {rec['n']}")
    lines += [
        "",
        "Track B filter: commons not ETP, prior_close in [10,50], prior_dollar_volume >= 5e6",
        f"Track B exploded past {TRACK_B_EXPLODE}/day: {capped}; cap={TRACK_B_CAP if capped else 'none'}",
        f"Track B study names/day after cap: {stats(cb)}",
        f"Track B 1m gap pull: missing_pairs={pulls.get('missing_pairs')} jobs={pulls.get('jobs')} fails={pulls.get('fails')}",
        "Did not pull 2026-07-03 or 2026-06-19 (full closes).",
        "Reused existing parquet; pulled only missing (symbol, session) 1m partitions.",
    ]
    text = "\n".join(lines) + "\n"
    (REPORTS / "arrow04_universe.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)


def run_arrow4(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow4 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    elig = pl.read_parquet(ELIGIBILITY)
    track_a = _filter_track_a(elig)
    track_b, capped = _filter_track_b(elig)
    print(
        f"Track A study mean names/day={float(_daily_counts(track_a)['n'].mean()):.1f} "
        f"Track B capped={capped} mean={float(_daily_counts(track_b)['n'].mean()):.1f}",
        flush=True,
    )
    a_path = ELIGIBILITY.parent / "eligibility_a.parquet"
    b_path = ELIGIBILITY.parent / "eligibility_b.parquet"
    a_path.parent.mkdir(parents=True, exist_ok=True)
    track_a.write_parquet(a_path)
    track_b.write_parquet(b_path)

    pulls = pull_track_b_gaps(track_b, workers=workers, theta_concurrency=8)
    _write_universe(track_a, track_b, capped, pulls)

    print("precompute first-5 and full-session volumes", flush=True)
    first5 = _build_first5_history(all_sess, workers)
    sess_vol = _build_session_vol(all_sess, workers)

    rows: list[dict] = []
    jobs = []
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for d in develop + holdout:
            jobs.append((d.isoformat(), track, first5, sess_vol, path, "study"))
    prog = Progress(len(jobs), "arrow4_same_day")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_track_session, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk)
            prog.mark(chunk[0]["session"] if chunk else "", rows=sum(len(r["trades"]) for r in chunk))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()

    swing_jobs = []
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for slc in (develop, holdout):
            for d in slc:
                nxt = _next_in_slice(d, slc)
                if nxt is None:
                    continue
                swing_jobs.append((nxt.isoformat(), d.isoformat(), track, sess_vol, path))
    prog2 = Progress(len(swing_jobs), "arrow4_swing")
    prog2.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_swing_fill_session, job) for job in swing_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rows.append(fut.result())
            prog2.mark(str(i), rows=1)
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    _write_results(rows, workers, cpu, develop, holdout, capped, pulls)
    return 0


def _write_results(rows, workers, cpu, develop, holdout, capped, pulls) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    results = []
    for track in ("A", "B"):
        for name, param in RULES:
            subset = [r for r in rows if r["track"] == track and r["name"] == name]
            if name != "cash":
                subset = [r for r in subset if r.get("param") == param]
            by_s = {}
            trades_by = {"dev": [], "hol": []}
            pnl_map = {}
            for r in subset:
                # last write wins; swing rows overwrite empty placeholders
                prev = pnl_map.get(r["session"])
                if prev is None or (name == "swing" and r["trades"]):
                    pnl_map[r["session"]] = r
            for iso, r in pnl_map.items():
                if iso in develop_set:
                    trades_by["dev"].extend(r["trades"])
                elif iso in holdout_set:
                    trades_by["hol"].extend(r["trades"])
            daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
            daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
            # cash placeholders may duplicate; use 0
            if name == "cash":
                daily_dev = [0.0] * len(develop)
                daily_hol = [0.0] * len(holdout)
                trades_by = {"dev": [], "hol": []}
            dev_sm = _summarize(daily_dev, trades_by["dev"], len(develop))
            hol_sm = _summarize(daily_hol, trades_by["hol"], len(holdout))
            results.append(
                {"track": track, "name": name, "param": param, "develop": dev_sm, "holdout": hol_sm}
            )

    clears = [
        r for r in results if r["name"] != "cash" and r["holdout"]["clears_200"]
    ]
    if clears:
        bits = [f"{r['track']}/{r['name']}" for r in clears]
        verdict = "VERDICT: HOLD OUT CLEARS $200 — " + ", ".join(bits)
    else:
        verdict = "VERDICT: FAIL — no Arrow 4 track/rule printed ≥ $200/day net on holdout"

    lines = [
        "Arrow 4 — tighter Lab A + liquid 10-50 field",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "same harness as Arrow 3 (next-bar open, costs, $200 risk, 5 pos, 10 entries, $1000 risk cap)",
        "no gap-fade; open_drive frozen Y=2.0; vwap_reclaim frozen min_price=10",
        f"Track B cap used={capped} gap_jobs={pulls.get('jobs')} gap_fails={pulls.get('fails')}",
        "swing: signal 11:30-11:50, fill next session 09:30; skip if next session out of slice or last day",
        "",
        f"{'track':<6} {'rule':<14} {'param':<8} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'maxDD':>10} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        lines.append(
            f"{r['track']:<6} {r['name']:<14} {str(r['param']):<8} "
            f"{r['develop']['per_day']:10.2f} {h['per_day']:11.2f} {h['n_trades']:7d} "
            f"{h['hit_rate']:6.3f} {h['max_dd']:10.2f} {'YES' if h['clears_200'] else 'NO':>6}"
        )
        lines.append(
            f"       develop {_fmt(r['develop'], holdout=False)}"
        )
        lines.append(
            f"       holdout {_fmt(r['holdout'], holdout=True)}"
        )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow04_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    dead = [r for r in results if r["name"] != "cash" and not r["holdout"]["clears_200"]]
    bits = [
        f"## {stamp} — Arrow 4",
        "",
        verdict,
        "",
        "Tracks: A = existing Lab A bars with prior_close [10,30] and ADV>=$5M; "
        "B = [10,50] ADV>=$5M commons not ETP, cap top 400/day because raw >800.",
        "Rules only: cash; OR-break after 09:45 of 09:30-09:44 range; next-open swing; "
        "open_drive Y=2.0 frozen; vwap_reclaim min_price=$10 frozen. No gap-fade. No Arrow 3 grids.",
        "",
        "What died:",
    ]
    for r in dead:
        bits.append(
            f"- Track {r['track']} {r['name']} param={r['param']}: "
            f"holdout ${r['holdout']['per_day']:.2f}/day develop ${r['develop']['per_day']:.2f}/day "
            f"trades_holdout={r['holdout']['n_trades']}. Do not retry this exact (track, rule, frozen param) "
            "without a new costed reason."
        )
    if clears:
        bits.append("")
        bits.append("Cleared: " + ", ".join(f"{r['track']}/{r['name']}" for r in clears))
    bits.append("")
    bits.append("Do not retry: Arrow 3 gap-fade {3,5,8} / open-drive grid / vwap {3,5,8} on the ~2000-name $1–$30 book.")
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
