"""Sidecar: combined EOD equity for A33 B lock + A31 flush at $200. Not an engine arrow."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow4 import _filter_track_b
from research.arrow20 import _iso, _read_hot_bars
from research.arrow31 import SHORT_POP
from research.arrow32 import FLUSH_ID
from research.arrow33 import MIN_RVOL_PRIORS
from research.arrow33 import _prep_one as _b_prep
from research.arrow40 import _flush_universe, _kw_b, _kw_f
from research.book import replay_session
from research.character import dv_ranks
from research.costs import ACCOUNT
from research.ema15 import stitch_15m
from research.harness import attach_atr, calendar_prior_dvs
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies25 import FLY_AVAILABLE_AT, fly_cell_ok, flush_ring_long, score_flush
from research.strategies26 import MAX_UNDERCUT
from research.strategies32 import conjunction_c5_ema9

ET = ZoneInfo("America/New_York")
CUT = date(2026, 7, 31)
CSV_NAME = "equity_combined_200.csv"
PNG_NAME = "equity_combined_200.png"
TXT_NAME = "equity_combined_200.txt"


def _replay_day(args: tuple) -> dict:
    (
        iso,
        b_names,
        flush_names,
        bars15,
        sess_order,
        lows,
        pc_by,
        dv9_hist,
    ) = args
    session = date.fromisoformat(iso)
    out = {
        "session": iso,
        "pnl_b": 0.0,
        "pnl_f": 0.0,
        "n_b": 0,
        "n_f": 0,
    }
    symbols = list({h["symbol"] for h in b_names + flush_names})
    if not symbols:
        return out
    bars = _read_hot_bars(session, symbols)
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
    trades_b = replay_session(
        {k: bars[k] for k in {s.symbol for s in b_sigs} if k in bars},
        b_sigs,
        prior_dv_b,
        prior_close=prior_c,
        prior_session_low=psl,
        prior_session_prior_close=pspc,
        **_kw_b(200.0),
    )
    trades_f = replay_session(
        {k: bars[k] for k in {s.symbol for s in f_sigs} if k in bars},
        f_sigs,
        prior_dv_f,
        **_kw_f(200.0),
    )
    out["pnl_b"] = sum(t.pnl for t in trades_b)
    out["pnl_f"] = sum(t.pnl for t in trades_f)
    out["n_b"] = len(trades_b)
    out["n_f"] = len(trades_f)
    return out


def _write_png(dates: list[date], equity: list[float], path) -> None:
    peak = equity[0] if equity else ACCOUNT
    dd = []
    for e in equity:
        peak = max(peak, e)
        dd.append(e - peak)
    fig, axes = plt.subplots(2, 1, sharex=True, figsize=(10.5, 6.5), height_ratios=(2.2, 1.0))
    ax, axd = axes
    ax.plot(dates, equity, color="#1f4e79", lw=1.6, label="combined EOD equity")
    ax.axvline(CUT, color="#b45309", ls="--", lw=1.2, label="2026-07-31 stained holdout (not EV)")
    ax.axhline(ACCOUNT, color="#9ca3af", ls=":", lw=0.8)
    ax.set_ylabel("equity ($)")
    ax.set_title("Combined B|conj|atr1559|lock + flush|max6|repaired  ($200 / $200)")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)
    axd.fill_between(dates, dd, 0, color="#9f1239", alpha=0.35)
    axd.plot(dates, dd, color="#9f1239", lw=1.0)
    axd.axvline(CUT, color="#b45309", ls="--", lw=1.2)
    axd.set_ylabel("drawdown from peak ($)")
    axd.set_xlabel("session date")
    axd.grid(True, alpha=0.3)
    axd.xaxis.set_major_formatter(DateFormatter("%m-%d"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)


def run_equity_curve(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=equity workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "sidecar combined EOD equity. A33 B lock + A31 flush at $200. "
        "No door change. No ingest. No Arrow 41. Holdout is not EV.",
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

    print(f"B prep n_sess={len(all_sess)}", flush=True)
    bars15: dict[tuple[str, str], list] = {}
    lows: dict[str, dict[str, float]] = {}
    dv9: dict[str, dict[str, float]] = {}
    prog = Progress(len(all_sess), "equity_b_pre")
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

    print("flush 08:00 hot universe", flush=True)
    flush_by = _flush_universe(elig, all_sess, study, workers)

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
            )
        )
    print(f"replay $200/$200 {len(jobs)} sessions", flush=True)
    prog2 = Progress(len(jobs), "equity_replay")
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

    rows = []
    eq = ACCOUNT
    n_b = n_f = 0
    n_b_h = n_f_h = 0
    holdout_set = {d.isoformat() for d in holdout}
    develop_set = {d.isoformat() for d in develop}
    for d in develop + holdout:
        iso = d.isoformat()
        rec = chunks.get(iso) or {"pnl_b": 0.0, "pnl_f": 0.0, "n_b": 0, "n_f": 0}
        b = float(rec["pnl_b"])
        f = float(rec["pnl_f"])
        comb = b + f
        eq += comb
        n_b += int(rec.get("n_b") or 0) if iso in develop_set else 0
        n_f += int(rec.get("n_f") or 0) if iso in develop_set else 0
        n_b_h += int(rec.get("n_b") or 0) if iso in holdout_set else 0
        n_f_h += int(rec.get("n_f") or 0) if iso in holdout_set else 0
        rows.append(
            {
                "date": iso,
                "b_pnl": b,
                "flush_pnl": f,
                "combined_pnl": comb,
                "equity": eq,
            }
        )

    csv_path = REPORTS / CSV_NAME
    png_path = REPORTS / PNG_NAME
    txt_path = REPORTS / TXT_NAME
    REPORTS.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).with_columns(
        [pl.col(c).round(2) for c in ("b_pnl", "flush_pnl", "combined_pnl", "equity")]
    ).write_csv(csv_path)

    dates = [date.fromisoformat(r["date"]) for r in rows]
    equity = [float(r["equity"]) for r in rows]
    _write_png(dates, equity, png_path)

    start = ACCOUNT
    end = equity[-1] if equity else ACCOUNT
    min_eq = min(equity) if equity else ACCOUNT
    peak = start
    max_dd = 0.0
    eq = start
    dev_end = start
    hol_end = end
    for r in rows:
        eq = float(r["equity"])
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
        d = date.fromisoformat(r["date"])
        if d < CUT:
            dev_end = eq
        hol_end = eq
    lines = [
        f"start=${start:.2f}  end=${end:.2f}  min_equity=${min_eq:.2f}",
        f"max_daily_close_DD=${max_dd:.2f}  develop_ending_equity=${dev_end:.2f}  holdout_ending_equity=${hol_end:.2f}",
        f"B n develop={n_b} holdout={n_b_h}  flush n develop={n_f} holdout={n_f_h}  "
        f"cut={CUT.isoformat()} stained holdout (not EV)",
    ]
    text = "\n".join(lines) + "\n"
    txt_path.write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {csv_path}", flush=True)
    print(f"wrote {png_path}", flush=True)
    print(f"wrote {txt_path}", flush=True)
    return 0
