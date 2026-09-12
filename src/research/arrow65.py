"""Arrow 65 — Wednesday leftover plumbing. Short only. Split on signal session."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow23 import _summarize_adv
from research.arrow43 import SEAT_FLOOR, _elig_frame, first_rth, load_combined_iwm
from research.arrow44 import (
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
from research.arrow55 import HOLD, LB, MIN_RESIDUAL, N_SHORT
from research.arrow59 import _read_bars
from research.book import daily_close_drawdown
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO, cost_per_share

ET = ZoneInfo("America/New_York")
A56_WED_IS_DAY = 290.63
A56_WED_IS_N = 118
CONTROL_ID = "close_3k"
NOTIONAL_3K = 3000.0
NOTIONAL_4K = 4000.0
# name, fill (close/open/nextrth), notional, keep
EXPERIMENTS = (
    ("close_3k", "close", 3000.0, False),
    ("close_4k", "close", 4000.0, False),
    ("open_4k", "open", 4000.0, False),
    ("nextrth_4k", "nextrth", 4000.0, False),
    ("open_4k_keep", "open", 4000.0, True),
    ("nextrth_4k_keep", "nextrth", 4000.0, True),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def fill_session_of(signal: date, kind: str, sessions: list[date]) -> date | None:
    """close = signal session; open/nextrth = next session."""
    if kind == "close":
        return signal
    return session_shift(signal, 1, sessions)


def fill_px(kind: str, signal_close, next_open, next_rth):
    """Resolve fill price. open is next 09:30, not the signal close."""
    if kind == "close":
        return signal_close
    if kind == "open":
        return next_open
    return next_rth


def resolve_exit_bar(target_close, keep: bool, last_avail):
    """Drop missing exits unless keep, which flattens last available RTH."""
    if target_close is not None:
        return target_close, False
    if keep and last_avail is not None:
        return last_avail, True
    return None, False


def fill_0930(session: date, symbol: str) -> tuple | None:
    """First print at or after 09:30: close of that bar."""
    df = _read_bars(session, symbol)
    if df is None:
        return None
    rec = first_rth(df)
    if rec is None:
        return None
    px = rec.get("close")
    if px is None or float(px) <= 0:
        return None
    return rec["bar_start"], float(px)


def last_available_rth(
    fill_d: date,
    target: date | None,
    sessions: list[date],
    symbol: str,
) -> tuple | None:
    """Last RTH close on or before target, not before fill. For keep-missing."""
    cap = target if target is not None else sessions[-1]
    days = [d for d in sessions if fill_d <= d <= cap]
    for d in reversed(days):
        if target is not None and d == target:
            continue
        got = _last_close(d, symbol)
        if got is not None:
            return got
    return None


def _rank_job(args: tuple) -> dict:
    iso, look15_iso, names, iwm_l15, iwm1 = args
    session = date.fromisoformat(iso)
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
    empty = {"session": iso, "rows": [], "n_res": 0, "skipped": "no_names"}
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
    return {
        "session": iso,
        "rows": rows,
        "n_res": len(rows),
        "skipped": "" if rows else "thin",
    }


def _as_date(ts) -> date:
    if isinstance(ts, date) and not isinstance(ts, datetime):
        return ts
    if hasattr(ts, "date"):
        return ts.date()
    return date.fromisoformat(str(ts)[:10])


def _make_trade(
    h: dict,
    kind: str,
    notional: float,
    keep: bool,
    signal: date,
    feats: list[date],
    hold: int | None = None,
):
    """Return (trade or None, skip_fill, exit_partial). Hold is sessions after fill."""
    fill_d = fill_session_of(signal, kind, feats)
    if fill_d is None:
        return None, True, False
    if kind == "close":
        ent = h.get("now")
    elif kind == "open":
        ent = fill_0930(fill_d, h["symbol"])
    else:
        ent = _last_close(fill_d, h["symbol"])
    if ent is None:
        return None, True, False
    hold_n = HOLD if hold is None else int(hold)
    target = session_shift(fill_d, hold_n, feats)
    target_close = _last_close(target, h["symbol"]) if target is not None else None
    last_avail = None
    if target_close is None and keep:
        last_avail = last_available_rth(fill_d, target, feats, h["symbol"])
    ex, partial = resolve_exit_bar(target_close, keep, last_avail)
    if ex is None:
        return None, False, False
    tr = _short_n(h, ent, ex, kind, notional)
    if tr is None:
        return None, False, False
    tr["signal"] = signal
    tr["fill_date"] = fill_d
    tr["exit_date"] = _as_date(ex[0])
    tr["exit_partial"] = partial
    return tr, False, partial


def _mtm_and_peak(trades: list[dict], sessions: list[date], last_map: dict) -> tuple[list[float], float]:
    daily = [0.0] * len(sessions)
    idx = {d: i for i, d in enumerate(sessions)}
    marks: dict[int, float] = {}
    peak = 0.0
    for i, d in enumerate(sessions):
        live = 0.0
        for ti, t in enumerate(trades):
            fill_d = t["fill_date"]
            exit_d = t["exit_date"]
            sh = float(t["shares"])
            if d == fill_d:
                last = last_map.get((d.isoformat(), t["symbol"]))
                if last is None:
                    last = float(t["entry_px"])
                daily[i] += sh * (float(t["entry_px"]) - last) - sh * cost_per_share(float(t["entry_px"]))
                marks[ti] = last
            elif fill_d < d < exit_d:
                last = last_map.get((d.isoformat(), t["symbol"]))
                prev = marks.get(ti, float(t["entry_px"]))
                if last is None:
                    last = prev
                daily[i] += sh * (prev - last)
                marks[ti] = last
            elif d == exit_d:
                prev = marks.get(ti, float(t["entry_px"]))
                daily[i] += sh * (prev - float(t["exit_px"])) - sh * cost_per_share(float(t["exit_px"]))
            if fill_d <= d < exit_d:
                px = marks.get(ti)
                if px is None:
                    px = last_map.get((d.isoformat(), t["symbol"])) or float(t["entry_px"])
                live += abs(sh * float(px))
        if live > peak:
            peak = live
    return daily, peak


def _last_job(args: tuple) -> tuple[str, str, float | None]:
    iso, symbol = args
    got = _last_close(date.fromisoformat(iso), symbol)
    return iso, symbol, None if got is None else float(got[1])


def run_arrow65(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 65 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow65 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "Wednesday leftover plumbing. Same leftover short. Split on signal session. "
        "Id 0 reprints Arrow 56 wm_wed_3k. Did not change rank, n, lookback, weekday, or hold. "
        "Did not use an OOS month to pick a threshold. Did not retune leftover pair, SIC, MAX, "
        "or frozen B/flush. No new ingest. No Arrow 66.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    weds: list[date] = []
    for d in study:
        if d.weekday() != 2:
            continue
        look15 = session_shift(d, -LB, feats)
        e10 = session_shift(d, HOLD, feats)
        if look15 is None:
            continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
        weds.append(d)
        jobs.append(
            (
                d.isoformat(),
                look15.isoformat(),
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"Wednesday only n=8 lb={LB} hold={HOLD} from fill session  "
        f"jobs={len(jobs)} short leftover plumbing",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow65")
    prog.start_heartbeat()
    recs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_rank_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            recs[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 8 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    picks_by: dict[str, list[dict]] = {}
    nres_by: dict[str, int] = {}
    for d in weds:
        rec = recs.get(d.isoformat()) or {}
        nres_by[d.isoformat()] = int(rec.get("n_res") or 0)
        rows = list(rec.get("rows") or [])
        if (rec.get("n_res") or 0) < MIN_RESIDUAL:
            picks_by[d.isoformat()] = []
            continue
        picks_by[d.isoformat()] = select_shorts(rows, N_SHORT, None)

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in study
    }
    skips: dict[str, dict[str, int]] = {k: {"IS": 0, "OOS": 0} for k in IDS}
    partials: dict[str, dict[str, int]] = {k: {"IS": 0, "OOS": 0} for k in IDS}
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    usable: dict[str, list[date]] = {k: [] for k in IDS}

    for d in weds:
        picks = picks_by.get(d.isoformat()) or []
        split = "IS" if is_is_session(d) else "OOS"
        for name, kind, notional, keep in EXPERIMENTS:
            if nres_by.get(d.isoformat(), 0) >= MIN_RESIDUAL:
                usable[name].append(d)
            for h in picks:
                tr, skip_fill, partial = _make_trade(h, kind, notional, keep, d, feats)
                if skip_fill:
                    skips[name][split] += 1
                    continue
                if tr is None:
                    continue
                if partial:
                    partials[name][split] += 1
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                trades_all[name].append(tr)

    need: set[tuple[str, str]] = set()
    for name, trs in trades_all.items():
        for t in trs:
            fill_d, exit_d = t["fill_date"], t["exit_date"]
            for d in study:
                if fill_d <= d < exit_d:
                    need.add((d.isoformat(), t["symbol"]))
    last_map: dict[tuple[str, str], float] = {}
    if need:
        prog2 = Progress(len(need), "arrow65-mtm")
        prog2.start_heartbeat()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_last_job, job) for job in sorted(need)]
            for i, fut in enumerate(as_completed(futs), 1):
                iso, symbol, px = fut.result()
                if px is not None:
                    last_map[(iso, symbol)] = px
                prog2.mark(str(i), rows=1)
                if i % 64 == 0:
                    prog2.heartbeat()
        prog2.stop_heartbeat()
        prog2.heartbeat()

    sm0_is, _, tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, [d for d in weds if is_is_session(d)])
    reprint_ok = _within(sm0_is["per_day"], A56_WED_IS_DAY) and _within(sm0_is["n_trades"], A56_WED_IS_N)
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS entry $/day={sm0_is['per_day']:.2f}/{A56_WED_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A56_WED_IS_N} "
        + (
            "— within ±10% of Arrow 56 wm_wed_3k."
            if reprint_ok
            else "— DRIFT beyond ±10%. Plumbing not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 65 — Wednesday leftover plumbing (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 56 wm_wed_3k. "
            "Did not score plumbing on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 66.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow65_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    results = []
    for name, kind, notional, keep in EXPERIMENTS:
        weeks = usable[name]
        is_w = [d for d in weeks if is_is_session(d)]
        oos_w = [d for d in weeks if not is_is_session(d)]
        sm_ent_is, day_ent_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_ent_oos, day_ent_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
        sm_ent_is["n_win"], sm_ent_is["n_loss"] = _wins_losses(tr_is)
        sm_ent_oos["n_win"], sm_ent_oos["n_loss"] = _wins_losses(tr_oos)
        mtm_all, peak_all = _mtm_and_peak(trades_all[name], study, last_map)
        mtm_is = [mtm_all[study.index(d)] for d in is_sess]
        mtm_oos = [mtm_all[study.index(d)] for d in oos_sess]
        sm_mtm_is = _summarize_adv(mtm_is, tr_is, len(is_sess))
        sm_mtm_oos = _summarize_adv(mtm_oos, tr_oos, len(oos_sess))
        sm_mtm_is["n_win"], sm_mtm_is["n_loss"] = sm_ent_is["n_win"], sm_ent_is["n_loss"]
        sm_mtm_oos["n_win"], sm_mtm_oos["n_loss"] = sm_ent_oos["n_win"], sm_ent_oos["n_loss"]
        sm_mtm_is["daily_close_dd"] = daily_close_drawdown(mtm_is)
        sm_mtm_oos["daily_close_dd"] = daily_close_drawdown(mtm_oos)
        sm_mtm_is["worst_day"] = min(mtm_is) if mtm_is else 0.0
        sm_mtm_oos["worst_day"] = min(mtm_oos) if mtm_oos else 0.0
        sm_mtm_is["n_week"] = sm_ent_is["n_week"]
        sm_mtm_oos["n_week"] = sm_ent_oos["n_week"]
        sm_mtm_is["trades_per_week"] = sm_ent_is["trades_per_week"]
        sm_mtm_oos["trades_per_week"] = sm_ent_oos["trades_per_week"]
        sm_mtm_is["peak_conc"] = sm_ent_is["peak_conc"]
        sm_mtm_oos["peak_conc"] = sm_ent_oos["peak_conc"]
        sm_mtm_is["mean_conc"] = sm_ent_is["mean_conc"]
        sm_mtm_oos["mean_conc"] = sm_ent_oos["mean_conc"]
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        _, peak_is = _mtm_and_peak(tr_is, is_sess, last_map)
        _, peak_oos = _mtm_and_peak(tr_oos, oos_sess, last_map)
        # Cross-boundary: peak on IS/OOS calendar using ALL trades still on that day
        _, peak_is_x = _mtm_and_peak(trades_all[name], is_sess, last_map)
        _, peak_oos_x = _mtm_and_peak(trades_all[name], oos_sess, last_map)
        peak_is, peak_oos = peak_is_x, peak_oos_x
        fits = peak_all <= ACCOUNT + 1e-12
        seat = sm_mtm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_mtm_is["per_day"] >= 0.0
        slate = (
            sm_mtm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_mtm_is["per_day"] >= 0.0 and fits
        )
        results.append(
            {
                "name": name,
                "kind": kind,
                "notional": notional,
                "keep": keep,
                "ent_is": sm_ent_is,
                "ent_oos": sm_ent_oos,
                "mtm_is": sm_mtm_is,
                "mtm_oos": sm_mtm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "fill_skips_is": skips[name]["IS"],
                "fill_skips_oos": skips[name]["OOS"],
                "partial_is": partials[name]["IS"],
                "partial_oos": partials[name]["OOS"],
                "seat": seat,
                "slate": slate,
                "oos_excludes": sm_mtm_oos["ci_lo"] > 0 or sm_mtm_oos["ci_hi"] < 0,
                "is_months": _month_lines(mtm_is, is_sess),
                "oos_months": _month_lines(mtm_oos, oos_sess),
                "n_reb": len(weeks),
                "peak_live": peak_all,
                "peak_live_is": peak_is,
                "peak_live_oos": peak_oos,
                "fits": fits,
            }
        )

    seats = [r["name"] for r in results if r["seat"]]
    slates = [r["name"] for r in results if r["slate"]]
    if slates:
        verdict = (
            "VERDICT: SLATE — "
            + ", ".join(slates)
            + f" (OOS MTM >= ${FAILURE_LINE:.0f}/day, IS MTM not red, peak live <= ${ACCOUNT:.0f})."
        )
    elif seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS MTM >= ${SEAT_FLOOR:.0f}/day and IS MTM not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 65 engine has OOS MTM >= ${SEAT_FLOOR:.0f}/day AND non-red IS MTM."
        )
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    open_r = next(r for r in results if r["name"] == "open_4k")
    keep_r = next(r for r in results if r["name"] == "open_4k_keep")
    ctrl = results[0]
    next_open_seats = open_r["seat"] or open_r["slate"]
    keep_n = keep_r["ent_is"]["n_trades"] + keep_r["ent_oos"]["n_trades"]
    open_n = open_r["ent_is"]["n_trades"] + open_r["ent_oos"]["n_trades"]
    lead = (
        f"{reprint_line} Next-open still seats: {'yes' if next_open_seats else 'no'} "
        f"(open_4k OOS MTM ${open_r['mtm_oos']['per_day']:.2f}/day). "
        f"Keep-missing changed n: open_4k n={open_n} vs open_4k_keep n={keep_n} "
        f"(exit_partial IS {keep_r['partial_is']} OOS {keep_r['partial_oos']}). "
        f"Peak live {ctrl['name']} ${ctrl['peak_live']:.0f} vs old $69–$72k mark "
        f"(id0 peak ${ctrl['peak_live']:.0f}). "
        f"Seat ${SEAT_FLOOR:.0f} MTM: {seat_s}. Slate ${FAILURE_LINE:.0f}: {slate_s}."
    )
    honesty = (
        "Wednesday leftover plumbing. Same leftover short: Wednesday signal, lb=15 vs IWM, "
        "short eight, hold 10 from the fill session. Split on the signal session. "
        "Did not change rank, n, lookback, weekday, or hold. Did not open keep/cash or replace "
        "as extra ids. Did not walk hold 5/15. "
        "Did not retune Friday+Wednesday pair, SIC group, MAX, volume-pace, day-two, same-slot, "
        "Arrow 43, or frozen B|conj|atr1559|lock / flush|max6|repaired. "
        "Rings locked from IS; OOS is one look. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. "
        "Seat uses OOS MTM $/day. Equity, daily-close DD, and worst day are MTM. "
        "Do not call a CI that includes 0 EV. Combined dollars are not EV. No Arrow 66."
    )
    lines = [
        "Arrow 65 — Wednesday leftover plumbing (IS / OOS)",
        verdict,
        lead,
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day OOS MTM with IS MTM not red: {seat_s}.",
        f"Engines that clear slate ${FAILURE_LINE:.0f}/day OOS MTM with IS MTM not red and peak live fit: {slate_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"wednesday signals={len(weds)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"Wednesday signal last-RTH  n=8  lb={LB} hold={HOLD} from fill  "
        f"${NOTIONAL_3K:.0f}/${NOTIONAL_4K:.0f}",
        "close = signal last-RTH. open = next session 09:30 last. nextrth = next session last-RTH. "
        "keep = flatten last available RTH if day-10 exit missing. Peak live = |shares × last|.",
        "",
        f"{'id':<18} {'split':<4} {'entry$':>9} {'MTM$':>9} {'n':>6} {'hit':>6} {'t':>6} "
        f"{'skip':>5} {'part':>5} {'seat':>5}",
    ]
    for r in results:
        for split, ent, mtm, a, skip_a, n_a, months_s, peak_s, fskip, part in (
            (
                "IS",
                r["ent_is"],
                r["mtm_is"],
                r["a_is"],
                r["skip_is"],
                r["n_a_is"],
                r["is_months"],
                r["peak_live_is"],
                r["fill_skips_is"],
                r["partial_is"],
            ),
            (
                "OOS",
                r["ent_oos"],
                r["mtm_oos"],
                r["a_oos"],
                r["skip_oos"],
                r["n_a_oos"],
                r["oos_months"],
                r["peak_live_oos"],
                r["fill_skips_oos"],
                r["partial_oos"],
            ),
        ):
            if split == "OOS" and r["slate"]:
                flag = "SLATE"
            elif split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<18} {split:<4} {ent['per_day']:9.2f} {mtm['per_day']:9.2f} "
                f"{ent['n_trades']:6d} {ent['hit_rate']:6.3f} {mtm['t_stat']:6.2f} "
                f"{fskip:5d} {part:5d} {flag:>5}"
            )
            lines.extend(_fmt_book48(mtm))
            lines.append(
                f"    entry $/day={ent['per_day']:.2f}  MTM $/day={mtm['per_day']:.2f}  "
                f"IWM alpha $/day={a:.2f} (n={n_a} skip={skip_a})  "
                f"fill={r['kind']} notional=${r['notional']:.0f} keep={r['keep']}  "
                f"skips={fskip} exit_partial={part}{_ci_note(mtm)}"
            )
            lines.append(
                f"    peak live |shares×last| ${peak_s:.0f}  all-sessions ${r['peak_live']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  signals={r['n_reb']}"
            )
            lines.append(f"    MTM months: {months_s}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow65_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow65_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 65",
        "",
        verdict,
        "",
        lead,
        f"Seat ${SEAT_FLOOR:.0f} MTM: {seat_s}. Slate ${FAILURE_LINE:.0f}: {slate_s}.",
        "Wednesday leftover plumbing. Split on signal session. "
        "Did not retune leftover pair, SIC, MAX, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 66.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: entry IS ${r['ent_is']['per_day']:.2f} MTM ${r['mtm_is']['per_day']:.2f} "
            f"n={r['ent_is']['n_trades']}  entry OOS ${r['ent_oos']['per_day']:.2f} "
            f"MTM ${r['mtm_oos']['per_day']:.2f} n={r['ent_oos']['n_trades']} "
            f"t={r['mtm_oos']['t_stat']:.2f}  peak_live ${r['peak_live']:.0f}  "
            + ("SLATE" if r["slate"] else ("SEAT" if r["seat"] else "no seat"))
            + ("  OOS MTM CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
