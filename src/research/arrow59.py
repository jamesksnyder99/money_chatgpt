"""Arrow 59 — volume-pace hotel, first night. Long and short are separate engines."""

from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _elig_frame, last_rth, load_combined_iwm
from research.arrow44 import MIN_PDV, MIN_PX, MAX_PX, _alpha, _month_lines
from research.arrow45 import _daily_and_trades
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow54 import take_passing
from research.arrow55 import ticket_live
from research.arrow57 import _char_stats, _long_n, name_return
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_bar_path,
    split_is_oos,
    tape_root,
)
from research.combine import _pearson
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO
from research.fills import is_tradeable
from research.signals import MINUTE_1000, MINUTE_1559, RTH_OPEN, bar_time

ET = ZoneInfo("America/New_York")
CONTROL_ID = "short_hot_1159"
LONG_H1 = "long_quiet_1159"
N_SLOT = 8
MIN_PACE = 16
MIN_PASS = 5
LOOKBACK = 20
MIN_BASE = 10
NOTIONAL = 3000.0
PACE_OPEN = RTH_OPEN
WINDOW_END = MINUTE_1000
FILL_CLOCK = MINUTE_1000
# name, side, slot (hot/quiet), exit (1159/next), confirm (up/dn/None)
EXPERIMENTS = (
    ("short_hot_1159", "short", "hot", "1159", None),
    ("long_quiet_1159", "long", "quiet", "1159", None),
    ("short_hot_next", "short", "hot", "next", None),
    ("long_quiet_next", "long", "quiet", "next", None),
    ("short_hot_up_1159", "short", "hot", "1159", "up"),
    ("long_quiet_dn_1159", "long", "quiet", "1159", "dn"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def _as_date(x) -> date:
    if isinstance(x, datetime):
        return x.date()
    return x


def _clock(ts: datetime) -> time:
    return bar_time(ts)


def bar_dollar_volume(close: float | None, volume: float | None) -> float:
    """One-minute dollar volume. Not a 15-session leftover."""
    if close is None or volume is None or close <= 0 or volume <= 0:
        return 0.0
    return float(close) * float(volume)


def pace(today_window: float | None, baseline: float | None) -> float | None:
    if today_window is None or baseline is None or baseline <= 0:
        return None
    return float(today_window) / float(baseline)


def hot_up_pass(fill_last: float | None, prior_last: float | None) -> bool:
    """True iff 10:00 last ≥ prior last-RTH close."""
    if fill_last is None or prior_last is None:
        return False
    return float(fill_last) >= float(prior_last)


def quiet_dn_pass(fill_last: float | None, prior_last: float | None) -> bool:
    """True iff 10:00 last ≤ prior last-RTH close."""
    if fill_last is None or prior_last is None:
        return False
    return float(fill_last) <= float(prior_last)


def select_hot(rows: list[dict], n: int = N_SLOT) -> list[dict]:
    ranked = sorted(
        (r for r in rows if r.get("pace") is not None),
        key=lambda r: (-float(r["pace"]), r["symbol"]),
    )
    return ranked[: max(0, int(n))]


def select_quiet(rows: list[dict], n: int = N_SLOT) -> list[dict]:
    ranked = sorted(
        (r for r in rows if r.get("pace") is not None),
        key=lambda r: (float(r["pace"]), r["symbol"]),
    )
    return ranked[: max(0, int(n))]


def _fmt_book59(sm: dict) -> list[str]:
    lines = _fmt_book48(sm)
    lines[0] = lines[0].replace("n/week=", "n/sess=")
    return lines


def peak_live_notional(trades: list[dict], sessions: list[date]) -> float:
    """Same-session 10:00–15:59 is live on the entry date. Multi-session uses [entry, exit)."""
    peak = 0.0
    for d in sessions:
        live = 0.0
        for t in trades:
            e = _as_date(t["entry_ts"])
            x = _as_date(t["exit_ts"])
            on = (e == x and d == e) or (e != x and ticket_live(e, x, d))
            if on:
                live += float(t["shares"]) * float(t["entry_px"])
        if live > peak:
            peak = live
    return peak


def _read_bars(session: date, symbol: str) -> pl.DataFrame | None:
    p = session_bar_path(session, symbol)
    if not p.exists():
        return None
    try:
        df = pl.read_parquet(p, columns=["bar_start", "open", "high", "low", "close", "volume"])
    except Exception:  # noqa: BLE001
        return None
    if df.height == 0:
        return None
    return df


def extract_session(session: date, symbol: str) -> dict | None:
    """Window DV, 10:00 fill, 15:59/last RTH from one parquet."""
    df = _read_bars(session, symbol)
    if df is None:
        return None
    has_0930 = False
    win = 0.0
    fill = None
    px1559 = None
    for rec in df.sort("bar_start").iter_rows(named=True):
        ts = rec["bar_start"]
        t = _clock(ts)
        op, cl, vol = rec["open"], rec["close"], rec["volume"]
        if t == RTH_OPEN and op is not None and float(op) > 0:
            has_0930 = True
        if RTH_OPEN <= t < WINDOW_END:
            win += bar_dollar_volume(cl, vol)
        if fill is None and t >= FILL_CLOCK and is_tradeable(op, cl, vol):
            fill = (ts, float(cl))
        if t == MINUTE_1559 and cl is not None and float(cl) > 0:
            px1559 = (ts, float(cl))
    if not has_0930:
        return None
    last = last_rth(df, session)
    last_px = (last["bar_start"], float(last["close"])) if last is not None else px1559
    return {
        "window": win,
        "fill": fill,
        "px1559": px1559 if px1559 is not None else last_px,
        "last_rth": last_px,
    }


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
        for j in range(max(0, i - LOOKBACK), min(len(feats), i + 2)):
            need.add(feats[j])
        if i > 0:
            need.add(feats[i - 1])
    extracted: dict[date, dict | None] = {}
    for d in need:
        extracted[d] = extract_session(d, symbol)
    out = []
    for d in elig_dates:
        i = idx.get(d)
        if i is None:
            continue
        today = extracted.get(d)
        if today is None or today.get("fill") is None:
            continue
        prior_dates = feats[max(0, i - LOOKBACK) : i]
        wins = []
        for pd in prior_dates:
            rec = extracted.get(pd)
            if rec is None:
                continue
            w = rec.get("window")
            if w is None:
                continue
            wins.append(float(w))
        if len(wins) < MIN_BASE:
            continue
        p = pace(today["window"], statistics.median(wins))
        if p is None:
            continue
        nxt = extracted.get(feats[i + 1]) if i + 1 < len(feats) else None
        prev = extracted.get(feats[i - 1]) if i > 0 else None
        fill = today["fill"]
        px1559 = today.get("px1559")
        h = meta[d]
        nxt_ret = name_return(fill[1], px1559[1]) if px1559 is not None else None
        prior_last = prev["last_rth"][1] if prev and prev.get("last_rth") else None
        out.append(
            {
                "session": d.isoformat(),
                "symbol": symbol,
                "prior_close": h["prior_close"],
                "prior_dv": h["prior_dv"],
                "pace": p,
                "now": fill,
                "ex1159": px1559,
                "ex_next": nxt["last_rth"] if nxt and nxt.get("last_rth") else None,
                "prior_last": prior_last,
                "next_ret": nxt_ret,
                "up_ok": hot_up_pass(fill[1], prior_last),
                "dn_ok": quiet_dn_pass(fill[1], prior_last),
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


def run_arrow59(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 59 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    feat_iso = [d.isoformat() for d in feats]
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow59 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "volume-pace hotel, first night. Long and short are separate engines. "
        "Pace = 09:30-09:59 dollar volume vs prior-20 median. Fill 10:00. "
        "Did not retune leftover pair, same-slot ids, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 60.",
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
        f"name-days={elig.height} symbols={len(jobs)} pace clock=10:00  "
        f"window=09:30-09:59  n=8  ${NOTIONAL:.0f}  long and short separate",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow59")
    prog.start_heartbeat()
    by_iso: dict[str, list[dict]] = {d.isoformat(): [] for d in study}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_symbol_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rows = fut.result()
            for r in rows:
                iso = r["session"]
                if iso in by_iso:
                    by_iso[iso].append(r)
            prog.mark(str(i), rows=1)
            if i % 32 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in study
    }
    char_hot: list[float] = []
    char_quiet: list[float] = []
    overlap_up: list[int] = []
    overlap_dn: list[int] = []
    usable: dict[str, list[date]] = {k: [] for k in IDS}

    for d in study:
        iso = d.isoformat()
        rows = by_iso.get(iso) or []
        n_res = len(rows)
        chunks[iso]["n_res"] = n_res
        if n_res < MIN_PACE:
            continue
        hot = select_hot(rows, N_SLOT)
        quiet = select_quiet(rows, N_SLOT)
        if is_is_session(d):
            for h in hot:
                if h.get("next_ret") is not None:
                    char_hot.append(float(h["next_ret"]))
            for h in quiet:
                if h.get("next_ret") is not None:
                    char_quiet.append(float(h["next_ret"]))
            overlap_up.append(sum(1 for h in hot if h.get("up_ok")))
            overlap_dn.append(sum(1 for h in quiet if h.get("dn_ok")))
        for name, side, slot, ex_kind, confirm in EXPERIMENTS:
            ranked = hot if slot == "hot" else quiet
            if confirm == "up":
                picks = take_passing(ranked, lambda r: r.get("up_ok"), n=N_SLOT, min_pass=MIN_PASS)
            elif confirm == "dn":
                picks = take_passing(ranked, lambda r: r.get("dn_ok"), n=N_SLOT, min_pass=MIN_PASS)
            else:
                picks = ranked
            if not picks:
                continue
            trs = []
            for h in picks:
                tr = _trade(h, side, ex_kind, name)
                if tr:
                    trs.append(tr)
            if not trs:
                continue
            chunks[iso]["trades"][name] = trs
            usable[name].append(d)

    def _frac(xs: list[int]) -> str:
        if not xs:
            return "n_sess=0"
        tot = sum(xs)
        n8 = len(xs) * N_SLOT
        return f"pass {tot}/{n8} frac={tot / n8:.3f} mean_per_sess={tot / len(xs):.2f} n_sess={len(xs)}"

    char_lines = [
        "IS character: 10:00 to 15:59 raw return of the slot eights. Description. Does not pick an id.",
        f"  hot eight {_char_stats(char_hot)}",
        f"  quiet eight {_char_stats(char_quiet)}",
        f"  hot-and-up among unfiltered hot 8 {_frac(overlap_up)}",
        f"  quiet-and-down among unfiltered quiet 8 {_frac(overlap_dn)}",
    ]
    if overlap_up:
        mean_up = sum(overlap_up) / len(overlap_up)
        changed_up = mean_up < 7.5
    else:
        mean_up = 0.0
        changed_up = False
    if overlap_dn:
        mean_dn = sum(overlap_dn) / len(overlap_dn)
        changed_dn = mean_dn < 7.5
    else:
        mean_dn = 0.0
        changed_dn = False
    confirm_line = (
        f"Hot-and-up {'changed' if changed_up else 'did not change'} the hot eight "
        f"(mean {mean_up:.2f}/8 pass). Quiet-and-down "
        f"{'changed' if changed_dn else 'did not change'} the quiet eight "
        f"(mean {mean_dn:.2f}/8 pass)."
    )

    results = []
    day0_is = day0_oos = day1_is = day1_oos = None
    iwm = load_combined_iwm()
    for name, side, slot, ex_kind, confirm in EXPERIMENTS:
        weeks = usable[name]
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
                "slot": slot,
                "ex": ex_kind,
                "confirm": confirm,
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
            f"VERDICT: FAIL — no Arrow 59 engine has OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS."
        )
    seat_s = ", ".join(seats) if seats else "none"
    short_s = ", ".join(short_seats) if short_seats else "none"
    long_s = ", ".join(long_seats) if long_seats else "none"
    honesty = (
        "Volume-pace hotel, first night. Long and short are separate engines. "
        "Did not build them as a sign flip. "
        "Did not retune the Friday+Wednesday leftover pair, Arrow 43 clocks, "
        "same-slot ids, or frozen B|conj|atr1559|lock / flush|max6|repaired. "
        "Rings locked from IS; OOS is one look for the family. Did not drop an id after seeing OOS. "
        "Did not use an OOS month to pick a threshold. "
        "Slate is $200/day for the shop, not this first night's job. "
        "Do not call a CI that includes 0 EV. Odd months IS, even months OOS, split on entry session. "
        "Combined dollars are not EV. No Arrow 60."
    )
    lines = [
        "Arrow 59 — volume-pace hotel, first night (IS / OOS)",
        verdict,
        char_lines[0],
        char_lines[1],
        char_lines[2],
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day on OOS with IS not red: {seat_s}.",
        f"Short seats: {short_s}. Long seats: {long_s}. A long id is not judged as a failed short.",
        confirm_line,
        corr_line,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day (shop, not this night)  "
        f"seat_floor={SEAT_FLOOR:.0f}/day  target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)}  OOS n={len(oos_sess)}  "
        f"symbols={len(jobs)}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as leftover pair, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  pace n=8  ${NOTIONAL:.0f}/name  fill 10:00  "
        f"window 09:30-09:59 vs prior-{LOOKBACK} median (need {MIN_BASE})",
        "Skip a session if fewer than 16 names have a pace. "
        "Skip a name if 09:30 open, 10:00 fill, or required exit is missing. "
        "Ids 4–5: skip the day if fewer than 5 pass the extra filter; if 5–7 take them all.",
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
            lines.extend(_fmt_book59(sm))
            conf = f"  confirm={r['confirm']}" if r["confirm"] else ""
            lines.append(
                f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})  "
                f"n_slot={N_SLOT} notional=${NOTIONAL:.0f}  {r['side']} {r['slot']}  "
                f"exit={r['ex']}{conf}{_ci_note(sm)}"
            )
            lines.append(
                f"    peak live notional ${peak_s:.0f}  hold-cohorts ${r['theoretical']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  sessions={r['n_reb']}"
            )
            lines.append(f"    months: {months}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow59_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow59_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 59",
        "",
        verdict,
        "",
        char_lines[1],
        char_lines[2],
        f"Seat ${SEAT_FLOOR:.0f}: {seat_s}. Short: {short_s}. Long: {long_s}.",
        confirm_line,
        corr_line,
        "Volume-pace hotel. Long and short are separate engines. "
        "Did not retune leftover pair, same-slot ids, or frozen B/flush. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 60.",
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
