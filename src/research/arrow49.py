"""Arrow 49 — n8 scale toward slate. Short only."""

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
from research.arrow48 import _fmt_book48, _scale_line, _wins_losses
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
A48_N8_IS_DAY = 185.30
A48_N8_IS_N = 135
CONTROL_ID = "n8_h10_3k"
MIN_RESIDUAL = 16
LB = 10
# name, n_short, hold, notional
EXPERIMENTS = (
    ("n8_h10_3k", 8, 10, 3000.0),
    ("n8_h10_4k", 8, 10, 4000.0),
    ("n8_h10_5k", 8, 10, 5000.0),
    ("n8_h10_6k", 8, 10, 6000.0),
    ("n8_h5_4k", 8, 5, 4000.0),
    ("n8_h5_5k", 8, 5, 5000.0),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
SCALE_IDS = ("n8_h10_4k", "n8_h10_5k", "n8_h10_6k")
SCALE_EXPECT = (4000.0 / 3000.0, 5000.0 / 3000.0, 6000.0 / 3000.0)


def _deployed(n_short: int, notional: float) -> tuple[float, float, bool]:
    one = float(n_short) * float(notional)
    two = 2.0 * one
    return one, two, two <= ACCOUNT + 1e-12


def _week_job(args: tuple) -> dict:
    (
        iso,
        look10_iso,
        exit5_iso,
        exit10_iso,
        names,
        iwm_l10,
        iwm1,
    ) = args
    session = date.fromisoformat(iso)
    look10 = date.fromisoformat(look10_iso) if look10_iso else None
    ex5 = date.fromisoformat(exit5_iso) if exit5_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    empty = {
        "session": iso,
        "trades": {k: [] for k in IDS},
        "n_res10": 0,
        "skipped": "no_names",
    }
    if not names or look10 is None or iwm_l10 is None or iwm1 is None or iwm_l10 <= 0 or iwm1 <= 0:
        empty["skipped"] = "iwm"
        return empty
    rows = []
    closes_r: dict[str, tuple] = {}
    closes_5: dict[str, tuple] = {}
    closes_10: dict[str, tuple] = {}
    for h in names:
        sym = h["symbol"]
        now = _last_close(session, sym)
        if now is None:
            continue
        a10 = _last_close(look10, sym)
        if a10 is None:
            continue
        res = residual(a10[1], now[1], iwm_l10, iwm1)
        if res is None:
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
        rows.append({**h, "residual": res})
    trades = {k: [] for k in IDS}
    if len(rows) < MIN_RESIDUAL:
        return {
            "session": iso,
            "trades": trades,
            "n_res10": len(rows),
            "skipped": "thin",
        }
    for name, n_short, hold, notional in EXPERIMENTS:
        picks = select_shorts(rows, n_short, None)
        exits = closes_5 if hold == 5 else closes_10
        for h in picks:
            ent = closes_r.get(h["symbol"])
            ex = exits.get(h["symbol"])
            if ent is None or ex is None:
                continue
            tr = _short_n(h, ent, ex, name, notional)
            if tr:
                trades[name].append(tr)
    return {
        "session": iso,
        "trades": trades,
        "n_res10": len(rows),
        "skipped": "",
    }


def run_arrow49(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 49 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    reb = rebalance_sessions(study)
    print(
        f"research start mode=arrow49 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"rebalance_weeks={len(reb)} jan_tape={tape_root(date(2026, 1, 2))} "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "n8 scale toward slate. Short only. Id 0 reprints Arrow 48 n8_h10_3k. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 50.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable: list[date] = []
    for r in reb:
        look5 = session_shift(r, -LOOKBACK, feats)
        look10 = session_shift(r, -10, feats)
        e5 = session_shift(r, 5, feats)
        e10 = session_shift(r, 10, feats)
        if look5 is None or e5 is None:
            continue
        if not (tape_root(e5) / e5.isoformat()).exists():
            continue
        if e10 is None or not (tape_root(e10) / e10.isoformat()).exists():
            continue
        i_l10 = _iwm_last_close(iwm, look10) if look10 is not None else None
        i1 = _iwm_last_close(iwm, r)
        usable.append(r)
        jobs.append(
            (
                r.isoformat(),
                look10.isoformat() if look10 is not None else None,
                e5.isoformat(),
                e10.isoformat(),
                by.get(r.isoformat(), []),
                i_l10[1] if i_l10 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} weeks={len(jobs)} short-only lb=10 n=8 control $3000",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow49")
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
    reprint_ok = _within(sm0_is["per_day"], A48_N8_IS_DAY) and _within(sm0_is["n_trades"], A48_N8_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A48_N8_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A48_N8_IS_N} "
        + (
            "— within ±10% of Arrow 48 n8_h10_3k."
            if reprint_ok
            else "— DRIFT beyond ±10%. Rings not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 49 — n8 scale toward slate (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 48 n8_h10_3k. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 50.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow49_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, n_short, hold, notional in EXPERIMENTS:
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_weeks)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_weeks)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        one, two, fits = _deployed(n_short, notional)
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        slate = (
            sm_oos["per_day"] >= FAILURE_LINE - 1e-12
            and sm_is["per_day"] >= 0.0
            and fits
        )
        if name == CONTROL_ID:
            ctrl_is = sm_is["per_day"]
            ctrl_oos = sm_oos["per_day"]
        lift_both = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = sm_is["per_day"] > ctrl_is + 1e-12 and sm_oos["per_day"] > ctrl_oos + 1e-12
        results.append(
            {
                "name": name,
                "n_short": n_short,
                "lb": LB,
                "hold": hold,
                "notional": notional,
                "one": one,
                "two": two,
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
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    by_name = {r["name"]: r for r in results}
    scale_lines = []
    for sid, exp in zip(SCALE_IDS, SCALE_EXPECT, strict=True):
        r = by_name[sid]
        scale_lines.append(
            _scale_line(
                f"{sid} ${r['notional']:.0f} / id 0 $3000",
                r["is"]["per_day"],
                r["oos"]["per_day"],
                ctrl_is,
                ctrl_oos,
                exp,
            )
        )
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 49 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    honesty = (
        "Short only. Rings locked from IS; OOS is one look for the family. "
        "Did not drop an id after seeing OOS. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg. Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and two-cohort notional <= $100k. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 50."
    )
    lines = [
        "Arrow 49 — n8 scale toward slate (IS / OOS)",
        verdict,
        reprint_line,
        *scale_lines,
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and two-cohort fit: {slate_s}.",
        f"Ids that lift $/day versus control on both IS and OOS: {both_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"rebalance weeks={len(jobs)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 44–48, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  lb=10  n=8",
        "Skip week if fewer than 16 eligible names have a residual. Skip a name if a required close is missing.",
        "",
        f"{'id':<12} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'vs0':>6} {'seat':>5}",
    ]
    for r in results:
        for split, sm, a, skip, n_a, months in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"]),
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
                f"{r['name']:<12} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} {vs:>6} {flag:>5}"
            )
            lines.extend(_fmt_book48(sm))
            ci_note = ""
            if split == "OOS" and sm["ci_lo"] <= 0 <= sm["ci_hi"]:
                ci_note = "  CI includes 0 — not EV"
            fit_s = "yes" if r["fits"] else "NO"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={r['n_short']} lb={r['lb']} hold={r['hold']}  "
                f"notional=${r['notional']:.0f}{ci_note}"
            )
            lines.append(
                f"    one-cohort $={r['one']:.0f}  two-cohort $={r['two']:.0f}  "
                f"fits_100k={fit_s}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow49_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow49_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 49",
        "",
        verdict,
        "",
        reprint_line,
        *scale_lines,
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.",
        f"Slate ${FAILURE_LINE:.0f} on OOS with IS not red and two-cohort fit: {slate_s}.",
        f"Lift vs control on both IS and OOS: {both_s}.",
        "Short only. lb=10 n=8. Rings locked from IS. One OOS look. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 50.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            f"one=${r['one']:.0f} two=${r['two']:.0f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r["lift_both"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
