"""Arrow 76 — open leftover short, first hallway (IS / OOS). Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from ingest.calendar import NYSE_EARLY_CLOSE
from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow43 import SEAT_FLOOR, _clock, _read_bars
from research.arrow44 import MIN_PDV, MIN_PX, MAX_PX, _by_sess, _month_lines
from research.arrow45 import _daily_and_trades, _within
from research.arrow47 import _short_n
from research.arrow48 import _wins_losses
from research.arrow51 import _ci_note
from research.arrow57 import _fmt_book57, select_winners
from research.arrow74 import NOTIONAL, _elig_janfeb, peak_live_intraday
from research.book import daily_close_drawdown
from research.clock import (
    arrow76_feature_sessions,
    arrow76_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO, signed_pnl
from research.fills import is_tradeable
from research.signals import MINUTE_1559, RTH_OPEN

ET = ZoneInfo("America/New_York")
RTH_END = time(16, 0)
LEFT_LB = 15
N8 = 8
N15 = 15
NOTIONAL_4K = 4000.0
CONTROL_ID = "h1029_n8"
A75_JAN_OPEN = 334.93
REPRINT_TOL = 0.20
EXIT_1029 = time(10, 29)
EXIT_1129 = time(11, 29)
FILL_0931 = time(9, 31)
# name, n, exit_kind, notional, days
EXPERIMENTS = (
    ("h1029_n8", N8, "1029", NOTIONAL, "all"),
    ("h1129_n8", N8, "1129", NOTIONAL, "all"),
    ("h1559_n8", N8, "1559", NOTIONAL, "all"),
    ("h1029_n15", N15, "1029", NOTIONAL, "all"),
    ("h1029_n8_4k", N8, "1029", NOTIONAL_4K, "all"),
    ("h1029_n8_wed", N8, "1029", NOTIONAL, "wed"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
HOLD_IDS = ("h1129_n8", "h1559_n8")


def exit_stamp(kind: str) -> time:
    """Id 0 exits 10:29, not 15:59. Id 2 exits 15:59."""
    if kind == "1129":
        return EXIT_1129
    if kind == "1559":
        return MINUTE_1559
    return EXIT_1029


def last_at_or_before(prints: list[tuple[datetime, float]], stamp: time) -> tuple[datetime, float] | None:
    last = None
    for ts, px in prints:
        if _clock(ts) <= stamp:
            last = (ts, px)
    return last


def pick_exit(got: dict, kind: str) -> tuple[datetime, float] | None:
    if kind == "1129":
        return got.get("ex1129")
    if kind == "1559":
        return got.get("ex1559")
    return got.get("ex1029")


def extract_open(session: date, symbol: str) -> dict | None:
    """First RTH fill, last print at/before 10:29 / 11:29 / 15:59, last RTH."""
    df = _read_bars(session, symbol)
    if df is None:
        return None
    early = NYSE_EARLY_CLOSE.get(session)
    fill = None
    fill0931 = None
    last_1029 = None
    last_1129 = None
    last_rth = None
    px1559 = None
    for rec in df.sort("bar_start").iter_rows(named=True):
        ts = rec["bar_start"]
        t = _clock(ts)
        if t < RTH_OPEN or t >= RTH_END:
            continue
        if early is not None and t >= early:
            continue
        op, cl, vol = rec["open"], rec["close"], rec["volume"]
        if not is_tradeable(op, cl, vol):
            continue
        px = float(cl)
        if px <= 0:
            continue
        if fill is None:
            fill = (ts, px)
        if fill0931 is None and t >= FILL_0931:
            fill0931 = (ts, px)
        if t <= EXIT_1029:
            last_1029 = (ts, px)
        if t <= EXIT_1129:
            last_1129 = (ts, px)
        last_rth = (ts, px)
        if t == MINUTE_1559:
            px1559 = (ts, px)
    if last_rth is None:
        return None
    return {
        "fill": fill,
        "fill0931": fill0931,
        "ex1029": last_1029,
        "ex1129": last_1129,
        "ex1559": px1559 if px1559 is not None else last_rth,
        "partial1559": px1559 is None,
        "last_rth": last_rth,
    }


def _extract_job(args: tuple) -> tuple[str, str, dict | None]:
    iso, symbol = args
    return iso, symbol, extract_open(date.fromisoformat(iso), symbol)


def run_arrow76(*, workers: int | None = None) -> int:
    sess = arrow76_sessions()
    feats = arrow76_feature_sessions()
    if any(d.month >= 5 for d in sess):
        raise RuntimeError("Arrow 76 must not score May–August")
    if any(tape_root(d) == BARS_DIR for d in (date(2026, 1, 2), date(2026, 4, 30))):
        raise RuntimeError("Arrow 76 must not read Lab A data/bars/")
    leftover = feature_sessions()
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    odd = [d for d in sess if is_is_session(d)]
    even = [d for d in sess if not is_is_session(d)]
    by_month: dict[str, list[date]] = {}
    for d in sess:
        by_month.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(d)
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    print(
        f"research start mode=arrow76 workers={workers} cpu={cpu} "
        f"window={sess[0]}..{sess[-1]} n={len(sess)} odd n={len(odd)} even n={len(even)} "
        f"feats={feats[0]}..{feats[-1]} "
        f"jan_tape={tape_root(date(2026, 1, 2))} apr_tape={tape_root(date(2026, 4, 30))}",
        flush=True,
    )
    print(
        "Open leftover short at 09:30. Short only. Did not retune Wednesday H10. "
        "Did not use April to pick a hold. Rank uses prior close only (15-session). "
        "Fill first print at or after 09:30. Exit last print of the stamp. "
        "Home-hour estimate is not required. No new ingest. No Arrow 77.",
        flush=True,
    )
    elig = _elig_janfeb(sess)
    by = _by_sess(elig)
    need: set[tuple[str, str]] = set()
    for d in sess:
        for h in by.get(d.isoformat(), []):
            sym = h["symbol"]
            need.add((d.isoformat(), sym))
            t1 = session_shift(d, -1, feats)
            t16 = session_shift(d, -LEFT_LB - 1, feats)
            if t1 is not None:
                need.add((t1.isoformat(), sym))
            if t16 is not None:
                need.add((t16.isoformat(), sym))
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"left={LEFT_LB} parent n={N8} ${NOTIONAL:.0f} extract_jobs={len(need)}",
        flush=True,
    )
    cache: dict[tuple[str, str], dict] = {}
    prog = Progress(len(need), "arrow76")
    prog.start_heartbeat()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_extract_job, job) for job in sorted(need)]
        for i, fut in enumerate(as_completed(futs), 1):
            iso, symbol, got = fut.result()
            if got is not None:
                cache[(iso, symbol)] = got
            prog.mark(str(i), rows=1)
            if i % 64 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0} for d in sess
    }
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}

    for d in sess:
        names = by.get(d.isoformat(), [])
        keyed = []
        for h in names:
            today = cache.get((d.isoformat(), h["symbol"]))
            if today is None or today.get("fill") is None:
                continue
            t1 = session_shift(d, -1, feats)
            t16 = session_shift(d, -LEFT_LB - 1, feats)
            left = None
            if t1 is not None and t16 is not None:
                a = cache.get((t1.isoformat(), h["symbol"]))
                b = cache.get((t16.isoformat(), h["symbol"]))
                if (
                    a
                    and b
                    and a.get("last_rth")
                    and b.get("last_rth")
                    and b["last_rth"][1] > 0
                ):
                    left = a["last_rth"][1] / b["last_rth"][1] - 1.0
            if left is None:
                continue
            keyed.append({**h, "today": today, "left": left})
        chunks[d.isoformat()]["n_res"] = len(keyed)
        for name, n_slot, kind, notional, days in EXPERIMENTS:
            if days == "wed" and d.weekday() != 2:
                continue
            if len(keyed) < n_slot:
                continue
            picks = select_winners(keyed, n_slot, "left")
            stamp = exit_stamp(kind)
            for row in picks:
                today = row["today"]
                ent = today.get("fill")
                ex = pick_exit(today, kind)
                if ent is None or ex is None:
                    continue
                if ent[0] > ex[0]:
                    continue
                tr = _short_n(row, ent, ex, name, notional)
                if tr is None:
                    continue
                tr["signal"] = d
                tr["fill_date"] = d
                tr["exit_date"] = d
                tr["exit_partial"] = _clock(ex[0]) != stamp
                if signed_pnl(-1, tr["shares"], tr["entry_px"], tr["exit_px"]) < 0 and tr["pnl"] > 0:
                    raise RuntimeError("Arrow 76 id is not short-only")
                if tr["side"] != -1:
                    raise RuntimeError("Arrow 76 must be short-only")
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                trades_all[name].append(tr)

    def _score_slice(name: str, slice_sess: list[date]) -> dict:
        mset = set(slice_sess)
        weeks = sorted({t["signal"] for t in trades_all[name] if t["signal"] in mset})
        sm_ent, daily, tr = _daily_and_trades(chunks, slice_sess, name, weeks)
        sm_ent["n_win"], sm_ent["n_loss"] = _wins_losses(tr)
        sm_ent["daily_close_dd"] = daily_close_drawdown(daily)
        sm_ent["worst_day"] = min(daily) if daily else 0.0
        return {
            "sm": sm_ent,
            "tr": tr,
            "peak": peak_live_intraday(tr),
            "n_sess": len(slice_sess),
            "n_days": len(weeks),
            "months": _month_lines(daily, slice_sess),
        }

    jan = by_month.get("2026-01") or []
    results = []
    for name, n_slot, kind, notional, days in EXPERIMENTS:
        odd_s = _score_slice(name, odd)
        even_s = _score_slice(name, even)
        months = {key: _score_slice(name, days_m) for key, days_m in sorted(by_month.items())}
        results.append(
            {
                "name": name,
                "n": n_slot,
                "exit": kind,
                "notional": notional,
                "days": days,
                "odd": odd_s,
                "even": even_s,
                "months": months,
                "peak_all": peak_live_intraday(trades_all[name]),
                "ci_odd_ex": odd_s["sm"]["ci_lo"] > 0 or odd_s["sm"]["ci_hi"] < 0,
                "ci_even_ex": even_s["sm"]["ci_lo"] > 0 or even_s["sm"]["ci_hi"] < 0,
            }
        )

    parent = next(r for r in results if r["name"] == CONTROL_ID)
    jan_pack = parent["months"]["2026-01"]
    jan_day = jan_pack["sm"]["per_day"]
    reprint_ok = _within(jan_day, A75_JAN_OPEN, REPRINT_TOL)
    reprint_line = (
        f"Id 0 {CONTROL_ID} January $/day={jan_day:.2f} vs Arrow 75 short_left_open "
        f"+{A75_JAN_OPEN:.2f} n={jan_pack['sm']['n_trades']} "
        + (
            "— within ±20%."
            if reprint_ok
            else "— DRIFT beyond ±20%. Stop and fix."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        raise RuntimeError(reprint_line)

    def _lifts_both(r: dict) -> bool:
        return r["odd"]["sm"]["per_day"] > parent["odd"]["sm"]["per_day"] and r["even"]["sm"][
            "per_day"
        ] > parent["even"]["sm"]["per_day"]

    hold_lift = [r["name"] for r in results if r["name"] in HOLD_IDS and _lifts_both(r)]
    n15 = next(r for r in results if r["name"] == "h1029_n15")
    wed = next(r for r in results if r["name"] == "h1029_n8_wed")
    k4 = next(r for r in results if r["name"] == "h1029_n8_4k")
    first_para = (
        f"{reprint_line} Holding past 10:29 lifts both odd and even: "
        f"{', '.join(hold_lift) if hold_lift else 'no'}. "
        f"n=15 lifts both: {'yes' if _lifts_both(n15) else 'no'} "
        f"(odd ${n15['odd']['sm']['per_day']:.2f} even ${n15['even']['sm']['per_day']:.2f} vs "
        f"id0 odd ${parent['odd']['sm']['per_day']:.2f} even ${parent['even']['sm']['per_day']:.2f}). "
        f"Wednesday lifts both: {'yes' if _lifts_both(wed) else 'no'} "
        f"(odd ${wed['odd']['sm']['per_day']:.2f} even ${wed['even']['sm']['per_day']:.2f}). "
        f"$4k lifts both: {'yes' if _lifts_both(k4) else 'no'} "
        f"(odd ${k4['odd']['sm']['per_day']:.2f} even ${k4['even']['sm']['per_day']:.2f})."
    )
    sniff = (
        "VERDICT: SNIFF — two extra months is still a sniff for promotion. "
        "Did not use April to pick a hold. Did not treat this window as a $200 slate pass. "
        "Did not score May–August."
    )
    honesty = (
        "Open leftover short at 09:30. Parent: eight largest 15-session close-to-close returns, "
        "fill first print at or after 09:30, exit last print of the stamp. Rank uses prior close "
        "only, so 09:30 fill is causal. Short only. Longs stay off. Did not retune Wednesday H10. "
        "Did not use April to pick a hold. Home-hour estimate is not required. Field $10–$80 "
        "PDV ≥ $10M ETP denylist. $3,000 parent. A ring beats id 0 only if it lifts $/day on "
        "both the odd pair and the even pair. Do not call a CI that includes 0 EV. "
        "No new ingest. Did not touch Lab A data/bars/. No Arrow 77."
    )
    lines = [
        "Arrow 76 — open leftover short, first hallway (IS / OOS)",
        first_para,
        sniff,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"window n={len(sess)} {sess[0]}..{sess[-1]}  odd n={len(odd)}  even n={len(even)}  "
        f"(May not scored)",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"apr_tape={tape_root(date(2026, 4, 30))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"left={LEFT_LB} parent n={N8} ${NOTIONAL:.0f}",
        "Peak live = |shares × entry| (same-session book). "
        "$/day = total PnL / NYSE sessions in that slice. Odd=Jan+Mar IS. Even=Feb+Apr OOS.",
        "",
        f"{'id':<16} {'slice':<7} {'$/day':>9} {'n':>6} {'hit':>6} {'t':>6}",
    ]

    def _emit(r: dict, label: str, pack: dict, ci_ex: bool | None = None) -> None:
        sm = pack["sm"]
        lines.append(
            f"{r['name']:<16} {label:<7} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
            f"{sm['hit_rate']:6.3f} {sm['t_stat']:6.2f}"
        )
        lines.extend(_fmt_book57(sm))
        note = _ci_note(sm)
        lines.append(
            f"    $/day={sm['per_day']:.2f} (total PnL / n={pack['n_sess']} sessions)  "
            f"n={r['n']} exit={r['exit']} ${r['notional']:.0f} days={r['days']}  "
            f"peak live ${pack['peak']:.0f}  all ${r['peak_all']:.0f}{note}"
        )
        lines.append(f"    months: {pack['months']}")
        if ci_ex is None:
            ci_ex = sm["ci_lo"] > 0 or sm["ci_hi"] < 0
        if ci_ex:
            lines.append(f"    {label} CI excludes 0.")
        else:
            lines.append(f"    {label} CI includes 0 — not EV.")

    for r in results:
        _emit(r, "odd", r["odd"], r["ci_odd_ex"])
        _emit(r, "even", r["even"], r["ci_even_ex"])
        for key, pack in r["months"].items():
            _emit(r, key, pack, None)
    beat = [r["name"] for r in results if r["name"] != CONTROL_ID and _lifts_both(r)]
    lines.append(
        f"    Rings that lift both odd and even vs id 0: {', '.join(beat) if beat else 'none'}. "
        "Did not use April to pick a hold. Two extra months is a sniff, not a seat. No Arrow 77."
    )
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow76_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow76_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 76",
        "",
        first_para,
        "",
        sniff,
        f"h1029_n8 odd ${parent['odd']['sm']['per_day']:.2f} n={parent['odd']['sm']['n_trades']}  "
        f"even ${parent['even']['sm']['per_day']:.2f} n={parent['even']['sm']['n_trades']}. "
        f"h1129_n8 odd ${next(r for r in results if r['name']=='h1129_n8')['odd']['sm']['per_day']:.2f} "
        f"even ${next(r for r in results if r['name']=='h1129_n8')['even']['sm']['per_day']:.2f}. "
        f"h1559_n8 odd ${next(r for r in results if r['name']=='h1559_n8')['odd']['sm']['per_day']:.2f} "
        f"even ${next(r for r in results if r['name']=='h1559_n8')['even']['sm']['per_day']:.2f}. "
        "Did not use April to pick a hold. No Arrow 77.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 76"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
