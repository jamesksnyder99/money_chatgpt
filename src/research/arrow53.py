"""Arrow 53 — group leftover. Short only. Friday vs IWM is control."""

from __future__ import annotations

import math
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
)
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
A52_FRI_IS_DAY = 495.38
A52_FRI_IS_N = 121
CONTROL_ID = "vs_iwm"
UNIV_ID = "vs_univ"
WED_ID = "wed_vs_univ"
NOTIONAL = 6000.0
N_SHORT = 8
MIN_RESIDUAL = 16
MIN_PEER = 8
LB = 15
HOLD = 10
TWO_COHORT = 2.0 * float(N_SHORT) * NOTIONAL
# name, weekday (Mon=0), bench
EXPERIMENTS = (
    ("vs_iwm", 4, "iwm"),
    ("vs_univ", 4, "univ"),
    ("vs_px", 4, "px"),
    ("vs_pdv", 4, "pdv"),
    ("vs_px_iwm", 4, "px_iwm"),
    ("wed_vs_univ", 2, "univ"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
FRI_IDS = tuple(e[0] for e in EXPERIMENTS if e[1] == 4)


def name_return(px0: float, px1: float) -> float | None:
    if not math.isfinite(px0) or not math.isfinite(px1) or px0 <= 0 or px1 <= 0:
        return None
    return px1 / px0 - 1.0


def residual_vs_iwm(name_ret: float, iwm_ret: float) -> float:
    return name_ret - iwm_ret


def residual_vs_median(name_ret: float, med: float) -> float:
    return name_ret - med


def residual_vs_px_iwm(name_ret: float, bucket_med: float, iwm_ret: float) -> float:
    return name_ret - bucket_med - iwm_ret


def price_bucket(prior_close: float) -> int | None:
    """[$10,$20), [$20,$40), [$40,$80]. None if off the wall."""
    if not math.isfinite(prior_close):
        return None
    if 10.0 <= prior_close < 20.0:
        return 0
    if 20.0 <= prior_close < 40.0:
        return 1
    if 40.0 <= prior_close <= 80.0:
        return 2
    return None


def assign_pdv_terciles(rows: list[dict]) -> None:
    s = sorted(rows, key=lambda r: (float(r["prior_dv"]), str(r["symbol"])))
    n = len(s)
    a, b = n // 3, 2 * n // 3
    for i, r in enumerate(s):
        r["pdv_tercile"] = 0 if i < a else (1 if i < b else 2)


def _group_median(rows: list[dict], key: str, val: int) -> float | None:
    xs = [float(r["name_ret"]) for r in rows if r.get(key) == val]
    if len(xs) < MIN_PEER:
        return None
    return float(statistics.median(xs))


def _rebalance_job(args: tuple) -> dict:
    (
        iso,
        look15_iso,
        exit10_iso,
        names,
        iwm_l15,
        iwm1,
        wd,
    ) = args
    session = date.fromisoformat(iso)
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    empty = {
        "session": iso,
        "trades": {k: [] for k in IDS},
        "picks": {k: [] for k in IDS},
        "n_res": 0,
        "skipped": "no_names",
    }
    if not names or look15 is None or iwm1 is None or iwm1 <= 0:
        empty["skipped"] = "iwm"
        return empty
    iwm_ret = None
    if iwm_l15 is not None and iwm_l15 > 0:
        iwm_ret = name_return(iwm_l15, iwm1)
    rows = []
    closes_x: dict[str, tuple] = {}
    for h in names:
        sym = h["symbol"]
        now = _last_close(session, sym)
        if now is None:
            continue
        a15 = _last_close(look15, sym)
        if a15 is None:
            continue
        nr = name_return(a15[1], now[1])
        if nr is None:
            continue
        rec = {**h, "name_ret": nr, "now": now, "px_bucket": price_bucket(h["prior_close"])}
        rows.append(rec)
        if ex10 is not None:
            cx = _last_close(ex10, sym)
            if cx is not None:
                closes_x[sym] = cx
    trades = {k: [] for k in IDS}
    picks = {k: [] for k in IDS}
    if len(rows) < MIN_RESIDUAL:
        return {
            "session": iso,
            "trades": trades,
            "picks": picks,
            "n_res": len(rows),
            "skipped": "thin",
        }
    assign_pdv_terciles(rows)
    univ_med = float(statistics.median([r["name_ret"] for r in rows]))
    px_med = {b: _group_median(rows, "px_bucket", b) for b in (0, 1, 2)}
    pdv_med = {t: _group_median(rows, "pdv_tercile", t) for t in (0, 1, 2)}
    id_rows: dict[str, list[dict]] = {k: [] for k in IDS}
    for r in rows:
        nr = r["name_ret"]
        if iwm_ret is not None:
            id_rows["vs_iwm"].append({**r, "residual": residual_vs_iwm(nr, iwm_ret)})
        id_rows["vs_univ"].append({**r, "residual": residual_vs_median(nr, univ_med)})
        id_rows["wed_vs_univ"].append({**r, "residual": residual_vs_median(nr, univ_med)})
        b = r["px_bucket"]
        if b is not None and px_med.get(b) is not None:
            id_rows["vs_px"].append({**r, "residual": residual_vs_median(nr, px_med[b])})
            if iwm_ret is not None:
                id_rows["vs_px_iwm"].append(
                    {**r, "residual": residual_vs_px_iwm(nr, px_med[b], iwm_ret)}
                )
        t = r.get("pdv_tercile")
        if t is not None and pdv_med.get(t) is not None:
            id_rows["vs_pdv"].append({**r, "residual": residual_vs_median(nr, pdv_med[t])})
    want = FRI_IDS if wd == 4 else (WED_ID,)
    for name in want:
        pool = id_rows[name]
        if len(pool) < MIN_RESIDUAL:
            continue
        chosen = select_shorts(pool, N_SHORT, None)
        picks[name] = [h["symbol"] for h in chosen]
        for h in chosen:
            ent = h.get("now")
            ex = closes_x.get(h["symbol"])
            if ent is None or ex is None:
                continue
            tr = _short_n(h, ent, ex, name, NOTIONAL)
            if tr:
                trades[name].append(tr)
    return {
        "session": iso,
        "trades": trades,
        "picks": picks,
        "n_res": len(rows),
        "skipped": "",
    }


def run_arrow53(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 53 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow53 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "group leftover. Short only. $6000. lb=15 n=8. Friday last-RTH hold 10. "
        "Id 0 reprints Arrow 52 fri_h10 vs IWM. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg. Did not retune Arrow 43 clocks or frozen B/flush. "
        "No new ingest. No Arrow 54.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable: dict[str, list[date]] = {k: [] for k in IDS}
    for d in study:
        wd = d.weekday()
        if wd not in (2, 4):
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
        if wd == 4:
            for name in FRI_IDS:
                usable[name].append(d)
        else:
            usable[WED_ID].append(d)
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
        f"name-days={elig.height} jobs={len(jobs)} fri={len(usable[CONTROL_ID])} "
        f"wed={len(usable[WED_ID])} short-only n=8 lb=15 $6000",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow53")
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

    chunks: dict[str, dict] = {}
    for iso, rec in recs.items():
        chunks[iso] = {"trades": rec.get("trades") or {k: [] for k in IDS}, "n_res": rec.get("n_res") or 0}

    is_fridays = [d for d in usable[CONTROL_ID] if is_is_session(d)]
    sm0_is, _, _tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, is_fridays)
    reprint_ok = _within(sm0_is["per_day"], A52_FRI_IS_DAY) and _within(sm0_is["n_trades"], A52_FRI_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A52_FRI_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A52_FRI_IS_N} "
        + (
            "— within ±10% of Arrow 52 fri_h10."
            if reprint_ok
            else "— DRIFT beyond ±10%. Rings not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 53 — group leftover (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 52 fri_h10. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 54.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow53_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    overlap = []
    for d in is_fridays:
        rec = recs.get(d.isoformat()) or {}
        a = set((rec.get("picks") or {}).get(CONTROL_ID) or [])
        b = set((rec.get("picks") or {}).get(UNIV_ID) or [])
        if len(a) == N_SHORT and len(b) == N_SHORT:
            overlap.append(len(a & b))
    if overlap:
        mean_ov = sum(overlap) / len(overlap)
        ov_line = (
            f"vs_univ vs vs_iwm IS Friday overlap: mean {mean_ov:.2f}/8 names in common "
            f"(n_fridays={len(overlap)}). "
            + (
                "Same book."
                if mean_ov >= 8 - 1e-9
                else "Different book than vs_iwm."
            )
        )
    else:
        ov_line = "vs_univ vs vs_iwm IS Friday overlap: n=0."

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, _wd, bench in EXPERIMENTS:
        weeks = usable[name]
        is_w = [d for d in weeks if is_is_session(d)]
        oos_w = [d for d in weeks if not is_is_session(d)]
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        fits = TWO_COHORT <= ACCOUNT + 1e-12
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
                "bench": bench,
                "wd": _wd,
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
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
                "n_reb": len(weeks),
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 53 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    honesty = (
        "Short only. Friday last-RTH hold 10 except wed_vs_univ. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and two-cohort notional <= $100k. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 54."
    )
    lines = [
        "Arrow 53 — group leftover (IS / OOS)",
        verdict,
        reprint_line,
        f"Ids that lift $/day versus vs_iwm on both IS and OOS: {both_s}.",
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and two-cohort fit: {slate_s}.",
        ov_line,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"friday rebalances={len(usable[CONTROL_ID])}  wednesday rebalances={len(usable[WED_ID])}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 44–52, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  n=8  lb=15  ${NOTIONAL:.0f}/name  "
        f"entry last RTH  hold=10  two-cohort $={TWO_COHORT:.0f}",
        "Skip a Friday if fewer than 16 eligible names have a residual. "
        "Price/PDV peer set with fewer than 8 names: drop the name from that id only.",
        "",
        f"{'id':<14} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
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
                f"{r['name']:<14} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} {vs:>6} {flag:>5}"
            )
            lines.extend(_fmt_book48(sm))
            wd = "Friday" if r["wd"] == 4 else "Wednesday"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={N_SHORT} notional=${NOTIONAL:.0f}  {wd}  bench={r['bench']}  "
                f"lb={LB} hold={HOLD}{_ci_note(sm)}"
            )
            lines.append(
                f"    deployed $={TWO_COHORT:.0f}  fits_100k=yes  rebalances={r['n_reb']}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow53_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow53_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 53",
        "",
        verdict,
        "",
        reprint_line,
        ov_line,
        f"Lift vs vs_iwm on both IS and OOS: {both_s}.",
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.  Slate ${FAILURE_LINE:.0f}: {slate_s}.",
        "Short only. Group leftover. Friday last-RTH hold 10 except wed_vs_univ. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 54.",
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
