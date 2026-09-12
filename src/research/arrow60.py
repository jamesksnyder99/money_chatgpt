"""Arrow 60 — day-two after an extreme. Long and short are separate engines."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, last_rth, load_combined_iwm
from research.arrow44 import MIN_PDV, MIN_PX, MAX_PX, _alpha, _month_lines
from research.arrow45 import _daily_and_trades
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow57 import _char_stats, _long_n, name_return
from research.arrow59 import _as_date, _clock, _read_bars, peak_live_notional
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
from research.signals import MINUTE_1559, RTH_OPEN

ET = ZoneInfo("America/New_York")
CONTROL_ID = "short_0930_1159"
LONG_H1 = "long_0930_1159"
N_SLOT = 8
NOTIONAL = 3000.0
EXTREME_BAR = 1.10
STILL_BAR = 1.05
# name, side, exit (1159/next), filter (all/still/gave)
EXPERIMENTS = (
    ("short_0930_1159", "short", "1159", "all"),
    ("long_0930_1159", "long", "1159", "all"),
    ("short_0930_next", "short", "next", "all"),
    ("short_still_1159", "short", "1159", "still"),
    ("short_gave_1159", "short", "1159", "gave"),
    ("long_gave_1159", "long", "1159", "gave"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def is_extreme(high: float | None, prior_close: float | None) -> bool:
    """T RTH high ≥ 1.10 × prior last-RTH close."""
    if high is None or prior_close is None or prior_close <= 0:
        return False
    return float(high) >= EXTREME_BAR * float(prior_close) - 1e-12


def still_extended(t_close: float | None, prior_close: float | None) -> bool:
    """T last-RTH still ≥ 1.05 × prior close."""
    if t_close is None or prior_close is None or prior_close <= 0:
        return False
    return float(t_close) >= STILL_BAR * float(prior_close) - 1e-12


def gave_back(t_close: float | None, prior_close: float | None) -> bool:
    """T last-RTH < 1.05 × prior close."""
    if t_close is None or prior_close is None or prior_close <= 0:
        return False
    return float(t_close) < STILL_BAR * float(prior_close) - 1e-12


def select_extremes(rows: list[dict], n: int = N_SLOT) -> list[dict]:
    ranked = sorted(rows, key=lambda r: (-float(r["ext"]), r["symbol"]))
    return ranked[: max(0, int(n))]


def _fmt_book60(sm: dict) -> list[str]:
    lines = _fmt_book48(sm)
    lines[0] = lines[0].replace("n/week=", "n/sess=")
    return lines


def extract_session(session: date, symbol: str) -> dict | None:
    """09:30 open, RTH high, last RTH close from one parquet."""
    df = _read_bars(session, symbol)
    if df is None:
        return None
    fill = None
    high = None
    last = last_rth(df, session)
    last_t = _clock(last["bar_start"]) if last is not None else MINUTE_1559
    for rec in df.sort("bar_start").iter_rows(named=True):
        ts = rec["bar_start"]
        t = _clock(ts)
        op, hi = rec["open"], rec["high"]
        if t == RTH_OPEN and op is not None and float(op) > 0:
            fill = (ts, float(op))
        if t >= RTH_OPEN and t <= last_t and hi is not None and float(hi) > 0:
            hv = float(hi)
            if high is None or hv > high:
                high = hv
    last_px = (last["bar_start"], float(last["close"])) if last is not None else None
    return {"fill0930": fill, "high": high, "last": last_px}


def _symbol_job(args: tuple) -> list[dict]:
    symbol, elig_rows, feat_iso = args
    feats = [date.fromisoformat(x) for x in feat_iso]
    idx = {d: i for i, d in enumerate(feats)}
    elig_dates = []
    meta = {}
    for h in elig_rows:
        d = _as_date(h["session"])
        elig_dates.append(d)
        meta[d] = h
    need: set[date] = set()
    for d in elig_dates:
        i = idx.get(d)
        if i is None:
            continue
        for j in (i - 1, i, i + 1, i + 2):
            if 0 <= j < len(feats):
                need.add(feats[j])
    extracted: dict[date, dict | None] = {}
    for d in need:
        extracted[d] = extract_session(d, symbol)
    out = []
    for d in elig_dates:
        i = idx.get(d)
        if i is None or i < 1 or i + 1 >= len(feats):
            continue
        t0 = extracted.get(feats[i - 1])
        t = extracted.get(d)
        t1 = extracted.get(feats[i + 1])
        t2 = extracted.get(feats[i + 2]) if i + 2 < len(feats) else None
        if t0 is None or t0.get("last") is None or t is None or t.get("high") is None:
            continue
        prior = t0["last"][1]
        if not is_extreme(t["high"], prior):
            continue
        if t1 is None or t1.get("fill0930") is None:
            continue
        t_close = t["last"][1] if t.get("last") else None
        fill = t1["fill0930"]
        ex1159 = t1.get("last")
        nxt = t2["last"] if t2 and t2.get("last") else None
        h = meta[d]
        day_ret = name_return(fill[1], ex1159[1]) if ex1159 is not None else None
        out.append(
            {
                "t": d.isoformat(),
                "entry": feats[i + 1].isoformat(),
                "symbol": symbol,
                "prior_close": h["prior_close"],
                "prior_dv": h["prior_dv"],
                "ext": float(t["high"]) / prior - 1.0,
                "still": still_extended(t_close, prior),
                "gave": gave_back(t_close, prior),
                "now": fill,
                "ex1159": ex1159,
                "ex_next": nxt,
                "day_ret": day_ret,
            }
        )
    return out


def _exit_of(h: dict, kind: str):
    return h.get("ex1159") if kind == "1159" else h.get("ex_next")


def _trade(h: dict, side: str, ex_kind: str, tag: str):
    ent, ex = h.get("now"), _exit_of(h, ex_kind)
    if ent is None or ex is None:
        return None
    if side == "short":
        return _short_n(h, ent, ex, tag, NOTIONAL)
    return _long_n(h, ent, ex, tag, NOTIONAL)


def _passes(h: dict, filt: str) -> bool:
    if filt == "still":
        return bool(h.get("still"))
    if filt == "gave":
        return bool(h.get("gave"))
    return True


def run_arrow60(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 60 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    feat_iso = [d.isoformat() for d in feats]
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow60 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "day-two after an extreme. Long and short are separate engines. "
        "T high >= 1.10 x prior last-RTH; entry T+1 09:30. "
        "Did not retune leftover pair, same-slot, volume-pace, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 61.",
        flush=True,
    )
    elig = _elig_frame()
    by_sym: dict[str, list[dict]] = {}
    for rec in elig.select("session_date", "symbol", "prior_close", "prior_dollar_volume").iter_rows(
        named=True
    ):
        sym = str(rec["symbol"])
        by_sym.setdefault(sym, []).append(
            {
                "session": _as_date(rec["session_date"]),
                "prior_close": float(rec["prior_close"]),
                "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
            }
        )
    jobs = [(sym, rows, feat_iso) for sym, rows in by_sym.items()]
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} symbols={len(jobs)} extreme=+10% RTH high  "
        f"entry T+1 09:30  n<=8  ${NOTIONAL:.0f}  long and short separate",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow60")
    prog.start_heartbeat()
    by_t: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_symbol_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            for r in fut.result():
                by_t.setdefault(r["t"], []).append(r)
            prog.mark(str(i), rows=1)
            if i % 32 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in study
    }
    usable: dict[str, list[date]] = {k: [] for k in IDS}
    raw_counts: list[int] = []
    booked_rets: list[float] = []
    still_rets: list[float] = []
    gave_rets: list[float] = []

    for t_iso, rows in by_t.items():
        t_date = date.fromisoformat(t_iso)
        entry = session_shift(t_date, 1, feats)
        if entry is None or entry not in set(study):
            continue
        raw_n = len(rows)
        booked = select_extremes(rows, N_SLOT)
        eiso = entry.isoformat()
        chunks.setdefault(eiso, {"trades": {k: [] for k in IDS}, "n_res": 0})
        chunks[eiso]["n_res"] = max(chunks[eiso]["n_res"], raw_n)
        if is_is_session(entry):
            raw_counts.append(raw_n)
            for h in booked:
                dr = h.get("day_ret")
                if dr is None:
                    continue
                booked_rets.append(float(dr))
                if h.get("still"):
                    still_rets.append(float(dr))
                elif h.get("gave"):
                    gave_rets.append(float(dr))
        for name, side, ex_kind, filt in EXPERIMENTS:
            picks = [h for h in booked if _passes(h, filt)]
            if not picks:
                continue
            trs = []
            for h in picks:
                tr = _trade(h, side, ex_kind, name)
                if tr:
                    trs.append(tr)
            if not trs:
                continue
            slot = chunks[eiso]["trades"]
            slot[name] = list(slot.get(name) or []) + trs
            usable[name].append(entry)

    if raw_counts:
        mean_n = sum(raw_counts) / len(raw_counts)
        max_n = max(raw_counts)
        count_s = f"n_sess={len(raw_counts)} mean={mean_n:.2f} max={max_n}"
    else:
        count_s = "n_sess=0"
    char_lines = [
        "IS character: T extremes (entry T+1 is IS). Description. Does not pick an id.",
        f"  T extremes per session {count_s}",
        f"  booked T+1 09:30-15:59 {_char_stats(booked_rets)}",
        f"  still-extended (>=1.05) {_char_stats(still_rets)}",
        f"  gave-back (<1.05) {_char_stats(gave_rets)}",
    ]

    results = []
    day0_is = day0_oos = day1_is = day1_oos = None
    iwm = load_combined_iwm()
    for name, side, ex_kind, filt in EXPERIMENTS:
        weeks = sorted(set(usable[name]))
        is_w = [x for x in weeks if is_is_session(x)]
        oos_w = [x for x in weeks if not is_is_session(x)]
        sm_is, day_is, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_oos, day_oos, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
        sm_is["n_win"], sm_is["n_loss"] = _wins_losses(tr_is)
        sm_oos["n_win"], sm_oos["n_loss"] = _wins_losses(tr_oos)
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        peak_is = peak_live_notional(tr_is, is_sess)
        peak_oos = peak_live_notional(tr_oos, oos_sess)
        peak = max(peak_is, peak_oos)
        theoretical = float(N_SLOT) * NOTIONAL * (2.0 if ex_kind == "next" else 1.0)
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
                "ex": ex_kind,
                "filt": filt,
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
            f"VERDICT: FAIL — no Arrow 60 engine has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    seat_s = ", ".join(seats) if seats else "none"
    short_s = ", ".join(short_seats) if short_seats else "none"
    long_s = ", ".join(long_seats) if long_seats else "none"
    still_r = next(r for r in results if r["name"] == "short_still_1159")
    gave_s = next(r for r in results if r["name"] == "short_gave_1159")
    split_line = (
        f"Still-extended short IS ${still_r['is']['per_day']:.2f} OOS ${still_r['oos']['per_day']:.2f}. "
        f"Gave-back short IS ${gave_s['is']['per_day']:.2f} OOS ${gave_s['oos']['per_day']:.2f}."
    )
    honesty = (
        "Day-two after an extreme. Hotel 5 of 7 (home hour skipped). "
        "Long and short are separate engines. Did not build them as a sign flip of one door. "
        "Did not retune the Friday+Wednesday leftover pair, same-slot ids, volume-pace ids, "
        "Arrow 43 clocks, or frozen B|conj|atr1559|lock / flush|max6|repaired. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. Split on the entry session (T+1). "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS. "
        "Combined dollars are not EV. No Arrow 61."
    )
    lines = [
        "Arrow 60 — day-two after an extreme (IS / OOS)",
        verdict,
        char_lines[0],
        char_lines[1],
        char_lines[2],
        char_lines[3],
        char_lines[4],
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Short seats: {short_s}. Long seats: {long_s}. A long id is not judged as a failed short.",
        split_line,
        corr_line,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"symbols={len(jobs)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility on T: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"extreme T high >= {EXTREME_BAR:.2f}x prior last-RTH  still >= {STILL_BAR:.2f}x  "
        f"entry T+1 09:30  n<=8  ${NOTIONAL:.0f}/name",
        "If more than 8 extremes on T, take the 8 largest highs versus prior close. "
        "If 1-8, take them all. Skip a name if T+1 09:30 or the required exit is missing.",
        "",
        *char_lines,
        "",
        f"{'id':<20} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
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
                f"{r['name']:<20} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} "
                f"{r['side']:>6} {flag:>5}"
            )
            lines.extend(_fmt_book60(sm))
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_slot<={N_SLOT} notional=${NOTIONAL:.0f}  {r['side']}  "
                f"exit={r['ex']}  filter={r['filt']}{_ci_note(sm)}"
            )
            lines.append(
                f"    peak live notional ${peak_s:.0f}  hold-cohorts ${r['theoretical']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  sessions={r['n_reb']}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow60_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow60_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 60",
        "",
        verdict,
        "",
        char_lines[1],
        char_lines[2],
        char_lines[3],
        char_lines[4],
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}. Short: {short_s}. Long: {long_s}.",
        split_line,
        corr_line,
        "Day-two after an extreme. Long and short are separate engines. "
        "Did not retune leftover pair, same-slot, volume-pace, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 61.",
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
