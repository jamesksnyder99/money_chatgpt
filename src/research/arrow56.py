"""Arrow 56 — net-pair size and Wednesday+Monday. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, load_combined_iwm
from research.arrow44 import (
    LOOKBACK,
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _alpha,
    _by_sess,
    _iwm_last_close,
    _month_lines,
)
from research.arrow45 import _daily_and_trades, _within
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import (
    HOLD,
    LB,
    N_SHORT,
    _assemble_trades,
    _picks_from,
    _rebalance_job,
    already_on,
    nearest_wednesday,
    net_skip,
    peak_live_notional,
    ticket_live,
)
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
A55_NET_IS_DAY = 291.47
A55_NET_IS_N = 156
CONTROL_ID = "fw_3k_net"
DBL_ID = "fw_4k_dbl"
WM_ID = "wm_3k_net"
CORR_ID = "wm_3k_corr"
WED_LEG = "wm_wed_3k"
MON_LEG = "wm_mon_3k"
WD_LAB = {0: "Mon", 2: "Wed", 4: "Fri"}
# name, weekdays (Mon=0), notional, net
EXPERIMENTS = (
    ("fw_3k_net", (4, 2), 3000.0, True),
    ("fw_2k_net", (4, 2), 2000.0, True),
    ("fw_4k_net", (4, 2), 4000.0, True),
    ("fw_4k_dbl", (4, 2), 4000.0, False),
    ("wm_3k_net", (2, 0), 3000.0, True),
)
LEGS = (
    (WED_LEG, (2,), 3000.0, False),
    (MON_LEG, (0,), 3000.0, False),
)
ALL_BOOKS = EXPERIMENTS + LEGS
IDS = tuple(e[0] for e in ALL_BOOKS)
STACKED = frozenset(n for n, wds, _nt, _net in EXPERIMENTS if len(wds) > 1)


def allows_second_ticket(net: bool) -> bool:
    """True when the id may open two tickets in the same name (dbl, not net)."""
    return not net


def nearest_following(anchor: date, others: list[date]) -> date | None:
    """Following session in others, else preceding."""
    return nearest_wednesday(anchor, others)


def _scale_line(label: str, got_is: float, got_oos: float, base_is: float, base_oos: float, expected: float) -> str:
    s_is = (got_is / base_is) if base_is else 0.0
    s_oos = (got_oos / base_oos) if base_oos else 0.0
    note = f"{label} IS {s_is:.2f}x OOS {s_oos:.2f}x vs linear {expected:.2f}x."
    if abs(s_is - expected) > 0.20 or abs(s_oos - expected) > 0.20:
        note += " Did not scale near-linear (costs or missing fills)."
    else:
        note += " Near-linear."
    return note


def run_arrow56(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 56 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow56 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "net-pair size and Wednesday+Monday. Short only. lb=15 n=8 hold=10. "
        "Id 0 reprints Arrow 55 pair_3k_net. Second pair is Wednesday+Monday, not Friday+Monday. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No fade filter. "
        "No new ingest. No Arrow 57.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable_cal: dict[int, list[date]] = {0: [], 2: [], 4: []}
    for d in study:
        wd = d.weekday()
        if wd not in (0, 2, 4):
            continue
        look5 = session_shift(d, -LOOKBACK, feats)
        look15 = session_shift(d, -LB, feats)
        e5 = session_shift(d, 5, feats)
        e10 = session_shift(d, HOLD, feats)
        if look15 is None or e10 is None:
            continue
        if not (tape_root(e10) / e10.isoformat()).exists():
            continue
        if wd == 4:
            if look5 is None or e5 is None:
                continue
            if not (tape_root(e5) / e5.isoformat()).exists():
                continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
        usable_cal[wd].append(d)
        jobs.append(
            (
                d.isoformat(),
                look15.isoformat(),
                e10.isoformat(),
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
                wd,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} jobs={len(jobs)} fri={len(usable_cal[4])} "
        f"wed={len(usable_cal[2])} mon={len(usable_cal[0])} short-only n=8 lb=15",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow56")
    prog.start_heartbeat()
    recs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_rebalance_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            recs[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    eights: dict[int, dict[date, list[dict]]] = {0: {}, 2: {}, 4: {}}
    usable: dict[int, list[date]] = {0: [], 2: [], 4: []}
    n_res_by: dict[str, int] = {}
    for wd, days in usable_cal.items():
        for d in days:
            rec = recs.get(d.isoformat()) or {}
            n_res_by[d.isoformat()] = rec.get("n_res") or 0
            picks = _picks_from(rec)
            if picks is None:
                continue
            eights[wd][d] = picks
            usable[wd].append(d)

    def _events_for(wds: tuple[int, ...]) -> list[tuple[date, int, list[dict]]]:
        ev = []
        for wd in wds:
            for d in usable[wd]:
                ev.append((d, wd, eights[wd][d]))
        ev.sort(key=lambda x: (x[0], x[1]))
        return ev

    def _weeks_for(wds: tuple[int, ...]) -> list[date]:
        seen: set[date] = set()
        out: list[date] = []
        for wd in wds:
            for d in usable[wd]:
                if d not in seen:
                    seen.add(d)
                    out.append(d)
        return sorted(out)

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": n_res_by.get(d.isoformat(), 0)}
        for d in study
    }
    for iso, n in n_res_by.items():
        chunks.setdefault(iso, {"trades": {k: [] for k in IDS}, "n_res": 0})["n_res"] = n

    for name, wds, notional, net in ALL_BOOKS:
        by_iso = _assemble_trades(_events_for(wds), notional, name, net, wds)
        for iso, trs in by_iso.items():
            slot = chunks.setdefault(iso, {"trades": {k: [] for k in IDS}, "n_res": 0})
            slot["trades"][name] = trs

    is_weeks0 = [d for d in _weeks_for((4, 2)) if is_is_session(d)]
    sm0_is, _, _tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, is_weeks0)
    reprint_ok = _within(sm0_is["per_day"], A55_NET_IS_DAY) and _within(sm0_is["n_trades"], A55_NET_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A55_NET_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A55_NET_IS_N} "
        + (
            "— within ±10% of Arrow 55 pair_3k_net."
            if reprint_ok
            else "— DRIFT beyond ±10% of Arrow 55 pair_3k_net. Rings not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 56 — net-pair size and Wednesday+Monday (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 55 pair_3k_net. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 57.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow56_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    is_weds = [d for d in usable[2] if is_is_session(d)]
    is_mons = [d for d in usable[0] if is_is_session(d)]
    overlap_n = []
    for d in is_weds:
        m = nearest_following(d, is_mons)
        if m is None:
            continue
        a = {h["symbol"] for h in eights[2][d]}
        b = {h["symbol"] for h in eights[0][m]}
        overlap_n.append(len(a & b))
    if overlap_n:
        mean_ov = sum(overlap_n) / len(overlap_n)
        ov_line = (
            f"IS character id 5: mean names in common Wednesday eight vs nearest Monday eight "
            f"{mean_ov:.2f}/8 (n_pairs={len(overlap_n)}). Description. Does not pick an id."
        )
        same_eight = mean_ov >= 7.5
    else:
        mean_ov = 0.0
        ov_line = (
            "IS character id 5: mean names in common Wednesday eight vs nearest Monday eight "
            "n_pairs=0. Description. Does not pick an id."
        )
        same_eight = False

    def _score(name: str, wds: tuple[int, ...], notional: float, net: bool, stacked: bool) -> dict:
        weeks = _weeks_for(wds)
        is_w = [d for d in weeks if is_is_session(d)]
        oos_w = [d for d in weeks if not is_is_session(d)]
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        peak_is = peak_live_notional(tr_is, is_sess)
        peak_oos = peak_live_notional(tr_oos, oos_sess)
        peak = max(peak_is, peak_oos)
        theoretical = float(N_SHORT) * float(notional) * (2.0 * max(1, len(wds)))
        fits = peak <= ACCOUNT + 1e-12
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        slate = sm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_is["per_day"] >= 0.0 and fits
        return {
            "name": name,
            "wds": wds,
            "notional": notional,
            "net": net,
            "stacked": stacked,
            "is": sm_is,
            "oos": sm_oos,
            "day_is": day_is,
            "day_oos": day_oos,
            "a_is": a_is,
            "a_oos": a_oos,
            "skip_is": skip_is,
            "skip_oos": skip_oos,
            "n_a_is": n_is,
            "n_a_oos": n_oos,
            "seat": seat,
            "slate": slate,
            "oos_excludes": sm_oos["ci_lo"] > 0 or sm_oos["ci_hi"] < 0,
            "is_months": _month_lines(day_is, is_sess),
            "oos_months": _month_lines(day_oos, oos_sess),
            "n_reb": len(weeks),
            "peak_live": peak,
            "peak_live_is": peak_is,
            "peak_live_oos": peak_oos,
            "theoretical": theoretical,
            "fits": fits,
        }

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, wds, notional, net in EXPERIMENTS:
        r = _score(name, wds, notional, net, name in STACKED)
        if name == CONTROL_ID:
            ctrl_is = r["is"]["per_day"]
            ctrl_oos = r["oos"]["per_day"]
        lift_both = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = r["is"]["per_day"] > ctrl_is + 1e-12 and r["oos"]["per_day"] > ctrl_oos + 1e-12
            if name in STACKED:
                lift_both = lift_both and r["fits"]
        r["lift_both"] = lift_both
        results.append(r)

    wed_leg = _score(WED_LEG, (2,), 3000.0, False, False)
    mon_leg = _score(MON_LEG, (0,), 3000.0, False, False)
    wed_leg["lift_both"] = False
    mon_leg["lift_both"] = False
    corr_is = _pearson(wed_leg["day_is"], mon_leg["day_is"])
    corr_oos = _pearson(wed_leg["day_oos"], mon_leg["day_oos"])
    corr_line = (
        f"Id 5 {CORR_ID} Pearson daily PnL Wednesday $3k vs Monday $3k "
        f"IS={corr_is:.3f} OOS={corr_oos:.3f} (entry-session series; not stacked)."
    )

    r2k = next(x for x in results if x["name"] == "fw_2k_net")
    r4k = next(x for x in results if x["name"] == "fw_4k_net")
    r4d = next(x for x in results if x["name"] == DBL_ID)
    rwm = next(x for x in results if x["name"] == WM_ID)
    scale_2k = _scale_line("fw_2k_net", r2k["is"]["per_day"], r2k["oos"]["per_day"], ctrl_is, ctrl_oos, 2.0 / 3.0)
    scale_4k = _scale_line("fw_4k_net", r4k["is"]["per_day"], r4k["oos"]["per_day"], ctrl_is, ctrl_oos, 4.0 / 3.0)
    scale_4d = _scale_line("fw_4k_dbl", r4d["is"]["per_day"], r4d["oos"]["per_day"], ctrl_is, ctrl_oos, 4.0 / 3.0)

    slates = [x["name"] for x in results if x["slate"]]
    seats = [x["name"] for x in results if x["seat"]]
    both = [x["name"] for x in results if x["lift_both"]]
    fit_s = ", ".join(x["name"] for x in results if x["fits"]) or "none"
    slate_s = ", ".join(slates) if slates else "none"
    seat_s = ", ".join(seats) if seats else "none"
    both_s = ", ".join(both) if both else "none"
    low_corr = abs(corr_is) < 0.50 and abs(corr_oos) < 0.50
    second_pair = (not same_eight) and low_corr and rwm["seat"]
    if second_pair:
        wm_line = (
            f"Wednesday+Monday is a second pair (overlap {mean_ov:.2f}/8, "
            f"corr IS={corr_is:.3f} OOS={corr_oos:.3f}, "
            f"wm_3k_net OOS ${rwm['oos']['per_day']:.2f}/day peak_live ${rwm['peak_live']:.0f})."
        )
    else:
        why = []
        if same_eight:
            why.append("same eight names")
        if not low_corr:
            why.append("daily PnL correlation not low")
        if not rwm["seat"]:
            why.append("wm_3k_net is not a seat")
        wm_line = (
            f"Wednesday+Monday is not a second pair ({', '.join(why) or 'did not clear'}; "
            f"overlap {mean_ov:.2f}/8, corr IS={corr_is:.3f} OOS={corr_oos:.3f}, "
            f"wm_3k_net OOS ${rwm['oos']['per_day']:.2f}/day)."
        )

    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 56 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    honesty = (
        "Short only. Net-pair size on Friday+Wednesday leftover vs IWM; second pair is Wednesday+Monday. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "No fade filter. No sector map. Did not pair Friday+Monday. "
        "A ring counts as better than id 0 only if it lifts $/day on both IS and OOS and fits $100k. "
        "Slate needs OOS >= $200/day, IS not red, and peak live notional <= $100k. "
        "Id 5 is diagnostic and is not stacked. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 57."
    )
    lines = [
        "Arrow 56 — net-pair size and Wednesday+Monday (IS / OOS)",
        verdict,
        reprint_line,
        scale_2k,
        scale_4k,
        scale_4d,
        f"Ids that fit $100k peak live: {fit_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and peak live <= $100k: {slate_s}.",
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        corr_line,
        wm_line,
        f"Ids that lift $/day versus fw_3k_net on both IS and OOS and fit $100k: {both_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"friday rebalances={len(usable_cal[4])}  wednesday rebalances={len(usable_cal[2])}  "
        f"monday rebalances={len(usable_cal[0])}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 44–55, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  n=8  lb=15  hold=10",
        "Skip a rebalance if fewer than 16 eligible names have a residual. "
        "Skip a name if a required close is missing. Holiday weekday: skip; do not roll. "
        "Net: skip the later ticket if the name is already on from the other weekday of the pair. "
        "fw_4k_dbl allows two tickets in the same name. Id 5 is not stacked.",
        "",
        ov_line,
        "",
        f"{'id':<14} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'vs0':>6} {'seat':>5}",
    ]

    def _book_lines(r: dict, *, vs_ctrl: bool) -> None:
        for split, sm, a, skip, n_a, months, peak_s in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"], r["peak_live_is"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"], r["peak_live_oos"]),
        ):
            vs = "ctrl"
            if vs_ctrl and r["name"] != CONTROL_ID and ctrl_is is not None and ctrl_oos is not None:
                base = ctrl_is if split == "IS" else ctrl_oos
                vs = f"{sm['per_day'] - base:+.1f}"
            elif not vs_ctrl:
                vs = "leg"
            if split == "OOS" and r["slate"]:
                flag = "SLATE"
            elif split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<14} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} {vs:>6} {flag:>5}"
            )
            lines.extend(_fmt_book48(sm))
            wds = "/".join(WD_LAB[w] for w in r["wds"])
            net_s = " net" if r["net"] else (" dbl" if r["name"] == DBL_ID else "")
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={N_SHORT} notional=${r['notional']:.0f}  {wds}{net_s}  "
                f"lb={LB} hold={HOLD}{_ci_note(sm)}"
            )
            lines.append(
                f"    peak live notional ${peak_s:.0f}  two-cohort×legs ${r['theoretical']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  rebalances={r['n_reb']}"
            )
            lines.append(f"    months: {months}")

    for r in results:
        _book_lines(r, vs_ctrl=True)
    lines.append("")
    lines.append(
        f"Id 5 {CORR_ID} scored apart (not stacked). {corr_line} Overlap {mean_ov:.2f}/8."
    )
    _book_lines(wed_leg, vs_ctrl=False)
    _book_lines(mon_leg, vs_ctrl=False)
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow56_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow56_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 56",
        "",
        verdict,
        "",
        reprint_line,
        scale_2k,
        scale_4k,
        scale_4d,
        corr_line,
        wm_line,
        f"Fit $100k: {fit_s}.  Seat ${SEAT_FLOOR:.0f}: {seat_s}.  Slate ${FAILURE_LINE:.0f}: {slate_s}.",
        f"Lift vs fw_3k_net on both and fit $100k: {both_s}.",
        "Short only. Friday+Wednesday net size; Wednesday+Monday second pair. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No fade filter. "
        "Did not pair Friday+Monday. No new ingest. No Arrow 57.",
    ]
    for r in results + [wed_leg, mon_leg]:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            f"peak_live ${r['peak_live']:.0f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r.get("lift_both") else "")
            + ("  OOS CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
