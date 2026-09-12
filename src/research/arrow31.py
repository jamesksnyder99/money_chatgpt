from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, FULL_IWM, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _summarize
from research.arrow4 import _filter_track_b
from research.arrow18 import load_iwm, trade_alpha
from research.arrow19 import _pack
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _flight, _fmt_adv, _summarize_adv
from research.arrow24 import _session_scan
from research.book import (
    concurrent_stats,
    daily_close_drawdown,
    joint_peak_risk,
    marked_equity_session,
    mfe_capture,
    replay_session,
)
from research.character import dv_ranks
from research.combine import combine_books
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, resample_15m, stitch_15m
from research.fills import is_tradeable
from research.harness import PRICE_FLOOR_PX5, attach_atr, calendar_prior_dvs, run_rel_vol
from research.signals import (
    MINUTE_0929,
    MINUTE_0945,
    MINUTE_1159,
    MINUTE_1559,
    bar_time,
)
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies15 import control_c5_ema9
from research.strategies22 import hot_gate_0800
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long, score_flush
from research.strategies26 import MAX_UNDERCUT
from research.strategies29 import flush_vs_anchor
from research.strategies30 import harvestable_altitude, r1_haircut

ET = ZoneInfo("America/New_York")
STITCH_0400 = time(4, 0)
STITCH_0730 = time(7, 30)

A27_UPTICK10_N_DEV = 204
A27_UPTICK10_N_HOL = 75

B_CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "harness_stop": True,
}
FLUSH_CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
    "harness_stop": True,
    "cost_gate": True,
    "flatten_at": MINUTE_1159,
    "last_entry_at": MINUTE_1159,
}
SHORT_POP = {"dv_min": 0.80, "gap_min": 0.015, "or_w_min": 0.025}
UPTICK10 = {
    "ssr_policy": "uptick",
    "ssr_filter": False,
    "borrow_filter": True,
    "ssr_uptick_minutes": 10,
}

B_EXPERIMENTS = (
    (
        "B|uptick10|flat1159|lock",
        {**UPTICK10, "flatten_at": MINUTE_1159, "last_entry_at": MINUTE_1159},
    ),
    (
        "B|uptick10|atr1559|lock",
        {
            **UPTICK10,
            "flatten_at": MINUTE_1559,
            "last_entry_at": MINUTE_1159,
            "atr_trail": True,
        },
    ),
    (
        "B|uptick10|atr1559|full",
        {
            **UPTICK10,
            "flatten_at": MINUTE_1559,
            "last_entry_at": MINUTE_1559,
            "atr_trail": True,
        },
    ),
)
B_IDS = tuple(e[0] for e in B_EXPERIMENTS)
FLUSH_ID = "flush|max6|repaired"
LOCK_TRAIL = "B|uptick10|atr1559|lock"
FULL_TRAIL = "B|uptick10|atr1559|full"
DIAG_0944 = "flush_0944"
DIAG_ORH = "flush_orhigh"


def _dv_through(df: pl.DataFrame, clock) -> float:
    if df is None or df.height == 0:
        return 0.0
    dv = 0.0
    for rec in df.sort("bar_start").iter_rows(named=True):
        if bar_time(rec["bar_start"]) > clock:
            break
        if not is_tradeable(rec["open"], rec["close"], rec["volume"]):
            continue
        dv += (float(rec["high"]) + float(rec["low"]) + float(rec["close"])) / 3.0 * float(
            rec["volume"] or 0.0
        )
    return dv


def _iwm_covers_full(df: pl.DataFrame) -> bool:
    if df is None or df.height == 0:
        return False
    times = [bar_time(t) for t in df["bar_start"].to_list()]
    if not times:
        return False
    return min(times) <= time(4, 5) and max(times) >= time(15, 50)


def ensure_iwm_full_hours(*, workers: int = 8) -> dict[str, pl.DataFrame]:
    """C-R2: if bench IWM lacks 04:00–16:00, pull study window only. No stock virgin pull."""
    from ingest.bars import normalize_ohlc_full, split_sessions
    from ingest.full import END_TIME, INTERVAL, START_TIME, VENUE
    from ingest.run import month_groups
    from ingest.theta_pool import ThetaLimiter, call_theta
    from theta.client import get_shared_client
    from thetadata.errors import NoDataFoundError

    FULL_IWM.mkdir(parents=True, exist_ok=True)
    study = study_sessions()
    need = []
    for d in study:
        p = FULL_IWM / f"{d.isoformat()}.parquet"
        if not p.exists():
            need.append(d)
            continue
        try:
            df = pl.read_parquet(p)
        except Exception:  # noqa: BLE001
            need.append(d)
            continue
        if not _iwm_covers_full(df):
            need.append(d)
    print(
        f"IWM 04:00-16:00 check study={len(study)} need_pull={len(need)}",
        flush=True,
    )
    if need:
        client = get_shared_client()
        limiter = ThetaLimiter(min(8, workers))
        groups = month_groups(need)
        for group in groups:
            start_d, end_d = group[0], group[-1]
            kwargs = {
                "symbol": "IWM",
                "interval": INTERVAL,
                "start_time": START_TIME,
                "end_time": END_TIME,
                "venue": VENUE,
            }
            if start_d == end_d:
                kwargs["date"] = start_d
            else:
                kwargs["start_date"] = start_d
                kwargs["end_date"] = end_d
            try:
                df, _elapsed = call_theta(limiter, client.stock_history_ohlc, **kwargs)
                norm = normalize_ohlc_full(df, "IWM", is_warmup=False)
                parts = split_sessions(norm, set(group))
                for d in group:
                    part = parts.get(d)
                    path = FULL_IWM / f"{d.isoformat()}.parquet"
                    if part is None or part.height == 0:
                        normalize_ohlc_full(pl.DataFrame(), "IWM", False).write_parquet(path)
                    else:
                        part.write_parquet(path)
                print(f"IWM full-hours wrote {start_d}..{end_d} days={len(group)}", flush=True)
            except NoDataFoundError:
                for d in group:
                    normalize_ohlc_full(pl.DataFrame(), "IWM", False).write_parquet(
                        FULL_IWM / f"{d.isoformat()}.parquet"
                    )
                print(f"IWM no data {start_d}..{end_d}", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"IWM pull failed {start_d}..{end_d}: {type(exc).__name__}",
                    flush=True,
                )
    iwm = load_iwm()
    n_full = sum(1 for d in study if _iwm_covers_full(iwm.get(d.isoformat())))
    print(f"IWM sessions on disk={len(iwm)} study_full_hours={n_full}/{len(study)}", flush=True)
    return iwm


def _prep_one(args: tuple) -> tuple:
    d, want = args
    iso = d.isoformat()
    folder = FULL_BARS / iso
    b0400: dict[str, list] = {}
    b0730: dict[str, list] = {}
    lows: dict[str, float] = {}
    dv9: dict[str, float] = {}
    if not folder.exists() or not want:
        return iso, b0400, b0730, lows, dv9
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
        b0400[sym] = resample_15m(df, not_before=STITCH_0400)
        b0730[sym] = resample_15m(df, not_before=STITCH_0730)
        lo = df["low"].min()
        if lo is not None:
            lows[sym] = float(lo)
        dv9[sym] = _dv_through(df, MINUTE_0929)
    return iso, b0400, b0730, lows, dv9


def _pack_trades(trades, bars: dict[str, pl.DataFrame] | None = None) -> list[dict]:
    out = []
    for t in trades:
        mfe_ext, reached = (0.0, False)
        if bars is not None:
            mfe_ext, reached = _flight(bars.get(t.symbol), t)
        stop_dist = t.risk / t.shares if t.shares else 0.0
        mfe_r = (mfe_ext * t.entry_px / stop_dist) if stop_dist else 0.0
        minutes = (t.exit_ts - t.entry_ts).total_seconds() / 60.0
        r = t.pnl / t.risk if t.risk else 0.0
        out.append(
            {
                "pnl": t.pnl,
                "win": t.pnl > 0,
                "risk": t.risk,
                "side": t.side,
                "shares": t.shares,
                "entry_px": t.entry_px,
                "entry_ts": t.entry_ts,
                "exit_ts": t.exit_ts,
                "tag": t.tag,
                "symbol": t.symbol,
                "r": r,
                "minutes": minutes,
                "mfe_ext": mfe_ext,
                "mfe_r": mfe_r,
                "reached_1r": reached,
            }
        )
    return out


def _pf(trades: list[dict]) -> str:
    wins = sum(float(t["pnl"]) for t in trades if t["pnl"] > 0)
    losses = abs(sum(float(t["pnl"]) for t in trades if t["pnl"] < 0))
    if not trades:
        return "0"
    if losses <= 1e-12:
        return "inf"
    return f"{wins / losses:.3f}"


def _replay_b(args: tuple) -> dict:
    (
        session_iso,
        names,
        bars15,
        sess_order,
        lows,
        pc_by,
        stitch_label,
    ) = args
    session = date.fromisoformat(session_iso)
    empty_rows = [
        {
            "session": session_iso,
            "name": n,
            "stitch": stitch_label,
            "pnl": 0.0,
            "trades": [],
            "peak": 0,
            "mean_conc": 0.0,
            "ssr_nofill": 0,
            "n_short_signals": 0,
            "n_ssr_signals": 0,
            "intraday_dd": 0.0,
            "daily_close_pnl": 0.0,
            "crossed_at_creation": 0,
            "unresolved_flatten": 0,
            "flatten_backdate_avoided": 0,
            "liquidation_requested": 0,
            "liquidation_filled": 0,
        }
        for n in B_IDS
    ]
    empty = {"session": session_iso, "stitch": stitch_label, "n_cand": len(names), "rows": empty_rows}
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
    sigs = []
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
            sigs.append(attach_atr(sig, sdf))
    rows = []
    for name, kw in B_EXPERIMENTS:
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
        rows.append(
            {
                "session": session_iso,
                "name": name,
                "stitch": stitch_label,
                "pnl": sum(t.pnl for t in trades),
                "trades": packed,
                "peak": peak,
                "mean_conc": mean_c,
                "ssr_nofill": int(st.get("ssr_nofill") or 0),
                "n_short_signals": int(st.get("n_short_signals") or 0),
                "n_ssr_signals": int(st.get("n_ssr_signals") or 0),
                "intraday_dd": float(mtm["intraday_peak_to_trough"]),
                "daily_close_pnl": float(mtm["daily_close_pnl"]),
                "crossed_at_creation": int(st.get("crossed_at_creation") or 0),
                "unresolved_flatten": int(st.get("unresolved_flatten") or 0),
                "flatten_backdate_avoided": int(st.get("flatten_backdate_avoided") or 0),
                "liquidation_requested": int(st.get("liquidation_requested") or 0),
                "liquidation_filled": int(st.get("liquidation_filled") or 0),
            }
        )
    return {"session": session_iso, "stitch": stitch_label, "n_cand": len(names), "rows": rows}


def _replay_flush(args: tuple) -> dict:
    iso, names, prior_dv = args
    session = date.fromisoformat(iso)
    empty = {
        "session": iso,
        "n_cand": len(names),
        "rows": [],
        "lookahead_n": 0,
        "lookahead_pnl": 0.0,
        "harvest": [],
        "pop": {"n_all": 0, "FLY": 0, "FAIL": 0, "other": 0, "cell": 0},
    }
    if not names:
        return empty
    bars = _read_hot_bars(session, [h["symbol"] for h in names])
    by_id: dict[str, list] = {FLUSH_ID: [], DIAG_0944: [], DIAG_ORH: [], "lookahead": []}
    pop = {"n_all": 0, "FLY": 0, "FAIL": 0, "other": 0, "cell": 0}
    harvest = []
    for h in names:
        sdf = bars.get(h["symbol"])
        pop["n_all"] += 1
        klass = str(h.get("klass") or "other")
        if klass in pop:
            pop[klass] += 1
        else:
            pop["other"] += 1
        if sdf is None or sdf.height == 0:
            continue
        in_cell = fly_cell_ok(h.get("orw"), h.get("dv0929"), h.get("ext0944"))
        if in_cell:
            pop["cell"] += 1
        score = float(h.get("rel0800") or h.get("rel0929") or 1.0)
        if in_cell:
            old = flush_ring_long(
                sdf, h.get("px0800"), tag="flush|max6", max_undercut=MAX_UNDERCUT
            )
            new = flush_ring_long(
                sdf,
                h.get("px0800"),
                tag=FLUSH_ID,
                max_undercut=MAX_UNDERCUT,
                signal_after=FLY_AVAILABLE_AT,
            )
            for s in old:
                if s.side == 1 and bar_time(s.signal_ts) < MINUTE_0945:
                    by_id["lookahead"].append(score_flush(s, score))
            for s in new:
                if s.side == 1:
                    by_id[FLUSH_ID].append(score_flush(s, score))
        px44 = h.get("px0944")
        or_high = None
        rng = opening_range(sdf)
        if rng:
            or_high = rng[0]
        if px44:
            for s in flush_vs_anchor(sdf, float(px44), tag=DIAG_0944):
                if s.side == 1:
                    by_id[DIAG_0944].append(score_flush(s, score))
        if or_high:
            for s in flush_vs_anchor(sdf, float(or_high), tag=DIAG_ORH):
                if s.side == 1:
                    by_id[DIAG_ORH].append(score_flush(s, score))
        if h.get("confirmed") and h.get("confirm_ts") is not None:
            pack = _pack(sdf)
            r1 = r1_haircut(sdf, h["confirm_ts"], h["prior_close"])
            rec = harvestable_altitude(pack, h["confirm_ts"], h["prior_close"], r1)
            harvest.append(
                {
                    "symbol": h["symbol"],
                    "harvestable": rec["harvestable"],
                    "harvest_ts": rec["harvest_ts"],
                    "launch_pre": bar_time(h["confirm_ts"]) < time(9, 30),
                }
            )
    rows = []
    la_pnl = 0.0
    for exp_id in (FLUSH_ID, DIAG_0944, DIAG_ORH, "lookahead"):
        sigs = by_id[exp_id]
        need = {s.symbol for s in sigs}
        sub = {k: bars[k] for k in need if k in bars}
        st = {}
        trades = replay_session(sub, sigs, prior_dv, stats=st, **FLUSH_CAP8)
        packed = _pack_trades(trades, bars)
        peak, mean_c = concurrent_stats(trades)
        mtm = marked_equity_session(trades, bars)
        if exp_id == "lookahead":
            la_pnl = sum(t.pnl for t in trades)
        rows.append(
            {
                "session": iso,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": packed,
                "peak": peak,
                "mean_conc": mean_c,
                "intraday_dd": float(mtm["intraday_peak_to_trough"]),
                "daily_close_pnl": float(mtm["daily_close_pnl"]),
                "crossed_at_creation": int(st.get("crossed_at_creation") or 0),
                "unresolved_flatten": int(st.get("unresolved_flatten") or 0),
                "flatten_backdate_avoided": int(st.get("flatten_backdate_avoided") or 0),
                "liquidation_requested": int(st.get("liquidation_requested") or 0),
                "liquidation_filled": int(st.get("liquidation_filled") or 0),
                "cost_skips": int(st.get("cost_skips") or 0),
            }
        )
    return {
        "session": iso,
        "n_cand": len(names),
        "rows": rows,
        "lookahead_n": len(by_id["lookahead"]),
        "lookahead_pnl": la_pnl,
        "harvest": harvest,
        "pop": pop,
    }


def _alpha_daily(trades, sessions, iwm):
    by_day = {d.isoformat(): 0.0 for d in sessions}
    skips = 0
    n_ok = 0
    for t in trades:
        iso = (
            t["entry_ts"].date().isoformat()
            if hasattr(t.get("entry_ts"), "date")
            else str(t.get("entry_ts") or "")[:10]
        )
        a = trade_alpha(t, iwm.get(iso)) if t.get("entry_ts") is not None else None
        if a is None:
            skips += 1
            continue
        by_day[iso] = by_day.get(iso, 0.0) + a
        n_ok += 1
    return [by_day.get(d.isoformat(), 0.0) for d in sessions], skips, n_ok


def _slice_rows(rows, name, stitch, isos):
    return [r for r in rows if r["name"] == name and r.get("stitch") == stitch and r["session"] in isos]


def _summ_side(subset, sessions, trades_key="trades"):
    isos = {d.isoformat() for d in sessions}
    subset = [r for r in subset if r["session"] in isos]
    pnl_map = {r["session"]: r for r in subset}
    daily = [float(pnl_map.get(d.isoformat(), {}).get("pnl", 0.0)) for d in sessions]
    trades = [t for r in subset for t in r.get(trades_key) or []]
    sm = _summarize_adv(daily, trades, len(sessions))
    peaks = [int(pnl_map.get(d.isoformat(), {}).get("peak") or 0) for d in sessions]
    means = [float(pnl_map.get(d.isoformat(), {}).get("mean_conc") or 0.0) for d in sessions]
    sm["peak_conc"] = max(peaks) if peaks else 0
    sm["mean_conc"] = (sum(means) / len(means)) if means else 0.0
    sm["pf_s"] = _pf(trades)
    sm["mfe_cap"] = mfe_capture(trades)
    idd = [float(pnl_map.get(d.isoformat(), {}).get("intraday_dd") or 0.0) for d in sessions]
    sm["intraday_dd"] = min(idd) if idd else 0.0
    sm["daily_close_dd"] = daily_close_drawdown(daily)
    sm["crossed"] = sum(int(r.get("crossed_at_creation") or 0) for r in subset)
    sm["unresolved"] = sum(int(r.get("unresolved_flatten") or 0) for r in subset)
    sm["backdate_avoided"] = sum(int(r.get("flatten_backdate_avoided") or 0) for r in subset)
    sm["liq_req"] = sum(int(r.get("liquidation_requested") or 0) for r in subset)
    sm["liq_fill"] = sum(int(r.get("liquidation_filled") or 0) for r in subset)
    return sm, daily, trades, {d.isoformat(): float(pnl_map.get(d.isoformat(), {}).get("pnl", 0.0)) for d in sessions}


def _pop_line(pop: dict, label: str) -> str:
    n = int(pop.get("n_all") or 0)
    if n <= 0:
        return f"{label}: n_all=0"
    fly = int(pop.get("FLY") or 0)
    fail = int(pop.get("FAIL") or 0)
    other = int(pop.get("other") or 0)
    cell = int(pop.get("cell") or 0)
    return (
        f"{label}: n_all={n}  FLY/n_all={fly/n:.3f} ({fly})  "
        f"FAIL/n_all={fail/n:.3f} ({fail})  other/n_all={other/n:.3f} ({other})  "
        f"FLY-cell={cell}"
    )


def run_arrow31(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    sess_order = [d.isoformat() for d in all_sess]
    cal_isos = sess_order
    print(
        f"research start mode=arrow31 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "integrity repairs A1-A7 C-R1-R7; rescore flush|max6 and B_uptick10 lock vs full. "
        "No new engine. No rocket rings. No $500/idea. No virgin pull. Combined holdout is not EV. "
        "No Arrow 32.",
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

    print(
        f"pass 1: 15m stitches 04:00 and 07:30 + session low n={len(all_sess)} symbols={len(want_b)}",
        flush=True,
    )
    bars15_0400: dict[tuple[str, str], list] = {}
    bars15_0730: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "arrow31_pre")
    prog.start_heartbeat()
    jobs = [(d, want_b) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_prep_one, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, b04, b73, lo, d9 = fut.result()
            lows[iso] = lo
            dv9[iso] = d9
            for sym, series in b04.items():
                bars15_0400[(sym, iso)] = series
            for sym, series in b73.items():
                bars15_0730[(sym, iso)] = series
            prog.mark(iso, rows=len(b04))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    replay_jobs = []
    for label, b15 in (("04:00", bars15_0400), ("07:30", bars15_0730)):
        for d in develop + holdout:
            replay_jobs.append(
                (
                    _iso(d),
                    by_sess_b.get(_iso(d), []),
                    b15,
                    sess_order,
                    lows,
                    pc_by,
                    label,
                )
            )
    print(f"pass 2: B-short replay {len(replay_jobs)} (2 stitches x sessions x {len(B_IDS)})", flush=True)
    prog2 = Progress(len(replay_jobs), "arrow31_b")
    prog2.start_heartbeat()
    b_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_b, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            b_chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_cand"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()

    print("pass 3: flush|max6 repaired + A29 id4/id5 diagnostic", flush=True)
    by_sess_f: dict[str, dict[str, dict]] = {}
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
        by_sess_f.setdefault(iso, {})[str(rec["symbol"])] = {
            "prior_close": pc,
            "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
        }
    feat: dict[str, dict[str, dict]] = {}
    prog3 = Progress(len(all_sess), "arrow31_flush_pre")
    prog3.start_heartbeat()
    jobs3 = [(d, by_sess_f.get(_iso(d), {})) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_scan, job): job[0] for job in jobs3}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog3.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog3.heartbeat()
    prog3.stop_heartbeat()
    prog3.heartbeat()

    dv8_by: dict[str, dict[str, float]] = {}
    dv9_by: dict[str, dict[str, float]] = {}
    for iso in sess_order:
        for st in feat.get(iso, {}).values():
            if st.get("dv0800") is not None:
                dv8_by.setdefault(st["symbol"], {})[iso] = float(st["dv0800"])
            if st.get("dv0929") is not None:
                dv9_by.setdefault(st["symbol"], {})[iso] = float(st["dv0929"])
    study_isos = {_iso(d) for d in study}
    n_cal_missing = 0
    n_cal_zero = 0
    n_cal_windows = 0
    for iso in sess_order:
        for st in feat.get(iso, {}).values():
            win8 = calendar_prior_dvs(dv8_by.get(st["symbol"]) or {}, iso, cal_isos)
            win9 = calendar_prior_dvs(dv9_by.get(st["symbol"]) or {}, iso, cal_isos)
            n_cal_windows += 1
            n_cal_missing += int(win9["n_missing"])
            n_cal_zero += int(win9["n_zero"])
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
    jobs4 = [
        (_iso(d), feats_by_sess.get(_iso(d), []), prior_dv_by_sess.get(_iso(d), {}))
        for d in develop + holdout
    ]
    prog4 = Progress(len(jobs4), "arrow31_flush")
    prog4.start_heartbeat()
    flush_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_flush, job) for job in jobs4]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            flush_chunks.append(chunk)
            prog4.mark(chunk["session"], rows=chunk.get("n_cand") or 0)
            if i % 8 == 0:
                prog4.heartbeat()
    prog4.stop_heartbeat()
    prog4.heartbeat()

    _write_reports(
        b_chunks,
        flush_chunks,
        iwm,
        workers,
        cpu,
        develop,
        holdout,
        capped,
        n_cal_missing,
        n_cal_zero,
        n_cal_windows,
    )
    return 0


def _write_reports(
    b_chunks,
    flush_chunks,
    iwm,
    workers,
    cpu,
    develop,
    holdout,
    capped,
    n_cal_missing,
    n_cal_zero,
    n_cal_windows,
) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    b_rows = [r for c in b_chunks for r in c["rows"]]
    f_rows = [r for c in flush_chunks for r in c["rows"]]

    def _b(name, stitch):
        return [r for r in b_rows if r["name"] == name and r.get("stitch") == stitch]

    results = []
    daily_map = {}
    trades_map = {}
    for name in B_IDS:
        sub = _b(name, "04:00")
        sm_d, daily_d, tr_d, map_d = _summ_side(sub, develop)
        sm_h, daily_h, tr_h, map_h = _summ_side(sub, holdout)
        daily_map[name] = {**map_d, **map_h}
        trades_map[name] = {"dev": tr_d, "hol": tr_h}
        a_hol, skip_h, n_ah = _alpha_daily(tr_h, holdout, iwm)
        a_dev, skip_d, n_ad = _alpha_daily(tr_d, develop, iwm)
        n_sig = sum(int(r.get("n_short_signals") or 0) for r in sub)
        n_ssr = sum(int(r.get("n_ssr_signals") or 0) for r in sub)
        results.append(
            {
                "name": name,
                "develop": sm_d,
                "holdout": sm_h,
                "ssr_share": (n_ssr / n_sig) if n_sig else 0.0,
                "ssr_nofill": sum(int(r.get("ssr_nofill") or 0) for r in sub),
                "alpha_hol": _summarize(a_hol, tr_h, len(holdout)),
                "n_alpha_hol": n_ah,
                "alpha_skip_hol": skip_h,
                "alpha_dev": _summarize(a_dev, tr_d, len(develop)),
                "n_alpha_dev": n_ad,
                "alpha_skip_dev": skip_d,
            }
        )

    stitch_n = {}
    for stitch in ("04:00", "07:30"):
        for name in ("B|uptick10|flat1159|lock", LOCK_TRAIL):
            sub = _b(name, stitch)
            tr_d = [t for r in sub if r["session"] in develop_set for t in r["trades"]]
            tr_h = [t for r in sub if r["session"] in holdout_set for t in r["trades"]]
            stitch_n[(name, stitch)] = (len(tr_d), len(tr_h))

    flush_sub = [r for r in f_rows if r["name"] == FLUSH_ID]
    sm_fd, _dd, tr_fd, map_fd = _summ_side(flush_sub, develop)
    sm_fh, _dh, tr_fh, map_fh = _summ_side(flush_sub, holdout)
    daily_flush = {**map_fd, **map_fh}
    trades_map[FLUSH_ID] = {"dev": tr_fd, "hol": tr_fh}

    diag = {}
    for did in (DIAG_0944, DIAG_ORH):
        sub = [r for r in f_rows if r["name"] == did]
        sm_d, _, _, _ = _summ_side(sub, develop)
        sm_h, _, _, _ = _summ_side(sub, holdout)
        diag[did] = (sm_d, sm_h)

    la_n = sum(int(c.get("lookahead_n") or 0) for c in flush_chunks)
    la_pnl = sum(float(c.get("lookahead_pnl") or 0.0) for c in flush_chunks)
    la_n_d = sum(int(c.get("lookahead_n") or 0) for c in flush_chunks if c["session"] in develop_set)
    la_n_h = sum(int(c.get("lookahead_n") or 0) for c in flush_chunks if c["session"] in holdout_set)
    la_pnl_d = sum(
        float(c.get("lookahead_pnl") or 0.0) for c in flush_chunks if c["session"] in develop_set
    )
    la_pnl_h = sum(
        float(c.get("lookahead_pnl") or 0.0) for c in flush_chunks if c["session"] in holdout_set
    )

    pop_d = {"n_all": 0, "FLY": 0, "FAIL": 0, "other": 0, "cell": 0}
    pop_h = {"n_all": 0, "FLY": 0, "FAIL": 0, "other": 0, "cell": 0}
    for c in flush_chunks:
        dest = pop_d if c["session"] in develop_set else pop_h
        p = c.get("pop") or {}
        for k in dest:
            dest[k] += int(p.get(k) or 0)

    harv_d = [h for c in flush_chunks if c["session"] in develop_set for h in c.get("harvest") or []]
    harv_vals = [float(h["harvestable"]) for h in harv_d]
    harv_hit = [v for v in harv_vals if v > 0]

    comb_lock_d = combine_books(
        {d.isoformat(): daily_map[LOCK_TRAIL].get(d.isoformat(), 0.0) for d in develop},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in develop},
    )
    comb_lock_h = combine_books(
        {d.isoformat(): daily_map[LOCK_TRAIL].get(d.isoformat(), 0.0) for d in holdout},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in holdout},
    )
    comb_full_d = combine_books(
        {d.isoformat(): daily_map[FULL_TRAIL].get(d.isoformat(), 0.0) for d in develop},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in develop},
    )
    comb_full_h = combine_books(
        {d.isoformat(): daily_map[FULL_TRAIL].get(d.isoformat(), 0.0) for d in holdout},
        {d.isoformat(): daily_flush.get(d.isoformat(), 0.0) for d in holdout},
    )
    peak_risk_lock_d = joint_peak_risk(trades_map[LOCK_TRAIL]["dev"], trades_map[FLUSH_ID]["dev"])
    peak_risk_lock_h = joint_peak_risk(trades_map[LOCK_TRAIL]["hol"], trades_map[FLUSH_ID]["hol"])
    peak_risk_full_d = joint_peak_risk(trades_map[FULL_TRAIL]["dev"], trades_map[FLUSH_ID]["dev"])
    peak_risk_full_h = joint_peak_risk(trades_map[FULL_TRAIL]["hol"], trades_map[FLUSH_ID]["hol"])

    def _promo(dev, hol) -> bool:
        return hol["clears_200"] and dev["per_day"] >= 0

    flush_green = sm_fd["per_day"] >= 0 and sm_fh["per_day"] > 0
    lock = next(r for r in results if r["name"] == LOCK_TRAIL)
    lock_green = lock["develop"]["per_day"] >= 0 and lock["holdout"]["per_day"] > 0
    lock_pass = _promo(lock["develop"], lock["holdout"])
    flush_pass = sm_fh["clears_200"] and sm_fd["per_day"] >= 0
    honesty = []
    if not flush_green:
        honesty.append(
            f"repaired flush is no longer both-green "
            f"(develop ${sm_fd['per_day']:.2f} holdout ${sm_fh['per_day']:.2f})"
        )
    if not lock_green:
        honesty.append(
            f"locked trail is no longer both-green "
            f"(develop ${lock['develop']['per_day']:.2f} holdout ${lock['holdout']['per_day']:.2f})"
        )
    if not honesty:
        honesty.append("repaired flush and locked trail are both-green on the printed slices")

    promo = [r["name"] for r in results if _promo(r["develop"], r["holdout"])]
    if flush_pass:
        promo.append(FLUSH_ID)
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(promo)
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 31 book has holdout >= $200/day AND non-red develop. "
            "Combined holdout is not expected value (EV)."
        )

    n_d_flat, n_h_flat = stitch_n[("B|uptick10|flat1159|lock", "04:00")]
    n_d_tr, n_h_tr = stitch_n[(LOCK_TRAIL, "04:00")]
    n_d_flat7, n_h_flat7 = stitch_n[("B|uptick10|flat1159|lock", "07:30")]
    n_d_tr7, n_h_tr7 = stitch_n[(LOCK_TRAIL, "07:30")]

    lines = [
        "Arrow 31 — integrity repairs; rescore flush|max6 and B_uptick10 lock vs full",
        verdict,
        "Honesty: " + "; ".join(honesty) + ".",
        "Combined holdout is not expected value (EV). Do not write that the account is one improvement from $200.",
        "No new engine. No rocket rings. No $500/idea. No virgin pull. No cell-buy. No cap12. No Arrow 32.",
        "Acronyms: EMA = exponential moving average; ATR = Average True Range; "
        "SSR = Short Sale Restriction; RVOL = relative volume; MFE = maximum favorable excursion; "
        "IWM = iShares Russell 2000 ETF.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap={capped}  tape={FULL_BARS}",
        "A1-A5 on. FLY cell available_at=09:45. last_entry_at distinct from flatten_at. "
        "Trail-through-close queues next-event. Flatten fills at or after the clock. "
        "RVOL calendar = last ten NYSE sessions (explicit zero vs missing).",
        "",
        "A1 look-ahead (historical flush|max6 entries that would be rejected: signal_ts < 09:45 using 09:44 cell)",
        f"  n={la_n} (develop {la_n_d} holdout {la_n_h})  PnL$={la_pnl:.2f} "
        f"(develop {la_pnl_d:.2f} holdout {la_pnl_h:.2f})",
        "",
        "C-R3 EMA stitch n vs A27 B_uptick10 (develop 204 / holdout 75). Neither stitch is a new champion.",
        f"  04:00 flat1159|lock n develop={n_d_flat} holdout={n_h_flat}  "
        f"vs A27 {n_d_flat}/{A27_UPTICK10_N_DEV}={n_d_flat / max(A27_UPTICK10_N_DEV, 1):.2f}x  "
        f"{n_h_flat}/{A27_UPTICK10_N_HOL}={n_h_flat / max(A27_UPTICK10_N_HOL, 1):.2f}x",
        f"  07:30 flat1159|lock n develop={n_d_flat7} holdout={n_h_flat7}  "
        f"vs A27 {n_d_flat7}/{A27_UPTICK10_N_DEV}={n_d_flat7 / max(A27_UPTICK10_N_DEV, 1):.2f}x  "
        f"{n_h_flat7}/{A27_UPTICK10_N_HOL}={n_h_flat7 / max(A27_UPTICK10_N_HOL, 1):.2f}x",
        f"  04:00 atr1559|lock n develop={n_d_tr} holdout={n_h_tr}",
        f"  07:30 atr1559|lock n develop={n_d_tr7} holdout={n_h_tr7}",
        "",
        _pop_line(pop_d, "population develop (hot-08:00 $5-20 scan)"),
        _pop_line(pop_h, "population holdout (hot-08:00 $5-20 scan)"),
        (
            f"A6 RVOL calendar windows={n_cal_windows} missing_name_days={n_cal_missing} "
            f"explicit_zeros={n_cal_zero}  (calendar enforced; zeros are zeros, missings excluded from median)"
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
            f"ssr_nofill={r['ssr_nofill']}  MFE-capture={r['develop']['mfe_cap']:.3f}"
        )
        lines.append(
            f"    marked equity: daily-close DD$={r['develop']['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={r['develop']['intraday_dd']:.2f}  "
            f"crossed_at_creation={r['develop']['crossed']}  unresolved_flatten={r['develop']['unresolved']}  "
            f"backdate_avoided={r['develop']['backdate_avoided']}  "
            f"liq_req={r['develop']['liq_req']} liq_fill={r['develop']['liq_fill']}"
        )
        lines.append(f"  holdout {_fmt(r['holdout'], holdout=True)}")
        lines.append(
            f"    PF={h['pf_s']}  peak_conc={h['peak_conc']}  mean_conc={h['mean_conc']:.2f}  "
            f"MFE-capture={h['mfe_cap']:.3f}  "
            f"IWM alpha hold ${r['alpha_hol']['per_day']:.2f} (n={r['n_alpha_hol']} skip={r['alpha_skip_hol']})"
        )
        lines.append(
            f"    marked equity: daily-close DD$={h['daily_close_dd']:.2f}  "
            f"intraday peak-to-trough$={h['intraday_dd']:.2f}  "
            f"crossed_at_creation={h['crossed']}  unresolved_flatten={h['unresolved']}  "
            f"backdate_avoided={h['backdate_avoided']}"
        )

    flag_f = "BOTH" if flush_pass else ("YES" if sm_fh["clears_200"] else "NO")
    if sm_fh["clears_200"] and sm_fd["per_day"] < 0:
        flag_f = "NO*"
    lines.append(
        f"{FLUSH_ID:<28} {sm_fd['per_day']:10.2f} {sm_fh['per_day']:11.2f} "
        f"{sm_fh['n_trades']:7d} {sm_fh['avg_r']:7.3f} {sm_fh['pf_s']:>6} {sm_fh['t_stat']:7.2f} "
        f"{sm_fh['mfe_cap']:8.3f} {flag_f:>6}"
    )
    lines.append("  develop")
    lines.extend(_fmt_adv(sm_fd))
    lines.append(
        f"    MFE-capture={sm_fd['mfe_cap']:.3f}  daily-close DD$={sm_fd['daily_close_dd']:.2f}  "
        f"intraday peak-to-trough$={sm_fd['intraday_dd']:.2f}  "
        f"crossed_at_creation={sm_fd['crossed']}  unresolved_flatten={sm_fd['unresolved']}  "
        f"backdate_avoided={sm_fd['backdate_avoided']}"
    )
    lines.append("  holdout")
    lines.extend(_fmt_adv(sm_fh))
    lines.append(
        f"    MFE-capture={sm_fh['mfe_cap']:.3f}  daily-close DD$={sm_fh['daily_close_dd']:.2f}  "
        f"intraday peak-to-trough$={sm_fh['intraday_dd']:.2f}  vs_$200="
        f"{'YES' if sm_fh['clears_200'] else 'NO'}"
    )
    lines.append("")
    lines.append("A29 ids 4/5 diagnostic only (undercut of 09:44 close; undercut of OR high). Not a pass candidate.")
    for did, (sd, sh) in diag.items():
        lines.append(
            f"  {did}: develop ${sd['per_day']:.2f}/day n={sd['n_trades']}  "
            f"holdout ${sh['per_day']:.2f}/day n={sh['n_trades']}"
        )
    lines.append("")
    if harv_vals:
        med = statistics.median(harv_vals)
        mean = sum(harv_vals) / len(harv_vals)
        lines.append(
            f"C-R7 harvestable_altitude develop n={len(harv_vals)} mean={mean:.4f} median={med:.4f} "
            f"frac>0={len(harv_hit) / len(harv_vals):.3f}  (confirm+5m, RTH/09:45, vol>=2000; not a full field scan)"
        )
    else:
        lines.append("C-R7 harvestable_altitude develop n=0")
    lines.append("")
    lines.append(
        f"COMBINED lock  {LOCK_TRAIL} + {FLUSH_ID}  (apples-to-apples morning book)"
    )
    lines.append(
        f"  develop $/day={comb_lock_d['per_day']:.2f}  std={comb_lock_d['std_day']:.2f}  "
        f"se={comb_lock_d['se_day']:.2f}  t={comb_lock_d['t_stat']:.2f}  "
        f"ci95=[{comb_lock_d['ci_lo']:.2f},{comb_lock_d['ci_hi']:.2f}]  "
        f"maxDD$={comb_lock_d['max_dd']:.2f}  corr={comb_lock_d['corr'].get((0, 1), 0.0):.3f}  "
        f"joint_peak_risk$={peak_risk_lock_d:.2f}"
    )
    lines.append(
        f"  holdout $/day={comb_lock_h['per_day']:.2f}  std={comb_lock_h['std_day']:.2f}  "
        f"se={comb_lock_h['se_day']:.2f}  t={comb_lock_h['t_stat']:.2f}  "
        f"ci95=[{comb_lock_h['ci_lo']:.2f},{comb_lock_h['ci_hi']:.2f}]  "
        f"maxDD$={comb_lock_h['max_dd']:.2f}  corr={comb_lock_h['corr'].get((0, 1), 0.0):.3f}  "
        f"joint_peak_risk$={peak_risk_lock_h:.2f}  NOT EV"
    )
    lines.append(f"FULL  {FULL_TRAIL} + {FLUSH_ID}  (afternoon admits allowed; not EV)")
    lines.append(
        f"  develop $/day={comb_full_d['per_day']:.2f}  std={comb_full_d['std_day']:.2f}  "
        f"se={comb_full_d['se_day']:.2f}  t={comb_full_d['t_stat']:.2f}  "
        f"ci95=[{comb_full_d['ci_lo']:.2f},{comb_full_d['ci_hi']:.2f}]  "
        f"maxDD$={comb_full_d['max_dd']:.2f}  corr={comb_full_d['corr'].get((0, 1), 0.0):.3f}  "
        f"joint_peak_risk$={peak_risk_full_d:.2f}"
    )
    lines.append(
        f"  holdout $/day={comb_full_h['per_day']:.2f}  std={comb_full_h['std_day']:.2f}  "
        f"se={comb_full_h['se_day']:.2f}  t={comb_full_h['t_stat']:.2f}  "
        f"ci95=[{comb_full_h['ci_lo']:.2f},{comb_full_h['ci_hi']:.2f}]  "
        f"maxDD$={comb_full_h['max_dd']:.2f}  corr={comb_full_h['corr'].get((0, 1), 0.0):.3f}  "
        f"joint_peak_risk$={peak_risk_full_h:.2f}  NOT EV"
    )
    lines.append(
        "NO* = holdout >= 200 but develop is red — not a pass. Combined holdout is not EV."
    )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow31_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 31",
        "",
        verdict,
        "",
        "Integrity repairs A1-A7 and C-R1-R7. Rescored flush|max6|repaired and B_uptick10 "
        "trail locked vs full. No new engine. No rocket rings. No $500/idea. No virgin pull. "
        "Combined holdout is not EV. No Arrow 32.",
        "Honesty: " + "; ".join(honesty) + ".",
        f"A1 look-ahead rejected n={la_n} PnL$={la_pnl:.2f}.",
        (
            f"C-R3 stitch 04:00 flat n={n_d_flat}/{n_h_flat}  07:30 flat n={n_d_flat7}/{n_h_flat7} "
            f"vs A27 204/75. Neither champion."
        ),
        (
            f"- {FLUSH_ID}: develop ${sm_fd['per_day']:.2f}/day holdout ${sm_fh['per_day']:.2f}/day "
            f"n_hold={sm_fh['n_trades']} MFE-capture={sm_fh['mfe_cap']:.3f}"
        ),
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"MFE-capture={r['holdout']['mfe_cap']:.3f} IWM skip={r['alpha_skip_hol']}"
        )
    bits.append(
        f"COMBINED lock develop ${comb_lock_d['per_day']:.2f} holdout ${comb_lock_h['per_day']:.2f} NOT EV"
    )
    bits.append(
        f"FULL develop ${comb_full_d['per_day']:.2f} holdout ${comb_full_h['per_day']:.2f} NOT EV"
    )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
