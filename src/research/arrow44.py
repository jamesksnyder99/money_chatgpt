"""Arrow 44 — weekly residual vs IWM. One book, two legs. No door search."""

from __future__ import annotations

import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow20 import _iso
from research.arrow23 import _summarize_adv
from research.arrow43 import (
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    NOTIONAL,
    SEAT_FLOOR,
    _elig_frame,
    _iwm_px,
    _pack,
    last_rth,
    load_combined_iwm,
    notional_shares,
)
from research.book import borrow_blocks_short, daily_close_drawdown
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    rebalance_sessions,
    session_bar_path,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.combine import combine_books
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO, signed_pnl

ET = ZoneInfo("America/New_York")
LOOKBACK = 5
HOLD = 5
N_LONG = 15
N_SHORT = 15
MIN_RESIDUAL_NAMES = 40
IDS = ("res_long", "res_short", "res_ls")


def residual(name_px0: float, name_px1: float, iwm_px0: float, iwm_px1: float) -> float | None:
    """Name return minus IWM return. Not a regression."""
    if min(name_px0, name_px1, iwm_px0, iwm_px1) <= 0:
        return None
    return (name_px1 / name_px0 - 1.0) - (iwm_px1 / iwm_px0 - 1.0)


def _last_close(session: date, symbol: str) -> tuple[datetime, float] | None:
    p = session_bar_path(session, symbol)
    if not p.exists():
        return None
    try:
        df = pl.read_parquet(p, columns=["bar_start", "open", "high", "low", "close", "volume"])
    except Exception:  # noqa: BLE001
        return None
    if df.height == 0:
        return None
    rec = last_rth(df, session)
    if rec is None:
        return None
    return rec["bar_start"], float(rec["close"])


def _iwm_last_close(iwm: dict[str, pl.DataFrame], session: date) -> tuple[datetime, float] | None:
    df = iwm.get(session.isoformat())
    if df is None or df.height == 0:
        return None
    rec = last_rth(df, session)
    if rec is None:
        return None
    return rec["bar_start"], float(rec["close"])


def _by_sess(elig: pl.DataFrame) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for rec in elig.select("session_date", "symbol", "prior_close", "prior_dollar_volume").iter_rows(
        named=True
    ):
        iso = _iso(rec["session_date"])
        out.setdefault(iso, []).append(
            {
                "symbol": str(rec["symbol"]),
                "prior_close": float(rec["prior_close"]),
                "prior_dv": float(rec["prior_dollar_volume"] or 0.0),
            }
        )
    return out


def _week_job(args: tuple) -> dict:
    (
        iso,
        look_iso,
        exit_iso,
        names,
        iwm_px0,
        iwm_px1,
        iwm_px_exit,
        do_char,
    ) = args
    session = date.fromisoformat(iso)
    look = date.fromisoformat(look_iso)
    exd = date.fromisoformat(exit_iso)
    empty = {
        "session": iso,
        "trades": {k: [] for k in IDS},
        "n_res": 0,
        "char_bottom": [],
        "char_top": [],
        "skipped": "no_names",
    }
    if not names or iwm_px0 is None or iwm_px1 is None or iwm_px0 <= 0 or iwm_px1 <= 0:
        empty["skipped"] = "iwm"
        return empty
    rows = []
    closes_r: dict[str, tuple[datetime, float]] = {}
    closes_e: dict[str, tuple[datetime, float]] = {}
    for h in names:
        sym = h["symbol"]
        a = _last_close(look, sym)
        b = _last_close(session, sym)
        if a is None or b is None:
            continue
        res = residual(a[1], b[1], iwm_px0, iwm_px1)
        if res is None:
            continue
        closes_r[sym] = b
        c = _last_close(exd, sym)
        if c is not None:
            closes_e[sym] = c
        nxt = None
        if iwm_px_exit is not None and iwm_px_exit > 0 and c is not None:
            nxt = residual(b[1], c[1], iwm_px1, iwm_px_exit)
        rows.append({**h, "residual": res, "next_res": nxt})
    if len(rows) < MIN_RESIDUAL_NAMES:
        empty["n_res"] = len(rows)
        empty["skipped"] = "thin"
        return empty
    ranked = sorted(rows, key=lambda r: r["residual"])
    bottom = ranked[:N_LONG]
    top = ranked[-N_SHORT:]
    char_b = []
    char_t = []
    if do_char:
        mid = len(ranked) // 2
        for r in ranked[:mid]:
            if r["next_res"] is not None:
                char_b.append(float(r["next_res"]))
        for r in ranked[mid:]:
            if r["next_res"] is not None:
                char_t.append(float(r["next_res"]))
    trades_l = []
    trades_s = []
    for h in bottom:
        sym = h["symbol"]
        ent = closes_r.get(sym)
        ex = closes_e.get(sym)
        if ent is None or ex is None:
            continue
        shares = notional_shares(ent[1])
        if shares < 1:
            continue
        pnl = signed_pnl(1, shares, ent[1], ex[1])
        trades_l.append(_pack(pnl, 1, shares, ent[1], ex[1], ent[0], ex[0], "res_long", sym))
    for h in top:
        sym = h["symbol"]
        ent = closes_r.get(sym)
        ex = closes_e.get(sym)
        if ent is None or ex is None:
            continue
        if borrow_blocks_short(
            (ent[1] / h["prior_close"] - 1.0) if h["prior_close"] > 0 else None,
            h["prior_dv"],
        ):
            continue
        shares = notional_shares(ent[1])
        if shares < 1:
            continue
        pnl = signed_pnl(-1, shares, ent[1], ex[1])
        trades_s.append(_pack(pnl, -1, shares, ent[1], ex[1], ent[0], ex[0], "res_short", sym))
    return {
        "session": iso,
        "trades": {
            "res_long": trades_l,
            "res_short": trades_s,
            "res_ls": trades_l + trades_s,
        },
        "n_res": len(rows),
        "char_bottom": char_b,
        "char_top": char_t,
        "skipped": "",
    }


def _daily_and_trades(chunks: dict, sessions: list[date], name: str, weeks: list[date]):
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
    n_weeks = sum(1 for d in weeks if (chunks.get(d.isoformat()) or {}).get("skipped") == "")
    sm["peak_conc"] = max((r["peak"] for r in rows), default=0)
    sm["mean_conc"] = (sum(r["mean_conc"] for r in rows if r["peak"]) / n_weeks) if n_weeks else 0.0
    sm["daily_close_dd"] = daily_close_drawdown(daily)
    sm["worst_day"] = min(daily) if daily else 0.0
    sm["n_week"] = n_weeks
    sm["trades_per_week"] = (len(trades) / n_weeks) if n_weeks else 0.0
    return sm, daily, trades, {r["session"]: r["pnl"] for r in rows}


def _alpha(trades, sessions, iwm):
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
        e = _iwm_px(iwm.get(e_iso), ets, use_open=False)
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


def _month_lines(daily: list[float], sessions: list[date]) -> str:
    buckets: dict[str, list[float]] = defaultdict(list)
    for d, v in zip(sessions, daily):
        buckets[f"{d.year:04d}-{d.month:02d}"].append(float(v))
    bits = []
    for key in sorted(buckets):
        xs = buckets[key]
        n = len(xs)
        mean = sum(xs) / n if n else 0.0
        bits.append(f"{key} n={n} $/day={mean:.2f}")
    return "; ".join(bits)


def _fmt_book(sm: dict) -> list[str]:
    return [
        (
            f"    n={sm['n_trades']}  n/week={sm['trades_per_week']:.2f}  hit={sm['hit_rate']:.3f}  "
            f"avgR=n/a (no stop)  PF={sm['pf_s']}"
        ),
        (
            f"    avgWin$={sm['avg_win']:.2f}  avgLoss$={sm['avg_loss']:.2f}  "
            f"$/day={sm['per_day']:.2f}  std={sm['std_day']:.2f}  se={sm['se_day']:.2f}  "
            f"t={sm['t_stat']:.2f}  ci95=[{sm['ci_lo']:.2f},{sm['ci_hi']:.2f}]"
        ),
        (
            f"    daily-close DD$={sm['daily_close_dd']:.2f}  worst_day$={sm['worst_day']:.2f}  "
            f"peak_conc={sm['peak_conc']}  mean_conc={sm['mean_conc']:.2f}  weeks={sm['n_week']}"
        ),
    ]


def _char_block(bottom: dict[str, list[float]], top: dict[str, list[float]]) -> list[str]:
    lines = [
        "character IS rebalance weeks only (full eligible universe, not the 15+15). "
        "This-week residual bottom vs top; next-week residual. Description. Does not pick a book."
    ]

    def _stats(xs: list[float]) -> str:
        if not xs:
            return "n=0"
        n = len(xs)
        mean = sum(xs) / n
        hit = sum(1 for x in xs if x > 0) / n
        return f"n={n} mean={mean:.5f} hit={hit:.3f}"

    all_b = [x for xs in bottom.values() for x in xs]
    all_t = [x for xs in top.values() for x in xs]
    spread = (sum(all_b) / len(all_b) - sum(all_t) / len(all_t)) if all_b and all_t else 0.0
    lines.append(f"  bottom (worst this-week residual) next-week residual {_stats(all_b)}")
    lines.append(f"  top (best this-week residual) next-week residual {_stats(all_t)}")
    lines.append(f"  spread bottom-top={spread:.5f}")
    for key in sorted(set(bottom) | set(top)):
        lines.append(
            f"  {key}  bottom {_stats(bottom.get(key) or [])}  top {_stats(top.get(key) or [])}"
        )
    return lines


def run_arrow44(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 44 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    reb = rebalance_sessions(study)
    print(
        f"research start mode=arrow44 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"rebalance_weeks={len(reb)} jan_tape={tape_root(date(2026, 1, 2))} "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "weekly residual vs IWM. res_long 15 worst / res_short 15 best / res_ls both. "
        "Did not retune Arrow 43 clocks or frozen B/flush. No FLY. No 08:00. No conjunction. "
        "No new ingest. Did not touch Lab A data/bars. No Arrow 45.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    usable_weeks: list[date] = []
    for r in reb:
        look = session_shift(r, -LOOKBACK, feats)
        exd = session_shift(r, HOLD, feats)
        if look is None or exd is None:
            continue
        if not (tape_root(exd) / exd.isoformat()).exists():
            continue
        i0 = _iwm_last_close(iwm, look)
        i1 = _iwm_last_close(iwm, r)
        ie = _iwm_last_close(iwm, exd)
        usable_weeks.append(r)
        jobs.append(
            (
                r.isoformat(),
                look.isoformat(),
                exd.isoformat(),
                by.get(r.isoformat(), []),
                i0[1] if i0 else None,
                i1[1] if i1 else None,
                ie[1] if ie else None,
                is_is_session(r),
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"name-days={elig.height} weeks={len(jobs)} long={N_LONG} short={N_SHORT} "
        f"notional=${NOTIONAL:.0f} min_names={MIN_RESIDUAL_NAMES}",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow44")
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

    char_b: dict[str, list[float]] = defaultdict(list)
    char_t: dict[str, list[float]] = defaultdict(list)
    for d in usable_weeks:
        if not is_is_session(d):
            continue
        rec = chunks.get(d.isoformat()) or {}
        key = f"{d.year:04d}-{d.month:02d}"
        char_b[key].extend(rec.get("char_bottom") or [])
        char_t[key].extend(rec.get("char_top") or [])

    results = []
    maps = {}
    for name in IDS:
        sm_is, day_is, tr_is, map_is = _daily_and_trades(chunks, is_sess, name, [d for d in usable_weeks if is_is_session(d)])
        sm_oos, day_oos, tr_oos, map_oos = _daily_and_trades(
            chunks, oos_sess, name, [d for d in usable_weeks if not is_is_session(d)]
        )
        a_is, skip_is, n_is = _alpha(tr_is, is_sess, iwm)
        a_oos, skip_oos, n_oos = _alpha(tr_oos, oos_sess, iwm)
        seat = name == "res_ls" and sm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_is["per_day"] >= 0.0
        results.append(
            {
                "name": name,
                "is": sm_is,
                "oos": sm_oos,
                "a_is": a_is,
                "a_oos": a_oos,
                "skip_is": skip_is,
                "skip_oos": skip_oos,
                "n_a_is": n_is,
                "n_a_oos": n_oos,
                "seat": seat,
                "is_months": _month_lines(day_is, is_sess),
                "oos_months": _month_lines(day_oos, oos_sess),
            }
        )
        maps[name] = {**map_is, **map_oos}

    ls = next(r for r in results if r["name"] == "res_ls")
    if ls["seat"]:
        verdict = (
            f"VERDICT: SEAT — res_ls (OOS >= ${SEAT_FLOOR:.0f}/day and IS not red). "
            "Legs are diagnostics. Slate $200 is not this arrow's job."
        )
    else:
        verdict = (
            f"VERDICT: FAIL — res_ls does not have OOS >= ${SEAT_FLOOR:.0f}/day AND non-red IS. "
            "Legs are diagnostics. Slate $200 is not this arrow's job."
        )
    comb_legs = combine_books(maps["res_long"], maps["res_short"])
    corr = comb_legs["corr"].get((0, 1), 0.0)
    honesty = (
        "No stop for a five-session hold. 30 names × $2,000 is $60k deployed. "
        "Costs on a weekly book are smaller than Arrow 43 overnight but still real. "
        "Residual = name return − IWM return (not a regression, not 09:30). "
        "Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "Odd months IS, even months OOS, split on entry session. Combined dollars are not EV. No Arrow 45."
    )
    n_skip_thin = sum(1 for d in usable_weeks if (chunks.get(d.isoformat()) or {}).get("skipped") == "thin")
    lines = [
        "Arrow 44 — weekly residual vs IWM (IS / OOS)",
        verdict,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"study n={len(study)} {study[0]}..{study[-1]}  IS n={len(is_sess)} odd months  "
        f"OOS n={len(oos_sess)} even months  rebalance weeks={len(jobs)} thin_skips={n_skip_thin}",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: same wall as Arrow 43, prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], "
        f"PDV >= ${MIN_PDV:.0f}  rank residual  long {N_LONG} worst / short {N_SHORT} best  "
        f"${NOTIONAL:.0f} notional/name  hold {HOLD} sessions",
        "Fills at last tradeable RTH minute of the rebalance session; exit last RTH five sessions later. "
        "Skip week if < 40 names have a residual. No FLY. No 08:00. No conjunction. No new ingest.",
        "",
    ]
    lines.extend(_char_block(char_b, char_t))
    lines.append("")
    lines.append(
        f"{'id':<12} {'split':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'PF':>7} {'t':>6} "
        f"{'IWM$':>8} {'seat':>5}"
    )
    for r in results:
        for split, sm, a, skip, n_a, months in (
            ("IS", r["is"], r["a_is"], r["skip_is"], r["n_a_is"], r["is_months"]),
            ("OOS", r["oos"], r["a_oos"], r["skip_oos"], r["n_a_oos"], r["oos_months"]),
        ):
            if split == "OOS" and r["seat"]:
                flag = "SEAT"
            elif split == "OOS":
                flag = "NO"
            else:
                flag = "IS"
            lines.append(
                f"{r['name']:<12} {split:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['pf_s']:>7} {sm['t_stat']:6.2f} {a:8.2f} {flag:>5}"
            )
            lines.extend(_fmt_book(sm))
            lines.append(f"    IWM alpha $/day={a:.2f} (n={n_a} skip={skip})")
            lines.append(f"    months: {months}")
    lines.append("")
    lines.append("legs are diagnostics; res_ls is the seat candidate")
    lines.append(f"  corr daily PnL  res_long vs res_short={corr:.3f}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow44_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow44_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 44",
        "",
        verdict,
        "",
        "Weekly residual vs IWM. Long 15 worst / short 15 best, 5-session hold. "
        "Odd months IS, even months OOS, split on entry session. Combined virgin Jan–May + full Jun–Aug. "
        "Did not retune Arrow 43 clocks or B|conj|atr1559|lock or flush|max6|repaired. "
        "No new ingest. Did not touch Lab A data/bars. Legs are diagnostics. No Arrow 45.",
    ]
    for r in results:
        bits.append(
            f"- {r['name']}: IS ${r['is']['per_day']:.2f}/day n={r['is']['n_trades']}  "
            f"OOS ${r['oos']['per_day']:.2f}/day n={r['oos']['n_trades']}  "
            f"{'SEAT' if r['seat'] else 'no seat'}"
        )
    bits.append("")
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
