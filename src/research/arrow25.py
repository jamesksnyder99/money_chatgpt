from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import FULL_ELIGIBILITY, FULL_BARS, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow20 import PRICE_HI, PRICE_LO, _iso, _read_hot_bars
from research.arrow23 import _fmt_adv, _pack_trades, _summarize_adv
from research.arrow24 import _session_scan
from research.book import replay_session
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.harness import PRICE_FLOOR_PX5, run_rel_vol, run_rel_vol_at
from research.signals import MINUTE_1000, MINUTE_1159, MINUTE_1559
from research.split import develop_holdout
from research.strategies22 import hot_gate_0800
from research.strategies25 import fly_cell_ok, flush_ring_long, score_flush

ET = ZoneInfo("America/New_York")

CAP8 = {
    "max_positions": 8,
    "max_entries": 16,
    "max_risk_outstanding": 1600.0,
    "min_stop_frac": 0.004,
    "harness_stop": True,
    "cost_gate": True,
}
CAP3 = {
    **CAP8,
    "max_positions": 3,
    "max_risk_outstanding": 600.0,
}

# (id, flush_kwargs, flatten, cap, use_cell, half1r, min_rel)
EXPERIMENTS = (
    ("flush|ctrl", {}, MINUTE_1159, CAP8, True, False, None),
    ("flush|cap3", {}, MINUTE_1159, CAP3, True, False, None),
    ("flush|flat1559", {}, MINUTE_1559, CAP8, True, False, None),
    ("flush|half1R", {}, MINUTE_1559, CAP8, True, True, None),
    ("flush|deep3", {"min_undercut": 0.03}, MINUTE_1159, CAP8, True, False, None),
    ("flush|max6", {"max_undercut": 0.06}, MINUTE_1159, CAP8, True, False, None),
    (
        "flush|reclaim",
        {"min_close_loc": 0.85, "reclaim_0800": True},
        MINUTE_1159,
        CAP8,
        True,
        False,
        None,
    ),
    ("flush|after10", {"flush_after": MINUTE_1000}, MINUTE_1159, CAP8, True, False, None),
    ("flush|rel5", {}, MINUTE_1159, CAP8, True, False, 5.0),
    ("flush|nocell", {}, MINUTE_1159, CAP8, False, False, None),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
CONTROL = IDS[0]


def _replay_one(args: tuple) -> dict:
    iso, names, prior_dv, dv_hist = args
    session = date.fromisoformat(iso)
    empty = {
        "session": iso,
        "n_cand": len(names),
        "rows": [{"session": iso, "name": n, "pnl": 0.0, "trades": []} for n in IDS],
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
        score = float(h.get("rel0800") or h.get("rel0929") or 1.0)
        prior_cum = [arr for s, arr in (dv_hist.get(h["symbol"]) or []) if s < iso][-10:]
        in_cell = fly_cell_ok(h.get("orw"), h.get("dv0929"), h.get("ext0944"))
        for exp_id, fkw, _flat, _cap, use_cell, _half, min_rel in EXPERIMENTS:
            if use_cell and not in_cell:
                continue
            sigs = flush_ring_long(sdf, h.get("px0800"), tag=exp_id, **fkw)
            if not sigs:
                continue
            if min_rel is not None:
                keep = []
                for s in sigs:
                    rel = run_rel_vol_at(h["cumdv"], s.signal_ts, prior_cum)
                    if rel is not None and rel >= min_rel - 1e-12:
                        keep.append(s)
                sigs = keep
            for s in sigs:
                if s.side != 1:
                    continue
                by_id[exp_id].append(score_flush(s, score))
    rows = []
    cost_skips = 0
    for exp_id, _fkw, flatten, cap, _use_cell, half, _min_rel in EXPERIMENTS:
        sigs = by_id[exp_id]
        need = {s.symbol for s in sigs}
        sub = {k: bars[k] for k in need if k in bars}
        st = {}
        kw = dict(cap)
        kw["flatten_at"] = flatten
        if half:
            kw["scale_half_at_1r"] = True
            kw["atr_trail"] = True
        trades = replay_session(sub, sigs, prior_dv, stats=st, **kw)
        cost_skips += int(st.get("cost_skips") or 0)
        rows.append(
            {
                "session": iso,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": _pack_trades(trades, bars),
            }
        )
    return {"session": iso, "n_cand": len(names), "rows": rows, "cost_skips": cost_skips}


def run_arrow25(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    study = study_sessions()
    all_sess = list(WARMUP_SESSIONS) + study
    print(
        f"research start mode=arrow25 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]} "
        f"tape={FULL_BARS}",
        flush=True,
    )
    print(
        "concentric rings on flush + FLY cell; harness on; long only; data/full. "
        "Did not rerun 100-grid, giveback, launch-catch, volfirst-as-hero, 08:00 open-buy, "
        "vs_iwm, climax. +146 is not EV. No Arrow 26.",
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

    print(f"pass 1: 08:00 hot + FLY cell stamps n={len(all_sess)}", flush=True)
    feat: dict[str, dict[str, dict]] = {}
    prog = Progress(len(all_sess), "arrow25_pre")
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
    dv8_hist: dict[str, list[tuple[str, float]]] = {}
    dv9_hist: dict[str, list[tuple[str, float]]] = {}
    for iso in [_iso(d) for d in all_sess]:
        for sym, st in feat.get(iso, {}).items():
            dv_hist.setdefault(sym, []).append((iso, st["cumdv"]))
            if st.get("dv0800") is not None:
                dv8_hist.setdefault(sym, []).append((iso, st["dv0800"]))
            if st.get("dv0929") is not None:
                dv9_hist.setdefault(sym, []).append((iso, st["dv0929"]))

    study_isos = {_iso(d) for d in study}
    for iso in [_iso(d) for d in all_sess]:
        for st in feat.get(iso, {}).values():
            prior8 = [v for s, v in (dv8_hist.get(st["symbol"]) or []) if s < iso]
            prior9 = [v for s, v in (dv9_hist.get(st["symbol"]) or []) if s < iso]
            st["rel0800"] = run_rel_vol(st.get("dv0800"), prior8)
            st["rel0929"] = run_rel_vol(st.get("dv0929"), prior9)
            ext8 = (st["px0800"] / st["prior_close"] - 1.0) if st.get("px0800") else None
            st["hot0800"] = hot_gate_0800(
                pre_dv=st.get("dv0800"), pre_dv_rel=st.get("rel0800"), ext_0800=ext8
            )

    feats_by_sess: dict[str, list[dict]] = {iso: [] for iso in study_isos}
    prior_dv_by_sess: dict[str, dict[str, float]] = {iso: {} for iso in study_isos}
    n_hot = n_cell = 0
    for d in study:
        iso = _iso(d)
        for st in feat.get(iso, {}).values():
            if st["prior_close"] < PRICE_FLOOR_PX5 - 1e-12:
                continue
            if not st.get("hot0800"):
                continue
            if st.get("rel0800") is None:
                continue
            feats_by_sess[iso].append(st)
            prior_dv_by_sess[iso][st["symbol"]] = st["prior_dv"]
            n_hot += 1
            if fly_cell_ok(st.get("orw"), st.get("dv0929"), st.get("ext0944")):
                n_cell += 1
    print(
        f"08:00 hot px5 name-days study={n_hot} of which FLY-cell={n_cell}",
        flush=True,
    )

    replay_jobs = [
        (_iso(d), feats_by_sess[_iso(d)], prior_dv_by_sess[_iso(d)], dv_hist)
        for d in develop + holdout
    ]
    print(f"pass 2: replay {len(replay_jobs)} sessions x {len(IDS)} longs", flush=True)
    prog2 = Progress(len(replay_jobs), "arrow25")
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
    _write_reports(chunks, workers, cpu, develop, holdout)
    return 0


def _write_reports(chunks, workers, cpu, develop, holdout) -> None:
    develop_set = {_iso(d) for d in develop}
    holdout_set = {_iso(d) for d in holdout}
    rows = [r for c in chunks for r in c["rows"]]
    cost_skips = sum(c.get("cost_skips") or 0 for c in chunks)

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
                "develop": _summarize_adv(daily_dev, tr_dev, len(develop)),
                "holdout": _summarize_adv(daily_hol, tr_hol, len(holdout)),
            }
        )
    ctrl = next(r for r in results if r["name"] == CONTROL)

    def _promotable(r) -> bool:
        return r["holdout"]["clears_200"] and r["develop"]["per_day"] >= 0

    promo = [r for r in results if _promotable(r)]
    beat_both = [
        r
        for r in results
        if r["name"] != CONTROL
        and r["develop"]["per_day"] > ctrl["develop"]["per_day"]
        and r["holdout"]["per_day"] > ctrl["holdout"]["per_day"]
    ]
    if promo:
        verdict = "VERDICT: HOLD OUT CLEARS $200 WITH NON-RED DEVELOP — " + ", ".join(
            r["name"] for r in promo
        )
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 25 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass. +146 holdout on Arrow 24 flush|flat1159|px5 "
            "is not EV."
        )

    lines = [
        "Arrow 25 — concentric rings on flush + FLY cell (data/full)",
        verdict,
        "Harness on (ATR/0.6pct stop floor, cost gate, ranked fill). Long only. "
        "Did not rerun the 100-grid, giveback, launch-catch, volfirst-as-hero, 08:00 open-buy, "
        "vs_iwm, climax. Did not touch data/bars. No Arrow 26.",
        "Reminder: Arrow 24 flush|flat1159|px5 holdout +146 is not expected value. "
        "Holdout is contaminated from earlier ring-picking on the B-short cell and was a peek on the FLY cell.",
        f"account=100000  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  failure_line={FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  cost_skips={cost_skips}",
        "Entry: 08:00 hot, >=2pct undercut of 08:00 last_px, 5-min higher-low + strong close. "
        "FLY cell (develop-locked): OR width>=5.1pct, pre_dv_0929>=98k, ext_0944>=3.4pct. "
        "Default prior_close [5,20], cap8, flatten 11:59, cost gate on.",
        "",
        f"{'id':<16} {'dev $/day':>10} {'hold $/day':>11} {'hold n':>7} {'n/ctrl':>7} "
        f"{'hit':>6} {'avgR':>7} {'PF':>6} {'t_hold':>7} {'1R':>6} {'>=200':>6}",
    ]
    n1_h = max(ctrl["holdout"]["n_trades"], 1)
    n1_d = max(ctrl["develop"]["n_trades"], 1)
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        if _promotable(r):
            flag = "BOTH"
        ratio = h["n_trades"] / n1_h
        lines.append(
            f"{r['name']:<16} {r['develop']['per_day']:10.2f} {h['per_day']:11.2f} "
            f"{h['n_trades']:7d} {ratio:7.2f} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} "
            f"{h['pf_s']:>6} {h['t_stat']:7.2f} {h['frac_1r']:6.3f} {flag:>6}"
        )
        lines.append("  develop")
        lines.extend(_fmt_adv(r["develop"]))
        lines.append("  holdout")
        lines.extend(_fmt_adv(r["holdout"]))
        lines.append(
            f"  n vs id1: develop {r['develop']['n_trades']}/{ctrl['develop']['n_trades']} "
            f"({r['develop']['n_trades']/n1_d:.2f}x)  "
            f"holdout {h['n_trades']}/{ctrl['holdout']['n_trades']} ({ratio:.2f}x)"
        )
    lines.append("")
    if beat_both:
        lines.append(
            "Beat control on both slices: " + ", ".join(r["name"] for r in beat_both)
        )
    else:
        lines.append("Beat control on both slices: none")
    lines.append(
        "NO* = holdout >= 200 but develop is red — not a pass. +146 is not EV."
    )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow25_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 25",
        "",
        verdict,
        "",
        "Ten longs on flush + FLY cell. Harness on. Did not rerun the 100-grid, giveback, "
        "launch-catch, volfirst-as-hero, 08:00 open-buy, vs_iwm, climax. +146 is not EV. "
        "No Arrow 26.",
        "",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: develop ${r['develop']['per_day']:.2f}/day "
            f"holdout ${r['holdout']['per_day']:.2f}/day n_hold={r['holdout']['n_trades']} "
            f"vs_id1={r['holdout']['n_trades']/n1_h:.2f}x avgR={r['holdout']['avg_r']:.3f} "
            f"hit={r['holdout']['hit_rate']:.3f} PF={r['holdout']['pf_s']} "
            f"t={r['holdout']['t_stat']:.2f}."
        )
    bits.append("")
    if beat_both:
        bits.append("Beat control on both slices: " + ", ".join(r["name"] for r in beat_both))
    else:
        bits.append("Beat control on both slices: none")
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
