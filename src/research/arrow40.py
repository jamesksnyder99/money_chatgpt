"""Arrow 40 — session risk budget on frozen B conjunction lock + repaired flush."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow4 import _filter_track_b
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _fmt_adv
from research.arrow24 import _session_scan
from research.arrow31 import (
    FLUSH_CAP8,
    SHORT_POP,
    _alpha_daily,
    _dv_through,
    _pack_trades,
    _summ_side,
    ensure_iwm_full_hours,
)
from research.arrow32 import CONTROL_KW, FLUSH_ID
from research.arrow33 import CONTROL_ID as B_LOCK_ID
from research.arrow33 import MIN_RVOL_PRIORS
from research.arrow33 import _prep_one as _b_prep
from research.book import (
    concurrent_stats,
    joint_peak_risk,
    marked_equity_session,
    outstanding_at,
    replay_session,
    replay_two_books,
)
from research.character import dv_ranks
from research.combine import combine_books
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import stitch_15m
from research.harness import PRICE_FLOOR_PX5, attach_atr, calendar_prior_dvs, run_rel_vol
from research.signals import MINUTE_0929, MINUTE_1159, MINUTE_1559
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies22 import hot_gate_0800
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long, score_flush
from research.strategies26 import MAX_UNDERCUT
from research.strategies32 import conjunction_c5_ema9

ET = ZoneInfo("America/New_York")
A33_B_N_DEV = 228
A33_B_N_HOL = 93
A31_FLUSH_N_DEV = 21
A31_FLUSH_N_HOL = 19
COUNT_TOL = 0.10
SHELVE_N = 0  # not used; budget arrow has no SHELVE n
FLUSH_FLAT = {
    **FLUSH_CAP8,
    "flatten_at": MINUTE_1159,
    "last_entry_at": MINUTE_1159,
}

EXPERIMENTS = (
    ("B200|F200", 200.0, 200.0, None),
    ("B200|F400", 200.0, 400.0, None),
    ("B200|F600", 200.0, 600.0, None),
    ("B400|F400", 400.0, 400.0, None),
    ("Bbud|Fbud|1600", "budget", "budget", 1600.0),
    ("Bbud|Fbud|2400", "budget", "budget", 2400.0),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
CONTROL_ID = IDS[0]


def _within(n: int, ref: int, tol: float = COUNT_TOL) -> bool:
    return abs(n - ref) <= tol * ref + 1e-9


def clamp_rpi(budget: float, n_exp: int) -> float:
    n = int(n_exp)
    if n <= 0:
        return 200.0
    return max(200.0, min(600.0, float(budget) / float(n)))


def _kw_b(rpi: float, joint_cap: float | None = None, other_risk_at=None) -> dict:
    mx = 8.0 * float(rpi)
    if joint_cap is not None:
        mx = min(mx, float(joint_cap))
    return {
        **CONTROL_KW,
        "harness_stop": True,
        "max_positions": 8,
        "max_entries": 16,
        "max_risk_outstanding": mx,
        "risk_per_idea": float(rpi),
        "joint_cap": joint_cap,
        "other_risk_at": other_risk_at,
    }


def _kw_f(rpi: float, joint_cap: float | None = None, other_risk_at=None) -> dict:
    mx = 8.0 * float(rpi)
    if joint_cap is not None:
        mx = min(mx, float(joint_cap))
    return {
        **FLUSH_FLAT,
        "max_risk_outstanding": mx,
        "risk_per_idea": float(rpi),
        "joint_cap": joint_cap,
        "other_risk_at": other_risk_at,
    }


def _peer_fn(trades):
    def at(ts):
        return outstanding_at(trades, ts)

    return at


def _replay_one(args: tuple) -> dict:
    (
        iso,
        b_names,
        flush_names,
        bars15,
        sess_order,
        lows,
        pc_by,
        dv9_hist,
        dv9_now,
    ) = args
    session = date.fromisoformat(iso)
    empty_rows = [
        {
            "session": iso,
            "name": n,
            "pnl_b": 0.0,
            "pnl_f": 0.0,
            "pnl": 0.0,
            "trades_b": [],
            "trades_f": [],
            "trades": [],
            "peak_b": 0,
            "peak_f": 0,
            "mean_conc": 0.0,
            "intraday_dd": 0.0,
            "intraday_dd_b": 0.0,
            "intraday_dd_f": 0.0,
            "joint_peak": 0.0,
            "joint_blocks": 0,
            "rpi_b": 200.0,
            "rpi_f": 200.0,
            "n_hot": 0,
            "n_kernel": 0,
            "at_joint_cap": 0,
        }
        for n in IDS
    ]
    empty = {"session": iso, "n_cand": len(b_names) + len(flush_names), "rows": empty_rows}
    symbols = list({h["symbol"] for h in b_names + flush_names})
    if not symbols:
        return empty
    bars = _read_hot_bars(session, symbols)
    prior_dv = {h["symbol"]: float(h["prior_dv"]) for h in b_names + flush_names}
    prior_c = {}
    for h in b_names + flush_names:
        if h.get("prior_close") is not None:
            prior_c[h["symbol"]] = float(h["prior_close"])
    idx = sess_order.index(iso) if iso in sess_order else -1
    prev_iso = sess_order[idx - 1] if idx > 0 else None
    psl = dict(lows.get(prev_iso) or {}) if prev_iso else {}
    pspc = dict(pc_by.get(prev_iso) or {}) if prev_iso else {}
    ranks = dv_ranks({h["symbol"]: float(h["prior_dv"]) for h in b_names})
    conj_by = {}
    kernel_n = 0
    for h in b_names:
        sym = h["symbol"]
        sdf = bars.get(sym)
        if sdf is None or sdf.height == 0:
            continue
        pc = h.get("prior_close")
        pc = float(pc) if pc is not None else None
        rank = ranks.get(sym, 0.0)
        rng = opening_range(sdf)
        or_w = rng[2] if rng else None
        or_high = rng[0] if rng else None
        gap = session_gap(sdf, pc)
        if not short_kernel_pop(rank, gap, or_w, **SHORT_POP) or or_high is None:
            continue
        kernel_n += 1
        win = calendar_prior_dvs(dv9_hist.get(sym) or {}, iso, sess_order)
        if int(win["n_present"]) < MIN_RVOL_PRIORS:
            continue
        stitched = stitch_15m(sym, iso, sess_order, bars15)
        got, _led = conjunction_c5_ema9(sdf, stitched, or_high)
        for sig in got:
            if sig.side != -1:
                continue
            conj_by[sym] = attach_atr(sig, sdf)
    b_sigs = list(conj_by.values())
    n_hot = len(flush_names)
    f_sigs = []
    for h in flush_names:
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
                f_sigs.append(score_flush(s, score))
    prior_dv_b = {h["symbol"]: float(h["prior_dv"]) for h in b_names}
    prior_dv_f = {h["symbol"]: float(h["prior_dv"]) for h in flush_names}
    rows = []
    for name, rb, rf, budget in EXPERIMENTS:
        if budget is not None:
            rpi_b = clamp_rpi(budget, kernel_n)
            rpi_f = clamp_rpi(budget, n_hot)
            joint = float(budget)
        else:
            rpi_b = float(rb)
            rpi_f = float(rf)
            joint = None
        st_b = {}
        st_f = {}
        if joint is not None:
            need = {s.symbol for s in b_sigs} | {s.symbol for s in f_sigs}
            sub = {k: bars[k] for k in need if k in bars}
            kw_b = _kw_b(rpi_b, joint_cap=joint)
            kw_f = _kw_f(rpi_f, joint_cap=joint)
            kw_b["prior_session_low"] = psl
            kw_b["prior_session_prior_close"] = pspc
            trades_b, trades_f = replay_two_books(
                sub,
                {
                    "signals": b_sigs,
                    "prior_dv": prior_dv_b,
                    "prior_close": prior_c,
                    "kw": kw_b,
                    "stats": st_b,
                },
                {
                    "signals": f_sigs,
                    "prior_dv": prior_dv_f,
                    "prior_close": prior_c,
                    "kw": kw_f,
                    "stats": st_f,
                },
            )
        else:
            trades_b = replay_session(
                {k: bars[k] for k in {s.symbol for s in b_sigs} if k in bars},
                b_sigs,
                prior_dv_b,
                prior_close=prior_c,
                prior_session_low=psl,
                prior_session_prior_close=pspc,
                stats=st_b,
                **_kw_b(rpi_b, joint_cap=None),
            )
            trades_f = replay_session(
                {k: bars[k] for k in {s.symbol for s in f_sigs} if k in bars},
                f_sigs,
                prior_dv_f,
                stats=st_f,
                **_kw_f(rpi_f, joint_cap=None),
            )
        packed_b = _pack_trades(trades_b, bars)
        packed_f = _pack_trades(trades_f, bars)
        packed = packed_b + packed_f
        peak_b, mean_b = concurrent_stats(trades_b)
        peak_f, mean_f = concurrent_stats(trades_f)
        mtm_b = marked_equity_session(trades_b, bars)
        mtm_f = marked_equity_session(trades_f, bars)
        mtm = marked_equity_session(list(trades_b) + list(trades_f), bars)
        jpeak = joint_peak_risk(trades_b, trades_f)
        jblocks = int(st_b.get("joint_blocks") or 0) + int(st_f.get("joint_blocks") or 0)
        at_cap = 0
        if joint is not None and (jblocks > 0 or jpeak >= float(joint) - 1e-6):
            at_cap = 1
        rows.append(
            {
                "session": iso,
                "name": name,
                "pnl_b": sum(t.pnl for t in trades_b),
                "pnl_f": sum(t.pnl for t in trades_f),
                "pnl": sum(t.pnl for t in trades_b) + sum(t.pnl for t in trades_f),
                "trades_b": packed_b,
                "trades_f": packed_f,
                "trades": packed,
                "peak_b": peak_b,
                "peak_f": peak_f,
                "mean_conc": (mean_b + mean_f) / 2.0,
                "intraday_dd": float(mtm["intraday_peak_to_trough"]),
                "intraday_dd_b": float(mtm_b["intraday_peak_to_trough"]),
                "intraday_dd_f": float(mtm_f["intraday_peak_to_trough"]),
                "joint_peak": float(jpeak),
                "joint_blocks": jblocks,
                "rpi_b": rpi_b,
                "rpi_f": rpi_f,
                "n_hot": n_hot,
                "n_kernel": kernel_n,
                "at_joint_cap": at_cap,
            }
        )
    return {"session": iso, "n_cand": len(b_names) + len(flush_names), "rows": rows}


def _flush_universe(elig, all_sess, study, workers):
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
    prog = Progress(len(all_sess), "arrow40_flush_pre")
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
    out: dict[str, list[dict]] = {iso: [] for iso in study_isos}
    for d in study:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            if st["prior_close"] < PRICE_FLOOR_PX5 - 1e-12:
                continue
            if not st.get("hot0800") or st.get("rel0800") is None:
                continue
            out[iso].append(st)
    return out


def run_arrow40(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow40 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "session risk budget on frozen B|conj|atr1559|lock + flush|max6|repaired. "
        "No new door. No Arrow 39. No atr150. No virgin pull. Combined holdout is not EV. No Arrow 41.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    track_b, _capped = _filter_track_b(elig)
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
        by_sess.setdefault(iso, []).append(
            {"symbol": sym, "prior_close": pc, "prior_dv": float(rec["prior_dollar_volume"] or 0.0)}
        )
        pc_by.setdefault(iso, {})[sym] = pc
    for rec in elig.select("session_date", "symbol", "prior_close").iter_rows(named=True):
        pc = rec["prior_close"]
        if pc is None:
            continue
        iso = _iso(rec["session_date"])
        pc_by.setdefault(iso, {})[str(rec["symbol"])] = float(pc)

    print(f"B prep (A33 lock reprint) n_sess={len(all_sess)}", flush=True)
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow40_b_pre")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_b_prep, (d, want)): d for d in all_sess}
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
    dv9_hist: dict[str, dict[str, float]] = {}
    for iso in sess_order:
        for sym, v in (dv9.get(iso) or {}).items():
            dv9_hist.setdefault(sym, {})[iso] = v

    print("flush 08:00 hot universe (A31 door, not a new door)", flush=True)
    flush_by = _flush_universe(elig, all_sess, study, workers)
    iwm = ensure_iwm_full_hours(workers=workers)

    jobs = []
    for d in develop + holdout:
        iso = _iso(d)
        jobs.append(
            (
                iso,
                by_sess.get(iso, []),
                flush_by.get(iso, []),
                bars15,
                sess_order,
                lows,
                pc_by,
                dv9_hist,
                dv9.get(iso, {}),
            )
        )
    print(f"replay budget ids {len(jobs)} sessions x {len(IDS)}", flush=True)
    prog2 = Progress(len(jobs), "arrow40_replay")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk.get("n_cand") or 0)
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    _write_report(chunks, iwm, workers, cpu, develop, holdout)
    return 0


def _write_report(chunks, iwm, workers, cpu, develop, holdout) -> None:
    f_rows = [r for c in chunks for r in c["rows"]]
    results = []
    for name in IDS:
        sub = [r for r in f_rows if r["name"] == name]
        sm_d, _dd, tr_d, map_d = _summ_side(sub, develop)
        sm_h, _dh, tr_h, map_h = _summ_side(sub, holdout)
        sm_bd, _bd, tr_bd, map_bd = _summ_side(sub, develop, trades_key="trades_b")
        sm_bh, _bh, tr_bh, map_bh = _summ_side(sub, holdout, trades_key="trades_b")
        sm_fd, _fd, tr_fd, map_fd = _summ_side(sub, develop, trades_key="trades_f")
        sm_fh, _fh, tr_fh, map_fh = _summ_side(sub, holdout, trades_key="trades_f")

        def _avg_key(sessions, key: str) -> float:
            by = {r["session"]: float(r.get(key) or 0.0) for r in sub}
            xs = [by.get(d.isoformat(), 0.0) for d in sessions]
            return (sum(xs) / len(xs)) if xs else 0.0

        sm_bd = dict(sm_bd)
        sm_bh = dict(sm_bh)
        sm_fd = dict(sm_fd)
        sm_fh = dict(sm_fh)
        sm_bd["per_day"] = _avg_key(develop, "pnl_b")
        sm_bh["per_day"] = _avg_key(holdout, "pnl_b")
        sm_fd["per_day"] = _avg_key(develop, "pnl_f")
        sm_fh["per_day"] = _avg_key(holdout, "pnl_f")
        a_hol, skip_h, n_ah = _alpha_daily(tr_h, holdout, iwm)
        idd_d = min(float(r.get("intraday_dd") or 0.0) for r in sub if r["session"] in {x.isoformat() for x in develop}) if sub else 0.0
        idd_h = min(float(r.get("intraday_dd") or 0.0) for r in sub if r["session"] in {x.isoformat() for x in holdout}) if sub else 0.0
        # recompute min over the slice only
        sub_d = [r for r in sub if r["session"] in {x.isoformat() for x in develop}]
        sub_h = [r for r in sub if r["session"] in {x.isoformat() for x in holdout}]
        idd_d = min((float(r.get("intraday_dd") or 0.0) for r in sub_d), default=0.0)
        idd_h = min((float(r.get("intraday_dd") or 0.0) for r in sub_h), default=0.0)
        jpk_d = max((float(r.get("joint_peak") or 0.0) for r in sub_d), default=0.0)
        jpk_h = max((float(r.get("joint_peak") or 0.0) for r in sub_h), default=0.0)
        cap_d = sum(int(r.get("at_joint_cap") or 0) for r in sub_d)
        cap_h = sum(int(r.get("at_joint_cap") or 0) for r in sub_h)
        mean_rb = (sum(float(r.get("rpi_b") or 0.0) for r in sub_d) / len(sub_d)) if sub_d else 0.0
        mean_rf = (sum(float(r.get("rpi_f") or 0.0) for r in sub_d) / len(sub_d)) if sub_d else 0.0
        worst_d = min((float(r.get("pnl") or 0.0) for r in sub_d), default=0.0)
        worst_h = min((float(r.get("pnl") or 0.0) for r in sub_h), default=0.0)
        results.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "b_dev": sm_bd,
                "b_hol": sm_bh,
                "f_dev": sm_fd,
                "f_hol": sm_fh,
                "alpha_hol": {"per_day": (sum(a_hol) / len(holdout)) if holdout else 0.0},
                "n_alpha_hol": n_ah,
                "alpha_skip_hol": skip_h,
                "idd_d": idd_d,
                "idd_h": idd_h,
                "jpk_d": jpk_d,
                "jpk_h": jpk_h,
                "cap_d": cap_d,
                "cap_h": cap_h,
                "mean_rb": mean_rb,
                "mean_rf": mean_rf,
                "worst_d": worst_d,
                "worst_h": worst_h,
                "map_d": map_d,
                "map_h": map_h,
                "tr_d": tr_d,
                "tr_h": tr_h,
            }
        )

    ctrl = next(r for r in results if r["name"] == CONTROL_ID)
    nb_d, nb_h = ctrl["b_dev"]["n_trades"], ctrl["b_hol"]["n_trades"]
    nf_d, nf_h = ctrl["f_dev"]["n_trades"], ctrl["f_hol"]["n_trades"]
    bits = []
    if _within(nb_d, A33_B_N_DEV) and _within(nb_h, A33_B_N_HOL):
        bits.append(f"Id 0 B n develop {nb_d}/{A33_B_N_DEV} holdout {nb_h}/{A33_B_N_HOL} — within ±10%.")
    else:
        bits.append(f"Id 0 B n develop {nb_d}/{A33_B_N_DEV} holdout {nb_h}/{A33_B_N_HOL} — DRIFT beyond ±10%.")
    if abs(nf_d - A31_FLUSH_N_DEV) <= 3 and abs(nf_h - A31_FLUSH_N_HOL) <= 3:
        bits.append(f"Id 0 flush n develop {nf_d}/{A31_FLUSH_N_DEV} holdout {nf_h}/{A31_FLUSH_N_HOL} — within ±3.")
    else:
        bits.append(f"Id 0 flush n develop {nf_d}/{A31_FLUSH_N_DEV} holdout {nf_h}/{A31_FLUSH_N_HOL} — DRIFT beyond ±3.")
    drift = " ".join(bits)

    def _promo(r) -> bool:
        return r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0

    promo = [r["name"] for r in results if _promo(r)]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 40 budget book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not expected value (EV)."
        )
    looks = [
        r["name"]
        for r in results
        if r["develop"]["per_day"] >= 150 - 1e-12 and abs(r["idd_d"]) < 0.03 * ACCOUNT + 1e-9
    ]
    looks_s = ", ".join(looks) if looks else "none"
    honesty = (
        "Frozen doors only (A33 B|conj|atr1559|lock + A31 flush|max6|repaired). "
        "Sized off intraday peak-to-trough, not daily-close DD. "
        f"Good-look (combined develop>=$150 and joint intraday maxDD<3% of $100k, not the pass line): {looks_s}. "
        "Do not write that $400 flush is safe because daily-close DD was small. Combined holdout is not EV."
    )

    lines = [
        "Arrow 40 — session risk budget on the two standing books",
        verdict,
        honesty,
        "Combined holdout is not expected value (EV). Do not write that the account is one improvement from $200.",
        "No new door. No Arrow 39. No atr150. No cap12. No virgin pull. No Arrow 41.",
        "Acronyms: ATR = Average True Range; MFE = maximum favorable excursion; SSR = Short Sale Restriction.",
        f"account={ACCOUNT:.0f}  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  tape={FULL_BARS}",
        "B: conjunction lock, 1.0x ATR after +1R, last_entry_at=11:59, flatten 15:59, cap8, SSR uptick10. "
        "Flush: max6 repaired, flatten 11:59. "
        "Budget rows: risk_per_idea=clamp(BUDGET/expected_signals, $200, $600); "
        "expected = 08:00 hot count (flush) and 09:29 Track-B gap-down-with-wide-OR count (short). "
        "Joint outstanding never exceeds BUDGET on budget rows.",
        drift,
        "",
        f"{'id':<16} {'dev $/day':>10} {'hold $/day':>11} {'B n':>5} {'F n':>5} "
        f"{'jPeak$':>8} {'inDD%':>7} {'clDD%':>7} {'MFE':>7} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if _promo(r):
            flag = "BOTH"
        in_pct = 100.0 * abs(r["idd_h"]) / ACCOUNT
        cl_pct = 100.0 * abs(h["daily_close_dd"]) / ACCOUNT
        lines.append(
            f"{r['name']:<16} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{r['b_hol']['n_trades']:5d} {r['f_hol']['n_trades']:5d} "
            f"{r['jpk_h']:8.0f} {in_pct:6.2f}% {cl_pct:6.2f}% {h['mfe_cap']:7.3f} {flag:>6}"
        )
        lines.append("  develop")
        lines.extend(_fmt_adv(r["develop"]))
        lines.append(
            f"    B n={r['b_dev']['n_trades']} $/day={r['b_dev']['per_day']:.2f}  "
            f"flush n={r['f_dev']['n_trades']} $/day={r['f_dev']['per_day']:.2f}  "
            f"mean R$ B={r['mean_rb']:.0f} flush={r['mean_rf']:.0f}"
        )
        lines.append(
            f"    MFE-capture={r['develop']['mfe_cap']:.3f}  joint_peak_risk$={r['jpk_d']:.2f}  "
            f"days_at_joint_cap={r['cap_d']}  worst_day$={r['worst_d']:.2f}"
        )
        lines.append(
            f"    marked equity: daily-close DD$={r['develop']['daily_close_dd']:.2f} "
            f"({100 * abs(r['develop']['daily_close_dd']) / ACCOUNT:.2f}% of account)  "
            f"intraday peak-to-trough$={r['idd_d']:.2f} "
            f"({100 * abs(r['idd_d']) / ACCOUNT:.2f}% of account)"
        )
        lines.append("  holdout PEEK")
        lines.extend(_fmt_adv(h))
        lines.append(
            f"    B n={r['b_hol']['n_trades']} $/day={r['b_hol']['per_day']:.2f}  "
            f"flush n={r['f_hol']['n_trades']} $/day={r['f_hol']['per_day']:.2f}"
        )
        lines.append(
            f"    MFE-capture={h['mfe_cap']:.3f}  joint_peak_risk$={r['jpk_h']:.2f}  "
            f"days_at_joint_cap={r['cap_h']}  worst_day$={r['worst_h']:.2f}  "
            f"IWM alpha hold ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
        lines.append(
            f"    marked equity: daily-close DD$={h['daily_close_dd']:.2f} "
            f"({100 * abs(h['daily_close_dd']) / ACCOUNT:.2f}% of account)  "
            f"intraday peak-to-trough$={r['idd_h']:.2f} "
            f"({100 * abs(r['idd_h']) / ACCOUNT:.2f}% of account)"
        )
        lines.append(
            f"  COMBINED {r['name']}  develop ${r['develop']['per_day']:.2f}/day  "
            f"holdout ${h['per_day']:.2f}/day  NOT EV"
        )
    lines.append("")
    lines.append("NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow40_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    log_bits = [
        f"## {stamp} — Arrow 40",
        "",
        verdict,
        "",
        "Session risk budget on frozen B conjunction lock + repaired flush. "
        "No new door. No Arrow 39. No atr150. No virgin pull. Combined holdout is not EV. No Arrow 41.",
        honesty,
        drift,
        "",
    ]
    for r in results:
        log_bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day "
            f"B n_hold={r['b_hol']['n_trades']} flush n_hold={r['f_hol']['n_trades']} "
            f"intraday DD$={r['idd_h']:.2f} ({100 * abs(r['idd_h']) / ACCOUNT:.2f}%) "
            f"joint_peak$={r['jpk_h']:.0f} MFE-capture={r['holdout']['mfe_cap']:.3f}"
        )
    log_bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(log_bits) + "\n", encoding="utf-8")
