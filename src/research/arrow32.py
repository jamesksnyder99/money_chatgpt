from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt
from research.arrow4 import _filter_track_b
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow24 import _session_scan
from research.arrow31 import (
    B_CAP8,
    FLUSH_CAP8,
    FLUSH_ID,
    SHORT_POP,
    UPTICK10,
    _alpha_daily,
    _pack_trades,
    _pf,
    _summ_side,
    ensure_iwm_full_hours,
)
from research.book import concurrent_stats, joint_peak_risk, marked_equity_session, replay_session
from research.character import dv_ranks
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, resample_15m, stitch_15m
from research.harness import PRICE_FLOOR_PX5, attach_atr, calendar_prior_dvs, run_rel_vol
from research.signals import MINUTE_1159, MINUTE_1559
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies15 import control_c5_ema9
from research.strategies22 import hot_gate_0800
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long, score_flush
from research.strategies26 import MAX_UNDERCUT
from research.strategies32 import conjunction_c5_ema9

ET = ZoneInfo("America/New_York")
STITCH_0400 = time(4, 0)

A31_LOCK_N_DEV = 216
A31_LOCK_N_HOL = 94
COUNT_TOL = 0.10

CONTROL_KW = {
    **UPTICK10,
    "flatten_at": MINUTE_1559,
    "last_entry_at": MINUTE_1159,
    "atr_trail": True,
}

CONTROL_ID = "B|uptick10|atr1559|lock"
CONJ_ID = "B|conj|atr1559|lock"
EXPERIMENTS = (
    (CONTROL_ID, dict(CONTROL_KW), "control"),
    (CONJ_ID, dict(CONTROL_KW), "conj"),
    ("B|atr075|lock", {**CONTROL_KW, "trail_atr_mult": 0.75}, "control"),
    ("B|atr150|lock", {**CONTROL_KW, "trail_atr_mult": 1.5}, "control"),
    ("B|arm05|lock", {**CONTROL_KW, "trail_arm_r": 0.5}, "control"),
    ("B|unarmed20|lock", {**CONTROL_KW, "unarmed_red_minutes": 20}, "control"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _within(n: int, ref: int, tol: float = COUNT_TOL) -> bool:
    return abs(n - ref) <= tol * ref + 1e-9


def _prep_one(args: tuple) -> tuple:
    d, want = args
    iso = d.isoformat()
    folder = FULL_BARS / iso
    b15: dict[str, list] = {}
    lows: dict[str, float] = {}
    if not folder.exists() or not want:
        return iso, b15, lows
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
        b15[sym] = resample_15m(df, not_before=STITCH_0400)
        lo = df["low"].min()
        if lo is not None:
            lows[sym] = float(lo)
    return iso, b15, lows


def _replay_one(args: tuple) -> dict:
    session_iso, names, bars15, sess_order, lows, pc_by = args
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
            "intraday_dd": 0.0,
            "filled": [],
            "n_ctrl_sigs": 0,
            "n_conj_sigs": 0,
            "unarmed_red_exits": 0,
            "ledgers": [],
        }
        for n in IDS
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
    ctrl_sigs = []
    conj_sigs = []
    ledgers = []
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
            ctrl_sigs.append(attach_atr(sig, sdf))
        got, led = conjunction_c5_ema9(sdf, stitched, or_high)
        led = dict(led)
        led["symbol"] = sym
        ledgers.append(led)
        for sig in got:
            if sig.side != -1:
                continue
            conj_sigs.append(attach_atr(sig, sdf))
    rows = []
    for name, kw, src in EXPERIMENTS:
        sigs = conj_sigs if src == "conj" else ctrl_sigs
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
        peak, mean_c = concurrent_stats(trades)
        packed = _pack_trades(trades, bars)
        mtm = marked_equity_session(trades, bars)
        filled = sorted({t.symbol for t in trades})
        rows.append(
            {
                "session": session_iso,
                "name": name,
                "pnl": sum(t.pnl for t in trades),
                "trades": packed,
                "peak": peak,
                "mean_conc": mean_c,
                "ssr_nofill": int(st.get("ssr_nofill") or 0),
                "n_short_signals": int(st.get("n_short_signals") or 0),
                "n_ssr_signals": int(st.get("n_ssr_signals") or 0),
                "intraday_dd": float(mtm["intraday_peak_to_trough"]),
                "filled": filled,
                "n_ctrl_sigs": len(ctrl_sigs),
                "n_conj_sigs": len(conj_sigs),
                "unarmed_red_exits": int(st.get("unarmed_red_exits") or 0),
                "ledgers": ledgers if name == CONJ_ID else [],
            }
        )
    return {"session": session_iso, "n_cand": len(names), "rows": rows}


def _replay_flush_repaired(args: tuple) -> dict:
    iso, names, prior_dv = args
    session = date.fromisoformat(iso)
    empty = {"session": iso, "pnl": 0.0, "trades": []}
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
        for s in flush_ring_long(
            sdf,
            h.get("px0800"),
            tag=FLUSH_ID,
            max_undercut=MAX_UNDERCUT,
            signal_after=FLY_AVAILABLE_AT,
        ):
            if s.side == 1:
                sigs.append(score_flush(s, score))
    need = {s.symbol for s in sigs}
    sub = {k: bars[k] for k in need if k in bars}
    trades = replay_session(sub, sigs, prior_dv, **FLUSH_CAP8)
    packed = _pack_trades(trades, bars)
    return {"session": iso, "pnl": sum(t.pnl for t in trades), "trades": packed}


def run_arrow32(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow32 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "B-short conjunction and trail rings on A31 lock. A1-A5 on. last_entry_at=11:59. "
        "No flush rings. No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 33.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    track_b, capped = _filter_track_b(elig)
    print(f"Track B rows={track_b.height} cap_file={capped} tape=data/full", flush=True)
    iwm = ensure_iwm_full_hours(workers=workers)

    want_b = set(str(s) for s in track_b["symbol"].unique().to_list())
    by_sess_b: dict[str, list[dict]] = {iso: [] for iso in sess_order}
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
        by_sess_b.setdefault(iso, []).append(
            {"symbol": sym, "prior_close": pc, "prior_dv": float(rec["prior_dollar_volume"] or 0.0)}
        )
        pc_by.setdefault(iso, {})[sym] = pc
    for rec in elig.select("session_date", "symbol", "prior_close").iter_rows(named=True):
        pc = rec["prior_close"]
        if pc is None:
            continue
        iso = _iso(rec["session_date"])
        pc_by.setdefault(iso, {})[str(rec["symbol"])] = float(pc)

    print(f"pass 1: 15m 04:00 stitch n={len(all_sess)} symbols={len(want_b)}", flush=True)
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow32_pre")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_prep_one, (d, want_b)): d for d in all_sess}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, b15, lo = fut.result()
            lows[iso] = lo
            for sym, series in b15.items():
                bars15[(sym, iso)] = series
            prog.mark(iso, rows=len(b15))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    jobs = [
        (_iso(d), by_sess_b.get(_iso(d), []), bars15, sess_order, lows, pc_by)
        for d in develop + holdout
    ]
    print(f"pass 2: B-short {len(jobs)} sessions x {len(IDS)}", flush=True)
    prog2 = Progress(len(jobs), "arrow32_b")
    prog2.start_heartbeat()
    b_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            b_chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    print("pass 3: reprint A31 flush|max6|repaired daily series (not a new ring)", flush=True)
    flush_chunks = _flush_reprint(elig, all_sess, study, develop, holdout, workers)
    _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped)
    return 0


def _flush_reprint(elig, all_sess, study, develop, holdout, workers) -> list[dict]:
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
    prog = Progress(len(all_sess), "arrow32_flush_pre")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_scan, (d, by_sess.get(_iso(d), {}))): d for d in all_sess}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    dv8_by: dict[str, dict[str, float]] = {}
    dv9_by: dict[str, dict[str, float]] = {}
    sess_order = [_iso(d) for d in all_sess]
    for iso in sess_order:
        for st in feat.get(iso, {}).values():
            if st.get("dv0800") is not None:
                dv8_by.setdefault(st["symbol"], {})[iso] = float(st["dv0800"])
            if st.get("dv0929") is not None:
                dv9_by.setdefault(st["symbol"], {})[iso] = float(st["dv0929"])
    study_isos = {_iso(d) for d in study}
    for iso in sess_order:
        for st in feat.get(iso, {}).values():
            win8 = calendar_prior_dvs(dv8_by.get(st["symbol"]) or {}, iso, sess_order)
            win9 = calendar_prior_dvs(dv9_by.get(st["symbol"]) or {}, iso, sess_order)
            st["rel0800"] = run_rel_vol(st.get("dv0800"), win8["values"])
            st["rel0929"] = run_rel_vol(st.get("dv0929"), win9["values"])
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
    jobs = [
        (_iso(d), feats_by_sess.get(_iso(d), []), prior_dv_by_sess.get(_iso(d), {}))
        for d in develop + holdout
    ]
    prog2 = Progress(len(jobs), "arrow32_flush")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_flush_repaired, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=1)
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    return chunks


def _write_reports(b_chunks, flush_chunks, iwm, workers, cpu, develop, holdout, capped) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    b_rows = [r for c in b_chunks for r in c["rows"]]
    results = []
    daily_map = {}
    trades_map = {}
    filled_dev: dict[str, set] = {}
    filled_hol: dict[str, set] = {}
    for name in IDS:
        sub = [r for r in b_rows if r["name"] == name]
        sm_d, _dd, tr_d, map_d = _summ_side(sub, develop)
        sm_h, _dh, tr_h, map_h = _summ_side(sub, holdout)
        daily_map[name] = {**map_d, **map_h}
        trades_map[name] = {"dev": tr_d, "hol": tr_h}
        filled_dev[name] = {s for r in sub if r["session"] in develop_set for s in r.get("filled") or []}
        filled_hol[name] = {s for r in sub if r["session"] in holdout_set for s in r.get("filled") or []}
        a_hol, skip_h, n_ah = _alpha_daily(tr_h, holdout, iwm)
        a_dev, skip_d, n_ad = _alpha_daily(tr_d, develop, iwm)
        n_sig = sum(int(r.get("n_short_signals") or 0) for r in sub)
        n_ssr = sum(int(r.get("n_ssr_signals") or 0) for r in sub)
        sm_d["unarmed_red"] = sum(int(r.get("unarmed_red_exits") or 0) for r in sub if r["session"] in develop_set)
        sm_h["unarmed_red"] = sum(int(r.get("unarmed_red_exits") or 0) for r in sub if r["session"] in holdout_set)
        results.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "ssr_share": (n_ssr / n_sig) if n_sig else 0.0,
                "ssr_nofill": sum(int(r.get("ssr_nofill") or 0) for r in sub),
                "alpha_hol": {"per_day": (sum(a_hol) / len(holdout)) if holdout else 0.0},
                "n_alpha_hol": n_ah,
                "alpha_skip_hol": skip_h,
                "n_alpha_dev": n_ad,
                "alpha_skip_dev": skip_d,
            }
        )

    ctrl = next(r for r in results if r["name"] == CONTROL_ID)
    n_d, n_h = ctrl["develop"]["n_trades"], ctrl["holdout"]["n_trades"]
    if _within(n_d, A31_LOCK_N_DEV) and _within(n_h, A31_LOCK_N_HOL):
        drift = (
            f"Id 0 vs A31 {CONTROL_ID}: develop {n_d}/{A31_LOCK_N_DEV} "
            f"holdout {n_h}/{A31_LOCK_N_HOL} — within ±10%."
        )
    else:
        drift = (
            f"Id 0 vs A31 {CONTROL_ID}: develop {n_d}/{A31_LOCK_N_DEV} "
            f"({n_d / max(A31_LOCK_N_DEV, 1):.2f}x) holdout {n_h}/{A31_LOCK_N_HOL} "
            f"({n_h / max(A31_LOCK_N_HOL, 1):.2f}x) — DRIFT beyond ±10%."
        )

    conj_rows = [r for r in b_rows if r["name"] == CONJ_ID]
    ledgers = [led for r in conj_rows for led in r.get("ledgers") or []]
    n_led = len(ledgers)
    n_conj_hit = sum(1 for led in ledgers if led.get("conjunction_ts") is not None)
    n_delay = sum(
        1
        for led in ledgers
        if led.get("conjunction_ts") is not None
        and led.get("first_primitive") not in (None, "both")
        and led.get("conjunction_ts") != led.get("first_primitive_ts")
    )
    veto_counts: dict[str, int] = {}
    for led in ledgers:
        v = led.get("veto_reason")
        if v:
            veto_counts[str(v)] = veto_counts.get(str(v), 0) + 1
    add_d = filled_dev[CONJ_ID] - filled_dev[CONTROL_ID]
    add_h = filled_hol[CONJ_ID] - filled_hol[CONTROL_ID]
    drop_d = filled_dev[CONTROL_ID] - filled_dev[CONJ_ID]
    drop_h = filled_hol[CONTROL_ID] - filled_hol[CONJ_ID]
    disp_sess = 0
    for c in b_chunks:
        by = {r["name"]: r for r in c["rows"]}
        c0 = by.get(CONTROL_ID) or {}
        c1 = by.get(CONJ_ID) or {}
        f0 = set(c0.get("filled") or [])
        f1 = set(c1.get("filled") or [])
        if (f1 - f0) and (f0 - f1) and int(c0.get("peak") or 0) >= 8:
            disp_sess += 1

    flush_map = {c["session"]: c for c in flush_chunks}
    daily_flush = {
        **{d.isoformat(): float(flush_map.get(d.isoformat(), {}).get("pnl") or 0.0) for d in develop},
        **{d.isoformat(): float(flush_map.get(d.isoformat(), {}).get("pnl") or 0.0) for d in holdout},
    }
    flush_dev = [daily_flush[d.isoformat()] for d in develop]
    flush_hol = [daily_flush[d.isoformat()] for d in holdout]
    from research.arrow3 import _summarize

    flush_sm_d = _summarize(flush_dev, [], len(develop))
    flush_sm_h = _summarize(flush_hol, [], len(holdout))

    def _promo(dev, hol) -> bool:
        return hol["clears_200"] and dev["per_day"] >= 0

    green = [r for r in results if r["develop"]["per_day"] >= 0]
    if green:
        best = max(green, key=lambda r: r["develop"]["per_day"])
    else:
        best = ctrl
    comb_d = combine_books(
        {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in develop},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in develop},
    )
    comb_h = combine_books(
        {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in holdout},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in holdout},
    )
    flush_tr_d = [
        t for c in flush_chunks if c["session"] in develop_set for t in c.get("trades") or []
    ]
    flush_tr_h = [
        t for c in flush_chunks if c["session"] in holdout_set for t in c.get("trades") or []
    ]
    peak_d = joint_peak_risk(trades_map[best["name"]]["dev"], flush_tr_d)
    peak_h = joint_peak_risk(trades_map[best["name"]]["hol"], flush_tr_h)

    promo = [r["name"] for r in results if _promo(r["develop"], r["holdout"])]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 32 book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not expected value (EV)."
        )
    pass_names = ", ".join(promo) if promo else "none"
    honesty = (
        f"Id 0 is the A31 lock reprint. $200 pass={pass_names}. "
        f"COMBINED uses the brief's best develop-not-red B ({best['name']}, "
        f"develop ${best['develop']['per_day']:.2f}/day), not the pass book. Combined holdout is not EV."
    )

    veto_s = ", ".join(f"{k}={v}" for k, v in sorted(veto_counts.items())) or "none"
    lines = [
        "Arrow 32 — B-short: first full conjunction, trail rings, unarmed-red cut",
        verdict,
        honesty,
        "Combined holdout is not expected value (EV). Do not write that the account is one improvement from $200.",
        "A1-A5 on. last_entry_at=11:59. Flatten 15:59 on trail rows. SSR=uptick10. No flush rings. "
        "No $500/idea. No virgin pull. No cell-buy. No Arrow 33.",
        "Acronyms: EMA = exponential moving average; ATR = Average True Range; "
        "MFE = maximum favorable excursion; RVOL = relative volume; IWM = iShares Russell 2000 ETF; "
        "SSR = Short Sale Restriction.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap={capped}  tape={FULL_BARS}",
        "Door: frozen repaired leader (5-min close below EMA9). Id 1 waits for close<EMA9 and EMA9<EMA21 "
        "at the same bar_end. Ids 2-5 locked cohort (same admits as id 0).",
        drift,
        "",
        (
            f"Id 1 ledger: name-days scanned={n_led} conjunction={n_conj_hit} delayed={n_delay} "
            f"veto={veto_s}"
        ),
        (
            f"Id 1 vs id 0 filled names: develop added={len(add_d)} dropped={len(drop_d)}  "
            f"holdout added={len(add_h)} dropped={len(drop_h)}  "
            f"cap8-displace sessions (peak>=8 and both add and drop)={disp_sess}"
        ),
        "",
        f"{'id':<28} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'avgR':>7} "
        f"{'PF':>6} {'t_hold':>7} {'MFE-cap':>8} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if _promo(r["develop"], h):
            flag = "BOTH"
        lines.append(
            f"{r['name']:<28} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['avg_r']:7.3f} {h['pf_s']:>6} {h['t_stat']:7.2f} "
            f"{h['mfe_cap']:8.3f} {flag:>6}"
        )
        lines.append(f"  develop {_fmt(r['develop'], holdout=False)}")
        lines.append(
            f"    PF={r['develop']['pf_s']}  peak_conc={r['develop']['peak_conc']}  "
            f"mean_conc={r['develop']['mean_conc']:.2f}  ssr_share={r['ssr_share']:.3f}  "
            f"ssr_nofill={r['ssr_nofill']}  MFE-capture={r['develop']['mfe_cap']:.3f}  "
            f"unarmed_red={r['develop'].get('unarmed_red', 0)}"
        )
        lines.append(
            f"    marked equity: daily-close DD$={r['develop']['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={r['develop']['intraday_dd']:.2f}"
        )
        lines.append(f"  holdout {_fmt(r['holdout'], holdout=True)}")
        lines.append(
            f"    PF={h['pf_s']}  peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}  "
            f"MFE-capture={h['mfe_cap']:.3f}  unarmed_red={h.get('unarmed_red', 0)}  "
            f"IWM alpha hold ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
        lines.append(
            f"    marked equity: daily-close DD$={h['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={h['intraday_dd']:.2f}"
        )
    lines.append("")
    lines.append(
        f"flush|max6|repaired (A31 reprint, not rescored) develop ${flush_sm_d['per_day']:.2f}/day "
        f"holdout ${flush_sm_h['per_day']:.2f}/day"
    )
    lines.append("")
    lines.append(f"COMBINED {best['name']} + {FLUSH_ID}  (best develop-not-red B this file + A31 flush)")
    lines.append(
        f"  develop $/day={comb_d['per_day']:.2f}  std={comb_d['std_day']:.2f}  "
        f"se={comb_d['se_day']:.2f}  t={comb_d['t_stat']:.2f}  "
        f"ci95=[{comb_d['ci_lo']:.2f},{comb_d['ci_hi']:.2f}]  maxDD$={comb_d['max_dd']:.2f}  "
        f"corr={comb_d['corr'].get((0, 1), 0.0):.3f}  joint_peak_risk_B$={peak_d:.2f}"
    )
    lines.append(
        f"  holdout $/day={comb_h['per_day']:.2f}  std={comb_h['std_day']:.2f}  "
        f"se={comb_h['se_day']:.2f}  t={comb_h['t_stat']:.2f}  "
        f"ci95=[{comb_h['ci_lo']:.2f},{comb_h['ci_hi']:.2f}]  maxDD$={comb_h['max_dd']:.2f}  "
        f"corr={comb_h['corr'].get((0, 1), 0.0):.3f}  joint_peak_risk_B$={peak_h:.2f}  NOT EV"
    )
    lines.append("NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow32_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 32",
        "",
        verdict,
        "",
        "B-short conjunction and trail rings on the A31 lock. A1-A5 on. last_entry_at=11:59. "
        "No flush rings. No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 33.",
        honesty,
        drift,
        (
            f"Id 1 vs id 0 filled: develop added={len(add_d)} dropped={len(drop_d)} "
            f"holdout added={len(add_h)} dropped={len(drop_h)} cap8-displace_sess={disp_sess}"
        ),
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"MFE-capture={r['holdout']['mfe_cap']:.3f} IWM skip={r['alpha_skip_hol']}"
        )
    bits.append(
        f"COMBINED {best['name']}+flush|max6|repaired develop ${comb_d['per_day']:.2f} "
        f"holdout ${comb_h['per_day']:.2f} NOT EV"
    )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
