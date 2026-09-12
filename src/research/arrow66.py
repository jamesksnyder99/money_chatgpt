"""Arrow 66 — Wednesday hold path 5/10/15. Short only. Split on signal session."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow23 import _summarize_adv
from research.arrow43 import SEAT_FLOOR, _elig_frame, load_combined_iwm
from research.arrow44 import (
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _alpha,
    _by_sess,
    _iwm_last_close,
    _last_close,
    _month_lines,
)
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import LB, MIN_RESIDUAL, N_SHORT
from research.arrow65 import (
    _last_job,
    _make_trade,
    _mtm_and_peak,
    _rank_job,
)
from research.book import daily_close_drawdown
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO, cost_per_share

ET = ZoneInfo("America/New_York")
A65_NEXTRTH_IS_MTM = 401.16
A65_NEXTRTH_IS_N = 116
CONTROL_ID = "h10_4k"
FILL_KIND = "nextrth"
PATH_N = 15
# name, hold, notional, keep
EXPERIMENTS = (
    ("h10_4k", 10, 4000.0, False),
    ("h5_4k", 5, 4000.0, False),
    ("h15_4k", 15, 4000.0, False),
    ("h10_3k", 10, 3000.0, False),
    ("h15_4k_keep", 15, 4000.0, True),
    ("h5_4k_keep", 5, 4000.0, True),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def hold_exit_of(fill: date, hold: int, sessions: list[date]) -> date | None:
    """Exit is hold sessions after the fill session."""
    return session_shift(fill, hold, sessions)


def path_is_only(rows: list[dict]) -> bool:
    return len(rows) == PATH_N and all(int(r["hold_day"]) == i for i, r in enumerate(rows, 1))


def _mean(xs: list[float]) -> float | None:
    if not xs:
        return None
    return sum(xs) / len(xs)


def run_arrow66(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 66 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow66 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "Wednesday hold path 5/10/15. Same leftover short as Arrow 65 nextrth_4k. "
        "Fill next session last-RTH. Split on signal Wednesday. "
        "Did not pick a hold from the OOS path. Did not use an OOS month to pick a threshold. "
        "Did not retune rank, weekday, or n. No new ingest. No Arrow 67.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    weds: list[date] = []
    for d in study:
        if d.weekday() != 2:
            continue
        look15 = session_shift(d, -LB, feats)
        if look15 is None:
            continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
        weds.append(d)
        jobs.append(
            (
                d.isoformat(),
                look15.isoformat(),
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"Wednesday signal n=8 lb={LB} fill=nextrth $4k control hold=10  jobs={len(jobs)}",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow66")
    prog.start_heartbeat()
    recs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_rank_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            recs[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    picks_by: dict[str, list[dict]] = {}
    nres_by: dict[str, int] = {}
    for d in weds:
        rec = recs.get(d.isoformat()) or {}
        nres_by[d.isoformat()] = int(rec.get("n_res") or 0)
        rows = list(rec.get("rows") or [])
        if (rec.get("n_res") or 0) < MIN_RESIDUAL:
            picks_by[d.isoformat()] = []
            continue
        picks_by[d.isoformat()] = select_shorts(rows, N_SHORT, None)

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in study
    }
    skips: dict[str, dict[str, int]] = {k: {"IS": 0, "OOS": 0} for k in IDS}
    partials: dict[str, dict[str, int]] = {k: {"IS": 0, "OOS": 0} for k in IDS}
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    usable: dict[str, list[date]] = {k: [] for k in IDS}

    for d in weds:
        picks = picks_by.get(d.isoformat()) or []
        split = "IS" if is_is_session(d) else "OOS"
        for name, hold, notional, keep in EXPERIMENTS:
            if nres_by.get(d.isoformat(), 0) >= MIN_RESIDUAL:
                usable[name].append(d)
            for h in picks:
                tr, skip_fill, partial = _make_trade(
                    h, FILL_KIND, notional, keep, d, feats, hold=hold
                )
                if skip_fill:
                    skips[name][split] += 1
                    continue
                if tr is None:
                    continue
                if partial:
                    partials[name][split] += 1
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                trades_all[name].append(tr)

    need: set[tuple[str, str]] = set()
    path_sessions: set[date] = set()
    for name, trs in trades_all.items():
        for t in trs:
            fill_d, exit_d = t["fill_date"], t["exit_date"]
            for d in study:
                if fill_d <= d < exit_d:
                    need.add((d.isoformat(), t["symbol"]))
            if name == CONTROL_ID and is_is_session(t["signal"]):
                for k in range(1, PATH_N + 1):
                    dk = session_shift(fill_d, k, feats)
                    if dk is not None:
                        need.add((dk.isoformat(), t["symbol"]))
                        path_sessions.add(dk)
                need.add((fill_d.isoformat(), t["symbol"]))

    last_map: dict[tuple[str, str], float] = {}
    if need:
        prog2 = Progress(len(need), "arrow66-mtm")
        prog2.start_heartbeat()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_last_job, job) for job in sorted(need)]
            for i, fut in enumerate(as_completed(futs), 1):
                iso, symbol, px = fut.result()
                if px is not None:
                    last_map[(iso, symbol)] = px
                prog2.mark(str(i), rows=1)
                if i % 64 == 0:
                    prog2.heartbeat()
        prog2.stop_heartbeat()
        prog2.heartbeat()

    # Leftover top-8 on path sessions (IS description only).
    path_jobs = []
    for d in sorted(path_sessions):
        look15 = session_shift(d, -LB, feats)
        if look15 is None:
            continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
        path_jobs.append(
            (
                d.isoformat(),
                look15.isoformat(),
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
            )
        )
    top8: dict[str, set[str]] = {}
    if path_jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_rank_job, job) for job in path_jobs]
            for fut in as_completed(futs):
                rec = fut.result()
                rows = list(rec.get("rows") or [])
                if (rec.get("n_res") or 0) < MIN_RESIDUAL:
                    top8[rec["session"]] = set()
                    continue
                top8[rec["session"]] = {h["symbol"] for h in select_shorts(rows, N_SHORT, None)}

    sm_ent0, _, tr0 = _daily_and_trades(
        chunks, is_sess, CONTROL_ID, [d for d in weds if is_is_session(d)]
    )
    mtm0_all, _ = _mtm_and_peak(trades_all[CONTROL_ID], study, last_map)
    mtm0_is = [mtm0_all[study.index(d)] for d in is_sess]
    sm_mtm0 = _summarize_adv(mtm0_is, tr0, len(is_sess))
    reprint_ok = _within(sm_mtm0["per_day"], A65_NEXTRTH_IS_MTM) and _within(
        sm_ent0["n_trades"], A65_NEXTRTH_IS_N
    )
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS MTM $/day={sm_mtm0['per_day']:.2f}/{A65_NEXTRTH_IS_MTM} "
        f"n={sm_ent0['n_trades']}/{A65_NEXTRTH_IS_N} "
        + (
            "— within ±10% of Arrow 65 nextrth_4k."
            if reprint_ok
            else "— DRIFT beyond ±10%. Hold path not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 66 — Wednesday hold path 5 / 10 / 15 (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 65 nextrth_4k. "
            "Did not score the hold path on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 67.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow66_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    # IS path on id 0 fills. Does not pick an id. Do not print OOS path.
    is_fills = [t for t in trades_all[CONTROL_ID] if is_is_session(t["signal"])]
    path_rows: list[dict] = []
    for k in range(1, PATH_N + 1):
        mtms: list[float] = []
        resids: list[float] = []
        in8: list[float] = []
        for t in is_fills:
            fill_d = t["fill_date"]
            dk = session_shift(fill_d, k, feats)
            last = None
            if dk is not None:
                last = last_map.get((dk.isoformat(), t["symbol"]))
            if last is None:
                last = float(t["exit_px"])
            sh = float(t["shares"])
            mtms.append(sh * (float(t["entry_px"]) - last) - sh * cost_per_share(float(t["entry_px"])))
            iwm_f = _iwm_last_close(iwm, fill_d)
            iwm_k = _iwm_last_close(iwm, dk) if dk is not None else None
            if (
                iwm_f is not None
                and iwm_k is not None
                and iwm_f[1] > 0
                and float(t["entry_px"]) > 0
            ):
                resids.append((last / float(t["entry_px"]) - 1.0) - (iwm_k[1] / iwm_f[1] - 1.0))
            if dk is not None:
                in8.append(1.0 if t["symbol"] in (top8.get(dk.isoformat()) or set()) else 0.0)
        path_rows.append(
            {
                "hold_day": k,
                "n": len(mtms),
                "mean_mtm": _mean(mtms),
                "mean_res": _mean(resids),
                "frac_top8": _mean(in8),
            }
        )
    assert path_is_only(path_rows)
    peak_day = max(
        (r for r in path_rows if r["mean_mtm"] is not None),
        key=lambda r: float(r["mean_mtm"]),
        default=None,
    )
    path_peak_s = (
        f"IS path mean mark peaks at fill+{peak_day['hold_day']} "
        f"(${peak_day['mean_mtm']:.2f}/name, n={peak_day['n']})."
        if peak_day and peak_day["mean_mtm"] is not None
        else "IS path mean mark n=0."
    )
    path_lines = [
        "IS path on id 0 fills (fill+1..+15). Description. Does not pick an id. "
        "Did not print the OOS path. Did not pick a hold from OOS.",
        f"{'hold_day':>8} {'n':>5} {'mean_MTM$':>12} {'mean_res_IWM':>14} {'frac_top8':>10}",
    ]
    for r in path_rows:
        mm = f"{r['mean_mtm']:.2f}" if r["mean_mtm"] is not None else "n/a"
        mr = f"{r['mean_res']:.5f}" if r["mean_res"] is not None else "n/a"
        fr = f"{r['frac_top8']:.3f}" if r["frac_top8"] is not None else "n/a"
        path_lines.append(f"{r['hold_day']:8d} {r['n']:5d} {mm:>12} {mr:>14} {fr:>10}")

    results = []
    ctrl_is = ctrl_oos = None
    for name, hold, notional, keep in EXPERIMENTS:
        weeks = usable[name]
        is_w = [d for d in weeks if is_is_session(d)]
        oos_w = [d for d in weeks if not is_is_session(d)]
        sm_ent_is, _, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_ent_oos, _, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
        sm_ent_is["n_win"], sm_ent_is["n_loss"] = _wins_losses(tr_is)
        sm_ent_oos["n_win"], sm_ent_oos["n_loss"] = _wins_losses(tr_oos)
        mtm_all, peak_all = _mtm_and_peak(trades_all[name], study, last_map)
        mtm_is = [mtm_all[study.index(d)] for d in is_sess]
        mtm_oos = [mtm_all[study.index(d)] for d in oos_sess]
        sm_mtm_is = _summarize_adv(mtm_is, tr_is, len(is_sess))
        sm_mtm_oos = _summarize_adv(mtm_oos, tr_oos, len(oos_sess))
        sm_mtm_is["n_win"], sm_mtm_is["n_loss"] = sm_ent_is["n_win"], sm_ent_is["n_loss"]
        sm_mtm_oos["n_win"], sm_mtm_oos["n_loss"] = sm_ent_oos["n_win"], sm_ent_oos["n_loss"]
        sm_mtm_is["daily_close_dd"] = daily_close_drawdown(mtm_is)
        sm_mtm_oos["daily_close_dd"] = daily_close_drawdown(mtm_oos)
        sm_mtm_is["worst_day"] = min(mtm_is) if mtm_is else 0.0
        sm_mtm_oos["worst_day"] = min(mtm_oos) if mtm_oos else 0.0
        sm_mtm_is["n_week"] = sm_ent_is["n_week"]
        sm_mtm_oos["n_week"] = sm_ent_oos["n_week"]
        sm_mtm_is["trades_per_week"] = sm_ent_is["trades_per_week"]
        sm_mtm_oos["trades_per_week"] = sm_ent_oos["trades_per_week"]
        sm_mtm_is["peak_conc"] = sm_ent_is["peak_conc"]
        sm_mtm_oos["peak_conc"] = sm_ent_oos["peak_conc"]
        sm_mtm_is["mean_conc"] = sm_ent_is["mean_conc"]
        sm_mtm_oos["mean_conc"] = sm_ent_oos["mean_conc"]
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        _, peak_is = _mtm_and_peak(trades_all[name], is_sess, last_map)
        _, peak_oos = _mtm_and_peak(trades_all[name], oos_sess, last_map)
        fits = peak_all <= ACCOUNT + 1e-12
        seat = sm_mtm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_mtm_is["per_day"] >= 0.0
        slate = (
            sm_mtm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_mtm_is["per_day"] >= 0.0 and fits
        )
        if name == CONTROL_ID:
            ctrl_is, ctrl_oos = sm_mtm_is["per_day"], sm_mtm_oos["per_day"]
        lift_both = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = (
                sm_mtm_is["per_day"] > ctrl_is + 1e-12 and sm_mtm_oos["per_day"] > ctrl_oos + 1e-12
            )
        results.append(
            {
                "name": name,
                "hold": hold,
                "notional": notional,
                "keep": keep,
                "ent_is": sm_ent_is,
                "ent_oos": sm_ent_oos,
                "mtm_is": sm_mtm_is,
                "mtm_oos": sm_mtm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "fill_skips_is": skips[name]["IS"],
                "fill_skips_oos": skips[name]["OOS"],
                "partial_is": partials[name]["IS"],
                "partial_oos": partials[name]["OOS"],
                "seat": seat,
                "slate": slate,
                "lift_both": lift_both,
                "oos_excludes": sm_mtm_oos["ci_lo"] > 0 or sm_mtm_oos["ci_hi"] < 0,
                "is_months": _month_lines(mtm_is, is_sess),
                "oos_months": _month_lines(mtm_oos, oos_sess),
                "n_reb": len(weeks),
                "peak_live": peak_all,
                "peak_live_is": peak_is,
                "peak_live_oos": peak_oos,
                "fits": fits,
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    if slates:
        verdict = (
            "VERDICT: SLATE — "
            + ", ".join(slates)
            + f" (OOS MTM >= ${FAILURE_LINE:.0f}/day, IS MTM not red, peak live <= ${ACCOUNT:.0f})."
        )
    elif seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS MTM >= ${SEAT_FLOOR:.0f}/day and IS MTM not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 66 engine has OOS MTM >= ${SEAT_FLOOR:.0f}/day AND non-red IS MTM."
        )
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    both_s = ", ".join(both) if both else "none"
    h15 = next(r for r in results if r["name"] == "h15_4k")
    lead = (
        f"{reprint_line} {path_peak_s} "
        f"Slate ${FAILURE_LINE:.0f}: {slate_s}. Seat ${SEAT_FLOOR:.0f}: {seat_s}. "
        f"Hold 15 fits $100k: {'yes' if h15['fits'] else 'NO'} (peak ${h15['peak_live']:.0f}). "
        f"Hold 15 lifts both slices vs id 0: {'yes' if h15['lift_both'] else 'no'}."
    )
    honesty = (
        "Wednesday hold path 5/10/15. Same leftover short as Arrow 65 nextrth_4k: "
        "Wednesday signal, lb=15 vs IWM, short eight, fill next session last-RTH, $4,000. "
        "Split on the signal session. Did not retune rank, weekday, or n. "
        "This is the path, not keep/cash and not replace. "
        "Did not pick a hold from the OOS path. Did not print the OOS path. "
        "Did not use an OOS month to pick a threshold. Did not drop an id after seeing OOS. "
        "Did not retune Friday+Wednesday pair, SIC group, MAX, or frozen B/flush. "
        "A ring beats id 0 only if it lifts MTM $/day on both IS and OOS. "
        "Seat uses OOS MTM $/day. Equity, DD, and worst day are MTM. "
        "Do not call a CI that includes 0 EV. Combined dollars are not EV. No Arrow 67."
    )
    lines = [
        "Arrow 66 — Wednesday hold path 5 / 10 / 15 (IS / OOS)",
        verdict,
        lead,
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day OOS MTM with IS MTM not red: {seat_s}.",
        f"Engines that clear slate ${FAILURE_LINE:.0f}/day OOS MTM with IS MTM not red and peak live fit: {slate_s}.",
        f"Ids that lift MTM $/day versus {CONTROL_ID} on both IS and OOS: {both_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"wednesday signals={len(weds)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"Wednesday signal  n=8  lb={LB} fill=nextrth  hold after fill  $4,000/$3,000",
        "Peak live = |shares × last|. Hold 15 stacks more cohorts.",
        "",
        *path_lines,
        "",
        f"{'id':<16} {'split':<4} {'entry$':>9} {'MTM$':>9} {'n':>6} {'hit':>6} {'t':>6} "
        f"{'hold':>5} {'seat':>5}",
    ]
    for r in results:
        for split, ent, mtm, a, skip_a, n_a, months_s, peak_s, fskip, part in (
            (
                "IS",
                r["ent_is"],
                r["mtm_is"],
                r["a_is"],
                r["skip_is"],
                r["n_a_is"],
                r["is_months"],
                r["peak_live_is"],
                r["fill_skips_is"],
                r["partial_is"],
            ),
            (
                "OOS",
                r["ent_oos"],
                r["mtm_oos"],
                r["a_oos"],
                r["skip_oos"],
                r["n_a_oos"],
                r["oos_months"],
                r["peak_live_oos"],
                r["fill_skips_oos"],
                r["partial_oos"],
            ),
        ):
            if split == "OOS" and r["slate"]:
                flag = "SLATE"
            elif split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<16} {split:<4} {ent['per_day']:9.2f} {mtm['per_day']:9.2f} "
                f"{ent['n_trades']:6d} {ent['hit_rate']:6.3f} {mtm['t_stat']:6.2f} "
                f"{r['hold']:5d} {flag:>5}"
            )
            lines.extend(_fmt_book48(mtm))
            lines.append(
                f"    entry $/day={ent['per_day']:.2f}  MTM $/day={mtm['per_day']:.2f}  "
                f"IWM alpha $/day={a:.2f} (n={n_a} skip={skip_a})  "
                f"hold={r['hold']} notional=${r['notional']:.0f} keep={r['keep']}  "
                f"skips={fskip} exit_partial={part}{_ci_note(mtm)}"
            )
            lines.append(
                f"    peak live |shares×last| ${peak_s:.0f}  all-sessions ${r['peak_live']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  signals={r['n_reb']}"
            )
            lines.append(f"    MTM months: {months_s}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow66_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow66_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 66",
        "",
        verdict,
        "",
        lead,
        path_peak_s,
        f"Seat ${SEAT_FLOOR:.0f} MTM: {seat_s}. Slate ${FAILURE_LINE:.0f}: {slate_s}. "
        f"Lift-both vs id0: {both_s}.",
        "Wednesday hold path 5/10/15. Did not pick a hold from OOS. "
        "Did not retune leftover pair, SIC, MAX, or frozen B/flush. No new ingest. No Arrow 67.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: entry IS ${r['ent_is']['per_day']:.2f} MTM ${r['mtm_is']['per_day']:.2f} "
            f"n={r['ent_is']['n_trades']}  entry OOS ${r['ent_oos']['per_day']:.2f} "
            f"MTM ${r['mtm_oos']['per_day']:.2f} n={r['ent_oos']['n_trades']} "
            f"t={r['mtm_oos']['t_stat']:.2f}  peak_live ${r['peak_live']:.0f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r["lift_both"] else "")
            + ("  OOS MTM CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
