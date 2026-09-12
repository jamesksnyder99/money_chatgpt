from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow19 import _pack
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _flight
from research.arrow24 import _scan_one
from research.book import replay_session
from research.harness import PRICE_FLOOR_PX5, run_rel_vol
from research.rockets import MIN_PRIORS, median_prior_window
from research.signals import MINUTE_1159
from research.split import develop_holdout
from research.strategies22 import hot_gate_0800
from research.strategies25 import fly_cell_ok, flush_ring_long, score_flush
from research.strategies26 import MAX_UNDERCUT
from research.strategies30 import gross_altitude, r1_haircut

ET = ZoneInfo("America/New_York")

FLUSH_CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
    "harness_stop": True,
    "cost_gate": True,
    "flatten_at": MINUTE_1159,
}
NEVER_SIT = frozenset({4, 5, 6, 7, 12, 13, 14, 15})


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


def _max_high_after(pack: dict, launch_ts) -> float | None:
    mh = None
    for ts, h in zip(pack["ts"], pack["high"]):
        if launch_ts is not None and ts < launch_ts:
            continue
        mh = float(h) if mh is None else max(mh, float(h))
    return mh


def _scan_alt(df: pl.DataFrame, pc: float) -> dict | None:
    st = _scan_one(df, pc)
    if st is None:
        return None
    pack = _pack(df)
    today_vol = float(sum(pack["vol"])) if pack else 0.0
    st["today_vol"] = today_vol
    st["confirmed"] = bool(st.get("confirmed"))
    st["altitude"] = 0.0
    st["r1"] = None
    st["launch_hour"] = st.get("launch_hour")
    if pack is None or not st["confirmed"] or st.get("confirm_ts") is None:
        return st
    launch_ts = st["confirm_ts"]
    mh = _max_high_after(pack, launch_ts)
    r1 = r1_haircut(df, launch_ts, pc)
    st["r1"] = r1
    st["altitude"] = gross_altitude(mh, pc, r1)
    st["launch_hour"] = launch_ts.timetz().replace(tzinfo=None).hour if launch_ts is not None else None
    return st


def _session_alt(args: tuple) -> tuple[str, dict[str, dict]]:
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
        st = _scan_alt(df, meta["prior_close"])
        if st is None:
            continue
        st["symbol"] = sym
        st["prior_close"] = meta["prior_close"]
        st["prior_dv"] = meta["prior_dv"]
        out[sym] = st
    return iso, out


def _replay_flush(args: tuple) -> dict:
    iso, names, prior_dv = args
    session = date.fromisoformat(iso)
    empty = {"session": iso, "trades": []}
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
        for s in flush_ring_long(sdf, h.get("px0800"), tag="flush|max6", max_undercut=MAX_UNDERCUT):
            if s.side != 1:
                continue
            sigs.append(score_flush(s, score))
    need = {s.symbol for s in sigs}
    sub = {k: bars[k] for k in need if k in bars}
    trades = replay_session(sub, sigs, prior_dv, **FLUSH_CAP8)
    out = []
    for t in trades:
        mfe_ext, _reached = _flight(bars.get(t.symbol), t)
        stop_dist = t.risk / t.shares if t.shares else 0.0
        fav = mfe_ext * t.entry_px if t.entry_px else 0.0
        mfe_r = (fav / stop_dist) if stop_dist > 0 else 0.0
        out.append(
            {
                "session": iso,
                "symbol": t.symbol,
                "mfe_ext": max(0.0, float(mfe_ext)),
                "mfe_r": max(0.0, float(mfe_r)),
            }
        )
    return {"session": iso, "trades": out}


def _slice_rows(rows: list[dict], isos: set[str]) -> list[dict]:
    return [r for r in rows if r["session"] in isos]


def _field_block(rows: list[dict], flush: list[dict], label: str) -> list[str]:
    n = len(rows)
    alts = [float(r["altitude"]) for r in rows]
    s_alt = sum(alts)
    med = statistics.median(alts) if alts else 0.0
    p90 = _pct(alts, 90)
    rocket_keys = {(r["session"], r["symbol"]) for r in rows}
    flush_on = [t for t in flush if (t["session"], t["symbol"]) in rocket_keys]
    flush_keys = {(t["session"], t["symbol"]) for t in flush_on}
    n_cov = len(flush_keys)
    cov = n_cov / n if n else 0.0
    s_mfe = sum(float(t["mfe_ext"]) for t in flush)
    s_mfe_r_usd = sum(200.0 * float(t["mfe_r"]) for t in flush)
    s_mfe_on = sum(float(t["mfe_ext"]) for t in flush_on)
    by_hour = {h: 0.0 for h in range(4, 16)}
    n_hour = {h: 0 for h in range(4, 16)}
    for r in rows:
        h = r.get("launch_hour")
        if h is None or h not in by_hour:
            continue
        by_hour[int(h)] += float(r["altitude"])
        n_hour[int(h)] += 1
    never = sum(by_hour[h] for h in NEVER_SIT)
    never_share = never / s_alt if s_alt else 0.0
    fly = [r for r in rows if r.get("klass") == "FLY"]
    fail = [r for r in rows if r.get("klass") == "FAIL"]
    lines = [
        f"{label}",
        f"  confirmed-launch rocket-days n={n}",
        f"  sum altitude={s_alt * 100:.2f} pct-points  median={med * 100:.3f}pp  p90={p90 * 100:.3f}pp",
        f"  flush|max6 trades n={len(flush)}  unique name-days={len({(t['session'], t['symbol']) for t in flush})}",
        f"  view1 name-day coverage: {n_cov}/{n} = {100 * cov:.2f}% of rocket-days",
        f"  view2 extension points: field {s_alt * 100:.2f}pp vs flush MFE-from-entry {s_mfe * 100:.2f}pp "
        f"(on rocket-days {s_mfe_on * 100:.2f}pp)",
        f"  flush captured MFE_R dollars (n * $200 * MFE_R) sum=${s_mfe_r_usd:.2f}  (not the same unit as pct-points)",
        f"  altitude share in hours we never sit (04-07 and after 12:00): {100 * never_share:.1f}% "
        f"({never * 100:.2f}pp of {s_alt * 100:.2f}pp)",
        "  altitude by launch hour:",
    ]
    for h in range(4, 16):
        lines.append(
            f"    {h:02d}: n={n_hour[h]}  alt={by_hour[h] * 100:.2f}pp"
        )
    if fly or fail:
        fa = sum(float(r["altitude"]) for r in fly)
        ga = sum(float(r["altitude"]) for r in fail)
        lines.append(
            f"  FLY n={len(fly)} alt={fa * 100:.2f}pp  FAIL n={len(fail)} alt={ga * 100:.2f}pp  "
            f"other n={n - len(fly) - len(fail)}"
        )
    return lines


def run_arrow30(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow30 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "diagnostic rocket altitude vs flush|max6. No new engine. No cell-buy. "
        "No B-short rescore. No $500/idea. No virgin pull. No $200 verdict. No Arrow 31.",
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

    print(f"scan confirmed-launch + survey rockets n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow30_scan")
    prog.start_heartbeat()
    jobs = [(d, by_sess.get(_iso(d), {})) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_alt, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    vol_hist: dict[str, list[tuple[str, float]]] = {}
    dv8_hist: dict[str, list[tuple[str, float]]] = {}
    dv9_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for st in feat.get(iso, {}).values():
            vol_hist.setdefault(st["symbol"], []).append((iso, float(st.get("today_vol") or 0.0)))
            if st.get("dv0800") is not None:
                dv8_hist.setdefault(st["symbol"], []).append((iso, st["dv0800"]))
            if st.get("dv0929") is not None:
                dv9_hist.setdefault(st["symbol"], []).append((iso, st["dv0929"]))
    for iso in [_iso(d) for d in all_sess]:
        for st in feat.get(iso, {}).values():
            prior_v = [v for s, v in (vol_hist.get(st["symbol"]) or []) if s < iso]
            st["n_prior"] = len(prior_v)
            st["rel_vol"] = None
            med = median_prior_window(prior_v)
            if med:
                st["rel_vol"] = float(st.get("today_vol") or 0.0) / med
            prior8 = [v for s, v in (dv8_hist.get(st["symbol"]) or []) if s < iso]
            prior9 = [v for s, v in (dv9_hist.get(st["symbol"]) or []) if s < iso]
            st["rel0800"] = run_rel_vol(st.get("dv0800"), prior8)
            st["rel0929"] = run_rel_vol(st.get("dv0929"), prior9)
            ext8 = (st["px0800"] / st["prior_close"] - 1.0) if st.get("px0800") else None
            st["hot0800"] = hot_gate_0800(
                pre_dv=st.get("dv0800"), pre_dv_rel=st.get("rel0800"), ext_0800=ext8
            )

    study_isos = {_iso(d) for d in study}
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}

    rockets: list[dict] = []
    survey: list[dict] = []
    flush_names: dict[str, list[dict]] = {iso: [] for iso in study_isos}
    prior_dv_by: dict[str, dict[str, float]] = {iso: {} for iso in study_isos}
    for d in all_sess:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            row = {
                "session": iso,
                "symbol": st["symbol"],
                "altitude": float(st.get("altitude") or 0.0),
                "launch_hour": st.get("launch_hour"),
                "klass": st.get("klass"),
                "confirmed": bool(st.get("confirmed")),
                "n_prior": int(st.get("n_prior") or 0),
                "rel_vol": st.get("rel_vol"),
                "tagged10": bool(st.get("tagged10")),
                "max_ext": st.get("max_ext"),
            }
            if iso in study_isos and st["n_prior"] >= MIN_PRIORS and st["confirmed"]:
                rockets.append(row)
            if (
                iso in study_isos
                and st["n_prior"] >= MIN_PRIORS
                and st.get("max_ext") is not None
                and float(st["max_ext"]) >= 0.10 - 1e-12
                and st.get("rel_vol") is not None
                and float(st["rel_vol"]) >= 3.0 - 1e-12
            ):
                survey.append(row)
            if iso not in study_isos:
                continue
            if st["prior_close"] < PRICE_FLOOR_PX5 - 1e-12:
                continue
            if not st.get("hot0800") or st.get("rel0800") is None:
                continue
            flush_names[iso].append(st)
            prior_dv_by[iso][st["symbol"]] = st["prior_dv"]

    print(
        f"confirmed-launch rocket-days study={len(rockets)}  "
        f"survey high∩rel>=3x={len(survey)}",
        flush=True,
    )
    flush_jobs = [
        (_iso(d), flush_names.get(_iso(d), []), prior_dv_by.get(_iso(d), {}))
        for d in develop + holdout
    ]
    print(f"replay flush|max6 {len(flush_jobs)} sessions", flush=True)
    prog2 = Progress(len(flush_jobs), "arrow30_flush")
    prog2.start_heartbeat()
    flush_trades: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_flush, job) for job in flush_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            flush_trades.extend(chunk["trades"])
            prog2.mark(chunk["session"], rows=len(chunk["trades"]))
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    _write_report(rockets, survey, flush_trades, workers, cpu, develop, holdout, study)
    return 0


def _write_report(rockets, survey, flush, workers, cpu, develop, holdout, study) -> None:
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    study_set = {_iso(d) for d in study}
    r_dev = _slice_rows(rockets, develop_set)
    r_hol = _slice_rows(rockets, holdout_set)
    r_stu = _slice_rows(rockets, study_set)
    f_dev = _slice_rows(flush, develop_set)
    f_hol = _slice_rows(flush, holdout_set)
    f_stu = _slice_rows(flush, study_set)
    s_dev = _slice_rows(survey, develop_set)
    s_hol = _slice_rows(survey, holdout_set)
    s_stu = _slice_rows(survey, study_set)

    def _cov(rows, fl):
        keys = {(r["session"], r["symbol"]) for r in rows}
        n = len(rows)
        n_hit = len({(t["session"], t["symbol"]) for t in fl if (t["session"], t["symbol"]) in keys})
        return n, n_hit, (n_hit / n if n else 0.0)

    n_d, hit_d, c_d = _cov(r_dev, f_dev)
    n_h, hit_h, c_h = _cov(r_hol, f_hol)
    n_s, hit_s, c_s = _cov(r_stu, f_stu)
    alt_d = sum(r["altitude"] for r in r_dev)
    alt_h = sum(r["altitude"] for r in r_hol)
    mfe_d = sum(t["mfe_ext"] for t in f_dev)
    mfe_h = sum(t["mfe_ext"] for t in f_hol)
    never_d = sum(r["altitude"] for r in r_dev if r.get("launch_hour") in NEVER_SIT)
    para = (
        f"On develop, confirmed-launch rocket-days (n={n_d}, prior_close $1-20, sea=prior close) "
        f"posted {alt_d * 100:.1f} pct-points of gross altitude after a 1R haircut "
        f"(median {(_pct([r['altitude'] for r in r_dev], 50) * 100) if r_dev else 0:.2f}pp). "
        f"flush|max6 sat on {hit_d} of those name-days ({100 * c_d:.1f}%) and captured "
        f"{mfe_d * 100:.1f} pct-points of MFE from its own entries "
        f"({(100 * mfe_d / alt_d) if alt_d else 0:.1f}% of field altitude points — % from entry, not from sea). "
        f"{100 * (never_d / alt_d) if alt_d else 0:.0f}% of develop field altitude launched in hours this specialist "
        f"never sits (04-07 and after 12:00). Holdout coverage {hit_h}/{n_h}={100 * c_h:.1f}% and "
        f"{mfe_h * 100:.1f}pp captured vs {alt_h * 100:.1f}pp field; holdout is not EV. "
        f"The A19 high-based ∩ rel_vol>=3× field is larger (study n={len(s_stu)} vs confirmed-launch n={n_s})."
    )

    lines = [
        "Arrow 30 — rocket altitude rollup (diagnostic, no book)",
        "No fills that change a verdict. No $200 pass line. No B-short rescore. No cell-buy. "
        "No $500/idea. No virgin pull. No Arrow 31.",
        "Rocket-day = confirmed launch (close>=1.10*pc and next tradeable low>=1.08*pc), "
        "prior_close [$1,$20], >=5 prior sessions. Sea level = prior close. "
        "Gross altitude = max(0, max_ext_after_launch − 1R). Depths ignored.",
        f"account=100000  tape={FULL_BARS}",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "",
        para,
        "",
        "SIDE TABLE — A19 survey field (high>=1.10*pc ∩ rel_vol>=3×, >=5 prior windows)",
        f"  develop n={len(s_dev)}  holdout n={len(s_hol)}  study n={len(s_stu)}",
        f"  confirmed-launch field: develop n={n_d}  holdout n={n_h}  study n={n_s}",
        "",
    ]
    lines.extend(_field_block(r_dev, f_dev, "DEVELOP (honest in-sample)"))
    lines.append("")
    lines.extend(_field_block(r_hol, f_hol, "HOLDOUT (not EV)"))
    lines.append("")
    lines.extend(_field_block(r_stu, f_stu, "STUDY (develop+holdout)"))
    lines.append("")
    lines.append("Holdout is not expected value. Coverage is not a $200 verdict.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow30_altitude.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
