from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _read_session_bars, _split_by_symbol, _summarize
from research.arrow4 import _filter_track_a, _filter_track_b
from research.arrow5 import _maps_from_elig
from research.arrow10 import _build_bars15
from research.book import concurrent_stats, replay_session
from research.character import dv_ranks
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, stitch_15m
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies13 import five_min_close_below_ema9
from research.strategies14 import union_c5_or_orlow

ET = ZoneInfo("America/New_York")

# Kernel = B/short_gap15|c5_ema9. Short only. Capacity stretch + one union door.
CAP5 = {"max_positions": 5, "max_entries": 10, "max_risk_outstanding": 1000.0}
CAP8 = {"max_positions": 8, "max_entries": 16, "max_risk_outstanding": 1600.0}
CAP10 = {"max_positions": 10, "max_entries": 20, "max_risk_outstanding": 2000.0}
EXPERIMENTS = (
    ("c5_ema9|cap5", {**CAP5}),
    ("c5_ema9|cap8", {**CAP8}),
    ("c5_ema9|cap10", {**CAP10}),
    ("c5_ema9|cap8|2R", {**CAP8, "take_2r": True}),
    ("c5_ema9|cap8|trail", {**CAP8, "trail_after_1r": True}),
    ("c5_ema9|cap8|union", {**CAP8}),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
SHORT_POP = {"dv_min": 0.80, "gap_min": 0.015, "or_w_min": 0.025}


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, bars15, sess_order = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty_rows = [
        {
            "session": session_iso,
            "track": track,
            "name": n,
            "pnl": 0.0,
            "trades": [],
            "peak": 0,
            "mean_conc": 0.0,
        }
        for n in IDS
    ]
    if elig_df.height == 0:
        return {"rows": empty_rows}
    bars = _read_session_bars(session)
    if bars.height == 0:
        return {"rows": empty_rows}
    keep = set(elig_df["symbol"].to_list())
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    ranks = dv_ranks(prior_dv)

    kernel: list = []
    union: list = []
    for sym, sdf in by_sym.items():
        m = meta.get(sym) or {}
        prior_c = m.get("prior_close")
        prior_c = float(prior_c) if prior_c is not None else None
        rank = ranks.get(sym, 0.0)
        rng = opening_range(sdf)
        or_w = rng[2] if rng else None
        gap = session_gap(sdf, prior_c)
        if not short_kernel_pop(rank, gap, or_w, **SHORT_POP):
            continue
        stitched = stitch_15m(sym, session_iso, sess_order, bars15)
        if rng is not None:
            for sig in five_min_close_below_ema9(sdf, stitched, rng[0]):
                if sig.side != -1:
                    continue
                if ema_stack(stitched, sig.signal_ts) != "short":
                    continue
                kernel.append(sig)
        for sig in union_c5_or_orlow(sdf, stitched):
            if sig.side != -1:
                continue
            if ema_stack(stitched, sig.signal_ts) != "short":
                continue
            union.append(sig)

    rows = []
    for exp_id, kwargs in EXPERIMENTS:
        sigs = union if exp_id.endswith("|union") else kernel
        sigs = [s for s in sigs if s.side == -1]
        trades = replay_session(by_sym, sigs, prior_dv, **kwargs)
        peak, mean_c = concurrent_stats(trades)
        rows.append(
            {
                "session": session_iso,
                "track": track,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
                "peak": peak,
                "mean_conc": mean_c,
            }
        )
    return {"rows": rows}


def run_arrow14(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow14 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "kernel=B/short_gap15|c5_ema9; cap5/8/10; cap8+2R/trail/union. "
        "RISK_PER_IDEA=200. Short only. No Arrow 15.",
        flush=True,
    )
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
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for d in develop + holdout:
            jobs.append((d.isoformat(), track, path, bars15, sess_order))
    prog = Progress(len(jobs), "arrow14")
    prog.start_heartbeat()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk["rows"])
            prog.mark(chunk["rows"][0]["session"] if chunk["rows"] else "", rows=len(chunk["rows"]))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    _write_reports(rows, workers, cpu, develop, holdout, capped)
    return 0


def _write_reports(rows, workers, cpu, develop, holdout, capped) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    results = []
    for track in ("A", "B"):
        for exp_id in IDS:
            subset = [r for r in rows if r["track"] == track and r["name"] == exp_id]
            pnl_map = {r["session"]: r for r in subset}
            daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
            daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
            tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
            tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
            peaks_dev = [pnl_map.get(d.isoformat(), {}).get("peak", 0) for d in develop]
            peaks_hol = [pnl_map.get(d.isoformat(), {}).get("peak", 0) for d in holdout]
            conc_dev = [pnl_map.get(d.isoformat(), {}).get("mean_conc", 0.0) for d in develop]
            conc_hol = [pnl_map.get(d.isoformat(), {}).get("mean_conc", 0.0) for d in holdout]
            n_d, n_h = len(develop), len(holdout)
            results.append(
                {
                    "track": track,
                    "name": exp_id,
                    "develop": _summarize(daily_dev, tr_dev, n_d),
                    "holdout": _summarize(daily_hol, tr_hol, n_h),
                    "mean_peak_dev": sum(peaks_dev) / n_d if n_d else 0.0,
                    "mean_peak_hol": sum(peaks_hol) / n_h if n_h else 0.0,
                    "mean_conc_dev": sum(conc_dev) / n_d if n_d else 0.0,
                    "mean_conc_hol": sum(conc_hol) / n_h if n_h else 0.0,
                }
            )

    def _promotable(r) -> bool:
        return r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0

    promo = [r for r in results if _promotable(r)]
    false_green = [
        r for r in results if r["holdout"]["clears_200"] and r["develop"]["per_day"] < 0
    ]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(
            f"{r['track']}/{r['name']}" for r in promo
        )
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 14 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass."
        )

    ctrl = {
        trk: next(r for r in results if r["track"] == trk and r["name"] == "c5_ema9|cap5")
        for trk in ("A", "B")
    }

    def _n_line(r) -> str:
        c = ctrl[r["track"]]
        hd, hh = c["develop"]["n_trades"], c["holdout"]["n_trades"]
        nd, nh = r["develop"]["n_trades"], r["holdout"]["n_trades"]

        def _rat(n, b):
            if b <= 0:
                return "n/a"
            return f"{n / b:.2f}x"

        return (
            f"  {r['track']}/{r['name']}: develop n={nd} vs cap5 {hd} ({_rat(nd, hd)}) "
            f"holdout n={nh} vs cap5 {hh} ({_rat(nh, hh)}); "
            f"mean_conc dev={r['mean_conc_dev']:.2f} hold={r['mean_conc_hol']:.2f} "
            f"(cap5 {c['mean_conc_dev']:.2f}/{c['mean_conc_hol']:.2f}); "
            f"mean_peak dev={r['mean_peak_dev']:.2f} hold={r['mean_peak_hol']:.2f}"
        )

    lines = [
        "Arrow 14 — more seats on B/short_gap15|c5_ema9 (short only)",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "Pass = holdout >= $200/day AND develop not red. RISK_PER_IDEA=200.",
        "Kernel: Q5, gap-down>=1.5%, OR>2.5%, ema15 short, 5-min close below ema9. Flatten 11:59.",
        "No Arrow 13 longs. No Q4. No 5-min ORBR. No 11:30 flatten. No Arrow 15.",
        "",
        "n and mean concurrent vs cap5 control:",
    ]
    for r in results:
        lines.append(_n_line(r))
    lines.append("")
    lines.append(
        f"{'track':<6} {'id':<22} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'mnConc':>7} {'>=200':>6}"
    )
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(
            f"{r['track']:<6} {r['name']:<22} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} {h['max_dd']:10.2f} "
            f"{r['mean_conc_hol']:7.2f} {flag:>6}"
        )
        lines.append(f"       develop {_fmt(r['develop'], holdout=False)}")
        lines.append(f"       holdout {_fmt(r['holdout'], holdout=True)}")
    if false_green:
        lines.append("")
        lines.append("NO* = holdout >= $200 but develop is red — not a pass:")
        for r in false_green:
            lines.append(
                f"  {r['track']}/{r['name']}: develop ${r['develop']['per_day']:.2f}/day holdout ${r['holdout']['per_day']:.2f}/day"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow14_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 14",
        "",
        verdict,
        "",
        "Kernel: Arrow 13 B/short_gap15|c5_ema9 (develop +$57, holdout +$164). Short only. "
        "RISK_PER_IDEA stayed 200. Caps: cap5=5/10/1000, cap8=8/16/1600, cap10=10/20/2000. "
        "Ids: cap5 control; cap8; cap10; cap8+2R; cap8+trail; cap8 union (5-min close < ema9 OR 1-min close < OR low). "
        "Did not rerun Arrow 13 longs, Q4, 5-min ORBR, or 11:30 flatten.",
        "",
        "n and mean concurrent vs cap5:",
    ]
    for r in results:
        bits.append(_n_line(r))
    bits.append("")
    bits.append("What died (holdout < $200, or holdout green with red develop):")
    for r in results:
        if _promotable(r):
            continue
        bits.append(
            f"- Track {r['track']} {r['name']}: "
            f"holdout ${r['holdout']['per_day']:.2f}/day develop ${r['develop']['per_day']:.2f}/day "
            f"trades_holdout={r['holdout']['n_trades']} avgR={r['holdout']['avg_r']:.3f}. "
            "Do not retry this exact (track, id) without a new costed reason."
        )
    if promo:
        bits.append("")
        bits.append("Promotable: " + ", ".join(f"{r['track']}/{r['name']}" for r in promo))
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
