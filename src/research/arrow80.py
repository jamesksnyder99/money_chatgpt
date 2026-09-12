"""Arrow 80 — five frozen open leftover books, Sep 2025–Aug 2026. Short only."""

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
from research.arrow70 import _elig_year
from research.arrow74 import NOTIONAL, peak_live_intraday
from research.arrow76 import EXIT_1029, EXIT_1129, LEFT_LB, N8, N15, _extract_job, pick_exit
from research.arrow77 import H10_HOLD, H10_NOTIONAL, h10_live_at_0930
from research.arrow78 import filter_eight
from research.arrow79 import TUESDAY, is_tuesday
from research.book import daily_close_drawdown
from research.clock import (
    arrow70_feature_sessions,
    arrow70_score_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
CONTROL_ID = "n8_1029"
N15_ID = "n15_1029"
COMP_ID = "comp_1029"
A76_JAN_N8 = 268.33
A76_JAN_N15 = 379.53
REPRINT_TOL = 0.20
H10_SEP = -553.56
H10_JUN = 942.32
SCORE_LO = date(2025, 9, 2)
SCORE_HI = date(2026, 8, 31)
H10_FIRST = date(2025, 9, 3)
# name, n, exit_kind, skip_tue, complement
EXPERIMENTS = (
    ("n15_1029", N15, "1029", False, False),
    ("n8_1029", N8, "1029", False, False),
    ("n8_1029_notue", N8, "1029", True, False),
    ("n8_1129", N8, "1129", False, False),
    ("comp_1029", N8, "1029", False, True),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
YEAR_MONTHS = [(2025, m) for m in range(9, 13)] + [(2026, m) for m in range(1, 9)]


def year_picks(
    ranked: list[dict],
    n: int,
    live: set[str],
    *,
    skip_tue: bool,
    complement: bool,
    weekday: int,
) -> list[dict]:
    """Sit out if empty. Do not backfill. Do not gap-filter."""
    if skip_tue and weekday == TUESDAY:
        return []
    picks = ranked[: max(0, int(n))]
    if complement:
        picks = filter_eight(picks, "complement", live)
    return picks


def sessions_with_left(score: list[date], feats: list[date], n: int = LEFT_LB) -> list[date]:
    """First session with n prior sessions on tape, through last score day."""
    out = []
    for d in score:
        prior = [x for x in feats if x < d]
        if len(prior) >= n:
            out.append(d)
    return out


def run_arrow80(*, workers: int | None = None) -> int:
    score = arrow70_score_sessions()
    feats = arrow70_feature_sessions()
    leftover = feature_sessions()
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    if FILL_KIND != "nextrth":
        raise RuntimeError("Arrow 80 must not retune Wednesday H10 fill")
    if any(tape_root(d) == BARS_DIR for d in (date(2025, 9, 2), date(2026, 1, 2), date(2026, 6, 1))):
        raise RuntimeError("Arrow 80 must not read Lab A data/bars/")
    sess = sessions_with_left(score, feats, LEFT_LB)
    if not sess or sess[0] < SCORE_LO or sess[-1] > SCORE_HI:
        raise RuntimeError("Arrow 80 score window drifted")
    odd = [d for d in sess if is_is_session(d)]
    even = [d for d in sess if not is_is_session(d)]
    jan = [d for d in sess if d.year == 2026 and d.month == 1]
    fall = [d for d in sess if d.year == 2025]
    y2026 = [d for d in sess if d.year == 2026]
    june = [d for d in sess if d.year == 2026 and d.month == 6]
    mayaug = [d for d in sess if d.year == 2026 and d.month >= 5]
    by_month: dict[str, list[date]] = {}
    for d in sess:
        by_month.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(d)
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    print(
        f"research start mode=arrow80 workers={workers} cpu={cpu} "
        f"window={sess[0]}..{sess[-1]} n={len(sess)} odd n={len(odd)} even n={len(even)} "
        f"feats={feats[0]}..{feats[-1]} leftover={leftover[0]}.. "
        f"sep_tape={tape_root(date(2025, 9, 2))} jan_tape={tape_root(date(2026, 1, 2))} "
        f"jun_tape={tape_root(date(2026, 6, 1))}",
        flush=True,
    )
    print(
        "Five frozen open leftover books Sep 2025–Aug 2026. Fill ≥ 09:30, short only. "
        "Did not gap-filter. Did not retune Wednesday H10. Did not add a sixth id. "
        "Did not pick an id after seeing a month. No new ingest. No Arrow 81.",
        flush=True,
    )
    elig = _elig_year(sess)
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
        f"left={LEFT_LB} n8={N8} n15={N15} ${NOTIONAL:.0f} fill>=09:30 extract_jobs={len(need)}",
        flush=True,
    )
    cache: dict[tuple[str, str], dict] = {}
    prog = Progress(len(need), "arrow80")
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

    iwm = load_combined_iwm()
    h10_jobs = []
    h10_weds: list[date] = []
    for d in feats:
        if d.weekday() != 2 or d < H10_FIRST or d > sess[-1]:
            continue
        look15 = session_shift(d, -LB, feats)
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
        f"weds={len(h10_jobs)} first={h10_weds[0] if h10_weds else None} (did not retune)",
        flush=True,
    )
    recs: dict[str, dict] = {}
    if h10_jobs:
        prog_h = Progress(len(h10_jobs), "arrow80-h10")
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
                h, FILL_KIND, H10_NOTIONAL, False, d, feats, hold=H10_HOLD
            )
            if skip_fill or tr is None:
                continue
            h10_trades.append(tr)

    need_h10: set[tuple[str, str]] = set()
    mtm_sess = [d for d in feats if SCORE_LO <= d <= SCORE_HI]
    for t in h10_trades:
        fill_d, exit_d = t["fill_date"], t["exit_date"]
        for d in mtm_sess:
            if fill_d <= d < exit_d:
                need_h10.add((d.isoformat(), t["symbol"]))
    last_map: dict[tuple[str, str], float] = {}
    if need_h10:
        prog_m = Progress(len(need_h10), "arrow80-h10-mtm")
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
    mtm_walk = [d for d in feats if d <= SCORE_HI]
    mtm_all, _peak_h10 = _mtm_and_peak(h10_trades, mtm_walk, last_map)
    mtm_idx = {d: i for i, d in enumerate(mtm_walk)}
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
    ov_fracs: list[float] = []

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
            continue
        eight = select_winners(keyed, N8, "left")
        fifteen = select_winners(keyed, N15, "left") if len(keyed) >= N15 else []
        ov_fracs.append(sum(1 for r in eight if r["symbol"] in live) / 8.0)
        for name, n_slot, ekind, skip_tue, complement in EXPERIMENTS:
            ranked = fifteen if n_slot == N15 else eight
            if n_slot == N15 and len(ranked) < N15:
                continue
            picks = year_picks(
                ranked, n_slot, live, skip_tue=skip_tue, complement=complement, weekday=d.weekday()
            )
            if not picks:
                continue
            for row in picks:
                today = row["today"]
                ent = today.get("fill")
                ex = pick_exit(today, ekind)
                if ent is None or ex is None:
                    continue
                if ent[0] > ex[0]:
                    continue
                tr = _short_n(row, ent, ex, name, NOTIONAL)
                if tr is None:
                    continue
                if tr["side"] != -1:
                    raise RuntimeError("Arrow 80 must be short-only")
                if complement and row["symbol"] in live:
                    raise RuntimeError("comp_1029 shorted an H10-live name")
                if skip_tue and is_tuesday(d):
                    raise RuntimeError("n8_1029_notue filled on Tuesday")
                tr["signal"] = d
                tr["fill_date"] = d
                tr["exit_date"] = d
                stamp = EXIT_1129 if ekind == "1129" else EXIT_1029
                tr["exit_partial"] = _clock(ex[0]) != stamp
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
    for name, n_slot, ekind, skip_tue, complement in EXPERIMENTS:
        year_s = _score(name, sess)
        jan_s = _score(name, jan)
        months = {key: _score(name, days_m) for key, days_m in sorted(by_month.items())}
        results.append(
            {
                "name": name,
                "n": n_slot,
                "exit": ekind,
                "skip_tue": skip_tue,
                "complement": complement,
                "year": year_s,
                "jan": jan_s,
                "odd": _score(name, odd),
                "even": _score(name, even),
                "months": months,
                "peak_all": peak_live_intraday(trades_all[name]),
            }
        )

    parent = next(r for r in results if r["name"] == CONTROL_ID)
    n15 = next(r for r in results if r["name"] == N15_ID)
    jan8 = parent["jan"]["sm"]["per_day"]
    jan15 = n15["jan"]["sm"]["per_day"]
    ok8 = _within(jan8, A76_JAN_N8, REPRINT_TOL)
    ok15 = _within(jan15, A76_JAN_N15, REPRINT_TOL)
    reprint_line = (
        f"Id 1 {CONTROL_ID} January $/day={jan8:.2f} vs Arrow 76 h1029_n8 {A76_JAN_N8:.2f} "
        f"n={parent['jan']['sm']['n_trades']} "
        + ("— within ±20%. " if ok8 else "— DRIFT beyond ±20%. Stop and fix. ")
        + f"Id 0 {N15_ID} January $/day={jan15:.2f} vs Arrow 76 h1029_n15 {A76_JAN_N15:.2f} "
        f"n={n15['jan']['sm']['n_trades']} "
        + ("— within ±20%." if ok15 else "— DRIFT beyond ±20%. Stop and fix.")
    )
    print(reprint_line, flush=True)
    if not ok8 or not ok15:
        raise RuntimeError(reprint_line)

    def _month_day(daily: list[float], slice_sess: list[date], year: int, month: int) -> float:
        xs = [v for d, v in zip(slice_sess, daily) if d.year == year and d.month == month]
        return (sum(xs) / len(xs)) if xs else 0.0

    def _corr(name: str, slice_sess: list[date]) -> tuple[float, int]:
        pack = _score(name, slice_sess)
        xs, ys = [], []
        sset = set(slice_sess)
        # align pack daily (over slice_sess) with h10 on those days
        hmap = {d: h for d, h in zip(sess, h10_daily)}
        for d, a in zip(slice_sess, pack["daily"]):
            if d not in sset:
                continue
            xs.append(float(a))
            ys.append(float(hmap.get(d, 0.0)))
        return _pearson(xs, ys), len(xs)

    corr_y1, n_y1 = _corr(CONTROL_ID, sess)
    corr_y4, n_y4 = _corr(COMP_ID, sess)
    corr_f1, n_f1 = _corr(CONTROL_ID, fall)
    corr_f4, n_f4 = _corr(COMP_ID, fall)
    corr_j1, n_j1 = _corr(CONTROL_ID, y2026)
    corr_j4, n_j4 = _corr(COMP_ID, y2026)
    corr_u1, n_u1 = _corr(CONTROL_ID, june)
    corr_u4, n_u4 = _corr(COMP_ID, june)
    corr_n4, n_n4 = _corr(COMP_ID, mayaug)
    mean_ov = (sum(ov_fracs) / len(ov_fracs)) if ov_fracs else 0.0

    h10_sep = _month_day(h10_daily, sess, 2025, 9)
    h10_jun = _month_day(h10_daily, sess, 2026, 6)
    p_sep = parent["months"].get("2025-09", {}).get("sm", {}).get("per_day", 0.0) if "2025-09" in parent["months"] else 0.0
    p_jun = parent["months"].get("2026-06", {}).get("sm", {}).get("per_day", 0.0) if "2026-06" in parent["months"] else 0.0
    # months packs are _score dicts
    p_sep = parent["months"]["2025-09"]["sm"]["per_day"] if "2025-09" in parent["months"] else 0.0
    p_jun = parent["months"]["2026-06"]["sm"]["per_day"] if "2026-06" in parent["months"] else 0.0
    sep_hole = p_sep < 0
    jun_fat = p_jun > 200
    pulse_new = abs(corr_f4) < 0.5 and abs(corr_n4) < 0.5
    year_bits = " ".join(
        f"{r['name']} ${r['year']['sm']['per_day']:.2f}" for r in results
    )
    first_para = (
        f"{reprint_line} Year $/day (total / n={len(sess)} sessions {sess[0]}..{sess[-1]}): "
        f"{year_bits}. September 2025 day-book {CONTROL_ID} ${p_sep:.2f} vs H10 MTM ${h10_sep:.2f} "
        f"(H10 Arrow 70 {H10_SEP:.2f}); hole={'yes' if sep_hole else 'no'}. "
        f"June 2026 day-book ${p_jun:.2f} vs H10 MTM ${h10_jun:.2f} "
        f"(H10 Arrow 66/70 ~{H10_JUN:.2f}); fat={'yes' if jun_fat else 'no'}. "
        f"Complement second pulse on new months (fall 2025 corr={corr_f4:.3f}, "
        f"May–Aug 2026 corr={corr_n4:.3f}): {'yes' if pulse_new else 'no'}. "
        f"Id 1 vs H10 overlap/8 mean={mean_ov:.3f}."
    )
    sniff = (
        "VERDICT: LOOK — not a $200 slate pass. The year is one look of five frozen day books, "
        "not a new IS/OOS split. Jan–Apr 2026 already had a look; Sep–Dec 2025 and May–Aug 2026 "
        "are new for this hotel. Did not pick an id after seeing a month. Did not gap-filter. "
        "Did not retune Wednesday H10."
    )
    honesty = (
        "Chassis: 15-session leftover rank, fill first print ≥ 09:30, $3,000, field $10–$80 "
        "PDV ≥ $10M. Short only. Five ids. Complement = leftover eight minus H10 live at 09:30. "
        "H10 = Wednesday signal, next last-RTH, $4,000, hold 10. Lookback may read August 2025. "
        "Jun–Aug 2026 from data/full/. Sep 2025–May 2026 from data/virgin/. "
        "Odd vs even is courtesy, not a new promotion split. Do not call a CI that includes 0 EV. "
        "Do not call the year a $200 slate pass. No new ingest. Did not touch Lab A data/bars/. "
        "No Arrow 81."
    )
    print(first_para, flush=True)

    lines = [
        "Arrow 80 — five frozen open leftover books, Sep 2025–Aug 2026",
        first_para,
        sniff,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"window n={len(sess)} {sess[0]}..{sess[-1]}  odd n={len(odd)}  even n={len(even)}  "
        f"(courtesy, not a new split)",
        f"workers={workers} cpu_count={cpu}  sep_tape={tape_root(date(2025, 9, 2))}  "
        f"jan_tape={tape_root(date(2026, 1, 2))}  jun_tape={tape_root(date(2026, 6, 1))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"left={LEFT_LB} n8={N8} n15={N15} ${NOTIONAL:.0f} fill>=09:30  "
        f"H10 nextrth hold={H10_HOLD} ${H10_NOTIONAL:.0f} weds={len(h10_weds)} trades={len(h10_trades)}",
        "Peak live = |shares × entry| (same-session day book). "
        "$/day = total PnL / NYSE sessions in that slice.",
        "",
        f"mean overlap/8 id1 vs H10 live={mean_ov:.3f} n_sess={len(ov_fracs)}",
        f"Pearson id1 vs H10 MTM: year={corr_y1:.3f} n={n_y1}  fall2025={corr_f1:.3f} n={n_f1}  "
        f"jan-aug2026={corr_j1:.3f} n={n_j1}  june2026={corr_u1:.3f} n={n_u1}",
        f"Pearson id4 vs H10 MTM: year={corr_y4:.3f} n={n_y4}  fall2025={corr_f4:.3f} n={n_f4}  "
        f"jan-aug2026={corr_j4:.3f} n={n_j4}  june2026={corr_u4:.3f} n={n_u4}  "
        f"may-aug2026={corr_n4:.3f} n={n_n4}",
        f"H10 MTM Sep 2025 $/day={h10_sep:.2f}  Jun 2026 $/day={h10_jun:.2f}",
        "",
        "12-month $/day (total PnL / NYSE sessions in that month)",
        f"{'month':<8} " + " ".join(f"{r['name']:>14}" for r in results),
    ]
    for y, m in YEAR_MONTHS:
        key = f"{y:04d}-{m:02d}"
        bits = [f"{key:<8}"]
        for r in results:
            pack = r["months"].get(key)
            val = pack["sm"]["per_day"] if pack else 0.0
            bits.append(f"{val:14.2f}")
        lines.append(" ".join(bits))
    lines.append("")
    lines.append(f"{'id':<16} {'slice':<11} {'$/day':>9} {'n':>6} {'hit':>6} {'t':>6}")

    def _emit(r: dict, label: str, pack: dict) -> None:
        sm = pack["sm"]
        lines.append(
            f"{r['name']:<16} {label:<11} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
            f"{sm['hit_rate']:6.3f} {sm['t_stat']:6.2f}"
        )
        lines.extend(_fmt_book57(sm))
        ci_ex = sm["ci_lo"] > 0 or sm["ci_hi"] < 0
        lines.append(
            f"    $/day={sm['per_day']:.2f} (total PnL / n={pack['n_sess']} sessions)  "
            f"n={r['n']} exit={r['exit']} skip_tue={r['skip_tue']} complement={r['complement']} "
            f"${NOTIONAL:.0f}  peak live ${pack['peak']:.0f}  all ${r['peak_all']:.0f}{_ci_note(sm)}"
        )
        lines.append(f"    months: {pack['months']}")
        if ci_ex:
            lines.append(f"    {label} CI excludes 0.")
        else:
            lines.append(f"    {label} CI includes 0 — not EV.")

    for r in results:
        _emit(r, "year", r["year"])
        _emit(r, "odd", r["odd"])
        _emit(r, "even", r["even"])
        _emit(r, "2026-01", r["jan"])
    lines.append(
        "    Did not pick an id after seeing a month. Did not gap-filter. "
        "Did not call the year a $200 slate pass. No Arrow 81."
    )
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow80_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow80_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 80",
        "",
        first_para,
        "",
        sniff,
        f"{year_bits}. Sep hole={sep_hole} Jun fat={jun_fat}. "
        f"comp corr fall={corr_f4:.3f} may-aug={corr_n4:.3f}. Did not gap-filter. No Arrow 81.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 80"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
