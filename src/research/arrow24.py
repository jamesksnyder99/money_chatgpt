from __future__ import annotations

import math
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow19 import CLOCK_0800, CLOCK_0929, CLOCK_1559, _last_at_or_before, _pack
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _fmt_adv, _pack_trades, _summarize_adv
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.harness import (
    PRICE_FLOOR,
    classify_fly_fail,
    confirmed_launch,
    cum_dv_array,
    run_rel_vol,
)
from research.signals import MINUTE_0944, MINUTE_1159, MINUTE_1559, RTH_OPEN, bar_time
from research.split import develop_holdout
from research.strategies22 import hot_gate_0800
from research.strategies24 import (
    DOORS,
    EXITS,
    FILTERS,
    GRID_IDS,
    am_high_pm_long,
    door_side,
    exit_kwargs,
    filter_kwargs,
    flush_long,
    giveback_short,
    launch_long,
    volfirst_long,
)

ET = ZoneInfo("America/New_York")
CLOCK_0944 = time(9, 44)
CONTROLS = ("flush_hl|harness", "am_high_pm|harness")
CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
}


def _range_mid(hi, lo):
    if hi is None or lo is None:
        return None
    mid = (float(hi) + float(lo)) / 2.0
    if mid <= 0:
        return None
    return (float(hi) - float(lo)) / mid


def _scan_one(df: pl.DataFrame, pc: float) -> dict | None:
    pack = _pack(df)
    if pack is None or pc is None or pc <= 0:
        return None
    conf = confirmed_launch(pack, pc)
    thresh = 1.10 * pc
    tagged = False
    launch_high_ts = None
    session_high = None
    peak_ts = None
    for ts, h in zip(pack["ts"], pack["high"]):
        session_high = h if session_high is None else max(session_high, h)
        if not tagged and h >= thresh - 1e-12:
            tagged = True
            launch_high_ts = ts
    if session_high is not None:
        for ts, h in zip(pack["ts"], pack["high"]):
            if h >= session_high - 1e-12:
                peak_ts = ts
                break
    max_ext = (session_high / pc - 1.0) if session_high else None
    i8, dv8 = _last_at_or_before(pack, CLOCK_0800)
    i9, dv9 = _last_at_or_before(pack, CLOCK_0929)
    i44, dv44 = _last_at_or_before(pack, CLOCK_0944)
    i1559, _ = _last_at_or_before(pack, CLOCK_1559)
    open930 = None
    or_h = or_l = None
    pre_h = pre_l = None
    for ts, o, h, l in zip(pack["ts"], pack["open"], pack["high"], pack["low"]):
        t = bar_time(ts)
        if t <= CLOCK_0929:
            pre_h = h if pre_h is None else max(pre_h, h)
            pre_l = l if pre_l is None else min(pre_l, l)
        if t >= RTH_OPEN and open930 is None:
            open930 = o
        if RTH_OPEN <= t <= MINUTE_0944:
            or_h = h if or_h is None else max(or_h, h)
            or_l = l if or_l is None else min(or_l, l)
    ext1559 = pack["close"][i1559] / pc - 1.0 if i1559 is not None else None
    still = ext1559 is not None and ext1559 >= 0.10 - 1e-12
    gave = ext1559 is not None and max_ext is not None and ext1559 < 0.5 * max_ext - 1e-12
    origin = conf["launch_close_ts"] if conf["confirmed"] else launch_high_ts
    minutes = None
    if origin is not None and peak_ts is not None:
        minutes = max(0.0, (peak_ts - origin).total_seconds() / 60.0)
    klass = classify_fly_fail(
        confirmed=bool(conf["confirmed"]),
        tagged_10=tagged,
        max_ext=max_ext,
        still_10_1559=still,
        minutes_to_peak=minutes,
        gave_back=gave,
    )
    cumdv = cum_dv_array(pack)
    px9 = pack["close"][i9] if i9 is not None else None
    px44 = pack["close"][i44] if i44 is not None else None
    px8 = pack["close"][i8] if i8 is not None else None
    return {
        "confirmed": bool(conf["confirmed"]),
        "confirm_ts": conf["confirm_ts"],
        "tagged10": tagged,
        "max_ext": max_ext,
        "minutes_to_peak": minutes,
        "ext_1559": ext1559,
        "still_10_1559": still,
        "gave_back": gave,
        "klass": klass,
        "launch_hour": bar_time(origin).hour if origin is not None else None,
        "dv0800": dv8 if i8 is not None else None,
        "px0800": px8,
        "dv0929": dv9 if i9 is not None else None,
        "px0929": px9,
        "ext0929": (px9 / pc - 1.0) if px9 else None,
        "dv0944": dv44 if i44 is not None else None,
        "px0944": px44,
        "ext0944": (px44 / pc - 1.0) if px44 else None,
        "pre_high": pre_h,
        "pre_low": pre_l,
        "rng": _range_mid(pre_h, pre_l),
        "gap0929": (px9 / pc - 1.0) if px9 else None,
        "gap0944": (open930 / pc - 1.0) if open930 else None,
        "orw": _range_mid(or_h, or_l),
        "cumdv": cumdv,
        "today_dv": cumdv[-1] if cumdv else 0.0,
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
        if want is not None and sym not in want:
            continue
        meta = want.get(sym) if want is not None else None
        if not meta:
            continue
        st = _scan_one(df, meta["prior_close"])
        if st is None:
            continue
        st["symbol"] = sym
        st["prior_close"] = meta["prior_close"]
        st["prior_dv"] = meta["prior_dv"]
        out[sym] = st
    return iso, out


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = (p / 100.0) * (len(ys) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    w = pos - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def _feat_table(rows: list[dict], keys: list[str], label: str) -> list[str]:
    lines = [f"  {label} n={len(rows)}"]
    hdr = f"    {'feat':<10} {'mean':>10} {'q20':>10} {'q40':>10} {'q60':>10} {'q80':>10}"
    lines.append(hdr)
    for k in keys:
        xs = [float(r[k]) for r in rows if r.get(k) is not None]
        if not xs:
            lines.append(f"    {k:<10} {'n/a':>10}")
            continue
        lines.append(
            f"    {k:<10} {sum(xs)/len(xs):10.4f} {_pct(xs,20):10.4f} {_pct(xs,40):10.4f} "
            f"{_pct(xs,60):10.4f} {_pct(xs,80):10.4f}"
        )
    return lines


def _choose_cell(fly: list[dict], fail: list[dict]) -> dict | None:
    keys = ["ext0929", "rel0929", "dv0929", "rng", "gap0929", "orw", "rel0944", "ext0944"]
    scored = []
    for k in keys:
        xf = [float(r[k]) for r in fly if r.get(k) is not None]
        xg = [float(r[k]) for r in fail if r.get(k) is not None]
        if len(xf) < 15 or len(xg) < 15:
            continue
        pooled = xf + xg
        sd = statistics.pstdev(pooled) if len(pooled) > 1 else 0.0
        gap = abs(sum(xf) / len(xf) - sum(xg) / len(xg)) / (sd + 1e-9)
        scored.append((gap, k, statistics.median(pooled)))
    scored.sort(reverse=True)
    top = scored[:3]
    if len(top) < 3:
        return None
    feats = [(k, med) for _g, k, med in top]
    best = None
    both = fly + fail
    base = len(fly) / len(both) if both else 0.0
    # 8 octants
    for mask in range(8):
        rules = []
        n_f = n_g = 0
        for i, (k, med) in enumerate(feats):
            ge = bool(mask & (1 << i))
            rules.append((k, ">=" if ge else "<", med))
        for r in both:
            ok = True
            for k, op, med in rules:
                v = r.get(k)
                if v is None:
                    ok = False
                    break
                if op == ">=" and float(v) < med:
                    ok = False
                    break
                if op == "<" and float(v) >= med:
                    ok = False
                    break
            if not ok:
                continue
            if r["klass"] == "FLY":
                n_f += 1
            else:
                n_g += 1
        n = n_f + n_g
        rate = n_f / n if n else 0.0
        if best is None or (n >= 20 and rate > best["fly_rate"]) or (
            n >= 20 and rate == best["fly_rate"] and n > best["n"]
        ):
            if n >= 20:
                best = {"rules": rules, "n": n, "n_fly": n_f, "fly_rate": rate, "gaps": top}
    if best is None:
        return None
    if best["fly_rate"] < max(0.40, 1.4 * base) or best["n"] < 25:
        return None
    best["base"] = base
    best["stamp"] = "0929/0944"
    return best


def _in_cell(h: dict, cell: dict | None) -> bool:
    if cell is None:
        return True
    for k, op, med in cell["rules"]:
        v = h.get(k)
        if v is None:
            return False
        if op == ">=" and float(v) < med:
            return False
        if op == "<" and float(v) >= med:
            return False
    return True


def _hour_hist(rows: list[dict]) -> str:
    buckets = {h: 0 for h in range(4, 16)}
    for r in rows:
        hr = r.get("launch_hour")
        if hr is not None and hr in buckets:
            buckets[hr] += 1
    return " ".join(f"{h}={buckets[h]}" for h in range(4, 16))


def _replay_one(args: tuple) -> dict:
    iso, names, prior_dv, dv_hist, cell = args
    session = date.fromisoformat(iso)
    empty_ids = list(GRID_IDS) + list(CONTROLS)
    empty_rows = [
        {"session": iso, "name": n, "pnl": 0.0, "trades": [], "side": -1 if n.startswith("giveback") else 1}
        for n in empty_ids
    ]
    if not names:
        return {"session": iso, "n_cand": 0, "rows": empty_rows, "cost_skips": 0}
    symbols = [h["symbol"] for h in names]
    bars = _read_hot_bars(session, symbols)
    pc_map = {h["symbol"]: h["prior_close"] for h in names}
    doors = {d: [] for d in DOORS}
    ctrl_flush = []
    ctrl_am = []
    cost_skips = 0
    for h in names:
        sdf = bars.get(h["symbol"])
        if sdf is None or sdf.height == 0:
            continue
        pack = _pack(sdf)
        if pack is None:
            continue
        prior_cum = [arr for s, arr in (dv_hist.get(h["symbol"]) or []) if s < iso][-10:]
        pc = h["prior_close"]
        score = float(h.get("rel0929") or h.get("rel0800") or 1.0)
        long_ok = _in_cell(h, cell)
        if pc >= PRICE_FLOOR - 1e-12:
            if long_ok:
                doors["launch"].extend(
                    launch_long(
                        sdf, pack, pc, h.get("ext0929"), h["cumdv"], prior_cum, score_rel=score
                    )
                )
                doors["volfirst"].extend(volfirst_long(sdf, pc, h["cumdv"], prior_cum))
                if h.get("hot0800"):
                    doors["flush"].extend(flush_long(sdf, h.get("px0800"), score))
                    ctrl_flush.extend(flush_long(sdf, h.get("px0800"), score))
                    ctrl_am.extend(am_high_pm_long(sdf, score))
            doors["giveback"].extend(giveback_short(sdf, pack, pc, score))
    rows = []
    for door in DOORS:
        raw = [s for s in doors[door] if s.side == door_side(door)]
        n_raw = len(raw)
        for exit_id in EXITS:
            for filt in FILTERS:
                exp_id = f"{door}|{exit_id}|{filt}"
                fkw = filter_kwargs(filt, n_raw)
                if fkw is None:
                    rows.append(
                        {
                            "session": iso,
                            "name": exp_id,
                            "pnl": 0.0,
                            "trades": [],
                            "side": door_side(door),
                        }
                    )
                    continue
                sigs = raw
                if filt == "px5":
                    sigs = [s for s in raw if pc_map.get(s.symbol, 0.0) >= 5.0 - 1e-12]
                need = {s.symbol for s in sigs}
                sub = {k: bars[k] for k in need if k in bars}
                st = {}
                trades = replay_session(
                    sub,
                    sigs,
                    prior_dv,
                    prior_close=pc_map,
                    borrow_filter=door == "giveback",
                    stats=st,
                    **exit_kwargs(exit_id),
                    **fkw,
                )
                cost_skips += int(st.get("cost_skips") or 0)
                packed = _pack_trades(trades, bars)
                rows.append(
                    {
                        "session": iso,
                        "name": exp_id,
                        "pnl": sum(t.pnl for t in trades),
                        "trades": packed,
                        "side": door_side(door),
                    }
                )
    for exp_id, sigs, flatten in (
        ("flush_hl|harness", ctrl_flush, MINUTE_1159),
        ("am_high_pm|harness", ctrl_am, MINUTE_1559),
    ):
        need = {s.symbol for s in sigs}
        sub = {k: bars[k] for k in need if k in bars}
        st = {}
        trades = replay_session(
            sub,
            sigs,
            prior_dv,
            flatten_at=flatten,
            harness_stop=True,
            cost_gate=True,
            stats=st,
            **CAP8,
        )
        cost_skips += int(st.get("cost_skips") or 0)
        packed = _pack_trades(trades, bars)
        rows.append(
            {
                "session": iso,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": packed,
                "side": 1,
            }
        )
    return {"session": iso, "n_cand": len(names), "rows": rows, "cost_skips": cost_skips}


def run_arrow24(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow24 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "FLY vs FAIL, harness, 100-book grid; data/full only; holdout is not a tuner. "
        "Did not rerun 08:00/09:29 buy-the-extended-open, A21 pullback, strong5, newhigh, "
        "fade, vs_iwm, climax. No Arrow 25.",
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

    print(f"pass 1: FLY/FAIL + stamps warmup+study n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow24_pre")
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

    dv_hist: dict[str, list[tuple[str, list[float]]]] = {}
    dv9_hist: dict[str, list[tuple[str, float]]] = {}
    dv8_hist: dict[str, list[tuple[str, float]]] = {}
    dv44_hist: dict[str, list[tuple[str, float]]] = {}
    full_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for sym, st in feat.get(iso, {}).items():
            dv_hist.setdefault(sym, []).append((iso, st["cumdv"]))
            if st.get("dv0929") is not None:
                dv9_hist.setdefault(sym, []).append((iso, st["dv0929"]))
            if st.get("dv0800") is not None:
                dv8_hist.setdefault(sym, []).append((iso, st["dv0800"]))
            if st.get("dv0944") is not None:
                dv44_hist.setdefault(sym, []).append((iso, st["dv0944"]))
            full_hist.setdefault(sym, []).append((iso, st["today_dv"]))

    study_isos = {_iso(d) for d in study}
    for iso in [_iso(d) for d in all_sess]:
        for sym, st in feat.get(iso, {}).items():
            prior9 = [v for s, v in (dv9_hist.get(sym) or []) if s < iso]
            prior8 = [v for s, v in (dv8_hist.get(sym) or []) if s < iso]
            prior44 = [v for s, v in (dv44_hist.get(sym) or []) if s < iso]
            priorf = [v for s, v in (full_hist.get(sym) or []) if s < iso]
            st["rel0929"] = run_rel_vol(st.get("dv0929"), prior9)
            st["rel0800"] = run_rel_vol(st.get("dv0800"), prior8)
            st["rel0944"] = run_rel_vol(st.get("dv0944"), prior44)
            st["rel_full"] = run_rel_vol(st.get("today_dv"), priorf)
            st["hot0800"] = hot_gate_0800(
                pre_dv=st.get("dv0800"),
                pre_dv_rel=st.get("rel0800"),
                ext_0800=(st["px0800"] / st["prior_close"] - 1.0) if st.get("px0800") else None,
            )
    for iso in [_iso(d) for d in all_sess]:
        for sym, st in feat.get(iso, {}).items():
            prev = None
            for s, _arr in dv_hist.get(sym) or []:
                if s < iso:
                    prev = s
            if prev and prev in feat and sym in feat[prev]:
                p = feat[prev][sym]
                st["was_rocket_prev"] = 1.0 if (
                    p.get("confirmed") and (p.get("rel_full") or 0) >= 3.0 - 1e-12
                ) else 0.0
                st["prev_close_ext"] = p.get("ext_1559")
                st["prev_gave_back"] = 1.0 if p.get("gave_back") else 0.0
            else:
                st["was_rocket_prev"] = None
                st["prev_close_ext"] = None
                st["prev_gave_back"] = None

    develop_set = {_iso(d) for d in develop}
    char_rows = []
    for d in develop:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            if st.get("rel_full") is None:
                continue
            char_rows.append(st)
    fly = [r for r in char_rows if r["klass"] == "FLY"]
    fail = [r for r in char_rows if r["klass"] == "FAIL"]
    other = [r for r in char_rows if r["klass"] == "other"]
    cell = _choose_cell(fly, fail)
    print(
        f"Part A develop FLY={len(fly)} FAIL={len(fail)} other={len(other)} "
        f"cell={'none' if cell is None else cell['rules']}",
        flush=True,
    )

    def _strategy_candidate(st: dict) -> bool:
        if st["prior_close"] < PRICE_FLOOR - 1e-12:
            return False
        if st.get("rel_full") is None:
            return False
        if st.get("hot0800"):
            return True
        if st.get("confirmed") or st.get("tagged10"):
            return True
        mx = st.get("max_ext")
        if mx is not None and mx >= 0.15 - 1e-12:
            return True
        if (st.get("rel0929") or 0.0) >= 3.0 - 1e-12:
            return True
        ext = st.get("ext0929")
        if ext is not None and -0.05 - 1e-12 <= float(ext) <= 0.08 + 1e-12:
            return True
        return False

    feats_by_sess: dict[str, list[dict]] = {iso: [] for iso in study_isos}
    prior_dv_by_sess: dict[str, dict[str, float]] = {iso: {} for iso in study_isos}
    for d in study:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            if not _strategy_candidate(st):
                continue
            feats_by_sess[iso].append(st)
            prior_dv_by_sess[iso][st["symbol"]] = st["prior_dv"]

    replay_jobs = [
        (_iso(d), feats_by_sess[_iso(d)], prior_dv_by_sess[_iso(d)], dv_hist, cell)
        for d in develop + holdout
    ]
    print(f"pass 2: replay {len(replay_jobs)} sessions x {len(GRID_IDS)}+2 ids", flush=True)
    prog2 = Progress(len(replay_jobs), "arrow24")
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
    _write_reports(
        chunks, fly, fail, other, cell, char_rows, workers, cpu, develop, holdout
    )
    return 0


def _write_reports(
    chunks, fly, fail, other, cell, char_rows, workers, cpu, develop, holdout
) -> None:
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    rows = [r for c in chunks for r in c["rows"]]
    cost_skips = sum(c.get("cost_skips") or 0 for c in chunks)

    def _score(exp_id: str) -> dict:
        subset = [r for r in rows if r["name"] == exp_id]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in holdout]
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        return {
            "name": exp_id,
            "side": subset[0]["side"] if subset else 1,
            "develop": _summarize_adv(daily_dev, tr_dev, len(develop)),
            "holdout": _summarize_adv(daily_hol, tr_hol, len(holdout)),
        }

    controls = [_score(n) for n in CONTROLS]
    grid = [_score(n) for n in GRID_IDS]
    grid.sort(key=lambda r: r["holdout"]["per_day"], reverse=True)

    both_green = [
        r for r in grid if r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0
    ]
    flush_ctrl = next(r for r in controls if r["name"].startswith("flush"))
    flush_beat = [
        r
        for r in grid
        if r["name"].startswith("flush|")
        and r["develop"]["per_day"] > flush_ctrl["develop"]["per_day"]
    ]

    promo = both_green
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(
            r["name"] for r in promo[:8]
        )
        if len(promo) > 8:
            verdict += f" (+{len(promo)-8} more)"
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 24 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass. Holdout is not a tuner. "
            "Did not rerun 08:00/09:29 buy-the-extended-open, A21 pullback, strong5, newhigh, "
            "fade, vs_iwm, climax."
        )

    keys_snap = ["ext0929", "rel0929", "dv0929", "rng", "gap0929", "px0929", "was_rocket_prev"]
    keys_944 = ["ext0944", "rel0944", "dv0944", "orw", "gap0944", "px0944"]
    lines = [
        "Arrow 24 — FLY vs FAIL, harness, 100-book grid (data/full)",
        verdict,
        "Holdout is not a tuner. Did not rerun 08:00/09:29 buy-the-extended-open, A21 pullback, "
        "strong5, newhigh, fade-the-hot-open, vs_iwm, climax. No B-short rescore. "
        "Did not touch data/bars. No Arrow 25.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        f"grid ids={len(GRID_IDS)}  cost_skips={cost_skips}  price_floor={PRICE_FLOOR}",
        "",
        "PART A — FLY vs FAIL (develop only; holdout is PEEK and was not used to pick the cell)",
        f"confirmed launch: first 1-min close >= 1.10*pc whose next tradeable low >= 1.08*pc",
        f"n FLY={len(fly)}  n FAIL={len(fail)}  n other={len(other)}  n scored={len(char_rows)}",
        f"launch hour FLY:  {_hour_hist(fly)}",
        f"launch hour FAIL: {_hour_hist(fail)}",
        "",
        "09:29 features FLY vs FAIL",
    ]
    lines.extend(_feat_table(fly, keys_snap, "FLY 09:29"))
    lines.extend(_feat_table(fail, keys_snap, "FAIL 09:29"))
    lines.append("09:44 features FLY vs FAIL")
    lines.extend(_feat_table(fly, keys_944, "FLY 09:44"))
    lines.extend(_feat_table(fail, keys_944, "FAIL 09:44"))
    lines.append("")
    if cell is None:
        cell_para = (
            "Cell: none. No 2x2x2 octant on the three largest FLY/FAIL-gap features cleared "
            "n>=25 and FLY rate >= max(40%, 1.4x baseline) on develop. Long doors use their "
            "own gates only."
        )
    else:
        bits = ", ".join(f"{k} {op} {med:.4f}" for k, op, med in cell["rules"])
        cell_para = (
            f"Cell (develop-locked, holdout PEEK): {bits}. n={cell['n']} FLY={cell['n_fly']} "
            f"rate={cell['fly_rate']:.3f} vs baseline {cell['base']:.3f}. Applied as an extra "
            f"population cut on every long door."
        )
        lines.append("2x2x2 winning octant (develop): " + bits)
        lines.append(
            f"  n={cell['n']} n_fly={cell['n_fly']} fly_rate={cell['fly_rate']:.3f} "
            f"base={cell['base']:.3f} gaps={[round(g,3) for g,_,_ in cell['gaps']]}"
        )
    lines.append(cell_para)
    lines.append("")
    lines.append("PART B — harness controls (same A23 entries, new stops/gates)")
    for r in controls:
        flag = "YES" if r["holdout"]["clears_200"] else "NO"
        if r["holdout"]["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(f"{r['name']}  holdout>=200={flag}")
        lines.append("  develop")
        lines.extend(_fmt_adv(r["develop"]))
        lines.append("  holdout")
        lines.extend(_fmt_adv(r["holdout"]))
    lines.append("")
    lines.append("PART C — 100-book grid sorted by holdout $/day (holdout is not a tuner)")
    lines.append(
        f"{'id':<28} {'side':>4} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} "
        f"{'hit':>6} {'avgR':>7} {'PF':>6} {'t_hold':>7} {'1R':>6} {'>=200':>6}"
    )
    for r in grid:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0:
            flag = "BOTH"
        side = "S" if r["side"] < 0 else "L"
        lines.append(
            f"{r['name']:<28} {side:>4} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} {h['pf_s']:>6} "
            f"{h['t_stat']:7.2f} {h['frac_1r']:6.3f} {flag:>6}"
        )
    lines.append("")
    lines.append(
        f"both-green (holdout>=200 and develop not red): {len(both_green)} / {len(grid)}"
    )
    lines.append(
        f"flush family beating flush_hl|harness on develop: {len(flush_beat)} / 25"
    )
    if both_green:
        lines.append("both-green ids: " + ", ".join(r["name"] for r in both_green))
    lines.append("")
    door_notes = []
    for door in DOORS:
        subset = [r for r in grid if r["name"].startswith(door + "|")]
        if not subset:
            continue
        best = max(subset, key=lambda r: r["holdout"]["per_day"])
        hits = statistics.mean(r["holdout"]["hit_rate"] for r in subset)
        door_notes.append(
            f"{door} best hold {best['name']} {best['holdout']['per_day']:.0f}/day "
            f"hit~{hits:.2f} PF {best['holdout']['pf_s']}"
        )
    shape = (
        "FLY vs FAIL "
        + ("named a cell. " + cell_para + " " if cell else "named no cell. ")
        + "Door families vs Arrows 20-22 (those were ~30% hit chasing an already-extended open): "
        + "; ".join(door_notes)
        + f". both-green={len(both_green)} of 100. Holdout was not used to pick doors, exits, or the cell."
    )
    lines.append(shape)
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow24_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 24",
        "",
        verdict,
        "",
        f"Part A develop FLY={len(fly)} FAIL={len(fail)} other={len(other)}. {cell_para}",
        f"100-grid both-green={len(both_green)}. flush-family beat harness control on develop: "
        f"{len(flush_beat)}/25. cost_skips={cost_skips}.",
        "",
    ]
    for r in controls:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} hit={r['holdout']['hit_rate']:.3f} "
            f"PF={r['holdout']['pf_s']} t={r['holdout']['t_stat']:.2f}."
        )
    bits.append("")
    bits.append("Top 5 grid by holdout $/day:")
    for r in grid[:5]:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} hit={r['holdout']['hit_rate']:.3f}."
        )
    bits.append("")
    bits.append(shape)
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
