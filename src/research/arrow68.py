"""Arrow 68 — frozen Wednesday H10 one-look on Sep–Dec 2025. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.paths import BARS_DIR, REPORTS, VIRGIN_BARS, VIRGIN_ELIGIBILITY
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
from research.arrow65 import _last_job, _make_trade, _mtm_and_peak, _rank_job
from research.book import daily_close_drawdown
from research.clock import (
    arrow68_feature_sessions,
    arrow68_score_sessions,
    feature_sessions,
    session_shift,
    tape_root,
)
from research.costs import ACCOUNT, FAILURE_LINE, TARGET_HI, TARGET_LO

ET = ZoneInfo("America/New_York")
CONTROL_ID = "wed_h10_4k"
FILL_KIND = "nextrth"
NOTIONAL = 4000.0
KEEP = False
EXPERIMENTS = ((CONTROL_ID, FILL_KIND, NOTIONAL, KEEP),)
IDS = (CONTROL_ID,)
SIGNAL_LO = date(2025, 9, 3)
SIGNAL_HI = date(2025, 12, 31)
SCORE_LO = date(2025, 9, 2)
SCORE_HI = date(2025, 12, 31)
AUG_SESSION = date(2025, 8, 1)
A66_H10_IS_MTM = 401.16
A66_H10_OOS_MTM = 260.36


def arrow68_signal_dates(feats: list[date] | None = None) -> list[date]:
    """Wednesdays 2025-09-03..2025-12-31 with 15 prior sessions on feats."""
    feats = list(feats) if feats is not None else arrow68_feature_sessions()
    out: list[date] = []
    for d in arrow68_score_sessions():
        if d.weekday() != 2:
            continue
        if d < SIGNAL_LO or d > SIGNAL_HI:
            continue
        if session_shift(d, -LB, feats) is None:
            continue
        out.append(d)
    return out


def _elig_2025(signal_dates: list[date]) -> pl.DataFrame:
    """Virgin eligibility for 2025 signal dates. Not _elig_frame (2026 study only)."""
    if not VIRGIN_ELIGIBILITY.exists():
        raise FileNotFoundError(f"missing {VIRGIN_ELIGIBILITY}")
    cols = ["symbol", "session_date", "prior_close", "prior_dollar_volume"]
    v = pl.read_parquet(VIRGIN_ELIGIBILITY)
    keep = [c for c in cols if c in v.columns]
    v = v.select(keep).filter(pl.col("session_date").is_in(list(signal_dates)))
    return v.filter(
        pl.col("prior_close").is_not_null()
        & (pl.col("prior_close") >= MIN_PX)
        & (pl.col("prior_close") <= MAX_PX)
        & (pl.col("prior_dollar_volume") >= MIN_PDV)
    )


def run_arrow68(*, workers: int | None = None) -> int:
    if tape_root(SIGNAL_LO) == BARS_DIR or tape_root(date(2026, 1, 2)) == BARS_DIR:
        raise RuntimeError("Arrow 68 must not read Lab A data/bars/")
    aug_dir = VIRGIN_BARS / AUG_SESSION.isoformat()
    if not aug_dir.exists():
        raise RuntimeError(
            "Arrow 68 lookback needs August 2025 on virgin. Run Arrow 69 first."
        )
    leftover = feature_sessions()
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    feats = arrow68_feature_sessions()
    score = arrow68_score_sessions()
    weds = arrow68_signal_dates(feats)
    print(
        f"research start mode=arrow68 workers={workers} cpu={cpu} "
        f"score={score[0]}..{score[-1]} n={len(score)} "
        f"feats={feats[0]}..{feats[-1]} n={len(feats)} "
        f"signals={len(weds)} first={weds[0] if weds else None} "
        f"sep_tape={tape_root(SIGNAL_LO)} jan_tape={tape_root(date(2026, 1, 2))}",
        flush=True,
    )
    print(
        "Frozen Wednesday H10 one-look on Sep–Dec 2025. "
        "Did not retune lookback, n, weekday, hold, ticket, or fill. "
        "Did not walk rings. Did not score 2026 signals. "
        "Lookback may read August 2025. No new ingest. No Arrow 70.",
        flush=True,
    )
    if not weds:
        raise RuntimeError("Arrow 68 has no legal Wednesday signals")
    elig = _elig_2025(weds)
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
        f"fill={FILL_KIND} ${NOTIONAL:.0f} keep={KEEP} jobs={len(jobs)}",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow68")
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

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in score
    }
    skips = 0
    partials = 0
    trades_all: list[dict] = []
    usable: list[date] = []
    for d in weds:
        picks = picks_by.get(d.isoformat()) or []
        if nres_by.get(d.isoformat(), 0) >= MIN_RESIDUAL:
            usable.append(d)
        for h in picks:
            tr, skip_fill, partial = _make_trade(
                h, FILL_KIND, NOTIONAL, KEEP, d, feats, hold=HOLD
            )
            if skip_fill:
                skips += 1
                continue
            if tr is None:
                continue
            if partial:
                partials += 1
            chunks[d.isoformat()]["trades"].setdefault(CONTROL_ID, []).append(tr)
            trades_all.append(tr)

    need: set[tuple[str, str]] = set()
    last_exit: date | None = None
    for t in trades_all:
        fill_d, exit_d = t["fill_date"], t["exit_date"]
        if last_exit is None or exit_d > last_exit:
            last_exit = exit_d
        for d in feats:
            if fill_d <= d < exit_d:
                need.add((d.isoformat(), t["symbol"]))
    last_map: dict[tuple[str, str], float] = {}
    if need:
        prog2 = Progress(len(need), "arrow68-mtm")
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

    first_signal = weds[0]
    span_end = last_exit if last_exit is not None else score[-1]
    span = [d for d in feats if first_signal <= d <= span_end]
    if not span:
        span = list(score)
    sm_ent, _, tr = _daily_and_trades(chunks, score, CONTROL_ID, usable)
    sm_ent["n_win"], sm_ent["n_loss"] = _wins_losses(tr)
    mtm_span, peak_live = _mtm_and_peak(trades_all, span, last_map)
    idx_span = {d: i for i, d in enumerate(span)}
    mtm_score = [
        mtm_span[idx_span[d]] if d in idx_span else 0.0 for d in score
    ]
    sm_mtm_score = _summarize_adv(mtm_score, tr, len(score))
    sm_mtm_span = _summarize_adv(mtm_span, tr, len(span))
    for sm in (sm_mtm_score, sm_mtm_span):
        sm["n_win"], sm["n_loss"] = sm_ent["n_win"], sm_ent["n_loss"]
        sm["n_week"] = sm_ent["n_week"]
        sm["trades_per_week"] = sm_ent["trades_per_week"]
        sm["peak_conc"] = sm_ent["peak_conc"]
        sm["mean_conc"] = sm_ent["mean_conc"]
    sm_mtm_score["daily_close_dd"] = daily_close_drawdown(mtm_score)
    sm_mtm_span["daily_close_dd"] = daily_close_drawdown(mtm_span)
    sm_mtm_score["worst_day"] = min(mtm_score) if mtm_score else 0.0
    sm_mtm_span["worst_day"] = min(mtm_span) if mtm_span else 0.0
    a_score, skip_a_score, n_a_score = _alpha(tr, score, iwm)
    a_span, skip_a_span, n_a_span = _alpha(tr, span, iwm)
    months_score = _month_lines(mtm_score, score)
    months_span = _month_lines(mtm_span, span)
    jan_exits = last_exit is not None and last_exit.year == 2026 and last_exit.month == 1
    jan_note = (
        f" Last hold exits {last_exit.isoformat()} on January 2026 virgin (not a 2026 signal)."
        if jan_exits
        else f" Last exit {last_exit.isoformat() if last_exit else 'n/a'}."
    )
    total_pnl = float(sm_ent["pnl_total"])
    mtm_per_score_n = total_pnl / len(score) if score else 0.0
    mtm_per_span_n = total_pnl / len(span) if span else 0.0
    sign_match = mtm_per_span_n > 0.0
    ci_excludes = sm_mtm_span["ci_lo"] > 0 or sm_mtm_span["ci_hi"] < 0
    ci_score_excludes = sm_mtm_score["ci_lo"] > 0 or sm_mtm_score["ci_hi"] < 0
    look_like = (
        "yes, same sign (both 2026 slices green)"
        if sign_match
        else "no, opposite sign vs 2026 Wednesday H10"
    )
    first_para = (
        f"First signal {first_signal.isoformat()} n={sm_ent['n_trades']} "
        f"MTM $/day={mtm_per_span_n:.2f} (total PnL / {len(span)} sessions "
        f"{span[0]}..{span[-1]}) and {mtm_per_score_n:.2f} "
        f"(total PnL / {len(score)} sessions 2025-09-02..2025-12-31). "
        f"Entry-attributed $/day={sm_ent['per_day']:.2f}. "
        f"Months: {months_score}. Peak live ${peak_live:.0f}. "
        f"Looks like 2026 Wednesday H10 (IS MTM +{A66_H10_IS_MTM:.2f} / "
        f"OOS MTM +{A66_H10_OOS_MTM:.2f}, both green): {look_like}."
        f"{jan_note} Truncated Sep–Dec MTM daily mean ${sm_mtm_score['per_day']:.2f} "
        f"is not total PnL / {len(score)} — January marks of the Dec 31 fill sit after 2025-12-31."
    )
    verdict = (
        "VERDICT: LOOK — not a $200 slate pass. "
        "Sep–Dec 2025 is one slice, not IS/OOS for promotion."
    )
    honesty = (
        "Frozen paper book: Wednesday signal, 15-session close-to-close vs IWM "
        "(IWM subtract is a scalar; rank = eight largest 15-session returns), "
        "short eight, fill next session last-RTH, $4,000, hold 10 from the fill session, "
        "drop a name if the exit bar is missing. Field $10–$80 PDV >= $10M ETP denylist. "
        "MTM daily equity as Arrow 65. Reused clock.py and Arrow 65 fill/MTM path. "
        "Did not retune lookback, n, weekday, hold, ticket, or fill. Did not walk rings. "
        "Did not score 2026 signals. Lookback may read August 2025. "
        "Did not treat Sep/Oct/Nov/Dec as IS/OOS. Did not drop anything after seeing a month. "
        "No new ingest. Did not touch Lab A data/bars/ or data/full/. "
        "Do not call a CI that includes 0 EV. Do not call this window a $200 slate pass. "
        "No Arrow 70."
    )
    lines = [
        "Arrow 68 — Wednesday H10 one-look on Sep–Dec 2025",
        verdict,
        first_para,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"score n={len(score)} {score[0]}..{score[-1]}  "
        f"span n={len(span)} {span[0]}..{span[-1]}  "
        f"wednesday signals={len(weds)} first={first_signal} last={weds[-1]}  "
        f"usable={len(usable)}",
        f"workers={workers} cpu_count={cpu}  "
        f"sep_tape={tape_root(SIGNAL_LO)}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"aug_on_virgin={'yes' if aug_dir.exists() else 'NO'}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"Wednesday signal last-RTH  n={N_SHORT}  lb={LB} hold={HOLD} from fill  "
        f"fill={FILL_KIND} ${NOTIONAL:.0f} keep={KEEP}",
        "close = signal last-RTH. nextrth = next session last-RTH. "
        "Peak live = |shares × last|. One frozen id. One look. Not IS/OOS.",
        "",
        f"{'id':<16} {'slice':<10} {'entry$':>9} {'MTM$':>9} {'n':>6} {'hit':>6} {'t':>6}",
        f"{CONTROL_ID:<16} {'look':<10} {sm_ent['per_day']:9.2f} {mtm_per_span_n:9.2f} "
        f"{sm_ent['n_trades']:6d} {sm_ent['hit_rate']:6.3f} {sm_mtm_span['t_stat']:6.2f}",
    ]
    lines.extend(_fmt_book48(sm_mtm_span))
    lines.append(
        f"    entry $/day={sm_ent['per_day']:.2f} (total PnL / n={len(score)} "
        f"sessions 2025-09-02..2025-12-31)  "
        f"MTM $/day={mtm_per_score_n:.2f} (total PnL / those sessions)  "
        f"MTM $/day={mtm_per_span_n:.2f} (total PnL / n={len(span)} "
        f"{span[0]}..{span[-1]})  "
        f"IWM alpha $/day={a_span:.2f} (n={n_a_span} skip={skip_a_span})  "
        f"fill={FILL_KIND} notional=${NOTIONAL:.0f} keep={KEEP}  "
        f"skips={skips} exit_partial={partials}{_ci_note(sm_mtm_span)}"
    )
    lines.append(
        f"    truncated Sep–Dec MTM daily mean ${sm_mtm_score['per_day']:.2f} "
        f"t={sm_mtm_score['t_stat']:.2f}{_ci_note(sm_mtm_score)}  "
        f"— not total PnL / {len(score)}. IWM alpha on score calendar "
        f"${a_score:.2f} (n={n_a_score} skip={skip_a_score})."
    )
    lines.append(
        f"    peak live |shares×last| ${peak_live:.0f}  fits_100k="
        f"{'yes' if peak_live <= ACCOUNT + 1e-12 else 'NO'}  "
        f"signals={len(weds)}  fill_skips={skips}  exit_partial={partials}"
    )
    lines.append(f"    MTM months (score 2025-09-02..2025-12-31): {months_score}")
    lines.append(f"    MTM months (first signal through last exit): {months_span}")
    lines.append(
        f"    2026 Wednesday H10 sign: A66 h10_4k IS MTM +{A66_H10_IS_MTM:.2f} "
        f"OOS MTM +{A66_H10_OOS_MTM:.2f}. This window MTM "
        f"{mtm_per_span_n:+.2f} (total PnL / span). Match: {'yes' if sign_match else 'no'}."
    )
    if ci_excludes:
        lines.append("    Span MTM CI excludes 0.")
    else:
        lines.append("    Span MTM CI includes 0 — not EV.")
    if ci_score_excludes:
        lines.append("    Score-window MTM CI excludes 0.")
    else:
        lines.append("    Score-window MTM CI includes 0 — not EV.")
    lines.append("    Did not call this window a $200 slate pass. No Arrow 70.")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow68_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow68_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 68",
        "",
        verdict,
        "",
        first_para,
        f"entry $/day={sm_ent['per_day']:.2f}  MTM total/score_n={mtm_per_score_n:.2f}  "
        f"MTM total/span_n={mtm_per_span_n:.2f} n={sm_ent['n_trades']}  "
        f"t_span={sm_mtm_span['t_stat']:.2f}  peak_live ${peak_live:.0f}  "
        + ("span MTM CI excludes 0" if ci_excludes else "span MTM CI includes 0 — not EV"),
        "Frozen Wednesday H10. One look. No rings. No 2026 signals. "
        "Lookback may read August 2025. No new ingest. No Arrow 70.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 68"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
