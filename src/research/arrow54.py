"""Arrow 54 — fade into the Friday fill. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, first_rth, last_rth, load_combined_iwm
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
    session_bar_path,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
A53_PLAIN_IS_DAY = 495.38
A53_PLAIN_IS_N = 121
CONTROL_ID = "plain"
NOTIONAL = 6000.0
N_SHORT = 8
MIN_RESIDUAL = 16
MIN_PASS = 5
LB = 15
HOLD = 10
TWO_COHORT = 2.0 * float(N_SHORT) * NOTIONAL
# name, weekday (Mon=0), filter
EXPERIMENTS = (
    ("plain", 4, "none"),
    ("fade1", 4, "fade1"),
    ("fade2", 4, "fade2"),
    ("rth_down", 4, "rth_down"),
    ("no_repeat", 4, "no_repeat"),
    ("wed_fade1", 2, "fade1"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
CHAR_IDS = ("fade1", "fade2", "rth_down")


def fade_pass(name_window_ret: float | None, iwm_window_ret: float | None) -> bool:
    """True iff last-N-session residual vs IWM is strictly negative."""
    if name_window_ret is None or iwm_window_ret is None:
        return False
    return (name_window_ret - iwm_window_ret) < 0.0


def rth_down_pass(rth_close: float | None, rth_open: float | None) -> bool:
    if rth_close is None or rth_open is None:
        return False
    return rth_close < rth_open


def no_repeat_pass(symbol: str, prior_eight: set[str]) -> bool:
    return symbol not in prior_eight


def take_passing(
    ranked: list[dict],
    pred,
    *,
    n: int = N_SHORT,
    min_pass: int = MIN_PASS,
) -> list[dict] | None:
    """Highest residual that pass pred. None if fewer than min_pass. Do not fill with fails."""
    passed = [r for r in ranked if pred(r)]
    if len(passed) < min_pass:
        return None
    return passed[:n]


def _session_px(session: date, symbol: str) -> tuple[tuple | None, tuple | None]:
    """Last RTH close and 09:30 open from one parquet read."""
    p = session_bar_path(session, symbol)
    if not p.exists():
        return None, None
    try:
        df = pl.read_parquet(p, columns=["bar_start", "open", "high", "low", "close", "volume"])
    except Exception:  # noqa: BLE001
        return None, None
    if df.height == 0:
        return None, None
    last = last_rth(df, session)
    first = first_rth(df)
    now = (last["bar_start"], float(last["close"])) if last is not None else None
    op = (first["bar_start"], float(first["open"])) if first is not None else None
    return now, op


def _window_ret(px0: float | None, px1: float | None) -> float | None:
    if px0 is None or px1 is None or px0 <= 0 or px1 <= 0:
        return None
    return px1 / px0 - 1.0


def _rebalance_job(args: tuple) -> dict:
    (
        iso,
        look15_iso,
        look2_iso,
        look1_iso,
        exit10_iso,
        names,
        iwm_l15,
        iwm_l2,
        iwm_l1,
        iwm1,
        wd,
    ) = args
    session = date.fromisoformat(iso)
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
    look2 = date.fromisoformat(look2_iso) if look2_iso else None
    look1 = date.fromisoformat(look1_iso) if look1_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    empty = {
        "session": iso,
        "rows": [],
        "n_res": 0,
        "wd": wd,
        "skipped": "no_names",
    }
    if not names or look15 is None or iwm_l15 is None or iwm1 is None or iwm_l15 <= 0 or iwm1 <= 0:
        empty["skipped"] = "iwm"
        return empty
    rows = []
    for h in names:
        sym = h["symbol"]
        now, op = _session_px(session, sym)
        if now is None:
            continue
        a15 = _last_close(look15, sym)
        if a15 is None:
            continue
        res = residual(a15[1], now[1], iwm_l15, iwm1)
        if res is None:
            continue
        a1 = _last_close(look1, sym) if look1 is not None else None
        a2 = _last_close(look2, sym) if look2 is not None else None
        n1 = _window_ret(a1[1] if a1 else None, now[1])
        n2 = _window_ret(a2[1] if a2 else None, now[1])
        i1 = _window_ret(iwm_l1, iwm1)
        i2 = _window_ret(iwm_l2, iwm1)
        ex = _last_close(ex10, sym) if ex10 is not None else None
        rows.append(
            {
                **h,
                "residual": res,
                "now": now,
                "ex": ex,
                "fade1_ok": fade_pass(n1, i1),
                "fade2_ok": fade_pass(n2, i2),
                "rth_down_ok": rth_down_pass(now[1], op[1] if op else None),
            }
        )
    return {
        "session": iso,
        "rows": rows,
        "n_res": len(rows),
        "wd": wd,
        "skipped": "" if rows else "thin",
    }


def _picks_for(ranked: list[dict], filt: str, prior: set[str]) -> list[dict] | None:
    if filt == "none":
        return ranked[:N_SHORT] if len(ranked) >= MIN_RESIDUAL else None
    if filt == "fade1":
        return take_passing(ranked, lambda r: r["fade1_ok"])
    if filt == "fade2":
        return take_passing(ranked, lambda r: r["fade2_ok"])
    if filt == "rth_down":
        return take_passing(ranked, lambda r: r["rth_down_ok"])
    if filt == "no_repeat":
        return take_passing(ranked, lambda r: no_repeat_pass(r["symbol"], prior))
    return None


def _trades_from(picks: list[dict], tag: str) -> list[dict]:
    out = []
    for h in picks:
        ent, ex = h.get("now"), h.get("ex")
        if ent is None or ex is None:
            continue
        tr = _short_n(h, ent, ex, tag, NOTIONAL)
        if tr:
            out.append(tr)
    return out


def run_arrow54(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 54 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow54 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "fade into the Friday fill. Short only. $6000. lb=15 n=8. "
        "Id 0 reprints Arrow 53 vs_iwm. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg. Did not retune Arrow 43 clocks or frozen B/flush. "
        "No new ingest. No Arrow 55.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable_cal: dict[int, list[date]] = {4: [], 2: []}
    for d in study:
        wd = d.weekday()
        if wd not in (2, 4):
            continue
        look5 = session_shift(d, -LOOKBACK, feats)
        look15 = session_shift(d, -LB, feats)
        look2 = session_shift(d, -2, feats)
        look1 = session_shift(d, -1, feats)
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
        i_l2 = _iwm_last_close(iwm, look2) if look2 is not None else None
        i_l1 = _iwm_last_close(iwm, look1) if look1 is not None else None
        i1 = _iwm_last_close(iwm, d)
        usable_cal[wd].append(d)
        jobs.append(
            (
                d.isoformat(),
                look15.isoformat(),
                look2.isoformat() if look2 is not None else None,
                look1.isoformat() if look1 is not None else None,
                e10.isoformat(),
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i_l2[1] if i_l2 else None,
                i_l1[1] if i_l1 else None,
                i1[1] if i1 else None,
                wd,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} jobs={len(jobs)} fri={len(usable_cal[4])} "
        f"wed={len(usable_cal[2])} short-only n=8 lb=15 $6000",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow54")
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

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in study
    }
    skipped_filt: dict[str, int] = {k: 0 for k in IDS}
    usable: dict[str, list[date]] = {k: [] for k in IDS}
    char_pass: dict[str, list[int]] = {k: [] for k in CHAR_IDS}
    prior_nr: set[str] = set()
    fridays = sorted(usable_cal[4])
    weds = sorted(usable_cal[2])

    for d in fridays:
        rec = recs.get(d.isoformat()) or {}
        rows = list(rec.get("rows") or [])
        n_res = rec.get("n_res") or 0
        chunks[d.isoformat()]["n_res"] = n_res
        if n_res < MIN_RESIDUAL:
            continue
        ranked = select_shorts(rows, len(rows), None)
        top8 = ranked[:N_SHORT]
        if is_is_session(d):
            for cid in CHAR_IDS:
                key = {"fade1": "fade1_ok", "fade2": "fade2_ok", "rth_down": "rth_down_ok"}[cid]
                char_pass[cid].append(sum(1 for r in top8 if r.get(key)))
        for name, _wd, filt in EXPERIMENTS:
            if _wd != 4:
                continue
            prior = prior_nr if filt == "no_repeat" else set()
            picks = _picks_for(ranked, filt, prior)
            if picks is None:
                skipped_filt[name] += 1
                continue
            usable[name].append(d)
            trs = _trades_from(picks, name)
            chunks[d.isoformat()]["trades"][name] = trs
            if filt == "no_repeat":
                prior_nr = {h["symbol"] for h in picks}

    for d in weds:
        rec = recs.get(d.isoformat()) or {}
        rows = list(rec.get("rows") or [])
        n_res = rec.get("n_res") or 0
        slot = chunks.setdefault(d.isoformat(), {"trades": {k: [] for k in IDS}, "n_res": 0})
        slot["n_res"] = n_res
        if n_res < MIN_RESIDUAL:
            continue
        ranked = select_shorts(rows, len(rows), None)
        picks = _picks_for(ranked, "fade1", set())
        if picks is None:
            skipped_filt["wed_fade1"] += 1
            continue
        usable["wed_fade1"].append(d)
        slot["trades"]["wed_fade1"] = _trades_from(picks, "wed_fade1")

    is_fridays = [d for d in usable[CONTROL_ID] if is_is_session(d)]
    sm0_is, _, _tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, is_fridays)
    reprint_ok = _within(sm0_is["per_day"], A53_PLAIN_IS_DAY) and _within(sm0_is["n_trades"], A53_PLAIN_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A53_PLAIN_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A53_PLAIN_IS_N} "
        + (
            "— within ±10% of Arrow 53 vs_iwm."
            if reprint_ok
            else "— DRIFT beyond ±10%. Rings not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 54 — fade into the Friday fill (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 53 vs_iwm. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 55.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow54_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    char_lines = [
        "IS character for ids 1–3: fraction of the unfiltered top 8 that would pass the filter. "
        "Description. Does not pick an id."
    ]
    for cid in CHAR_IDS:
        xs = char_pass[cid]
        if not xs:
            char_lines.append(f"  {cid} n_fridays=0")
            continue
        tot = sum(xs)
        n8 = len(xs) * N_SHORT
        char_lines.append(
            f"  {cid} unfiltered-top8 pass {tot}/{n8} frac={tot / n8:.3f}  "
            f"mean_per_week={tot / len(xs):.2f}  n_fridays={len(xs)}"
        )

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, _wd, filt in EXPERIMENTS:
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
                "filt": filt,
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
                "n_skip_filt": skipped_filt[name],
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    fade1 = next(r for r in results if r["name"] == "fade1")
    plain_n = next(r for r in results if r["name"] == CONTROL_ID)["is"]["n_trades"]
    fade1_n = fade1["is"]["n_trades"]
    cut_frac = (plain_n - fade1_n) / plain_n if plain_n else 0.0
    if cut_frac < 0.25:
        cut_s = "a little"
    elif cut_frac < 0.50:
        cut_s = "moderately"
    else:
        cut_s = "a lot"
    fade1_line = (
        f"fade1 IS n={fade1_n} vs plain n={plain_n} (cut {cut_frac:.0%}, {cut_s}). "
        f"weeks skipped by filter={fade1['n_skip_filt']}."
    )
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 54 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    honesty = (
        "Short only. Rank leftover vs IWM, then entry filter. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and two-cohort notional <= $100k. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 55."
    )
    lines = [
        "Arrow 54 — fade into the Friday fill (IS / OOS)",
        verdict,
        reprint_line,
        f"Ids that lift $/day versus plain on both IS and OOS: {both_s}.",
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and two-cohort fit: {slate_s}.",
        fade1_line,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"friday rebalances={len(usable_cal[4])}  wednesday rebalances={len(usable_cal[2])}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 44–53, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  n=8 after filters  lb=15  "
        f"${NOTIONAL:.0f}/name  hold=10  two-cohort $={TWO_COHORT:.0f}",
        "Skip a week if fewer than 16 eligible names have a residual. "
        "If fewer than 5 pass the entry filter, skip that id's week. If 5–7 pass, take them all.",
        "",
        *char_lines,
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
            wd = "Friday" if r["wd"] == 4 else "Wednesday"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={N_SHORT} notional=${NOTIONAL:.0f}  {wd}  filter={r['filt']}  "
                f"lb={LB} hold={HOLD}{_ci_note(sm)}"
            )
            lines.append(
                f"    deployed $={TWO_COHORT:.0f}  fits_100k=yes  rebalances={r['n_reb']}  "
                f"weeks_skipped_by_filter={r['n_skip_filt']}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow54_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow54_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 54",
        "",
        verdict,
        "",
        reprint_line,
        fade1_line,
        f"Lift vs plain on both IS and OOS: {both_s}.",
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.  Slate ${FAILURE_LINE:.0f}: {slate_s}.",
        "Short only. Fade-into-entry on leftover vs IWM. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 55.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            f"skip_filt={r['n_skip_filt']}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r["lift_both"] else "")
            + ("  OOS CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
