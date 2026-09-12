from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_BARS, FULL_ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _summarize
from research.arrow20 import (
    PRICE_HI,
    PRICE_LO,
    _iso,
    _read_hot_bars,
    _session_pre,
)
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.rockets import median_prior_window
from research.signals import MINUTE_1159
from research.split import develop_holdout
from research.strategies20 import STOP_MIN_FRAC, gap_and_go_long, hot_gate
from research.strategies21 import (
    EXT8_HI,
    PRE_DV_1M,
    fade_open_short,
    gap1_open_long,
    pullback_long,
)

ET = ZoneInfo("America/New_York")

CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": STOP_MIN_FRAC,
}
CAP3 = {
    "max_positions": 3,
    "max_entries": 16,
    "max_risk_outstanding": 600.0,
    "min_stop_frac": STOP_MIN_FRAC,
}

EXPERIMENTS = (
    ("pullback", "pullback", CAP8),
    ("open|gap1", "gap1", CAP8),
    ("open|ext8", "ext8", CAP8),
    ("open|dv1m", "dv1m", CAP8),
    ("pullback|max3", "pullback", CAP3),
    ("fade|open", "fade", CAP8),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _replay_one(args: tuple) -> dict:
    session_iso, hots, prior_dv = args
    session = date.fromisoformat(session_iso)
    empty = {
        "session": session_iso,
        "n_hot": len(hots),
        "rows": [
            {"session": session_iso, "name": n, "pnl": 0.0, "trades": []} for n in IDS
        ],
    }
    if not hots:
        return empty
    bars = _read_hot_bars(session, [h["symbol"] for h in hots])
    pull_sigs: list = []
    gap1_sigs: list = []
    ext8_sigs: list = []
    dv1m_sigs: list = []
    fade_sigs: list = []
    for h in hots:
        sym = h["symbol"]
        sdf = bars.get(sym)
        if sdf is None:
            continue
        score = float(h["pre_dv_rel"])
        if sdf.height:
            for sig in pullback_long(sdf, h["last_px"], score):
                if sig.side == 1:
                    pull_sigs.append(sig)
            for sig in gap1_open_long(
                sdf, h["last_ts"], sym, h["sess_low"], h["last_px"], score
            ):
                if sig.side == 1:
                    gap1_sigs.append(sig)
        if h["ext_0929"] < EXT8_HI - 1e-12:
            for sig in gap_and_go_long(h["last_ts"], sym, h["sess_low"], h["last_px"], score):
                if sig.side == 1:
                    ext8_sigs.append(sig)
        if h["pre_dv"] >= PRE_DV_1M - 1e-9:
            for sig in gap_and_go_long(h["last_ts"], sym, h["sess_low"], h["last_px"], score):
                if sig.side == 1:
                    dv1m_sigs.append(sig)
        for sig in fade_open_short(
            h["last_ts"], sym, h["sess_high"], h["last_px"], score
        ):
            if sig.side == -1:
                fade_sigs.append(sig)

    by_kind = {
        "pullback": pull_sigs,
        "gap1": gap1_sigs,
        "ext8": ext8_sigs,
        "dv1m": dv1m_sigs,
        "fade": fade_sigs,
    }
    rows = []
    for exp_id, kind, cap in EXPERIMENTS:
        sigs = by_kind[kind]
        if kind in ("gap1", "ext8", "dv1m", "fade"):
            trades = replay_session(
                bars,
                [],
                prior_dv,
                rth_open_entries=sigs,
                flatten_at=MINUTE_1159,
                **cap,
            )
        else:
            trades = replay_session(
                bars, sigs, prior_dv, flatten_at=MINUTE_1159, **cap
            )
        rows.append(
            {
                "session": session_iso,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    return {"session": session_iso, "n_hot": len(hots), "rows": rows}


def run_arrow21(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow21 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "ids 1-5 long; id 6 short contrast; same 09:29 hot gate; data/full only; "
        "no B-short rescore; no data/bars; did not rerun strong5/newhigh/flat1559. No Arrow 22.",
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

    print(f"pass 1: 09:29 pre stats warmup+study n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow21_pre")
    prog.start_heartbeat()
    study_syms: set[str] = set()
    for iso, mp in by_sess.items():
        if iso in {_iso(d) for d in study}:
            study_syms.update(mp)
    jobs = [(d, study_syms) for d in all_sess]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_session_pre, job): job[0] for job in jobs}
        for i, fut in enumerate(as_completed(futs), 1):
            iso, mp = fut.result()
            feat[iso] = mp
            prog.mark(iso, rows=len(mp))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    dv_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for sym, st in feat.get(iso, {}).items():
            dv_hist.setdefault(sym, []).append((iso, st["dv0929"]))

    study_set = {_iso(d) for d in study}
    hots_by_sess: dict[str, list[dict]] = {iso: [] for iso in study_set}
    prior_dv_by_sess: dict[str, dict[str, float]] = {iso: {} for iso in study_set}
    for d in study:
        iso = _iso(d)
        for sym, meta in by_sess.get(iso, {}).items():
            st = (feat.get(iso) or {}).get(sym)
            if not st:
                continue
            prior = [v for s, v in (dv_hist.get(sym) or []) if s < iso]
            med = median_prior_window(prior)
            if med is None:
                continue
            ext = st["last_px"] / meta["prior_close"] - 1.0
            rel = st["dv0929"] / med
            if not hot_gate(pre_dv=st["dv0929"], pre_dv_rel=rel, ext_0929=ext):
                continue
            hots_by_sess[iso].append(
                {
                    "symbol": sym,
                    "last_ts": st["last_ts"],
                    "last_px": st["last_px"],
                    "sess_low": st["sess_low"],
                    "sess_high": st["sess_high"],
                    "pre_dv": st["dv0929"],
                    "pre_dv_rel": rel,
                    "ext_0929": ext,
                }
            )
            prior_dv_by_sess[iso][sym] = meta["prior_dv"]

    replay_jobs = [
        (_iso(d), hots_by_sess[_iso(d)], prior_dv_by_sess[_iso(d)]) for d in develop + holdout
    ]
    print(
        f"pass 2: replay {len(replay_jobs)} sessions; "
        f"hot name-days develop={sum(len(hots_by_sess[_iso(d)]) for d in develop)} "
        f"holdout={sum(len(hots_by_sess[_iso(d)]) for d in holdout)}",
        flush=True,
    )
    prog2 = Progress(len(replay_jobs), "arrow21")
    prog2.start_heartbeat()
    chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in replay_jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            chunks.append(chunk)
            prog2.mark(chunk["session"], rows=chunk["n_hot"])
            if i % 8 == 0:
                prog2.heartbeat()
    prog2.stop_heartbeat()
    prog2.heartbeat()
    _write_reports(chunks, hots_by_sess, workers, cpu, develop, holdout)
    return 0


def _write_reports(chunks, hots_by_sess, workers, cpu, develop, holdout) -> None:
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    rows = [r for c in chunks for r in c["rows"]]
    hot_dev = [len(hots_by_sess[_iso(d)]) for d in develop]
    hot_hol = [len(hots_by_sess[_iso(d)]) for d in holdout]

    def _hot_line(label, xs):
        if not xs:
            return f"{label}: n=0"
        return (
            f"{label}: n_sess={len(xs)} total={sum(xs)} mean={sum(xs)/len(xs):.2f} "
            f"median={statistics.median(xs):.1f} max={max(xs)}"
        )

    results = []
    for exp_id in IDS:
        subset = [r for r in rows if r["name"] == exp_id]
        pnl_map = {r["session"]: r for r in subset}
        daily_dev = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in develop]
        daily_hol = [pnl_map.get(_iso(d), {}).get("pnl", 0.0) for d in holdout]
        tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
        tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
        results.append(
            {
                "name": exp_id,
                "develop": _summarize(daily_dev, tr_dev, len(develop)),
                "holdout": _summarize(daily_hol, tr_hol, len(holdout)),
            }
        )

    def _promotable(r) -> bool:
        return r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0

    promo = [r for r in results if _promotable(r)]
    false_green = [
        r for r in results if r["holdout"]["clears_200"] and r["develop"]["per_day"] < 0
    ]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(
            r["name"] for r in promo
        )
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 21 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass. Did not rerun strong5/newhigh/flat1559."
        )

    lines = [
        "Arrow 21 — iterate the 09:29 hot book after Arrow 20 washout (data/full)",
        verdict,
        "Same 09:29 hot gate unless an id tightens it. Ids 1-5 long; id 6 short contrast.",
        "Did not rerun Arrow 20 strong5 / newhigh / flat1559. No B-short rescore. "
        "Did not touch data/bars. No Track B cap. No Arrow 22.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}",
        "Hot gate at 09:29: prior_close [$1,$20], pre_dv>=250k, pre_dv_rel>=3, ext in [0.03, 0.15).",
        "id3 tightens ext to [0.03, 0.08). id4 tightens pre_dv>=1M. cap8=8/16/1600 except "
        "id5 max_positions=3. RISK_PER_IDEA=200. Fills=next tradeable open. Leak-fixed flatten 11:59.",
        "",
        _hot_line("hot name-days develop", hot_dev),
        _hot_line("hot name-days holdout", hot_hol),
        "develop hot/session:",
    ]
    for d in develop:
        lines.append(f"  {_iso(d)} {len(hots_by_sess[_iso(d)])}")
    lines.append("holdout hot/session:")
    for d in holdout:
        lines.append(f"  {_iso(d)} {len(hots_by_sess[_iso(d)])}")
    lines.append("")
    lines.append(
        f"{'id':<16} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} "
        f"{'hit':>6} {'avgR':>7} {'t_hold':>7} {'ci95 hold':>22} {'>=200':>6}"
    )
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        ci = f"[{h['ci_lo']:.1f},{h['ci_hi']:.1f}]"
        lines.append(
            f"{r['name']:<16} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} {h['t_stat']:7.2f} "
            f"{ci:>22} {flag:>6}"
        )
        lines.append(f"       develop {_fmt(r['develop'], holdout=False)}")
        lines.append(f"       holdout {_fmt(r['holdout'], holdout=True)}")
    if false_green:
        lines.append("")
        lines.append("NO* = holdout >= $200 but develop is red — not a pass:")
        for r in false_green:
            lines.append(
                f"  {r['name']}: develop {r['develop']['per_day']:.2f}/day "
                f"holdout {r['holdout']['per_day']:.2f}/day"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow21_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 21",
        "",
        verdict,
        "",
        "Same 09:29 hot gate as Arrow 20 (prior_close $1-20, pre_dv>=250k, pre_dv_rel>=3, "
        "ext in [3%, 15)). Six ids: pullback to 09:29 px or RTH VWAP; 09:30 open only if "
        "open <= +1% vs 09:29; tighter ext [3%, 8%); pre_dv>=1M 09:30 open; pullback with "
        "max_positions=3; short the 09:30 open of the same hot names. Flatten 11:59. "
        "Did not rerun strong5/newhigh/flat1559. Did not rescore the B-short. Did not "
        "touch data/bars. No Arrow 22.",
        "",
        _hot_line("hot develop", hot_dev),
        _hot_line("hot holdout", hot_hol),
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day trades_holdout={r['holdout']['n_trades']} "
            f"avgR={r['holdout']['avg_r']:.3f} t={r['holdout']['t_stat']:.2f}."
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
