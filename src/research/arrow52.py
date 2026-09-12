"""Arrow 52 — weekday rank and standing top-8. Short only. $6,000. Score apart."""

from __future__ import annotations

import os
import statistics
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
    _last_close,
    _month_lines,
    residual,
)
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    rebalance_sessions,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
A51_LB15_IS_DAY = 575.43
A51_LB15_IS_N = 129
CONTROL_ID = "fri_h10"
STAND_ID = "stand_top8"
NOTIONAL = 6000.0
N_SHORT = 8
MIN_RESIDUAL = 16
LB = 15
HOLD = 10
ONE_COHORT = float(N_SHORT) * NOTIONAL
TWO_COHORT = 2.0 * ONE_COHORT
# name, weekday (Mon=0)
WEEKDAY_IDS = (
    ("fri_h10", 4),
    ("mon_h10", 0),
    ("tue_h10", 1),
    ("wed_h10", 2),
    ("thu_h10", 3),
)
WD_BY_DOW = {dow: name for name, dow in WEEKDAY_IDS}
IDS = tuple(n for n, _ in WEEKDAY_IDS) + (STAND_ID,)


def weekday_id(d: date) -> str | None:
    """Weekday book for this calendar day, or None (weekend / not a hallway)."""
    return WD_BY_DOW.get(d.weekday())


def stand_exits(prev_top: set[str], today_top: set[str]) -> set[str]:
    return set(prev_top) - set(today_top)


def stand_enters(prev_top: set[str], today_top: set[str]) -> set[str]:
    return set(today_top) - set(prev_top)


def _fmt_book52(sm: dict, *, per: str = "week") -> list[str]:
    lines = _fmt_book48(sm)
    if per != "week":
        lines[0] = lines[0].replace("n/week=", "n/sess=")
    return lines


def _median_stay(stints: list[int]) -> str:
    if not stints:
        return "n=0"
    return f"n={len(stints)} median_days={statistics.median(stints):.1f}"


def _session_job(args: tuple) -> dict:
    (
        iso,
        look15_iso,
        exit10_iso,
        names,
        iwm_l15,
        iwm1,
        wd_name,
        do_weekday,
    ) = args
    session = date.fromisoformat(iso)
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    empty = {
        "session": iso,
        "top8": [],
        "n_res": 0,
        "wd_name": wd_name,
        "wd_trades": [],
        "skipped": "no_names",
    }
    if not names or look15 is None or iwm_l15 is None or iwm1 is None or iwm_l15 <= 0 or iwm1 <= 0:
        empty["skipped"] = "iwm"
        return empty
    rows = []
    for h in names:
        sym = h["symbol"]
        now = _last_close(session, sym)
        if now is None:
            continue
        a15 = _last_close(look15, sym)
        if a15 is None:
            continue
        res = residual(a15[1], now[1], iwm_l15, iwm1)
        if res is None:
            continue
        rows.append({**h, "residual": res, "now": now})
    top8 = select_shorts(rows, N_SHORT, None) if len(rows) >= MIN_RESIDUAL else []
    wd_trades = []
    if do_weekday and wd_name and top8 and ex10 is not None:
        for h in top8:
            ent = h.get("now")
            ex = _last_close(ex10, h["symbol"])
            if ent is None or ex is None:
                continue
            tr = _short_n(h, ent, ex, wd_name, NOTIONAL)
            if tr:
                wd_trades.append(tr)
    return {
        "session": iso,
        "top8": [
            {
                "symbol": h["symbol"],
                "residual": h["residual"],
                "prior_close": h["prior_close"],
                "prior_dv": h["prior_dv"],
                "now": h["now"],
            }
            for h in top8
        ],
        "n_res": len(rows),
        "wd_name": wd_name,
        "wd_trades": wd_trades,
        "skipped": "" if rows else "thin",
    }


def _standing_trades(
    study: list[date],
    by_iso: dict[str, dict],
) -> tuple[dict[str, list[dict]], list[int], list[int]]:
    """Walk sessions in order. Enter joiners, exit leavers, at last RTH that session."""
    idx = {d: i for i, d in enumerate(study)}
    trades_by: dict[str, list[dict]] = {}
    stints_is: list[int] = []
    stints_oos: list[int] = []
    prev: set[str] = set()
    held: dict[str, dict] = {}
    for d in study:
        rec = by_iso.get(d.isoformat()) or {}
        top = list(rec.get("top8") or [])
        today = {h["symbol"] for h in top}
        by_sym = {h["symbol"]: h for h in top}
        if rec.get("n_res", 0) < MIN_RESIDUAL:
            today = set(prev)
        else:
            for sym in stand_exits(prev, today):
                h = held.get(sym)
                if h is None:
                    continue
                ex = _last_close(d, sym)
                if ex is None:
                    held.pop(sym, None)
                    continue
                tr = _short_n(h["h"], h["ent"], ex, STAND_ID, NOTIONAL)
                if tr:
                    days = idx[d] - h["idx"]
                    tr["hold_days"] = days
                    iso_e = h["ent"][0].date().isoformat() if hasattr(h["ent"][0], "date") else d.isoformat()
                    trades_by.setdefault(iso_e, []).append(tr)
                    (stints_is if is_is_session(study[h["idx"]]) else stints_oos).append(days)
                held.pop(sym, None)
            if d != study[-1]:
                for sym in stand_enters(prev, today):
                    h = by_sym.get(sym)
                    if h is None or h.get("now") is None:
                        continue
                    held[sym] = {"h": h, "ent": h["now"], "idx": idx[d]}
            prev = today
    if study:
        last = study[-1]
        for sym, h in list(held.items()):
            ex = _last_close(last, sym)
            if ex is None:
                continue
            tr = _short_n(h["h"], h["ent"], ex, STAND_ID, NOTIONAL)
            if tr:
                days = idx[last] - h["idx"]
                tr["hold_days"] = days
                iso_e = h["ent"][0].date().isoformat() if hasattr(h["ent"][0], "date") else last.isoformat()
                trades_by.setdefault(iso_e, []).append(tr)
                (stints_is if is_is_session(study[h["idx"]]) else stints_oos).append(days)
    return trades_by, stints_is, stints_oos


def run_arrow52(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 52 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    last_of_week = rebalance_sessions(study)
    thu_low = [d for d in last_of_week if d.weekday() != 4]
    print(
        f"research start mode=arrow52 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"last_of_week={len(last_of_week)} non_friday_last_of_week={len(thu_low)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "weekday rank and standing top-8. Short only. $6000. lb=15 n=8. "
        "Did not combine weekday books into one portfolio. Id 0 reprints Arrow 51 lb15_h10. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 53.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable_wd: dict[str, list[date]] = {n: [] for n, _ in WEEKDAY_IDS}
    for d in study:
        look5 = session_shift(d, -LOOKBACK, feats)
        look15 = session_shift(d, -LB, feats)
        e5 = session_shift(d, 5, feats)
        e10 = session_shift(d, HOLD, feats)
        wd = weekday_id(d)
        do_wd = False
        if wd is not None and look15 is not None and e10 is not None:
            if (tape_root(e10) / e10.isoformat()).exists():
                if wd == CONTROL_ID:
                    if look5 is not None and e5 is not None and (tape_root(e5) / e5.isoformat()).exists():
                        do_wd = True
                else:
                    do_wd = True
        if do_wd:
            usable_wd[wd].append(d)
        i_l15 = _iwm_last_close(iwm, look15) if look15 is not None else None
        i1 = _iwm_last_close(iwm, d)
        jobs.append(
            (
                d.isoformat(),
                look15.isoformat() if look15 is not None else None,
                e10.isoformat() if e10 is not None else None,
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
                wd or "",
                do_wd,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} study_sessions={len(jobs)} "
        f"fri={len(usable_wd[CONTROL_ID])} mon={len(usable_wd['mon_h10'])} "
        f"tue={len(usable_wd['tue_h10'])} wed={len(usable_wd['wed_h10'])} "
        f"thu={len(usable_wd['thu_h10'])} short-only n=8 lb=15 $6000",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow52")
    prog.start_heartbeat()
    by_iso: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_session_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            by_iso[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 16 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in study
    }
    for iso, rec in by_iso.items():
        slot = chunks.setdefault(iso, {"trades": {k: [] for k in IDS}, "n_res": 0})
        slot["n_res"] = rec.get("n_res") or 0
        wd = rec.get("wd_name") or ""
        if wd and rec.get("wd_trades"):
            slot["trades"][wd] = list(rec["wd_trades"])

    stand_by, stints_is, stints_oos = _standing_trades(study, by_iso)
    for iso, trs in stand_by.items():
        slot = chunks.setdefault(iso, {"trades": {k: [] for k in IDS}, "n_res": 0})
        slot["trades"][STAND_ID] = list(trs)

    is_weeks_fri = [d for d in usable_wd[CONTROL_ID] if is_is_session(d)]
    sm0_is, _, _tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, is_weeks_fri)
    reprint_ok = _within(sm0_is["per_day"], A51_LB15_IS_DAY) and _within(sm0_is["n_trades"], A51_LB15_IS_N)
    subset_note = (
        f"A51 last-of-week n={A51_LB15_IS_N} IS $/day={A51_LB15_IS_DAY}. "
        f"Friday-only n={sm0_is['n_trades']} IS $/day={sm0_is['per_day']:.2f}. "
        f"Non-Friday last-of-week dates in A51 calendar: {len(thu_low)}"
        + (
            " (" + ", ".join(d.isoformat() for d in thu_low) + ")."
            if thu_low
            else "."
        )
    )
    if reprint_ok:
        reprint_line = (
            f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A51_LB15_IS_DAY} "
            f"n={sm0_is['n_trades']}/{A51_LB15_IS_N} — within ±10% of Arrow 51 lb15_h10. "
            "Scored Friday-only (did not roll last-of-week Thursdays onto Friday). "
            + subset_note
        )
    else:
        reprint_line = (
            f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A51_LB15_IS_DAY} "
            f"n={sm0_is['n_trades']}/{A51_LB15_IS_N} — outside ±10% of Arrow 51 lb15_h10. "
            + subset_note
        )
    print(reprint_line, flush=True)
    if not reprint_ok and not thu_low:
        text = (
            "Arrow 52 — weekday rank and standing top-8 (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 51 lb15_h10 and last-of-week had no extra Thursdays. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 53.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow52_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1
    if not reprint_ok and thu_low:
        reprint_line += (
            " Friday-only n differs because Arrow 51 used last-of-week including Thursdays. "
            "Printed both. Still scored the other ids. Did not roll those Thursdays onto Friday."
        )
        print(reprint_line, flush=True)

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, _dow in WEEKDAY_IDS:
        weeks = [d for d in usable_wd[name]]
        is_w = [d for d in weeks if is_is_session(d)]
        oos_w = [d for d in weeks if not is_is_session(d)]
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        deployed = TWO_COHORT
        fits = deployed <= ACCOUNT + 1e-12
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        slate = sm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_is["per_day"] >= 0.0 and fits
        if name == CONTROL_ID:
            ctrl_is = sm_is["per_day"]
            ctrl_oos = sm_oos["per_day"]
        lift_both = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = sm_is["per_day"] > ctrl_is + 1e-12 and sm_oos["per_day"] > ctrl_oos + 1e-12
        results.append(
            {
                "name": name,
                "kind": "weekday",
                "per": "week",
                "deployed": deployed,
                "fits": fits,
                "is": sm_is,
                "oos": sm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "seat": seat,
                "slate": slate,
                "lift_both": lift_both,
                "oos_excludes": sm_oos["ci_lo"] > 0 or sm_oos["ci_hi"] < 0,
                "stay_is": "",
                "stay_oos": "",
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
                "n_reb": len(weeks),
            }
        )

    sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, STAND_ID, is_sess)
    sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, STAND_ID, oos_sess)
    sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
    sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
    sm_is["peak_conc"] = N_SHORT
    sm_oos["peak_conc"] = N_SHORT
    sm_is["mean_conc"] = float(N_SHORT)
    sm_oos["mean_conc"] = float(N_SHORT)
    a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
    a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
    deployed = ONE_COHORT
    fits = deployed <= ACCOUNT + 1e-12
    seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
    slate = sm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_is["per_day"] >= 0.0 and fits
    lift_both = (
        ctrl_is is not None
        and ctrl_oos is not None
        and sm_is["per_day"] > ctrl_is + 1e-12
        and sm_oos["per_day"] > ctrl_oos + 1e-12
    )
    results.append(
        {
            "name": STAND_ID,
            "kind": "standing",
            "per": "sess",
            "deployed": deployed,
            "fits": fits,
            "is": sm_is,
            "oos": sm_oos,
            "a_is": a_is,
            "a_oos": a_oos,
            "skip_is": skip_is,
            "skip_oos": skip_oos,
            "n_a_is": n_is,
            "n_a_oos": n_oos,
            "seat": seat,
            "slate": slate,
            "lift_both": lift_both,
            "oos_excludes": sm_oos["ci_lo"] > 0 or sm_oos["ci_hi"] < 0,
            "stay_is": _median_stay(stints_is),
            "stay_oos": _median_stay(stints_oos),
            "is_months": _month_lines(day_is, is_sess),
            "oos_months": _month_lines(day_oos, oos_sess),
            "n_reb": len(study),
        }
    )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    wd_seat = [r["name"] for r in results if r["kind"] == "weekday" and r["seat"]]
    wd_slate = [r["name"] for r in results if r["kind"] == "weekday" and r["slate"]]
    wd_both = [r["name"] for r in results if r["kind"] == "weekday" and r["lift_both"]]
    stand = next(r for r in results if r["name"] == STAND_ID)
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 52 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    wd_seat_s = ", ".join(wd_seat) if wd_seat else "none"
    wd_slate_s = ", ".join(wd_slate) if wd_slate else "none"
    wd_both_s = ", ".join(wd_both) if wd_both else "none"
    stand_line = (
        f"stand_top8 is a seat (OOS ${stand['oos']['per_day']:.2f}/day)."
        if stand["seat"]
        else f"stand_top8 is not a seat (OOS ${stand['oos']['per_day']:.2f}/day)."
    )
    honesty = (
        "Short only. Weekday books scored apart; did not combine them into one portfolio. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "Did not roll a holiday weekday onto the next day. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and live notional <= $100k. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 53."
    )
    lines = [
        "Arrow 52 — weekday rank and standing top-8 (IS / OOS)",
        verdict,
        reprint_line,
        f"Weekdays that clear seat ${SEAT_FLOOR:.0f}/day: {wd_seat_s}.",
        f"Weekdays that clear slate ${FAILURE_LINE:.0f}/day with live notional fit: {wd_slate_s}.",
        f"Weekdays that lift $/day versus Friday on both IS and OOS: {wd_both_s}.",
        stand_line,
        f"Ids that lift $/day versus control on both IS and OOS: {both_s}.",
        f"Ids that clear seat ${SEAT_FLOOR:.0f}: {seat_s}.  slate: {slate_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 44–51, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  n=8  lb=15  ${NOTIONAL:.0f}/name  entry last RTH",
        "Skip a rebalance if fewer than 16 eligible names have a residual. "
        "Skip a name if a required fill is missing. Holiday weekday: skip that id's week; do not roll.",
        "",
        f"IS character id 5 {STAND_ID} stay in book: {stand['stay_is']}. Description. Does not pick an id.",
        "",
        f"{'id':<14} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'vs0':>6} {'seat':>5}",
    ]
    for r in results:
        for split, sm, a, skip, n_a, months, stay in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"], r["stay_is"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"], r["stay_oos"]),
        ):
            vs = "ctrl"
            if r["name"] != CONTROL_ID and ctrl_is is not None and ctrl_oos is not None:
                base = ctrl_is if split == "IS" else ctrl_oos
                vs = f"{sm['per_day'] - base:+.1f}"
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
            lines.extend(_fmt_book52(sm, per=r["per"]))
            extra = f"  entry=close hold={HOLD} lb={LB}" if r["kind"] == "weekday" else "  standing top-8 no clock"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={N_SHORT} notional=${NOTIONAL:.0f}{extra}{_ci_note(sm)}"
            )
            lines.append(
                f"    deployed $={r['deployed']:.0f}  fits_100k={'yes' if r['fits'] else 'NO'}  "
                f"rebalances={r['n_reb']}"
            )
            if r["name"] == STAND_ID:
                lines.append(f"    stay in book {split}: {stay}")
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow52_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow52_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 52",
        "",
        verdict,
        "",
        reprint_line,
        f"Weekday seat: {wd_seat_s}.  Weekday slate: {wd_slate_s}.  Weekday lift-both vs Friday: {wd_both_s}.",
        stand_line,
        f"Lift vs control on both IS and OOS: {both_s}.",
        "Short only. Weekday books scored apart. Did not combine them. lb=15 n=8 $6k. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 53.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r["lift_both"] else "")
            + ("  OOS CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
