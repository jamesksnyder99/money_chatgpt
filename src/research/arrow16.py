from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import WARMUP_SESSIONS, study_sessions
from ingest.paths import ELIGIBILITY, REPORTS, ensure_dirs
from ingest.progress import Progress
from research.arrow3 import _fmt, _read_session_bars, _split_by_symbol, _summarize
from research.arrow4 import _filter_track_a, _filter_track_b
from research.arrow5 import _maps_from_elig
from research.arrow10 import _build_bars15
from research.book import replay_session
from research.character import dv_ranks
from research.costs import FAILURE_LINE, TARGET_HI, TARGET_LO
from research.ema15 import ema_stack, stitch_15m
from research.fills import tradeable_mask
from research.split import develop_holdout
from research.strategies8 import opening_range
from research.strategies10 import session_gap
from research.strategies11 import short_kernel_pop
from research.strategies15 import c5_ema9_plus_memory, control_c5_ema9
from research.strategies16 import (
    c5_ema9_after_1000,
    c5_ema9_below_avwap,
    c5_ema9_expanding,
    c5_ema9_mem_avwap,
    c5_ema9_no_pre_rocket,
    c5_ema9_prior_morning_stop,
    c5_ema9_relvol,
    c5_ema9_three_down,
)

ET = ZoneInfo("America/New_York")

CAP8 = {"max_positions": 8, "max_entries": 16, "max_risk_outstanding": 1600.0}
EXPERIMENTS = (
    ("c5_ema9|cap8",),
    ("c5_ema9|mem",),
    ("c5_ema9|3down",),
    ("c5_ema9|avwap",),
    ("c5_ema9|rv3",),
    ("c5_ema9|pdhigh",),
    ("c5_ema9|1000",),
    ("c5_ema9|nopre",),
    ("c5_ema9|expand",),
    ("c5_ema9|mem_avwap",),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
CONTROL_ID = "c5_ema9|cap8"
SHORT_POP = {"dv_min": 0.80, "gap_min": 0.015, "or_w_min": 0.025}


def _stats_one(d: date) -> tuple[str, dict[str, float], dict[str, float]]:
    df = _read_session_bars(d)
    iso = d.isoformat()
    if df.height == 0:
        return iso, {}, {}
    ok = df.filter(tradeable_mask(df))
    if ok.height == 0:
        return iso, {}, {}
    g = ok.group_by("symbol").agg(
        pl.col("volume").fill_null(0).sum().alias("v"),
        pl.col("high").max().alias("hi"),
    )
    vols = {str(r["symbol"]): float(r["v"]) for r in g.iter_rows(named=True)}
    highs = {str(r["symbol"]): float(r["hi"]) for r in g.iter_rows(named=True)}
    return iso, vols, highs


def _prev_iso(session_iso: str, sess_order: list[str]) -> str | None:
    prev = None
    for iso in sess_order:
        if iso >= session_iso:
            break
        prev = iso
    return prev


def _short_ok(sig, stitched) -> bool:
    return sig.side == -1 and ema_stack(stitched, sig.signal_ts) == "short"


def _replay_one(args: tuple) -> dict:
    session_iso, track, elig_path, bars15, sess_order, vol_hist, session_highs = args
    session = date.fromisoformat(session_iso)
    elig_df = pl.read_parquet(elig_path).filter(pl.col("session_date") == session)
    empty_rows = [
        {"session": session_iso, "track": track, "name": n, "pnl": 0.0, "trades": []}
        for n in IDS
    ]
    if elig_df.height == 0:
        return {"rows": empty_rows}
    bars = _read_session_bars(session)
    if bars.height == 0:
        return {"rows": empty_rows}
    keep = set(elig_df["symbol"].to_list())
    bars = bars.filter(pl.col("symbol").is_in(list(keep)))
    by_sym = _split_by_symbol(bars)
    meta = {
        r["symbol"]: r
        for r in elig_df.select("symbol", "prior_close", "prior_dollar_volume").iter_rows(named=True)
    }
    prior_dv = {s: float(m["prior_dollar_volume"] or 0.0) for s, m in meta.items()}
    ranks = dv_ranks(prior_dv)
    prev_iso = _prev_iso(session_iso, sess_order)

    buckets: dict[str, list] = {n: [] for n in IDS}
    for sym, sdf in by_sym.items():
        m = meta.get(sym) or {}
        prior_c = m.get("prior_close")
        prior_c = float(prior_c) if prior_c is not None else None
        rank = ranks.get(sym, 0.0)
        rng = opening_range(sdf)
        or_w = rng[2] if rng else None
        or_high = rng[0] if rng else None
        gap = session_gap(sdf, prior_c)
        stitched = stitch_15m(sym, session_iso, sess_order, bars15)
        if not short_kernel_pop(rank, gap, or_w, **SHORT_POP) or or_high is None:
            continue
        hist = vol_hist.get(sym) or []
        prior_vols = [v for iso, v in hist if iso < session_iso]
        prior_hi = session_highs.get((sym, prev_iso)) if prev_iso else None

        for sig in control_c5_ema9(sdf, stitched, or_high):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|cap8"].append(sig)
        for sig in c5_ema9_plus_memory(sdf, stitched, or_high):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|mem"].append(sig)
        for sig in c5_ema9_three_down(sdf, stitched, or_high):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|3down"].append(sig)
        for sig in c5_ema9_below_avwap(sdf, stitched, or_high):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|avwap"].append(sig)
        for sig in c5_ema9_relvol(sdf, stitched, or_high, prior_vols):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|rv3"].append(sig)
        for sig in c5_ema9_prior_morning_stop(sdf, stitched, or_high, prior_hi):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|pdhigh"].append(sig)
        for sig in c5_ema9_after_1000(sdf, stitched, or_high):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|1000"].append(sig)
        for sig in c5_ema9_no_pre_rocket(sdf, stitched, or_high, prior_c):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|nopre"].append(sig)
        for sig in c5_ema9_expanding(sdf, stitched, or_high):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|expand"].append(sig)
        for sig in c5_ema9_mem_avwap(sdf, stitched, or_high):
            if _short_ok(sig, stitched):
                buckets["c5_ema9|mem_avwap"].append(sig)

    rows = []
    for exp_id, in EXPERIMENTS:
        sigs = [s for s in buckets[exp_id] if s.side == -1]
        trades = replay_session(by_sym, sigs, prior_dv, **CAP8)
        rows.append(
            {
                "session": session_iso,
                "track": track,
                "name": exp_id,
                "pnl": sum(t.pnl for t in trades),
                "trades": [{"pnl": t.pnl, "win": t.pnl > 0, "risk": t.risk} for t in trades],
            }
        )
    return {"rows": rows}


def run_arrow16(*, workers: int | None = None) -> int:
    ensure_dirs()
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    develop, holdout = develop_holdout()
    all_sess = list(WARMUP_SESSIONS) + study_sessions()
    sess_order = [d.isoformat() for d in all_sess]
    print(
        f"research start mode=arrow16 workers={workers} cpu={cpu} "
        f"develop={develop[0]}..{develop[-1]} holdout={holdout[0]}..{holdout[-1]}",
        flush=True,
    )
    print(
        "cap8; id1=exact B/c5_ema9|cap8; ten shorts. RISK_PER_IDEA=200. "
        "No 09:31 early, no longs, no Q4, no cap10, no 11:30, no union. No Arrow 17.",
        flush=True,
    )
    elig_all = pl.read_parquet(ELIGIBILITY)
    a_path = ELIGIBILITY.parent / "eligibility_a.parquet"
    b_path = ELIGIBILITY.parent / "eligibility_b.parquet"
    if a_path.exists():
        track_a = pl.read_parquet(a_path)
    else:
        track_a = _filter_track_a(elig_all)
        track_a.write_parquet(a_path)
    if b_path.exists():
        track_b = pl.read_parquet(b_path)
        capped = True
    else:
        track_b, capped = _filter_track_b(elig_all)
        track_b.write_parquet(b_path)
    print(f"Track A rows={track_a.height} Track B rows={track_b.height}", flush=True)
    _pc, _dv = _maps_from_elig(elig_all)
    print("precompute 15m closes for ema15 stitch", flush=True)
    bars15 = _build_bars15(all_sess, workers)
    print(f"bars15 keys={len(bars15)}", flush=True)
    print("precompute window volume and session highs", flush=True)
    vol_hist: dict[str, list[tuple[str, float]]] = {}
    session_highs: dict[tuple[str, str], float] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_stats_one, d): d for d in all_sess}
        for fut in as_completed(futs):
            iso, vols, highs = fut.result()
            for sym, v in vols.items():
                vol_hist.setdefault(sym, []).append((iso, v))
            for sym, hi in highs.items():
                session_highs[(sym, iso)] = hi
    for sym in vol_hist:
        vol_hist[sym].sort(key=lambda x: x[0])
    print(f"vol_hist symbols={len(vol_hist)} session_highs={len(session_highs)}", flush=True)

    jobs = []
    for track, path in (("A", str(a_path)), ("B", str(b_path))):
        for d in develop + holdout:
            jobs.append((d.isoformat(), track, path, bars15, sess_order, vol_hist, session_highs))
    prog = Progress(len(jobs), "arrow16")
    prog.start_heartbeat()
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_replay_one, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            chunk = fut.result()
            rows.extend(chunk["rows"])
            prog.mark(chunk["rows"][0]["session"] if chunk["rows"] else "", rows=len(chunk["rows"]))
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()
    _write_reports(rows, workers, cpu, develop, holdout, capped)
    return 0


def _write_reports(rows, workers, cpu, develop, holdout, capped) -> None:
    develop_set = {d.isoformat() for d in develop}
    holdout_set = {d.isoformat() for d in holdout}
    results = []
    for track in ("A", "B"):
        for exp_id in IDS:
            subset = [r for r in rows if r["track"] == track and r["name"] == exp_id]
            pnl_map = {r["session"]: r for r in subset}
            daily_dev = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in develop]
            daily_hol = [pnl_map.get(d.isoformat(), {}).get("pnl", 0.0) for d in holdout]
            tr_dev = [t for iso, r in pnl_map.items() if iso in develop_set for t in r["trades"]]
            tr_hol = [t for iso, r in pnl_map.items() if iso in holdout_set for t in r["trades"]]
            n_d, n_h = len(develop), len(holdout)
            results.append(
                {
                    "track": track,
                    "name": exp_id,
                    "develop": _summarize(daily_dev, tr_dev, n_d),
                    "holdout": _summarize(daily_hol, tr_hol, n_h),
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
            f"{r['track']}/{r['name']}" for r in promo
        )
    else:
        verdict = (
            "VERDICT: FAIL — no Arrow 16 book has holdout >= $200/day AND non-red develop. "
            "Develop-red / holdout-green is not a pass."
        )

    ctrl = {
        trk: next(r for r in results if r["track"] == trk and r["name"] == CONTROL_ID)
        for trk in ("A", "B")
    }

    def _rat(n, b):
        if b <= 0:
            return "n/a"
        return f"{n / b:.2f}x"

    def _n_line(r) -> str:
        c = ctrl[r["track"]]
        hd, hh = c["develop"]["n_trades"], c["holdout"]["n_trades"]
        nd, nh = r["develop"]["n_trades"], r["holdout"]["n_trades"]
        return (
            f"  {r['track']}/{r['name']}: develop n={nd} vs id1 {hd} ({_rat(nd, hd)}) "
            f"holdout n={nh} vs id1 {hh} ({_rat(nh, hh)})"
        )

    beat_notes = []
    both_yes = []
    for r in results:
        if r["name"] == CONTROL_ID:
            continue
        c = ctrl[r["track"]]
        beat_dev = r["develop"]["per_day"] > c["develop"]["per_day"]
        beat_hol = r["holdout"]["per_day"] > c["holdout"]["per_day"]
        both = beat_dev and beat_hol
        line = (
            f"  {r['track']}/{r['name']}: develop ${r['develop']['per_day']:.2f} vs control "
            f"${c['develop']['per_day']:.2f} ({'BEATS' if beat_dev else 'no'}); "
            f"holdout ${r['holdout']['per_day']:.2f} vs control "
            f"${c['holdout']['per_day']:.2f} ({'BEATS' if beat_hol else 'no'}); "
            f"both_slices={'YES' if both else 'NO'}"
        )
        beat_notes.append(line)
        if both:
            both_yes.append(f"{r['track']}/{r['name']}")
    beat_verdict = (
        "Ids that beat control on BOTH slices: " + (", ".join(both_yes) if both_yes else "none")
    )

    lines = [
        "Arrow 16 — denser rings on the B-short kernel (short only)",
        verdict,
        f"account=$100000  target=${TARGET_LO:.0f}-${TARGET_HI:.0f}/day  failure_line=${FAILURE_LINE:.0f}/day",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        f"holdout n={len(holdout)} {holdout[0]}..{holdout[-1]}",
        f"workers={workers} cpu_count={cpu}  Track B cap file={capped}",
        "Pass = holdout >= $200/day AND develop not red. RISK_PER_IDEA=200. cap8=8/16/1600.",
        "Id 1 = exact B/c5_ema9|cap8 (5-min close below ema9 after 09:45, ema9<ema21).",
        "Did not rerun 09:31 early 1-min, Arrow 13/15 longs, Q4, cap10-as-idea, 11:30 flatten, or union.",
        "No Arrow 17.",
        "",
        "n vs id 1:",
    ]
    for r in results:
        lines.append(_n_line(r))
    lines.append("")
    lines.append("vs control on both slices:")
    lines.extend(beat_notes)
    lines.append(beat_verdict)
    if promo:
        lines.append("Clears $200 with non-red develop: " + ", ".join(
            f"{r['track']}/{r['name']}" for r in promo
        ))
    lines.append("")
    lines.append(
        f"{'track':<6} {'id':<20} {'dev $/day':>10} {'hold $/day':>11} "
        f"{'hold n':>7} {'hit':>6} {'avgR':>7} {'maxDD':>10} {'>=200':>6}"
    )
    for r in results:
        h = r["holdout"]
        flag = "YES" if h["clears_200"] else "NO"
        if h["clears_200"] and r["develop"]["per_day"] < 0:
            flag = "NO*"
        lines.append(
            f"{r['track']:<6} {r['name']:<20} {r['develop']['per_day']:10.2f} "
            f"{h['per_day']:11.2f} {h['n_trades']:7d} {h['hit_rate']:6.3f} {h['avg_r']:7.3f} "
            f"{h['max_dd']:10.2f} {flag:>6}"
        )
        lines.append(f"       develop {_fmt(r['develop'], holdout=False)}")
        lines.append(f"       holdout {_fmt(r['holdout'], holdout=True)}")
    if false_green:
        lines.append("")
        lines.append("NO* = holdout >= $200 but develop is red — not a pass:")
        for r in false_green:
            lines.append(
                f"  {r['track']}/{r['name']}: develop ${r['develop']['per_day']:.2f}/day "
                f"holdout ${r['holdout']['per_day']:.2f}/day"
            )
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow16_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 16",
        "",
        verdict,
        "",
        "Preserved B/c5_ema9|cap8 as id 1 (cap8, RISK_PER_IDEA=200). Ten shorts: control; "
        "memory; three down 5-min closes; close below AVWAP; rel vol >= 3x (rocket-scan "
        "full-window definition); stop = prior session morning high if above fill and >= 0.4%; "
        "first signal at/after 10:00; not a premarket +10% rocket; expanding 5-min range; "
        "memory+AVWAP. Did not rerun 09:31 early 1-min, Arrow 13/15 longs, Q4, cap10-as-idea, "
        "11:30 flatten, or union.",
        "",
        beat_verdict,
        "",
        "n vs id 1:",
    ]
    for r in results:
        bits.append(_n_line(r))
    bits.append("")
    bits.append("vs control on both slices:")
    bits.extend(beat_notes)
    bits.append("")
    bits.append("What died (holdout < $200, or holdout green with red develop):")
    for r in results:
        if _promotable(r):
            continue
        bits.append(
            f"- Track {r['track']} {r['name']} (short): "
            f"holdout ${r['holdout']['per_day']:.2f}/day develop ${r['develop']['per_day']:.2f}/day "
            f"trades_holdout={r['holdout']['n_trades']} avgR={r['holdout']['avg_r']:.3f}. "
            "Do not retry this exact (track, id) without a new costed reason."
        )
    if promo:
        bits.append("")
        bits.append("Promotable: " + ", ".join(f"{r['track']}/{r['name']}" for r in promo))
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else "# Research log\n\n"
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits) + "\n", encoding="utf-8")
