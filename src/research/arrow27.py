from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ELIGIBILITY, FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _read_session_bars, _split_by_symbol, _summarize
from research.arrow4 import _filter_track_b
from research.arrow10 import _build_bars15
from research.arrow18 import load_iwm, trade_alpha
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _fmt_adv, _pack_trades, _summarize_adv
from research.arrow24 import _session_scan
from research.book import concurrent_stats, replay_session
from research.character import dv_ranks
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, stitch_15m
from research.grid import structural_grid_row
from research.harness import PRICE_FLOOR_PX5, run_rel_vol
from research.signals import MINUTE_1159
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies15 import control_c5_ema9
from research.strategies22 import hot_gate_0800
from research.strategies26 import MAX_UNDERCUT, fly_cell_ok, flush_ring_long, score_flush

ET = ZoneInfo("America/New_York")

B_CAP8 = {"max_positions": 8, "max_entries": 16, "max_risk_outstanding": 1600.0}
FLUSH_CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
    "harness_stop": True,
    "cost_gate": True,
    "flatten_at": MINUTE_1159,
}
SHORT_POP = {"dv_min": 0.80, "gap_min": 0.015, "or_w_min": 0.025}

# (id, replay kwargs). Borrow stays on. Kernel unchanged except SSR fill policy.
B_POLICIES = (
    ("B_reject", {"ssr_policy": "reject", "ssr_filter": True, "borrow_filter": True}),
    ("B_nofilter", {"ssr_policy": "off", "ssr_filter": False, "borrow_filter": True}),
    (
        "B_uptick10",
        {
            "ssr_policy": "uptick",
            "ssr_filter": False,
            "borrow_filter": True,
            "ssr_uptick_minutes": 10,
        },
    ),
    (
        "B_uptick5",
        {
            "ssr_policy": "uptick",
            "ssr_filter": False,
            "borrow_filter": True,
            "ssr_uptick_minutes": 5,
        },
    ),
    (
        "B_uptick10_cap",
        {
            "ssr_policy": "uptick",
            "ssr_filter": False,
            "borrow_filter": True,
            "ssr_uptick_minutes": 10,
            "ssr_fill_cap": 0.005,
        },
    ),
)
B_IDS = tuple(p[0] for p in B_POLICIES)
FLUSH_ID = "flush|max6"


def _session_low_one(d: date) -> tuple[str, dict[str, float]]:
    iso = d.isoformat()
    df = _read_session_bars(d)
    if df.height == 0:
        return iso, {}
    g = df.group_by("symbol").agg(pl.col("low").min().alias("lo"))
    out = {str(r["symbol"]): float(r["lo"]) for r in g.iter_rows(named=True) if r["lo"] is not None}
    return iso, out


def _pack_b_trades(trades) -> list[dict]:
    out = []
    for t in trades:
        out.append(
            {
                "pnl": t.pnl,
                "win": t.pnl > 0,
                "risk": t.risk,
                "side": t.side,
                "shares": t.shares,
                "entry_px": t.entry_px,
                "entry_ts": t.entry_ts,
                "exit_ts": t.exit_ts,
                "tag": t.tag,
            }
        )
    return out


def _replay_b(args: tuple) -> dict:
    (
        session_iso,
        elig_path,
        bars15,
        sess_order,
        lows,
        pc_by,
    ) = args
    session = date.fromisoformat(session_iso)
    empty_rows = [
        {
            "session": session_iso,
            "name": n,
            "pnl": 0.0,
            "trades": [],
            "peak": 0,
            "mean_conc": 0.0,
            "ssr_nofill": 0,
            "n_short_signals": 0,
            "n_ssr_signals": 0,
        }
        for n in B_IDS
    ]
    empty = {"session": session_iso, "rows": empty_rows}
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
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
    idx = sess_order.index(session_iso) if session_iso in sess_order else -1
    prev_iso = sess_order[idx - 1] if idx > 0 else None
    psl = dict(lows.get(prev_iso) or {}) if prev_iso else {}
    pspc = dict(pc_by.get(prev_iso) or {}) if prev_iso else {}
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
    rows = []
    for name, kw in B_POLICIES:
        st = {}
        trades = replay_session(
            by_sym,
            sigs,
            prior_dv,
            prior_close=prior_c,
            prior_session_low=psl,
            prior_session_prior_close=pspc,
            stats=st,
            **B_CAP8,
            **kw,
        )
        peak, mean_c = concurrent_stats(trades)
        rows.append(
            {
                "session": session_iso,
                "name": name,
                "pnl": sum(t.pnl for t in trades),
                "trades": _pack_b_trades(trades),
                "peak": peak,
                "mean_conc": mean_c,
                "ssr_nofill": int(st.get("ssr_nofill") or 0),
                "n_short_signals": int(st.get("n_short_signals") or 0),
                "n_ssr_signals": int(st.get("n_ssr_signals") or 0),
            }
        )
    return {"session": session_iso, "rows": rows}


def _replay_flush(args: tuple) -> dict:
    iso, names, prior_dv = args
    session = date.fromisoformat(iso)
    empty = {
        "session": iso,
        "n_cand": len(names),
        "pnl": 0.0,
        "trades": [],
        "peak": 0,
        "mean_conc": 0.0,
        "cost_skips": 0,
    }
    if not names:
        return empty
    bars = _read_hot_bars(session, [h["symbol"] for h in names])
    sigs = []
    for h in names:
        sdf = bars.get(h["symbol"])
        if sdf is None or sdf.height == 0:
            continue
        if not fly_cell_ok(h.get("orw"), h.get("dv0929"), h.get("ext0944")):
            continue
        score = float(h.get("rel0800") or h.get("rel0929") or 1.0)
        for s in flush_ring_long(sdf, h.get("px0800"), tag=FLUSH_ID, max_undercut=MAX_UNDERCUT):
            if s.side != 1:
                continue
            sigs.append(score_flush(s, score))
    need = {s.symbol for s in sigs}
    sub = {k: bars[k] for k in need if k in bars}
    st = {}
    trades = replay_session(sub, sigs, prior_dv, stats=st, **FLUSH_CAP8)
    peak, mean_c = concurrent_stats(trades)
    return {
        "session": iso,
        "n_cand": len(names),
        "pnl": sum(t.pnl for t in trades),
        "trades": _pack_trades(trades, bars),
        "peak": peak,
        "mean_conc": mean_c,
        "cost_skips": int(st.get("cost_skips") or 0),
    }


def run_arrow27(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow27 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "repairs R1-R5, combine_books, B-short SSR policy rows, reprint flush|max6. "
        "No rocket rings. No $500/idea. No virgin pull. R6 skipped beta-IWM. No Arrow 28.",
        flush=True,
    )

    print("B-short: session lows on Lab A tape", flush=True)
    lows: dict[str, dict[str, float]] = {}
    prog_l = Progress(len(all_sess), "arrow27_lows")
    prog_l.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_low_one, d): d for d in all_sess}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            lows[iso] = mp
            prog_l.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog_l.heartbeat()
    prog_l.stop_heartbeat()
    prog_l.heartbeat()

    elig_all = pl.read_parquet(ELIGIBILITY)
    b_path = ELIGIBILITY.parent / "eligibility_b.parquet"
    if b_path.exists():
        track_b = pl.read_parquet(b_path)
        capped = True
    else:
        track_b, capped = _filter_track_b(elig_all)
        track_b.write_parquet(b_path)
    pc_by: dict[str, dict[str, float]] = {}
    for rec in elig_all.select("session_date", "symbol", "prior_close").iter_rows(named=True):
        pc = rec["prior_close"]
        if pc is None:
            continue
        iso = _iso(rec["session_date"])
        pc_by.setdefault(iso, {})[str(rec["symbol"])] = float(pc)
    print(f"Track B rows={track_b.height} cap_file={capped}", flush=True)
    print("precompute 15m closes for ema15 stitch", flush=True)
    bars15 = _build_bars15(all_sess, workers)
    print(f"bars15 keys={len(bars15)}", flush=True)

    b_jobs = [
        (d.isoformat(), str(b_path), bars15, sess_order, lows, pc_by)
        for d in develop + holdout
    ]
    print(f"B-short replay {len(b_jobs)} sessions x {len(B_IDS)} policies", flush=True)
    prog_b = Progress(len(b_jobs), "arrow27_b")
    prog_b.start_heartbeat()
    b_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_b, job) for job in b_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            b_chunks.append(chunk)
            prog_b.mark(chunk["session"], rows=len(chunk["rows"]))
            if i % 8 == 0:
                prog_b.heartbeat()
    prog_b.stop_heartbeat()
    prog_b.heartbeat()

    print("flush|max6 reprint on data/full (R4 close fallback only)", flush=True)
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig_f = pl.read_parquet(FULL_ELIGIBILITY)
    by_sess: dict[str, dict[str, dict]] = {}
    for rec in elig_f.select(
        "session_date", "symbol", "prior_close", "prior_dollar_volume", "eligible"
    ).iter_rows(named=True):
        if rec.get("eligible") is False:
            continue
        pc = rec["prior_close"]
        if pc is None:
            continue
        pc = float(pc)
        if pc < PRICE_LO - 1e-12 or pc > PRICE_HI + 1e-12:
            continue
        iso = _iso(rec["session_date"])
        by_sess.setdefault(iso, {})[str(rec["symbol"])] = {
            "prior_close": pc,
            "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
        }
    print(f"flush pass 1: 08:00 hot + FLY cell stamps n={len(all_sess)} tape={FULL_BARS}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog_f = Progress(len(all_sess), "arrow27_flush_pre")
    prog_f.start_heartbeat()
    scan_jobs = [(d, by_sess.get(_iso(d), {})) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_scan, job): job[0] for job in scan_jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog_f.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog_f.heartbeat()
    prog_f.stop_heartbeat()
    prog_f.heartbeat()

    dv8_hist: dict[str, list[tuple[str, float]]] = {}
    dv9_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for st in feat.get(iso, {}).values():
            if st.get("dv0800") is not None:
                dv8_hist.setdefault(st["symbol"], []).append((iso, st["dv0800"]))
            if st.get("dv0929") is not None:
                dv9_hist.setdefault(st["symbol"], []).append((iso, st["dv0929"]))
    study_isos = {_iso(d) for d in study}
    for iso in [_iso(d) for d in all_sess]:
        for st in feat.get(iso, {}).values():
            prior8 = [v for s, v in (dv8_hist.get(st["symbol"]) or []) if s < iso]
            prior9 = [v for s, v in (dv9_hist.get(st["symbol"]) or []) if s < iso]
            st["rel0800"] = run_rel_vol(st.get("dv0800"), prior8)
            st["rel0929"] = run_rel_vol(st.get("dv0929"), prior9)
            ext8 = (st["px0800"] / st["prior_close"] - 1.0) if st.get("px0800") else None
            st["hot0800"] = hot_gate_0800(
                pre_dv=st.get("dv0800"), pre_dv_rel=st.get("rel0800"), ext_0800=ext8
            )
    feats_by_sess: dict[str, list[dict]] = {iso: [] for iso in study_isos}
    prior_dv_by_sess: dict[str, dict[str, float]] = {iso: {} for iso in study_isos}
    n_hot = n_cell = 0
    for d in study:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            if st["prior_close"] < PRICE_FLOOR_PX5 - 1e-12:
                continue
            if not st.get("hot0800"):
                continue
            if st.get("rel0800") is None:
                continue
            feats_by_sess[iso].append(st)
            prior_dv_by_sess[iso][st["symbol"]] = st["prior_dv"]
            n_hot += 1
            if fly_cell_ok(st.get("orw"), st.get("dv0929"), st.get("ext0944")):
                n_cell += 1
    print(f"08:00 hot px5 name-days study={n_hot} of which FLY-cell={n_cell}", flush=True)
    flush_jobs = [
        (_iso(d), feats_by_sess[_iso(d)], prior_dv_by_sess[_iso(d)])
        for d in develop + holdout
    ]
    print(f"flush pass 2: replay {len(flush_jobs)} sessions x 1 long", flush=True)
    prog_r = Progress(len(flush_jobs), "arrow27_flush")
    prog_r.start_heartbeat()
    flush_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_flush, job) for job in flush_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            flush_chunks.append(chunk)
            prog_r.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog_r.heartbeat()
    prog_r.stop_heartbeat()
    prog_r.heartbeat()

    iwm = load_iwm()
    print(f"IWM sessions on disk={len(iwm)} (no virgin pull; R6 skipped beta-IWM)", flush=True)
    _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped)
    return 0


def _alpha_daily(trades, sessions, iwm) -> tuple[list[float], int, int]:
    by_day = {d.isoformat(): 0.0 for d in sessions}
    skips = 0
    n_ok = 0
    for t in trades:
        iso = t["entry_ts"].date().isoformat() if hasattr(t["entry_ts"], "date") else str(t["entry_ts"])[:10]
        a = trade_alpha(t, iwm.get(iso))
        if a is None:
            skips += 1
            continue
        by_day[iso] = by_day.get(iso, 0.0) + a
        n_ok += 1
    return [by_day.get(d.isoformat(), 0.0) for d in sessions], skips, n_ok


def _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    b_rows = [r for c in b_chunks for r in c["rows"]]
    results_b = []
    daily_b: dict[str, dict[str, float]] = {}
    for name in B_IDS:
        subset = [r for r in b_rows if r["name"] == name]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
        daily_b[name] = {
            **{d.isoformat(): pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop},
            **{d.isoformat(): pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout},
        }
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        peaks_d = [pnl_map.get(d.isoformat(), {}).get("peak", 0) for d in develop]
        peaks_h = [pnl_map.get(d.isoformat(), {}).get("peak", 0) for d in holdout]
        means_d = [pnl_map.get(d.isoformat(), {}).get("mean_conc", 0.0) for d in develop]
        means_h = [pnl_map.get(d.isoformat(), {}).get("mean_conc", 0.0) for d in holdout]
        sm_d = _summarize(daily_dev, tr_dev, len(develop))
        sm_h = _summarize(daily_hol, tr_hol, len(holdout))
        sm_d["peak_conc"] = max(peaks_d) if peaks_d else 0
        sm_h["peak_conc"] = max(peaks_h) if peaks_h else 0
        sm_d["mean_conc"] = (sum(means_d) / len(means_d)) if means_d else 0.0
        sm_h["mean_conc"] = (sum(means_h) / len(means_h)) if means_h else 0.0
        n_sig = sum(int(r.get("n_short_signals") or 0) for r in subset)
        n_ssr = sum(int(r.get("n_ssr_signals") or 0) for r in subset)
        nofill = sum(int(r.get("ssr_nofill") or 0) for r in subset)
        a_dev, skip_d, n_ad = _alpha_daily(tr_dev, develop, iwm)
        a_hol, skip_h, n_ah = _alpha_daily(tr_hol, holdout, iwm)
        results_b.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "ssr_share": (n_ssr / n_sig) if n_sig else 0.0,
                "ssr_nofill": nofill,
                "n_short_signals": n_sig,
                "alpha_dev": _summarize(a_dev, tr_dev, len(develop)),
                "alpha_hol": _summarize(a_hol, tr_hol, len(holdout)),
                "alpha_skip_dev": skip_d,
                "alpha_skip_hol": skip_h,
                "n_alpha_dev": n_ad,
                "n_alpha_hol": n_ah,
            }
        )

    flush_map = {c["session"]: c for c in flush_chunks}
    daily_flush_dev = [flush_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
    daily_flush_hol = [flush_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
    tr_f_dev = [t for iso, c in flush_map.items() if iso in develop_set for t in c["trades"]]
    tr_f_hol = [t for iso, c in flush_map.items() if iso in holdout_set for t in c["trades"]]
    flush_dev = _summarize_adv(daily_flush_dev, tr_f_dev, len(develop))
    flush_hol = _summarize_adv(daily_flush_hol, tr_f_hol, len(holdout))
    flush_dev["peak_conc"] = max((flush_map.get(d.isoformat(), {}).get("peak", 0) for d in develop), default=0)
    flush_hol["peak_conc"] = max((flush_map.get(d.isoformat(), {}).get("peak", 0) for d in holdout), default=0)
    md = [flush_map.get(d.isoformat(), {}).get("mean_conc", 0.0) for d in develop]
    mh = [flush_map.get(d.isoformat(), {}).get("mean_conc", 0.0) for d in holdout]
    flush_dev["mean_conc"] = (sum(md) / len(md)) if md else 0.0
    flush_hol["mean_conc"] = (sum(mh) / len(mh)) if mh else 0.0
    cost_skips = sum(c.get("cost_skips") or 0 for c in flush_chunks)
    daily_flush = {
        **{d.isoformat(): flush_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop},
        **{d.isoformat(): flush_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout},
    }

    best = max(results_b, key=lambda r: r["develop"]["per_day"])
    comb_dev = combine_books(
        {d.isoformat(): daily_b[best["name"]].get(d.isoformat(), 0.0) for d in develop},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in develop},
    )
    comb_hol = combine_books(
        {d.isoformat(): daily_b[best["name"]].get(d.isoformat(), 0.0) for d in holdout},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in holdout},
    )
    corr_d = comb_dev["corr"].get((0, 1), 0.0)
    corr_h = comb_hol["corr"].get((0, 1), 0.0)

    def _promo(dev, hol) -> bool:
        return hol["clears_200"] and dev["per_day"] >= 0

    promo_names = []
    if _promo(flush_dev, flush_hol):
        promo_names.append(FLUSH_ID)
    for r in results_b:
        if _promo(r["develop"], r["holdout"]):
            promo_names.append(r["name"])
    if promo_names:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo_names)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 27 book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not EV. Combined develop is the helper print, not '$200 minus one improvement'."
        )

    gb_struct = structural_grid_row("giveback", MINUTE_1159)
    lines = [
        "Arrow 27 — repairs, combined scoreboard, SSR as a fill (Lab A B-short + data/full flush)",
        verdict,
        "R1 ssr_active = session low at or before ts <= 0.90*prior_close OR prior session tripped the same rule.",
        f"R2 giveback|flat1159 STRUCTURAL={gb_struct} (flatten 11:59 <= entry 13:00); excluded from both-green. Not rerun.",
        "R4 untradeable flatten bar exits at last tradeable close, not open.",
        "R5 peak_conc/mean_conc on every id. Do not spend ids on cap3 vs cap8 unless peak_conc > 3.",
        "R6 skipped beta-IWM this arrow. IWM alpha on B rows only if bench already on disk (no virgin pull).",
        "No rocket rings. No $500/idea. No 100-grid. No Arrow 28.",
        "Honesty: A18 SSR-on (~+$59) plus A26 flush (~+$11) was ~+$70 before this helper. "
        f"combine_books this file: develop ${comb_dev['per_day']:.2f}/day. "
        "Do not write that the account is one improvement from $200. Combined holdout is two contaminated/cluster prints and is not EV.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}  flush_cost_skips={cost_skips}",
        "",
        "B-short c5_ema9|cap8 SSR policy (Lab A tape, borrow on)",
        f"{'id':<16} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'avgR':>7} "
        f"{'t_hold':>7} {'ssr%':>6} {'nofill':>7} {'peak':>5} {'meanC':>6} {'a_hold':>8} {'>=200':>6}",
    ]
    for r in results_b:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if _promo(r["develop"], h):
            flag = "BOTH"
        lines.append(
            f"{r['name']:<16} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['avg_r']:7.3f} {h['t_stat']:7.2f} "
            f"{100*r['ssr_share']:5.1f}% {r['ssr_nofill']:7d} {h['peak_conc']:5d} "
            f"{h['mean_conc']:6.2f} {r['alpha_hol']['per_day']:8.2f} {flag:>6}"
        )
        lines.append(f"  develop {_fmt(r['develop'], holdout=False)}")
        lines.append(
            f"    peak_conc={r['develop']['peak_conc']}  mean_conc={r['develop']['mean_conc']:.2f}  "
            f"ssr_share={r['ssr_share']:.3f}  ssr_nofill={r['ssr_nofill']}"
        )
        lines.append(f"  holdout {_fmt(r['holdout'], holdout=True)}")
        lines.append(
            f"    peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}  "
            f"IWM alpha develop ${r['alpha_dev']['per_day']:.2f} (n={r['n_alpha_dev']} skip={r['alpha_skip_dev']}) "
            f"holdout ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
    lines.append("")
    lines.append("flush|max6 reprint (data/full, FLY cell, harness on, R4 close fallback)")
    fflag = "YES" if flush_hol["clears_200"] else "NO"
    if flush_hol["clears_200"] and flush_dev["per_day"] < 0:
        fflag = "NO*"
    if _promo(flush_dev, flush_hol):
        fflag = "BOTH"
    lines.append(
        f"{FLUSH_ID:<16} {flush_dev['per_day']:10.2f} {flush_hol['per_day']:11.2f} "
        f"{flush_hol['n_trades']:7d} {flush_hol['avg_r']:7.3f} {flush_hol['t_stat']:7.2f} "
        f"{'':>6} {'':>7} {flush_hol['peak_conc']:5d} {flush_hol['mean_conc']:6.2f} {'':>8} {fflag:>6}"
    )
    lines.append("  develop")
    lines.extend(_fmt_adv(flush_dev))
    lines.append(
        f"    peak_conc={flush_dev['peak_conc']}  mean_conc={flush_dev['mean_conc']:.2f}"
    )
    lines.append("  holdout")
    lines.extend(_fmt_adv(flush_hol))
    lines.append(
        f"    peak_conc={flush_hol['peak_conc']}  mean_conc={flush_hol['mean_conc']:.2f}"
    )
    lines.append("")
    lines.append(
        f"COMBINED {best['name']} + {FLUSH_ID}  (B-short best develop row this file + flush|max6)"
    )
    lines.append(
        f"  develop $/day={comb_dev['per_day']:.2f}  std={comb_dev['std_day']:.2f}  "
        f"se={comb_dev['se_day']:.2f}  t={comb_dev['t_stat']:.2f}  "
        f"ci95=[{comb_dev['ci_lo']:.2f},{comb_dev['ci_hi']:.2f}]  maxDD$={comb_dev['max_dd']:.2f}  "
        f"corr={corr_d:.3f}"
    )
    lines.append(
        f"  holdout $/day={comb_hol['per_day']:.2f}  std={comb_hol['std_day']:.2f}  "
        f"se={comb_hol['se_day']:.2f}  t={comb_hol['t_stat']:.2f}  "
        f"ci95=[{comb_hol['ci_lo']:.2f},{comb_hol['ci_hi']:.2f}]  maxDD$={comb_hol['max_dd']:.2f}  "
        f"corr={corr_h:.3f}  NOT EV"
    )
    lines.append(
        "Peak concurrent risk is not jointly modelled across books (separate tapes). "
        "Missing engine-day is $0, not a dropped session."
    )
    lines.append(
        "NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV."
    )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow27_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 27",
        "",
        verdict,
        "",
        "Repairs R1-R5. combine_books. B-short SSR policy rows on Lab A. flush|max6 reprint on data/full. "
        "No rocket rings. No $500/idea. No virgin pull. R6 skipped beta-IWM. No Arrow 28.",
        "R3: launch-catch was under-sampled in A24 (cell vs launch gates almost disjoint), not refuted. Not rerun here.",
        "Honesty: do not write that the account is one improvement from $200. "
        f"A18 SSR-on (~+$59) plus A26 flush (~+$11) was ~+$70 before this helper. "
        f"combine_books this file: develop ${comb_dev['per_day']:.2f}/day. Combined holdout is not EV.",
        "",
    ]
    for r in results_b:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} t={r['holdout']['t_stat']:.2f} "
            f"ssr_share={r['ssr_share']:.3f} ssr_nofill={r['ssr_nofill']} "
            f"peak_conc={r['holdout']['peak_conc']}."
        )
    bits.append(
        f"- {FLUSH_ID}: develop ${flush_dev['per_day']:.2f}/day "
        f"holdout ${flush_hol['per_day']:.2f}/day n_hold={flush_hol['n_trades']} "
        f"avgR={flush_hol['avg_r']:.3f} t={flush_hol['t_stat']:.2f} "
        f"peak_conc={flush_hol['peak_conc']}."
    )
    bits.append(
        f"- COMBINED {best['name']}+{FLUSH_ID}: develop ${comb_dev['per_day']:.2f}/day "
        f"holdout ${comb_hol['per_day']:.2f}/day corr_dev={corr_d:.3f} corr_hold={corr_h:.3f} "
        f"(holdout not EV)."
    )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
