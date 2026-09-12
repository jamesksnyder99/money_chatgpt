"""Arrow 58 — short the loser slot. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, load_combined_iwm
from research.arrow44 import (
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _alpha,
    _by_sess,
    _month_lines,
)
from research.arrow45 import _daily_and_trades, _within
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import peak_live_notional
from research.arrow57 import (
    _cached_last_close,
    _char_stats,
    name_return,
    select_losers,
)
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
A57_LOSE_MEAN = -0.00861
A57_LOSE_HIT = 0.441
CONTROL_ID = "lose_h1"
N8 = 8
N15 = 15
MIN_N8 = 2 * N8
MIN_N15 = 2 * N15
# name, n, hold, notional
EXPERIMENTS = (
    ("lose_h1", 8, 1, 3000.0),
    ("lose_h5", 8, 5, 3000.0),
    ("lose_h10", 8, 10, 3000.0),
    ("lose_h10_6k", 8, 10, 6000.0),
    ("lose_h10_n15", 15, 10, 3000.0),
    ("lose_h5_6k", 8, 5, 6000.0),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _slim(h: dict) -> dict:
    return {
        "symbol": h["symbol"],
        "prior_close": h["prior_close"],
        "prior_dv": h["prior_dv"],
        "ret": h["ret"],
        "now": h["now"],
        "e1": h.get("e1"),
        "e5": h.get("e5"),
        "e10": h.get("e10"),
        "next_ret": h.get("next_ret"),
    }


def _exit_fill(h: dict, hold: int):
    if hold == 1:
        return h.get("e1")
    if hold == 5:
        return h.get("e5")
    return h.get("e10")


def _fmt_book58(sm: dict) -> list[str]:
    lines = _fmt_book48(sm)
    lines[0] = lines[0].replace("n/week=", "n/sess=")
    return lines


def _session_job(args: tuple) -> dict:
    iso, look_iso, e1_iso, e5_iso, e10_iso, names = args
    session = date.fromisoformat(iso)
    look = date.fromisoformat(look_iso) if look_iso else None
    e1d = date.fromisoformat(e1_iso) if e1_iso else None
    e5d = date.fromisoformat(e5_iso) if e5_iso else None
    e10d = date.fromisoformat(e10_iso) if e10_iso else None
    empty = {
        "session": iso,
        "n_res": 0,
        "lose8": [],
        "lose15": [],
        "skipped": "no_names",
    }
    if not names or look is None:
        empty["skipped"] = "look"
        return empty
    rows = []
    for h in names:
        sym = h["symbol"]
        now = _cached_last_close(session, sym)
        if now is None:
            continue
        a = _cached_last_close(look, sym)
        if a is None:
            continue
        ret = name_return(a[1], now[1])
        if ret is None:
            continue
        e1 = _cached_last_close(e1d, sym) if e1d is not None else None
        e5 = _cached_last_close(e5d, sym) if e5d is not None else None
        e10 = _cached_last_close(e10d, sym) if e10d is not None else None
        nxt = name_return(now[1], e1[1]) if e1 is not None else None
        rows.append(
            {
                **h,
                "ret": ret,
                "now": now,
                "e1": e1,
                "e5": e5,
                "e10": e10,
                "next_ret": nxt,
            }
        )
    n_res = len(rows)
    if n_res < MIN_N8:
        empty["n_res"] = n_res
        empty["skipped"] = "thin"
        return empty
    lose8 = [_slim(h) for h in select_losers(rows, N8, "ret")]
    lose15 = [_slim(h) for h in select_losers(rows, N15, "ret")] if n_res >= MIN_N15 else []
    return {
        "session": iso,
        "n_res": n_res,
        "lose8": lose8,
        "lose15": lose15,
        "skipped": "",
    }


def run_arrow58(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 58 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow58 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "short the loser slot. Short only. Holds 1/5/10. No IWM subtract. "
        "Did not retune Friday+Wednesday leftover pair or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 59.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    for d in study:
        look = session_shift(d, -1, feats)
        e1 = session_shift(d, 1, feats)
        e5 = session_shift(d, 5, feats)
        e10 = session_shift(d, 10, feats)
        if look is None:
            continue
        jobs.append(
            (
                d.isoformat(),
                look.isoformat(),
                e1.isoformat() if e1 is not None else None,
                e5.isoformat() if e5 is not None else None,
                e10.isoformat() if e10 is not None else None,
                by.get(d.isoformat(), []),
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} jobs={len(jobs)} short-only loser slot  n=8/15  last-RTH",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow58")
    prog.start_heartbeat()
    recs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_session_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            recs[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 16 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in study
    }
    char_next: list[float] = []
    usable: dict[str, list[date]] = {k: [] for k in IDS}

    for d in study:
        rec = recs.get(d.isoformat()) or {}
        n_res = rec.get("n_res") or 0
        chunks[d.isoformat()]["n_res"] = n_res
        lose8 = list(rec.get("lose8") or [])
        lose15 = list(rec.get("lose15") or [])
        if is_is_session(d):
            for h in lose8:
                nxt = h.get("next_ret")
                if nxt is not None:
                    char_next.append(float(nxt))
        for name, n_slot, hold, notional in EXPERIMENTS:
            if n_slot == 15:
                if n_res < MIN_N15 or not lose15:
                    continue
                picks = lose15
            else:
                if n_res < MIN_N8 or not lose8:
                    continue
                picks = lose8
            trs = []
            for h in picks:
                ent, ex = h.get("now"), _exit_fill(h, hold)
                if ent is None or ex is None:
                    continue
                tr = _short_n(h, ent, ex, name, notional)
                if tr:
                    trs.append(tr)
            if not trs:
                continue
            chunks[d.isoformat()]["trades"][name] = trs
            usable[name].append(d)

    if char_next:
        char_mean = sum(char_next) / len(char_next)
        char_hit = sum(1 for x in char_next if x > 0) / len(char_next)
    else:
        char_mean = 0.0
        char_hit = 0.0
    char_ok = bool(char_next) and _within(char_mean, A57_LOSE_MEAN) and _within(char_hit, A57_LOSE_HIT)
    char_line = (
        f"IS character loser eight next-session raw return {_char_stats(char_next)} "
        f"vs Arrow 57 {A57_LOSE_MEAN:.5f} / {A57_LOSE_HIT:.3f}."
    )
    if char_ok:
        char_line += " Same neighborhood as Arrow 57 loser-slot."
    else:
        char_line += " DRIFT beyond Arrow 57 loser-slot neighborhood. Rings not a valid read."
    print(char_line, flush=True)
    if not char_ok:
        text = (
            "Arrow 58 — short the loser slot (IS / OOS)\n"
            "VERDICT: FAIL — IS character did not match Arrow 57 loser-slot. Did not score rings.\n"
            f"{char_line}\n"
            "No Arrow 59.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow58_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, n_slot, hold, notional in EXPERIMENTS:
        weeks = usable[name]
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
        theoretical = float(n_slot) * float(notional) * float(hold)
        fits = peak <= ACCOUNT + 1e-12
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
                "n_slot": n_slot,
                "hold": hold,
                "notional": notional,
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
                "peak_live": peak,
                "peak_live_is": peak_is,
                "peak_live_oos": peak_oos,
                "theoretical": theoretical,
                "fits": fits,
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    h10 = [r for r in results if r["hold"] == 10]
    h10_paid = [r["name"] for r in h10 if r["is"]["per_day"] >= 0.0 and r["oos"]["per_day"] > 0.0]
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 58 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    both_s = ", ".join(both) if both else "none"
    h10_s = ", ".join(h10_paid) if h10_paid else "none"
    h10_line = f"Hold 10 paid on both IS and OOS: {h10_s}."
    honesty = (
        "Short only. Short the loser slot (eight smallest T close-to-close unless n=15). "
        "Did not retune the Friday+Wednesday leftover pair or frozen B|conj|atr1559|lock / flush|max6|repaired. "
        "No long id. No IWM subtract. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and peak live notional <= $100k. "
        "Hold 10 with daily entry is many overlapping cohorts. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 59."
    )
    lines = [
        "Arrow 58 — short the loser slot (IS / OOS)",
        verdict,
        char_line,
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and peak live <= $100k: {slate_s}.",
        h10_line,
        f"Ids that lift $/day versus lose_h1 on both IS and OOS: {both_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"jobs={len(jobs)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as leftover pair, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  loser slot  last-RTH  short only",
        "Skip T if fewer than 2xn eligible names have a T return. "
        "Skip a name if a required close is missing. "
        "Loser slot = smallest T close-to-close. No IWM subtract.",
        "",
        "IS character: next-session raw return of the loser eight. Description. Does not pick an id.",
        f"  {char_line}",
        "",
        f"{'id':<14} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'vs0':>6} {'seat':>5}",
    ]
    for r in results:
        for split, sm, a, skip, n_a, months, peak_s in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"], r["peak_live_is"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"], r["peak_live_oos"]),
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
            lines.extend(_fmt_book58(sm))
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_slot={r['n_slot']} notional=${r['notional']:.0f}  short lose  "
                f"hold={r['hold']}{_ci_note(sm)}"
            )
            lines.append(
                f"    peak live notional ${peak_s:.0f}  hold-cohorts ${r['theoretical']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  sessions={r['n_reb']}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow58_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow58_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 58",
        "",
        verdict,
        "",
        char_line,
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.  Slate ${FAILURE_LINE:.0f}: {slate_s}.",
        h10_line,
        f"Lift vs lose_h1 on both IS and OOS: {both_s}.",
        "Short only. Short the loser slot. Did not retune leftover pair or frozen B/flush. "
        "No long id. No IWM subtract. Did not use an OOS month to pick a threshold. "
        "No new ingest. No Arrow 59.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            f"peak_live ${r['peak_live']:.0f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r["lift_both"] else "")
            + ("  OOS CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
