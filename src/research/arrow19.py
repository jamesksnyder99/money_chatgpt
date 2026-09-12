from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow4 import _filter_track_a, _filter_track_b
from research.fills import tradeable_mask
from research.rockets import median_prior_window, window_tradeable
from research.signals import MINUTE_0944, MINUTE_0945, RTH_OPEN, bar_time
from research.split import develop_holdout

ET = ZoneInfo("America/New_York")

PRICE_LO = 1.0
PRICE_HI_ROCKET = 20.0
PRICE_HI_SNAP = 50.0
ROCKET_MULT = 1.10
MIN_PRIORS = 5
LOOKBACK = 10
CLOCK_0730 = time(7, 30)
CLOCK_0800 = time(8, 0)
CLOCK_0929 = time(9, 29)
CLOCK_1559 = time(15, 59)
GAP_MOVER = 0.05
DV_REL_MOVER = 3.0


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = (p / 100.0) * (len(ys) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    w = pos - lo
    return ys[lo] * (1.0 - w) + ys[hi] * w


def _fmt_f(x: float | None, digits: int = 4) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _launch_bucket(ts: datetime) -> str:
    t = bar_time(ts)
    if t < CLOCK_0730:
        return "pre0730"
    if t < RTH_OPEN:
        return "pre_rth"
    if t <= MINUTE_0944:
        return "first15"
    return "after0945"


def _pack(bars: pl.DataFrame) -> dict | None:
    ok = window_tradeable(bars)
    if ok.height == 0:
        return None
    return {
        "ts": ok["bar_start"].to_list(),
        "open": [float(x) for x in ok["open"].to_list()],
        "high": [float(x) for x in ok["high"].to_list()],
        "low": [float(x) for x in ok["low"].to_list()],
        "close": [float(x) for x in ok["close"].to_list()],
        "vol": [float(x) if x is not None else 0.0 for x in ok["volume"].to_list()],
    }


def _last_at_or_before(pack: dict, clock: time) -> tuple[int | None, float]:
    """Index of last bar with t <= clock, and typical*vol dollar volume through that bar."""
    last = None
    dv = 0.0
    for i, ts in enumerate(pack["ts"]):
        if bar_time(ts) > clock:
            break
        last = i
        h, l, c, v = pack["high"][i], pack["low"][i], pack["close"][i], pack["vol"][i]
        dv += (h + l + c) / 3.0 * v
    return last, dv


def scan_full_rocket(bars: pl.DataFrame, prior_close: float, prior_vols: list[float]) -> dict:
    """Full-clock rocket (04:00-15:59). Skip if <5 prior window volumes."""
    out = {
        "status": "skip",
        "rocket": False,
        "max_ext": None,
        "launch_ts": None,
        "launch_hour": None,
        "launch_bucket": None,
        "peak_ts": None,
        "minutes_to_peak": None,
        "ext_0930": None,
        "ext_1559": None,
        "still_10_0930": None,
        "still_10_1559": None,
        "gave_back": None,
        "rel_vol": None,
        "today_vol": 0.0,
    }
    med = median_prior_window(prior_vols)
    if med is None or prior_close is None or prior_close <= 0:
        return out
    pack = _pack(bars)
    today_vol = float(sum(pack["vol"])) if pack else 0.0
    out["status"] = "ok"
    out["today_vol"] = today_vol
    out["rel_vol"] = today_vol / med
    if pack is None:
        return out
    highs = pack["high"]
    session_high = max(highs)
    max_ext = session_high / float(prior_close) - 1.0
    out["max_ext"] = max_ext
    thresh = ROCKET_MULT * float(prior_close)
    launch_ts = None
    peak_ts = None
    for ts, h in zip(pack["ts"], highs):
        if launch_ts is None and h >= thresh - 1e-12:
            launch_ts = ts
        if peak_ts is None and h >= session_high - 1e-12:
            peak_ts = ts
    i930, _ = _last_at_or_before(pack, RTH_OPEN)
    i1559, _ = _last_at_or_before(pack, CLOCK_1559)
    if i930 is not None:
        out["ext_0930"] = pack["close"][i930] / float(prior_close) - 1.0
        out["still_10_0930"] = out["ext_0930"] >= 0.10 - 1e-12
    if i1559 is not None:
        out["ext_1559"] = pack["close"][i1559] / float(prior_close) - 1.0
        out["still_10_1559"] = out["ext_1559"] >= 0.10 - 1e-12
        out["gave_back"] = 1 if out["ext_1559"] < 0.5 * max_ext - 1e-12 else 0
    rocket = session_high >= thresh - 1e-12
    out["rocket"] = rocket
    if rocket and launch_ts is not None:
        out["launch_ts"] = launch_ts
        out["launch_hour"] = bar_time(launch_ts).hour
        out["launch_bucket"] = _launch_bucket(launch_ts)
        out["peak_ts"] = peak_ts
        if peak_ts is not None:
            out["minutes_to_peak"] = max(0.0, (peak_ts - launch_ts).total_seconds() / 60.0)
    return out


def _rocket_from_raw(st: dict, prior_close: float, prior_vols: list[float]) -> dict:
    out = {
        "status": "skip",
        "rocket": False,
        "max_ext": None,
        "launch_ts": None,
        "launch_hour": None,
        "launch_bucket": None,
        "peak_ts": None,
        "minutes_to_peak": None,
        "ext_0930": None,
        "ext_1559": None,
        "still_10_0930": None,
        "still_10_1559": None,
        "gave_back": None,
        "rel_vol": None,
        "today_vol": float(st.get("vol") or 0.0),
    }
    med = median_prior_window(prior_vols)
    if med is None or prior_close is None or prior_close <= 0:
        return out
    out["status"] = "ok"
    out["rel_vol"] = out["today_vol"] / med
    high = st.get("high")
    if high is None:
        return out
    max_ext = float(high) / float(prior_close) - 1.0
    out["max_ext"] = max_ext
    c930, c1559 = st.get("close_0930"), st.get("close_1559")
    if c930 is not None:
        out["ext_0930"] = float(c930) / float(prior_close) - 1.0
        out["still_10_0930"] = out["ext_0930"] >= 0.10 - 1e-12
    if c1559 is not None:
        out["ext_1559"] = float(c1559) / float(prior_close) - 1.0
        out["still_10_1559"] = out["ext_1559"] >= 0.10 - 1e-12
        out["gave_back"] = 1 if out["ext_1559"] < 0.5 * max_ext - 1e-12 else 0
    rocket = float(high) >= ROCKET_MULT * float(prior_close) - 1e-12
    out["rocket"] = rocket
    launch_ts = st.get("launch_ts")
    peak_ts = st.get("peak_ts")
    if rocket and launch_ts is not None:
        out["launch_ts"] = launch_ts
        out["launch_hour"] = bar_time(launch_ts).hour
        out["launch_bucket"] = _launch_bucket(launch_ts)
        out["peak_ts"] = peak_ts
        if peak_ts is not None:
            out["minutes_to_peak"] = max(0.0, (peak_ts - launch_ts).total_seconds() / 60.0)
    return out


def _snap_from_raw(st: dict, prior_close: float, which: str, prior_dvs: list[float]) -> dict:
    px = st.get("px0800") if which == "0800" else st.get("px0929")
    ts = st.get("ts0800") if which == "0800" else st.get("ts0929")
    dv = st.get("dv0800") if which == "0800" else st.get("dv0929")
    out = {
        "status": "skip",
        "gap_so_far": None,
        "already_up10": False,
        "already_down10": False,
        "pre_dv_so_far": float(dv or 0.0),
        "pre_dv_rel": None,
        "mover": False,
        "last_ts": ts,
        "clock": which,
    }
    if px is None or prior_close is None or prior_close <= 0:
        return out
    gap = float(px) / float(prior_close) - 1.0
    up10 = gap >= 0.10 - 1e-12
    down10 = gap <= -0.10 + 1e-12
    med = median_prior_window(prior_dvs)
    rel = (float(dv) / med) if med is not None and dv is not None else None
    mover = abs(gap) >= GAP_MOVER - 1e-12 or up10 or down10
    if rel is not None and rel >= DV_REL_MOVER - 1e-12:
        mover = True
    out.update(
        {
            "status": "ok" if med is not None else "ok_norel",
            "gap_so_far": gap,
            "already_up10": up10,
            "already_down10": down10,
            "pre_dv_rel": rel,
            "mover": mover,
        }
    )
    return out


def snapshot_at(
    bars: pl.DataFrame,
    prior_close: float,
    clock: time,
    prior_dvs: list[float],
) -> dict:
    """Point-in-time snapshot at `clock`. Ignores prints after that stamp."""
    out = {
        "status": "skip",
        "gap_so_far": None,
        "already_up10": False,
        "already_down10": False,
        "pre_dv_so_far": 0.0,
        "pre_dv_rel": None,
        "mover": False,
        "last_ts": None,
    }
    if prior_close is None or prior_close <= 0:
        return out
    pack = _pack(bars)
    if pack is None:
        return out
    idx, dv = _last_at_or_before(pack, clock)
    if idx is None:
        return out
    last_px = pack["close"][idx]
    gap = last_px / float(prior_close) - 1.0
    up10 = gap >= 0.10 - 1e-12
    down10 = gap <= -0.10 + 1e-12
    med = median_prior_window(prior_dvs)
    rel = (dv / med) if med is not None else None
    mover = abs(gap) >= GAP_MOVER - 1e-12 or up10 or down10
    if rel is not None and rel >= DV_REL_MOVER - 1e-12:
        mover = True
    out.update(
        {
            "status": "ok" if med is not None else "ok_norel",
            "gap_so_far": gap,
            "already_up10": up10,
            "already_down10": down10,
            "pre_dv_so_far": dv,
            "pre_dv_rel": rel,
            "mover": mover,
            "last_ts": pack["ts"][idx],
        }
    )
    return out


def _raw_from_pack(pack: dict, prior_close: float | None) -> dict:
    vol = float(sum(pack["vol"]))
    i8, dv8 = _last_at_or_before(pack, CLOCK_0800)
    i9, dv9 = _last_at_or_before(pack, CLOCK_0929)
    i930, _ = _last_at_or_before(pack, RTH_OPEN)
    i1559, _ = _last_at_or_before(pack, CLOCK_1559)
    rec = {
        "vol": vol,
        "dv0800": dv8,
        "dv0929": dv9,
        "px0800": pack["close"][i8] if i8 is not None else None,
        "ts0800": pack["ts"][i8] if i8 is not None else None,
        "px0929": pack["close"][i9] if i9 is not None else None,
        "ts0929": pack["ts"][i9] if i9 is not None else None,
        "high": max(pack["high"]),
        "launch_ts": None,
        "peak_ts": None,
        "close_0930": pack["close"][i930] if i930 is not None else None,
        "close_1559": pack["close"][i1559] if i1559 is not None else None,
    }
    if prior_close is None or prior_close <= 0:
        return rec
    thresh = ROCKET_MULT * float(prior_close)
    session_high = rec["high"]
    for ts, h in zip(pack["ts"], pack["high"]):
        if rec["launch_ts"] is None and h >= thresh - 1e-12:
            rec["launch_ts"] = ts
        if rec["peak_ts"] is None and h >= session_high - 1e-12:
            rec["peak_ts"] = ts
        if rec["launch_ts"] is not None and rec["peak_ts"] is not None:
            break
    return rec


def _session_features(args: tuple) -> tuple[str, dict[str, dict]]:
    d, elig_d = args
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
        pack = _pack(df)
        if pack is None:
            continue
        pc = (elig_d.get(sym) or {}).get("prior_close")
        out[sym] = _raw_from_pack(pack, pc)
    return iso, out


def _keys(df: pl.DataFrame) -> set[tuple[str, str]]:
    if df.height == 0:
        return set()
    out = set()
    for rec in df.select("session_date", "symbol").iter_rows(named=True):
        d = rec["session_date"]
        iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        out.add((iso, str(rec["symbol"])))
    return out


def _iso(d) -> str:
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _rocket_block(title: str, rows: list[dict]) -> list[str]:
    ok = [r for r in rows if r["status"] == "ok"]
    skipped = [r for r in rows if r["status"] == "skip"]
    n_ok = len(ok)
    rockets = [r for r in ok if r["rocket"]]
    r3 = [r for r in rockets if (r["rel_vol"] or 0) >= 3.0 - 1e-12]
    r5 = [r for r in rockets if (r["rel_vol"] or 0) >= 5.0 - 1e-12]

    def _n_pct(n: int) -> str:
        if n_ok <= 0:
            return f"{n} (n/a)"
        return f"{n} ({100.0 * n / n_ok:.2f}%)"

    def _ext_count(thr: float) -> int:
        return sum(1 for r in ok if r["max_ext"] is not None and r["max_ext"] >= thr - 1e-12)

    hours = {h: 0 for h in range(4, 16)}
    buckets = {"pre0730": 0, "pre_rth": 0, "first15": 0, "after0945": 0}
    for r in r3:
        h = r["launch_hour"]
        if h in hours:
            hours[h] += 1
        b = r["launch_bucket"]
        if b in buckets:
            buckets[b] += 1

    def _dist(label: str, xs: list[float]) -> str:
        return (
            f"  {label}: n={len(xs)} median={_fmt_f(statistics.median(xs) if xs else None)} "
            f"p90={_fmt_f(_percentile(xs, 90))}"
        )

    def _rocket_stats(label: str, rs: list[dict]) -> list[str]:
        maxs = [float(r["max_ext"]) for r in rs if r["max_ext"] is not None]
        mins = [float(r["minutes_to_peak"]) for r in rs if r["minutes_to_peak"] is not None]
        e930 = [float(r["ext_0930"]) for r in rs if r["ext_0930"] is not None]
        e1559 = [float(r["ext_1559"]) for r in rs if r["ext_1559"] is not None]
        still_o = sum(1 for r in rs if r["still_10_0930"])
        still_e = sum(1 for r in rs if r["still_10_1559"])
        gave = sum(1 for r in rs if r["gave_back"] == 1)
        n = len(rs)
        fo = f"{still_o / n:.3f}" if n else "n/a"
        fe = f"{still_e / n:.3f}" if n else "n/a"
        fg = f"{gave / n:.3f}" if n else "n/a"
        return [
            f"{label}:",
            _dist("max_ext", maxs),
            _dist("minutes_to_peak", mins),
            _dist("ext_0930", e930),
            _dist("ext_1559", e1559),
            f"  still >= +10% at 09:30: {still_o}/{n} ({fo})",
            f"  still >= +10% at 15:59: {still_e}/{n} ({fe})",
            f"  gave_back by 15:59 (end_ext < 0.5*max_ext): {gave}/{n} ({fg})",
        ]

    ta = sum(1 for r in r3 if r["track_a"])
    tb = sum(1 for r in r3 if r["track_b"])
    lines = [
        title,
        f"eligible $1-$20 name-days with enough history (>=5 prior full windows): {n_ok}",
        f"skipped for <5 prior sessions: {len(skipped)}",
        f"max_ext >= 10%: {_n_pct(_ext_count(0.10))}",
        f"max_ext >= 15%: {_n_pct(_ext_count(0.15))}",
        f"max_ext >= 20%: {_n_pct(_ext_count(0.20))}",
        f"max_ext >= 50%: {_n_pct(_ext_count(0.50))}",
        f"rel_vol >= 3x (among enough-history): {sum(1 for r in ok if (r['rel_vol'] or 0) >= 3)}",
        f"rel_vol >= 5x (among enough-history): {sum(1 for r in ok if (r['rel_vol'] or 0) >= 5)}",
        f"rocket ∩ rel_vol>=3x: {len(r3)}",
        f"rocket ∩ rel_vol>=5x: {len(r5)}",
        "",
        "launch-clock histogram (rockets ∩ rel_vol>=3x), hours 04-15:",
    ]
    for h in range(4, 16):
        lines.append(f"  {h:02d}: {hours[h]}")
    lines.append("buckets (rockets ∩ rel_vol>=3x):")
    lines.append(f"  pre-07:30: {buckets['pre0730']}")
    lines.append(f"  07:30-09:29: {buckets['pre_rth']}")
    lines.append(f"  09:30-09:44: {buckets['first15']}")
    lines.append(f"  09:45-15:59: {buckets['after0945']}")
    lines.append("")
    lines.extend(_rocket_stats("all rockets (max_ext>=10%)", rockets))
    lines.append("")
    lines.extend(_rocket_stats("rockets ∩ rel_vol>=3x", r3))
    n3 = len(r3)
    lines.append(f"Track A gate (prior_close $10-30, $5M ADV, eligible): {ta}/{n3} of >=3x rockets")
    lines.append(f"Track B gate (prior_close $10-50, $5M ADV, 400/day cap): {tb}/{n3} of >=3x rockets")
    return lines


def _snap_block(title: str, snaps: list[dict], r3_keys: set[tuple[str, str]]) -> list[str]:
    movers = [s for s in snaps if s["mover"]]
    n = len(snaps)
    nm = len(movers)
    ov = sum(1 for s in movers if (s["session"], s["symbol"]) in r3_keys)
    cheap = sum(1 for s in movers if s["prior_close"] < 10.0 - 1e-12)
    mid = sum(1 for s in movers if 10.0 - 1e-12 <= s["prior_close"] <= 50.0 + 1e-12)
    tb = sum(1 for s in movers if s["track_b"])
    return [
        title,
        f"eligible $1-$50 name-days scored: {n}",
        f"movers: {nm} ({(100.0 * nm / n):.2f}% of scored)" if n else "movers: 0",
        f"overlap with §A rocket∩>=3x: {ov}/{nm}",
        f"movers prior_close <$10: {cheap}",
        f"movers prior_close $10-50: {mid}",
        f"movers Track B eligible that day: {tb}/{nm}",
    ]


def _paragraph(study_r: list[dict], snaps_0929: list[dict]) -> str:
    ok = [r for r in study_r if r["status"] == "ok"]
    r3 = [r for r in ok if r["rocket"] and (r["rel_vol"] or 0) >= 3.0 - 1e-12]
    buckets = {"pre0730": 0, "pre_rth": 0, "first15": 0, "after0945": 0}
    hours = {h: 0 for h in range(4, 16)}
    for r in r3:
        if r["launch_bucket"] in buckets:
            buckets[r["launch_bucket"]] += 1
        if r["launch_hour"] in hours:
            hours[r["launch_hour"]] += 1
    early = buckets["pre0730"]
    n3 = len(r3)
    stub_pre = 569
    stub_n3 = 1214
    peak_h = max(hours, key=hours.get) if n3 else None
    r3_keys = {(r["session"], r["symbol"]) for r in r3}
    movers = [s for s in snaps_0929 if s["mover"]]
    ov = sum(1 for s in movers if (s["session"], s["symbol"]) in r3_keys)
    nm = len(movers)
    wider = nm > 0 and ov / nm < 0.5
    clock_bit = (
        f"04:00 moved the launch clock vs the stub scan: {early}/{n3} of full-tape >=3x rockets "
        f"print +10% before 07:30 (stub had {stub_pre}/{stub_n3} in 07:30-09:29 premarket, none before 07:30). "
        f"Peak launch hour is {peak_h:02d}."
        if n3
        else "No >=3x rockets on the full tape."
    )
    field_bit = (
        f" Already-moving at 09:29 is a wider field than the rocket set: {nm} movers vs {n3} >=3x rockets, "
        f"overlap {ov} ({(100.0 * ov / nm):.1f}% of movers)."
        if nm and wider
        else (
            f" Already-moving at 09:29 is mostly the rocket set: overlap {ov}/{nm} movers with {n3} >=3x rockets."
            if nm
            else " No 09:29 movers."
        )
    )
    return clock_bit + field_bit


def run_arrow19(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow19 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} develop={develop[0]}..{develop[-1]} "
        f"holdout={holdout[0]}..{holdout[-1]} tape={FULL_BARS}",
        flush=True,
    )
    print(
        "diagnostic only; no fills; no $200 verdict; do not touch data/bars; no kernel rescore. No Arrow 20.",
        flush=True,
    )
    if not FULL_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
    elig = pl.read_parquet(FULL_ELIGIBILITY)
    track_a = _keys(_filter_track_a(elig) if "eligible" in elig.columns else elig.head(0))
    track_b_df, _capped = _filter_track_b(elig)
    track_b = _keys(track_b_df)

    by_sess: dict[str, dict[str, dict]] = {}
    for rec in elig.select(
        "session_date", "symbol", "prior_close", "prior_dollar_volume", "eligible"
    ).iter_rows(named=True):
        iso = _iso(rec["session_date"])
        if rec.get("eligible") is False:
            continue
        pc = rec["prior_close"]
        if pc is None:
            continue
        by_sess.setdefault(iso, {})[str(rec["symbol"])] = {
            "prior_close": float(pc),
            "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
        }

    print(f"pass 1: session features over warmup+study n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow19_feat")
    prog.start_heartbeat()
    jobs = [(d, by_sess.get(_iso(d), {})) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_features, job): job[0] for job in jobs}
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
        for sym, st in feat.get(iso, {}).items():
            vol_hist.setdefault(sym, []).append((iso, st["vol"]))
            dv8_hist.setdefault(sym, []).append((iso, st["dv0800"]))
            dv9_hist.setdefault(sym, []).append((iso, st["dv0929"]))

    study_set = {_iso(d) for d in study}
    rocket_rows: list[dict] = []
    snap8: list[dict] = []
    snap9: list[dict] = []
    print("pass 2: rockets $1-20 and snapshots $1-50 on study sessions", flush=True)
    prog2 = Progress(len(study), "arrow19_score")
    prog2.start_heartbeat()
    for i, d in enumerate(study, 1):
        iso = _iso(d)
        elig_d = by_sess.get(iso, {})
        files = feat.get(iso, {})
        for sym, meta in elig_d.items():
            pc = meta["prior_close"]
            st = files.get(sym) or {}
            if PRICE_LO - 1e-12 <= pc <= PRICE_HI_ROCKET + 1e-12:
                prior_vols = [v for s, v in (vol_hist.get(sym) or []) if s < iso]
                rec = _rocket_from_raw(st, pc, prior_vols)
                rec["session"] = iso
                rec["symbol"] = sym
                rec["prior_close"] = pc
                rec["prior_dv"] = meta["prior_dv"]
                rec["track_a"] = (iso, sym) in track_a
                rec["track_b"] = (iso, sym) in track_b
                rocket_rows.append(rec)
            if PRICE_LO - 1e-12 <= pc <= PRICE_HI_SNAP + 1e-12:
                p8 = [v for s, v in (dv8_hist.get(sym) or []) if s < iso]
                p9 = [v for s, v in (dv9_hist.get(sym) or []) if s < iso]
                s8 = _snap_from_raw(st, pc, "0800", p8)
                s9 = _snap_from_raw(st, pc, "0929", p9)
                for snap in (s8, s9):
                    snap["session"] = iso
                    snap["symbol"] = sym
                    snap["prior_close"] = pc
                    snap["track_b"] = (iso, sym) in track_b
                snap8.append(s8)
                snap9.append(s9)
        prog2.mark(iso, rows=len(elig_d))
        if i % 8 == 0:
            prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    _write_report(
        rocket_rows,
        snap8,
        snap9,
        workers,
        cpu,
        develop,
        holdout,
        study,
    )
    return 0


def _write_report(rockets, snap8, snap9, workers, cpu, develop, holdout, study) -> None:
    dev_set = {_iso(d) for d in develop}
    hol_set = {_iso(d) for d in holdout}
    study_set = {_iso(d) for d in study}

    def _slice(rows, sess):
        return [r for r in rows if r["session"] in sess]

    r_study, r_dev, r_hol = _slice(rockets, study_set), _slice(rockets, dev_set), _slice(rockets, hol_set)
    s8_study, s8_dev, s8_hol = _slice(snap8, study_set), _slice(snap8, dev_set), _slice(snap8, hol_set)
    s9_study, s9_dev, s9_hol = _slice(snap9, study_set), _slice(snap9, dev_set), _slice(snap9, hol_set)

    def _r3_keys(rows):
        return {
            (r["session"], r["symbol"])
            for r in rows
            if r.get("rocket") and (r.get("rel_vol") or 0) >= 3.0 - 1e-12
        }

    para = _paragraph(r_study, s9_study)
    lines = [
        "Arrow 19 — full-tape rocket and already-moving survey (04:00-16:00)",
        "Diagnostic only. No fills. No $200 verdict. Did not touch data/bars. Did not rescore the kernel. No Arrow 20.",
        f"tape={FULL_BARS} eligibility={FULL_ELIGIBILITY}",
        f"rockets: prior_close [$1, $20], high >= 1.10 * prior_close, rel_vol vs prior 10 full 04:00-15:59 windows",
        f"snapshots: 08:00 and 09:29 last tradeable bar, eligible prior_close [$1, $50]",
        f"study n={len(study)} {study[0]}..{study[-1]}",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "",
    ]
    lines.extend(_rocket_block("A — ROCKETS STUDY-WIDE", r_study))
    lines.append("")
    lines.extend(_rocket_block("A — ROCKETS DEVELOP (through 2026-07-30)", r_dev))
    lines.append("")
    lines.extend(_rocket_block("A — ROCKETS HOLDOUT (from 2026-07-31)", r_hol))
    lines.append("")
    lines.extend(_snap_block("B — SNAPSHOT 08:00 STUDY-WIDE", s8_study, _r3_keys(r_study)))
    lines.append("")
    lines.extend(_snap_block("B — SNAPSHOT 08:00 DEVELOP", s8_dev, _r3_keys(r_dev)))
    lines.append("")
    lines.extend(_snap_block("B — SNAPSHOT 08:00 HOLDOUT", s8_hol, _r3_keys(r_hol)))
    lines.append("")
    lines.extend(_snap_block("B — SNAPSHOT 09:29 STUDY-WIDE", s9_study, _r3_keys(r_study)))
    lines.append("")
    lines.extend(_snap_block("B — SNAPSHOT 09:29 DEVELOP", s9_dev, _r3_keys(r_dev)))
    lines.append("")
    lines.extend(_snap_block("B — SNAPSHOT 09:29 HOLDOUT", s9_hol, _r3_keys(r_hol)))
    lines.append("")
    lines.append("Did 04:00 move the launch clock; is 09:29 already-moving the rocket set or wider:")
    lines.append(para)
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow19_survey.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
