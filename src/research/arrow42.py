"""Arrow 42 — one-look score of frozen B lock + repaired flush on virgin tape."""

from __future__ import annotations

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import virgin_study_sessions, virgin_warmup_sessions
from ingest.paths import (
    BARS_DIR,
    FULL_BARS,
    REPORTS,
    VIRGIN_BARS,
    VIRGIN_ELIGIBILITY,
    VIRGIN_IWM,
    virgin_bar_path,
)
from ingest.progress import Progress
from research.arrow4 import TRACK_B_CAP, TRACK_B_EXPLODE, TRACK_B_MAX_PX, TRACK_B_MIN_DV, TRACK_B_MIN_PX, _filter_track_b
from research.arrow18 import trade_alpha
from research.arrow20 import PRICE_HI, PRICE_LO, _iso
from research.arrow23 import _fmt_adv, _summarize_adv
from research.arrow24 import _scan_one
from research.arrow31 import (
    SHORT_POP,
    _alpha_daily,
    _dv_through,
    _pack_trades,
    _summ_side,
)
from research.arrow32 import FLUSH_ID
from research.arrow33 import MIN_RVOL_PRIORS
from research.arrow40 import _kw_b, _kw_f
from research.book import concurrent_stats, joint_peak_risk, marked_equity_session, replay_session
from research.character import dv_ranks
from research.combine import combine_books
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import resample_15m, stitch_15m
from research.harness import PRICE_FLOOR_PX5, attach_atr, calendar_prior_dvs, run_rel_vol
from research.signals import MINUTE_0929, Signal
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies22 import hot_gate_0800
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long, score_flush
from research.strategies26 import MAX_UNDERCUT
from research.strategies32 import conjunction_c5_ema9

ET = ZoneInfo("America/New_York")
TAPE = VIRGIN_BARS
SHELVE_N = 40
PDV_10M = 10_000_000.0
NICE_MIN_PX = 20.0
NICE_MAX_PX = 80.0
STITCH_0400 = dtime(4, 0)
B_LOCK_ID = "B|conj|atr1559|lock"
FLUSH_NAME = "flush|max6|repaired"
CSV_NAME = "equity_virgin_200.csv"


def score_sessions() -> list[date]:
    """One window: first 2026 session through last full May. Do not split."""
    return virgin_study_sessions()


def warmup_for_features() -> list[date]:
    return virgin_warmup_sessions()


def is_score_session(d: date) -> bool:
    return d in set(score_sessions())


def keep_b_signal(sig: Signal) -> bool:
    return sig.side == -1


def keep_f_signal(sig: Signal) -> bool:
    return sig.side == 1


def shelve_reason(n: int) -> str:
    if n < SHELVE_N:
        return f"SHELVE n={n} < {SHELVE_N}"
    return ""


def _cap_list(raw: pl.DataFrame) -> tuple[pl.DataFrame, bool]:
    if raw.height == 0:
        return raw, False
    per = raw.group_by("session_date").len()
    max_n = int(per["len"].max()) if per.height else 0
    capped = max_n > TRACK_B_EXPLODE
    if capped:
        raw = (
            raw.sort(["session_date", "prior_dollar_volume"], descending=[False, True])
            .group_by("session_date", maintain_order=True)
            .head(TRACK_B_CAP)
        )
    return raw, capped


def _filter_band(elig: pl.DataFrame, min_px: float, max_px: float, min_dv: float) -> tuple[pl.DataFrame, bool]:
    raw = elig.filter(
        pl.col("prior_close").is_not_null()
        & (pl.col("prior_close") >= min_px)
        & (pl.col("prior_close") <= max_px)
        & (pl.col("prior_dollar_volume") >= min_dv)
    )
    return _cap_list(raw)


def _by_sess(frame: pl.DataFrame) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    if frame.height == 0:
        return out
    for rec in frame.select("session_date", "symbol", "prior_close", "prior_dollar_volume").iter_rows(
        named=True
    ):
        pc = rec["prior_close"]
        if pc is None:
            continue
        iso = _iso(rec["session_date"])
        out.setdefault(iso, []).append(
            {
                "symbol": str(rec["symbol"]),
                "prior_close": float(pc),
                "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
            }
        )
    return out


def _read_virgin_bars(session: date, symbols: list[str]) -> dict[str, pl.DataFrame]:
    out: dict[str, pl.DataFrame] = {}
    for sym in symbols:
        p = virgin_bar_path(session, sym)
        if not p.exists():
            continue
        try:
            df = pl.read_parquet(p)
        except Exception:  # noqa: BLE001
            continue
        if df.height:
            out[sym] = df
    return out


def _b_prep(args: tuple) -> tuple:
    d, want = args
    iso = d.isoformat()
    folder = VIRGIN_BARS / iso
    b15: dict[str, list] = {}
    lows: dict[str, float] = {}
    dv9: dict[str, float] = {}
    if not folder.exists() or not want:
        return iso, b15, lows, dv9
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
        dv9[sym] = _dv_through(df, MINUTE_0929)
    return iso, b15, lows, dv9


def _session_scan(args: tuple) -> tuple[str, dict[str, dict]]:
    d, want = args
    iso = d.isoformat()
    folder = VIRGIN_BARS / iso
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
    prog = Progress(len(all_sess), "arrow42_flush_pre")
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


def _conj_sigs(
    names: list[dict],
    bars: dict[str, pl.DataFrame],
    iso: str,
    sess_order: list[str],
    bars15,
    dv9_hist,
) -> list:
    ranks = dv_ranks({h["symbol"]: float(h["prior_dv"]) for h in names})
    conj_by = {}
    for h in names:
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
        win = calendar_prior_dvs(dv9_hist.get(sym) or {}, iso, sess_order)
        if int(win["n_present"]) < MIN_RVOL_PRIORS:
            continue
        stitched = stitch_15m(sym, iso, sess_order, bars15)
        got, _led = conjunction_c5_ema9(sdf, stitched, or_high)
        for sig in got:
            if not keep_b_signal(sig):
                continue
            conj_by[sym] = attach_atr(sig, sdf)
    return list(conj_by.values())


def _flush_sigs(names: list[dict], bars: dict[str, pl.DataFrame]) -> list:
    out = []
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
            if keep_f_signal(s):
                out.append(score_flush(s, score))
    return out


def _replay_book(
    sigs,
    bars,
    prior_dv,
    kw,
    *,
    prior_c=None,
    psl=None,
    pspc=None,
) -> tuple[list, list, int, float, float]:
    need = {s.symbol for s in sigs}
    sub = {k: bars[k] for k in need if k in bars}
    if not sigs or not sub:
        return [], [], 0, 0.0, 0.0
    extra = {"prior_close": prior_c}
    if psl is not None:
        extra["prior_session_low"] = psl
        extra["prior_session_prior_close"] = pspc or {}
    trades = replay_session(sub, sigs, prior_dv, **extra, **kw)
    packed = _pack_trades(trades, bars)
    peak, mean_c = concurrent_stats(trades)
    mtm = marked_equity_session(trades, bars)
    return trades, packed, int(peak), float(mean_c), float(mtm["intraday_peak_to_trough"])


def _replay_day(args: tuple) -> dict:
    (
        iso,
        b_names,
        b10_names,
        nice_names,
        flush_names,
        bars15,
        sess_order,
        lows,
        pc_by,
        dv9_hist,
    ) = args
    session = date.fromisoformat(iso)
    empty = {
        "session": iso,
        "pnl_b": 0.0,
        "pnl_f": 0.0,
        "pnl_b10": 0.0,
        "pnl_nice": 0.0,
        "trades_b": [],
        "trades_f": [],
        "trades_b10": [],
        "trades_nice": [],
        "peak_b": 0,
        "peak_f": 0,
        "peak_b10": 0,
        "peak_nice": 0,
        "mean_b": 0.0,
        "mean_f": 0.0,
        "mean_b10": 0.0,
        "mean_nice": 0.0,
        "idd_b": 0.0,
        "idd_f": 0.0,
        "idd": 0.0,
        "idd_b10": 0.0,
        "idd_nice": 0.0,
        "joint_peak": 0.0,
        "n_b": 0,
        "n_f": 0,
        "n_b10": 0,
        "n_nice": 0,
    }
    symbols = list(
        {h["symbol"] for h in b_names + b10_names + nice_names + flush_names}
    )
    if not symbols:
        return empty
    bars = _read_virgin_bars(session, symbols)
    prior_c = {}
    for h in b_names + b10_names + nice_names + flush_names:
        if h.get("prior_close") is not None:
            prior_c[h["symbol"]] = float(h["prior_close"])
    idx = sess_order.index(iso) if iso in sess_order else -1
    prev_iso = sess_order[idx - 1] if idx > 0 else None
    psl = dict(lows.get(prev_iso) or {}) if prev_iso else {}
    pspc = dict(pc_by.get(prev_iso) or {}) if prev_iso else {}

    kw_b = _kw_b(200.0)
    kw_f = _kw_f(200.0)
    b_sigs = _conj_sigs(b_names, bars, iso, sess_order, bars15, dv9_hist)
    b10_sigs = _conj_sigs(b10_names, bars, iso, sess_order, bars15, dv9_hist)
    nice_sigs = _conj_sigs(nice_names, bars, iso, sess_order, bars15, dv9_hist)
    f_sigs = _flush_sigs(flush_names, bars)
    prior_dv_b = {h["symbol"]: float(h["prior_dv"]) for h in b_names}
    prior_dv_b10 = {h["symbol"]: float(h["prior_dv"]) for h in b10_names}
    prior_dv_nice = {h["symbol"]: float(h["prior_dv"]) for h in nice_names}
    prior_dv_f = {h["symbol"]: float(h["prior_dv"]) for h in flush_names}

    trades_b, pack_b, peak_b, mean_b, idd_b = _replay_book(
        b_sigs, bars, prior_dv_b, kw_b, prior_c=prior_c, psl=psl, pspc=pspc
    )
    trades_b10, pack_b10, peak_b10, mean_b10, idd_b10 = _replay_book(
        b10_sigs, bars, prior_dv_b10, kw_b, prior_c=prior_c, psl=psl, pspc=pspc
    )
    trades_nice, pack_nice, peak_nice, mean_nice, idd_nice = _replay_book(
        nice_sigs, bars, prior_dv_nice, kw_b, prior_c=prior_c, psl=psl, pspc=pspc
    )
    trades_f, pack_f, peak_f, mean_f, idd_f = _replay_book(
        f_sigs, bars, prior_dv_f, kw_f, prior_c=prior_c
    )
    union = list(trades_b) + list(trades_f)
    mtm = marked_equity_session(union, bars) if union else {"intraday_peak_to_trough": 0.0}
    jpeak = joint_peak_risk(trades_b, trades_f)
    return {
        "session": iso,
        "pnl_b": sum(t.pnl for t in trades_b),
        "pnl_f": sum(t.pnl for t in trades_f),
        "pnl_b10": sum(t.pnl for t in trades_b10),
        "pnl_nice": sum(t.pnl for t in trades_nice),
        "trades_b": pack_b,
        "trades_f": pack_f,
        "trades_b10": pack_b10,
        "trades_nice": pack_nice,
        "peak_b": peak_b,
        "peak_f": peak_f,
        "peak_b10": peak_b10,
        "peak_nice": peak_nice,
        "mean_b": mean_b,
        "mean_f": mean_f,
        "mean_b10": mean_b10,
        "mean_nice": mean_nice,
        "idd_b": idd_b,
        "idd_f": idd_f,
        "idd": float(mtm["intraday_peak_to_trough"]),
        "idd_b10": idd_b10,
        "idd_nice": idd_nice,
        "joint_peak": float(jpeak),
        "n_b": len(trades_b),
        "n_f": len(trades_f),
        "n_b10": len(trades_b10),
        "n_nice": len(trades_nice),
    }


def _rows_as(chunks: dict, sessions: list[date], pnl_key: str, trades_key: str, peak_key: str, mean_key: str, idd_key: str):
    rows = []
    for d in sessions:
        iso = d.isoformat()
        rec = chunks.get(iso) or {}
        rows.append(
            {
                "session": iso,
                "pnl": float(rec.get(pnl_key) or 0.0),
                "trades": rec.get(trades_key) or [],
                "peak": int(rec.get(peak_key) or 0),
                "mean_conc": float(rec.get(mean_key) or 0.0),
                "intraday_dd": float(rec.get(idd_key) or 0.0),
            }
        )
    return rows


def load_virgin_iwm() -> dict[str, pl.DataFrame]:
    out: dict[str, pl.DataFrame] = {}
    if not VIRGIN_IWM.exists():
        return out
    for p in VIRGIN_IWM.glob("*.parquet"):
        out[p.stem] = pl.read_parquet(p)
    return out


def _monthly(daily: list[float], sessions: list[date]) -> list[str]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for d, v in zip(sessions, daily):
        buckets[f"{d.year:04d}-{d.month:02d}"].append(float(v))
    lines = ["monthly combined $/day (description, not a pick):"]
    for key in sorted(buckets):
        xs = buckets[key]
        n = len(xs)
        mean = sum(xs) / n if n else 0.0
        lines.append(f"  {key} n={n}  $/day={mean:.2f}  sum$={sum(xs):.2f}")
    return lines


def _write_equity(sessions: list[date], daily_b: list[float], daily_f: list[float]) -> None:
    eq = ACCOUNT
    rows = []
    for d, b, f in zip(sessions, daily_b, daily_f):
        comb = float(b) + float(f)
        eq += comb
        rows.append(
            {
                "date": d.isoformat(),
                "b_pnl": round(float(b), 2),
                "flush_pnl": round(float(f), 2),
                "combined_pnl": round(comb, 2),
                "equity": round(eq, 2),
            }
        )
    REPORTS.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_csv(REPORTS / CSV_NAME)


def run_arrow42(*, workers: int | None = None) -> int:
    if TAPE.resolve() == FULL_BARS.resolve() or TAPE.resolve() == BARS_DIR.resolve():
        raise RuntimeError("Arrow 42 must read data/virgin/bars, not data/full or Lab A data/bars")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = score_sessions()
    warm = warmup_for_features()
    all_sess = list(warm) + list(study)
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow42 workers={workers} cpu={cpu} "
        f"score={study[0]}..{study[-1]} n={len(study)} one_window "
        f"warmup_features={warm[0]}..{warm[-1]} tape={TAPE}",
        flush=True,
    )
    print(
        "one look on data/virgin/. Frozen $200/$200 A33 B|conj|atr1559|lock + A31 flush|max6|repaired. "
        "Do not split and pick. Do not change doors. Did not touch data/full or Lab A data/bars. No Arrow 43.",
        flush=True,
    )
    if not VIRGIN_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {VIRGIN_ELIGIBILITY}")
    elig = pl.read_parquet(VIRGIN_ELIGIBILITY)
    track_b, capped_b = _filter_track_b(elig)
    track_b10, capped_b10 = _filter_band(elig, TRACK_B_MIN_PX, TRACK_B_MAX_PX, PDV_10M)
    nice, capped_nice = _filter_band(elig, NICE_MIN_PX, NICE_MAX_PX, PDV_10M)
    want = set(str(s) for s in track_b["symbol"].unique().to_list()) | set(
        str(s) for s in nice["symbol"].unique().to_list()
    )
    by_b = _by_sess(track_b)
    by_b10 = _by_sess(track_b10)
    by_nice = _by_sess(nice)
    pc_by: dict[str, dict[str, float]] = {}
    for rec in elig.select("session_date", "symbol", "prior_close").iter_rows(named=True):
        pc = rec["prior_close"]
        if pc is None:
            continue
        pc_by.setdefault(_iso(rec["session_date"]), {})[str(rec["symbol"])] = float(pc)

    print(f"B prep n_sess={len(all_sess)} want={len(want)} tape={TAPE}", flush=True)
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow42_b_pre")
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

    print("flush 08:00 hot universe on virgin tape", flush=True)
    flush_by = _flush_universe(elig, all_sess, study, workers)

    jobs = []
    for d in study:
        iso = _iso(d)
        jobs.append(
            (
                iso,
                by_b.get(iso, []),
                by_b10.get(iso, []),
                by_nice.get(iso, []),
                flush_by.get(iso, []),
                bars15,
                sess_order,
                lows,
                pc_by,
                dv9_hist,
            )
        )
    print(f"replay $200/$200 one window {len(jobs)} sessions", flush=True)
    prog2 = Progress(len(jobs), "arrow42_replay")
    prog2.start_heartbeat()
    chunks: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_day, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            chunks[rec["session"]] = rec
            prog2.mark(rec["session"], rows=1)
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    comb_rows = []
    for d in study:
        iso = d.isoformat()
        rec = chunks.get(iso) or {}
        pb = float(rec.get("pnl_b") or 0.0)
        pf = float(rec.get("pnl_f") or 0.0)
        comb_rows.append(
            {
                "session": iso,
                "pnl": pb + pf,
                "trades": (rec.get("trades_b") or []) + (rec.get("trades_f") or []),
                "peak": max(int(rec.get("peak_b") or 0), int(rec.get("peak_f") or 0)),
                "mean_conc": (float(rec.get("mean_b") or 0.0) + float(rec.get("mean_f") or 0.0)) / 2.0,
                "intraday_dd": float(rec.get("idd") or 0.0),
            }
        )
    b_rows = _rows_as(chunks, study, "pnl_b", "trades_b", "peak_b", "mean_b", "idd_b")
    f_rows = _rows_as(chunks, study, "pnl_f", "trades_f", "peak_f", "mean_f", "idd_f")
    b10_rows = _rows_as(chunks, study, "pnl_b10", "trades_b10", "peak_b10", "mean_b10", "idd_b10")
    nice_rows = _rows_as(chunks, study, "pnl_nice", "trades_nice", "peak_nice", "mean_nice", "idd_nice")

    sm_c, daily_c, tr_c, map_c = _summ_side(comb_rows, study)
    sm_b, daily_b, tr_b, map_b = _summ_side(b_rows, study)
    sm_f, daily_f, tr_f, map_f = _summ_side(f_rows, study)
    sm_b10, daily_b10, tr_b10, _ = _summ_side(b10_rows, study)
    sm_nice, daily_nice, tr_nice, _ = _summ_side(nice_rows, study)
    comb = combine_books(map_b, map_f)
    jpk = max(float((chunks.get(d.isoformat()) or {}).get("joint_peak") or 0.0) for d in study)
    worst = min(daily_c) if daily_c else 0.0
    iwm = load_virgin_iwm()
    a_daily, a_skip, a_n = _alpha_daily(tr_c, study, iwm)
    a_day = (sum(a_daily) / len(study)) if study else 0.0

    _write_equity(study, daily_b, daily_f)

    nice_n = int(sm_nice["n_trades"])
    nice_tag = shelve_reason(nice_n)
    clears = bool(sm_c["clears_200"])
    if clears:
        verdict = (
            "VERDICT: ONE-LOOK CLEARS $200 — combined B|conj|atr1559|lock + flush|max6|repaired "
            "on virgin Jan–May 2026. This window is one sample of weather, not EV."
        )
    else:
        verdict = (
            "VERDICT: FAIL — combined frozen books do not print >= $200/day on the virgin window. "
            "This window is the first unstained look; it is still one sample of weather, not EV."
        )
    honesty = (
        "One look. No rings. No new door. No parameter search. Did not split Jan–May into "
        "develop/holdout and pick. Jun–Aug holdout is not this window. Combined dollars here "
        "are still one calendar, not a printer. Did not touch data/full or Lab A data/bars. No Arrow 43."
    )
    lines = [
        "Arrow 42 — one-look score of frozen books on virgin tape",
        verdict,
        honesty,
        "Frozen $200/$200: A33 B|conj|atr1559|lock + A31 flush|max6|repaired. Side tables are filters, not tuners.",
        "Do not write that the account is one improvement from $200. Combined dollars are not EV.",
        "Acronyms: ATR = Average True Range; MFE = maximum favorable excursion; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; SSR = Short Sale Restriction; EMA = exponential moving average.",
        f"account={ACCOUNT:.0f}  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"score n={len(study)} {study[0]}..{study[-1]}  (one window; warmup {warm[0]}..{warm[-1]} features only)",
        f"workers={workers} cpu_count={cpu}  tape={TAPE}",
        f"Track B cap={capped_b}  pdv10 cap={capped_b10}  nice-houses cap={capped_nice}",
        "B: conjunction lock, 1.0x ATR after +1R, last_entry_at=11:59, flatten 15:59, cap8, SSR uptick10. "
        "Flush: max6 repaired, flatten 11:59. Risk $200/idea.",
        "",
        f"{'id':<28} {'$/day':>10} {'n':>6} {'hit':>6} {'avgR':>7} {'PF':>7} {'t':>6} {'MFE':>7} {'>=200':>6}",
    ]

    def _line(name: str, sm: dict, extra: str = "") -> str:
        flag = "YES" if sm["clears_200"] else "NO"
        return (
            f"{name:<28} {sm['per_day']:10.2f} {sm['n_trades']:6d} {sm['hit_rate']:6.3f} "
            f"{sm['avg_r']:7.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {sm['mfe_cap']:7.3f} {flag:>6}"
            f"{extra}"
        )

    lines.append(_line(B_LOCK_ID, sm_b))
    lines.extend(_fmt_adv(sm_b))
    lines.append(
        f"    peak_conc={sm_b['peak_conc']}  mean_conc={sm_b['mean_conc']:.2f}  "
        f"daily-close DD$={sm_b['daily_close_dd']:.2f}  intraday trough$={sm_b['intraday_dd']:.2f}"
    )
    lines.append(_line(FLUSH_NAME, sm_f))
    lines.extend(_fmt_adv(sm_f))
    lines.append(
        f"    peak_conc={sm_f['peak_conc']}  mean_conc={sm_f['mean_conc']:.2f}  "
        f"daily-close DD$={sm_f['daily_close_dd']:.2f}  intraday trough$={sm_f['intraday_dd']:.2f}"
    )
    lines.append(_line("COMBINED $200/$200", sm_c))
    lines.extend(_fmt_adv(sm_c))
    corr = comb["corr"].get((0, 1), 0.0)
    lines.append(
        f"    corr(B,flush)={corr:.3f}  joint_peak_risk$={jpk:.2f}  worst_day$={worst:.2f}"
    )
    lines.append(
        f"    daily-close DD$={sm_c['daily_close_dd']:.2f}  intraday trough$={sm_c['intraday_dd']:.2f}  "
        f"peak_conc={sm_c['peak_conc']}  mean_conc={sm_c['mean_conc']:.2f}"
    )
    lines.append(
        f"    IWM alpha $/day={a_day:.2f} (n={a_n} skip={a_skip})  vs_$200={'YES' if sm_c['clears_200'] else 'NO'}  "
        f"vs_$300-500={'YES' if sm_c['per_day'] >= TARGET_LO else 'NO'}  NOT EV"
    )
    lines.append("")
    lines.append("side tables (not tuners):")
    lines.append(_line("B|pdv>=$10M", sm_b10))
    lines.extend(_fmt_adv(sm_b10))
    lines.append(
        f"    daily-close DD$={sm_b10['daily_close_dd']:.2f}  intraday trough$={sm_b10['intraday_dd']:.2f}  "
        f"peak_conc={sm_b10['peak_conc']}  mean_conc={sm_b10['mean_conc']:.2f}"
    )
    extra = f"  {nice_tag}" if nice_tag else ""
    lines.append(_line("B|$20-80|pdv>=$10M", sm_nice, extra=extra))
    if nice_tag:
        lines.append(f"    {nice_tag} — not a pass candidate. Same door; n too thin to read.")
    else:
        lines.extend(_fmt_adv(sm_nice))
        lines.append(
            f"    daily-close DD$={sm_nice['daily_close_dd']:.2f}  intraday trough$={sm_nice['intraday_dd']:.2f}  "
            f"peak_conc={sm_nice['peak_conc']}  mean_conc={sm_nice['mean_conc']:.2f}"
        )
    lines.append("")
    lines.extend(_monthly(daily_c, study))
    lines.append("")
    lines.append(f"wrote {REPORTS / CSV_NAME}")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow42_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow42_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    log = [
        f"## {stamp} — Arrow 42",
        "",
        verdict,
        "",
        "One look on data/virgin/. Frozen $200/$200 A33 B|conj|atr1559|lock + A31 flush|max6|repaired. "
        "Score 2026-01-02..2026-05-29 as one window. Did not split and pick. Did not change doors. "
        "Did not touch data/full or Lab A data/bars. Combined dollars are not EV. No Arrow 43.",
        f"COMBINED $/day={sm_c['per_day']:.2f} n_B={sm_b['n_trades']} n_flush={sm_f['n_trades']} "
        f"IWM alpha ${a_day:.2f} skip={a_skip} NOT EV",
        f"B|pdv>=$10M $/day={sm_b10['per_day']:.2f} n={sm_b10['n_trades']}",
        f"B|$20-80|pdv>=$10M $/day={sm_nice['per_day']:.2f} n={sm_nice['n_trades']} {nice_tag or ''}".rstrip(),
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(log), encoding="utf-8")
    return 0
