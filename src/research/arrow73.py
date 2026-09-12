"""Arrow 73 — IWM-up skip, one-look Sep–Dec 2025. Two frozen books. Short only."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, FULL_BARS, REPORTS, VIRGIN_BARS
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
from research.arrow68 import (
    AUG_SESSION,
    SIGNAL_LO,
    _elig_2025,
    arrow68_signal_dates,
)
from research.arrow72 import iwm_lookback, wednesday_exists
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
ALWAYS_ID = "always"
UP_ID = "iwm_up"
FILL_KIND = "nextrth"
NOTIONAL = 4000.0
KEEP = False
EXPERIMENTS = (
    (ALWAYS_ID, "always"),
    (UP_ID, "iwm_up"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)
A68_SEP_DAY = -553.56
A68_OCT_DAY = 878.51
A68_DEC_DAY = -190.66


def run_arrow73(*, workers: int | None = None) -> int:
    if tape_root(SIGNAL_LO) == BARS_DIR or tape_root(date(2026, 1, 2)) == BARS_DIR:
        raise RuntimeError("Arrow 73 must not read Lab A data/bars/")
    if tape_root(SIGNAL_LO) == FULL_BARS:
        raise RuntimeError("Arrow 73 must not read data/full/")
    aug_dir = VIRGIN_BARS / AUG_SESSION.isoformat()
    if not aug_dir.exists():
        raise RuntimeError("Arrow 73 lookback needs August 2025 on virgin.")
    leftover = feature_sessions()
    if leftover[0] != date(2025, 12, 17):
        raise RuntimeError("leftover feature_sessions() lookback drifted")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    feats = arrow68_feature_sessions()
    score = arrow68_score_sessions()
    weds = arrow68_signal_dates(feats)
    print(
        f"research start mode=arrow73 workers={workers} cpu={cpu} "
        f"score={score[0]}..{score[-1]} n={len(score)} "
        f"feats={feats[0]}..{feats[-1]} n={len(feats)} "
        f"signals={len(weds)} first={weds[0] if weds else None} "
        f"sep_tape={tape_root(SIGNAL_LO)} jan_tape={tape_root(date(2026, 1, 2))}",
        flush=True,
    )
    print(
        "IWM-up skip, one-look Sep–Dec 2025. Two frozen books. "
        "Did not retune. Did not invent a new cutoff. Did not walk width/crowd/vol. "
        "Did not score 2026 signals. No new ingest. No Arrow 74.",
        flush=True,
    )
    if not weds:
        raise RuntimeError("Arrow 73 has no legal Wednesday signals")
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
    prog = Progress(len(jobs), "arrow73")
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
    feat_by: dict[str, dict] = {}
    for d in weds:
        rec = recs.get(d.isoformat()) or {}
        nres_by[d.isoformat()] = int(rec.get("n_res") or 0)
        iwm_15, _ivol = iwm_lookback(iwm, d, feats, LB)
        feat_by[d.isoformat()] = {"iwm_15": iwm_15}
        rows = list(rec.get("rows") or [])
        if (rec.get("n_res") or 0) < MIN_RESIDUAL:
            picks_by[d.isoformat()] = []
            continue
        picks_by[d.isoformat()] = select_shorts(rows, N_SHORT, None)

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in score
    }
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    usable: dict[str, list[date]] = {k: [] for k in IDS}
    skips: dict[str, int] = {k: 0 for k in IDS}

    for d in weds:
        picks = picks_by.get(d.isoformat()) or []
        if nres_by.get(d.isoformat(), 0) >= MIN_RESIDUAL:
            usable[ALWAYS_ID].append(d)
            if wednesday_exists("iwm_up", feat_by.get(d.isoformat()), None):
                usable[UP_ID].append(d)
        for h in picks:
            tr, skip_fill, _partial = _make_trade(
                h, FILL_KIND, NOTIONAL, KEEP, d, feats, hold=HOLD
            )
            if skip_fill:
                skips[ALWAYS_ID] += 1
                if d in usable[UP_ID]:
                    skips[UP_ID] += 1
                continue
            if tr is None:
                continue
            chunks[d.isoformat()]["trades"].setdefault(ALWAYS_ID, []).append(tr)
            trades_all[ALWAYS_ID].append(tr)
            if d in usable[UP_ID]:
                copy = dict(tr)
                chunks[d.isoformat()]["trades"].setdefault(UP_ID, []).append(copy)
                trades_all[UP_ID].append(copy)

    need: set[tuple[str, str]] = set()
    last_exit_by: dict[str, date | None] = {k: None for k in IDS}
    for name, trs in trades_all.items():
        for t in trs:
            fill_d, exit_d = t["fill_date"], t["exit_date"]
            if last_exit_by[name] is None or exit_d > last_exit_by[name]:
                last_exit_by[name] = exit_d
            for x in feats:
                if fill_d <= x < exit_d:
                    need.add((x.isoformat(), t["symbol"]))
    last_map: dict[tuple[str, str], float] = {}
    if need:
        prog2 = Progress(len(need), "arrow73-mtm")
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

    def _pack(name: str) -> dict:
        trs = trades_all[name]
        weeks = usable[name]
        first = weeks[0] if weeks else weds[0]
        last_ex = last_exit_by[name] if last_exit_by[name] is not None else score[-1]
        span = [d for d in feats if first <= d <= last_ex]
        if not span:
            span = list(score)
        sm_ent, _, tr = _daily_and_trades(chunks, score, name, weeks)
        sm_ent["n_win"], sm_ent["n_loss"] = _wins_losses(tr)
        mtm_span, peak = _mtm_and_peak(trs, span, last_map)
        idx_span = {d: i for i, d in enumerate(span)}
        mtm_score = [mtm_span[idx_span[d]] if d in idx_span else 0.0 for d in score]
        sm_score = _summarize_adv(mtm_score, tr, len(score))
        sm_span = _summarize_adv(mtm_span, tr, len(span))
        for sm in (sm_score, sm_span):
            sm["n_win"], sm["n_loss"] = sm_ent["n_win"], sm_ent["n_loss"]
            sm["n_week"] = sm_ent["n_week"]
            sm["trades_per_week"] = sm_ent["trades_per_week"]
            sm["peak_conc"] = sm_ent["peak_conc"]
            sm["mean_conc"] = sm_ent["mean_conc"]
        sm_score["daily_close_dd"] = daily_close_drawdown(mtm_score)
        sm_span["daily_close_dd"] = daily_close_drawdown(mtm_span)
        sm_score["worst_day"] = min(mtm_score) if mtm_score else 0.0
        sm_span["worst_day"] = min(mtm_span) if mtm_span else 0.0
        a_span, skip_a, n_a = _alpha(tr, span, iwm)
        total = float(sm_ent["pnl_total"])
        return {
            "name": name,
            "ent": sm_ent,
            "tr": tr,
            "mtm_score": sm_score,
            "mtm_span": sm_span,
            "mtm_score_days": mtm_score,
            "span": span,
            "peak": peak,
            "total": total,
            "per_score": total / len(score) if score else 0.0,
            "per_span": total / len(span) if span else 0.0,
            "a_span": a_span,
            "skip_a": skip_a,
            "n_a": n_a,
            "months_score": _month_lines(mtm_score, score),
            "months_span": _month_lines(mtm_span, span),
            "n_weds": len(weeks),
            "n_sat": len(usable[ALWAYS_ID]) - len(weeks) if name != ALWAYS_ID else 0,
            "last_exit": last_ex,
            "first": first,
            "skips": skips[name],
        }

    always = _pack(ALWAYS_ID)
    sep_days = [v for d, v in zip(score, always["mtm_score_days"]) if d.year == 2025 and d.month == 9]
    oct_days = [v for d, v in zip(score, always["mtm_score_days"]) if d.year == 2025 and d.month == 10]
    sep_day = (sum(sep_days) / len(sep_days)) if sep_days else 0.0
    oct_day = (sum(oct_days) / len(oct_days)) if oct_days else 0.0
    oct_empty = (not oct_days) or abs(oct_day) < 1e-9
    seam_line = (
        f"Id 0 Sep MTM $/day={sep_day:.2f} vs Arrow 68 {A68_SEP_DAY:.2f} "
        f"(hole={'yes' if sep_day < 0 else 'NO'}). "
        f"Oct MTM $/day={oct_day:.2f} vs Arrow 68 {A68_OCT_DAY:.2f} "
        f"(fat={'yes' if oct_day > 0 else 'NO'} n={len(oct_days)})."
    )
    print(seam_line, flush=True)
    if sep_day >= 0 and oct_empty:
        text = (
            "Arrow 73 — IWM-up skip, one-look Sep–Dec 2025\n"
            "VERDICT: FAIL — September is green and October is empty. "
            "Seam is broken. Did not score iwm_up.\n"
            f"{seam_line}\n"
            "No Arrow 74.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow73_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    up = _pack(UP_ID)

    def _month_day(pack: dict, month: int) -> float:
        xs = [
            v
            for d, v in zip(score, pack["mtm_score_days"])
            if d.year == 2025 and d.month == month
        ]
        return (sum(xs) / len(xs)) if xs else 0.0

    sep_a, sep_u = _month_day(always, 9), _month_day(up, 9)
    oct_a, oct_u = _month_day(always, 10), _month_day(up, 10)
    nov_a, nov_u = _month_day(always, 11), _month_day(up, 11)
    dec_a, dec_u = _month_day(always, 12), _month_day(up, 12)
    cuts_total = up["total"] + 1e-12 < always["total"]
    sep_less_red = sep_u > sep_a + 1e-12
    dec_less_red = dec_u > dec_a + 1e-12
    if cuts_total and not (sep_less_red or dec_less_red):
        follow = (
            "Parametric follow-up is not on the table: iwm_up cut total dollars "
            "and did not make September or December less red."
        )
    elif sep_less_red or dec_less_red:
        follow = (
            "Parametric follow-up is on the table only as a later look: "
            "iwm_up moved a red month, but this window is not IS/OOS and not a slate pass."
        )
    else:
        follow = (
            "Parametric follow-up is not on the table from this look: "
            "iwm_up did not cut September/December redness."
        )
    n0 = len(usable[ALWAYS_ID])
    n1 = len(usable[UP_ID])
    first_para = (
        f"Id 1 sat out {n0 - n1}/{n0} Wednesdays (kept {n1}). "
        f"September always {sep_a:.2f} vs iwm_up {sep_u:.2f} "
        f"(less red={'yes' if sep_less_red else 'no'}). "
        f"October always {oct_a:.2f} vs iwm_up {oct_u:.2f}. "
        f"December always {dec_a:.2f} vs iwm_up {dec_u:.2f} "
        f"(less red={'yes' if dec_less_red else 'no'}). "
        f"Total MTM$ always {always['total']:.2f} vs iwm_up {up['total']:.2f} "
        f"(cut={'yes' if cuts_total else 'no'}). {follow} {seam_line}"
    )
    verdict = (
        "VERDICT: LOOK — not a $200 slate pass. "
        "Sep–Dec 2025 is one slice, not IS/OOS for promotion."
    )
    honesty = (
        "Two frozen books. Parent: Wednesday H10, every Wednesday, next last-RTH, $4,000, hold 10. "
        "Skip: same, but no new fills on a Wednesday whose IWM 15-session close-to-close return is < 0. "
        "Names already on still ride to day 10. Rank is still the eight largest 15-session name returns. "
        "Field $10–$80 PDV >= $10M ETP denylist. MTM as Arrow 65. "
        "Did not retune. Did not invent a new cutoff. Did not walk width/crowd/vol. "
        "Did not mix 2026 signals. Lookback may read August 2025. "
        "Did not treat Sep/Oct/Nov/Dec as IS/OOS. Did not drop a month after seeing it. "
        "No new ingest. Did not touch Lab A data/bars/ or data/full/. "
        "Do not call a CI that includes 0 EV. Do not call this window a $200 slate pass. "
        "No Arrow 74."
    )
    lines = [
        "Arrow 73 — IWM-up skip, one-look Sep–Dec 2025",
        verdict,
        first_para,
        honesty,
        "Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar volume; "
        "IWM = iShares Russell 2000 ETF; RTH = regular trading hours; EV = expected value; "
        "SSR = Short Sale Restriction; CI = confidence interval; MTM = mark-to-market.",
        f"account={ACCOUNT:.0f}  slate_floor={FAILURE_LINE:.0f}/day  "
        f"target={TARGET_LO:.0f}-{TARGET_HI:.0f}/day",
        f"score n={len(score)} {score[0]}..{score[-1]}  "
        f"wednesday signals={len(weds)} first={weds[0]} last={weds[-1]}  "
        f"always usable={n0} iwm_up usable={n1} sat_out={n0 - n1}",
        f"workers={workers} cpu_count={cpu}  "
        f"sep_tape={tape_root(SIGNAL_LO)}  jan_tape={tape_root(date(2026, 1, 2))}  "
        f"aug_on_virgin={'yes' if aug_dir.exists() else 'NO'}",
        f"eligibility: prior_close [${MIN_PX:.0f}, ${MAX_PX:.0f}], PDV >= ${MIN_PDV:.0f}  "
        f"Wednesday signal  n={N_SHORT}  lb={LB} hold={HOLD} from fill  "
        f"fill={FILL_KIND} ${NOTIONAL:.0f}",
        "Peak live = |shares × last|. Skipped Wednesday = no new fills that week. "
        "Two ids only. One look. Not IS/OOS.",
        "",
        f"{'id':<12} {'slice':<10} {'entry$':>9} {'MTM$':>9} {'n':>6} {'weds':>5} {'sat':>4} "
        f"{'hit':>6} {'t':>6}",
    ]
    for pack in (always, up):
        sm_span = pack["mtm_span"]
        sm_ent = pack["ent"]
        lines.append(
            f"{pack['name']:<12} {'look':<10} {sm_ent['per_day']:9.2f} {pack['per_span']:9.2f} "
            f"{sm_ent['n_trades']:6d} {pack['n_weds']:5d} {pack['n_sat']:4d} "
            f"{sm_ent['hit_rate']:6.3f} {sm_span['t_stat']:6.2f}"
        )
        lines.extend(_fmt_book48(sm_span))
        jan_note = ""
        if pack["last_exit"].year == 2026 and pack["last_exit"].month == 1:
            jan_note = (
                f"  last hold exits {pack['last_exit']} on January 2026 virgin "
                "(not a 2026 signal)."
            )
        lines.append(
            f"    entry $/day={sm_ent['per_day']:.2f} (total PnL / n={len(score)} "
            f"sessions 2025-09-02..2025-12-31)  "
            f"MTM $/day={pack['per_score']:.2f} (total PnL / those sessions)  "
            f"MTM $/day={pack['per_span']:.2f} (total PnL / n={len(pack['span'])} "
            f"{pack['span'][0]}..{pack['span'][-1]})  "
            f"IWM alpha $/day={pack['a_span']:.2f} (n={pack['n_a']} skip={pack['skip_a']})  "
            f"weds={pack['n_weds']} sat_out={pack['n_sat']}  skips={pack['skips']}"
            f"{_ci_note(sm_span)}{jan_note}"
        )
        lines.append(
            f"    truncated Sep–Dec MTM daily mean ${pack['mtm_score']['per_day']:.2f} "
            f"t={pack['mtm_score']['t_stat']:.2f}{_ci_note(pack['mtm_score'])}  "
            f"— not total PnL / {len(score)}."
        )
        lines.append(
            f"    peak live |shares×last| ${pack['peak']:.0f}  fits_100k="
            f"{'yes' if pack['peak'] <= ACCOUNT + 1e-12 else 'NO'}  "
            f"total MTM$={pack['total']:.2f}"
        )
        lines.append(f"    MTM months (score 2025-09-02..2025-12-31): {pack['months_score']}")
        lines.append(f"    MTM months (first signal through last exit): {pack['months_span']}")
        if sm_span["ci_lo"] > 0 or sm_span["ci_hi"] < 0:
            lines.append("    Span MTM CI excludes 0.")
        else:
            lines.append("    Span MTM CI includes 0 — not EV.")
    lines.append(
        f"    Sep less red={'yes' if sep_less_red else 'no'}  "
        f"Dec less red={'yes' if dec_less_red else 'no'}  "
        f"total $ cut={'yes' if cuts_total else 'no'}."
    )
    lines.append("    Did not call this window a $200 slate pass. No Arrow 74.")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow73_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow73_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 73",
        "",
        verdict,
        "",
        first_para,
        f"always MTM span $/day={always['per_span']:.2f} n={always['ent']['n_trades']}  "
        f"iwm_up MTM span $/day={up['per_span']:.2f} n={up['ent']['n_trades']}  "
        f"sat_out={n0 - n1}/{n0}  peak_a ${always['peak']:.0f} peak_u ${up['peak']:.0f}",
        "IWM-up skip one-look Sep–Dec 2025. Two ids. No new cutoff. "
        "No 2026 signals. No new ingest. No Arrow 74.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 73"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
