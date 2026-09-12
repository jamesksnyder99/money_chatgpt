"""Arrow 74 — intradaily leftover, January / February 2026. Long and short are separate."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import NYSE_EARLY_CLOSE
from ingest.paths import BARS_DIR, FULL_BARS, REPORTS, VIRGIN_BARS, VIRGIN_ELIGIBILITY
from ingest.progress import Progress
from research.arrow23 import _summarize_adv
from research.arrow43 import (
    SEAT_FLOOR,
    _clock,
    _read_bars,
    load_combined_iwm,
)
from research.arrow44 import MIN_PDV, MIN_PX, MAX_PX, _by_sess, _month_lines
from research.arrow45 import _daily_and_trades
from research.arrow47 import _short_n
from research.arrow48 import _wins_losses
from research.arrow51 import _ci_note
from research.arrow57 import _char_stats, _fmt_book57, _long_n, select_losers, select_winners
from research.book import daily_close_drawdown
from research.clock import (
    arrow74_february,
    arrow74_january,
    arrow74_sessions,
    feature_sessions,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO
from research.fills import is_tradeable
from research.signals import MINUTE_1100, MINUTE_1559, RTH_OPEN

ET = ZoneInfo("America/New_York")
FILL_1101 = time(11, 1)
RTH_END = time(16, 0)
N_SLOT = 8
MIN_NAMES = 16
NOTIONAL = 3000.0
CONTROL_ID = "short_all"
LONG_ID = "long_all"
# name, side, days (all/wed), iwm (None/up/dn), fill (1101/1100)
EXPERIMENTS = (
    ("short_all", "short", "all", None, "1101"),
    ("long_all", "long", "all", None, "1101"),
    ("short_wed", "short", "wed", None, "1101"),
    ("short_1100", "short", "all", None, "1100"),
    ("short_up", "short", "all", "up", "1101"),
    ("short_dn", "short", "all", "dn", "1101"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def fill_clock(kind: str) -> time:
    """Id 0 fill is 11:01, not the 11:00 rank stamp. Id 3 fills 11:00 (old lie)."""
    if kind == "1100":
        return MINUTE_1100
    return FILL_1101


def morning_return(px0930: float | None, px1100: float | None) -> float | None:
    if px0930 is None or px1100 is None or px0930 <= 0 or px1100 <= 0:
        return None
    return px1100 / px0930 - 1.0


def extract_intraday(session: date, symbol: str) -> dict | None:
    """0930, last <=11:00, first >=11:01, 15:59 / last RTH after 11:01."""
    df = _read_bars(session, symbol)
    if df is None:
        return None
    early = NYSE_EARLY_CLOSE.get(session)
    px0930 = None
    px1100 = None
    fill1101 = None
    last_after = None
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
        if px0930 is None and t >= RTH_OPEN:
            px0930 = (ts, px)
        if t <= MINUTE_1100:
            px1100 = (ts, px)
        if t >= FILL_1101:
            if fill1101 is None:
                fill1101 = (ts, px)
            last_after = (ts, px)
        if t == MINUTE_1559:
            px1559 = (ts, px)
    if px0930 is None or px1100 is None:
        return None
    mret = morning_return(px0930[1], px1100[1])
    if mret is None:
        return None
    exit_bar = px1559 if px1559 is not None else last_after
    return {
        "mret": mret,
        "px0930": px0930,
        "px1100": px1100,
        "fill1101": fill1101,
        "exit": exit_bar,
        "partial": px1559 is None and last_after is not None,
    }


def session_exists(kind_days: str, iwm_filt: str | None, session: date, iwm_mret: float | None) -> bool:
    if kind_days == "wed" and session.weekday() != 2:
        return False
    if iwm_filt == "up":
        return iwm_mret is not None and iwm_mret >= 0.0
    if iwm_filt == "dn":
        return iwm_mret is not None and iwm_mret < 0.0
    return True


def peak_live_intraday(trades: list[dict]) -> float:
    by: dict[str, float] = {}
    for t in trades:
        iso = t["signal"].isoformat() if isinstance(t.get("signal"), date) else str(t.get("signal"))[:10]
        by[iso] = by.get(iso, 0.0) + abs(float(t["shares"]) * float(t["entry_px"]))
    return max(by.values()) if by else 0.0


def _elig_janfeb(sessions: list[date]) -> pl.DataFrame:
    if not VIRGIN_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {VIRGIN_ELIGIBILITY}")
    cols = ["symbol", "session_date", "prior_close", "prior_dollar_volume"]
    v = pl.read_parquet(VIRGIN_ELIGIBILITY)
    keep = [c for c in cols if c in v.columns]
    v = v.select(keep).filter(pl.col("session_date").is_in(list(sessions)))
    return v.filter(
        pl.col("prior_close").is_not_null()
        & (pl.col("prior_close") >= MIN_PX)
        & (pl.col("prior_close") <= MAX_PX)
        & (pl.col("prior_dollar_volume") >= MIN_PDV)
    )


def _session_job(args: tuple) -> dict:
    iso, names, iwm_df = args
    session = date.fromisoformat(iso)
    empty = {
        "session": iso,
        "rows": [],
        "n_mret": 0,
        "iwm_mret": None,
        "skipped": "no_names",
    }
    if not names:
        return empty
    iwm_mret = _iwm_morning(iwm_df, session)
    rows = []
    for h in names:
        got = extract_intraday(session, h["symbol"])
        if got is None:
            continue
        rows.append({**h, **got})
    return {
        "session": iso,
        "rows": rows,
        "n_mret": len(rows),
        "iwm_mret": iwm_mret,
        "skipped": "" if rows else "thin",
    }


def _iwm_morning(df: pl.DataFrame | None, session: date) -> float | None:
    if df is None or df.height == 0:
        return None
    early = NYSE_EARLY_CLOSE.get(session)
    px0930 = None
    px1100 = None
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
        if px0930 is None and t >= RTH_OPEN:
            px0930 = px
        if t <= MINUTE_1100:
            px1100 = px
    return morning_return(px0930, px1100)


def run_arrow74(*, workers: int | None = None) -> int:
    jan = arrow74_january()
    feb = arrow74_february()
    sess = arrow74_sessions()
    if any(d.month == 3 for d in sess):
        raise RuntimeError("Arrow 74 must not score March")
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 2, 3)) == FULL_BARS:
        raise RuntimeError("Arrow 74 must not read Lab A data/bars/ or data/full/")
    leftover = feature_sessions()
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    print(
        f"research start mode=arrow74 workers={workers} cpu={cpu} "
        f"window={sess[0]}..{sess[-1]} n={len(sess)} jan n={len(jan)} feb n={len(feb)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} feb_tape={tape_root(date(2026, 2, 3))}",
        flush=True,
    )
    print(
        "Intradaily leftover January / February 2026. Long and short are separate engines. "
        "Did not retune Wednesday H10. Did not keep/cash. Did not IWM-up skip the swing book. "
        "Did not use February to pick a threshold. No new ingest. No Arrow 75.",
        flush=True,
    )
    elig = _elig_janfeb(sess)
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    for d in sess:
        jobs.append((d.isoformat(), by.get(d.isoformat(), []), iwm.get(d.isoformat())))
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"morning 09:30→11:00 n={N_SLOT} fill>=11:01 exit 15:59 ${NOTIONAL:.0f} "
        f"jobs={len(jobs)}",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow74")
    prog.start_heartbeat()
    recs: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_session_job, job) for job in jobs]
        for i, fut in enumerate(as_completed(futs), 1):
            rec = fut.result()
            recs[rec["session"]] = rec
            prog.mark(rec["session"], rows=1)
            if i % 5 == 0:
                prog.heartbeat()
    prog.stop_heartbeat()
    prog.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": 0}
        for d in sess
    }
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    usable: dict[str, list[date]] = {k: [] for k in IDS}
    skips: dict[str, dict[str, int]] = {k: {"jan": 0, "feb": 0} for k in IDS}
    partials: dict[str, dict[str, int]] = {k: {"jan": 0, "feb": 0} for k in IDS}
    jan_win: list[float] = []
    jan_lag: list[float] = []

    for d in sess:
        rec = recs.get(d.isoformat()) or {}
        rows = list(rec.get("rows") or [])
        n_mret = int(rec.get("n_mret") or 0)
        chunks[d.isoformat()]["n_res"] = n_mret
        iwm_mret = rec.get("iwm_mret")
        month = "jan" if d.month == 1 else "feb"
        if n_mret < MIN_NAMES:
            continue
        for r in rows:
            r["session_iso"] = d.isoformat()
        winners = select_winners(rows, N_SLOT, "mret")
        laggards = select_losers(rows, N_SLOT, "mret")
        if d.month == 1:
            for h in winners:
                ent, ex = h.get("fill1101"), h.get("exit")
                if ent is not None and ex is not None and ent[1] > 0:
                    jan_win.append(ex[1] / ent[1] - 1.0)
            for h in laggards:
                ent, ex = h.get("fill1101"), h.get("exit")
                if ent is not None and ex is not None and ent[1] > 0:
                    jan_lag.append(ex[1] / ent[1] - 1.0)
        for name, side, days, iwm_filt, fill_kind in EXPERIMENTS:
            if not session_exists(days, iwm_filt, d, iwm_mret):
                continue
            usable[name].append(d)
            picks = winners if side == "short" else laggards
            for h in picks:
                if fill_kind == "1100":
                    ent = h.get("px1100")
                else:
                    ent = h.get("fill1101")
                ex = h.get("exit")
                if ent is None or ex is None:
                    skips[name][month] += 1
                    continue
                if fill_kind != "1100" and _clock(ent[0]) < FILL_1101:
                    skips[name][month] += 1
                    continue
                if side == "short":
                    tr = _short_n(h, ent, ex, fill_kind, NOTIONAL)
                else:
                    tr = _long_n(h, ent, ex, fill_kind, NOTIONAL)
                if tr is None:
                    continue
                tr["signal"] = d
                tr["fill_date"] = d
                tr["exit_date"] = d
                tr["exit_partial"] = bool(h.get("partial"))
                if tr["exit_partial"]:
                    partials[name][month] += 1
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                trades_all[name].append(tr)

    fade = (sum(jan_win) / len(jan_win)) if jan_win else None
    bounce = (sum(jan_lag) / len(jan_lag)) if jan_lag else None
    fade_exists = fade is not None and fade < 0
    char_line = (
        f"January character (11:01→15:59 of the eight morning winners / laggards). "
        f"Description. Does not pick an id. "
        f"winners {_char_stats(jan_win)}  laggards {_char_stats(jan_lag)}. "
        f"Afternoon fade of morning winners: {'yes' if fade_exists else 'no'}."
    )
    print(char_line, flush=True)

    def _score_month(name: str, month_sess: list[date], label: str) -> dict:
        weeks = [d for d in usable[name] if d in set(month_sess)]
        sm_ent, daily, tr = _daily_and_trades(chunks, month_sess, name, weeks)
        sm_ent["n_win"], sm_ent["n_loss"] = _wins_losses(tr)
        sm_ent["daily_close_dd"] = daily_close_drawdown(daily)
        sm_ent["worst_day"] = min(daily) if daily else 0.0
        peak = peak_live_intraday(tr)
        return {
            "sm": sm_ent,
            "tr": tr,
            "daily": daily,
            "peak": peak,
            "n_sess": len(month_sess),
            "n_days": len(weeks),
            "months": _month_lines(daily, month_sess),
        }

    results = []
    for name, side, days, iwm_filt, fill_kind in EXPERIMENTS:
        jan_s = _score_month(name, jan, "jan")
        feb_s = _score_month(name, feb, "feb")
        peak_all = peak_live_intraday(trades_all[name])
        results.append(
            {
                "name": name,
                "side": side,
                "days": days,
                "iwm_filt": iwm_filt,
                "fill_kind": fill_kind,
                "jan": jan_s,
                "feb": feb_s,
                "peak_all": peak_all,
                "n_all": len(trades_all[name]),
                "skip_jan": skips[name]["jan"],
                "skip_feb": skips[name]["feb"],
                "part_jan": partials[name]["jan"],
                "part_feb": partials[name]["feb"],
                "ci_jan_ex": jan_s["sm"]["ci_lo"] > 0 or jan_s["sm"]["ci_hi"] < 0,
                "ci_feb_ex": feb_s["sm"]["ci_lo"] > 0 or feb_s["sm"]["ci_hi"] < 0,
            }
        )

    short0 = next(r for r in results if r["name"] == CONTROL_ID)
    long1 = next(r for r in results if r["name"] == LONG_ID)
    wed = next(r for r in results if r["name"] == "short_wed")
    lie = next(r for r in results if r["name"] == "short_1100")
    fill_prints = short0["jan"]["sm"]["n_trades"] > 0
    wed_vs_all = (
        f"Wednesday-only Jan $/day={wed['jan']['sm']['per_day']:.2f} vs every-session "
        f"{short0['jan']['sm']['per_day']:.2f}."
    )
    long_vs_short = (
        f"Long Jan $/day={long1['jan']['sm']['per_day']:.2f} vs short "
        f"{short0['jan']['sm']['per_day']:.2f}."
    )
    first_para = (
        f"{char_line} 11:01 fill still prints: {'yes' if fill_prints else 'NO'} "
        f"(id 0 Jan n={short0['jan']['sm']['n_trades']}; id 3 11:00-fill Jan n="
        f"{lie['jan']['sm']['n_trades']}). {wed_vs_all} {long_vs_short}"
    )
    verdict = (
        "VERDICT: SNIFF — two months is not a seat. February is one look, not a $200 slate pass. "
        "Did not treat January/February as the shop IS/OOS split. Did not score March–August."
    )
    honesty = (
        "Intradaily leftover. Jersey = who already ran this morning, not three weeks. "
        "Long and short are separate engines. Did not retune Wednesday H10. "
        "Did not keep/cash. Did not IWM-up skip the swing book. "
        "Morning return = last print at or before 11:00 ÷ first RTH print at or after 09:30 − 1. "
        "IWM morning return uses the same stamps (scalar). "
        "Short the 8 largest morning returns. Long buys the 8 smallest. "
        "Did not fill the 11:00 rank bar except id 3 (old lie). "
        "Fill = first print at or after 11:01. Exit = last RTH 15:59 same session. $3,000 a name. "
        "January is character / first look. February is one look. "
        "Did not use February to pick a threshold. "
        "Do not call a CI that includes 0 EV. Do not call February a $200 slate pass. "
        "No new ingest. Did not touch Lab A data/bars/ or data/full/. No Arrow 75."
    )
    lines = [
        "Arrow 74 — intradaily leftover, January / February 2026",
        verdict,
        first_para,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  seat_floor={SEAT_FLOOR:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"window n={len(sess)} {sess[0]}..{sess[-1]}  jan n={len(jan)}  feb n={len(feb)}  "
        f"(March not scored)",
        f"workers={workers} cpu_count={cpu}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"feb_tape={tape_root(date(2026, 2, 3))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"n={N_SLOT}  fill>=11:01  exit 15:59  ${NOTIONAL:.0f}",
        "Peak live = |shares × entry| same session. $/day = total PnL / NYSE sessions in that month.",
        "",
        f"{'id':<12} {'month':<4} {'$/day':>9} {'n':>6} {'hit':>6} {'t':>6} {'days':>5}",
    ]
    for r in results:
        for label, pack, skip_n, part_n, ci_ex in (
            ("Jan", r["jan"], r["skip_jan"], r["part_jan"], r["ci_jan_ex"]),
            ("Feb", r["feb"], r["skip_feb"], r["part_feb"], r["ci_feb_ex"]),
        ):
            sm = pack["sm"]
            lines.append(
                f"{r['name']:<12} {label:<4} {sm['per_day']:9.2f} {sm['n_trades']:6d} "
                f"{sm['hit_rate']:6.3f} {sm['t_stat']:6.2f} {pack['n_days']:5d}"
            )
            lines.extend(_fmt_book57(sm))
            lines.append(
                f"    $/day={sm['per_day']:.2f} (total PnL / n={pack['n_sess']} sessions)  "
                f"side={r['side']} days={r['days']} iwm={r['iwm_filt'] or 'any'} "
                f"fill={r['fill_kind']}  skips={skip_n} partial={part_n}  "
                f"peak live ${pack['peak']:.0f}  all ${r['peak_all']:.0f}"
                f"{_ci_note(sm)}"
            )
            lines.append(f"    months: {pack['months']}")
            if ci_ex:
                lines.append(f"    {label} CI excludes 0.")
            else:
                lines.append(f"    {label} CI includes 0 — not EV.")
    lines.append("    Did not call February a $200 slate pass. Two months is a sniff, not a seat. No Arrow 75.")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow74_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow74_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 74",
        "",
        verdict,
        "",
        first_para,
        f"short_all Jan ${short0['jan']['sm']['per_day']:.2f} n={short0['jan']['sm']['n_trades']}  "
        f"Feb ${short0['feb']['sm']['per_day']:.2f} n={short0['feb']['sm']['n_trades']}  "
        f"long_all Jan ${long1['jan']['sm']['per_day']:.2f} Feb ${long1['feb']['sm']['per_day']:.2f}. "
        "Did not use February to pick a threshold. No Arrow 75.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 74"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
