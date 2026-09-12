"""Arrow 57 — same-slot hotel, first night. Long and short are separate engines."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, _pack, load_combined_iwm
from research.arrow44 import (
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _alpha,
    _by_sess,
    _iwm_last_close,
    _last_close,
    _month_lines,
)
from research.arrow45 import _daily_and_trades
from research.arrow47 import _short_n, shares_for
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import peak_live_notional
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO, signed_pnl

ET = ZoneInfo("America/New_York")
CONTROL_ID = "short_win_h1"
LONG_H1 = "long_lose_h1"
N_SLOT = 8
MIN_RESIDUAL = 16
NOTIONAL = 3000.0
# name, side, slot (win/lose), rank (raw/res), hold
EXPERIMENTS = (
    ("short_win_h1", "short", "win", "raw", 1),
    ("long_lose_h1", "long", "lose", "raw", 1),
    ("short_win_h5", "short", "win", "raw", 5),
    ("long_lose_h5", "long", "lose", "raw", 5),
    ("short_res_h1", "short", "win", "res", 1),
    ("long_res_h1", "long", "lose", "res", 1),
)
IDS = tuple(e[0] for e in EXPERIMENTS)

_CLOSE: dict[tuple[str, str], tuple | None] = {}
_CLOSE_LOCK = threading.Lock()


def name_return(px0: float | None, px1: float | None) -> float | None:
    """One-session close-to-close. Not a 15-session leftover."""
    if px0 is None or px1 is None or px0 <= 0 or px1 <= 0:
        return None
    return px1 / px0 - 1.0


def select_winners(rows: list[dict], n: int = N_SLOT, key: str = "ret") -> list[dict]:
    ranked = sorted((r for r in rows if r.get(key) is not None), key=lambda r: r[key], reverse=True)
    return ranked[: max(0, int(n))]


def select_losers(rows: list[dict], n: int = N_SLOT, key: str = "ret") -> list[dict]:
    ranked = sorted((r for r in rows if r.get(key) is not None), key=lambda r: r[key])
    return ranked[: max(0, int(n))]


def hold_exit(entry: date, hold: int, sessions: list[date] | None = None) -> date | None:
    """Hold 1 = next session; hold 5 = five sessions later."""
    return session_shift(entry, hold, sessions)


def _cached_last_close(session: date, symbol: str) -> tuple | None:
    key = (session.isoformat(), symbol)
    with _CLOSE_LOCK:
        if key in _CLOSE:
            return _CLOSE[key]
    val = _last_close(session, symbol)
    with _CLOSE_LOCK:
        _CLOSE[key] = val
    return val


def _long_n(h: dict, ent: tuple, ex: tuple, tag: str, notional: float) -> dict | None:
    shares = shares_for(ent[1], notional)
    if shares < 1:
        return None
    pnl = signed_pnl(1, shares, ent[1], ex[1])
    return _pack(pnl, 1, shares, ent[1], ex[1], ent[0], ex[0], tag, h["symbol"])


def _fmt_book57(sm: dict) -> list[str]:
    lines = _fmt_book48(sm)
    lines[0] = lines[0].replace("n/week=", "n/sess=")
    return lines


def _char_stats(xs: list[float]) -> str:
    if not xs:
        return "n=0"
    n = len(xs)
    mean = sum(xs) / n
    hit = sum(1 for x in xs if x > 0) / n
    return f"n={n} mean={mean:.5f} hit={hit:.3f}"


def _slim(h: dict) -> dict:
    return {
        "symbol": h["symbol"],
        "prior_close": h["prior_close"],
        "prior_dv": h["prior_dv"],
        "ret": h["ret"],
        "residual": h.get("residual"),
        "now": h["now"],
        "e1": h.get("e1"),
        "e5": h.get("e5"),
        "next_ret": h.get("next_ret"),
    }


def _session_job(args: tuple) -> dict:
    iso, look_iso, e1_iso, e5_iso, names, iwm_l1, iwm1 = args
    session = date.fromisoformat(iso)
    look = date.fromisoformat(look_iso) if look_iso else None
    e1d = date.fromisoformat(e1_iso) if e1_iso else None
    e5d = date.fromisoformat(e5_iso) if e5_iso else None
    empty = {
        "session": iso,
        "n_res": 0,
        "win_raw": [],
        "lose_raw": [],
        "win_res": [],
        "lose_res": [],
        "skipped": "no_names",
    }
    if not names or look is None:
        empty["skipped"] = "look"
        return empty
    iwm_ret = name_return(iwm_l1, iwm1)
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
        nxt = name_return(now[1], e1[1]) if e1 is not None else None
        res = (ret - iwm_ret) if iwm_ret is not None else None
        rows.append(
            {
                **h,
                "ret": ret,
                "residual": res,
                "now": now,
                "e1": e1,
                "e5": e5,
                "next_ret": nxt,
            }
        )
    n_res = len(rows)
    if n_res < MIN_RESIDUAL:
        empty["n_res"] = n_res
        empty["skipped"] = "thin"
        return empty
    win_raw = [_slim(h) for h in select_winners(rows, N_SLOT, "ret")]
    lose_raw = [_slim(h) for h in select_losers(rows, N_SLOT, "ret")]
    res_rows = [r for r in rows if r.get("residual") is not None]
    if len(res_rows) >= MIN_RESIDUAL:
        win_res = [_slim(h) for h in select_winners(res_rows, N_SLOT, "residual")]
        lose_res = [_slim(h) for h in select_losers(res_rows, N_SLOT, "residual")]
    else:
        win_res, lose_res = [], []
    return {
        "session": iso,
        "n_res": n_res,
        "win_raw": win_raw,
        "lose_raw": lose_raw,
        "win_res": win_res,
        "lose_res": lose_res,
        "skipped": "",
    }


def _slot_of(rec: dict, slot: str, rank: str) -> list[dict]:
    if rank == "res":
        return list(rec.get("win_res" if slot == "win" else "lose_res") or [])
    return list(rec.get("win_raw" if slot == "win" else "lose_raw") or [])


def _make_trade(h: dict, hold: int, side: str, tag: str) -> dict | None:
    ent = h.get("now")
    ex = h.get("e1") if hold == 1 else h.get("e5")
    if ent is None or ex is None:
        return None
    if side == "short":
        return _short_n(h, ent, ex, tag, NOTIONAL)
    return _long_n(h, ent, ex, tag, NOTIONAL)


def run_arrow57(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 57 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow57 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "same-slot hotel, first night. Long and short are separate engines. "
        "Raw 1-session close-to-close jersey, not 15-session leftover. "
        "Did not retune Friday+Wednesday leftover pair or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 58.",
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
        if look is None:
            continue
        i_l1 = _iwm_last_close(iwm, look)
        i1 = _iwm_last_close(iwm, d)
        jobs.append(
            (
                d.isoformat(),
                look.isoformat(),
                e1.isoformat() if e1 is not None else None,
                e5.isoformat() if e5 is not None else None,
                by.get(d.isoformat(), []),
                i_l1[1] if i_l1 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} jobs={len(jobs)} short and long separate  n=8  $3000  "
        f"hold 1 or 5  last-RTH",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow57")
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
    char: dict[str, list[float]] = {
        "win_raw": [],
        "lose_raw": [],
        "win_res": [],
        "lose_res": [],
    }
    overlap_n: list[int] = []
    usable: dict[str, list[date]] = {k: [] for k in IDS}

    for d in study:
        rec = recs.get(d.isoformat()) or {}
        n_res = rec.get("n_res") or 0
        chunks[d.isoformat()]["n_res"] = n_res
        if n_res < MIN_RESIDUAL:
            continue
        if is_is_session(d):
            for key in ("win_raw", "lose_raw", "win_res", "lose_res"):
                for h in rec.get(key) or []:
                    nxt = h.get("next_ret")
                    if nxt is not None:
                        char[key].append(float(nxt))
            wr = {h["symbol"] for h in rec.get("win_raw") or []}
            ws = {h["symbol"] for h in rec.get("win_res") or []}
            if wr and ws:
                overlap_n.append(len(wr & ws))
        for name, side, slot, rank, hold in EXPERIMENTS:
            picks = _slot_of(rec, slot, rank)
            if not picks:
                continue
            trs = []
            for h in picks:
                tr = _make_trade(h, hold, side, name)
                if tr:
                    trs.append(tr)
            if not trs:
                continue
            chunks[d.isoformat()]["trades"][name] = trs
            usable[name].append(d)

    if overlap_n:
        mean_ov = sum(overlap_n) / len(overlap_n)
        jersey_same = mean_ov >= 7.5
    else:
        mean_ov = 0.0
        jersey_same = False
    jersey_line = (
        f"IWM does not change the jersey (id 0 vs id 4 mean overlap {mean_ov:.2f}/8, "
        f"n_sess={len(overlap_n)}). Subtracting a session-wide IWM return is a scalar."
        if jersey_same
        else (
            f"IWM changes the jersey (id 0 vs id 4 mean overlap {mean_ov:.2f}/8, "
            f"n_sess={len(overlap_n)})."
        )
    )
    char_lines = [
        "IS character: next-session raw return of the slot eights. Description. Does not pick an id.",
        f"  winner-slot eight { _char_stats(char['win_raw']) }",
        f"  loser-slot eight { _char_stats(char['lose_raw']) }",
        f"  residual-vs-IWM winner eight { _char_stats(char['win_res']) }",
        f"  residual-vs-IWM loser eight { _char_stats(char['lose_res']) }",
    ]

    results = []
    day0_is = day0_oos = day1_is = day1_oos = None
    for name, side, slot, rank, hold in EXPERIMENTS:
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
        theoretical = float(N_SLOT) * NOTIONAL * float(hold)
        fits = peak <= ACCOUNT + 1e-12
        seat = sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        if name == CONTROL_ID:
            day0_is, day0_oos = day_is, day_oos
        if name == LONG_H1:
            day1_is, day1_oos = day_is, day_oos
        results.append(
            {
                "name": name,
                "side": side,
                "slot": slot,
                "rank": rank,
                "hold": hold,
                "is": sm_is,
                "oos": sm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "seat": seat,
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

    corr_is = _pearson(day0_is or [], day1_is or [])
    corr_oos = _pearson(day0_oos or [], day1_oos or [])
    corr_line = (
        f"Pearson daily PnL {CONTROL_ID} vs {LONG_H1} IS={corr_is:.3f} OOS={corr_oos:.3f} "
        "(entry-session series)."
    )
    short_seats = [r["name"] for r in results if r["seat"] and r["side"] == "short"]
    long_seats = [r["name"] for r in results if r["seat"] and r["side"] == "long"]
    seats = [r["name"] for r in results if r["seat"]]
    if seats:
        verdict = (
            "VERDICT: SEAT — "
            + ", ".join(seats)
            + f" (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red)."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — no Arrow 57 engine has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    short_s = ", ".join(short_seats) if short_seats else "none"
    long_s = ", ".join(long_seats) if long_seats else "none"
    seat_s = ", ".join(seats) if seats else "none"
    long_vs_short = (
        f"Short seats: {short_s}. Long seats: {long_s}. "
        "A long id is not judged as a failed short."
    )
    honesty = (
        "Same-slot hotel, first night. Long and short are separate engines. "
        "Did not build them as a sign flip of one door. "
        "Did not retune the Friday+Wednesday leftover pair, Arrow 43 clocks, "
        "or frozen B|conj|atr1559|lock / flush|max6|repaired. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. "
        "Slate is $200/day for the shop, not this first night's job. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 58."
    )
    lines = [
        "Arrow 57 — same-slot hotel, first night (IS / OOS)",
        verdict,
        char_lines[0],
        char_lines[1],
        char_lines[2],
        char_lines[3],
        char_lines[4],
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        long_vs_short,
        corr_line,
        jersey_line,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day (shop, not this night)  "
        f"seat_floor={SEAT_FLOOR:.0f}/day  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"jobs={len(jobs)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as leftover pair, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  slot n=8  ${NOTIONAL:.0f}/name  last-RTH  "
        f"two h1 engines same day ${2.0 * N_SLOT * NOTIONAL:.0f}",
        "Skip T if fewer than 16 eligible names have a T return. "
        "Skip a name if a required close is missing. "
        "Winner slot = 8 largest T close-to-close. Loser slot = 8 smallest. "
        "Residual ids subtract IWM T return.",
        "",
        *char_lines,
        "",
        f"{'id':<16} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'side':>6} {'seat':>5}",
    ]
    for r in results:
        for split, sm, a, skip, n_a, months, peak_s in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"], r["peak_live_is"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"], r["peak_live_oos"]),
        ):
            if split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<16} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} "
                f"{r['side']:>6} {flag:>5}"
            )
            lines.extend(_fmt_book57(sm))
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_slot={N_SLOT} notional=${NOTIONAL:.0f}  {r['side']} {r['slot']} {r['rank']}  "
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
    (REPORTS / "arrow57_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow57_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 57",
        "",
        verdict,
        "",
        char_lines[1],
        char_lines[2],
        char_lines[3],
        char_lines[4],
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}.",
        long_vs_short,
        corr_line,
        jersey_line,
        "Same-slot hotel. Long and short are separate engines. "
        "Did not retune Friday+Wednesday leftover pair or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 58.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']} t={r['oos']['t_stat']:.2f}  "
            f"peak_live ${r['peak_live']:.0f}  "
            + ("SEAT" if r["seat"] else "no seat")
            + ("  OOS CI excludes 0" if r["oos_excludes"] else "")
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
