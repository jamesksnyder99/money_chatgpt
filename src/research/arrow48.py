"""Arrow 48 — scale and n8 on the lb10 seat. Short only."""

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
    _fmt_book,
    _iwm_last_close,
    _last_close,
    _month_lines,
    residual,
)
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow47 import _short_n
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
A47_3K_IS_DAY = 332.58
A47_3K_IS_N = 260
A47_N8_2K_IS = 122.94
A47_N8_2K_OOS = 102.47
CONTROL_ID = "n15_h10_3k"
ID_4K = "n15_h10_4k"
ID_5K = "n15_h10_5k"
ID_N8_3K = "n8_h10_3k"
# name, n_short, hold, notional
EXPERIMENTS = (
    ("n15_h10_3k", 15, 10, 3000.0),
    ("n15_h10_4k", 15, 10, 4000.0),
    ("n15_h10_5k", 15, 10, 5000.0),
    ("n8_h10_3k", 8, 10, 3000.0),
    ("n15_h5_3k", 15, 5, 3000.0),
    ("n8_h5_3k", 8, 5, 3000.0),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
LB = 10


def _week_job(args: tuple) -> dict:
    (
        iso,
        look10_iso,
        exit5_iso,
        exit10_iso,
        names,
        iwm_l10,
        iwm1,
        iwm_x5,
        iwm_x10,
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
    for name, n_short, hold, notional in EXPERIMENTS:
        if len(rows) < 2 * n_short:
            continue
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


def _wins_losses(trades: list[dict]) -> tuple[int, int]:
    n_win = sum(1 for t in trades if t.get("win") or t["pnl"] > 0)
    n_loss = sum(1 for t in trades if t["pnl"] < 0)
    return n_win, n_loss


def _fmt_book48(sm: dict) -> list[str]:
    lines = _fmt_book(sm)
    lines[0] = (
        f"    n={sm['n_trades']}  n/week={sm['trades_per_week']:.2f}  hit={sm['hit_rate']:.3f}  "
        f"wins={sm['n_win']}  losses={sm['n_loss']}  avgR=n/a (no stop)  PF={sm['pf_s']}"
    )
    return lines


def _scale_line(label: str, got_is: float, got_oos: float, base_is: float, base_oos: float, expected: float) -> str:
    s_is = (got_is / base_is) if base_is else 0.0
    s_oos = (got_oos / base_oos) if base_oos else 0.0
    note = f"{label} IS {s_is:.2f}x OOS {s_oos:.2f}x vs linear {expected:.2f}x."
    if abs(s_is - expected) > 0.20 or abs(s_oos - expected) > 0.20:
        note += " Did not scale near-linear (costs or missing fills)."
    else:
        note += " Near-linear."
    return note


def run_arrow48(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 48 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    reb = rebalance_sessions(study)
    print(
        f"research start mode=arrow48 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"rebalance_weeks={len(reb)} jan_tape={tape_root(date(2026, 1, 2))} "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "scale and n8 on the lb10 seat. Short only. Id 0 reprints Arrow 47 n15_lb10_h10_3k. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 49.",
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
        ix5 = _iwm_last_close(iwm, e5)
        ix10 = _iwm_last_close(iwm, e10)
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
                ix5[1] if ix5 else None,
                ix10[1] if ix10 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} weeks={len(jobs)} short-only lb=10 control $3000",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow48")
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
    reprint_ok = _within(sm0_is["per_day"], A47_3K_IS_DAY) and _within(sm0_is["n_trades"], A47_3K_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A47_3K_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A47_3K_IS_N} "
        + (
            "— within ±10% of Arrow 47 n15_lb10_h10_3k."
            if reprint_ok
            else "— DRIFT beyond ±10%. Rings not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 48 — scale and n8 on the lb10 seat (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 47 n15_lb10_h10_3k. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 49.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow48_results.txt").write_text(text, encoding="utf-8")
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
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        slate = sm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_is["per_day"] >= 0.0
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
    r4 = by_name[ID_4K]
    r5 = by_name[ID_5K]
    rn8 = by_name[ID_N8_3K]
    scale_4k = _scale_line(
        f"Id 1 {ID_4K} $4k / id 0 $3k",
        r4["is"]["per_day"],
        r4["oos"]["per_day"],
        ctrl_is,
        ctrl_oos,
        4000.0 / 3000.0,
    )
    scale_5k = _scale_line(
        f"Id 2 {ID_5K} $5k / id 0 $3k",
        r5["is"]["per_day"],
        r5["oos"]["per_day"],
        ctrl_is,
        ctrl_oos,
        5000.0 / 3000.0,
    )
    scale_n8 = _scale_line(
        f"Id 3 {ID_N8_3K} vs Arrow 47 n8_lb10_h10 $2k",
        rn8["is"]["per_day"],
        rn8["oos"]["per_day"],
        A47_N8_2K_IS,
        A47_N8_2K_OOS,
        3000.0 / 2000.0,
    )
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 48 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    honesty = (
        "Short only. Rings locked from IS; OOS is one look for the family. "
        "Did not drop an id after seeing OOS. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg. Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 49."
    )
    lines = [
        "Arrow 48 — scale and n8 on the lb10 seat (IS / OOS)",
        verdict,
        reprint_line,
        scale_4k,
        scale_5k,
        scale_n8,
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red: {slate_s}.",
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
        f"eligibility: same wall as Arrow 44–47, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  lb=10",
        "Skip week if fewer than 2×n eligible names have a residual. Skip a name if a required close is missing.",
        "",
        f"{'id':<16} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
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
                f"{r['name']:<16} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} {vs:>6} {flag:>5}"
            )
            lines.extend(_fmt_book48(sm))
            ci_note = ""
            if split == "OOS" and sm["ci_lo"] <= 0 <= sm["ci_hi"]:
                ci_note = "  CI includes 0 — not EV"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={r['n_short']} lb={r['lb']} hold={r['hold']}  "
                f"notional=${r['notional']:.0f}{ci_note}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow48_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow48_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 48",
        "",
        verdict,
        "",
        reprint_line,
        scale_4k,
        scale_5k,
        scale_n8,
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.",
        f"Slate ${FAILURE_LINE:.0f} on OOS with IS not red: {slate_s}.",
        f"Lift vs control on both IS and OOS: {both_s}.",
        "Short only. lb=10. Rings locked from IS. One OOS look. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 49.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  lift-both" if r["lift_both"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
