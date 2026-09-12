"""Arrow 35 — harvestable altitude from the first fillable bar + point-in-time score."""

from __future__ import annotations

import array
import math
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow19 import CLOCK_0929, CLOCK_1559, _last_at_or_before, _pack
from research.arrow20 import PRICE_HI, PRICE_LO, _iso
from research.arrow24 import _range_mid, _scan_one
from research.harness import (
    STOP_FLOOR_FRAC,
    calendar_prior_dvs,
    confirmed_launch,
    cum_dv_array,
    halt_windows,
    minute_idx,
    run_rel_vol,
)
from research.rockets import MIN_PRIORS, median_prior_window
from research.signals import MINUTE_0944, RTH_OPEN, bar_time
from research.split import develop_holdout
from research.strategies15 import resample_5m
from research.strategies30 import (
    gross_altitude,
    harvestable_from_fillable,
    r1_from_bars5,
    r1_haircut,
)

ET = ZoneInfo("America/New_York")
SCORE_LO = 3.0
SCORE_HI = 20.0
FEATURE_KEYS = (
    "ext",
    "orw",
    "pre_dv_0929",
    "run_rel_vol",
    "gap",
    "price",
    "prior_dv",
    "was_rocket_prev",
    "prev_close_ext",
    "minutes_since_launch",
    "dist_from_high",
    "vwap_rel",
    "halt_seen",
    "launch_hour",
)
PC_BANDS = ("$1-3", "$3-5", "$5-10", "$10-20")
NEVER_SIT = frozenset({4, 5, 6, 7, 12, 13, 14, 15})

# A33 B lock + A31 flush control — reprint only, do not replay.
A33_B_ID = "B|conj|atr1559|lock"
A33_B_DEV = 72.57
A33_B_HOL = 175.40
A33_B_N_HOL = 93
A31_FLUSH_ID = "flush|max6|repaired"
A31_FLUSH_DEV = 6.20
A31_FLUSH_HOL = 79.10
A31_FLUSH_N_HOL = 19
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


def pc_band(pc: float) -> str:
    if pc < 3.0 - 1e-12:
        return "$1-3"
    if pc < 5.0 - 1e-12:
        return "$3-5"
    if pc < 10.0 - 1e-12:
        return "$5-10"
    return "$10-20"


def assign_deciles(scores: list[float]) -> list[int]:
    """Decile 1 = lowest score, 10 = highest. n sums to n_all even when n % 10 != 0."""
    n = len(scores)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: (scores[i], i))
    out = [0] * n
    for r, i in enumerate(order):
        out[i] = min(10, r * 10 // n + 1)
    return out


def assign_quintiles(values: list[float | None]) -> list[int | None]:
    """Quintile 1 = lowest, 5 = highest. None stays None (skip)."""
    idx = [i for i, v in enumerate(values) if v is not None]
    out: list[int | None] = [None] * len(values)
    m = len(idx)
    if m == 0:
        return out
    order = sorted(idx, key=lambda i: (float(values[i]), i))
    for r, i in enumerate(order):
        out[i] = min(5, r * 5 // m + 1)
    return out


def _ranks(xs: list[float | None]) -> list[float]:
    """Average ranks, 1-based. None → (n+1)/2 (neutral)."""
    n = len(xs)
    mid = (n + 1) / 2.0
    indexed = [(i, float(x)) for i, x in enumerate(xs) if x is not None]
    ranks = [mid] * n
    if not indexed:
        return ranks
    indexed.sort(key=lambda t: t[1])
    i = 0
    m = len(indexed)
    while i < m:
        j = i
        while j + 1 < m and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = 0.0
    dx = 0.0
    dy = 0.0
    for x, y in zip(xs, ys):
        vx = x - mx
        vy = y - my
        num += vx * vy
        dx += vx * vx
        dy += vy * vy
    if dx <= 1e-18 or dy <= 1e-18:
        return None
    return num / math.sqrt(dx * dy)


def spearman(xs: list[float | None], ys: list[float | None]) -> float | None:
    pairs_x: list[float] = []
    pairs_y: list[float] = []
    for x, y in zip(xs, ys):
        if x is None or y is None:
            continue
        if not math.isfinite(float(x)) or not math.isfinite(float(y)):
            continue
        pairs_x.append(float(x))
        pairs_y.append(float(y))
    if len(pairs_x) < 5:
        return None
    rx = _ranks(pairs_x)
    ry = _ranks(pairs_y)
    return _pearson(rx, ry)


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


def _vwap_series(pack: dict) -> list[float | None]:
    n = len(pack["ts"])
    out: list[float | None] = [None] * n
    cpv = 0.0
    cv = 0.0
    last: float | None = None
    for i, ts in enumerate(pack["ts"]):
        if bar_time(ts) < RTH_OPEN:
            out[i] = None
            continue
        typical = (pack["high"][i] + pack["low"][i] + pack["close"][i]) / 3.0
        cv += float(pack["vol"][i])
        cpv += typical * float(pack["vol"][i])
        last = (cpv / cv) if cv > 0 else last
        out[i] = last
    return out


def _index_at_or_before_clock(pack: dict, clock: time) -> int | None:
    last = None
    for i, ts in enumerate(pack["ts"]):
        if bar_time(ts) > clock:
            break
        last = i
    return last


def _index_at_or_after(pack: dict, ts0: datetime) -> int | None:
    for i, ts in enumerate(pack["ts"]):
        if ts >= ts0:
            return i
    return None


def _session_high_to(pack: dict, i: int) -> float | None:
    mh = None
    highs = pack["high"]
    for j in range(i + 1):
        h = float(highs[j])
        mh = h if mh is None else max(mh, h)
    return mh


def _or_hl(pack: dict) -> tuple[float | None, float | None]:
    or_h = or_l = None
    for ts, h, l in zip(pack["ts"], pack["high"], pack["low"]):
        t = bar_time(ts)
        if RTH_OPEN <= t <= MINUTE_0944:
            or_h = h if or_h is None else max(or_h, h)
            or_l = l if or_l is None else min(or_l, l)
    return or_h, or_l


def _member_at(
    pack: dict,
    i: int,
    *,
    stamp_name: str,
    pc: float,
    prior_dv: float,
    confirm_ts: datetime | None,
    or_h: float | None,
    or_l: float | None,
    vwap: list[float | None],
    halt_starts: list[datetime],
    pre_dv_0929: float | None,
    gap: float | None,
    bars5: list[dict],
    harvestable: float,
    klass: str,
) -> dict:
    ts = pack["ts"][i]
    px = float(pack["close"][i])
    clock = bar_time(ts)
    ext = (px / pc - 1.0) if pc > 0 else None
    orw = _range_mid(or_h, or_l) if (or_h is not None and clock >= MINUTE_0944) else None
    launched = confirm_ts is not None and ts >= confirm_ts
    minutes = ((ts - confirm_ts).total_seconds() / 60.0) if launched else 0.0
    lh = bar_time(confirm_ts).hour if launched else None
    sh = _session_high_to(pack, i)
    dist = ((sh - px) / px) if (sh is not None and px > 0) else None
    vw = vwap[i] if i < len(vwap) else None
    if clock >= RTH_OPEN and vw is not None and vw > 0 and px > 0:
        vwap_rel = px / vw - 1.0
    else:
        vwap_rel = None
    halt_seen = 1.0 if any(h <= ts for h in halt_starts) else 0.0
    atr, r1 = r1_from_bars5(bars5, ts, px)
    atr_1 = max(float(atr), STOP_FLOOR_FRAC * px) if px > 0 else 0.0
    ref_low = or_l if or_l is not None else float(pack["low"][i])
    mae = max(0.0, px - float(ref_low)) if ref_low is not None else 0.0
    mae_le_1atr = bool(atr_1 > 0 and mae <= atr_1 + 1e-12)
    return {
        "stamp": stamp_name,
        "stamp_ts": ts,
        "ext": ext,
        "orw": orw,
        "pre_dv_0929": pre_dv_0929,
        "run_rel_vol": None,
        "gap": gap,
        "price": px,
        "prior_dv": prior_dv,
        "was_rocket_prev": None,
        "prev_close_ext": None,
        "minutes_since_launch": minutes,
        "dist_from_high": dist,
        "vwap_rel": vwap_rel,
        "halt_seen": halt_seen,
        "launch_hour": float(lh) if lh is not None else None,
        "harvestable": float(harvestable),
        "r1": r1,
        "atr": atr,
        "mae": mae,
        "mae_le_1atr": mae_le_1atr,
        "klass": klass,
        "minute_idx": minute_idx(ts),
    }


def _scan_one_35(df: pl.DataFrame, pc: float, prior_dv: float, *, want_members: bool) -> dict | None:
    pack = _pack(df)
    if pack is None or pc is None or pc <= 0:
        return None
    st = _scan_one(df, pc)
    if st is None:
        return None
    bars5 = resample_5m(df)
    conf = confirmed_launch(pack, pc)
    confirm_ts = conf["confirm_ts"] if conf["confirmed"] else None
    harv = {"harvestable": 0.0, "r1": None, "harvest_ts": None, "fill_px": None}
    gross = 0.0
    if confirm_ts is not None:
        harv = harvestable_from_fillable(pack, confirm_ts, df, bars5=bars5)
        mh = None
        for ts, h in zip(pack["ts"], pack["high"]):
            if ts < confirm_ts:
                continue
            mh = float(h) if mh is None else max(mh, float(h))
        r1_sea = r1_haircut(df, confirm_ts, pc)
        gross = gross_altitude(mh, pc, r1_sea)
    today_vol = float(sum(pack["vol"]))
    cumdv = array.array("d", cum_dv_array(pack))
    i9, dv9 = _last_at_or_before(pack, CLOCK_0929)
    i1559, _ = _last_at_or_before(pack, CLOCK_1559)
    ext1559 = pack["close"][i1559] / pc - 1.0 if i1559 is not None else None
    open930 = None
    for ts, o in zip(pack["ts"], pack["open"]):
        if bar_time(ts) >= RTH_OPEN:
            open930 = o
            break
    gap = (open930 / pc - 1.0) if open930 else None
    or_h, or_l = _or_hl(pack)
    members: list[dict] = []
    if want_members and SCORE_LO - 1e-12 <= pc <= SCORE_HI + 1e-12:
        vwap = _vwap_series(pack)
        halt_starts = [a for a, _b in halt_windows(df)]
        klass = st.get("klass") or "other"
        i44 = _index_at_or_before_clock(pack, MINUTE_0944)
        used = set()
        if i44 is not None and RTH_OPEN <= bar_time(pack["ts"][i44]) <= MINUTE_0944:
            members.append(
                _member_at(
                    pack,
                    i44,
                    stamp_name="0944",
                    pc=pc,
                    prior_dv=prior_dv,
                    confirm_ts=confirm_ts,
                    or_h=or_h,
                    or_l=or_l,
                    vwap=vwap,
                    halt_starts=halt_starts,
                    pre_dv_0929=dv9 if i9 is not None else None,
                    gap=gap,
                    bars5=bars5,
                    harvestable=float(harv.get("harvestable") or 0.0),
                    klass=klass,
                )
            )
            used.add(i44)
        if confirm_ts is not None and bar_time(confirm_ts) >= RTH_OPEN:
            i5 = _index_at_or_after(pack, confirm_ts + timedelta(minutes=5))
            if i5 is not None and i5 not in used:
                members.append(
                    _member_at(
                        pack,
                        i5,
                        stamp_name="launch+5",
                        pc=pc,
                        prior_dv=prior_dv,
                        confirm_ts=confirm_ts,
                        or_h=or_h,
                        or_l=or_l,
                        vwap=vwap,
                        halt_starts=halt_starts,
                        pre_dv_0929=dv9 if i9 is not None else None,
                        gap=gap,
                        bars5=bars5,
                        harvestable=float(harv.get("harvestable") or 0.0),
                        klass=klass,
                    )
                )
    launch_idx = minute_idx(confirm_ts) if confirm_ts is not None else None
    launch_dv = None
    if launch_idx is not None and 0 <= launch_idx < len(cumdv):
        launch_dv = float(cumdv[launch_idx])
    return {
        "confirmed": bool(conf["confirmed"]),
        "confirm_ts": confirm_ts,
        "launch_hour": bar_time(confirm_ts).hour if confirm_ts is not None else None,
        "klass": st.get("klass") or "other",
        "tagged10": bool(st.get("tagged10")),
        "max_ext": st.get("max_ext"),
        "prior_close": pc,
        "prior_dv": prior_dv,
        "today_vol": today_vol,
        "ext_1559": ext1559,
        "harvestable": float(harv.get("harvestable") or 0.0),
        "harvest_r1": harv.get("r1"),
        "harvest_ts": harv.get("harvest_ts"),
        "gross_altitude": float(gross),
        "cumdv": cumdv,
        "launch_dv": launch_dv,
        "launch_idx": launch_idx,
        "members": members,
    }


def _session_work(args: tuple) -> tuple[str, dict[str, dict]]:
    d, want, study_isos = args
    iso = d.isoformat()
    folder = FULL_BARS / iso
    out: dict[str, dict] = {}
    if not folder.exists():
        return iso, out
    want_members = iso in study_isos
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
        rec = _scan_one_35(
            df, meta["prior_close"], meta["prior_dv"], want_members=want_members
        )
        if rec is None:
            continue
        rec["symbol"] = sym
        out[sym] = rec
    return iso, out


def _slice_rows(rows: list[dict], isos: set[str]) -> list[dict]:
    return [r for r in rows if r["session"] in isos]


def _pick_five(members: list[dict]) -> list[tuple[str, float]]:
    ys = [m["harvestable"] for m in members]
    scored: list[tuple[str, float]] = []
    for k in FEATURE_KEYS:
        xs = [m.get(k) for m in members]
        rho = spearman(xs, ys)
        if rho is None:
            continue
        scored.append((k, float(rho)))
    scored.sort(key=lambda t: abs(t[1]), reverse=True)
    return scored[:5]


def _score_members(
    members: list[dict], five: list[tuple[str, float]]
) -> list[float]:
    n = len(members)
    if n == 0 or not five:
        return [0.0] * n
    acc = [0.0] * n
    for k, rho in five:
        xs = [m.get(k) for m in members]
        ranks = _ranks(xs)
        if rho < 0:
            ranks = [(n + 1) - r for r in ranks]
        for i, r in enumerate(ranks):
            acc[i] += r
    k_n = float(len(five))
    return [a / k_n for a in acc]


def _decile_table(members: list[dict], scores: list[float]) -> tuple[list[dict], int]:
    dec = assign_deciles(scores)
    n_all = len(members)
    rows = []
    for d in range(1, 11):
        idx = [i for i, x in enumerate(dec) if x == d]
        sub = [members[i] for i in idx]
        harv = [float(m["harvestable"]) for m in sub]
        mae = [float(m["mae"]) for m in sub]
        r1s = [float(m["r1"]) for m in sub if m.get("r1") is not None]
        n_mae_ok = sum(1 for m in sub if m.get("mae_le_1atr"))
        fly = sum(1 for m in sub if m.get("klass") == "FLY")
        fail = sum(1 for m in sub if m.get("klass") == "FAIL")
        other = len(sub) - fly - fail
        rows.append(
            {
                "decile": d,
                "n": len(sub),
                "median_harv": statistics.median(harv) if harv else 0.0,
                "mean_harv": (sum(harv) / len(harv)) if harv else 0.0,
                "p90_harv": _pct(harv, 90),
                "median_mae": statistics.median(mae) if mae else 0.0,
                "median_r1": statistics.median(r1s) if r1s else 0.0,
                "frac_mae_le_1atr": (n_mae_ok / len(sub)) if sub else 0.0,
                "fly": fly,
                "fail": fail,
                "other": other,
            }
        )
    return rows, n_all


def _fmt_decile(rows: list[dict], n_all: int, label: str) -> list[str]:
    n_sum = sum(r["n"] for r in rows)
    lines = [
        f"{label}  n_all={n_all}  decile_n_sum={n_sum}  n_sum==n_all={n_sum == n_all}",
        "  dec  n   med_harv  mean_harv   p90   med_mae  med_r1  mae<=1ATR  FLY  FAIL  other",
    ]
    for r in rows:
        lines.append(
            f"  {r['decile']:3d} {r['n']:5d}  {100 * r['median_harv']:8.3f}pp "
            f"{100 * r['mean_harv']:8.3f}pp {100 * r['p90_harv']:6.2f}pp "
            f"{r['median_mae']:8.4f} {100 * r['median_r1']:6.3f}% "
            f"{100 * r['frac_mae_le_1atr']:8.1f}%  "
            f"{r['fly']:4d} {r['fail']:5d} {r['other']:6d}"
        )
    return lines


def _bucket_block(rows: list[dict], key: str, values: list, label: str) -> list[str]:
    lines = [f"  by {label}:"]
    for v in values:
        sub = [r for r in rows if r.get(key) == v]
        if not sub:
            lines.append(f"    {v}: n=0")
            continue
        harv = [float(r["harvestable"]) for r in sub]
        lines.append(
            f"    {v}: n={len(sub)}  sum={100 * sum(harv):.2f}pp  "
            f"median={100 * statistics.median(harv):.3f}pp  "
            f"p90={100 * _pct(harv, 90):.3f}pp"
        )
    return lines


def _field_block(rows: list[dict], label: str) -> list[str]:
    n = len(rows)
    harv = [float(r["harvestable"]) for r in rows]
    gross = [float(r["gross_altitude"]) for r in rows]
    s_h = sum(harv)
    s_g = sum(gross)
    med = statistics.median(harv) if harv else 0.0
    p90 = _pct(harv, 90)
    by_hour = {h: 0.0 for h in range(4, 16)}
    n_hour = {h: 0 for h in range(4, 16)}
    for r in rows:
        h = r.get("launch_hour")
        if h is None or h not in by_hour:
            continue
        by_hour[int(h)] += float(r["harvestable"])
        n_hour[int(h)] += 1
    never_g = sum(float(r["gross_altitude"]) for r in rows if r.get("launch_hour") in NEVER_SIT)
    sit_pre = sum(
        float(r["harvestable"])
        for r in rows
        if r.get("launch_hour") is not None and int(r["launch_hour"]) < 9
    )
    fly = [r for r in rows if r.get("klass") == "FLY"]
    fail = [r for r in rows if r.get("klass") == "FAIL"]
    lines = [
        f"{label}",
        f"  confirmed-launch rocket-days n={n}  prior_close [$1,$20]  >=5 prior sessions",
        f"  sum harvestable={s_h * 100:.2f} pct-points  median={med * 100:.3f}pp  p90={p90 * 100:.3f}pp",
        f"  A30-style gross (sea=prior close) sum={s_g * 100:.2f}pp  "
        f"sit-able share of that mountain={100 * s_h / s_g if s_g else 0:.1f}%",
        f"  A30 never-sit hours (04-07, 12-15) gross={never_g * 100:.2f}pp; "
        f"A35 harvestable from those launches (next-open at 09:45 / confirm+5)="
        f"{sit_pre * 100:.2f}pp pre-09:00 only (see hour table for all)",
        "  harvestable by launch hour:",
    ]
    for h in range(4, 16):
        lines.append(f"    {h:02d}: n={n_hour[h]}  harv={by_hour[h] * 100:.2f}pp")
    lines.append(
        f"  FLY n={len(fly)} harv={100 * sum(float(r['harvestable']) for r in fly):.2f}pp  "
        f"FAIL n={len(fail)} harv={100 * sum(float(r['harvestable']) for r in fail):.2f}pp  "
        f"other n={n - len(fly) - len(fail)}"
    )
    lines.extend(_bucket_block(rows, "pc_band", list(PC_BANDS), "prior-close band"))
    qvals = [1, 2, 3, 4, 5]
    lines.extend(_bucket_block(rows, "rvol_q", qvals, "RVOL quintile at launch (1=low, 5=high)"))
    skip_q = [r for r in rows if r.get("rvol_q") is None]
    if skip_q:
        harv_s = [float(r["harvestable"]) for r in skip_q]
        lines.append(
            f"    RVOL skip: n={len(skip_q)}  sum={100 * sum(harv_s):.2f}pp  "
            f"median={100 * statistics.median(harv_s):.3f}pp"
        )
    return lines


def run_arrow35(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    cal_isos = [_iso(d) for d in all_sess]
    study_isos = {_iso(d) for d in study}
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    print(
        f"research start mode=arrow35 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "diagnostic harvestable from first fillable bar + PIT score. No new engine. "
        "No B-short rescore. No flush rings. No $500/idea. No virgin pull. No Arrow 36.",
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

    print(f"scan harvestable + PIT stamps n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow35_scan")
    prog.start_heartbeat()
    jobs = [(d, by_sess.get(_iso(d), {}), study_isos) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_work, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    vol_hist: dict[str, dict[str, float]] = {}
    rocket_hist: dict[str, dict[str, bool]] = {}
    ext_hist: dict[str, dict[str, float | None]] = {}
    cumdv_hist: dict[str, dict[str, array.array]] = {}
    for iso in cal_isos:
        for st in feat.get(iso, {}).values():
            sym = st["symbol"]
            vol_hist.setdefault(sym, {})[iso] = float(st.get("today_vol") or 0.0)
            rocket_hist.setdefault(sym, {})[iso] = bool(st.get("confirmed"))
            ext_hist.setdefault(sym, {})[iso] = st.get("ext_1559")
            cumdv_hist.setdefault(sym, {})[iso] = st["cumdv"]

    rockets: list[dict] = []
    survey: list[dict] = []
    members_dev: list[dict] = []
    members_hol: list[dict] = []
    for d in all_sess:
        iso = _iso(d)
        prev_iso = None
        prevs = [s for s in cal_isos if s < iso]
        if prevs:
            prev_iso = prevs[-1]
        for st in feat.get(iso, {}).values():
            sym = st["symbol"]
            prior_v = [vol_hist[sym][s] for s in cal_isos if s < iso and s in vol_hist.get(sym, {})]
            n_prior = len(prior_v)
            rel_vol = None
            med = median_prior_window(prior_v)
            if med:
                rel_vol = float(st.get("today_vol") or 0.0) / med
            was_prev = None
            prev_ext = None
            if prev_iso is not None:
                if prev_iso in rocket_hist.get(sym, {}):
                    was_prev = 1.0 if rocket_hist[sym][prev_iso] else 0.0
                if prev_iso in ext_hist.get(sym, {}):
                    pe = ext_hist[sym][prev_iso]
                    prev_ext = float(pe) if pe is not None else None
            launch_rvol = None
            if st.get("launch_idx") is not None and st.get("launch_dv") is not None:
                idx = int(st["launch_idx"])
                by_iso = {
                    s: float(arr[idx])
                    for s, arr in cumdv_hist.get(sym, {}).items()
                    if arr is not None and idx < len(arr)
                }
                cal = calendar_prior_dvs(by_iso, iso, cal_isos)
                if cal["n_present"] >= 5:
                    launch_rvol = run_rel_vol(st["launch_dv"], cal["values"])
            if iso in study_isos and n_prior >= MIN_PRIORS and st["confirmed"]:
                rockets.append(
                    {
                        "session": iso,
                        "symbol": sym,
                        "harvestable": float(st["harvestable"]),
                        "gross_altitude": float(st["gross_altitude"]),
                        "launch_hour": st.get("launch_hour"),
                        "klass": st.get("klass"),
                        "pc_band": pc_band(float(st["prior_close"])),
                        "rvol_launch": launch_rvol,
                        "prior_close": float(st["prior_close"]),
                    }
                )
            if (
                iso in study_isos
                and n_prior >= MIN_PRIORS
                and st.get("max_ext") is not None
                and float(st["max_ext"]) >= 0.10 - 1e-12
                and rel_vol is not None
                and float(rel_vol) >= 3.0 - 1e-12
            ):
                survey.append(
                    {
                        "session": iso,
                        "symbol": sym,
                        "harvestable": float(st["harvestable"]) if st["confirmed"] else 0.0,
                        "confirmed": bool(st["confirmed"]),
                        "klass": st.get("klass"),
                    }
                )
            if iso not in study_isos:
                continue
            dest = members_dev if iso in develop_set else members_hol
            for m in st.get("members") or []:
                mm = dict(m)
                mm["session"] = iso
                mm["symbol"] = sym
                mm["was_rocket_prev"] = was_prev
                mm["prev_close_ext"] = prev_ext
                idx = int(mm["minute_idx"])
                by_iso = {
                    s: float(arr[idx])
                    for s, arr in cumdv_hist.get(sym, {}).items()
                    if arr is not None and idx < len(arr)
                }
                today_dv = by_iso.get(iso)
                cal = calendar_prior_dvs(by_iso, iso, cal_isos)
                if cal["n_present"] >= 5 and today_dv is not None:
                    mm["run_rel_vol"] = run_rel_vol(today_dv, cal["values"])
                dest.append(mm)

    # drop bulky arrays
    for iso in feat:
        for st in feat[iso].values():
            st["cumdv"] = None
    cumdv_hist.clear()

    for iso_set, _label in ((develop_set, "dev"), (holdout_set, "hol")):
        sub = [r for r in rockets if r["session"] in iso_set]
        qs = assign_quintiles([r.get("rvol_launch") for r in sub])
        for r, q in zip(sub, qs):
            r["rvol_q"] = q

    r_dev = _slice_rows(rockets, develop_set)
    r_hol = _slice_rows(rockets, holdout_set)
    s_dev = _slice_rows(survey, develop_set)
    s_hol = _slice_rows(survey, holdout_set)

    five = _pick_five(members_dev)
    scores_dev = _score_members(members_dev, five)
    scores_hol = _score_members(members_hol, five)
    tab_dev, n_dev = _decile_table(members_dev, scores_dev)
    tab_hol, n_hol = _decile_table(members_hol, scores_hol)
    top = tab_dev[-1] if tab_dev else None
    gate_h = False
    gate_m = False
    if top and top["n"] > 0:
        gate_h = top["median_harv"] > 2.0 * top["median_r1"] + 1e-12
        gate_m = top["frac_mae_le_1atr"] >= 0.50 - 1e-12
    gate = bool(gate_h and gate_m)
    gate_s = "YES" if gate else "NO"

    g_dev = sum(r["gross_altitude"] for r in r_dev)
    h_dev = sum(r["harvestable"] for r in r_dev)
    never_g = sum(r["gross_altitude"] for r in r_dev if r.get("launch_hour") in NEVER_SIT)
    para = (
        f"On develop, confirmed-launch rocket-days (n={len(r_dev)}, prior_close $1-20) posted "
        f"{h_dev * 100:.1f} pct-points of harvestable altitude from the first fillable bar "
        f"(median {(_pct([r['harvestable'] for r in r_dev], 50) * 100) if r_dev else 0:.2f}pp) "
        f"versus {g_dev * 100:.1f} pct-points of Arrow 30 sea-level gross (prior close, max high after launch − 1R). "
        f"Sit-able share of that mountain for a next-open engine is "
        f"{100 * h_dev / g_dev if g_dev else 0:.1f}% — the rest is either the 1R haircut from a later fillable price "
        f"or premarket wick that is gone before 09:45. Arrow 30's never-sit hours (04-07 and after 12:00) held "
        f"{100 * never_g / g_dev if g_dev else 0:.1f}% of sea-level gross; a next-open book can still sit the 04-07 "
        f"launches at 09:45, so harvestable is the honest leftover, not the specialist's 0.6% flush coverage. "
        f"Holdout tables are PEEK, not a tuner. Holdout is not EV."
    )

    five_line = ", ".join(f"{k} rho={rho:+.4f}" for k, rho in five) if five else "none"
    lines = [
        "Arrow 35 — harvestable altitude + point-in-time score (diagnostic, no book)",
        "No new engine. No $200 verdict on a book. No B-short rescore. No flush rings. "
        "No $500/idea. No virgin pull. No cell-buy. No Arrow 36.",
        "Rocket-day = confirmed launch (1-min close >= 1.10*pc and next tradeable low >= 1.08*pc), "
        "prior_close [$1,$20], >=5 prior sessions. "
        "harvestable = max(0, max_high after first fillable bar / price at that bar − 1 − r1). "
        "Fillable = confirm+5m (RTH) or 09:45 (pre-09:30), volume >= 2000. "
        "r1 = 1.0x ATR of last six completed 5-min bars at the fillable stamp, floored 0.6% of price.",
        "Acronyms: ATR = Average True Range; RVOL = relative volume; MAE = maximum adverse excursion.",
        f"account=100000  tape={FULL_BARS}",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "",
        para,
        "",
        "SIDE TABLE — A19 survey field (high>=1.10*pc ∩ rel_vol>=3×, >=5 prior windows)",
        f"  develop n={len(s_dev)} confirmed={sum(1 for r in s_dev if r.get('confirmed'))}  "
        f"sum harvestable={100 * sum(r['harvestable'] for r in s_dev):.2f}pp",
        f"  holdout n={len(s_hol)} confirmed={sum(1 for r in s_hol if r.get('confirmed'))}  "
        f"sum harvestable={100 * sum(r['harvestable'] for r in s_hol):.2f}pp  PEEK",
        f"  confirmed-launch field: develop n={len(r_dev)}  holdout n={len(r_hol)}",
        "",
    ]
    lines.extend(_field_block(r_dev, "DEVELOP harvestable (honest in-sample)"))
    lines.append("")
    lines.extend(_field_block(r_hol, "HOLDOUT harvestable (PEEK, not EV)"))
    lines.append("")
    lines.append("POINT-IN-TIME SCORE  universe=eligible name-days prior_close $3-20")
    lines.append("  stamps=09:44 and (RTH launches) launch_confirm+5m")
    lines.append("  score = rank-average of five develop features with largest |Spearman| vs harvestable")
    lines.append(f"  frozen five (develop): {five_line}")
    lines.append("  No fitted model. Holdout deciles PEEK only.")
    lines.append("")
    lines.extend(_fmt_decile(tab_dev, n_dev, "DEVELOP deciles (over ALL members)"))
    lines.append("")
    lines.extend(_fmt_decile(tab_hol, n_hol, "HOLDOUT deciles (PEEK, over ALL members)"))
    lines.append("")
    if top:
        lines.append(
            f"GATE inputs (top develop decile 10): n={top['n']}  "
            f"median harvestable={100 * top['median_harv']:.3f}pp  "
            f"2x median r1={100 * 2 * top['median_r1']:.3f}pp  "
            f"harv>2r1={'YES' if gate_h else 'NO'}  "
            f"MAE<=1ATR={100 * top['frac_mae_le_1atr']:.1f}% (>=50%={'YES' if gate_m else 'NO'})"
        )
    lines.append(f"GATE={gate_s}")
    if not gate:
        lines.append("GATE=NO — Arrow 36 runs ungated by hour bucket.")
    lines.append("")
    lines.append("COMBINED (reprint, not replayed)")
    lines.append(
        f"A33 {A33_B_ID} reprint develop ${A33_B_DEV:.2f}/day "
        f"holdout ${A33_B_HOL:.2f}/day n_hold={A33_B_N_HOL}"
    )
    lines.append(
        f"A31 {A31_FLUSH_ID} control reprint develop ${A31_FLUSH_DEV:.2f}/day "
        f"holdout ${A31_FLUSH_HOL:.2f}/day n_hold={A31_FLUSH_N_HOL}"
    )
    lines.append(
        f"COMBINED {A33_B_ID} + {A31_FLUSH_ID}  (A33 B lock reprint + A31 flush control)"
    )
    lines.append(A33_COMB_DEV_LINE)
    lines.append(A33_COMB_HOL_LINE)
    lines.append("Combined holdout is not expected value (EV). Honesty: not EV.")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow35_score.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 35",
        "",
        "Diagnostic. No new engine. No $200 verdict on a book. No B-short rescore. "
        "No flush rings. No $500/idea. No virgin pull. Holdout tables are PEEK. Combined holdout is not EV. No Arrow 36.",
        para,
        f"Frozen five (develop): {five_line}",
        f"Develop members n={n_dev}  holdout members n={n_hol}  GATE={gate_s}",
        f"COMBINED {A33_B_ID}+{A31_FLUSH_ID} develop ${A33_COMB_DEV:.2f} holdout ${A33_COMB_HOL:.2f} NOT EV (reprint)",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
    return 0
