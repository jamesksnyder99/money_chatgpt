"""Arrow 50 — execution and hold path on n8. Short only. $6,000."""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, _iwm_px, first_rth, load_combined_iwm
from research.arrow44 import (
    LOOKBACK,
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _by_sess,
    _iwm_last_close,
    _last_close,
    _month_lines,
    residual,
)
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    next_session,
    rebalance_sessions,
    session_bar_path,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO
from research.signals import MINUTE_1559, RTH_OPEN

ET = ZoneInfo("America/New_York")
A49_6K_IS_DAY = 371.20
A49_6K_IS_N = 135
CONTROL_ID = "fri_h10"
MON_ID = "mon_h10"
GIVE5_ID = "fri_give5"
NOTIONAL = 6000.0
N_SHORT = 8
MIN_RESIDUAL = 16
LB10 = 10
IWM_BAR = 0.08
# name, lookback, entry, exit, iwm_bar
EXPERIMENTS = (
    ("fri_h10", 10, "close", "h10", None),
    ("mon_h10", 10, "open_next", "h10", None),
    ("fri_h5", 10, "close", "h5", None),
    ("fri_give5", 10, "close", "give5", None),
    ("fri_h10_iwm8", 10, "close", "h10", IWM_BAR),
    ("lb15_fri_h10", 15, "close", "h10", None),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def give5_hold(entry_px: float, px5: float | None, px10: float | None) -> int | None:
    """+5 if the short is ahead (px5 < entry); else +10. None if a required fill is missing."""
    if not math.isfinite(entry_px) or entry_px <= 0:
        return None
    if px5 is not None and math.isfinite(px5) and px5 < entry_px:
        return 5
    if px10 is None or not math.isfinite(px10) or px10 <= 0:
        return None
    return 10


def iwm_blocks_week(px0: float, px1: float, bar: float = IWM_BAR) -> bool:
    """True iff IWM lookback return is at or above the bar (skip that week's id)."""
    if not math.isfinite(px0) or not math.isfinite(px1) or px0 <= 0 or px1 <= 0:
        return True
    return (px1 / px0 - 1.0) >= bar - 1e-12


def _rth_open(session: date, symbol: str) -> tuple[datetime, float] | None:
    p = session_bar_path(session, symbol)
    if not p.exists():
        return None
    try:
        df = pl.read_parquet(p, columns=["bar_start", "open", "high", "low", "close", "volume"])
    except Exception:  # noqa: BLE001
        return None
    if df.height == 0:
        return None
    rec = first_rth(df)
    if rec is None:
        return None
    return rec["bar_start"], float(rec["open"])


def _alpha50(trades, sessions, iwm):
    by_day = {d.isoformat(): 0.0 for d in sessions}
    skips = 0
    n_ok = 0
    for t in trades:
        ets, xts = t.get("entry_ts"), t.get("exit_ts")
        if ets is None or xts is None:
            skips += 1
            continue
        e_iso = ets.date().isoformat() if hasattr(ets, "date") else str(ets)[:10]
        x_iso = xts.date().isoformat() if hasattr(xts, "date") else str(xts)[:10]
        e = _iwm_px(iwm.get(e_iso), ets, use_open=(t.get("tag") == MON_ID))
        x = _iwm_px(iwm.get(x_iso), xts, use_open=False)
        if e is None or x is None or e <= 0:
            skips += 1
            continue
        iwm_ret = x / e - 1.0
        a = float(t["pnl"]) - int(t["side"]) * int(t["shares"]) * float(t["entry_px"]) * iwm_ret
        by_day[e_iso] = by_day.get(e_iso, 0.0) + a
        n_ok += 1
    per = (sum(by_day.get(d.isoformat(), 0.0) for d in sessions) / len(sessions)) if sessions else 0.0
    return per, skips, n_ok


def _give5_frac(trades: list[dict]) -> tuple[int, int, str]:
    n5 = sum(1 for t in trades if int(t.get("hold") or 0) == 5)
    n10 = sum(1 for t in trades if int(t.get("hold") or 0) == 10)
    n = n5 + n10
    if n == 0:
        return 0, 0, "n5=0 n10=0"
    return n5, n10, f"n5={n5} ({n5 / n:.3f}) n10={n10} ({n10 / n:.3f})"


def _cohort_fit(name: str, n_plus10: int) -> tuple[float, float, bool]:
    one = float(N_SHORT) * NOTIONAL
    two = 2.0 * one
    if name == "fri_h5":
        used = one
    elif name == GIVE5_ID:
        used = two if n_plus10 > 0 else one
    else:
        used = two
    return one, two, used <= ACCOUNT + 1e-12


def _chunks_for(name: str, chunks: dict[str, dict]) -> dict[str, dict]:
    if name != MON_ID:
        return chunks
    moved: dict[str, dict] = {}
    for rec in chunks.values():
        for tr in (rec.get("trades") or {}).get(MON_ID) or []:
            ets = tr.get("entry_ts")
            if ets is None:
                continue
            d = ets.astimezone(ET).date() if hasattr(ets, "astimezone") else date.fromisoformat(str(ets)[:10])
            iso = d.isoformat()
            slot = moved.setdefault(iso, {"trades": {k: [] for k in IDS}})
            slot["trades"][name].append(tr)
    return moved


def _week_job(args: tuple) -> dict:
    (
        iso,
        look10_iso,
        look15_iso,
        exit5_iso,
        exit10_iso,
        mon_iso,
        mon_x10_iso,
        names,
        iwm_l10,
        iwm_l15,
        iwm1,
    ) = args
    session = date.fromisoformat(iso)
    look10 = date.fromisoformat(look10_iso) if look10_iso else None
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
    ex5 = date.fromisoformat(exit5_iso) if exit5_iso else None
    ex10 = date.fromisoformat(exit10_iso) if exit10_iso else None
    mon = date.fromisoformat(mon_iso) if mon_iso else None
    mon_x10 = date.fromisoformat(mon_x10_iso) if mon_x10_iso else None
    empty = {
        "session": iso,
        "trades": {k: [] for k in IDS},
        "n_res10": 0,
        "n_res15": 0,
        "skipped": "no_names",
    }
    if not names or look10 is None or iwm_l10 is None or iwm1 is None or iwm_l10 <= 0 or iwm1 <= 0:
        empty["skipped"] = "iwm"
        return empty
    rows10 = []
    rows15 = []
    closes_r: dict[str, tuple] = {}
    closes_5: dict[str, tuple] = {}
    closes_10: dict[str, tuple] = {}
    opens_m: dict[str, tuple] = {}
    closes_mx: dict[str, tuple] = {}
    blocked = iwm_blocks_week(iwm_l10, iwm1, IWM_BAR)
    for h in names:
        sym = h["symbol"]
        now = _last_close(session, sym)
        if now is None:
            continue
        a10 = _last_close(look10, sym)
        res10 = residual(a10[1], now[1], iwm_l10, iwm1) if a10 is not None else None
        res15 = None
        if look15 is not None and iwm_l15 is not None and iwm_l15 > 0:
            a15 = _last_close(look15, sym)
            if a15 is not None:
                res15 = residual(a15[1], now[1], iwm_l15, iwm1)
        if res10 is None and res15 is None:
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
        if mon is not None:
            om = _rth_open(mon, sym)
            if om is not None:
                opens_m[sym] = om
        if mon_x10 is not None:
            cx = _last_close(mon_x10, sym)
            if cx is not None:
                closes_mx[sym] = cx
        rec = {**h}
        if res10 is not None:
            rows10.append({**rec, "residual": res10})
        if res15 is not None:
            rows15.append({**rec, "residual": res15})
    trades = {k: [] for k in IDS}
    if len(rows10) < MIN_RESIDUAL and len(rows15) < MIN_RESIDUAL:
        return {
            "session": iso,
            "trades": trades,
            "n_res10": len(rows10),
            "n_res15": len(rows15),
            "skipped": "thin",
        }
    for name, lb, entry, exit_kind, iwm_bar in EXPERIMENTS:
        pool = rows15 if lb == 15 else rows10
        if len(pool) < MIN_RESIDUAL:
            continue
        if iwm_bar is not None and blocked:
            continue
        picks = select_shorts(pool, N_SHORT, None)
        for h in picks:
            sym = h["symbol"]
            if entry == "open_next":
                ent = opens_m.get(sym)
            else:
                ent = closes_r.get(sym)
            if ent is None:
                continue
            hold = 10
            if exit_kind == "h5":
                ex = closes_5.get(sym)
                hold = 5
            elif exit_kind == "give5":
                px5 = closes_5[sym][1] if sym in closes_5 else None
                px10 = closes_10[sym][1] if sym in closes_10 else None
                hold_n = give5_hold(ent[1], px5, px10)
                if hold_n is None:
                    continue
                hold = hold_n
                ex = closes_5.get(sym) if hold == 5 else closes_10.get(sym)
            elif entry == "open_next":
                ex = closes_mx.get(sym)
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
        "n_res10": len(rows10),
        "n_res15": len(rows15),
        "skipped": "",
    }


def run_arrow50(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 50 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    reb = rebalance_sessions(study)
    print(
        f"research start mode=arrow50 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"rebalance_weeks={len(reb)} jan_tape={tape_root(date(2026, 1, 2))} "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "execution and hold path on n8. Short only. $6000. Id 0 reprints Arrow 49 n8_h10_6k. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 51.",
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
        look15 = session_shift(r, -15, feats)
        e5 = session_shift(r, 5, feats)
        e10 = session_shift(r, 10, feats)
        mon = next_session(r, feats)
        mon_x10 = session_shift(mon, 10, feats) if mon is not None else None
        if look5 is None or e5 is None:
            continue
        if not (tape_root(e5) / e5.isoformat()).exists():
            continue
        if e10 is None or not (tape_root(e10) / e10.isoformat()).exists():
            continue
        i_l10 = _iwm_last_close(iwm, look10) if look10 is not None else None
        i_l15 = _iwm_last_close(iwm, look15) if look15 is not None else None
        i1 = _iwm_last_close(iwm, r)
        usable.append(r)
        jobs.append(
            (
                r.isoformat(),
                look10.isoformat() if look10 is not None else None,
                look15.isoformat() if look15 is not None else None,
                e5.isoformat(),
                e10.isoformat(),
                mon.isoformat() if mon is not None else None,
                mon_x10.isoformat() if mon_x10 is not None else None,
                by.get(r.isoformat(), []),
                i_l10[1] if i_l10 else None,
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} weeks={len(jobs)} short-only n=8 lb=10 control $6000 last-RTH",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow50")
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
    reprint_ok = _within(sm0_is["per_day"], A49_6K_IS_DAY) and _within(sm0_is["n_trades"], A49_6K_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A49_6K_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A49_6K_IS_N} "
        + (
            "— within ±10% of Arrow 49 n8_h10_6k."
            if reprint_ok
            else "— DRIFT beyond ±10%. Rings not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 50 — execution and hold path on n8 (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 49 n8_h10_6k. "
            "Did not score rings on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 51.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow50_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    results = []
    ctrl_is = None
    ctrl_oos = None
    for name, lb, entry, exit_kind, iwm_bar in EXPERIMENTS:
        use = _chunks_for(name, chunks)
        sm_is, day_is, tr_is = _daily_and_trades(use, is_sess, name, is_weeks)
        sm_oos, day_oos, tr_oos = _daily_and_trades(use, oos_sess, name, oos_weeks)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        n5_is, n10_is, frac_is = _give5_frac(tr_is)
        n5_oos, n10_oos, frac_oos = _give5_frac(tr_oos)
        a_is, skip_is, n_is = _alpha50(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha50(tr_oos, oos_sess, iwm)
        one, two, fits = _cohort_fit(name, n10_is + n10_oos)
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
                "lb": lb,
                "entry": entry,
                "exit_kind": exit_kind,
                "iwm_bar": iwm_bar,
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
                "frac_is": frac_is,
                "frac_oos": frac_oos,
                "n5_is": n5_is,
                "n10_is": n10_is,
                "n5_oos": n5_oos,
                "n10_oos": n10_oos,
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    both = [r["name"] for r in results if r["lift_both"]]
    by_name = {r["name"]: r for r in results}
    mon = by_name[MON_ID]
    mon_oos = mon["oos"]["per_day"]
    if mon_oos >= FAILURE_LINE - 1e-12:
        mon_line = f"Monday entry OOS ${mon_oos:.2f}/day kept the OOS slate print (>= $200)."
    elif mon_oos >= SEAT_FLOOR - 1e-12:
        mon_line = f"Monday entry OOS ${mon_oos:.2f}/day kept a seat but not the OOS slate print."
    else:
        mon_line = f"Monday entry OOS ${mon_oos:.2f}/day did not keep the OOS print."
    give = by_name[GIVE5_ID]
    char_line = f"IS character id 3 {GIVE5_ID} exit +5 vs +10: {give['frac_is']}. Description. Does not pick an id."
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 50 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    honesty = (
        "Short only. Rings locked from IS; OOS is one look for the family. "
        "Did not drop an id after seeing OOS. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg. Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "A ring counts as better only if it lifts $/day versus id 0 on both IS and OOS. "
        "Slate needs OOS >= $200/day, IS not red, and two-cohort notional <= $100k "
        "(hold 5 is one cohort; give5 is two if any name stays past +5). "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 51."
    )
    lines = [
        "Arrow 50 — execution and hold path on n8 (IS / OOS)",
        verdict,
        reprint_line,
        f"Ids that lift $/day versus control on both IS and OOS: {both_s}.",
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and two-cohort fit: {slate_s}.",
        mon_line,
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
        f"eligibility: same wall as Arrow 44–49, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  n=8  ${NOTIONAL:.0f}/name",
        "Skip week if fewer than 16 eligible names have a residual. Skip a name if a required fill is missing.",
        "",
        char_line,
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
            ci_note = ""
            if split == "OOS" and sm["ci_lo"] <= 0 <= sm["ci_hi"]:
                ci_note = "  CI includes 0 — not EV"
            extra = f"  entry={r['entry']} exit={r['exit_kind']} lb={r['lb']}"
            if r["iwm_bar"] is not None:
                extra += f"  skip IWM 10s>={r['iwm_bar']}"
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={N_SHORT} notional=${NOTIONAL:.0f}{extra}{ci_note}"
            )
            fit_s = "yes" if r["fits"] else "NO"
            lines.append(
                f"    one-cohort $={r['one']:.0f}  two-cohort $={r['two']:.0f}  "
                f"fits_100k={fit_s}"
            )
            if r["name"] == GIVE5_ID:
                lines.append(f"    give5 {split} +5 vs +10: {frac}")
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow50_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow50_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 50",
        "",
        verdict,
        "",
        reprint_line,
        f"Lift vs control on both IS and OOS: {both_s}.",
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.",
        f"Slate ${FAILURE_LINE:.0f} on OOS with IS not red and two-cohort fit: {slate_s}.",
        mon_line,
        char_line,
        "Short only. n=8 $6k. Rings locked from IS. One OOS look. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No new ingest. No Arrow 51.",
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
