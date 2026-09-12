from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _summarize
from research.arrow4 import _filter_track_b
from research.arrow18 import load_iwm, trade_alpha
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _fmt_adv, _pack_trades, _summarize_adv
from research.arrow24 import _session_scan
from research.arrow27 import _replay_flush
from research.book import concurrent_stats, replay_session
from research.character import dv_ranks
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, resample_15m, stitch_15m
from research.fills import is_tradeable
from research.harness import PRICE_FLOOR_PX5, attach_atr, run_rel_vol
from research.signals import (
    MINUTE_0929,
    MINUTE_1159,
    MINUTE_1330,
    MINUTE_1430,
    MINUTE_1559,
    bar_time,
)
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies15 import control_c5_ema9
from research.strategies22 import hot_gate_0800

ET = ZoneInfo("America/New_York")

# A27 B_uptick10 on Lab A (row 0 must land within ±10%).
A27_UPTICK10_N_DEV = 204
A27_UPTICK10_N_HOL = 75
COUNT_TOL = 0.10

B_CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "harness_stop": True,
}
SHORT_POP = {"dv_min": 0.80, "gap_min": 0.015, "or_w_min": 0.025}
UPTICK10 = {
    "ssr_policy": "uptick",
    "ssr_filter": False,
    "borrow_filter": True,
    "ssr_uptick_minutes": 10,
}
REJECT = {"ssr_policy": "reject", "ssr_filter": True, "borrow_filter": True}

# (id, extra replay kwargs). Same entry; SSR = uptick10 except the reject diagnostic.
EXPERIMENTS = (
    ("B_uptick10|flat1159", {**UPTICK10, "flatten_at": MINUTE_1159}),
    ("B_uptick10|flat1559", {**UPTICK10, "flatten_at": MINUTE_1559}),
    (
        "B_uptick10|hold05",
        {
            **UPTICK10,
            "flatten_at": MINUTE_1159,
            "hold_plus_r": 0.5,
            "late_flatten_at": MINUTE_1559,
        },
    ),
    (
        "B_uptick10|atr1559",
        {**UPTICK10, "flatten_at": MINUTE_1559, "atr_trail": True},
    ),
    ("B_uptick10|flat1330", {**UPTICK10, "flatten_at": MINUTE_1330}),
    (
        "B_uptick10|hold05_1430",
        {
            **UPTICK10,
            "flatten_at": MINUTE_1159,
            "hold_plus_r": 0.5,
            "late_flatten_at": MINUTE_1430,
        },
    ),
    ("B_reject|flat1159", {**REJECT, "flatten_at": MINUTE_1159}),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
AFTERNOON_IDS = IDS[:6]
CONTROL = IDS[0]
FLUSH_ID = "flush|max6"


def _dv_through(df: pl.DataFrame, clock) -> float:
    if df is None or df.height == 0:
        return 0.0
    dv = 0.0
    for rec in df.sort("bar_start").iter_rows(named=True):
        if bar_time(rec["bar_start"]) > clock:
            break
        if not is_tradeable(rec["open"], rec["close"], rec["volume"]):
            continue
        dv += (float(rec["high"]) + float(rec["low"]) + float(rec["close"])) / 3.0 * float(
            rec["volume"] or 0.0
        )
    return dv


def _prep_one(args: tuple) -> tuple[str, dict[str, list], dict[str, float], dict[str, float]]:
    d, want = args
    iso = d.isoformat()
    folder = FULL_BARS / iso
    bars15: dict[str, list] = {}
    lows: dict[str, float] = {}
    dv9: dict[str, float] = {}
    if not folder.exists() or not want:
        return iso, bars15, lows, dv9
    for path in folder.glob("*.parquet"):
        try:
            df = pl.read_parquet(path)
        except Exception:  # noqa: BLE001
            continue
        if df.height == 0:
            continue
        sym = str(df["symbol"][0]) if "symbol" in df.columns else path.stem.lstrip("_")
        if sym not in want:
            continue
        bars15[sym] = resample_15m(df)
        lo = df["low"].min()
        if lo is not None:
            lows[sym] = float(lo)
        dv9[sym] = _dv_through(df, MINUTE_0929)
    return iso, bars15, lows, dv9


def _mfe_r_after(df: pl.DataFrame | None, trade, after_clock, until_ts) -> float:
    if df is None or df.height == 0 or trade.shares < 1 or trade.risk <= 0:
        return 0.0
    stop_dist = trade.risk / trade.shares
    fav = 0.0
    times = df["bar_start"].to_list()
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    for ts, h, l in zip(times, highs, lows):
        if ts < trade.entry_ts:
            continue
        if bar_time(ts) < after_clock:
            continue
        if ts >= until_ts:
            break
        if trade.side > 0:
            fav = max(fav, float(h) - trade.entry_px)
        else:
            fav = max(fav, trade.entry_px - float(l))
    return fav / stop_dist if stop_dist else 0.0


def _pack_b_trades(trades, *, pre_dv=None, rel0929=None, mfe_after=None) -> list[dict]:
    out = []
    for t in trades:
        r = t.pnl / t.risk if t.risk else 0.0
        rec = {
            "pnl": t.pnl,
            "win": t.pnl > 0,
            "risk": t.risk,
            "side": t.side,
            "shares": t.shares,
            "entry_px": t.entry_px,
            "entry_ts": t.entry_ts,
            "exit_ts": t.exit_ts,
            "tag": t.tag,
            "symbol": t.symbol,
            "r": r,
        }
        if pre_dv is not None:
            rec["pre_dv"] = float(pre_dv.get(t.symbol) or 0.0)
        if rel0929 is not None:
            rec["rel0929"] = rel0929.get(t.symbol)
        if mfe_after is not None:
            rec["mfe_after_1159"] = float(mfe_after.get((t.symbol, t.entry_ts), 0.0))
        out.append(rec)
    return out


def _pf(trades: list[dict]) -> str:
    wins = sum(float(t["pnl"]) for t in trades if t["pnl"] > 0)
    losses = abs(sum(float(t["pnl"]) for t in trades if t["pnl"] < 0))
    if not trades:
        return "0"
    if losses <= 1e-12:
        return "inf"
    return f"{wins / losses:.3f}"


def _replay_b(args: tuple) -> dict:
    only_ids = None
    if len(args) == 9:
        (
            session_iso,
            names,
            bars15,
            sess_order,
            lows,
            pc_by,
            dv9_now,
            rel9,
            only_ids,
        ) = args
    else:
        (
            session_iso,
            names,
            bars15,
            sess_order,
            lows,
            pc_by,
            dv9_now,
            rel9,
        ) = args
    exp_list = tuple(e for e in EXPERIMENTS if only_ids is None or e[0] in only_ids)
    id_list = tuple(e[0] for e in exp_list)
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
        for n in id_list
    ]
    empty = {"session": session_iso, "n_cand": len(names), "rows": empty_rows}
    if not names:
        return empty
    symbols = [h["symbol"] for h in names]
    bars = _read_hot_bars(session, symbols)
    meta = {h["symbol"]: h for h in names}
    prior_dv = {h["symbol"]: float(h["prior_dv"]) for h in names}
    prior_c = {
        h["symbol"]: float(h["prior_close"])
        for h in names
        if h.get("prior_close") is not None
    }
    idx = sess_order.index(session_iso) if session_iso in sess_order else -1
    prev_iso = sess_order[idx - 1] if idx > 0 else None
    psl = dict(lows.get(prev_iso) or {}) if prev_iso else {}
    pspc = dict(pc_by.get(prev_iso) or {}) if prev_iso else {}
    ranks = dv_ranks(prior_dv)
    sigs = []
    for sym, sdf in bars.items():
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
            sigs.append(attach_atr(sig, sdf))
    by_name_trades = {}
    rows = []
    for name, kw in exp_list:
        st = {}
        trades = replay_session(
            bars,
            sigs,
            prior_dv,
            prior_close=prior_c,
            prior_session_low=psl,
            prior_session_prior_close=pspc,
            stats=st,
            **B_CAP8,
            **kw,
        )
        by_name_trades[name] = trades
        peak, mean_c = concurrent_stats(trades)
        mfe_map = {}
        if name == CONTROL:
            held = by_name_trades.get("B_uptick10|flat1559") or []
            held_by = {(t.symbol, t.entry_ts): t for t in held}
            for t in trades:
                t1 = held_by.get((t.symbol, t.entry_ts))
                until = t1.exit_ts if t1 is not None else t.exit_ts
                mfe_map[(t.symbol, t.entry_ts)] = _mfe_r_after(
                    bars.get(t.symbol), t, MINUTE_1159, until
                )
        # id 0 mfe needs id 1 trades; compute after both exist
        rows.append(
            {
                "session": session_iso,
                "name": name,
                "pnl": sum(t.pnl for t in trades),
                "trades": trades,
                "peak": peak,
                "mean_conc": mean_c,
                "ssr_nofill": int(st.get("ssr_nofill") or 0),
                "n_short_signals": int(st.get("n_short_signals") or 0),
                "n_ssr_signals": int(st.get("n_ssr_signals") or 0),
                "mfe_map": mfe_map,
            }
        )
    # fill id-0 MFE now that flat1559 trades exist
    held = by_name_trades.get("B_uptick10|flat1559") or []
    held_by = {(t.symbol, t.entry_ts): t for t in held}
    out_rows = []
    for rec in rows:
        trades = rec["trades"]
        mfe_map = rec["mfe_map"]
        if rec["name"] == CONTROL:
            mfe_map = {}
            for t in trades:
                t1 = held_by.get((t.symbol, t.entry_ts))
                until = t1.exit_ts if t1 is not None else t.exit_ts
                mfe_map[(t.symbol, t.entry_ts)] = _mfe_r_after(
                    bars.get(t.symbol), t, MINUTE_1159, until
                )
        packed = _pack_b_trades(
            trades, pre_dv=dv9_now, rel0929=rel9, mfe_after=mfe_map if rec["name"] == CONTROL else None
        )
        out_rows.append(
            {
                "session": rec["session"],
                "name": rec["name"],
                "pnl": rec["pnl"],
                "trades": packed,
                "peak": rec["peak"],
                "mean_conc": rec["mean_conc"],
                "ssr_nofill": rec["ssr_nofill"],
                "n_short_signals": rec["n_short_signals"],
                "n_ssr_signals": rec["n_ssr_signals"],
            }
        )
    return {"session": session_iso, "n_cand": len(names), "rows": out_rows}


def run_arrow28(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow28 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "B-short on data/full; SSR=B_uptick10; afternoon exits. "
        "No rocket rings. No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 29.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    track_b, capped = _filter_track_b(elig)
    print(f"Track B rows={track_b.height} cap_file={capped} tape=data/full", flush=True)
    want = set(str(s) for s in track_b["symbol"].unique().to_list())
    by_sess: dict[str, list[dict]] = {iso: [] for iso in sess_order}
    pc_by: dict[str, dict[str, float]] = {}
    for rec in track_b.select(
        "session_date", "symbol", "prior_close", "prior_dollar_volume"
    ).iter_rows(named=True):
        iso = _iso(rec["session_date"])
        sym = str(rec["symbol"])
        pc = rec["prior_close"]
        if pc is None:
            continue
        pc = float(pc)
        row = {
            "symbol": sym,
            "prior_close": pc,
            "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
        }
        by_sess.setdefault(iso, []).append(row)
        pc_by.setdefault(iso, {})[sym] = pc
    for rec in elig.select("session_date", "symbol", "prior_close").iter_rows(named=True):
        pc = rec["prior_close"]
        if pc is None:
            continue
        iso = _iso(rec["session_date"])
        pc_by.setdefault(iso, {})[str(rec["symbol"])] = float(pc)

    print(f"pass 1: 15m + session low + dv0929 n={len(all_sess)} symbols={len(want)}", flush=True)
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow28_pre")
    prog.start_heartbeat()
    jobs = [(d, want) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_prep_one, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, b15, lo, d9 = fut.result()
            lows[iso] = lo
            dv9[iso] = d9
            for sym, series in b15.items():
                bars15[(sym, iso)] = series
            prog.mark(iso, rows=len(b15))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    dv9_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in sess_order:
        for sym, v in (dv9.get(iso) or {}).items():
            dv9_hist.setdefault(sym, []).append((iso, v))
    rel_by_sess: dict[str, dict[str, float | None]] = {}
    for iso in sess_order:
        rel_by_sess[iso] = {}
        for h in by_sess.get(iso, []):
            sym = h["symbol"]
            prior = [v for s, v in (dv9_hist.get(sym) or []) if s < iso]
            rel_by_sess[iso][sym] = run_rel_vol((dv9.get(iso) or {}).get(sym), prior)

    replay_jobs = [
        (
            _iso(d),
            by_sess.get(_iso(d), []),
            bars15,
            sess_order,
            lows,
            pc_by,
            dv9.get(_iso(d), {}),
            rel_by_sess.get(_iso(d), {}),
        )
        for d in develop + holdout
    ]
    print(f"pass 2: B-short replay {len(replay_jobs)} sessions x {len(IDS)}", flush=True)
    prog2 = Progress(len(replay_jobs), "arrow28_b")
    prog2.start_heartbeat()
    b_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_b, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            b_chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    print("flush|max6 daily series for COMBINED (reuse A27 path, data/full)", flush=True)
    flush_chunks = _flush_chunks(elig, all_sess, study, develop, holdout, workers)
    iwm = load_iwm()
    print(f"IWM sessions on disk={len(iwm)} (no virgin pull)", flush=True)
    _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped)
    return 0


def _flush_chunks(elig, all_sess, study, develop, holdout, workers) -> list[dict]:
    by_sess: dict[str, dict[str, dict]] = {}
    for rec in elig.select(
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
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow28_flush_pre")
    prog.start_heartbeat()
    jobs = [(d, by_sess.get(_iso(d), {})) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_scan, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
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
    for d in study:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            if st["prior_close"] < PRICE_FLOOR_PX5 - 1e-12:
                continue
            if not st.get("hot0800") or st.get("rel0800") is None:
                continue
            feats_by_sess[iso].append(st)
            prior_dv_by_sess[iso][st["symbol"]] = st["prior_dv"]
    jobs2 = [
        (_iso(d), feats_by_sess.get(_iso(d), []), prior_dv_by_sess.get(_iso(d), {}))
        for d in develop + holdout
    ]
    prog2 = Progress(len(jobs2), "arrow28_flush")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_flush, job) for job in jobs2]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk.get("n_cand") or 0)
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    return chunks


def _within(n: int, ref: int, tol: float = COUNT_TOL) -> bool:
    return abs(n - ref) <= tol * ref + 1e-9


def _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    b_rows = [r for c in b_chunks for r in c["rows"]]
    results = []
    daily_map: dict[str, dict[str, float]] = {}
    for name in IDS:
        subset = [r for r in b_rows if r["name"] == name]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
        daily_map[name] = {
            **{d.isoformat(): pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop},
            **{d.isoformat(): pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout},
        }
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        sm_d = _summarize(daily_dev, tr_dev, len(develop))
        sm_h = _summarize(daily_hol, tr_hol, len(holdout))
        peaks_d = [int(pnl_map.get(d.isoformat(), {}).get("peak") or 0) for d in develop]
        peaks_h = [int(pnl_map.get(d.isoformat(), {}).get("peak") or 0) for d in holdout]
        means_d = [float(pnl_map.get(d.isoformat(), {}).get("mean_conc") or 0.0) for d in develop]
        means_h = [float(pnl_map.get(d.isoformat(), {}).get("mean_conc") or 0.0) for d in holdout]
        sm_d["peak_conc"] = max(peaks_d) if peaks_d else 0
        sm_h["peak_conc"] = max(peaks_h) if peaks_h else 0
        sm_d["mean_conc"] = (sum(means_d) / len(means_d)) if means_d else 0.0
        sm_h["mean_conc"] = (sum(means_h) / len(means_h)) if means_h else 0.0
        sm_d["pf_s"] = _pf(tr_dev)
        sm_h["pf_s"] = _pf(tr_hol)
        n_sig = sum(int(r.get("n_short_signals") or 0) for r in subset)
        n_ssr = sum(int(r.get("n_ssr_signals") or 0) for r in subset)
        nofill = sum(int(r.get("ssr_nofill") or 0) for r in subset)

        def _frac_half(tr):
            timed = [t for t in tr if t.get("tag") == "time"]
            if not timed:
                return 0.0
            return sum(1 for t in timed if float(t.get("r") or 0.0) >= 0.5 - 1e-12) / len(timed)

        def _mean_mfe(tr):
            xs = [float(t["mfe_after_1159"]) for t in tr if t.get("mfe_after_1159") is not None]
            return (sum(xs) / len(xs)) if xs else 0.0

        def _mean_opt(tr, key):
            xs = [float(t[key]) for t in tr if t.get(key) is not None]
            return (sum(xs) / len(xs)) if xs else 0.0

        a_dev, skip_d, n_ad = _alpha_daily(tr_dev, develop, iwm)
        a_hol, skip_h, n_ah = _alpha_daily(tr_hol, holdout, iwm)
        results.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "ssr_share": (n_ssr / n_sig) if n_sig else 0.0,
                "ssr_nofill": nofill,
                "frac_half_d": _frac_half(tr_dev),
                "frac_half_h": _frac_half(tr_hol),
                "mfe_after_d": _mean_mfe(tr_dev),
                "mfe_after_h": _mean_mfe(tr_hol),
                "pre_dv_d": _mean_opt(tr_dev, "pre_dv"),
                "pre_dv_h": _mean_opt(tr_hol, "pre_dv"),
                "rel9_d": _mean_opt(tr_dev, "rel0929"),
                "rel9_h": _mean_opt(tr_hol, "rel0929"),
                "alpha_hol": _summarize(a_hol, tr_hol, len(holdout)),
                "alpha_dev": _summarize(a_dev, tr_dev, len(develop)),
                "n_alpha_dev": n_ad,
                "n_alpha_hol": n_ah,
                "alpha_skip_dev": skip_d,
                "alpha_skip_hol": skip_h,
            }
        )

    flush_map = {c["session"]: c for c in flush_chunks}
    daily_flush = {
        **{d.isoformat(): flush_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop},
        **{d.isoformat(): flush_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout},
    }
    tr_f_dev = [t for iso, c in flush_map.items() if iso in develop_set for t in c.get("trades") or []]
    tr_f_hol = [t for iso, c in flush_map.items() if iso in holdout_set for t in c.get("trades") or []]
    flush_dev = _summarize_adv(
        [daily_flush.get(d.isoformat(), 0.0) for d in develop], tr_f_dev, len(develop)
    )
    flush_hol = _summarize_adv(
        [daily_flush.get(d.isoformat(), 0.0) for d in holdout], tr_f_hol, len(holdout)
    )

    afternoon = [r for r in results if r["name"] in AFTERNOON_IDS]
    green = [r for r in afternoon if r["develop"]["per_day"] >= 0]
    if green:
        best = max(green, key=lambda r: r["develop"]["per_day"])
    else:
        best = next(r for r in results if r["name"] == CONTROL)
    comb_dev = combine_books(
        {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in develop},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in develop},
    )
    comb_hol = combine_books(
        {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in holdout},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in holdout},
    )
    corr_d = comb_dev["corr"].get((0, 1), 0.0)
    corr_h = comb_hol["corr"].get((0, 1), 0.0)

    ctrl = next(r for r in results if r["name"] == CONTROL)
    n_d, n_h = ctrl["develop"]["n_trades"], ctrl["holdout"]["n_trades"]
    ok_d = _within(n_d, A27_UPTICK10_N_DEV)
    ok_h = _within(n_h, A27_UPTICK10_N_HOL)
    if ok_d and ok_h:
        drift = (
            f"Row 0 counts vs A27 B_uptick10: develop {n_d}/{A27_UPTICK10_N_DEV} "
            f"holdout {n_h}/{A27_UPTICK10_N_HOL} — within ±10%."
        )
    else:
        drift = (
            f"Row 0 counts vs A27 B_uptick10: develop {n_d}/{A27_UPTICK10_N_DEV} "
            f"({n_d / max(A27_UPTICK10_N_DEV, 1):.2f}x) holdout {n_h}/{A27_UPTICK10_N_HOL} "
            f"({n_h / max(A27_UPTICK10_N_HOL, 1):.2f}x) — DRIFT beyond ±10%. "
            "Likely causes: data/full 04:00-16:00 tape adds premarket 15m bars to the EMA stitch "
            "(Lab A started 07:30), and ssr_active session-low now includes 04:00-07:30 prints; "
            "harness ATR/0.6pct floor is on (A27 B-short did not use it) which changes size not skips."
        )

    def _promo(dev, hol) -> bool:
        return hol["clears_200"] and dev["per_day"] >= 0

    promo = [r["name"] for r in afternoon if _promo(r["develop"], r["holdout"])]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 28 book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not EV."
        )

    lines = [
        "Arrow 28 — B-short on data/full; afternoon exits; SSR=B_uptick10",
        verdict,
        "No rocket rings. No $500/idea. No virgin pull. No cap3-vs-cap8 on flush. No Arrow 29.",
        drift,
        "Honesty: combined develop is the combine_books number. Combined holdout is not EV. "
        "Do not write that the account is one improvement from $200.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap={capped}  tape={FULL_BARS}",
        "Entry: Track B [$10,$50] cap400, dv_rank>=0.80, gap-down>=1.5%, OR>2.5%, "
        "first 5-min close below ema9 after 09:45, ema9<ema21. cap8 $200/idea, borrow on, uptick10. "
        "Harness ATR/0.6pct stop floor on. Flatten per id.",
        "",
        f"{'id':<24} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'avgR':>7} "
        f"{'PF':>6} {'t_hold':>7} {'peak':>5} {'meanC':>6} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if r["name"] in AFTERNOON_IDS and _promo(r["develop"], h):
            flag = "BOTH"
        lines.append(
            f"{r['name']:<24} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['avg_r']:7.3f} {h['pf_s']:>6} {h['t_stat']:7.2f} "
            f"{h['peak_conc']:5d} {h['mean_conc']:6.2f} {flag:>6}"
        )
        lines.append(f"  develop {_fmt(r['develop'], holdout=False)}")
        lines.append(
            f"    PF={r['develop']['pf_s']}  peak_conc={r['develop']['peak_conc']}  "
            f"mean_conc={r['develop']['mean_conc']:.2f}  ssr_share={r['ssr_share']:.3f}  "
            f"ssr_nofill={r['ssr_nofill']}"
        )
        lines.append(f"  holdout {_fmt(r['holdout'], holdout=True)}")
        lines.append(
            f"    PF={h['pf_s']}  peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}  "
            f"IWM alpha hold ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
        lines.append(
            f"    pre_dv_0929 mean develop={r['pre_dv_d']:.0f} holdout={r['pre_dv_h']:.0f}  "
            f"rel0929 mean develop={r['rel9_d']:.2f} holdout={r['rel9_h']:.2f}  (report-only, no gate)"
        )
        if r["name"] == CONTROL:
            lines.append(
                f"    id0 time-exits >=+0.5R develop={r['frac_half_d']:.3f} holdout={r['frac_half_h']:.3f}  "
                f"MFE after 11:59 if held to 15:59 meanR develop={r['mfe_after_d']:.3f} holdout={r['mfe_after_h']:.3f}"
            )
    lines.append("")
    lines.append(
        f"flush|max6 (COMBINED input) develop ${flush_dev['per_day']:.2f}/day "
        f"holdout ${flush_hol['per_day']:.2f}/day n_hold={flush_hol['n_trades']}"
    )
    lines.append("")
    lines.append(
        f"COMBINED {best['name']} + {FLUSH_ID}  (best develop-not-red B row this file + flush|max6)"
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
    lines.append("NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow28_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 28",
        "",
        verdict,
        "",
        "B-short on data/full. SSR=B_uptick10. Afternoon exits. No rocket rings. No $500/idea. "
        "No virgin pull. Combined holdout is not EV. No Arrow 29.",
        drift,
        "Honesty: combined develop is the combine_books number. Combined holdout is not EV.",
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} PF={r['holdout']['pf_s']} "
            f"t={r['holdout']['t_stat']:.2f} peak_conc={r['holdout']['peak_conc']} "
            f"mean_conc={r['holdout']['mean_conc']:.2f}."
        )
    bits.append(
        f"- COMBINED {best['name']}+{FLUSH_ID}: develop ${comb_dev['per_day']:.2f}/day "
        f"holdout ${comb_hol['per_day']:.2f}/day corr_dev={corr_d:.3f} (holdout not EV)."
    )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")


def _alpha_daily(trades, sessions, iwm):
    by_day = {d.isoformat(): 0.0 for d in sessions}
    skips = 0
    n_ok = 0
    for t in trades:
        iso = (
            t["entry_ts"].date().isoformat()
            if hasattr(t.get("entry_ts"), "date")
            else str(t.get("entry_ts") or "")[:10]
        )
        a = trade_alpha(t, iwm.get(iso)) if t.get("entry_ts") is not None else None
        if a is None:
            skips += 1
            continue
        by_day[iso] = by_day.get(iso, 0.0) + a
        n_ok += 1
    return [by_day.get(d.isoformat(), 0.0) for d in sessions], skips, n_ok
