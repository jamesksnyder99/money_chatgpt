"""Arrow 70 — compounded twelve-month Wednesday H10. Size-on-equity, not a new engine."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.calendar import VIRGIN_STUDY_END
from ingest.paths import (
    BARS_DIR,
    FULL_ELIGIBILITY,
    REPORTS,
    VIRGIN_BARS,
    VIRGIN_ELIGIBILITY,
)
from ingest.progress import Progress
from research.arrow23 import _summarize_adv
from research.arrow43 import load_combined_iwm
from research.arrow44 import (
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _alpha,
    _by_sess,
    _iwm_last_close,
    _month_lines,
)
from research.arrow45 import _daily_and_trades, select_shorts
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import HOLD, LB, MIN_RESIDUAL, N_SHORT
from research.arrow65 import (
    _last_job,
    _make_trade,
    _mtm_and_peak,
    _rank_job,
    fill_session_of,
)
from research.book import daily_close_drawdown
from research.clock import (
    arrow70_feature_sessions,
    arrow70_score_sessions,
    feature_sessions,
    session_shift,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
FLAT_ID = "flat_4k"
COMP_ID = "comp_4k"
FILL_KIND = "nextrth"
BASE_TICKET = 4000.0
START_EQUITY = 100_000.0
KEEP = False
IDS = (FLAT_ID, COMP_ID)
SIGNAL_LO = date(2025, 9, 3)
SCORE_LO = date(2025, 9, 2)
SCORE_HI = date(2026, 8, 31)
AUG_SESSION = date(2025, 8, 1)
A68_SEP_DAY = -553.56
A68_OCT_DAY = 878.51


def compound_ticket(
    equity: float, base: float = BASE_TICKET, start: float = START_EQUITY
) -> float:
    """New-fill ticket. Clip at $0 if equity <= 0. Do not add cash."""
    if equity <= 0:
        return 0.0
    return base * (equity / start)


def flat_ticket() -> float:
    return BASE_TICKET


def iso_week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y:04d}-W{w:02d}"


def year_months() -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = 2025, 9
    while (y, m) <= (2026, 8):
        out.append((y, m))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def crosses_seam(fill_d: date, exit_d: date) -> bool:
    """Hold spans virgin study end into full tape. Do not drop."""
    return fill_d <= VIRGIN_STUDY_END < exit_d


def arrow70_signal_dates(feats: list[date] | None = None) -> list[date]:
    """Wednesdays 2025-09-03..2026-08 whose fill exists and 15 prior sessions exist."""
    feats = list(feats) if feats is not None else arrow70_feature_sessions()
    out: list[date] = []
    for d in arrow70_score_sessions():
        if d.weekday() != 2:
            continue
        if d < SIGNAL_LO or d > SCORE_HI:
            continue
        if session_shift(d, -LB, feats) is None:
            continue
        if fill_session_of(d, FILL_KIND, feats) is None:
            continue
        out.append(d)
    return out


def _elig_year(signal_dates: list[date]) -> pl.DataFrame:
    """Virgin through May 2026, full Jun–Aug 2026. Not leftover _elig_frame."""
    cols = ["symbol", "session_date", "prior_close", "prior_dollar_volume"]
    frames: list[pl.DataFrame] = []
    v_dates = [d for d in signal_dates if d <= VIRGIN_STUDY_END]
    f_dates = [d for d in signal_dates if d > VIRGIN_STUDY_END]
    if v_dates:
        if not VIRGIN_ELIGIBILITY.exists():
            raise FileNotFoundError(f"missing {VIRGIN_ELIGIBILITY}")
        v = pl.read_parquet(VIRGIN_ELIGIBILITY)
        keep = [c for c in cols if c in v.columns]
        frames.append(v.select(keep).filter(pl.col("session_date").is_in(v_dates)))
    if f_dates:
        if not FULL_ELIGIBILITY.exists():
            raise FileNotFoundError(f"missing {FULL_ELIGIBILITY}")
        f = pl.read_parquet(FULL_ELIGIBILITY)
        keep = [c for c in cols if c in f.columns]
        frames.append(f.select(keep).filter(pl.col("session_date").is_in(f_dates)))
    if not frames:
        raise FileNotFoundError("missing virgin/full eligibility for Arrow 70")
    elig = pl.concat(frames, how="diagonal_relaxed")
    return elig.filter(
        pl.col("prior_close").is_not_null()
        & (pl.col("prior_close") >= MIN_PX)
        & (pl.col("prior_close") <= MAX_PX)
        & (pl.col("prior_dollar_volume") >= MIN_PDV)
    )


def _month_slice(
    daily: list[float], sessions: list[date], year: int, month: int
) -> tuple[list[date], list[float]]:
    days: list[date] = []
    vals: list[float] = []
    for d, v in zip(sessions, daily):
        if d.year == year and d.month == month:
            days.append(d)
            vals.append(float(v))
    return days, vals


def _week_groups(sessions: list[date]) -> list[tuple[str, list[date]]]:
    by: dict[str, list[date]] = {}
    order: list[str] = []
    for d in sessions:
        k = iso_week_key(d)
        if k not in by:
            by[k] = []
            order.append(k)
        by[k].append(d)
    return [(k, by[k]) for k in order]


def run_arrow70(*, workers: int | None = None) -> int:
    if tape_root(SIGNAL_LO) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 70 must not read Lab A data/bars/")
    aug_dir = VIRGIN_BARS / AUG_SESSION.isoformat()
    if not aug_dir.exists():
        raise RuntimeError("Arrow 70 lookback needs August 2025 on virgin.")
    leftover = feature_sessions()
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    feats = arrow70_feature_sessions()
    score = arrow70_score_sessions()
    weds = arrow70_signal_dates(feats)
    print(
        f"research start mode=arrow70 workers={workers} cpu={cpu} "
        f"score={score[0]}..{score[-1]} n={len(score)} "
        f"feats={feats[0]}..{feats[-1]} n={len(feats)} "
        f"signals={len(weds)} first={weds[0] if weds else None} "
        f"sep_tape={tape_root(SIGNAL_LO)} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "Frozen Wednesday H10 twelve-month size-on-equity. "
        "Did not retune rank, n, weekday, hold, fill, or base ticket. "
        "Did not walk rings. Did not use an OOS month to pick a threshold. "
        "No new ingest. No Arrow 71.",
        flush=True,
    )
    if not weds:
        raise RuntimeError("Arrow 70 has no legal Wednesday signals")
    elig = _elig_year(weds)
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    for d in weds:
        look15 = session_shift(d, -LB, feats)
        i_l15 = _iwm_last_close(iwm, look15) if look15 is not None else None
        i1 = _iwm_last_close(iwm, d)
        jobs.append(
            (
                d.isoformat(),
                look15.isoformat() if look15 is not None else None,
                by.get(d.isoformat(), []),
                i_l15[1] if i_l15 else None,
                i1[1] if i1 else None,
            )
        )
    print(
        f"eligibility prior_close [${MIN_PX:.0f},${MAX_PX:.0f}] PDV>=${MIN_PDV:.0f} "
        f"Wednesday only n={N_SHORT} lb={LB} hold={HOLD} from fill  "
        f"fill={FILL_KIND} base=${BASE_TICKET:.0f} start_eq=${START_EQUITY:.0f} "
        f"jobs={len(jobs)}",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow70")
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

    need: set[tuple[str, str]] = set()
    for d in weds:
        fill_d = fill_session_of(d, FILL_KIND, feats)
        if fill_d is None:
            continue
        target = session_shift(fill_d, HOLD, feats)
        if target is None:
            continue
        for h in picks_by.get(d.isoformat()) or []:
            for x in feats:
                if fill_d <= x < target:
                    need.add((x.isoformat(), h["symbol"]))
    last_map: dict[tuple[str, str], float] = {}
    if need:
        prog2 = Progress(len(need), "arrow70-mtm")
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

    chunks_flat: dict[str, dict] = {
        d.isoformat(): {"trades": {FLAT_ID: []}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in score
    }
    flat_trades: list[dict] = []
    flat_skips = 0
    usable: list[date] = []
    for d in weds:
        picks = picks_by.get(d.isoformat()) or []
        if nres_by.get(d.isoformat(), 0) >= MIN_RESIDUAL:
            usable.append(d)
        for h in picks:
            tr, skip_fill, _partial = _make_trade(
                h, FILL_KIND, BASE_TICKET, KEEP, d, feats, hold=HOLD
            )
            if skip_fill:
                flat_skips += 1
                continue
            if tr is None:
                continue
            tr["ticket"] = BASE_TICKET
            tr["seam"] = crosses_seam(tr["fill_date"], tr["exit_date"])
            chunks_flat[d.isoformat()]["trades"][FLAT_ID].append(tr)
            flat_trades.append(tr)

    mtm_flat, peak_flat = _mtm_and_peak(flat_trades, score, last_map)
    sep_days, sep_vals = _month_slice(mtm_flat, score, 2025, 9)
    oct_days, oct_vals = _month_slice(mtm_flat, score, 2025, 10)
    sep_day = (sum(sep_vals) / len(sep_vals)) if sep_vals else 0.0
    oct_day = (sum(oct_vals) / len(oct_vals)) if oct_vals else 0.0
    oct_empty = (not oct_vals) or abs(oct_day) < 1e-9
    sep_green = sep_day >= 0.0
    seam_line = (
        f"Id 0 Sep MTM $/day={sep_day:.2f} vs Arrow 68 {A68_SEP_DAY:.2f} "
        f"(hole={'yes' if sep_day < 0 else 'NO'}). "
        f"Oct MTM $/day={oct_day:.2f} vs Arrow 68 {A68_OCT_DAY:.2f} "
        f"(fat={'yes' if oct_day > 0 else 'NO'} n={len(oct_days)})."
    )
    print(seam_line, flush=True)
    if sep_green and oct_empty:
        text = (
            "Arrow 70 — compounded twelve-month Wednesday H10\n"
            "VERDICT: FAIL — September is green and October is empty. "
            "Seam is broken. Did not score compound.\n"
            f"{seam_line}\n"
            "No Arrow 71.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow70_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    chunks_comp: dict[str, dict] = {
        d.isoformat(): {"trades": {COMP_ID: []}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in score
    }
    comp_trades: list[dict] = []
    comp_skips = 0
    tickets: dict[str, float] = {}
    equity_at_signal: dict[str, float] = {}
    for d in weds:
        if not comp_trades:
            equity = START_EQUITY
        else:
            sess_to_d = [s for s in score if s <= d]
            daily_tmp, _ = _mtm_and_peak(comp_trades, sess_to_d, last_map)
            equity = START_EQUITY + sum(daily_tmp)
        ticket = compound_ticket(equity)
        tickets[d.isoformat()] = ticket
        equity_at_signal[d.isoformat()] = equity
        picks = picks_by.get(d.isoformat()) or []
        if ticket <= 0:
            continue
        for h in picks:
            tr, skip_fill, _partial = _make_trade(
                h, FILL_KIND, ticket, KEEP, d, feats, hold=HOLD
            )
            if skip_fill:
                comp_skips += 1
                continue
            if tr is None:
                continue
            tr["ticket"] = ticket
            tr["seam"] = crosses_seam(tr["fill_date"], tr["exit_date"])
            chunks_comp[d.isoformat()]["trades"][COMP_ID].append(tr)
            comp_trades.append(tr)

    mtm_comp, peak_comp = _mtm_and_peak(comp_trades, score, last_map)
    sm_ent_flat, _, tr_flat = _daily_and_trades(chunks_flat, score, FLAT_ID, usable)
    sm_ent_comp, _, tr_comp = _daily_and_trades(chunks_comp, score, COMP_ID, usable)
    sm_ent_flat["n_win"], sm_ent_flat["n_loss"] = _wins_losses(tr_flat)
    sm_ent_comp["n_win"], sm_ent_comp["n_loss"] = _wins_losses(tr_comp)
    sm_mtm_flat = _summarize_adv(mtm_flat, tr_flat, len(score))
    sm_mtm_comp = _summarize_adv(mtm_comp, tr_comp, len(score))
    for sm, ent, daily in (
        (sm_mtm_flat, sm_ent_flat, mtm_flat),
        (sm_mtm_comp, sm_ent_comp, mtm_comp),
    ):
        sm["n_win"], sm["n_loss"] = ent["n_win"], ent["n_loss"]
        sm["n_week"] = ent["n_week"]
        sm["trades_per_week"] = ent["trades_per_week"]
        sm["peak_conc"] = ent["peak_conc"]
        sm["mean_conc"] = ent["mean_conc"]
        sm["daily_close_dd"] = daily_close_drawdown(daily)
        sm["worst_day"] = min(daily) if daily else 0.0
    a_flat, skip_a, n_a = _alpha(tr_flat, score, iwm)
    end_flat = START_EQUITY + sum(mtm_flat)
    end_comp = START_EQUITY + sum(mtm_comp)
    n_seam_flat = sum(1 for t in flat_trades if t.get("seam"))
    n_seam_comp = sum(1 for t in comp_trades if t.get("seam"))

    fall = [d for d in score if d.year == 2025]
    y2026 = [d for d in score if d.year == 2026]
    fall_i = [i for i, d in enumerate(score) if d.year == 2025]
    y2026_i = [i for i, d in enumerate(score) if d.year == 2026]
    fall_mtm_f = [mtm_flat[i] for i in fall_i]
    y2026_mtm_f = [mtm_flat[i] for i in y2026_i]
    fall_mtm_c = [mtm_comp[i] for i in fall_i]
    y2026_mtm_c = [mtm_comp[i] for i in y2026_i]
    fall_day_f = (sum(fall_mtm_f) / len(fall)) if fall else 0.0
    y2026_day_f = (sum(y2026_mtm_f) / len(y2026)) if y2026 else 0.0
    fall_day_c = (sum(fall_mtm_c) / len(fall)) if fall else 0.0
    y2026_day_c = (sum(y2026_mtm_c) / len(y2026)) if y2026 else 0.0

    month_rows: list[str] = [
        f"{'month':<8} {'n':>4} {'flat_MTM$':>12} {'flat$/d':>10} {'comp_MTM$':>12} "
        f"{'comp$/d':>10} {'end_eq_1':>12} {'peak_live_f':>12} {'peak_live_c':>12}"
    ]
    eq_f = START_EQUITY
    eq_c = START_EQUITY
    for y, m in year_months():
        days_m, vals_f = _month_slice(mtm_flat, score, y, m)
        _, vals_c = _month_slice(mtm_comp, score, y, m)
        n_m = len(days_m)
        sum_f = sum(vals_f)
        sum_c = sum(vals_c)
        eq_f += sum_f
        eq_c += sum_c
        per_f = (sum_f / n_m) if n_m else 0.0
        per_c = (sum_c / n_m) if n_m else 0.0
        _, peak_mf = _mtm_and_peak(flat_trades, days_m, last_map) if days_m else (None, 0.0)
        _, peak_mc = _mtm_and_peak(comp_trades, days_m, last_map) if days_m else (None, 0.0)
        month_rows.append(
            f"{y:04d}-{m:02d} {n_m:4d} {sum_f:12.2f} {per_f:10.2f} {sum_c:12.2f} "
            f"{per_c:10.2f} {eq_c:12.2f} {peak_mf:12.0f} {peak_mc:12.0f}"
        )

    week_rows: list[str] = [
        "ISO weeks Monday–Sunday that contain a NYSE session in 2025-09-02..2026-08-31. "
        "Not NYSE weeks ending Friday.",
        f"{'week':<10} {'n':>4} {'MTM$':>12} {'end_eq_1':>12}",
    ]
    idx = {d: i for i, d in enumerate(score)}
    eq_w = START_EQUITY
    for key, days_w in _week_groups(score):
        s = sum(mtm_comp[idx[d]] for d in days_w)
        eq_w += s
        week_rows.append(f" {key:<9} {len(days_w):4d} {s:12.2f} {eq_w:12.2f}")

    ci_flat = sm_mtm_flat["ci_lo"] > 0 or sm_mtm_flat["ci_hi"] < 0
    ci_comp = sm_mtm_comp["ci_lo"] > 0 or sm_mtm_comp["ci_hi"] < 0
    hole = sep_day < 0
    first_para = (
        f"Start equity ${START_EQUITY:.0f} on 2025-09-02. "
        f"Compound end equity ${end_comp:.0f}. Flat end equity ${end_flat:.0f}. "
        f"Flat-year MTM $/day={sm_mtm_flat['per_day']:.2f} vs compound-year "
        f"MTM $/day={sm_mtm_comp['per_day']:.2f} (total / {len(score)} sessions "
        f"2025-09-02..2026-08-31). "
        f"Max MTM DD flat ${sm_mtm_flat['daily_close_dd']:.2f} compound "
        f"${sm_mtm_comp['daily_close_dd']:.2f}. "
        f"Fall 2025 still has the September hole: {'yes' if hole else 'NO'} "
        f"(Sep {sep_day:.2f}/day, Oct {oct_day:.2f}/day). {seam_line}"
    )
    verdict = (
        "VERDICT: LOOK — not a $200 slate pass. "
        "This year is size-on-equity of the frozen book, not a new IS/OOS split. "
        "Jan–Aug 2026 already had that look."
    )
    honesty = (
        "Frozen paper book: Wednesday signal, eight largest 15-session close-to-close "
        "returns (IWM subtract is a scalar), fill next session last-RTH, hold 10, "
        "drop missing exits. Field $10–$80 PDV >= $10M ETP denylist. "
        f"Start equity ${START_EQUITY:.0f} on 2025-09-02. "
        "Id 0 flat $4,000 every signal. Id 1 ticket = 4000 × (MTM equity at signal "
        "last-RTH before new fills / 100000). Did not resize names already on. "
        "Clipped ticket at $0 if equity <= 0. Did not add cash. Did not withdraw. "
        "Did not retune rank, n, weekday, hold, fill, or base ticket. Did not walk rings. "
        "Did not treat this year as a new IS/OOS split. "
        "Did not drop a month after seeing it. Did not use an OOS month to pick a threshold. "
        "A hold may cross the virgin/full seam; did not drop it. "
        "IWM alpha is flat $4k only. "
        "No new ingest. Did not touch Lab A data/bars/. "
        "Do not call a CI that includes 0 EV. Do not call the year a $200 slate pass. "
        "No Arrow 71."
    )
    lines = [
        "Arrow 70 — compounded twelve-month Wednesday H10",
        verdict,
        first_para,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day  start_equity={START_EQUITY:.0f}",
        f"score n={len(score)} {score[0]}..{score[-1]}  "
        f"wednesday signals={len(weds)} first={weds[0]} last={weds[-1]}  "
        f"usable={len(usable)}",
        f"workers={workers} cpu_count={cpu}  "
        f"sep_tape={tape_root(SIGNAL_LO)}  "
        f"may_tape={tape_root(date(2026, 5, 27))}  "
        f"jun_tape={tape_root(date(2026, 6, 1))}  "
        f"jul_tape={tape_root(date(2026, 7, 1))}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"Wednesday signal  n={N_SHORT}  lb={LB} hold={HOLD} from fill  fill={FILL_KIND}  "
        f"base ${BASE_TICKET:.0f}",
        f"holds crossing virgin/full seam: flat n={n_seam_flat} compound n={n_seam_comp} "
        f"(did not drop). Peak live = |shares × last|.",
        "",
        "2025-09..12 (Arrow 68 window, not a new IS) vs 2026-01..08 (Arrow 65/66 window, not a new OOS).",
        f"  fall 2025 n={len(fall)} flat MTM $/day={fall_day_f:.2f} compound $/day={fall_day_c:.2f}",
        f"  2026 Jan–Aug n={len(y2026)} flat MTM $/day={y2026_day_f:.2f} compound $/day={y2026_day_c:.2f}",
        "",
        "12 months 2025-09 through 2026-08. end_eq_1 is compound equity after that month.",
        *month_rows,
        "",
        *week_rows,
        "",
        f"start_equity={START_EQUITY:.2f}  end_equity_flat={end_flat:.2f}  "
        f"end_equity_comp={end_comp:.2f}",
        f"total MTM$ flat={sum(mtm_flat):.2f}  compound={sum(mtm_comp):.2f}",
        f"MTM $/day flat={sm_mtm_flat['per_day']:.2f}  compound={sm_mtm_comp['per_day']:.2f}  "
        f"(total / n={len(score)} NYSE sessions 2025-09-02..2026-08-31)",
        f"peak live flat ${peak_flat:.0f}  compound ${peak_comp:.0f}  "
        f"fits_100k_flat={'yes' if peak_flat <= ACCOUNT + 1e-12 else 'NO'}  "
        f"fits_100k_comp={'yes' if peak_comp <= ACCOUNT + 1e-12 else 'NO'}",
        f"IWM alpha $/day flat only={a_flat:.2f} (n={n_a} skip={skip_a}). "
        "Did not pretend a growing short of IWM.",
        "",
        f"{'id':<12} {'entry$':>9} {'MTM$':>9} {'n':>6} {'hit':>6} {'t':>6}",
        f"{FLAT_ID:<12} {sm_ent_flat['per_day']:9.2f} {sm_mtm_flat['per_day']:9.2f} "
        f"{sm_ent_flat['n_trades']:6d} {sm_ent_flat['hit_rate']:6.3f} {sm_mtm_flat['t_stat']:6.2f}",
    ]
    lines.extend(_fmt_book48(sm_mtm_flat))
    lines.append(
        f"    entry $/day={sm_ent_flat['per_day']:.2f}  MTM $/day={sm_mtm_flat['per_day']:.2f}  "
        f"IWM alpha $/day={a_flat:.2f} (n={n_a} skip={skip_a})  "
        f"ticket=${BASE_TICKET:.0f} always  skips={flat_skips}  "
        f"peak live ${peak_flat:.0f}{_ci_note(sm_mtm_flat)}"
    )
    lines.append(
        f"{COMP_ID:<12} {sm_ent_comp['per_day']:9.2f} {sm_mtm_comp['per_day']:9.2f} "
        f"{sm_ent_comp['n_trades']:6d} {sm_ent_comp['hit_rate']:6.3f} {sm_mtm_comp['t_stat']:6.2f}"
    )
    lines.extend(_fmt_book48(sm_mtm_comp))
    first_t = tickets.get(weds[0].isoformat(), BASE_TICKET) if weds else BASE_TICKET
    later = next((tickets[d.isoformat()] for d in weds[1:] if abs(tickets[d.isoformat()] - BASE_TICKET) > 1e-9), None)
    later_s = f"{later:.2f}" if later is not None else "n/a (equity stayed $100k)"
    lines.append(
        f"    entry $/day={sm_ent_comp['per_day']:.2f}  MTM $/day={sm_mtm_comp['per_day']:.2f}  "
        f"ticket at first signal ${first_t:.2f}  later Wednesday ticket example ${later_s}  "
        f"skips={comp_skips}  peak live ${peak_comp:.0f}{_ci_note(sm_mtm_comp)}"
    )
    lines.append(f"    MTM months flat: {_month_lines(mtm_flat, score)}")
    lines.append(f"    MTM months compound: {_month_lines(mtm_comp, score)}")
    if ci_flat:
        lines.append("    Flat MTM CI excludes 0.")
    else:
        lines.append("    Flat MTM CI includes 0 — not EV.")
    if ci_comp:
        lines.append("    Compound MTM CI excludes 0.")
    else:
        lines.append("    Compound MTM CI includes 0 — not EV.")
    lines.append("    Did not call the year a $200 slate pass. No Arrow 71.")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow70_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow70_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 70",
        "",
        verdict,
        "",
        first_para,
        f"flat MTM $/day={sm_mtm_flat['per_day']:.2f} n={sm_ent_flat['n_trades']}  "
        f"compound MTM $/day={sm_mtm_comp['per_day']:.2f} n={sm_ent_comp['n_trades']}  "
        f"end_eq ${end_comp:.0f}  peak_live_f ${peak_flat:.0f} peak_live_c ${peak_comp:.0f}  "
        + ("flat MTM CI excludes 0" if ci_flat else "flat MTM CI includes 0 — not EV"),
        "Frozen Wednesday H10 size-on-equity. No rings. No new IS/OOS. "
        "No new ingest. No Arrow 71.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 70"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
