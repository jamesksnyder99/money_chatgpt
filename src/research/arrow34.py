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
from research.arrow4 import TRACK_A_MAX_PX, TRACK_A_MIN_PX, _filter_track_b
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _fmt_adv
from research.arrow24 import _session_scan
from research.arrow31 import (
    _alpha_daily,
    _pack_trades,
    _summ_side,
    ensure_iwm_full_hours,
)
from research.arrow32 import FLUSH_ID
from research.arrow33 import CONTROL_ID as B_LOCK_ID
from research.arrow33 import _prep_one as _b_prep
from research.arrow33 import _replay_one as _b_replay
from research.book import concurrent_stats, joint_peak_risk, marked_equity_session, replay_session
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.harness import PRICE_FLOOR_PX5, calendar_prior_dvs, run_rel_vol
from research.signals import MINUTE_1159, MINUTE_1330, MINUTE_1559
from research.split import develop_holdout
from research.strategies22 import hot_gate_0800
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long, score_flush
from research.strategies26 import MAX_UNDERCUT

ET = ZoneInfo("America/New_York")
A31_FLUSH_N_DEV = 21
CONTROL_ID = "flush|max6|flat1159"

FLUSH_BASE = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
    "harness_stop": True,
    "cost_gate": True,
    "last_entry_at": MINUTE_1159,
}
EXPERIMENTS = (
    (CONTROL_ID, {"flatten_at": MINUTE_1159}),
    (
        "flush|max6|atr1559",
        {"flatten_at": MINUTE_1559, "atr_trail": True, "trail_atr_mult": 1.0, "trail_arm_r": 1.0},
    ),
    (
        "flush|max6|arm05",
        {"flatten_at": MINUTE_1559, "atr_trail": True, "trail_atr_mult": 1.0, "trail_arm_r": 0.5},
    ),
    (
        "flush|max6|atr15",
        {"flatten_at": MINUTE_1559, "atr_trail": True, "trail_atr_mult": 1.5, "trail_arm_r": 1.0},
    ),
    (
        "flush|max6|atr1330",
        {"flatten_at": MINUTE_1330, "atr_trail": True, "trail_atr_mult": 1.0, "trail_arm_r": 1.0},
    ),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _replay_flush_exits(args: tuple) -> dict:
    iso, names, prior_dv = args
    session = date.fromisoformat(iso)
    empty_rows = [
        {
            "session": iso,
            "name": n,
            "pnl": 0.0,
            "trades": [],
            "peak": 0,
            "mean_conc": 0.0,
            "intraday_dd": 0.0,
        }
        for n in IDS
    ]
    empty = {"session": iso, "n_cand": len(names), "rows": empty_rows}
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
    rows = []
    for name, extra in EXPERIMENTS:
        st = {}
        trades = replay_session(sub, sigs, prior_dv, stats=st, **FLUSH_BASE, **extra)
        packed = _pack_trades(trades, bars)
        peak, mean_c = concurrent_stats(trades)
        mtm = marked_equity_session(trades, bars)
        rows.append(
            {
                "session": iso,
                "name": name,
                "pnl": sum(t.pnl for t in trades),
                "trades": packed,
                "peak": peak,
                "mean_conc": mean_c,
                "intraday_dd": float(mtm["intraday_peak_to_trough"]),
                "unresolved_flatten": int(st.get("unresolved_flatten") or 0),
                "unresolved_late": int(st.get("unresolved_late") or 0),
            }
        )
    return {"session": iso, "n_cand": len(names), "rows": rows}


def _flush_universe(elig, all_sess, study, develop, holdout, workers):
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
    prog = Progress(len(all_sess), "arrow34_flush_pre")
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
    return [
        (_iso(d), feats_by_sess.get(_iso(d), []), prior_dv_by_sess.get(_iso(d), {}))
        for d in develop + holdout
    ]


def _reprint_b_lock(elig, all_sess, develop, holdout, workers) -> list[dict]:
    """Frozen A33 B|conj|atr1559|lock daily series. Not a new B ring."""
    track_b, _capped = _filter_track_b(elig)
    sess_order = [d.isoformat() for d in all_sess]
    want = set(str(s) for s in track_b["symbol"].unique().to_list())
    by_sess: dict[str, list[dict]] = {iso: [] for iso in sess_order}
    drift_sess: dict[str, list[dict]] = {iso: [] for iso in sess_order}
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
        row = {"symbol": sym, "prior_close": pc, "prior_dv": float(rec["prior_dollar_volume"] or 0.0)}
        by_sess.setdefault(iso, []).append(row)
        if TRACK_A_MIN_PX - 1e-12 <= pc <= TRACK_A_MAX_PX + 1e-12:
            drift_sess.setdefault(iso, []).append(row)
        pc_by.setdefault(iso, {})[sym] = pc
    for rec in elig.select("session_date", "symbol", "prior_close").iter_rows(named=True):
        pc = rec["prior_close"]
        if pc is None:
            continue
        iso = _iso(rec["session_date"])
        pc_by.setdefault(iso, {})[str(rec["symbol"])] = float(pc)
    print(f"B reprint (A33 {B_LOCK_ID}, not a rescore) n_sess={len(all_sess)}", flush=True)
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow34_b_pre")
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
    jobs = []
    for d in develop + holdout:
        iso = _iso(d)
        jobs.append(
            (
                iso,
                by_sess.get(iso, []),
                drift_sess.get(iso, []),
                bars15,
                sess_order,
                lows,
                pc_by,
                dv9_hist,
                dv9.get(iso, {}),
                False,
            )
        )
    prog2 = Progress(len(jobs), "arrow34_b")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_b_replay, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    return chunks


def run_arrow34(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow34 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "ATR trail on A31 flush|max6|repaired. Door frozen. B-short not rescored. "
        "No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 35.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    iwm = ensure_iwm_full_hours(workers=workers)
    jobs = _flush_universe(elig, all_sess, study, develop, holdout, workers)
    print(f"pass 2: flush trail {len(jobs)} sessions x {len(IDS)}", flush=True)
    prog = Progress(len(jobs), "arrow34_flush")
    prog.start_heartbeat()
    flush_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_flush_exits, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            flush_chunks.append(chunk)
            prog.mark(chunk["session"], rows=chunk.get("n_cand") or 0)
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    print("pass 3: reprint A33 B|conj|atr1559|lock daily series for COMBINED (not a B rescore)", flush=True)
    b_chunks = _reprint_b_lock(elig, all_sess, develop, holdout, workers)
    _write_reports(flush_chunks, b_chunks, iwm, workers, cpu, develop, holdout)
    return 0


def _write_reports(flush_chunks, b_chunks, iwm, workers, cpu, develop, holdout) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    f_rows = [r for c in flush_chunks for r in c["rows"]]
    results = []
    daily_map = {}
    trades_map = {}
    for name in IDS:
        sub = [r for r in f_rows if r["name"] == name]
        sm_d, _dd, tr_d, map_d = _summ_side(sub, develop)
        sm_h, _dh, tr_h, map_h = _summ_side(sub, holdout)
        daily_map[name] = {**map_d, **map_h}
        trades_map[name] = {"dev": tr_d, "hol": tr_h}
        a_hol, skip_h, n_ah = _alpha_daily(tr_h, holdout, iwm)
        results.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "alpha_hol": {"per_day": (sum(a_hol) / len(holdout)) if holdout else 0.0},
                "n_alpha_hol": n_ah,
                "alpha_skip_hol": skip_h,
            }
        )
    ctrl = next(r for r in results if r["name"] == CONTROL_ID)
    n_d = ctrl["develop"]["n_trades"]
    if abs(n_d - A31_FLUSH_N_DEV) <= 3:
        drift = f"Id 0 develop n={n_d} vs A31 n={A31_FLUSH_N_DEV} — within ±3."
    else:
        drift = f"Id 0 develop n={n_d} vs A31 n={A31_FLUSH_N_DEV} — DRIFT beyond ±3."

    b_rows = [r for c in b_chunks for r in c["rows"] if r["name"] == B_LOCK_ID]
    sm_bd, _bdd, tr_bd, map_bd = _summ_side(b_rows, develop)
    sm_bh, _bdh, tr_bh, map_bh = _summ_side(b_rows, holdout)

    def _promo(dev, hol) -> bool:
        return hol["clears_200"] and dev["per_day"] >= 0

    green = [r for r in results if r["develop"]["per_day"] >= 0]
    if green:
        best = max(green, key=lambda r: r["develop"]["per_day"])
    else:
        best = ctrl
    comb_d = combine_books(map_bd, {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in develop})
    comb_h = combine_books(map_bh, {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in holdout})
    peak_d = joint_peak_risk(tr_bd, trades_map[best["name"]]["dev"])
    peak_h = joint_peak_risk(tr_bh, trades_map[best["name"]]["hol"])

    promo = [r["name"] for r in results if _promo(r["develop"], r["holdout"])]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 34 flush book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not expected value (EV)."
        )
    looks = [
        r["name"]
        for r in results
        if r["develop"]["per_day"] >= 25 - 1e-12
        and r["develop"]["mfe_cap"] >= 0.30 - 1e-12
        and r["develop"]["per_day"] >= 0
    ]
    looks_s = ", ".join(looks) if looks else "none"
    honesty = (
        f"Door frozen (A31 flush|max6|repaired). B-short not rescored; COMBINED uses A33 {B_LOCK_ID} reprint "
        f"(develop ${sm_bd['per_day']:.2f}/day) + best develop-not-red flush ({best['name']}). "
        f"Good-look diagnostic (develop>=$25 and MFE-capture>=0.30, not the pass line): {looks_s}. "
        "Combined holdout is not EV."
    )

    lines = [
        "Arrow 34 — trail on repaired flush|max6",
        verdict,
        honesty,
        "Combined holdout is not expected value (EV). Do not write that the account is one improvement from $200.",
        "A1-A5 on. Long only. Door frozen. No B-short rescore. No $500/idea. No virgin pull. No cell-buy. No Arrow 35.",
        "Acronyms: ATR = Average True Range; MFE = maximum favorable excursion; IWM = iShares Russell 2000 ETF.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  tape={FULL_BARS}",
        "Kernel: 08:00 hot, FLY cell available_at=09:45, $5-20, undercut [2%, 6%], 5-min higher-low + strong close, "
        "ATR-floored stop, cap8, $200/idea. Locked last_entry_at=11:59 (id 0 admits).",
        drift,
        "",
        f"{'id':<24} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'avgR':>7} "
        f"{'PF':>6} {'t_hold':>7} {'MFE-cap':>8} {'1R':>6} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if _promo(r["develop"], h):
            flag = "BOTH"
        lines.append(
            f"{r['name']:<24} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['avg_r']:7.3f} {h['pf_s']:>6} {h['t_stat']:7.2f} "
            f"{h['mfe_cap']:8.3f} {h.get('frac_1r', 0.0):6.3f} {flag:>6}"
        )
        lines.append("  develop")
        lines.extend(_fmt_adv(r["develop"]))
        lines.append(
            f"    MFE-capture={r['develop']['mfe_cap']:.3f}  reached_1R={r['develop'].get('frac_1r', 0.0):.3f}  "
            f"stop%={100 * r['develop'].get('pct_stop', 0.0):.1f}  time%={100 * r['develop'].get('pct_time', 0.0):.1f}  "
            f"peak_conc={r['develop']['peak_conc']}  mean_conc={r['develop']['mean_conc']:.2f}"
        )
        lines.append(
            f"    marked equity: daily-close DD$={r['develop']['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={r['develop']['intraday_dd']:.2f}"
        )
        lines.append("  holdout")
        lines.extend(_fmt_adv(h))
        lines.append(
            f"    MFE-capture={h['mfe_cap']:.3f}  reached_1R={h.get('frac_1r', 0.0):.3f}  "
            f"stop%={100 * h.get('pct_stop', 0.0):.1f}  time%={100 * h.get('pct_time', 0.0):.1f}  "
            f"peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}  "
            f"IWM alpha hold ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
        lines.append(
            f"    marked equity: daily-close DD$={h['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={h['intraday_dd']:.2f}"
        )
    lines.append("")
    lines.append(
        f"A33 {B_LOCK_ID} reprint (not rescored) develop ${sm_bd['per_day']:.2f}/day "
        f"holdout ${sm_bh['per_day']:.2f}/day n_hold={sm_bh['n_trades']}"
    )
    lines.append("")
    lines.append(f"COMBINED {B_LOCK_ID} + {best['name']}  (A33 B lock reprint + best develop-not-red flush)")
    lines.append(
        f"  develop $/day={comb_d['per_day']:.2f}  std={comb_d['std_day']:.2f}  "
        f"se={comb_d['se_day']:.2f}  t={comb_d['t_stat']:.2f}  "
        f"ci95=[{comb_d['ci_lo']:.2f},{comb_d['ci_hi']:.2f}]  maxDD$={comb_d['max_dd']:.2f}  "
        f"corr={comb_d['corr'].get((0, 1), 0.0):.3f}  joint_peak_risk$={peak_d:.2f}"
    )
    lines.append(
        f"  holdout $/day={comb_h['per_day']:.2f}  std={comb_h['std_day']:.2f}  "
        f"se={comb_h['se_day']:.2f}  t={comb_h['t_stat']:.2f}  "
        f"ci95=[{comb_h['ci_lo']:.2f},{comb_h['ci_hi']:.2f}]  maxDD$={comb_h['max_dd']:.2f}  "
        f"corr={comb_h['corr'].get((0, 1), 0.0):.3f}  joint_peak_risk$={peak_h:.2f}  NOT EV"
    )
    lines.append("NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow34_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 34",
        "",
        verdict,
        "",
        "ATR trail on A31 flush|max6|repaired. Door frozen. B-short not rescored. "
        "No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 35.",
        honesty,
        drift,
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"MFE-capture={r['holdout']['mfe_cap']:.3f} reached_1R={r['holdout'].get('frac_1r', 0.0):.3f}"
        )
    bits.append(
        f"COMBINED {B_LOCK_ID}+{best['name']} develop ${comb_d['per_day']:.2f} "
        f"holdout ${comb_h['per_day']:.2f} NOT EV"
    )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
