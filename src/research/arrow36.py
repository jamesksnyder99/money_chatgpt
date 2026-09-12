"""Arrow 36 — ungated RTH confirmed-launch birth by hour bucket."""

from __future__ import annotations

import array
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow19 import _pack
from research.arrow20 import _iso, _read_hot_bars
from research.arrow23 import _fmt_adv
from research.arrow31 import (
    _alpha_daily,
    _pack_trades,
    _summ_side,
    ensure_iwm_full_hours,
)
from research.arrow33 import CONTROL_ID as B_LOCK_ID
from research.arrow34 import _reprint_b_lock
from research.book import concurrent_stats, joint_peak_risk, marked_equity_session, replay_session
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.harness import calendar_prior_dvs, confirmed_launch, cum_dv_array, minute_idx, run_rel_vol
from research.rockets import MIN_PRIORS
from research.signals import MINUTE_1159, MINUTE_1559, bar_time
from research.split import develop_holdout
from research.strategies30 import harvestable_from_fillable
from research.strategies36 import (
    WIN_AM,
    WIN_EARLY,
    WIN_LATE,
    WIN_PM,
    in_launch_window,
    rth_birth_long,
)

ET = ZoneInfo("America/New_York")
PRICE_LO = 3.0
PRICE_HI = 20.0
SHELVE_N = 40

# A31 flush control reprint if no develop-not-red birth id.
A31_FLUSH_ID = "flush|max6|repaired"
A31_FLUSH_DEV = 6.20
A31_FLUSH_HOL = 79.10
A31_FLUSH_N_HOL = 19
A33_B_DEV = 72.57
A33_B_HOL = 175.40
A33_B_N_HOL = 93
A33_COMB_DEV = 78.77
A33_COMB_HOL = 254.50
A33_COMB_DEV_LINE = (
    "  develop $/day=78.77  std=752.67  se=116.14  t=0.68  "
    "ci95=[-142.76,297.17]  maxDD$=-2953.13  corr=-0.236  joint_peak_risk$=2135.37"
)
A33_COMB_HOL_LINE = (
    "  holdout $/day=254.50  std=555.62  se=118.46  t=2.15  "
    "ci95=[29.03,476.84]  maxDD$=-972.10  corr=-0.058  joint_peak_risk$=1911.84  NOT EV"
)

CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
    "harness_stop": True,
    "cost_gate": True,
}
EXPERIMENTS = (
    (
        "birth|0945-1159|flat1159",
        WIN_AM,
        {"flatten_at": MINUTE_1159, "last_entry_at": MINUTE_1159},
    ),
    (
        "birth|0945-1159|atr1559",
        WIN_AM,
        {
            "flatten_at": MINUTE_1559,
            "last_entry_at": MINUTE_1559,
            "atr_trail": True,
            "trail_atr_mult": 1.0,
            "trail_arm_r": 1.0,
        },
    ),
    (
        "birth|0945-1029|flat1159",
        WIN_EARLY,
        {"flatten_at": MINUTE_1159, "last_entry_at": MINUTE_1159},
    ),
    (
        "birth|1030-1159|flat1159",
        WIN_LATE,
        {"flatten_at": MINUTE_1159, "last_entry_at": MINUTE_1159},
    ),
    (
        "birth|1200-1500|atr1559",
        WIN_PM,
        {
            "flatten_at": MINUTE_1559,
            "last_entry_at": MINUTE_1559,
            "atr_trail": True,
            "trail_atr_mult": 1.0,
            "trail_arm_r": 1.0,
        },
    ),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
WIN_BY = {e[0]: e[1] for e in EXPERIMENTS}


def _scan_one(df: pl.DataFrame, pc: float, prior_dv: float) -> dict | None:
    pack = _pack(df)
    if pack is None or pc is None or pc <= 0:
        return None
    rec = confirmed_launch(pack, pc)
    today_vol = float(sum(pack["vol"]))
    cumdv = array.array("d", cum_dv_array(pack))
    confirm_ts = rec["confirm_ts"] if rec["confirmed"] else None
    launch_ts = rec["launch_close_ts"] if rec["confirmed"] else None
    harv = 0.0
    if confirm_ts is not None:
        h = harvestable_from_fillable(pack, confirm_ts, df)
        harv = float(h.get("harvestable") or 0.0)
    idx = minute_idx(confirm_ts) if confirm_ts is not None else None
    return {
        "confirmed": bool(rec["confirmed"]),
        "launch_close_ts": launch_ts,
        "confirm_ts": confirm_ts,
        "today_vol": today_vol,
        "cumdv": cumdv,
        "launch_idx": idx,
        "harvestable": harv,
        "prior_close": pc,
        "prior_dv": prior_dv,
    }


def _session_scan(args: tuple) -> tuple[str, dict[str, dict]]:
    d, want = args
    iso = d.isoformat()
    folder = FULL_BARS / iso
    out: dict[str, dict] = {}
    if not folder.exists():
        return iso, out
    for path in folder.glob("*.parquet"):
        try:
            df = pl.read_parquet(path)
        except Exception:  # noqa: BLE001
            continue
        if df.height == 0:
            continue
        sym = str(df["symbol"][0]) if "symbol" in df.columns else path.stem.lstrip("_")
        meta = want.get(sym) if want is not None else None
        if not meta:
            continue
        rec = _scan_one(df, meta["prior_close"], meta["prior_dv"])
        if rec is None:
            continue
        rec["symbol"] = sym
        out[sym] = rec
    return iso, out


def _replay_one(args: tuple) -> dict:
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
    packs = {}
    for h in names:
        sdf = bars.get(h["symbol"])
        if sdf is None or sdf.height == 0:
            continue
        pk = _pack(sdf)
        if pk is not None:
            packs[h["symbol"]] = pk
    rows = []
    for name, win, extra in EXPERIMENTS:
        sigs = []
        for h in names:
            sdf = bars.get(h["symbol"])
            pack = packs.get(h["symbol"])
            if sdf is None or pack is None:
                continue
            score = float(h.get("run_rel_vol") if h.get("run_rel_vol") is not None else 0.0)
            for s in rth_birth_long(sdf, pack, h["prior_close"], win, score=score, tag=name):
                if s.side != 1:
                    continue
                sigs.append(s)
        need = {s.symbol for s in sigs}
        sub = {k: bars[k] for k in need if k in bars}
        st = {}
        trades = replay_session(sub, sigs, prior_dv, stats=st, **CAP8, **extra)
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
                "intraday_dd": float((mtm or {}).get("intraday_peak_to_trough") or 0.0),
            }
        )
    return {"session": iso, "n_cand": len(names), "rows": rows}


def _bucket_harvestable(field: list[dict], win: tuple[time, time]) -> tuple[float, int]:
    sub = [r for r in field if in_launch_window(r.get("launch_close_ts"), win)]
    return sum(float(r.get("harvestable") or 0.0) for r in sub), len(sub)


def run_arrow36(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    cal_isos = [_iso(d) for d in all_sess]
    study_isos = {_iso(d) for d in study}
    print(
        f"research start mode=arrow36 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "ungated RTH confirmed-launch birth on one-minute bars. No cell. No score gate. "
        "No RVOL floor. No B-short rescore. No $500/idea. No virgin pull. Combined holdout is not EV. "
        "No Arrow 37.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
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

    print(f"scan confirmed launch n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow36_scan")
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

    vol_hist: dict[str, dict[str, float]] = {}
    cumdv_hist: dict[str, dict[str, array.array]] = {}
    for iso in cal_isos:
        for st in feat.get(iso, {}).values():
            vol_hist.setdefault(st["symbol"], {})[iso] = float(st.get("today_vol") or 0.0)
            cumdv_hist.setdefault(st["symbol"], {})[iso] = st["cumdv"]

    field_rows: list[dict] = []
    cand: dict[str, list[dict]] = {iso: [] for iso in study_isos}
    prior_dv_by: dict[str, dict[str, float]] = {iso: {} for iso in study_isos}
    for d in all_sess:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            sym = st["symbol"]
            prior_v = [vol_hist[sym][s] for s in cal_isos if s < iso and s in vol_hist.get(sym, {})]
            n_prior = len(prior_v)
            rel = None
            if st.get("launch_idx") is not None:
                idx = int(st["launch_idx"])
                by_iso = {
                    s: float(arr[idx])
                    for s, arr in cumdv_hist.get(sym, {}).items()
                    if arr is not None and idx < len(arr)
                }
                cal = calendar_prior_dvs(by_iso, iso, cal_isos)
                today_dv = by_iso.get(iso)
                if cal["n_present"] >= 5 and today_dv is not None:
                    rel = run_rel_vol(today_dv, cal["values"])
            st["n_prior"] = n_prior
            st["run_rel_vol"] = rel
            if iso not in study_isos:
                continue
            if n_prior < MIN_PRIORS:
                continue
            if not st["confirmed"] or st.get("launch_close_ts") is None:
                continue
            field_rows.append(
                {
                    "session": iso,
                    "symbol": sym,
                    "launch_close_ts": st["launch_close_ts"],
                    "harvestable": float(st.get("harvestable") or 0.0),
                }
            )
            clock = bar_time(st["launch_close_ts"])
            if clock < WIN_AM[0] or clock > WIN_PM[1]:
                continue
            cand[iso].append(
                {
                    "symbol": sym,
                    "prior_close": st["prior_close"],
                    "prior_dv": st["prior_dv"],
                    "run_rel_vol": rel,
                    "harvestable": float(st.get("harvestable") or 0.0),
                    "launch_close_ts": st["launch_close_ts"],
                }
            )
            prior_dv_by[iso][sym] = st["prior_dv"]

    for iso in feat:
        for st in feat[iso].values():
            st["cumdv"] = None
    cumdv_hist.clear()

    replay_jobs = [
        (_iso(d), cand.get(_iso(d), []), prior_dv_by.get(_iso(d), {}))
        for d in develop + holdout
    ]
    print(f"replay birth ids {len(replay_jobs)} sessions x {len(IDS)}", flush=True)
    prog2 = Progress(len(replay_jobs), "arrow36_replay")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk.get("n_cand") or 0)
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    print("reprint A33 B|conj|atr1559|lock daily series for COMBINED (not a B rescore)", flush=True)
    iwm = ensure_iwm_full_hours(workers=workers)
    b_chunks = _reprint_b_lock(elig, all_sess, develop, holdout, workers)
    _write_report(chunks, b_chunks, field_rows, iwm, workers, cpu, develop, holdout)
    return 0


def _write_report(chunks, b_chunks, field_rows, iwm, workers, cpu, develop, holdout) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    f_rows = [r for c in chunks for r in c["rows"]]
    field_dev = [r for r in field_rows if r["session"] in develop_set]
    field_hol = [r for r in field_rows if r["session"] in holdout_set]
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
        win = WIN_BY[name]
        bsum_d, bn_d = _bucket_harvestable(field_dev, win)
        bsum_h, bn_h = _bucket_harvestable(field_hol, win)
        cap_d = 0.0
        n_hit_d = 0
        traded_d = {(str(t.get("entry_ts") or "")[:10], t.get("symbol")) for t in tr_d}
        for r in field_dev:
            if (r["session"], r["symbol"]) in traded_d:
                cap_d += float(r["harvestable"] or 0.0)
                n_hit_d += 1
        cap_h = 0.0
        n_hit_h = 0
        traded_h = {(str(t.get("entry_ts") or "")[:10], t.get("symbol")) for t in tr_h}
        for r in field_hol:
            if (r["session"], r["symbol"]) in traded_h:
                cap_h += float(r["harvestable"] or 0.0)
                n_hit_h += 1
        shelve = sm_d["n_trades"] < SHELVE_N
        results.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "alpha_hol": {"per_day": (sum(a_hol) / len(holdout)) if holdout else 0.0},
                "n_alpha_hol": n_ah,
                "alpha_skip_hol": skip_h,
                "shelve": shelve,
                "harv_field_d": bsum_d,
                "harv_n_d": bn_d,
                "harv_cap_d": cap_d,
                "harv_hit_d": n_hit_d,
                "harv_field_h": bsum_h,
                "harv_n_h": bn_h,
                "harv_cap_h": cap_h,
                "harv_hit_h": n_hit_h,
            }
        )

    def _promo(r) -> bool:
        return (
            not r["shelve"]
            and r["holdout"]["clears_200"]
            and r["develop"]["per_day"] >= 0
        )

    green = [r for r in results if (not r["shelve"]) and r["develop"]["per_day"] >= 0]
    if green:
        best = max(green, key=lambda r: r["develop"]["per_day"])
        best_label = best["name"]
    else:
        best = None
        best_label = A31_FLUSH_ID

    b_rows = [r for c in b_chunks for r in c["rows"] if r["name"] == B_LOCK_ID]
    sm_bd, _bdd, tr_bd, map_bd = _summ_side(b_rows, develop)
    sm_bh, _bdh, tr_bh, map_bh = _summ_side(b_rows, holdout)

    if best is not None:
        comb_d = combine_books(
            map_bd,
            {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in develop},
        )
        comb_h = combine_books(
            map_bh,
            {d.isoformat(): daily_map[best["name"]].get(d.isoformat(), 0.0) for d in holdout},
        )
        peak_d = joint_peak_risk(tr_bd, trades_map[best["name"]]["dev"])
        peak_h = joint_peak_risk(tr_bh, trades_map[best["name"]]["hol"])
    else:
        comb_d = None
        comb_h = None
        peak_d = 0.0
        peak_h = 0.0

    promo = [r["name"] for r in results if _promo(r)]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 36 birth book has holdout >= $200/day AND non-red develop "
            "(ids with develop n < 40 are SHELVED). Combined holdout is not expected value (EV)."
        )
    honesty = (
        f"Ungated RTH confirmed launch. No cell. No score gate. No RVOL floor. "
        f"B-short not rescored; COMBINED uses A33 {B_LOCK_ID} reprint "
        f"(develop ${sm_bd['per_day']:.2f}/day) + "
        + (
            f"best develop-not-red id this file ({best_label})."
            if best is not None
            else f"A31 flush control reprint ({A31_FLUSH_ID}) because no develop-not-red birth id with n>=40."
        )
        + " Combined holdout is not EV."
    )

    lines = [
        "Arrow 36 — ungated RTH confirmed-launch birth by hour",
        verdict,
        honesty,
        "Combined holdout is not expected value (EV). Do not write that the account is one improvement from $200.",
        "No cell. No FLY label. No 08:00 hot. No score decile gate. No RVOL floor. "
        "No B-short rescore. No $500/idea. No virgin pull. No Arrow 37.",
        "Acronyms: ATR = Average True Range; RVOL = relative volume; MFE = maximum favorable excursion; "
        "IWM = iShares Russell 2000 ETF.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  tape={FULL_BARS}",
        "Population: prior_close [$3,$20], >=5 prior sessions, confirmed 1-min launch "
        "(close>=1.10*pc, next tradeable low>=1.08*pc). Entry=next 1-min open. "
        "Stop=max(15-min lookback low, 1.0x ATR, 0.6% of price). Cap8, $200/idea, rank by run_rel_vol at signal. "
        "A1: launch close complete before the order. SHELVE if develop n<40.",
        "",
        f"{'id':<28} {'dev $/day':>10} {'hold $/day':>11} {'dev n':>6} {'hold n':>7} {'avgR':>7} "
        f"{'PF':>6} {'t_hold':>7} {'MFE-cap':>8} {'1R':>6} {'>=200':>6}",
    ]
    for r in results:
        h = r["holdout"]
        flag = "SHELVE" if r["shelve"] else ("YES" if h["clears_200"] else "NO")
        if (not r["shelve"]) and h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if _promo(r):
            flag = "BOTH"
        lines.append(
            f"{r['name']:<28} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{r['develop']['n_trades']:6d} {h['n_trades']:7d} {h['avg_r']:7.3f} {h['pf_s']:>6} "
            f"{h['t_stat']:7.2f} {h['mfe_cap']:8.3f} {h.get('frac_1r', 0.0):6.3f} {flag:>6}"
        )
        if r["shelve"]:
            lines.append(
                f"  SHELVE develop n={r['develop']['n_trades']} < {SHELVE_N} — not a tuner, not a pass."
            )
        lines.append("  develop")
        lines.extend(_fmt_adv(r["develop"]))
        share_d = (r["harv_cap_d"] / r["harv_field_d"]) if r["harv_field_d"] else 0.0
        lines.append(
            f"    MFE-capture={r['develop']['mfe_cap']:.3f}  reached_1R={r['develop'].get('frac_1r', 0.0):.3f}  "
            f"stop%={100 * r['develop'].get('pct_stop', 0.0):.1f}  time%={100 * r['develop'].get('pct_time', 0.0):.1f}  "
            f"peak_conc={r['develop']['peak_conc']}  mean_conc={r['develop']['mean_conc']:.2f}"
        )
        lines.append(
            f"    harvestable captured/bucket={100 * r['harv_cap_d']:.2f}pp/"
            f"{100 * r['harv_field_d']:.2f}pp ({100 * share_d:.1f}%)  "
            f"name-days {r['harv_hit_d']}/{r['harv_n_d']}"
        )
        lines.append(
            f"    marked equity: daily-close DD$={r['develop']['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={r['develop']['intraday_dd']:.2f}"
        )
        lines.append("  holdout PEEK")
        lines.extend(_fmt_adv(h))
        share_h = (r["harv_cap_h"] / r["harv_field_h"]) if r["harv_field_h"] else 0.0
        lines.append(
            f"    MFE-capture={h['mfe_cap']:.3f}  reached_1R={h.get('frac_1r', 0.0):.3f}  "
            f"stop%={100 * h.get('pct_stop', 0.0):.1f}  time%={100 * h.get('pct_time', 0.0):.1f}  "
            f"peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}  "
            f"IWM alpha hold ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
        lines.append(
            f"    harvestable captured/bucket={100 * r['harv_cap_h']:.2f}pp/"
            f"{100 * r['harv_field_h']:.2f}pp ({100 * share_h:.1f}%)  "
            f"name-days {r['harv_hit_h']}/{r['harv_n_h']}  PEEK"
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
    if best is not None and comb_d is not None and comb_h is not None:
        lines.append(
            f"COMBINED {B_LOCK_ID} + {best['name']}  (A33 B lock reprint + best develop-not-red birth)"
        )
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
    else:
        lines.append(
            f"COMBINED {B_LOCK_ID} + {A31_FLUSH_ID}  (A33 B lock reprint + A31 flush control; no birth id qualified)"
        )
        lines.append(A33_COMB_DEV_LINE)
        lines.append(A33_COMB_HOL_LINE)
    lines.append("NO* = holdout >= 200 but develop is red — not a pass. SHELVE = develop n<40. Combined holdout is not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow36_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 36",
        "",
        verdict,
        "",
        "Ungated RTH confirmed-launch birth on one-minute bars. No cell. No score gate. "
        "No RVOL floor. No B-short rescore. No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 37.",
        honesty,
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_dev={r['develop']['n_trades']} "
            f"n_hold={r['holdout']['n_trades']} MFE-capture={r['holdout']['mfe_cap']:.3f} "
            f"reached_1R={r['holdout'].get('frac_1r', 0.0):.3f}"
            + (" SHELVE" if r["shelve"] else "")
        )
    if best is not None and comb_d is not None and comb_h is not None:
        bits.append(
            f"COMBINED {B_LOCK_ID}+{best['name']} develop ${comb_d['per_day']:.2f} "
            f"holdout ${comb_h['per_day']:.2f} NOT EV"
        )
    else:
        bits.append(
            f"COMBINED {B_LOCK_ID}+{A31_FLUSH_ID} develop ${A33_COMB_DEV:.2f} "
            f"holdout ${A33_COMB_HOL:.2f} NOT EV (reprint)"
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
