from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _summarize
from research.arrow4 import _filter_track_b
from research.arrow19 import CLOCK_0929, _last_at_or_before, _pack
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _fmt_adv, _pack_trades, _summarize_adv
from research.arrow24 import _scan_one
from research.arrow28 import _prep_one as _b_prep_one, _replay_b
from research.book import concurrent_stats, replay_session
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.harness import PRICE_FLOOR, PRICE_FLOOR_PX5, atr_last6_5m, cum_dv_array, run_rel_vol
from research.signals import MINUTE_0944, MINUTE_1159, MINUTE_1330, MINUTE_1559, RTH_OPEN, bar_time
from research.split import develop_holdout
from research.strategies25 import fly_cell_ok
from research.strategies29 import (
    cell_buy_gate,
    cell_buy_long,
    flush_vs_anchor,
    fly_or_dv_ok,
    launch_compatible_long,
    path_from_0944,
)

ET = ZoneInfo("America/New_York")
CLOCK_0944 = time(9, 44)
FROZEN_B = "B_uptick10|atr1559"
CELL_REL_MIN = 3.0

CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
    "harness_stop": True,
    "cost_gate": True,
}

# (id, kind, extra replay kwargs, needs_gate)
EXPERIMENTS = (
    ("cell0945|flat1159", "cell", {"flatten_at": MINUTE_1159}, True),
    (
        "cell0945|hold05",
        "cell",
        {"flatten_at": MINUTE_1159, "hold_plus_r": 0.5, "late_flatten_at": MINUTE_1559},
        True,
    ),
    (
        "cell0945|atr1559",
        "cell",
        {"flatten_at": MINUTE_1559, "atr_trail": True},
        True,
    ),
    ("flush_0944|flat1159", "flush44", {"flatten_at": MINUTE_1159}, False),
    ("flush_orh|flat1159", "flush_or", {"flatten_at": MINUTE_1159}, False),
    ("launch_compat|flat1159", "launch", {"flatten_at": MINUTE_1159}, False),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _or_hl(pack: dict) -> tuple[float | None, float | None]:
    or_h = or_l = None
    for ts, h, l in zip(pack["ts"], pack["high"], pack["low"]):
        t = bar_time(ts)
        if RTH_OPEN <= t <= MINUTE_0944:
            or_h = h if or_h is None else max(or_h, h)
            or_l = l if or_l is None else min(or_l, l)
    return or_h, or_l


def _peak_bucket(peak_ts) -> str | None:
    if peak_ts is None:
        return None
    t = bar_time(peak_ts)
    if t < MINUTE_0944:
        return "before_0944"
    if t <= MINUTE_1159:
        return "0944_1159"
    return "after_1159"


def _scan_fwd(df: pl.DataFrame, pc: float) -> dict | None:
    st = _scan_one(df, pc)
    if st is None:
        return None
    pack = _pack(df)
    if pack is None:
        return st
    or_h, or_l = _or_hl(pack)
    st["or_high"] = or_h
    st["or_low"] = or_l
    i44, _ = _last_at_or_before(pack, CLOCK_0944)
    px44 = st.get("px0944")
    if i44 is None or px44 is None:
        return st
    st["ts0944"] = pack["ts"][i44]
    atr = atr_last6_5m(df, pack["ts"][i44])
    st["atr0944"] = atr
    st.update(path_from_0944(pack, px44=float(px44), or_low=or_l, atr=atr, i44=i44))
    peak_ts = None
    session_high = None
    for ts, h in zip(pack["ts"], pack["high"]):
        if session_high is None or h > session_high + 1e-12:
            session_high = h
            peak_ts = ts
    st["peak_bucket"] = _peak_bucket(peak_ts)
    return st


def _session_fwd(args: tuple) -> tuple[str, dict[str, dict]]:
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
        if want is not None and sym not in want:
            continue
        meta = want.get(sym) if want is not None else None
        if not meta:
            continue
        st = _scan_fwd(df, meta["prior_close"])
        if st is None:
            continue
        st["symbol"] = sym
        st["prior_close"] = meta["prior_close"]
        st["prior_dv"] = meta["prior_dv"]
        out[sym] = st
    return iso, out


def _peak_from_scan(st: dict) -> str | None:
    # _scan_one stores launch_hour not peak_ts. Recompute bucket from minutes_to_peak + origin if needed.
    return st.get("peak_bucket")


def _replay_one(args: tuple) -> dict:
    iso, names, dv_hist, gate = args
    session = date.fromisoformat(iso)
    empty = {
        "session": iso,
        "n_cand": len(names),
        "rows": [
            {"session": iso, "name": n, "pnl": 0.0, "trades": [], "peak": 0, "mean_conc": 0.0}
            for n in IDS
        ],
        "cost_skips": 0,
    }
    if not names:
        return empty
    bars = _read_hot_bars(session, [h["symbol"] for h in names])
    by_id = {n: [] for n in IDS}
    for h in names:
        sdf = bars.get(h["symbol"])
        if sdf is None or sdf.height == 0:
            continue
        pc = h["prior_close"]
        prior_cum = [arr for s, arr in (dv_hist.get(h["symbol"]) or []) if s < iso][-10:]
        rel44 = h.get("rel0944")
        in_cell = fly_cell_ok(h.get("orw"), h.get("dv0929"), h.get("ext0944"))
        px5 = pc >= PRICE_FLOOR_PX5 - 1e-12
        for exp_id, kind, _kw, needs_gate in EXPERIMENTS:
            if needs_gate and not gate:
                continue
            if kind == "cell":
                if not (gate and in_cell and px5):
                    continue
                if rel44 is None or rel44 < CELL_REL_MIN - 1e-12:
                    continue
                by_id[exp_id].extend(
                    cell_buy_long(
                        sdf,
                        signal_ts=h.get("ts0944"),
                        or_low=h.get("or_low"),
                        rel0944=rel44,
                        gate=True,
                        tag=exp_id,
                    )
                )
            elif kind == "flush44":
                if not (in_cell and px5):
                    continue
                for s in flush_vs_anchor(sdf, h.get("px0944"), tag=exp_id):
                    if s.side == 1:
                        by_id[exp_id].append(s)
            elif kind == "flush_or":
                if not (in_cell and px5):
                    continue
                for s in flush_vs_anchor(sdf, h.get("or_high"), tag=exp_id):
                    if s.side == 1:
                        by_id[exp_id].append(s)
            elif kind == "launch":
                if not px5 or not fly_or_dv_ok(h.get("orw"), h.get("dv0929")):
                    continue
                pack = _pack(sdf)
                by_id[exp_id].extend(
                    launch_compatible_long(
                        sdf,
                        pack,
                        pc,
                        ext_0929=h.get("ext0929"),
                        orw=h.get("orw"),
                        dv0929=h.get("dv0929"),
                        cumdv=h.get("cumdv") or [],
                        prior_cum=prior_cum,
                    )
                )
    rows = []
    cost_skips = 0
    for exp_id, _kind, kw, needs_gate in EXPERIMENTS:
        sigs = [s for s in by_id[exp_id] if s.side == 1]
        need = {s.symbol for s in sigs}
        sub = {k: bars[k] for k in need if k in bars}
        st = {}
        cap = dict(CAP8)
        cap.update(kw)
        trades = replay_session(sub, sigs, {h["symbol"]: h["prior_dv"] for h in names}, stats=st, **cap)
        cost_skips += int(st.get("cost_skips") or 0)
        peak, mean_c = concurrent_stats(trades)
        rows.append(
            {
                "session": iso,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": _pack_trades(trades, bars),
                "peak": peak,
                "mean_conc": mean_c,
                "skipped_gate": bool(needs_gate and not gate),
            }
        )
    return {"session": iso, "n_cand": len(names), "rows": rows, "cost_skips": cost_skips}


def _median(xs: list[float]) -> float | None:
    ys = [float(x) for x in xs if x is not None]
    if not ys:
        return None
    return float(statistics.median(ys))


def _mean(xs: list[float]) -> float | None:
    ys = [float(x) for x in xs if x is not None]
    if not ys:
        return None
    return sum(ys) / len(ys)


def _fmt_part_a(rows: list[dict], label: str) -> list[str]:
    n = len(rows)
    lines = [f"  {label} n={n}"]
    if n == 0:
        return lines
    fly = [r for r in rows if r.get("klass") == "FLY"]
    fail = [r for r in rows if r.get("klass") == "FAIL"]
    lines.append(f"    FLY={len(fly)} FAIL={len(fail)} other={n - len(fly) - len(fail)}")

    def _blk(sub, name):
        if not sub:
            return [f"    {name}: n=0"]
        e11 = [r.get("ext1159_44") for r in sub]
        e13 = [r.get("ext1330_44") for r in sub]
        e15 = [r.get("ext1559_44") for r in sub]
        mae = [r.get("mae_atr_1159") for r in sub]
        frac = sum(1 for r in sub if r.get("hit_1atr_before_or")) / len(sub)
        tag = sum(1 for r in sub if r.get("tagged_or_low")) / len(sub)
        return [
            f"    {name} n={len(sub)}",
            f"      median ext vs 09:44 close  11:59={_median(e11)}  13:30={_median(e13)}  15:59={_median(e15)}",
            f"      mean ext vs 09:44 close    11:59={_mean(e11)}  13:30={_mean(e13)}  15:59={_mean(e15)}",
            f"      MAE to 11:59 vs OR-low (ATR) median={_median(mae)} mean={_mean(mae)}",
            f"      frac +1ATR before OR-low={frac:.3f}  frac tagged OR-low={tag:.3f}",
        ]

    lines.extend(_blk(rows, "all"))
    lines.extend(_blk(fly, "FLY"))
    lines.extend(_blk(fail, "FAIL"))
    if fly:
        buckets = {"before_0944": 0, "0944_1159": 0, "after_1159": 0}
        for r in fly:
            b = r.get("peak_bucket")
            if b in buckets:
                buckets[b] += 1
        tot = sum(buckets.values()) or 1
        lines.append(
            f"    FLY max_ext clock: before 09:44={buckets['before_0944']} "
            f"({buckets['before_0944']/tot:.0%})  09:44-11:59={buckets['0944_1159']} "
            f"({buckets['0944_1159']/tot:.0%})  after 11:59={buckets['after_1159']} "
            f"({buckets['after_1159']/tot:.0%})"
        )
    return lines


def _pf(trades: list[dict]) -> str:
    wins = sum(float(t["pnl"]) for t in trades if t["pnl"] > 0)
    losses = abs(sum(float(t["pnl"]) for t in trades if t["pnl"] < 0))
    if not trades:
        return "0"
    if losses <= 1e-12:
        return "inf"
    return f"{wins / losses:.3f}"


def run_arrow29(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow29 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "FLY cell as population; new rocket radii. No flush|max6 synonyms. "
        "No B-short rescore. No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 30.",
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

    print(f"Part A+B scan n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow29_scan")
    prog.start_heartbeat()
    jobs = [(d, by_sess.get(_iso(d), {})) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_fwd, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    dv44_hist: dict[str, list[tuple[str, float]]] = {}
    dv_hist: dict[str, list[tuple[str, list[float]]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for st in feat.get(iso, {}).values():
            if st.get("dv0944") is not None:
                dv44_hist.setdefault(st["symbol"], []).append((iso, st["dv0944"]))
            if st.get("cumdv") is not None:
                dv_hist.setdefault(st["symbol"], []).append((iso, st["cumdv"]))
    for iso in [_iso(d) for d in all_sess]:
        for st in feat.get(iso, {}).values():
            prior = [v for s, v in (dv44_hist.get(st["symbol"]) or []) if s < iso]
            st["rel0944"] = run_rel_vol(st.get("dv0944"), prior)

    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    part_a_dev = []
    part_a_hol = []
    for d in develop + holdout:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            row = dict(st)
            if iso in develop_set:
                part_a_dev.append(row)
            elif iso in holdout_set:
                part_a_hol.append(row)

    def _sel(rows, lo, hi, cell=True):
        out = []
        for r in rows:
            pc = r.get("prior_close")
            if pc is None or pc < lo - 1e-12 or pc > hi + 1e-12:
                continue
            if cell and not fly_cell_ok(r.get("orw"), r.get("dv0929"), r.get("ext0944")):
                continue
            out.append(r)
        return out

    gate_rows = [
        r
        for r in _sel(part_a_dev, PRICE_FLOOR_PX5, PRICE_HI)
        if r.get("klass") == "FLY"
    ]
    med = _median([r.get("ext1159_44") for r in gate_rows])
    frac = (
        sum(1 for r in gate_rows if r.get("hit_1atr_before_or")) / len(gate_rows)
        if gate_rows
        else 0.0
    )
    gate = cell_buy_gate(median_ext_1159=med, frac_1atr_before_or=frac)
    print(
        f"Part A gate develop FLY $5-20 n={len(gate_rows)} median_ext1159_vs_0944={med} "
        f"frac_1atr_before_or={frac:.3f} GATE={'YES' if gate else 'NO'}",
        flush=True,
    )

    study_isos = {_iso(d) for d in study}
    feats_by_sess = {iso: [] for iso in study_isos}
    for d in study:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            feats_by_sess[iso].append(st)
    replay_jobs = [
        (_iso(d), feats_by_sess.get(_iso(d), []), dv_hist, gate) for d in develop + holdout
    ]
    print(f"Part B replay {len(replay_jobs)} sessions x {len(IDS)} gate={gate}", flush=True)
    prog2 = Progress(len(replay_jobs), "arrow29")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    print("frozen A28 B_uptick10|atr1559 dailies for COMBINED (not a rescore)", flush=True)
    b_daily = _frozen_b_dailies(workers, develop, holdout, all_sess)
    _write_reports(
        part_a_dev,
        part_a_hol,
        gate,
        med,
        frac,
        len(gate_rows),
        chunks,
        b_daily,
        workers,
        cpu,
        develop,
        holdout,
    )
    return 0


def _frozen_b_dailies(workers, develop, holdout, all_sess) -> dict[str, float]:
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    track_b, _capped = _filter_track_b(elig)
    want = set(str(s) for s in track_b["symbol"].unique().to_list())
    sess_order = [d.isoformat() for d in all_sess]
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
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow29_bfrozen")
    prog.start_heartbeat()
    jobs = [(d, want) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_b_prep_one, job): job[0] for job in jobs}
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
    only = (FROZEN_B,)
    replay_jobs = [
        (
            _iso(d),
            by_sess.get(_iso(d), []),
            bars15,
            sess_order,
            lows,
            pc_by,
            dv9.get(_iso(d), {}),
            {},
            only,
        )
        for d in develop + holdout
    ]
    prog2 = Progress(len(replay_jobs), "arrow29_bfrozen_replay")
    prog2.start_heartbeat()
    daily: dict[str, float] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_b, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            pnl = 0.0
            for r in chunk["rows"]:
                if r["name"] == FROZEN_B:
                    pnl = r["pnl"]
            daily[chunk["session"]] = pnl
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    return daily


def _write_reports(
    part_a_dev,
    part_a_hol,
    gate,
    med,
    frac,
    n_gate,
    chunks,
    b_daily,
    workers,
    cpu,
    develop,
    holdout,
) -> None:
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    rows = [r for c in chunks for r in c["rows"]]
    cost_skips = sum(c.get("cost_skips") or 0 for c in chunks)
    results = []
    daily_map: dict[str, dict[str, float]] = {}
    for exp_id in IDS:
        subset = [r for r in rows if r["name"] == exp_id]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in holdout]
        daily_map[exp_id] = {
            **{_iso(d): pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in develop},
            **{_iso(d): pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in holdout},
        }
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        skipped = any(r.get("skipped_gate") for r in subset)
        sm_d = _summarize_adv(daily_dev, tr_dev, len(develop))
        sm_h = _summarize_adv(daily_hol, tr_hol, len(holdout))
        peaks_d = [int(pnl_map.get(_iso(d), {}).get("peak") or 0) for d in develop]
        peaks_h = [int(pnl_map.get(_iso(d), {}).get("peak") or 0) for d in holdout]
        means_d = [float(pnl_map.get(_iso(d), {}).get("mean_conc") or 0.0) for d in develop]
        means_h = [float(pnl_map.get(_iso(d), {}).get("mean_conc") or 0.0) for d in holdout]
        sm_d["peak_conc"] = max(peaks_d) if peaks_d else 0
        sm_h["peak_conc"] = max(peaks_h) if peaks_h else 0
        sm_d["mean_conc"] = (sum(means_d) / len(means_d)) if means_d else 0.0
        sm_h["mean_conc"] = (sum(means_h) / len(means_h)) if means_h else 0.0
        shelve = exp_id.startswith("launch") and sm_d["n_trades"] < 40
        results.append(
            {
                "name": exp_id,
                "develop": sm_d,
                "holdout": sm_h,
                "skipped": skipped,
                "shelve": shelve,
            }
        )

    def _sel(rows, lo, hi):
        return [
            r
            for r in rows
            if r.get("prior_close") is not None
            and lo - 1e-12 <= r["prior_close"] <= hi + 1e-12
            and fly_cell_ok(r.get("orw"), r.get("dv0929"), r.get("ext0944"))
        ]

    live = [r for r in results if not r["skipped"] and not r["shelve"]]
    green = [r for r in live if r["develop"]["per_day"] >= 0]
    best = max(green, key=lambda r: r["develop"]["per_day"]) if green else None
    rocket_daily = daily_map[best["name"]] if best else None
    if rocket_daily is None:
        # fallback: flush|max6 reprint is expensive; COMBINED vs B only if no rocket
        rocket_name = "flush|max6 (no develop-not-red rocket this file; not reprinted)"
        rocket_daily = {d.isoformat(): 0.0 for d in develop + holdout}
        # Use A27/A28 printed flush as zeros would be wrong. Reprint flush.
        from research.arrow28 import _flush_chunks

        print("no develop-not-red rocket; reprint flush|max6 for COMBINED", flush=True)
        elig = pl.read_parquet(FULL_ELIGIBILITY)
        study = study_sessions()
        all_sess = list(WARMUP_SESSIONS) + study
        flush_chunks = _flush_chunks(elig, all_sess, study, develop, holdout, workers)
        fmap = {c["session"]: c.get("pnl", 0.0) for c in flush_chunks}
        rocket_daily = {
            **{_iso(d): fmap.get(_iso(d), 0.0) for d in develop},
            **{_iso(d): fmap.get(_iso(d), 0.0) for d in holdout},
        }
        rocket_name = "flush|max6"
    else:
        rocket_name = best["name"]

    comb_dev = combine_books(
        {_iso(d): b_daily.get(_iso(d), 0.0) for d in develop},
        {_iso(d): rocket_daily.get(_iso(d), 0.0) for d in develop},
    )
    comb_hol = combine_books(
        {_iso(d): b_daily.get(_iso(d), 0.0) for d in holdout},
        {_iso(d): rocket_daily.get(_iso(d), 0.0) for d in holdout},
    )

    def _promo(r) -> bool:
        return (not r["skipped"]) and (not r["shelve"]) and r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0

    promo = [r["name"] for r in results if _promo(r)]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 29 book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not EV."
        )

    fly5 = [r for r in _sel(part_a_dev, PRICE_FLOOR_PX5, PRICE_HI) if r.get("klass") == "FLY"]
    para = (
        f"Forward from 09:44 close (not prior close), develop FLY $5-20 n={len(fly5)}: "
        f"median ext_1159={med}. Gate requires median ext_1159>0 and "
        f"frac reaching +1 ATR before OR-low >=0.35 (got {frac:.3f}). "
        f"GATE={'YES' if gate else 'NO'}."
    )
    if fly5:
        e11 = _median([r.get("ext1159_44") for r in fly5])
        tagged = sum(1 for r in fly5 if r.get("tagged_or_low")) / len(fly5)
        para += (
            f" FLY members still have leftover extension after 09:44 if median ext_1159>0 "
            f"(median={e11}); OR-low stop is tagged by {tagged:.0%} by 11:59."
        )
    else:
        para += " No develop FLY members in $5-20 cell."

    lines = [
        "Arrow 29 — FLY cell as population; new rocket radii (data/full)",
        verdict,
        "No flush|max6 synonyms. No B-short rescore. No $500/idea. No virgin pull. No Arrow 30.",
        "Honesty: combined develop is the combine_books number. Combined holdout is not EV. "
        "Do not write that the account is one improvement from $200. Holdout Part A is PEEK.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  cost_skips={cost_skips}  cell-buy GATE={'YES' if gate else 'NO'}",
        "",
        "PART A — develop-only forward from 09:44 close (holdout PEEK)",
        para,
        f"Gate inputs: develop FLY $5-20 n={n_gate} median_ext1159_vs_0944={med} "
        f"frac_1atr_before_or={frac:.3f} GATE={'YES' if gate else 'NO'}",
        "",
        "develop cell $3-20",
    ]
    lines.extend(_fmt_part_a(_sel(part_a_dev, PRICE_FLOOR, PRICE_HI), "cell $3-20"))
    lines.append("develop cell $5-20")
    lines.extend(_fmt_part_a(_sel(part_a_dev, PRICE_FLOOR_PX5, PRICE_HI), "cell $5-20"))
    lines.append("holdout cell $5-20 PEEK")
    lines.extend(_fmt_part_a(_sel(part_a_hol, PRICE_FLOOR_PX5, PRICE_HI), "cell $5-20 PEEK"))
    if not gate:
        lines.append("Cell-buy ids 1-3 SKIP — gate failed; did not invent a buy.")
    lines.append("")
    lines.append("PART B — longs, harness on, cap8, $200/idea, ranked by run_rel_vol")
    lines.append(
        f"{'id':<24} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'avgR':>7} "
        f"{'PF':>6} {'t_hold':>7} {'peak':>5} {'meanC':>6} {'>=200':>6}"
    )
    for r in results:
        h = r["holdout"]
        if r["skipped"]:
            flag = "SKIP"
        elif r["shelve"]:
            flag = "SHELVE"
        elif _promo(r):
            flag = "BOTH"
        elif h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        elif h["clears_200"]:
            flag = "YES"
        else:
            flag = "NO"
        lines.append(
            f"{r['name']:<24} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['avg_r']:7.3f} {h.get('pf_s') or _pf([]):>6} "
            f"{h['t_stat']:7.2f} {h['peak_conc']:5d} {h['mean_conc']:6.2f} {flag:>6}"
        )
        if r["skipped"]:
            lines.append("  SKIP gate")
            continue
        lines.append("  develop")
        lines.extend(_fmt_adv(r["develop"]))
        lines.append(
            f"    peak_conc={r['develop']['peak_conc']}  mean_conc={r['develop']['mean_conc']:.2f}"
        )
        lines.append("  holdout")
        lines.extend(_fmt_adv(r["holdout"]))
        lines.append(
            f"    peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}"
        )
        if r["shelve"]:
            lines.append("  SHELVE: develop n<40 on id 6 — not closed, not promoted.")
    lines.append("")
    lines.append(
        f"COMBINED {FROZEN_B} + {rocket_name}  (frozen A28 short, not rescored, + best develop-not-red rocket)"
    )
    lines.append(
        f"  develop $/day={comb_dev['per_day']:.2f}  std={comb_dev['std_day']:.2f}  "
        f"se={comb_dev['se_day']:.2f}  t={comb_dev['t_stat']:.2f}  "
        f"ci95=[{comb_dev['ci_lo']:.2f},{comb_dev['ci_hi']:.2f}]  maxDD$={comb_dev['max_dd']:.2f}  "
        f"corr={comb_dev['corr'].get((0, 1), 0.0):.3f}"
    )
    lines.append(
        f"  holdout $/day={comb_hol['per_day']:.2f}  std={comb_hol['std_day']:.2f}  "
        f"se={comb_hol['se_day']:.2f}  t={comb_hol['t_stat']:.2f}  "
        f"ci95=[{comb_hol['ci_lo']:.2f},{comb_hol['ci_hi']:.2f}]  maxDD$={comb_hol['max_dd']:.2f}  "
        f"corr={comb_hol['corr'].get((0, 1), 0.0):.3f}  NOT EV"
    )
    lines.append("NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow29_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 29",
        "",
        verdict,
        "",
        "FLY cell as population; new rocket radii. No flush|max6 synonyms. No B-short rescore. "
        "No $500/idea. No virgin pull. Combined holdout is not EV. No Arrow 30.",
        para,
        f"GATE={'YES' if gate else 'NO'}.",
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} t={r['holdout']['t_stat']:.2f} "
            f"peak_conc={r['holdout']['peak_conc']} skipped={r['skipped']} shelve={r['shelve']}."
        )
    bits.append(
        f"- COMBINED {FROZEN_B}+{rocket_name}: develop ${comb_dev['per_day']:.2f}/day "
        f"holdout ${comb_hol['per_day']:.2f}/day (holdout not EV)."
    )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
