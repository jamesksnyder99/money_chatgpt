"""Arrow 78 — open leftover complement, overlap, gap. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _clock, load_combined_iwm
from research.arrow44 import MIN_PDV, MIN_PX, MAX_PX, _by_sess, _iwm_last_close, _month_lines
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow47 import _short_n
from research.arrow48 import _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import LB, MIN_RESIDUAL, N_SHORT
from research.arrow57 import _fmt_book57, select_winners
from research.arrow65 import _last_job, _make_trade, _mtm_and_peak, _rank_job
from research.arrow66 import FILL_KIND
from research.arrow74 import NOTIONAL, _elig_janfeb, peak_live_intraday
from research.arrow76 import EXIT_1029, FILL_0931, LEFT_LB, N8, _extract_job, pick_exit
from research.arrow77 import H10_HOLD, H10_NOTIONAL, h10_live_at_0930
from research.book import daily_close_drawdown
from research.clock import (
    arrow76_feature_sessions,
    arrow76_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO
from research.signals import RTH_OPEN

ET = ZoneInfo("America/New_York")
CONTROL_ID = "all_0930"
CAUSAL_ID = "all_0931"
A76_ODD = 125.39
REPRINT_TOL = 0.15
# name, fill_kind (0930/0931), filt
EXPERIMENTS = (
    ("all_0930", "0930", "all"),
    ("all_0931", "0931", "all"),
    ("complement", "0931", "complement"),
    ("overlap_only", "0931", "overlap"),
    ("gap_up", "0931", "gap_up"),
    ("gap_dn", "0931", "gap_dn"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def fill_stamp(kind: str) -> time:
    """Id 1 fill is ≥ 09:31, not 09:30. Id 0 reprint stays 09:30."""
    if kind == "0931":
        return FILL_0931
    return RTH_OPEN


def filter_eight(eight: list[dict], filt: str, live: set[str]) -> list[dict]:
    """Do not backfill with names outside the leftover eight."""
    if filt == "all":
        return list(eight)
    if filt == "complement":
        return [r for r in eight if r["symbol"] not in live]
    if filt == "overlap":
        return [r for r in eight if r["symbol"] in live]
    if filt == "gap_up":
        return [r for r in eight if r.get("gap") is not None and r["gap"] >= 0.0]
    if filt == "gap_dn":
        return [r for r in eight if r.get("gap") is not None and r["gap"] < 0.0]
    return []


def pick_fill(today: dict, kind: str) -> tuple | None:
    if kind == "0931":
        return today.get("fill0931")
    return today.get("fill")


def gap_of(today: dict, prior_last: float | None) -> float | None:
    """Gap = 09:30 first print / prior last-RTH − 1. None if no 09:30 print."""
    px = today.get("fill")
    if px is None or prior_last is None or prior_last <= 0:
        return None
    if _clock(px[0]) >= FILL_0931:
        return None
    return float(px[1]) / float(prior_last) - 1.0


def run_arrow78(*, workers: int | None = None) -> int:
    sess = arrow76_sessions()
    feats = arrow76_feature_sessions()
    leftover = feature_sessions()
    if any(d.month >= 5 for d in sess):
        raise RuntimeError("Arrow 78 must not score May–August")
    if any(tape_root(d) == BARS_DIR for d in (date(2026, 1, 2), date(2026, 4, 30))):
        raise RuntimeError("Arrow 78 must not read Lab A data/bars/")
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    if FILL_KIND != "nextrth":
        raise RuntimeError("Arrow 78 must not retune Wednesday H10 fill")
    odd = [d for d in sess if is_is_session(d)]
    even = [d for d in sess if not is_is_session(d)]
    by_month: dict[str, list[date]] = {}
    for d in sess:
        by_month.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(d)
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    print(
        f"research start mode=arrow78 workers={workers} cpu={cpu} "
        f"window={sess[0]}..{sess[-1]} n={len(sess)} odd n={len(odd)} even n={len(even)} "
        f"day_feats={feats[0]}..{feats[-1]} leftover={leftover[0]}.. "
        f"jan_tape={tape_root(date(2026, 1, 2))} apr_tape={tape_root(date(2026, 4, 30))}",
        flush=True,
    )
    print(
        "Open leftover complement / overlap / gap. Short only. "
        "Did not retune Wednesday H10. Did not change the 10:29 exit. "
        "Fill 09:31 for filters so the gap is known. Did not use April to pick a filter. "
        "No new ingest. No Arrow 79.",
        flush=True,
    )
    elig = _elig_janfeb(sess)
    by = _by_sess(elig)
    need: set[tuple[str, str]] = set()
    for d in sess:
        for h in by.get(d.isoformat(), []):
            sym = h["symbol"]
            need.add((d.isoformat(), sym))
            t1 = session_shift(d, -1, feats)
            t16 = session_shift(d, -LEFT_LB - 1, feats)
            if t1 is not None:
                need.add((t1.isoformat(), sym))
            if t16 is not None:
                need.add((t16.isoformat(), sym))
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"left={LEFT_LB} parent n={N8} ${NOTIONAL:.0f} extract_jobs={len(need)}",
        flush=True,
    )
    cache: dict[tuple[str, str], dict] = {}
    prog = Progress(len(need), "arrow78")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_extract_job, job) for job in sorted(need)]
        for i, fut in enumerate(as_completed(futs), 1):
            iso, symbol, got = fut.result()
            if got is not None:
                cache[(iso, symbol)] = got
            prog.mark(str(i), rows=1)
            if i % 64 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    # Frozen Wednesday H10 (signal Wednesday, nextrth fill, hold 10, $4k).
    iwm = load_combined_iwm()
    h10_jobs = []
    h10_weds: list[date] = []
    for d in leftover:
        if d.weekday() != 2 or d > sess[-1]:
            continue
        look15 = session_shift(d, -LB, leftover)
        if look15 is None:
            continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
        h10_weds.append(d)
        h10_jobs.append(
            (
                d.isoformat(),
                look15.isoformat(),
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"H10 Wednesday nextrth hold={H10_HOLD} ${H10_NOTIONAL:.0f} drop-missing "
        f"weds={len(h10_jobs)} (did not retune)",
        flush=True,
    )
    recs: dict[str, dict] = {}
    if h10_jobs:
        prog_h = Progress(len(h10_jobs), "arrow78-h10")
        prog_h.start_heartbeat()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_rank_job, job) for job in h10_jobs]
            for i, fut in enumerate(as_completed(futs), 1):
                rec = fut.result()
                recs[rec["session"]] = rec
                prog_h.mark(rec["session"], rows=1)
        prog_h.stop_heartbeat()
        prog_h.heartbeat()

    h10_trades: list[dict] = []
    for d in h10_weds:
        rec = recs.get(d.isoformat()) or {}
        rows = list(rec.get("rows") or [])
        if (rec.get("n_res") or 0) < MIN_RESIDUAL:
            continue
        picks = select_shorts(rows, N_SHORT, None)
        for h in picks:
            tr, skip_fill, _partial = _make_trade(
                h, FILL_KIND, H10_NOTIONAL, False, d, leftover, hold=H10_HOLD
            )
            if skip_fill or tr is None:
                continue
            h10_trades.append(tr)

    need_h10: set[tuple[str, str]] = set()
    mtm_sess = [d for d in leftover if d <= sess[-1]]
    for t in h10_trades:
        fill_d, exit_d = t["fill_date"], t["exit_date"]
        for d in mtm_sess:
            if fill_d <= d < exit_d:
                need_h10.add((d.isoformat(), t["symbol"]))
    last_map: dict[tuple[str, str], float] = {}
    if need_h10:
        prog_m = Progress(len(need_h10), "arrow78-h10-mtm")
        prog_m.start_heartbeat()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_last_job, job) for job in sorted(need_h10)]
            for i, fut in enumerate(as_completed(futs), 1):
                iso, symbol, px = fut.result()
                if px is not None:
                    last_map[(iso, symbol)] = px
                prog_m.mark(str(i), rows=1)
        prog_m.stop_heartbeat()
        prog_m.heartbeat()
    mtm_all, _peak_h10 = _mtm_and_peak(h10_trades, mtm_sess, last_map)
    mtm_idx = {d: i for i, d in enumerate(mtm_sess)}
    h10_daily = [mtm_all[mtm_idx[d]] if d in mtm_idx else 0.0 for d in sess]

    live_h10: dict[str, set[str]] = {d.isoformat(): set() for d in sess}
    for t in h10_trades:
        for d in sess:
            if h10_live_at_0930(t["fill_date"], t["exit_date"], d):
                live_h10[d.isoformat()].add(t["symbol"])

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in sess
    }
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    char_n: dict[str, list[int]] = {k: [] for k in ("complement", "overlap_only", "gap_up", "gap_dn")}

    for d in sess:
        names = by.get(d.isoformat(), [])
        keyed = []
        live = live_h10.get(d.isoformat()) or set()
        for h in names:
            today = cache.get((d.isoformat(), h["symbol"]))
            if today is None or today.get("fill") is None:
                continue
            t1 = session_shift(d, -1, feats)
            t16 = session_shift(d, -LEFT_LB - 1, feats)
            left = None
            prior_last = None
            if t1 is not None and t16 is not None:
                a = cache.get((t1.isoformat(), h["symbol"]))
                b = cache.get((t16.isoformat(), h["symbol"]))
                if (
                    a
                    and b
                    and a.get("last_rth")
                    and b.get("last_rth")
                    and b["last_rth"][1] > 0
                ):
                    left = a["last_rth"][1] / b["last_rth"][1] - 1.0
                    prior_last = a["last_rth"][1]
            if left is None:
                continue
            keyed.append({**h, "today": today, "left": left, "gap": gap_of(today, prior_last)})
        chunks[d.isoformat()]["n_res"] = len(keyed)
        if len(keyed) < N8:
            if d in odd:
                for k in char_n:
                    char_n[k].append(0)
            continue
        eight = select_winners(keyed, N8, "left")
        for name, fkind, filt in EXPERIMENTS:
            picks = filter_eight(eight, filt, live)
            if d in odd and name in char_n:
                char_n[name].append(len(picks))
            if not picks:
                continue
            for row in picks:
                today = row["today"]
                ent = pick_fill(today, fkind)
                ex = pick_exit(today, "1029")
                if ent is None or ex is None:
                    continue
                if ent[0] > ex[0]:
                    continue
                if fkind == "0931" and _clock(ent[0]) < FILL_0931:
                    continue
                tr = _short_n(row, ent, ex, name, NOTIONAL)
                if tr is None:
                    continue
                if tr["side"] != -1:
                    raise RuntimeError("Arrow 78 must be short-only")
                if filt == "complement" and row["symbol"] in live:
                    raise RuntimeError("complement shorted an H10-live name")
                if filt == "overlap" and row["symbol"] not in live:
                    raise RuntimeError("overlap_only shorted a name not on H10")
                tr["signal"] = d
                tr["fill_date"] = d
                tr["exit_date"] = d
                tr["exit_partial"] = _clock(ex[0]) != EXIT_1029
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                trades_all[name].append(tr)

    def _score(name: str, slice_sess: list[date]) -> dict:
        mset = set(slice_sess)
        weeks = sorted({t["signal"] for t in trades_all[name] if t["signal"] in mset})
        sm, daily, tr = _daily_and_trades(chunks, slice_sess, name, weeks)
        sm["n_win"], sm["n_loss"] = _wins_losses(tr)
        sm["daily_close_dd"] = daily_close_drawdown(daily)
        sm["worst_day"] = min(daily) if daily else 0.0
        return {
            "sm": sm,
            "tr": tr,
            "daily": daily,
            "peak": peak_live_intraday(tr),
            "n_sess": len(slice_sess),
            "months": _month_lines(daily, slice_sess),
        }

    results = []
    for name, fkind, filt in EXPERIMENTS:
        odd_s = _score(name, odd)
        even_s = _score(name, even)
        months = {key: _score(name, days_m) for key, days_m in sorted(by_month.items())}
        results.append(
            {
                "name": name,
                "fill": fkind,
                "filt": filt,
                "odd": odd_s,
                "even": even_s,
                "months": months,
                "peak_all": peak_live_intraday(trades_all[name]),
            }
        )

    parent = next(r for r in results if r["name"] == CONTROL_ID)
    causal = next(r for r in results if r["name"] == CAUSAL_ID)
    odd_day = parent["odd"]["sm"]["per_day"]
    reprint_ok = _within(odd_day, A76_ODD, REPRINT_TOL)
    reprint_line = (
        f"Id 0 {CONTROL_ID} odd $/day={odd_day:.2f} vs Arrow 76/77 parent {A76_ODD:.2f} "
        f"n={parent['odd']['sm']['n_trades']} "
        + ("— within ±15%." if reprint_ok else "— DRIFT beyond ±15%. Stop and fix.")
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        raise RuntimeError(reprint_line)

    def _mean_n(xs: list[int]) -> float:
        return (sum(xs) / len(xs)) if xs else 0.0

    mean_comp = _mean_n(char_n["complement"])
    mean_ov = _mean_n(char_n["overlap_only"])
    mean_up = _mean_n(char_n["gap_up"])
    mean_dn = _mean_n(char_n["gap_dn"])

    _, comp_daily, _ = _daily_and_trades(
        chunks, sess, "complement", sorted({t["signal"] for t in trades_all["complement"]})
    )
    def _corr_slice(slice_sess: list[date], day_daily: list[float]) -> tuple[float, int]:
        xs, ys = [], []
        sset = set(slice_sess)
        for d, a, b in zip(sess, day_daily, h10_daily):
            if d not in sset:
                continue
            xs.append(float(a))
            ys.append(float(b))
        return _pearson(xs, ys), len(xs)

    corr_odd, n_co = _corr_slice(odd, comp_daily)
    corr_even, n_ce = _corr_slice(even, comp_daily)
    comp = next(r for r in results if r["name"] == "complement")
    ovl = next(r for r in results if r["name"] == "overlap_only")
    gup = next(r for r in results if r["name"] == "gap_up")
    gdn = next(r for r in results if r["name"] == "gap_dn")
    comp_green_both = comp["odd"]["sm"]["per_day"] > 0 and comp["even"]["sm"]["per_day"] > 0
    low_corr = abs(corr_odd) < 0.5 and abs(corr_even) < 0.5
    pulse = "yes" if (low_corr and comp_green_both) else "no"

    def _lifts_causal(r: dict) -> bool:
        return (
            r["odd"]["sm"]["per_day"] > causal["odd"]["sm"]["per_day"]
            and r["even"]["sm"]["per_day"] > causal["even"]["sm"]["per_day"]
        )

    beat = [r["name"] for r in results if r["name"] not in {CONTROL_ID, CAUSAL_ID} and _lifts_causal(r)]
    first_para = (
        f"{reprint_line} 09:31 vs 09:30: odd ${causal['odd']['sm']['per_day']:.2f} vs "
        f"${parent['odd']['sm']['per_day']:.2f}; even ${causal['even']['sm']['per_day']:.2f} vs "
        f"${parent['even']['sm']['per_day']:.2f}. Complement is the second pulse "
        f"(low corr, both slices green): {pulse} "
        f"(corr odd={corr_odd:.3f} even={corr_even:.3f}; "
        f"odd ${comp['odd']['sm']['per_day']:.2f} even ${comp['even']['sm']['per_day']:.2f}). "
        f"gap_up odd ${gup['odd']['sm']['per_day']:.2f} even ${gup['even']['sm']['per_day']:.2f} vs "
        f"gap_dn odd ${gdn['odd']['sm']['per_day']:.2f} even ${gdn['even']['sm']['per_day']:.2f}. "
        f"Filters that lift both vs id 1: {', '.join(beat) if beat else 'none'}."
    )
    sniff = (
        "VERDICT: SNIFF — complement / overlap / gap on four months is still a sniff for promotion. "
        "Did not use April to pick a filter. Did not treat this window as a $200 slate pass. "
        "Did not score May–August."
    )
    honesty = (
        "Frozen chassis: 15-session leftover rank, fill first print ≥ 09:30 (id 0 reprint) or "
        "≥ 09:31 (ids 1–5), exit last print at 10:29, $3,000. Short only. Did not retune "
        "Wednesday H10. Did not change the 10:29 exit. Gap = 09:30 first print / prior last-RTH "
        "− 1; fill 09:31 so the gap is known. Complement = leftover eight minus H10 live at 09:30. "
        "Overlap = leftover eight intersect H10 live. Do not backfill. A filter beats id 1 only if "
        "it lifts $/day on both odd and even. Do not call a CI that includes 0 EV. "
        "No new ingest. Did not touch Lab A data/bars/. No Arrow 79."
    )
    char_lines = [
        "CHARACTER odd-only mean n per session. Description. Does not pick an id. "
        "Did not use April to pick a filter.",
        f"  complement mean n={mean_comp:.3f}  overlap_only mean n={mean_ov:.3f}  "
        f"gap_up mean n={mean_up:.3f}  gap_dn mean n={mean_dn:.3f}  odd sessions={len(odd)}.",
        f"  complement vs H10 MTM daily Pearson: odd={corr_odd:.3f} n={n_co}  "
        f"even={corr_even:.3f} n={n_ce}. second pulse={pulse}.",
        f"  H10 trades n={len(h10_trades)} weds_ranked={len(h10_weds)}. "
        f"H10 fill is nextrth last-RTH, not the day-book 09:30/09:31 fill.",
    ]
    print("\n".join(char_lines), flush=True)

    lines = [
        "Arrow 78 — open leftover: complement, overlap, gap",
        first_para,
        sniff,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"window n={len(sess)} {sess[0]}..{sess[-1]}  odd n={len(odd)}  even n={len(even)}  "
        f"(May not scored)",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"apr_tape={tape_root(date(2026, 4, 30))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"left={LEFT_LB} n={N8} ${NOTIONAL:.0f} exit=10:29  H10 nextrth hold={H10_HOLD} ${H10_NOTIONAL:.0f}",
        "Peak live = |shares × entry| (same-session day book). "
        "$/day = total PnL / NYSE sessions in that slice. Odd=Jan+Mar IS. Even=Feb+Apr OOS.",
        "",
        *char_lines,
        "",
        f"{'id':<14} {'slice':<7} {'$/day':>9} {'n':>6} {'hit':>6} {'t':>6}",
    ]

    def _emit(r: dict, label: str, pack: dict) -> None:
        sm = pack["sm"]
        lines.append(
            f"{r['name']:<14} {label:<7} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
            f"{sm['hit_rate']:6.3f} {sm['t_stat']:6.2f}"
        )
        lines.extend(_fmt_book57(sm))
        ci_ex = sm["ci_lo"] > 0 or sm["ci_hi"] < 0
        lines.append(
            f"    $/day={sm['per_day']:.2f} (total PnL / n={pack['n_sess']} sessions)  "
            f"fill={r['fill']} filt={r['filt']} ${NOTIONAL:.0f}  peak live ${pack['peak']:.0f}  "
            f"all ${r['peak_all']:.0f}{_ci_note(sm)}"
        )
        lines.append(f"    months: {pack['months']}")
        if ci_ex:
            lines.append(f"    {label} CI excludes 0.")
        else:
            lines.append(f"    {label} CI includes 0 — not EV.")

    for r in results:
        _emit(r, "odd", r["odd"])
        _emit(r, "even", r["even"])
        for key, pack in r["months"].items():
            _emit(r, key, pack)
    lines.append(
        f"    Filters that lift both odd and even vs id 1 {CAUSAL_ID}: "
        f"{', '.join(beat) if beat else 'none'}. Did not use April to pick a filter. "
        "Still a sniff, not a seat. No Arrow 79."
    )
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow78_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow78_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 78",
        "",
        first_para,
        "",
        sniff,
        f"all_0930 odd ${parent['odd']['sm']['per_day']:.2f} n={parent['odd']['sm']['n_trades']}  "
        f"even ${parent['even']['sm']['per_day']:.2f}. "
        f"all_0931 odd ${causal['odd']['sm']['per_day']:.2f} even ${causal['even']['sm']['per_day']:.2f}. "
        f"complement odd ${comp['odd']['sm']['per_day']:.2f} even ${comp['even']['sm']['per_day']:.2f} "
        f"corr odd={corr_odd:.3f} even={corr_even:.3f}. "
        "Did not use April to pick a filter. No Arrow 79.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 78"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
