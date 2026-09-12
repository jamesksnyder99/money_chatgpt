"""Arrow 62 — last-month MAX, first night. Long and short are separate engines."""

from __future__ import annotations

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS, VIRGIN_BARS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, load_combined_iwm
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
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import peak_live_notional
from research.arrow57 import _char_stats, _long_n, name_return
from research.clock import (
    arrow62_feature_sessions,
    combined_study_sessions,
    is_is_session,
    month_first_last,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
CONTROL_ID = "short_max_m"
LONG_H1 = "long_min_m"
N_SLOT = 8
MIN_NAMES = 16
NOTIONAL = 3000.0
NOTIONAL_4K = 4000.0
# name, side, slot (max/min/iwm_max), n, hold (month/h10), notional
EXPERIMENTS = (
    ("short_max_m", "short", "max", 8, "month", 3000.0),
    ("long_min_m", "long", "min", 8, "month", 3000.0),
    ("short_max_h10", "short", "max", 8, "h10", 3000.0),
    ("short_max_iwm_m", "short", "iwm_max", 8, "month", 3000.0),
    ("short_max_n15_m", "short", "max", 15, "month", 3000.0),
    ("short_max_4k_m", "short", "max", 8, "month", 4000.0),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def prior_month_return(px_first: float | None, px_last: float | None) -> float | None:
    """Last RTH of last session in M-1 / last RTH of first session in M-1 − 1."""
    return name_return(px_first, px_last)


def select_max(rows: list[dict], n: int = N_SLOT, key: str = "ret") -> list[dict]:
    ranked = sorted(
        (r for r in rows if r.get(key) is not None),
        key=lambda r: (-float(r[key]), r["symbol"]),
    )
    return ranked[: max(0, int(n))]


def select_min(rows: list[dict], n: int = N_SLOT, key: str = "ret") -> list[dict]:
    ranked = sorted(
        (r for r in rows if r.get(key) is not None),
        key=lambda r: (float(r[key]), r["symbol"]),
    )
    return ranked[: max(0, int(n))]


def hold_month_exit(entry: date, sessions: list[date]) -> date | None:
    """Last NYSE session of the entry calendar month."""
    days = [d for d in sessions if d.year == entry.year and d.month == entry.month]
    return max(days) if days else None


def hold_n(entry: date, n: int, sessions: list[date]) -> date | None:
    """Hold n = n sessions later."""
    return session_shift(entry, n, sessions)


def prior_month_stamps(entry: date, sessions: list[date]) -> tuple[date, date] | None:
    y, m = entry.year, entry.month - 1
    if m < 1:
        y, m = y - 1, 12
    return month_first_last(y, m, sessions)


def entry_months(study: list[date]) -> list[date]:
    """First NYSE session of each calendar month in study."""
    first: dict[tuple[int, int], date] = {}
    for d in study:
        first.setdefault((d.year, d.month), d)
    return [first[k] for k in sorted(first)]


def _picks(rows: list[dict], slot: str, n: int) -> list[dict]:
    if slot == "max":
        return select_max(rows, n, "ret")
    if slot == "min":
        return select_min(rows, n, "ret")
    return select_max(rows, n, "residual")


def _fmt_book62(sm: dict) -> list[str]:
    lines = _fmt_book48(sm)
    lines[0] = lines[0].replace("n/week=", "n/month=")
    lines[-1] = lines[-1].replace("weeks=", "months=")
    return lines


def _trade(h: dict, side: str, hold: str, tag: str, notional: float):
    ent = h.get("now")
    ex = h.get("em") if hold == "month" else h.get("e10")
    if ent is None or ex is None:
        return None
    if side == "short":
        return _short_n(h, ent, ex, tag, notional)
    return _long_n(h, ent, ex, tag, notional)


def _close_job(args: tuple) -> tuple[str, str, tuple | None]:
    iso, symbol = args
    return iso, symbol, _last_close(date.fromisoformat(iso), symbol)


def _monthly_series(daily: list[float], sessions: list[date]) -> list[float]:
    buckets: dict[tuple[int, int], float] = defaultdict(float)
    for d, v in zip(sessions, daily):
        buckets[(d.year, d.month)] += float(v)
    return [buckets[k] for k in sorted(buckets)]


def confirm_december_rank() -> dict:
    """Step 1. If January cannot rank December, stop."""
    feats = arrow62_feature_sessions()
    stamps = month_first_last(2025, 12, feats)
    if stamps is None:
        raise RuntimeError("January cannot rank December: Dec 2025 not on calendar. Stop.")
    first, last = stamps
    if tape_root(first) != VIRGIN_BARS or tape_root(last) != VIRGIN_BARS:
        raise RuntimeError("January cannot rank December: Dec 2025 is not on virgin. Stop.")
    d1 = tape_root(first) / first.isoformat()
    d2 = tape_root(last) / last.isoformat()
    if not d1.is_dir() or not d2.is_dir():
        raise RuntimeError(f"January cannot rank December: missing {d1} or {d2}. Stop.")
    iwm = load_combined_iwm()
    if _iwm_last_close(iwm, first) is None or _iwm_last_close(iwm, last) is None:
        raise RuntimeError("January cannot rank December: IWM last-RTH missing on Dec first/last. Stop.")
    fixture = None
    for cand in ("A", "AA", "AAL", "F", "INTC", "BAC", "PFE"):
        if (d1 / f"{cand}.parquet").exists() and (d2 / f"{cand}.parquet").exists():
            if _last_close(first, cand) is not None and _last_close(last, cand) is not None:
                fixture = cand
                break
    if fixture is None:
        names1 = {p.stem for p in d1.glob("*.parquet")}
        names2 = {p.stem for p in d2.glob("*.parquet")}
        for cand in sorted(names1 & names2):
            if _last_close(first, cand) is not None and _last_close(last, cand) is not None:
                fixture = cand
                break
    if fixture is None:
        raise RuntimeError("January cannot rank December: no fixture name with both Dec closes. Stop.")
    jan = month_first_last(2026, 1, feats)
    if jan is None or prior_month_stamps(jan[0], feats) != stamps:
        raise RuntimeError("January cannot rank December: Jan 2026 entry does not map to Dec stamps. Stop.")
    return {"first": first, "last": last, "fixture": fixture, "entry": jan[0]}


def run_arrow62(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 62 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = arrow62_feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow62 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "last-month MAX, first night. Long and short are separate engines. "
        "Did not retune leftover pair, same-slot, volume-pace, day-two, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 63.",
        flush=True,
    )
    conf = confirm_december_rank()
    print(
        f"December rank works fixture={conf['fixture']} "
        f"first={conf['first']} last={conf['last']} tape={tape_root(conf['first'])} "
        f"jan_entry={conf['entry']}",
        flush=True,
    )

    elig = _elig_frame()
    by_sess = _by_sess(elig)
    months = entry_months(study)
    specs = []
    for entry in months:
        prior = prior_month_stamps(entry, feats)
        mx = hold_month_exit(entry, feats)
        h10 = hold_n(entry, 10, feats)
        if prior is None or mx is None:
            print(f"skip month entry={entry} missing prior or month-exit", flush=True)
            continue
        names = list(by_sess.get(entry.isoformat()) or [])
        specs.append(
            {
                "entry": entry,
                "prior_first": prior[0],
                "prior_last": prior[1],
                "month_exit": mx,
                "h10": h10,
                "names": names,
            }
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"entry months={len(specs)} (4 IS + 4 OOS expected)  n<=8 unless n15  "
        f"${NOTIONAL:.0f}/name (id5 ${NOTIONAL_4K:.0f})  long and short separate",
        flush=True,
    )

    need: set[tuple[str, str]] = set()
    for spec in specs:
        dates = [spec["prior_first"], spec["prior_last"], spec["entry"], spec["month_exit"]]
        if spec["h10"] is not None:
            dates.append(spec["h10"])
        for h in spec["names"]:
            sym = h["symbol"]
            for d in dates:
                need.add((d.isoformat(), sym))
    jobs = sorted(need)
    prog = Progress(len(jobs), "arrow62")
    prog.start_heartbeat()
    cache: dict[tuple[str, str], tuple | None] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_close_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            iso, symbol, val = fut.result()
            cache[(iso, symbol)] = val
            prog.mark(str(i), rows=1)
            if i % 32 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    iwm = load_combined_iwm()
    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in study
    }
    usable: dict[str, list[date]] = {k: [] for k in IDS}
    max_rets: list[float] = []
    min_rets: list[float] = []
    overlap_n: list[int] = []
    booked_months: list[date] = []
    skipped_thin = 0

    def _px(d: date | None, symbol: str):
        if d is None:
            return None
        return cache.get((d.isoformat(), symbol))

    for spec in specs:
        entry = spec["entry"]
        pf, pl, mx, h10 = spec["prior_first"], spec["prior_last"], spec["month_exit"], spec["h10"]
        iwm_a = _iwm_last_close(iwm, pf)
        iwm_b = _iwm_last_close(iwm, pl)
        iwm_ret = (
            prior_month_return(iwm_a[1], iwm_b[1]) if iwm_a is not None and iwm_b is not None else None
        )
        rows = []
        for h in spec["names"]:
            sym = h["symbol"]
            a = _px(pf, sym)
            b = _px(pl, sym)
            if a is None or b is None:
                continue
            ret = prior_month_return(a[1], b[1])
            if ret is None:
                continue
            now = _px(entry, sym)
            em = _px(mx, sym)
            e10 = _px(h10, sym) if h10 is not None else None
            nxt = name_return(now[1], em[1]) if now is not None and em is not None else None
            res = (ret - iwm_ret) if iwm_ret is not None else None
            rows.append(
                {
                    **h,
                    "ret": ret,
                    "residual": res,
                    "now": now,
                    "em": em,
                    "e10": e10,
                    "next_ret": nxt,
                }
            )
        n_res = len(rows)
        eiso = entry.isoformat()
        chunks.setdefault(eiso, {"trades": {k: [] for k in IDS}, "n_res": 0})
        chunks[eiso]["n_res"] = n_res
        if n_res < MIN_NAMES:
            skipped_thin += 1
            continue
        booked_months.append(entry)
        max8 = select_max(rows, N_SLOT, "ret")
        min8 = select_min(rows, N_SLOT, "ret")
        iwm8 = select_max(rows, N_SLOT, "residual")
        if is_is_session(entry):
            for h in max8:
                if h.get("next_ret") is not None:
                    max_rets.append(float(h["next_ret"]))
            for h in min8:
                if h.get("next_ret") is not None:
                    min_rets.append(float(h["next_ret"]))
        sa = {h["symbol"] for h in max8}
        sb = {h["symbol"] for h in iwm8}
        if sa and sb:
            overlap_n.append(len(sa & sb))
        for name, side, slot, n_take, hold, notional in EXPERIMENTS:
            picks = _picks(rows, slot, n_take)
            if not picks:
                continue
            trs = []
            for h in picks:
                tr = _trade(h, side, hold, name, notional)
                if tr:
                    trs.append(tr)
            if not trs:
                continue
            slot_tr = chunks[eiso]["trades"]
            slot_tr[name] = list(slot_tr.get(name) or []) + trs
            usable[name].append(entry)

    if overlap_n:
        mean_ov = sum(overlap_n) / len(overlap_n)
        ov_line = (
            f"MAX vs IWM-MAX overlap mean {mean_ov:.2f}/8 (n_months={len(overlap_n)})."
        )
    else:
        mean_ov = 0.0
        ov_line = "MAX vs IWM-MAX overlap n=0."
    char_lines = [
        "IS character: next-month raw return of the MAX eight and of the MIN eight. "
        "Description. Does not pick an id.",
        f"  MAX eight {_char_stats(max_rets)}",
        f"  MIN eight {_char_stats(min_rets)}",
    ]

    results = []
    day0_is = day0_oos = day1_is = day1_oos = None
    for name, side, slot, n_take, hold, notional in EXPERIMENTS:
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
        theoretical = float(n_take) * float(notional)
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
                "n_take": n_take,
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
    m_is = _pearson(_monthly_series(day0_is or [], is_sess), _monthly_series(day1_is or [], is_sess))
    m_oos = _pearson(_monthly_series(day0_oos or [], oos_sess), _monthly_series(day1_oos or [], oos_sess))
    corr_line = (
        f"Pearson daily PnL {CONTROL_ID} vs {LONG_H1} IS={corr_is:.3f} OOS={corr_oos:.3f} "
        f"(entry-session series). Pearson monthly IS={m_is:.3f} OOS={m_oos:.3f} "
        "(4 IS months, 4 OOS months)."
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
            f"VERDICT: FAIL — no Arrow 62 engine has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    seat_s = ", ".join(seats) if seats else "none"
    short_s = ", ".join(short_seats) if short_seats else "none"
    long_s = ", ".join(long_seats) if long_seats else "none"
    n_is_m = sum(1 for d in booked_months if is_is_session(d))
    n_oos_m = sum(1 for d in booked_months if not is_is_session(d))
    sample_line = (
        f"Booked months={len(booked_months)} (IS {n_is_m}, OOS {n_oos_m}); skipped_thin={skipped_thin}. "
        "There are only 4 IS months and 4 OOS months of entries. "
        "Do not dress a 4-point t-stat as a large sample."
    )
    lead = (
        f"December rank works (fixture={conf['fixture']} first={conf['first']} last={conf['last']} "
        f"on virgin; IWM both stamps). {char_lines[1].strip()}; {char_lines[2].strip()}. "
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}. "
        f"{ov_line} Short seats: {short_s}. Long seats: {long_s}. "
        "A long id is not judged as a failed short. "
        "4 IS months and 4 OOS months of entries; do not dress a 4-point t-stat as a large sample."
    )
    honesty = (
        "Last-month MAX, first night. Hotel 7 of 7. "
        "Long and short are separate engines. Did not build them as a sign flip of one door. "
        "Did not retune the Wednesday leftover paper book, the Friday+Wednesday pair, "
        "same-slot ids, volume-pace ids, day-two ids, Arrow 43 clocks, or frozen B|conj|atr1559|lock / "
        "flush|max6|repaired. Rings locked from IS; OOS is one look for the family. "
        "Did not drop an id after seeing OOS. Did not use an OOS month to pick a threshold. "
        "Split on the entry session (first NYSE of month M). "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS. "
        "Combined dollars are not EV. Id 5 is the paper ticket size, diagnostic. No Arrow 63."
    )
    lines = [
        "Arrow 62 — last-month MAX, first night (IS / OOS)",
        verdict,
        lead,
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Short seats: {short_s}. Long seats: {long_s}. A long id is not judged as a failed short.",
        ov_line,
        corr_line,
        sample_line,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"entry_months={len(specs)}  booked={len(booked_months)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}  dec_tape={tape_root(date(2025, 12, 1))}",
        f"eligibility on entry: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"prior-month return = last RTH last-of-M-1 / last RTH first-of-M-1 − 1  "
        f"skip month if < {MIN_NAMES} names  n<=8 (id4 n=15)  ${NOTIONAL:.0f}/name "
        f"(id5 ${NOTIONAL_4K:.0f})  enter first NYSE of M last RTH",
        "MAX = 8 largest prior-month returns. MIN = 8 smallest. "
        "IWM-MAX = 8 largest (name month return − IWM month return). "
        "Hold month = last RTH of last session in M. Hold 10 = 10 sessions later.",
        "",
        *char_lines,
        "",
        f"{'id':<20} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'side':>6} {'seat':>5}",
    ]
    for r in results:
        for split, sm, a, skip, n_a, months_s, peak_s in (
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
            lines.extend(_fmt_book62(sm))
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_slot<={r['n_take']} notional=${r['notional']:.0f}  {r['side']}  "
                f"slot={r['slot']}  hold={r['hold']}{_ci_note(sm)}"
            )
            lines.append(
                f"    peak live notional ${peak_s:.0f}  one-cohort ${r['theoretical']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  months={r['n_reb']}"
            )
            lines.append(f"    months: {months_s}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow62_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow62_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 62",
        "",
        verdict,
        "",
        lead,
        char_lines[1],
        char_lines[2],
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}. Short: {short_s}. Long: {long_s}.",
        ov_line,
        corr_line,
        sample_line,
        "Last-month MAX, first night. Long and short are separate engines. "
        "Did not retune leftover pair, same-slot, volume-pace, day-two, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 63.",
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
