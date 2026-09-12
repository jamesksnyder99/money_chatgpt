"""Arrow 71 — Wednesday H10 keep/cash. Same entries as Arrow 66 h10_4k. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.calendar import NYSE_EARLY_CLOSE
from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow23 import _summarize_adv
from research.arrow43 import (
    SEAT_FLOOR,
    _clock,
    _elig_frame,
    _read_bars,
    _rth_rows,
    load_combined_iwm,
)
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
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow47 import _short_n
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import LB, MIN_RESIDUAL, N_SHORT
from research.arrow65 import (
    _as_date,
    _last_job,
    _make_trade,
    _mtm_and_peak,
    _rank_job,
    fill_session_of,
)
from research.book import daily_close_drawdown
from research.clock import (
    combined_study_sessions,
    feature_sessions,
    is_is_session,
    session_shift,
    split_is_oos,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
A66_H10_IS_MTM = 401.16
A66_H10_IS_N = 116
CONTROL_ID = "h10_4k"
FILL_KIND = "nextrth"
NOTIONAL = 4000.0
HOLD_BACKSTOP = 10
N_TOP_A = 20
CASH_C_FROM = 3
CASH_C_FRAC = 0.01
KEEP = False
# name, rules in order (first fire wins). Empty = hold 10 only.
EXPERIMENTS = (
    ("h10_4k", ()),
    ("cash_A", ("A",)),
    ("cash_B", ("B",)),
    ("cash_C", ("C",)),
    ("cash_AB", ("A", "B")),
    ("cash_ABC", ("A", "B", "C")),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def fires_A(symbol: str, top20: set[str] | None) -> bool:
    """A: name is not in today's leftover top 20. None = rank missing, do not fire."""
    if top20 is None:
        return False
    return symbol not in top20


def fires_B(last_rth: float, fill_px: float, prior_highs: list[float]) -> bool:
    """B: last-RTH >= fill, or last-RTH is a new high vs prior 5 session highs."""
    if last_rth >= fill_px - 1e-12:
        return True
    if prior_highs and last_rth >= max(prior_highs) - 1e-12:
        return True
    return False


def fires_C(hold_day: int, last_rth: float, fill_px: float) -> bool:
    """C: hold-day 3+ and last-RTH is not at least 1% below fill."""
    if hold_day < CASH_C_FROM:
        return False
    if fill_px <= 0:
        return False
    return last_rth >= fill_px * (1.0 - CASH_C_FRAC) - 1e-12


def first_cash_rule(
    hold_day: int,
    symbol: str,
    last_rth: float,
    fill_px: float,
    prior_highs: list[float],
    top20: set[str] | None,
    rules: tuple[str, ...],
) -> str | None:
    """First enabled rule that fires. None = keep."""
    for r in rules:
        if r == "A" and fires_A(symbol, top20):
            return "A"
        if r == "B" and fires_B(last_rth, fill_px, prior_highs):
            return "B"
        if r == "C" and fires_C(hold_day, last_rth, fill_px):
            return "C"
    return None


def remaining_names(
    original: list[str], cashed: set[str], new_leftover: list[str] | None = None
) -> list[str]:
    """Do not replace a cashed name with a new leftover."""
    _ = new_leftover
    return [s for s in original if s not in cashed]


def dd_not_worse(cash_dd: float, ctrl_dd: float, frac: float = 0.25) -> bool:
    """True if cash OOS DD is not more than 25% worse than control (more negative)."""
    if ctrl_dd >= 0:
        return cash_dd >= ctrl_dd * (1.0 + frac) - 1e-12
    return cash_dd + 1e-12 >= ctrl_dd * (1.0 + frac)


def hold_days_between(fill_d: date, exit_d: date, sessions: list[date]) -> int | None:
    try:
        return sessions.index(exit_d) - sessions.index(fill_d)
    except ValueError:
        return None


def session_rth_high(session: date, symbol: str) -> float | None:
    """Max RTH bar high. Early-close clipped."""
    df = _read_bars(session, symbol)
    if df is None:
        return None
    rows = _rth_rows(df)
    early = NYSE_EARLY_CLOSE.get(session)
    if early is not None:
        rows = [r for r in rows if _clock(r["bar_start"]) < early]
    highs = [float(r["high"]) for r in rows if r.get("high") is not None]
    return max(highs) if highs else None


def _high_job(args: tuple) -> tuple[str, str, float | None]:
    iso, symbol = args
    return iso, symbol, session_rth_high(date.fromisoformat(iso), symbol)


def _close_job(args: tuple) -> tuple[str, str, tuple | None]:
    iso, symbol = args
    got = _last_close(date.fromisoformat(iso), symbol)
    return iso, symbol, got


def run_arrow71(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 71 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow71 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "Wednesday H10 keep/cash. Same leftover short as Arrow 66 h10_4k. "
        "Same entries. Only the exit can change. Did not replace a cashed name. "
        "Did not use an OOS month to pick a threshold. No new ingest. No Arrow 72.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    weds: list[date] = []
    rank_days: list[date] = []
    for d in study:
        look15 = session_shift(d, -LB, feats)
        if look15 is None:
            continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
        rank_days.append(d)
        if d.weekday() == 2:
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
        f"Wednesday signal n={N_SHORT} lb={LB} fill=nextrth ${NOTIONAL:.0f} "
        f"hold-10 backstop  cash top{N_TOP_A}  jobs={len(jobs)} weds={len(weds)}",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow71")
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
    top20_by: dict[str, set[str] | None] = {}
    for d in rank_days:
        rec = recs.get(d.isoformat()) or {}
        nres_by[d.isoformat()] = int(rec.get("n_res") or 0)
        rows = list(rec.get("rows") or [])
        if not rows or rec.get("skipped"):
            top20_by[d.isoformat()] = None
        else:
            top20_by[d.isoformat()] = {h["symbol"] for h in select_shorts(rows, N_TOP_A, None)}
    for d in weds:
        rec = recs.get(d.isoformat()) or {}
        rows = list(rec.get("rows") or [])
        if (rec.get("n_res") or 0) < MIN_RESIDUAL:
            picks_by[d.isoformat()] = []
            continue
        picks_by[d.isoformat()] = select_shorts(rows, N_SHORT, None)

    need_close: set[tuple[str, str]] = set()
    need_high: set[tuple[str, str]] = set()
    for d in weds:
        fill_d = fill_session_of(d, FILL_KIND, feats)
        if fill_d is None:
            continue
        for h in picks_by.get(d.isoformat()) or []:
            sym = h["symbol"]
            for k in range(0, HOLD_BACKSTOP + 1):
                dk = session_shift(fill_d, k, feats)
                if dk is None:
                    continue
                need_close.add((dk.isoformat(), sym))
                if k < HOLD_BACKSTOP:
                    need_high.add((dk.isoformat(), sym))

    close_map: dict[tuple[str, str], tuple] = {}
    if need_close:
        prog2 = Progress(len(need_close), "arrow71-close")
        prog2.start_heartbeat()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_close_job, job) for job in sorted(need_close)]
            for i, fut in enumerate(as_completed(futs), 1):
                iso, symbol, got = fut.result()
                if got is not None:
                    close_map[(iso, symbol)] = got
                prog2.mark(str(i), rows=1)
                if i % 64 == 0:
                    prog2.heartbeat()
        prog2.stop_heartbeat()
        prog2.heartbeat()
    high_map: dict[tuple[str, str], float] = {}
    if need_high:
        prog3 = Progress(len(need_high), "arrow71-high")
        prog3.start_heartbeat()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_high_job, job) for job in sorted(need_high)]
            for i, fut in enumerate(as_completed(futs), 1):
                iso, symbol, px = fut.result()
                if px is not None:
                    high_map[(iso, symbol)] = px
                prog3.mark(str(i), rows=1)
                if i % 64 == 0:
                    prog3.heartbeat()
        prog3.stop_heartbeat()
        prog3.heartbeat()

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in study
    }
    skips: dict[str, dict[str, int]] = {k: {"IS": 0, "OOS": 0} for k in IDS}
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    usable: dict[str, list[date]] = {k: [] for k in IDS}

    def _prior_highs(fill_d: date, today: date, symbol: str) -> list[float]:
        days = [x for x in feats if fill_d <= x < today]
        days = days[-5:]
        out: list[float] = []
        for x in days:
            hi = high_map.get((x.isoformat(), symbol))
            if hi is not None:
                out.append(float(hi))
        return out

    def _cash_exit(symbol: str, fill_d: date, fill_px: float, rules: tuple[str, ...]):
        for k in range(1, HOLD_BACKSTOP + 1):
            dk = session_shift(fill_d, k, feats)
            if dk is None:
                return None, None, None
            got = close_map.get((dk.isoformat(), symbol))
            if got is None:
                if k == HOLD_BACKSTOP:
                    return None, None, None
                continue
            if k < HOLD_BACKSTOP and rules:
                rule = first_cash_rule(
                    k,
                    symbol,
                    float(got[1]),
                    fill_px,
                    _prior_highs(fill_d, dk, symbol),
                    top20_by.get(dk.isoformat()),
                    rules,
                )
                if rule:
                    return got, k, rule
            if k == HOLD_BACKSTOP:
                return got, k, None
        return None, None, None

    for d in weds:
        picks = picks_by.get(d.isoformat()) or []
        split = "IS" if is_is_session(d) else "OOS"
        for name, rules in EXPERIMENTS:
            if nres_by.get(d.isoformat(), 0) >= MIN_RESIDUAL:
                usable[name].append(d)
            for h in picks:
                if not rules:
                    tr, skip_fill, _partial = _make_trade(
                        h, FILL_KIND, NOTIONAL, KEEP, d, feats, hold=HOLD_BACKSTOP
                    )
                    if skip_fill:
                        skips[name][split] += 1
                        continue
                    if tr is None:
                        continue
                    hd = hold_days_between(tr["fill_date"], tr["exit_date"], feats)
                    tr["hold_days"] = hd if hd is not None else HOLD_BACKSTOP
                    tr["early_cash"] = False
                    tr["cash_rule"] = None
                    chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                    trades_all[name].append(tr)
                    continue
                fill_d = fill_session_of(d, FILL_KIND, feats)
                if fill_d is None:
                    skips[name][split] += 1
                    continue
                ent = close_map.get((fill_d.isoformat(), h["symbol"]))
                if ent is None:
                    skips[name][split] += 1
                    continue
                ex, hold_k, rule = _cash_exit(h["symbol"], fill_d, float(ent[1]), rules)
                if ex is None or hold_k is None:
                    continue
                tr = _short_n(h, ent, ex, FILL_KIND, NOTIONAL)
                if tr is None:
                    continue
                tr["signal"] = d
                tr["fill_date"] = fill_d
                tr["exit_date"] = _as_date(ex[0])
                tr["exit_partial"] = False
                tr["hold_days"] = int(hold_k)
                tr["early_cash"] = int(hold_k) < HOLD_BACKSTOP
                tr["cash_rule"] = rule
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(tr)
                trades_all[name].append(tr)

    sm0_is, _, tr0 = _daily_and_trades(
        chunks, is_sess, CONTROL_ID, [d for d in weds if is_is_session(d)]
    )
    last_map: dict[tuple[str, str], float] = {}
    need_mtm: set[tuple[str, str]] = set()
    for name, trs in trades_all.items():
        for t in trs:
            fill_d, exit_d = t["fill_date"], t["exit_date"]
            for x in study:
                if fill_d <= x < exit_d:
                    need_mtm.add((x.isoformat(), t["symbol"]))
            last_map.setdefault(
                (t["fill_date"].isoformat(), t["symbol"]),
                float(t["entry_px"]),
            )
    for key, got in close_map.items():
        last_map[key] = float(got[1])
    missing = [job for job in need_mtm if job not in last_map]
    if missing:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_last_job, job) for job in sorted(missing)]
            for fut in as_completed(futs):
                iso, symbol, px = fut.result()
                if px is not None:
                    last_map[(iso, symbol)] = px

    mtm0_all, _ = _mtm_and_peak(trades_all[CONTROL_ID], study, last_map)
    mtm0_is = [mtm0_all[study.index(d)] for d in is_sess]
    sm_mtm0 = _summarize_adv(mtm0_is, tr0, len(is_sess))
    reprint_ok = _within(sm_mtm0["per_day"], A66_H10_IS_MTM) and _within(
        sm0_is["n_trades"], A66_H10_IS_N
    )
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS MTM $/day={sm_mtm0['per_day']:.2f}/{A66_H10_IS_MTM} "
        f"n={sm0_is['n_trades']}/{A66_H10_IS_N} "
        + (
            "— within ±10% of Arrow 66 h10_4k."
            if reprint_ok
            else "— DRIFT beyond ±10%. Keep/cash not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 71 — Wednesday H10 keep / cash (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 66 h10_4k. "
            "Did not score cash on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 72.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow71_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    is_fills = [t for t in trades_all[CONTROL_ID] if is_is_session(t["signal"])]
    char_rows: list[dict] = []
    for k in range(1, HOLD_BACKSTOP + 1):
        n = n_a = n_b = n_c = 0
        for t in is_fills:
            fill_d = t["fill_date"]
            dk = session_shift(fill_d, k, feats)
            if dk is None:
                continue
            got = close_map.get((dk.isoformat(), t["symbol"]))
            if got is None:
                continue
            n += 1
            last = float(got[1])
            fill_px = float(t["entry_px"])
            if fires_A(t["symbol"], top20_by.get(dk.isoformat())):
                n_a += 1
            if fires_B(last, fill_px, _prior_highs(fill_d, dk, t["symbol"])):
                n_b += 1
            if fires_C(k, last, fill_px):
                n_c += 1
        char_rows.append(
            {
                "hold_day": k,
                "n": n,
                "frac_A": (n_a / n) if n else None,
                "frac_B": (n_b / n) if n else None,
                "frac_C": (n_c / n) if n else None,
            }
        )
    char_lines = [
        "IS character on id 0 names (hold-day 1..10). Fraction that would have fired "
        "A / B / C independently. Description. Does not pick an id. "
        "Did not replace a cashed name.",
        f"{'hold_day':>8} {'n':>5} {'frac_A':>8} {'frac_B':>8} {'frac_C':>8}",
    ]
    for r in char_rows:
        fa = f"{r['frac_A']:.3f}" if r["frac_A"] is not None else "n/a"
        fb = f"{r['frac_B']:.3f}" if r["frac_B"] is not None else "n/a"
        fc = f"{r['frac_C']:.3f}" if r["frac_C"] is not None else "n/a"
        char_lines.append(f"{r['hold_day']:8d} {r['n']:5d} {fa:>8} {fb:>8} {fc:>8}")

    results = []
    ctrl_is = ctrl_oos = ctrl_oos_dd = None
    for name, rules in EXPERIMENTS:
        weeks = usable[name]
        is_w = [d for d in weeks if is_is_session(d)]
        oos_w = [d for d in weeks if not is_is_session(d)]
        sm_ent_is, _, tr_is = _daily_and_trades(chunks, is_sess, name, is_w)
        sm_ent_oos, _, tr_oos = _daily_and_trades(chunks, oos_sess, name, oos_w)
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
        _, peak_is = _mtm_and_peak(trades_all[name], is_sess, last_map)
        _, peak_oos = _mtm_and_peak(trades_all[name], oos_sess, last_map)
        mean_h_is = (
            sum(float(t.get("hold_days") or 0) for t in tr_is) / len(tr_is) if tr_is else 0.0
        )
        mean_h_oos = (
            sum(float(t.get("hold_days") or 0) for t in tr_oos) / len(tr_oos) if tr_oos else 0.0
        )
        n_early_is = sum(1 for t in tr_is if t.get("early_cash"))
        n_early_oos = sum(1 for t in tr_oos if t.get("early_cash"))
        fits = peak_all <= ACCOUNT + 1e-12
        seat = sm_mtm_oos["per_day"] >= SEAT_FLOOR - 1e-12 and sm_mtm_is["per_day"] >= 0.0
        slate = (
            sm_mtm_oos["per_day"] >= FAILURE_LINE - 1e-12 and sm_mtm_is["per_day"] >= 0.0 and fits
        )
        if name == CONTROL_ID:
            ctrl_is, ctrl_oos = sm_mtm_is["per_day"], sm_mtm_oos["per_day"]
            ctrl_oos_dd = sm_mtm_oos["daily_close_dd"]
        lift_both = False
        beat = False
        if ctrl_is is not None and ctrl_oos is not None and name != CONTROL_ID:
            lift_both = (
                sm_mtm_is["per_day"] > ctrl_is + 1e-12 and sm_mtm_oos["per_day"] > ctrl_oos + 1e-12
            )
            beat = lift_both and dd_not_worse(sm_mtm_oos["daily_close_dd"], ctrl_oos_dd or 0.0)
        results.append(
            {
                "name": name,
                "rules": rules,
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
                "mean_h_is": mean_h_is,
                "mean_h_oos": mean_h_oos,
                "n_early_is": n_early_is,
                "n_early_oos": n_early_oos,
                "seat": seat,
                "slate": slate,
                "lift_both": lift_both,
                "beat": beat,
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
    both = [r["name"] for r in results if r["lift_both"]]
    beats = [r["name"] for r in results if r["beat"]]
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
            f"VERDICT: FAIL — no Arrow 71 engine has OOS MTM >= ${SEAT_FLOOR:.0f}/day AND non-red IS MTM."
        )
    abc = next(r for r in results if r["name"] == "cash_ABC")
    ctrl = results[0]
    if abc["beat"]:
        abc_note = "ABC helped (lifted both slices and did not worsen OOS DD >25%)."
    elif abc["ent_is"]["avg_win"] + 1e-12 < ctrl["ent_is"]["avg_win"] and (
        abc["n_early_is"] + abc["n_early_oos"] > 0
    ):
        abc_note = "ABC flattened winners (did not lift both slices)."
    else:
        abc_note = "ABC did not lift both slices versus id 0."
    beat_s = ", ".join(beats) if beats else "none"
    both_s = ", ".join(both) if both else "none"
    lead = (
        f"{reprint_line} Beat id 0 on both slices with DD guard: {beat_s}. "
        f"Lift-both (no DD guard): {both_s}. "
        f"Id 0 mean hold IS {ctrl['mean_h_is']:.2f} OOS {ctrl['mean_h_oos']:.2f}. "
        f"ABC mean hold IS {abc['mean_h_is']:.2f} OOS {abc['mean_h_oos']:.2f} "
        f"(early-cash IS {abc['n_early_is']} OOS {abc['n_early_oos']}). {abc_note}"
    )
    honesty = (
        "Wednesday H10 keep/cash. Same leftover short as Arrow 66 h10_4k: "
        "Wednesday signal, eight largest 15-session close-to-close returns, "
        "fill next session last-RTH, $4,000, hold-10 backstop. Same entries. "
        "Only the exit can change. Did not replace a flattened name with a new leftover. "
        "Did not retune rank, n, weekday, ticket, or fill. Did not retune frozen B/flush. "
        "Cash rules frozen: A = not in today's leftover top 20; "
        "B = last-RTH >= fill or new high vs prior 5 session highs from fill onward; "
        "C = hold-day 3+ and last-RTH not >=1% below fill. First rule that fires. "
        "Did not search X on OOS. Did not use an OOS month to pick a threshold. "
        "Did not drop an id after seeing OOS. Split on the signal Wednesday. "
        "Did not mix Sep–Dec 2025 into this family. "
        "A cash id beats id 0 only if it lifts MTM $/day on both IS and OOS "
        "and does not worsen OOS max DD by more than 25%. "
        "Do not call a CI that includes 0 EV. Combined dollars are not EV. No Arrow 72."
    )
    lines = [
        "Arrow 71 — Wednesday H10 keep / cash (IS / OOS)",
        verdict,
        lead,
        f"Engines that clear seat ${SEAT_FLOOR:.0f}/day OOS MTM with IS MTM not red: "
        + (", ".join(seats) if seats else "none")
        + ".",
        f"Engines that clear slate ${FAILURE_LINE:.0f}/day OOS MTM with IS MTM not red and peak live fit: "
        + (", ".join(slates) if slates else "none")
        + ".",
        f"Ids that beat {CONTROL_ID} on both IS and OOS MTM without worsening OOS DD >25%: {beat_s}.",
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
        f"Wednesday signal  n={N_SHORT}  lb={LB} fill=nextrth  hold-10 backstop  ${NOTIONAL:.0f}",
        "Peak live = |shares × last|. Day 10 last-RTH is always an exit if still on. "
        "Did not enter a different name into the empty slot.",
        "",
        *char_lines,
        "",
        f"{'id':<12} {'split':<4} {'entry$':>9} {'MTM$':>9} {'n':>6} {'hold':>6} {'early':>6} "
        f"{'hit':>6} {'t':>6} {'seat':>5}",
    ]
    for r in results:
        for split, ent, mtm, a, skip_a, n_a, months_s, peak_s, fskip, mean_h, n_early in (
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
                r["mean_h_is"],
                r["n_early_is"],
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
                r["mean_h_oos"],
                r["n_early_oos"],
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
                f"{r['name']:<12} {split:<4} {ent['per_day']:9.2f} {mtm['per_day']:9.2f} "
                f"{ent['n_trades']:6d} {mean_h:6.2f} {n_early:6d} "
                f"{ent['hit_rate']:6.3f} {mtm['t_stat']:6.2f} {flag:>5}"
            )
            lines.extend(_fmt_book48(mtm))
            rules_s = "+".join(r["rules"]) if r["rules"] else "hold10"
            lines.append(
                f"    entry $/day={ent['per_day']:.2f}  MTM $/day={mtm['per_day']:.2f}  "
                f"IWM alpha $/day={a:.2f} (n={n_a} skip={skip_a})  "
                f"rules={rules_s}  mean_hold={mean_h:.2f}  early_cash={n_early}  "
                f"skips={fskip}{_ci_note(mtm)}"
            )
            lines.append(
                f"    peak live |shares×last| ${peak_s:.0f}  all-sessions ${r['peak_live']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  signals={r['n_reb']}"
            )
            lines.append(f"    MTM months: {months_s}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow71_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow71_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 71",
        "",
        verdict,
        "",
        lead,
        f"Seat ${SEAT_FLOOR:.0f}: {', '.join(seats) if seats else 'none'}. "
        f"Slate ${FAILURE_LINE:.0f}: {', '.join(slates) if slates else 'none'}. "
        f"Beat id 0: {beat_s}. {abc_note}",
        "Wednesday H10 keep/cash. Same entries as Arrow 66 h10_4k. "
        "Did not replace a cashed name. Did not use an OOS month to pick a threshold. "
        "No new ingest. No Arrow 72.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 71"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
