"""Arrow 77 — open leftover short: H10 overlap + weekdays. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
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
from research.arrow76 import EXIT_1029, LEFT_LB, N8, _extract_job, pick_exit
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

ET = ZoneInfo("America/New_York")
CONTROL_ID = "all"
A76_ODD = 125.39
REPRINT_TOL = 0.15
H10_HOLD = 10
H10_NOTIONAL = 4000.0
# name, weekday (None = every session)
EXPERIMENTS = (
    ("all", None),
    ("mon", 0),
    ("tue", 1),
    ("wed", 2),
    ("thu", 3),
    ("fri", 4),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
WD_NAME = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}


def h10_live_at_0930(fill_d: date, exit_d: date, session: date) -> bool:
    """H10 fills next last-RTH, so 09:30 on the fill session is before the fill."""
    return fill_d < session <= exit_d


def weekday_ok(wd: int | None, session: date) -> bool:
    if wd is None:
        return True
    return session.weekday() == wd


def run_arrow77(*, workers: int | None = None) -> int:
    sess = arrow76_sessions()
    feats = arrow76_feature_sessions()
    leftover = feature_sessions()
    if any(d.month >= 5 for d in sess):
        raise RuntimeError("Arrow 77 must not score May–August")
    if any(tape_root(d) == BARS_DIR for d in (date(2026, 1, 2), date(2026, 4, 30))):
        raise RuntimeError("Arrow 77 must not read Lab A data/bars/")
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    if FILL_KIND != "nextrth":
        raise RuntimeError("Arrow 77 must not retune Wednesday H10 fill")
    odd = [d for d in sess if is_is_session(d)]
    even = [d for d in sess if not is_is_session(d)]
    by_month: dict[str, list[date]] = {}
    for d in sess:
        by_month.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(d)
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    print(
        f"research start mode=arrow77 workers={workers} cpu={cpu} "
        f"window={sess[0]}..{sess[-1]} n={len(sess)} odd n={len(odd)} even n={len(even)} "
        f"day_feats={feats[0]}..{feats[-1]} leftover={leftover[0]}.. "
        f"jan_tape={tape_root(date(2026, 1, 2))} apr_tape={tape_root(date(2026, 4, 30))}",
        flush=True,
    )
    print(
        "Open leftover short at 09:30, exit 10:29. Short only. "
        "Did not retune Wednesday H10. Did not change the 10:29 exit. "
        "Did not use April to pick a weekday. No new ingest. No Arrow 78.",
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
    prog = Progress(len(need), "arrow77")
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

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in sess
    }
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    day_names: dict[str, list[str]] = {}

    for d in sess:
        names = by.get(d.isoformat(), [])
        keyed = []
        for h in names:
            today = cache.get((d.isoformat(), h["symbol"]))
            if today is None or today.get("fill") is None:
                continue
            t1 = session_shift(d, -1, feats)
            t16 = session_shift(d, -LEFT_LB - 1, feats)
            left = None
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
            if left is None:
                continue
            keyed.append({**h, "today": today, "left": left})
        chunks[d.isoformat()]["n_res"] = len(keyed)
        if len(keyed) < N8:
            day_names[d.isoformat()] = []
            continue
        picks = select_winners(keyed, N8, "left")
        day_names[d.isoformat()] = [row["symbol"] for row in picks]
        for name, wd in EXPERIMENTS:
            if not weekday_ok(wd, d):
                continue
            for row in picks:
                today = row["today"]
                ent = today.get("fill")
                ex = pick_exit(today, "1029")
                if ent is None or ex is None:
                    continue
                if ent[0] > ex[0]:
                    continue
                tr = _short_n(row, ent, ex, name, NOTIONAL)
                if tr is None:
                    continue
                if tr["side"] != -1:
                    raise RuntimeError("Arrow 77 must be short-only")
                tr["signal"] = d
                tr["fill_date"] = d
                tr["exit_date"] = d
                tr["exit_partial"] = _clock(ex[0]) != EXIT_1029
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                trades_all[name].append(tr)

    # Frozen Wednesday H10 on this window (signal Wednesday, nextrth fill, hold 10, $4k).
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
        prog_h = Progress(len(h10_jobs), "arrow77-h10")
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
        prog_m = Progress(len(need_h10), "arrow77-h10-mtm")
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

    def _overlap_stats(slice_sess: list[date]) -> dict:
        counts: list[int] = []
        fracs: list[float] = []
        n_live = 0
        for d in slice_sess:
            eight = day_names.get(d.isoformat()) or []
            if not eight:
                continue
            live = live_h10.get(d.isoformat()) or set()
            if live:
                n_live += 1
            n_ov = sum(1 for s in eight if s in live)
            counts.append(n_ov)
            fracs.append(n_ov / 8.0)
        mean_c = (sum(counts) / len(counts)) if counts else 0.0
        mean_f = (sum(fracs) / len(fracs)) if fracs else 0.0
        return {
            "n": len(counts),
            "mean_count": mean_c,
            "mean_frac": mean_f,
            "n_h10_live": n_live,
        }

    def _corr_slice(slice_sess: list[date], day_daily: list[float]) -> tuple[float, int]:
        xs = []
        ys = []
        sset = set(slice_sess)
        for d, a, b in zip(sess, day_daily, h10_daily):
            if d not in sset:
                continue
            xs.append(float(a))
            ys.append(float(b))
        n = len(xs)
        return _pearson(xs, ys), n

    def _score(name: str, slice_sess: list[date], fired: list[date]) -> dict:
        mset = set(slice_sess)
        weeks = sorted({t["signal"] for t in trades_all[name] if t["signal"] in mset})
        sm_slice, daily, tr = _daily_and_trades(chunks, slice_sess, name, weeks)
        sm_slice["n_win"], sm_slice["n_loss"] = _wins_losses(tr)
        sm_slice["daily_close_dd"] = daily_close_drawdown(daily)
        sm_slice["worst_day"] = min(daily) if daily else 0.0
        fired_weeks = [d for d in fired if d in mset]
        sm_fire, daily_f, tr_f = _daily_and_trades(chunks, fired_weeks, name, fired_weeks)
        sm_fire["n_win"], sm_fire["n_loss"] = _wins_losses(tr_f)
        sm_fire["daily_close_dd"] = daily_close_drawdown(daily_f)
        sm_fire["worst_day"] = min(daily_f) if daily_f else 0.0
        return {
            "sm": sm_slice,
            "fired": sm_fire,
            "tr": tr,
            "daily": daily,
            "peak": peak_live_intraday(tr),
            "n_sess": len(slice_sess),
            "n_fired": len(fired_weeks),
            "months": _month_lines(daily, slice_sess),
        }

    parent_daily_all = []
    sm_tmp, parent_daily_all, _ = _daily_and_trades(
        chunks, sess, CONTROL_ID, sorted({t["signal"] for t in trades_all[CONTROL_ID]})
    )
    ov_odd = _overlap_stats(odd)
    ov_even = _overlap_stats(even)
    corr_odd, n_odd = _corr_slice(odd, parent_daily_all)
    corr_even, n_even = _corr_slice(even, parent_daily_all)

    results = []
    for name, wd in EXPERIMENTS:
        fired_all = [d for d in sess if weekday_ok(wd, d)]
        odd_s = _score(name, odd, [d for d in fired_all if d in set(odd)])
        even_s = _score(name, even, [d for d in fired_all if d in set(even)])
        months = {key: _score(name, days_m, fired_all) for key, days_m in sorted(by_month.items())}
        results.append(
            {
                "name": name,
                "wd": wd,
                "odd": odd_s,
                "even": even_s,
                "months": months,
                "peak_all": peak_live_intraday(trades_all[name]),
            }
        )

    parent = next(r for r in results if r["name"] == CONTROL_ID)
    odd_day = parent["odd"]["sm"]["per_day"]
    reprint_ok = _within(odd_day, A76_ODD, REPRINT_TOL)
    reprint_line = (
        f"Id 0 {CONTROL_ID} odd $/day={odd_day:.2f} vs Arrow 76 h1029_n8 {A76_ODD:.2f} "
        f"n={parent['odd']['sm']['n_trades']} "
        + ("— within ±15%." if reprint_ok else "— DRIFT beyond ±15%. Stop and fix.")
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        raise RuntimeError(reprint_line)

    mean_ov = (ov_odd["mean_frac"] + ov_even["mean_frac"]) / 2.0 if (ov_odd["n"] and ov_even["n"]) else ov_odd["mean_frac"]
    same_names = mean_ov >= 0.5
    pulse = "same eight names" if same_names else "a second pulse"
    both_print = [
        r["name"]
        for r in results
        if r["name"] != CONTROL_ID
        and r["odd"]["sm"]["n_trades"] > 0
        and r["even"]["sm"]["n_trades"] > 0
    ]

    def _lifts_fired(r: dict) -> bool:
        return (
            r["odd"]["fired"]["per_day"] > parent["odd"]["fired"]["per_day"]
            and r["even"]["fired"]["per_day"] > parent["even"]["fired"]["per_day"]
        )

    beat = [r["name"] for r in results if r["name"] != CONTROL_ID and _lifts_fired(r)]
    first_para = (
        f"{reprint_line} Mean overlap vs H10 (live at 09:30) /8: odd={ov_odd['mean_frac']:.3f} "
        f"even={ov_even['mean_frac']:.3f}. Daily Pearson day-book vs H10 MTM: odd={corr_odd:.3f} "
        f"n={n_odd} even={corr_even:.3f} n={n_even}. Description: {pulse}. "
        f"Weekdays that print on both slices: {', '.join(both_print) if both_print else 'none'}. "
        f"Fired-day lift both vs id 0: {', '.join(beat) if beat else 'none'}."
    )
    sniff = (
        "VERDICT: SNIFF — weekday rings on four months are still a sniff for promotion. "
        "Did not use April to pick a weekday. Did not treat this window as a $200 slate pass. "
        "Did not score May–August."
    )
    honesty = (
        "Frozen day book: eight largest 15-session close-to-close, fill first print ≥ 09:30, "
        "exit last print at 10:29, $3,000. Short only. Did not retune Wednesday H10. "
        "Did not change the 10:29 exit. H10 = Wednesday signal, next last-RTH fill, $4,000, "
        "hold 10, drop missing exits. Split leftover lookback did not change (2025-12-17). "
        "A weekday beats id 0 only if it lifts $/day on both odd and even using the fired-day "
        "denominator. Do not call a CI that includes 0 EV. No new ingest. "
        "Did not touch Lab A data/bars/. No Arrow 78."
    )
    char_lines = [
        "CHARACTER id 0 vs H10. Description. Does not pick an id. Did not use April to pick a weekday.",
        f"  overlap count of the eight also on H10 live at 09:30: odd mean={ov_odd['mean_count']:.3f} "
        f"/8={ov_odd['mean_frac']:.3f} n={ov_odd['n']} h10_live_days={ov_odd['n_h10_live']}; "
        f"even mean={ov_even['mean_count']:.3f} /8={ov_even['mean_frac']:.3f} n={ov_even['n']} "
        f"h10_live_days={ov_even['n_h10_live']}.",
        f"  daily Pearson day-book PnL vs H10 MTM (sessions both exist): odd={corr_odd:.3f} n={n_odd}; "
        f"even={corr_even:.3f} n={n_even}. {pulse}.",
        f"  H10 trades n={len(h10_trades)} weds_ranked={len(h10_weds)}. "
        f"H10 fill is nextrth last-RTH, not the day-book 09:30 fill.",
    ]
    print("\n".join(char_lines), flush=True)

    lines = [
        "Arrow 77 — open leftover short: H10 overlap + weekdays",
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
        "$/day slice = total PnL / NYSE sessions in that slice. "
        "$/day fired = total PnL / sessions that weekday fired. Odd=Jan+Mar IS. Even=Feb+Apr OOS.",
        "",
        *char_lines,
        "",
        f"{'id':<8} {'slice':<7} {'slice$':>9} {'fired$':>9} {'n':>6} {'nf':>4} {'hit':>6} {'t':>6}",
    ]

    def _emit(r: dict, label: str, pack: dict) -> None:
        sm = pack["sm"]
        fr = pack["fired"]
        lines.append(
            f"{r['name']:<8} {label:<7} {sm['per_day']:9.2f} {fr['per_day']:9.2f} "
            f"{sm['n_trades']:6d} {pack['n_fired']:4d} {fr['hit_rate']:6.3f} {fr['t_stat']:6.2f}"
        )
        lines.extend(_fmt_book57(fr))
        ci_ex = fr["ci_lo"] > 0 or fr["ci_hi"] < 0
        lines.append(
            f"    slice $/day={sm['per_day']:.2f} (total / n={pack['n_sess']} sessions)  "
            f"fired $/day={fr['per_day']:.2f} (total / n={pack['n_fired']} fired)  "
            f"days={r['name']} exit=1029 ${NOTIONAL:.0f}  peak live ${pack['peak']:.0f}  "
            f"all ${r['peak_all']:.0f}{_ci_note(fr)}"
        )
        lines.append(f"    months: {pack['months']}")
        if ci_ex:
            lines.append(f"    {label} fired CI excludes 0.")
        else:
            lines.append(f"    {label} fired CI includes 0 — not EV.")

    for r in results:
        _emit(r, "odd", r["odd"])
        _emit(r, "even", r["even"])
        for key, pack in r["months"].items():
            _emit(r, key, pack)
    lines.append(
        f"    Weekdays that lift both odd and even on the fired-day denominator vs id 0: "
        f"{', '.join(beat) if beat else 'none'}. Did not use April to pick a weekday. "
        "Still a sniff, not a seat. No Arrow 78."
    )
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow77_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow77_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 77",
        "",
        first_para,
        "",
        sniff,
        f"all odd ${parent['odd']['sm']['per_day']:.2f} n={parent['odd']['sm']['n_trades']}  "
        f"even ${parent['even']['sm']['per_day']:.2f} n={parent['even']['sm']['n_trades']}. "
        f"overlap/8 odd={ov_odd['mean_frac']:.3f} even={ov_even['mean_frac']:.3f}. "
        f"corr odd={corr_odd:.3f} even={corr_even:.3f}. {pulse}. "
        "Did not use April to pick a weekday. No Arrow 78.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 77"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
