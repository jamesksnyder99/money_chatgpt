"""Arrow 55 — Friday and Wednesday as a pair. Short only."""

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
from research.arrow51 import _ci_note
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
A54_PLAIN_IS_DAY = 495.38
A54_PLAIN_IS_N = 121
A52_WED_IS_DAY = 583.07
A52_WED_IS_N = 118
CONTROL_ID = "fri_6k"
WED_ID = "wed_6k"
NET_ID = "pair_3k_net"
N_SHORT = 8
MIN_RESIDUAL = 16
LB = 15
HOLD = 10
# name, weekdays (Mon=0), notional, net
EXPERIMENTS = (
    ("fri_6k", (4,), 6000.0, False),
    ("wed_6k", (2,), 6000.0, False),
    ("pair_6k", (4, 2), 6000.0, False),
    ("pair_3k", (4, 2), 3000.0, False),
    ("pair_3k_net", (4, 2), 3000.0, True),
    ("pair_3k_thu", (2, 3), 3000.0, True),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
STACKED = frozenset(n for n, wds, _nt, _net in EXPERIMENTS if len(wds) > 1)


def ticket_live(entry: date, exit: date, asof: date) -> bool:
    """On from entry session through the session before exit."""
    return entry <= asof < exit


def already_on(
    symbol: str,
    open_tickets: list[dict],
    asof: date,
    from_wd: int | None = None,
) -> bool:
    """True if symbol has a live ticket, optionally only from one weekday."""
    for t in open_tickets:
        if t["symbol"] != symbol:
            continue
        if from_wd is not None and t["wd"] != from_wd:
            continue
        if ticket_live(t["entry"], t["exit"], asof):
            return True
    return False


def net_skip(symbol: str, open_tickets: list[dict], asof: date, other_wd: int) -> bool:
    """Skip a second ticket when the name is already on from the other weekday."""
    return already_on(symbol, open_tickets, asof, from_wd=other_wd)


def nearest_wednesday(friday: date, weds: list[date]) -> date | None:
    """Following Wednesday, else preceding."""
    after = [w for w in weds if w > friday]
    if after:
        return min(after)
    before = [w for w in weds if w < friday]
    return max(before) if before else None


def _as_date(ts) -> date:
    if isinstance(ts, date) and not isinstance(ts, datetime):
        return ts
    if hasattr(ts, "date"):
        return ts.date()
    return ts


def peak_live_notional(trades: list[dict], sessions: list[date]) -> float:
    """Max over sessions of open-ticket notional (shares × entry px)."""
    peak = 0.0
    for d in sessions:
        live = 0.0
        for t in trades:
            e = _as_date(t["entry_ts"])
            x = _as_date(t["exit_ts"])
            if ticket_live(e, x, d):
                live += float(t["shares"]) * float(t["entry_px"])
        if live > peak:
            peak = live
    return peak


def _rebalance_job(args: tuple) -> dict:
    iso, look15_iso, exit10_iso, names, iwm_l15, iwm1, wd = args
    session = date.fromisoformat(iso)
    look15 = date.fromisoformat(look15_iso) if look15_iso else None
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
        now = _last_close(session, sym)
        if now is None:
            continue
        a15 = _last_close(look15, sym)
        if a15 is None:
            continue
        res = residual(a15[1], now[1], iwm_l15, iwm1)
        if res is None:
            continue
        ex = _last_close(ex10, sym) if ex10 is not None else None
        rows.append({**h, "residual": res, "now": now, "ex": ex})
    return {
        "session": iso,
        "rows": rows,
        "n_res": len(rows),
        "wd": wd,
        "skipped": "" if rows else "thin",
    }


def _picks_from(rec: dict) -> list[dict] | None:
    rows = list(rec.get("rows") or [])
    n_res = rec.get("n_res") or 0
    if n_res < MIN_RESIDUAL:
        return None
    return select_shorts(rows, N_SHORT, None)


def _other_wd(wds: tuple[int, ...], wd: int) -> int | None:
    if len(wds) != 2:
        return None
    return wds[1] if wd == wds[0] else wds[0]


def _assemble_trades(
    events: list[tuple[date, int, list[dict]]],
    notional: float,
    tag: str,
    net: bool,
    wds: tuple[int, ...],
) -> dict[str, list[dict]]:
    """Return trades keyed by entry iso. Net skips a second ticket on the other weekday."""
    by_iso: dict[str, list[dict]] = {}
    open_tickets: list[dict] = []
    for d, wd, picks in events:
        other = _other_wd(wds, wd) if net else None
        for h in picks:
            if other is not None and net_skip(h["symbol"], open_tickets, d, other):
                continue
            ent, ex = h.get("now"), h.get("ex")
            if ent is None or ex is None:
                continue
            tr = _short_n(h, ent, ex, tag, notional)
            if not tr:
                continue
            iso = d.isoformat()
            by_iso.setdefault(iso, []).append(tr)
            open_tickets.append(
                {
                    "symbol": h["symbol"],
                    "entry": d,
                    "exit": _as_date(ex[0]),
                    "wd": wd,
                }
            )
    return by_iso


def run_arrow55(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 55 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow55 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "Friday and Wednesday as a pair. Short only. lb=15 n=8 hold=10. "
        "Id 0 reprints Arrow 54 plain. Id 1 reprints Arrow 52 wed_h10. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No fade filter. "
        "No new ingest. No Arrow 56.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable_cal: dict[int, list[date]] = {2: [], 3: [], 4: []}
    for d in study:
        wd = d.weekday()
        if wd not in (2, 3, 4):
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
        usable_cal[wd].append(d)
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
        f"name-days={elig.height} jobs={len(jobs)} fri={len(usable_cal[4])} "
        f"wed={len(usable_cal[2])} thu={len(usable_cal[3])} short-only n=8 lb=15",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow55")
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

    eights: dict[int, dict[date, list[dict]]] = {2: {}, 3: {}, 4: {}}
    usable: dict[int, list[date]] = {2: [], 3: [], 4: []}
    n_res_by: dict[str, int] = {}
    for wd, days in usable_cal.items():
        for d in days:
            rec = recs.get(d.isoformat()) or {}
            n_res_by[d.isoformat()] = rec.get("n_res") or 0
            picks = _picks_from(rec)
            if picks is None:
                continue
            eights[wd][d] = picks
            usable[wd].append(d)

    def _events_for(wds: tuple[int, ...]) -> list[tuple[date, int, list[dict]]]:
        ev = []
        for wd in wds:
            for d in usable[wd]:
                ev.append((d, wd, eights[wd][d]))
        ev.sort(key=lambda x: (x[0], x[1]))
        return ev

    def _weeks_for(wds: tuple[int, ...]) -> list[date]:
        seen: set[date] = set()
        out: list[date] = []
        for wd in wds:
            for d in usable[wd]:
                if d not in seen:
                    seen.add(d)
                    out.append(d)
        return sorted(out)

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": n_res_by.get(d.isoformat(), 0)}
        for d in study
    }
    for iso, n in n_res_by.items():
        chunks.setdefault(iso, {"trades": {k: [] for k in IDS}, "n_res": 0})["n_res"] = n

    for name, wds, notional, net in EXPERIMENTS:
        by_iso = _assemble_trades(_events_for(wds), notional, name, net, wds)
        for iso, trs in by_iso.items():
            slot = chunks.setdefault(iso, {"trades": {k: [] for k in IDS}, "n_res": 0})
            slot["trades"][name] = trs

    is_fridays = [d for d in usable[4] if is_is_session(d)]
    sm0_is, _, _tr0 = _daily_and_trades(chunks, is_sess, CONTROL_ID, is_fridays)
    reprint0_ok = _within(sm0_is["per_day"], A54_PLAIN_IS_DAY) and _within(sm0_is["n_trades"], A54_PLAIN_IS_N)
    reprint0 = (
        f"Id 0 {CONTROL_ID} IS $/day={sm0_is['per_day']:.2f}/{A54_PLAIN_IS_DAY} "
        f"n={sm0_is['n_trades']}/{A54_PLAIN_IS_N} "
        + (
            "— within ±10% of Arrow 54 plain."
            if reprint0_ok
            else "— DRIFT beyond ±10% of Arrow 54 plain. Rings not a valid read."
        )
    )
    print(reprint0, flush=True)

    is_weds = [d for d in usable[2] if is_is_session(d)]
    sm1_is, _, _tr1 = _daily_and_trades(chunks, is_sess, WED_ID, is_weds)
    reprint1_ok = _within(sm1_is["per_day"], A52_WED_IS_DAY) and _within(sm1_is["n_trades"], A52_WED_IS_N)
    reprint1 = (
        f"Id 1 {WED_ID} IS $/day={sm1_is['per_day']:.2f}/{A52_WED_IS_DAY} "
        f"n={sm1_is['n_trades']}/{A52_WED_IS_N} "
        + (
            "— within ±10% of Arrow 52 wed_h10."
            if reprint1_ok
            else "— DRIFT beyond ±10% of Arrow 52 wed_h10. Rings not a valid read."
        )
    )
    print(reprint1, flush=True)
    reprint_ok = reprint0_ok and reprint1_ok
    reprint_line = reprint0 + " " + reprint1
    if not reprint_ok:
        text = (
            "Arrow 55 — Friday and Wednesday as a pair (IS / OOS)\n"
            "VERDICT: FAIL — id 0 or id 1 did not reprint. Did not score the pair on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 56.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow55_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    is_fri_eights = [d for d in usable[4] if is_is_session(d)]
    is_wed_eights = [d for d in usable[2] if is_is_session(d)]
    overlap_n = []
    for d in is_fri_eights:
        w = nearest_wednesday(d, is_wed_eights)
        if w is None:
            continue
        a = {h["symbol"] for h in eights[4][d]}
        b = {h["symbol"] for h in eights[2][w]}
        overlap_n.append(len(a & b))
    if overlap_n:
        mean_ov = sum(overlap_n) / len(overlap_n)
        ov_line = (
            f"IS character: mean names in common Friday eight vs nearest Wednesday eight "
            f"{mean_ov:.2f}/8 (n_pairs={len(overlap_n)}). Description. Does not pick an id."
        )
        same_eight = mean_ov >= 7.5
    else:
        mean_ov = 0.0
        ov_line = (
            "IS character: mean names in common Friday eight vs nearest Wednesday eight "
            "n_pairs=0. Description. Does not pick an id."
        )
        same_eight = False

    results = []
    ctrl_is = None
    ctrl_oos = None
    day_fri_is = day_fri_oos = day_wed_is = day_wed_oos = None
    for name, wds, notional, net in EXPERIMENTS:
        weeks = _weeks_for(wds)
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
        theoretical = float(N_SHORT) * float(notional) * (2.0 * len(wds))
        fits = peak <= ACCOUNT + 1e-12
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        slate = (
            sm_oos["per_day"] >= FAILURE_LINE - 1e-12
            and sm_is["per_day"] >= 0.0
            and (fits or name == "pair_6k")
        )
        if name == CONTROL_ID:
            ctrl_is = sm_is["per_day"]
            ctrl_oos = sm_oos["per_day"]
            day_fri_is = day_is
            day_fri_oos = day_oos
        if name == WED_ID:
            day_wed_is = day_is
            day_wed_oos = day_oos
        lift_both = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = sm_is["per_day"] > ctrl_is + 1e-12 and sm_oos["per_day"] > ctrl_oos + 1e-12
            if name in STACKED:
                lift_both = lift_both and fits
        results.append(
            {
                "name": name,
                "wds": wds,
                "notional": notional,
                "net": net,
                "stacked": name in STACKED,
                "is": sm_is,
                "oos": sm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "seat": seat,
                "slate": slate and fits,
                "slate_diag": slate,
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

    corr_is = _pearson(day_fri_is or [], day_wed_is or [])
    corr_oos = _pearson(day_fri_oos or [], day_wed_oos or [])
    corr_line = (
        f"Pearson daily PnL fri_6k vs wed_6k IS={corr_is:.3f} OOS={corr_oos:.3f} "
        "(entry-session series from ids 0 and 1)."
    )

    net_r = next(r for r in results if r["name"] == NET_ID)
    net_slate_fits = net_r["slate"]
    net_line = (
        f"$3k net pair (pair_3k_net) is a slate that fits $100k "
        f"(OOS ${net_r['oos']['per_day']:.2f}/day peak_live ${net_r['peak_live']:.0f})."
        if net_slate_fits
        else (
            f"$3k net pair (pair_3k_net) is not a slate that fits $100k "
            f"(OOS ${net_r['oos']['per_day']:.2f}/day peak_live ${net_r['peak_live']:.0f} "
            f"fits={'yes' if net_r['fits'] else 'NO'})."
        )
    )
    same_line = (
        f"Friday and Wednesday eights are the same eight names (mean overlap {mean_ov:.2f}/8)."
        if same_eight
        else f"Friday and Wednesday eights are not the same eight names (mean overlap {mean_ov:.2f}/8)."
    )

    pair6 = next(r for r in results if r["name"] == "pair_6k")
    pair6_cap = (
        f"Id 2 pair_6k peak live notional ${pair6['peak_live']:.0f} "
        + (
            "fits $100k."
            if pair6["fits"]
            else "misses the $100k cap — diagnostic paper stack, allowed to miss."
        )
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
            f"VERDICT: FAIL — no Arrow 55 short ring has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    both_s = ", ".join(both) if both else "none"
    seat_s = ", ".join(seats) if seats else "none"
    slate_s = ", ".join(slates) if slates else "none"
    honesty = (
        "Short only. Stacked Friday and Wednesday leftover vs IWM. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. Did not add a long leg. "
        "Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "No fade filter. No sector map. "
        "A stacked id counts as better than id 0 only if it lifts $/day on both IS and OOS and fits $100k. "
        "Slate needs OOS >= $200/day, IS not red, and peak live notional <= $100k. "
        "Id 2 is allowed to miss the $100k cap — diagnostic. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 56."
    )
    lines = [
        "Arrow 55 — Friday and Wednesday as a pair (IS / OOS)",
        verdict,
        reprint_line,
        corr_line,
        net_line,
        same_line,
        pair6_cap,
        f"Ids that lift $/day versus fri_6k on both IS and OOS and fit $100k (stacked) "
        f"or lift both (id 1): {both_s}.",
        f"Ids that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Ids that clear slate ${FAILURE_LINE:.0f}/day on OOS with IS not red and peak live <= $100k: {slate_s}.",
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"friday rebalances={len(usable_cal[4])}  wednesday rebalances={len(usable_cal[2])}  "
        f"thursday rebalances={len(usable_cal[3])}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 44–54, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  short residual winners  n=8  lb=15  hold=10",
        "Skip a rebalance if fewer than 16 eligible names have a residual. "
        "Skip a name if a required close is missing. Holiday weekday: skip; do not roll. "
        "pair_6k / pair_3k allow two tickets in the same name. pair_3k_net and pair_3k_thu skip the later ticket.",
        "",
        ov_line,
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
            elif split == "OOS" and r["name"] == "pair_6k" and r["slate_diag"] and not r["fits"]:
                flag = "DIAG"
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
            wds = "/".join({4: "Fri", 2: "Wed", 3: "Thu"}[w] for w in r["wds"])
            net_s = " net" if r["net"] else ""
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_short={N_SHORT} notional=${r['notional']:.0f}  {wds}{net_s}  "
                f"lb={LB} hold={HOLD}{_ci_note(sm)}"
            )
            lines.append(
                f"    peak live notional ${peak_s:.0f}  two-cohort×legs ${r['theoretical']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  rebalances={r['n_reb']}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow55_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow55_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 55",
        "",
        verdict,
        "",
        reprint_line,
        corr_line,
        net_line,
        same_line,
        pair6_cap,
        f"Lift vs fri_6k on both (stacked also must fit $100k): {both_s}.",
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.  Slate ${FAILURE_LINE:.0f}: {slate_s}.",
        "Short only. Friday + Wednesday pair. Did not use an OOS month to pick a threshold. "
        "Did not add a long leg. Did not retune Arrow 43 clocks or frozen B/flush. "
        "No fade filter. No new ingest. No Arrow 56.",
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
