from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl
from thetadata.errors import NoDataFoundError

from ingest.bars import normalize_ohlc, split_sessions
from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ELIGIBILITY, FULL_IWM, REPORTS, ensure_dirs
from ingest.progress import Progress
from ingest.run import END_TIME, INTERVAL, START_TIME, VENUE, month_groups
from ingest.theta_pool import ThetaLimiter, call_theta
from research.arrow3 import _fmt, _read_session_bars, _split_by_symbol, _summarize
from research.arrow4 import _filter_track_a, _filter_track_b
from research.arrow5 import _maps_from_elig
from research.arrow10 import _build_bars15
from research.book import replay_session
from research.character import dv_ranks
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, stitch_15m
from research.fills import is_tradeable
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies15 import control_c5_ema9
from theta.client import get_shared_client

ET = ZoneInfo("America/New_York")

CAP8 = {"max_positions": 8, "max_entries": 16, "max_risk_outstanding": 1600.0}
SHORT_POP = {"dv_min": 0.80, "gap_min": 0.015, "or_w_min": 0.025}
EXPERIMENTS = (
    ("B", "kernel|nofilter", False),
    ("B", "kernel|ssr_borrow", True),
    ("A", "kernel|nofilter", False),
    ("A", "kernel|ssr_borrow", True),
)


def _iwm_path(d: date):
    return FULL_IWM / f"{d.isoformat()}.parquet"


def pull_iwm(*, workers: int, theta_concurrency: int = 8, force: bool = False) -> int:
    """IWM 1m 07:30-11:59 warmup+study into data/full/bench/IWM. Does not touch data/bars."""
    ensure_dirs()
    FULL_IWM.mkdir(parents=True, exist_ok=True)
    sessions = list(WARMUP_SESSIONS) + study_sessions()
    groups = month_groups(sessions)
    client = get_shared_client()
    limiter = ThetaLimiter(theta_concurrency)
    n_ok = 0
    for group in groups:
        need = [d for d in group if force or not _iwm_path(d).exists()]
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
            is_w = all(d in set(WARMUP_SESSIONS) for d in need)
            norm = normalize_ohlc(df, "IWM", is_warmup=is_w)
            parts = split_sessions(norm, set(need))
            for d in need:
                part = parts.get(d)
                path = _iwm_path(d)
                if part is None or part.height == 0:
                    normalize_ohlc(pl.DataFrame(), "IWM", is_w).write_parquet(path)
                else:
                    part.write_parquet(path)
                n_ok += 1
            print(f"IWM wrote {start_d}..{end_d} days={len(need)}", flush=True)
        except NoDataFoundError:
            for d in need:
                normalize_ohlc(pl.DataFrame(), "IWM", False).write_parquet(_iwm_path(d))
            print(f"IWM no data {start_d}..{end_d}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"IWM pull failed {start_d}..{end_d}: {type(exc).__name__}", flush=True)
    print(f"IWM sessions on disk={n_ok}/{len(sessions)} dir={FULL_IWM}", flush=True)
    return n_ok


def load_iwm() -> dict[str, pl.DataFrame]:
    out: dict[str, pl.DataFrame] = {}
    if not FULL_IWM.exists():
        return out
    for p in FULL_IWM.glob("*.parquet"):
        out[p.stem] = pl.read_parquet(p)
    return out


def _iwm_open_at_or_after(df: pl.DataFrame, ts: datetime) -> float | None:
    if df is None or df.height == 0:
        return None
    times = df["bar_start"].to_list()
    opens = df["open"].to_list()
    closes = df["close"].to_list()
    vols = df["volume"].to_list()
    for t, o, c, v in zip(times, opens, closes, vols):
        if t < ts:
            continue
        if is_tradeable(o, c, v):
            return float(o)
    return None


def trade_alpha(tr: dict, iwm: pl.DataFrame | None) -> float | None:
    if iwm is None:
        return None
    e = _iwm_open_at_or_after(iwm, tr["entry_ts"])
    x = _iwm_open_at_or_after(iwm, tr["exit_ts"])
    if e is None or x is None or e <= 0:
        return None
    iwm_ret = x / e - 1.0
    return tr["pnl"] - tr["side"] * tr["shares"] * tr["entry_px"] * iwm_ret


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, bars15, sess_order, filters_on = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty = {
        "session": session_iso,
        "track": track,
        "filters": filters_on,
        "pnl": 0.0,
        "trades": [],
    }
    if elig_df.height == 0:
        return empty
    bars = _read_session_bars(session)
    if bars.height == 0:
        return empty
    keep = set(elig_df["symbol"].to_list())
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    prior_c = {
        s: float(m["prior_close"]) for s, m in meta.items() if m.get("prior_close") is not None
    }
    ranks = dv_ranks(prior_dv)
    sigs = []
    for sym, sdf in by_sym.items():
        m = meta.get(sym) or {}
        pc = m.get("prior_close")
        pc = float(pc) if pc is not None else None
        rank = ranks.get(sym, 0.0)
        rng = opening_range(sdf)
        or_w = rng[2] if rng else None
        or_high = rng[0] if rng else None
        gap = session_gap(sdf, pc)
        if not short_kernel_pop(rank, gap, or_w, **SHORT_POP) or or_high is None:
            continue
        stitched = stitch_15m(sym, session_iso, sess_order, bars15)
        for sig in control_c5_ema9(sdf, stitched, or_high):
            if sig.side != -1:
                continue
            if ema_stack(stitched, sig.signal_ts) != "short":
                continue
            sigs.append(sig)
    trades = replay_session(
        by_sym,
        sigs,
        prior_dv,
        prior_close=prior_c,
        ssr_filter=filters_on,
        borrow_filter=filters_on,
        **CAP8,
    )
    return {
        "session": session_iso,
        "track": track,
        "filters": filters_on,
        "pnl": sum(t.pnl for t in trades),
        "trades": [
            {
                "pnl": t.pnl,
                "win": t.pnl > 0,
                "risk": t.risk,
                "side": t.side,
                "shares": t.shares,
                "entry_px": t.entry_px,
                "entry_ts": t.entry_ts,
                "exit_ts": t.exit_ts,
            }
            for t in trades
        ],
    }


def run_arrow18(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow18 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "kernel only B/A c5_ema9|cap8; leak-fixed flatten; SSR+borrow variants. "
        "No discovery grid. No Arrow 19.",
        flush=True,
    )
    print("pull IWM 07:30-11:59 bench (does not touch data/bars)", flush=True)
    pull_iwm(workers=workers, theta_concurrency=8)
    iwm = load_iwm()
    print(f"IWM sessions loaded={len(iwm)}", flush=True)

    elig_all = pl.read_parquet(ELIGIBILITY)
    a_path = ELIGIBILITY.parent / "eligibility_a.parquet"
    b_path = ELIGIBILITY.parent / "eligibility_b.parquet"
    if a_path.exists():
        track_a = pl.read_parquet(a_path)
    else:
        track_a = _filter_track_a(elig_all)
        track_a.write_parquet(a_path)
    if b_path.exists():
        track_b = pl.read_parquet(b_path)
        capped = True
    else:
        track_b, capped = _filter_track_b(elig_all)
        track_b.write_parquet(b_path)
    print(f"Track A rows={track_a.height} Track B rows={track_b.height}", flush=True)
    _pc, _dv = _maps_from_elig(elig_all)
    print("precompute 15m closes for ema15 stitch", flush=True)
    bars15 = _build_bars15(all_sess, workers)
    print(f"bars15 keys={len(bars15)}", flush=True)

    jobs = []
    for track, _name, filt in EXPERIMENTS:
        path = str(a_path if track == "A" else b_path)
        for d in develop + holdout:
            jobs.append((d.isoformat(), track, path, bars15, sess_order, filt))
    prog = Progress(len(jobs), "arrow18")
    prog.start_heartbeat()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.append(chunk)
            prog.mark(chunk["session"], rows=len(chunk["trades"]))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    _write_reports(rows, workers, cpu, develop, holdout, capped, iwm)
    return 0


def _write_reports(rows, workers, cpu, develop, holdout, capped, iwm) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    results = []
    for track, name, filt in EXPERIMENTS:
        subset = [r for r in rows if r["track"] == track and r["filters"] is filt]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        n_d, n_h = len(develop), len(holdout)

        def _alpha_pack(trades, sessions):
            alphas = []
            skips = 0
            by_day = {d.isoformat(): 0.0 for d in sessions}
            for t in trades:
                iso = t["entry_ts"].date().isoformat() if hasattr(t["entry_ts"], "date") else str(t["entry_ts"])[:10]
                a = trade_alpha(t, iwm.get(iso))
                if a is None:
                    skips += 1
                    continue
                by_day[iso] = by_day.get(iso, 0.0) + a
                alphas.append(a)
            daily = [by_day.get(d.isoformat(), 0.0) for d in sessions]
            return daily, skips, len(alphas)

        a_dev, skip_d, n_ad = _alpha_pack(tr_dev, develop)
        a_hol, skip_h, n_ah = _alpha_pack(tr_hol, holdout)
        results.append(
            {
                "track": track,
                "name": name,
                "filters": filt,
                "develop": _summarize(daily_dev, tr_dev, n_d),
                "holdout": _summarize(daily_hol, tr_hol, n_h),
                "alpha_dev": _summarize(a_dev, tr_dev, n_d),
                "alpha_hol": _summarize(a_hol, tr_hol, n_h),
                "alpha_skip_dev": skip_d,
                "alpha_skip_hol": skip_h,
                "n_alpha_dev": n_ad,
                "n_alpha_hol": n_ah,
            }
        )

    honesty = [
        "HONESTY:",
        "Holdout has been used to pick rings (or25 -> c5_ema9 -> cap8). +179/day is not an expected value. It is a contaminated holdout print.",
        "Arithmetic: 200 risk x avgR x trades/day. Develop avgR ~0.05 and ~5 fills/day ~ 50/day. Holdout avgR ~0.23 x ~3.5 ~ 160/day.",
        "300/day on this cell needs more R, more fills, or more dollars at risk — not another 5-min pattern.",
        "SSR/borrow were unmodelled before this arrow. Flatten leak: a zero-volume 11:59 bar no longer orphans a live position.",
    ]

    lines = [
        "Arrow 18 — leak-fixed engine, SSR/borrow proxies, dispersion, IWM alpha; kernel only",
        "Not a discovery grid. Not a 190-book rerun. No 09:31. No longs.",
        *honesty,
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "cap8=8/16/1600 RISK_PER_IDEA=200 flatten=11:59. IWM bench 07:30-11:59 same-window next-open-to-exit-open.",
        "Borrow proxy is crude (gap<=-5% and prior DV < 10M). SSR proxy is last close <= 0.90 * prior_close.",
        "No Arrow 19.",
        "",
        f"{'track':<6} {'id':<20} {'filt':<6} {'dev $/day':>10} {'hold $/day':>11} "
        f"{'hold n':>7} {'avgR':>7} {'t_hold':>7} {'ci95 hold':>22} {'a_hold':>10}",
    ]
    for r in results:
        h = r["holdout"]
        ci = f"[{h['ci_lo']:.1f},{h['ci_hi']:.1f}]"
        lines.append(
            f"{r['track']:<6} {r['name']:<20} {'on' if r['filters'] else 'off':<6} "
            f"{r['develop']['per_day']:10.2f} {h['per_day']:11.2f} {h['n_trades']:7d} "
            f"{h['avg_r']:7.3f} {h['t_stat']:7.2f} {ci:>22} {r['alpha_hol']['per_day']:10.2f}"
        )
        lines.append(f"       develop {_fmt(r['develop'], holdout=False)}")
        lines.append(f"       holdout {_fmt(r['holdout'], holdout=True)}")
        lines.append(
            f"       IWM alpha develop $/day={r['alpha_dev']['per_day']:.2f} "
            f"(n={r['n_alpha_dev']} skip={r['alpha_skip_dev']}) "
            f"holdout $/day={r['alpha_hol']['per_day']:.2f} "
            f"(n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow18_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 18",
        "",
        "Repairs then kernel-only rescore. Flatten leak fixed (zero-volume 11:59 no longer orphans).",
        "SSR proxy (last close <= 0.90 * prior close) and crude borrow proxy (gap<=-5% and prior DV < 10M).",
        "Dispersion: std/se/t/bootstrap CI on $/day. IWM same-window alpha. Holdout is contaminated; not EV.",
        "Four rows: B no-filter, B SSR+borrow, A no-filter, A SSR+borrow. Did not rerun Arrow 3-16 grids.",
        "",
    ]
    bits.extend(honesty)
    bits.append("")
    for r in results:
        bits.append(
            f"- Track {r['track']} {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day trades_holdout={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} t={r['holdout']['t_stat']:.2f} "
            f"IWM_alpha_hold ${r['alpha_hol']['per_day']:.2f}/day."
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
