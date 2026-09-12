"""Arrow 51 — rank 15 parent and giveback path. Short only. $6,000."""

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
    _last_close,
    _month_lines,
    residual,
)
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow50 import _give5_frac, give5_hold
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
from research.signals import MINUTE_1559, RTH_OPEN

ET = ZoneInfo("America/New_York")
A50_LB15_IS_DAY = 575.43
A50_LB15_IS_N = 129
CONTROL_ID = "lb15_h10"
GIVE5_ID = "lb15_give5"
H15_ID = "lb15_h15"
NOTIONAL = 6000.0
N_SHORT = 8
MIN_RESIDUAL = 16
# name, lookback, exit
EXPERIMENTS = (
    ("lb15_h10", 15, "h10"),
    ("lb15_give5", 15, "give5"),
    ("lb15_h5", 15, "h5"),
    ("lb20_h10", 20, "h10"),
    ("lb12_h10", 12, "h10"),
    ("lb15_h15", 15, "h15"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _cohort_fit(name: str, n_plus10: int) -> tuple[float, float, float, bool]:
    one = float(N_SHORT) * NOTIONAL
    two = 2.0 * one
    three = 3.0 * one
    if name == "lb15_h5":
        used = one
    elif name == GIVE5_ID:
        used = two if n_plus10 > 0 else one
    elif name == H15_ID:
        used = three
    else:
        used = two
    return one, two, three, used <= ACCOUNT + 1e-12


def _ci_note(sm: dict) -> str:
    if sm["ci_lo"] > 0 or sm["ci_hi"] < 0:
        return "  CI excludes 0"
    if sm["ci_lo"] <= 0 <= sm["ci_hi"]:
        return "  CI includes 0 — not EV"
    return ""


def _week_job(args: tuple) -> dict:
    (
        iso,
        look12_iso,
        look15_iso,
        look20_iso,
        exit5_iso,
        exit10_iso,
        exit15_iso,
        names,
        iwm_l12,
        iwm_l15,
        iwm_l20,
        iwm1,
    ) = args
    session = date.fromisoformat(iso)
    look12 = date.fromisoformat(look12_iso) if look12_iso else None
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
    look20 = date.fromisoformat(look20_iso) if look20_iso else None
    ex5 = date.fromisoformat(exit5_iso) if exit5_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    ex15 = date.fromisoformat(exit15_iso) if exit15_iso else None
    empty = {
        "session": iso,
        "trades": {k: [] for k in IDS},
        "n_res12": 0,
        "n_res15": 0,
        "n_res20": 0,
        "skipped": "no_names",
    }
    if not names or iwm1 is None or iwm1 <= 0:
        empty["skipped"] = "iwm"
        return empty

    def _res(look: date | None, iwm_l: float | None, now: tuple, sym: str) -> float | None:
        if look is None or iwm_l is None or iwm_l <= 0:
            return None
        a = _last_close(look, sym)
        if a is None:
            return None
        return residual(a[1], now[1], iwm_l, iwm1)

    rows12: list[dict] = []
    rows15: list[dict] = []
    rows20: list[dict] = []
    closes_r: dict[str, tuple] = {}
    closes_5: dict[str, tuple] = {}
    closes_10: dict[str, tuple] = {}
    closes_15: dict[str, tuple] = {}
    for h in names:
        sym = h["symbol"]
        now = _last_close(session, sym)
        if now is None:
            continue
        r12 = _res(look12, iwm_l12, now, sym)
        r15 = _res(look15, iwm_l15, now, sym)
        r20 = _res(look20, iwm_l20, now, sym)
        if r12 is None and r15 is None and r20 is None:
            continue
        closes_r[sym] = now
        if ex5 is not None:
            c5 = _last_close(ex5, sym)
            if c5 is not None:
                closes_5[sym] = c5
        if ex10 is not None:
            c10 = _last_close(ex10, sym)
            if c10 is not None:
                closes_10[sym] = c10
        if ex15 is not None:
            c15 = _last_close(ex15, sym)
            if c15 is not None:
                closes_15[sym] = c15
        rec = {**h}
        if r12 is not None:
            rows12.append({**rec, "residual": r12})
        if r15 is not None:
            rows15.append({**rec, "residual": r15})
        if r20 is not None:
            rows20.append({**rec, "residual": r20})
    trades = {k: [] for k in IDS}
    pools = {12: rows12, 15: rows15, 20: rows20}
    if all(len(p) < MIN_RESIDUAL for p in pools.values()):
        return {
            "session": iso,
            "trades": trades,
            "n_res12": len(rows12),
            "n_res15": len(rows15),
            "n_res20": len(rows20),
            "skipped": "thin",
        }
    for name, lb, exit_kind in EXPERIMENTS:
        pool = pools[lb]
        if len(pool) < MIN_RESIDUAL:
            continue
        picks = select_shorts(pool, N_SHORT, None)
        for h in picks:
            sym = h["symbol"]
            ent = closes_r.get(sym)
            if ent is None:
                continue
            hold = 10
            if exit_kind == "h5":
                ex = closes_5.get(sym)
                hold = 5
            elif exit_kind == "h15":
                ex = closes_15.get(sym)
                hold = 15
            elif exit_kind == "give5":
                px5 = closes_5[sym][1] if sym in closes_5 else None
                px10 = closes_10[sym][1] if sym in closes_10 else None
                hold_n = give5_hold(ent[1], px5, px10)
                if hold_n is None:
                    continue
                hold = hold_n
                ex = closes_5.get(sym) if hold == 5 else closes_10.get(sym)
            else:
                ex = closes_10.get(sym)
            if ex is None:
                continue
            tr = _short_n(h, ent, ex, name, NOTIONAL)
            if tr:
                tr["hold"] = hold
                trades[name].append(tr)
    return {
        "session": iso,
        "trades": trades,
        "n_res12": len(rows12),
        "n_res15": len(rows15),
        "n_res20": len(rows20),
        "skipped": "",
    }


def run_arrow51(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 51 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    reb = rebalance_sessions(study)
    print(
        f"research start mode=arrow51 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"rebalance_weeks={len(reb)} jan_tape={tape_root(date(2026, 1, 2))} "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "rank 15 parent and giveback path. Short only. $6000. Friday last-RTH. "
        "Id 0 reprints Arrow 50 lb15_fri_h10. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg or a Monday id. Did not retune Arrow 43 clocks or frozen B/flush. "
        "No new ingest. No Arrow 52.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable: list[date] = []
    for r in reb:
        look5 = session_shift(r, -LOOKBACK, feats)
        look12 = session_shift(r, -12, feats)
        look15 = session_shift(r, -15, feats)
        look20 = session_shift(r, -20, feats)
        e5 = session_shift(r, 5, feats)
        e10 = session_shift(r, 10, feats)
        e15 = session_shift(r, 15, feats)
        if look5 is None or e5 is None:
            continue
        if not (tape_root(e5) / e5.isoformat()).exists():
            continue
        if e10 is None or not (tape_root(e10) / e10.isoformat()).exists():
            continue
        i_l12 = _iwm_last_close(iwm, look12) if look12 is not None else None
        i_l15 = _iwm_last_close(iwm, look15) if look15 is not None else None
        i_l20 = _iwm_last_close(iwm, look20) if look20 is not None else None
        i1 = _iwm_last_close(iwm, r)
        usable.append(r)
        jobs.append(
            (
                r.isoformat(),
                look12.isoformat() if look12 is not None else None,
                look15.isoformat() if look15 is not None else None,
                look20.isoformat() if look20 is not None else None,
                e5.isoformat(),
                e10.isoformat(),
                e15.isoformat() if e15 is not None else None,
                by.get(r.isoformat(), []),
                i_l12[1] if i_l12 else None,
                i_l15[1] if i_l15 else None,
                i_l20[1] if i_l20 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} weeks={len(jobs)} short-only n=8 control lb=15 $6000 last-RTH",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow51")
    prog.start_heartbeat()
    chunks: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_week_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            chunks[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 4 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    is_weeks = [d for d in usable if is_is_session(d)]
    oos_weeks = [d for d in usable if not is_is_session(d)]
    sm0_is, _, _tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, is_weeks)
    reprint_ok = _within(sm0_is["per_day"], A50_LB15_IS_DAY) and _within(sm0_is["n_trades"], A50_LB15_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A50_LB15_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A50_LB15_IS_N} "
        + (
            "— within ±10% of Arrow 50 lb15_fri_h10."
            if reprint_ok
            else "— DRIFT beyond ±10%. Rings not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 51 — rank 15 parent and giveback path (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 50 lb15_fri_h10. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 52.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow51_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, lb, exit_kind in EXPERIMENTS:
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_weeks)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_weeks)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        _n5_is, n10_is, frac_is = _give5_frac(tr_is)
        _n5_oos, n10_oos, frac_oos = _give5_frac(tr_oos)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        one, two, three, fits = _cohort_fit(name, n10_is + n10_oos)
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        slate = sm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_is["per_day"] >= 0.0 and fits
        if name == CONTROL_ID:
            ctrl_is = sm_is["per_day"]
            ctrl_oos = sm_oos["per_day"]
        lift_both = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = sm_is["per_day"] > ctrl_is + 1e-12 and sm_oos["per_day"] > ctrl_oos + 1e-12
        oos_excludes = sm_oos["ci_lo"] > 0 or sm_oos["ci_hi"] < 0
        results.append(
            {
                "name": name,
                "lb": lb,
                "exit_kind": exit_kind,
                "one": one,
                "two": two,
                "three": three,
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
                "oos_excludes": oos_excludes,
                "frac_is": frac_is,
                "frac_oos": frac_oos,
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    oos_ex = [r["name"] for r in results if r["oos_excludes"]]
    by_name = {r["name"]: r for r in results}
    give = by_name[GIVE5_ID]
    give_both = give["lift_both"]
    give_line = (
        f"Give5 on rank 15 {'lifted both slices versus control.' if give_both else 'did not lift both slices versus control.'} "
        f"IS {give['frac_is']}  OOS {give['frac_oos']}."
    )
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 51 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    oos_ex_s = ", ".join(oos_ex) if oos_ex else "none"
    honesty = (
        "Short only. Friday last-RTH. Rings locked from IS; OOS is one look for the family. "
        "Did not drop an id after seeing OOS. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg or a Monday id. Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and overlapping-cohort notional <= $100k "
        "(hold 5 is one cohort; hold 10 is two; hold 15 is three; give5 is two if any name stays past +5). "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 52."
    )
    lines = [
        "Arrow 51 — rank 15 parent and giveback path (IS / OOS)",
        verdict,
        reprint_line,
        f"Ids that lift $/day versus control on both IS and OOS: {both_s}.",
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and overlapping-cohort fit: {slate_s}.",
        give_line,
        f"OOS CI excludes 0: {oos_ex_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"rebalance weeks={len(jobs)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 44–50, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  n=8  ${NOTIONAL:.0f}/name  entry last RTH",
        "Skip week if fewer than 16 eligible names have a residual. Skip a name if a required fill is missing.",
        "",
        f"IS character id 1 {GIVE5_ID} exit +5 vs +10: {give['frac_is']}. Description. Does not pick an id.",
        "",
        f"{'id':<14} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'vs0':>6} {'seat':>5}",
    ]
    for r in results:
        for split, sm, a, skip, n_a, months, frac in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"], r["frac_is"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"], r["frac_oos"]),
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
            lines.extend(_fmt_book48(sm))
            fit_s = "yes" if r["fits"] else "NO"
            extra = f"  entry=close exit={r['exit_kind']} lb={r['lb']}"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={N_SHORT} notional=${NOTIONAL:.0f}{extra}{_ci_note(sm)}"
            )
            cohort = (
                f"    one-cohort $={r['one']:.0f}  two-cohort $={r['two']:.0f}  "
                f"fits_100k={fit_s}"
            )
            if r["name"] == H15_ID:
                cohort += f"  three-cohort $={r['three']:.0f}"
            lines.append(cohort)
            if r["name"] == GIVE5_ID:
                lines.append(f"    give5 {split} +5 vs +10: {frac}")
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow51_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow51_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 51",
        "",
        verdict,
        "",
        reprint_line,
        f"Lift vs control on both IS and OOS: {both_s}.",
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.",
        f"Slate ${FAILURE_LINE:.0f} on OOS with IS not red and overlapping-cohort fit: {slate_s}.",
        give_line,
        f"OOS CI excludes 0: {oos_ex_s}.",
        "Short only. n=8 $6k Friday last-RTH. Rank 15 parent. Rings locked from IS. One OOS look. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg or a Monday id. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 52.",
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
