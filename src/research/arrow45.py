"""Arrow 45 — residual-short rings. Short last week's winners only."""

from __future__ import annotations

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, _pack, load_combined_iwm, notional_shares
from research.arrow44 import (
    HOLD,
    LOOKBACK,
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    NOTIONAL,
    _alpha,
    _by_sess,
    _fmt_book,
    _iwm_last_close,
    _last_close,
    _month_lines,
    residual,
)
from research.book import borrow_blocks_short, daily_close_drawdown
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    rebalance_sessions,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO, signed_pnl

ET = ZoneInfo("America/New_York")
A44_SHORT_IS_DAY = 246.77
A44_SHORT_IS_N = 272
COUNT_TOL = 0.10
CONTROL_ID = "n15_h5"
EXPERIMENTS = (
    ("n15_h5", 15, 5, None),
    ("n10_h5", 10, 5, None),
    ("n8_h5", 8, 5, None),
    ("n15_h5_r04", 15, 5, 0.04),
    ("n15_h5_r08", 15, 5, 0.08),
    ("n15_h10", 15, 10, None),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
CHAR_IDS = ("n10_h5", "n8_h5", "n15_h5_r04", "n15_h5_r08")


def _within(n: float, ref: float, tol: float = COUNT_TOL) -> bool:
    return abs(n - ref) <= tol * abs(ref) + 1e-9


def select_shorts(rows: list[dict], n_short: int, min_res: float | None) -> list[dict]:
    """High residual = winner. Threshold ids never take a name under the bar."""
    ranked = sorted(rows, key=lambda r: r["residual"], reverse=True)
    if min_res is not None:
        ranked = [r for r in ranked if r["residual"] >= min_res - 1e-12]
    return ranked[: max(0, int(n_short))]


def _short_trade(h: dict, ent: tuple, ex: tuple, tag: str) -> dict | None:
    if borrow_blocks_short(
        (ent[1] / h["prior_close"] - 1.0) if h["prior_close"] > 0 else None,
        h["prior_dv"],
    ):
        return None
    shares = notional_shares(ent[1])
    if shares < 1:
        return None
    pnl = signed_pnl(-1, shares, ent[1], ex[1])
    return _pack(pnl, -1, shares, ent[1], ex[1], ent[0], ex[0], tag, h["symbol"])


def _week_job(args: tuple) -> dict:
    (
        iso,
        look_iso,
        exit5_iso,
        exit10_iso,
        names,
        iwm0,
        iwm1,
        iwm5,
        iwm10,
        do_char,
    ) = args
    session = date.fromisoformat(iso)
    look = date.fromisoformat(look_iso)
    ex5 = date.fromisoformat(exit5_iso) if exit5_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    empty = {
        "session": iso,
        "trades": {k: [] for k in IDS},
        "char": {k: [] for k in CHAR_IDS},
        "n_res": 0,
        "skipped": "no_names",
    }
    if not names or iwm0 is None or iwm1 is None or iwm0 <= 0 or iwm1 <= 0:
        empty["skipped"] = "iwm"
        return empty
    rows = []
    closes_r: dict[str, tuple] = {}
    closes_5: dict[str, tuple] = {}
    closes_10: dict[str, tuple] = {}
    for h in names:
        sym = h["symbol"]
        a = _last_close(look, sym)
        b = _last_close(session, sym)
        if a is None or b is None:
            continue
        res = residual(a[1], b[1], iwm0, iwm1)
        if res is None:
            continue
        closes_r[sym] = b
        if ex5 is not None:
            c5 = _last_close(ex5, sym)
            if c5 is not None:
                closes_5[sym] = c5
        if ex10 is not None:
            c10 = _last_close(ex10, sym)
            if c10 is not None:
                closes_10[sym] = c10
        nxt5 = None
        if iwm5 is not None and iwm5 > 0 and sym in closes_5:
            nxt5 = residual(b[1], closes_5[sym][1], iwm1, iwm5)
        rows.append({**h, "residual": res, "next5": nxt5})
    n_res = len(rows)
    trades = {k: [] for k in IDS}
    char = {k: [] for k in CHAR_IDS}
    skipped = ""
    for name, n_short, hold, min_res in EXPERIMENTS:
        if n_res < 2 * n_short:
            continue
        picks = select_shorts(rows, n_short, min_res)
        exits = closes_10 if hold == 10 else closes_5
        for h in picks:
            ent = closes_r.get(h["symbol"])
            ex = exits.get(h["symbol"])
            if ent is None or ex is None:
                continue
            tr = _short_trade(h, ent, ex, name)
            if tr:
                trades[name].append(tr)
        if do_char and name in CHAR_IDS:
            for h in picks:
                if h.get("next5") is not None:
                    char[name].append(float(h["next5"]))
    if n_res < 2 * 15:
        skipped = "thin"
    return {
        "session": iso,
        "trades": trades,
        "char": char,
        "n_res": n_res,
        "skipped": skipped,
    }


def _daily_and_trades(chunks: dict, sessions: list[date], name: str, weeks: list[date]):
    from research.arrow23 import _summarize_adv

    rows = []
    for d in sessions:
        iso = d.isoformat()
        rec = chunks.get(iso) or {}
        tr = list((rec.get("trades") or {}).get(name) or [])
        pnl = sum(t["pnl"] for t in tr)
        rows.append({"session": iso, "pnl": pnl, "trades": tr, "peak": len(tr), "mean_conc": float(len(tr))})
    daily = [float(r["pnl"]) for r in rows]
    trades = [t for r in rows for t in r["trades"]]
    sm = _summarize_adv(daily, trades, len(sessions))
    n_weeks = sum(1 for d in weeks if (chunks.get(d.isoformat()) or {}).get("n_res", 0) >= 2 * 8)
    traded_weeks = [r for r in rows if r["peak"]]
    sm["peak_conc"] = max((r["peak"] for r in rows), default=0)
    sm["mean_conc"] = (sum(r["mean_conc"] for r in traded_weeks) / len(traded_weeks)) if traded_weeks else 0.0
    sm["daily_close_dd"] = daily_close_drawdown(daily)
    sm["worst_day"] = min(daily) if daily else 0.0
    sm["n_week"] = len(traded_weeks)
    sm["trades_per_week"] = (len(trades) / len(traded_weeks)) if traded_weeks else 0.0
    return sm, daily, trades


def _char_block(char: dict[str, dict[str, list[float]]]) -> list[str]:
    lines = [
        "IS character for rings that change the population (n10, n8, r04, r08). "
        "Mean next-hold residual of names that would be shorted. Description. Does not pick an id."
    ]

    def _stats(xs: list[float]) -> str:
        if not xs:
            return "n=0"
        n = len(xs)
        mean = sum(xs) / n
        hit = sum(1 for x in xs if x > 0) / n
        return f"n={n} mean={mean:.5f} hit={hit:.3f}"

    for name in CHAR_IDS:
        by_m = char.get(name) or {}
        all_x = [x for xs in by_m.values() for x in xs]
        lines.append(f"  {name} next-hold residual {_stats(all_x)}")
        for key in sorted(by_m):
            lines.append(f"    {key} {_stats(by_m[key])}")
    return lines


def run_arrow45(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 45 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    reb = rebalance_sessions(study)
    print(
        f"research start mode=arrow45 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"rebalance_weeks={len(reb)} jan_tape={tape_root(date(2026, 1, 2))} "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "residual-short rings. Short only. Id 0 reprints Arrow 44 res_short. "
        "Did not use an OOS month to pick a threshold. Did not bring back res_long. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 46.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable: list[date] = []
    for r in reb:
        look = session_shift(r, -LOOKBACK, feats)
        e5 = session_shift(r, HOLD, feats)
        e10 = session_shift(r, 10, feats)
        if look is None or e5 is None:
            continue
        if not (tape_root(e5) / e5.isoformat()).exists():
            continue
        i0 = _iwm_last_close(iwm, look)
        i1 = _iwm_last_close(iwm, r)
        i5 = _iwm_last_close(iwm, e5) if e5 is not None else None
        i10 = _iwm_last_close(iwm, e10) if e10 is not None and (tape_root(e10) / e10.isoformat()).exists() else None
        usable.append(r)
        jobs.append(
            (
                r.isoformat(),
                look.isoformat(),
                e5.isoformat(),
                e10.isoformat() if e10 is not None and (tape_root(e10) / e10.isoformat()).exists() else None,
                by.get(r.isoformat(), []),
                i0[1] if i0 else None,
                i1[1] if i1 else None,
                i5[1] if i5 else None,
                i10[1] if i10 else None,
                is_is_session(r),
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} weeks={len(jobs)} notional=${NOTIONAL:.0f} short-only",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow45")
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
    sm0_is, _, tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, is_weeks)
    reprint_ok = _within(sm0_is["per_day"], A44_SHORT_IS_DAY) and _within(sm0_is["n_trades"], A44_SHORT_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A44_SHORT_IS_DAY} n={sm0_is['n_trades']}/{A44_SHORT_IS_N} "
        + ("— within ±10% of Arrow 44 res_short." if reprint_ok else "— DRIFT beyond ±10%. Rings not a valid read.")
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 45 — residual-short rings (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 44 res_short. Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 46.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow45_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    char: dict[str, dict[str, list[float]]] = {k: defaultdict(list) for k in CHAR_IDS}
    for d in is_weeks:
        rec = chunks.get(d.isoformat()) or {}
        key = f"{d.year:04d}-{d.month:02d}"
        for name in CHAR_IDS:
            char[name][key].extend((rec.get("char") or {}).get(name) or [])

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, n_short, hold, min_res in EXPERIMENTS:
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_weeks)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_weeks)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
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
                "hold": hold,
                "min_res": min_res,
                "is": sm_is,
                "oos": sm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "seat": seat,
                "lift_both": lift_both,
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    both = [r["name"] for r in results if r["lift_both"]]
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red). Slate $200 is not this arrow's job."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 45 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS. "
            "Slate $200 is not this arrow's job."
        )
    both_s = ", ".join(both) if both else "none"
    honesty = (
        "Short only. Rings locked from IS; OOS is one look for the whole family. "
        "Did not drop an id after seeing OOS. Did not use June, August, or any OOS month to pick a threshold. "
        "Did not bring back res_long. Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "An id that lifts IS and cuts OOS is not an improvement. An id that lifts OOS and turns IS red is not a seat. "
        "Odd months IS, even months OOS, split on entry session. Combined dollars are not EV. No Arrow 46."
    )
    lines = [
        "Arrow 45 — residual-short rings (IS / OOS)",
        verdict,
        reprint_line,
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
        f"eligibility: same wall as Arrow 44, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  ${NOTIONAL:.0f} notional/name  short residual winners only",
        "Skip week if fewer than 2×n_short names have a residual. "
        "Threshold ids take only residual ≥ bar; do not fill the seat under the bar.",
        "",
    ]
    lines.extend(_char_block(char))
    lines.append("")
    lines.append(
        f"{'id':<14} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'vs0':>6} {'seat':>5}"
    )
    for r in results:
        for split, sm, a, skip, n_a, months in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"]),
        ):
            vs = "ctrl"
            if r["name"] != CONTROL_ID and ctrl_is is not None and ctrl_oos is not None:
                base = ctrl_is if split == "IS" else ctrl_oos
                vs = f"{sm['per_day'] - base:+.1f}"
            if split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<14} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} {vs:>6} {flag:>5}"
            )
            lines.extend(_fmt_book(sm))
            extra = ""
            if r["min_res"] is not None:
                extra = f"  residual>={r['min_res']}"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  n_short={r['n_short']} hold={r['hold']}{extra}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow45_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow45_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 45",
        "",
        verdict,
        "",
        reprint_line,
        f"Lift vs control on both IS and OOS: {both_s}.",
        "Short only residual winners. Rings locked from IS. One OOS look. "
        "Did not use an OOS month to pick a threshold. Did not bring back res_long. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 46.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']}  "
            f"{'SEAT' if r['seat'] else 'no seat'}"
            + ("  lift-both" if r["lift_both"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
