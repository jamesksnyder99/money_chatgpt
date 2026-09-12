"""Arrow 72 — Wednesday H10 regime skips. Same fill/hold as Arrow 66 h10_4k. Short only."""

from __future__ import annotations

import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, REPORTS
from ingest.progress import Progress
from research.arrow23 import _summarize_adv
from research.arrow43 import SEAT_FLOOR, _elig_frame, load_combined_iwm
from research.arrow44 import (
    MIN_PDV,
    MIN_PX,
    MAX_PX,
    _alpha,
    _by_sess,
    _iwm_last_close,
    _month_lines,
)
from research.arrow45 import _daily_and_trades, _within, select_shorts
from research.arrow48 import _fmt_book48, _wins_losses
from research.arrow51 import _ci_note
from research.arrow55 import HOLD, LB, MIN_RESIDUAL, N_SHORT
from research.arrow65 import _last_job, _make_trade, _mtm_and_peak, _rank_job
from research.arrow71 import dd_not_worse
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
KEEP = False
CROWD_RET = 0.15
# name, skip kind
EXPERIMENTS = (
    ("h10_4k", "always"),
    ("iwm_up", "iwm_up"),
    ("iwm_dn", "iwm_dn"),
    ("wide", "wide"),
    ("uncrowded", "uncrowded"),
    ("lowvol", "lowvol"),
)
IDS = tuple(e[0] for e in EXPERIMENTS)


def wednesday_exists(
    kind: str,
    feat: dict | None,
    cuts: dict[str, float] | None,
) -> bool:
    """Whether this Wednesday takes new fills. Id 0 never skips."""
    if kind == "always":
        return True
    if not feat:
        return False
    iwm_15 = feat.get("iwm_15")
    width = feat.get("width")
    crowd = feat.get("crowd")
    ivol = feat.get("ivol")
    cuts = cuts or {}
    if kind == "iwm_up":
        return iwm_15 is not None and float(iwm_15) >= 0.0
    if kind == "iwm_dn":
        return iwm_15 is not None and float(iwm_15) < 0.0
    if kind == "wide":
        return width is not None and "width" in cuts and float(width) >= cuts["width"] - 1e-12
    if kind == "uncrowded":
        return crowd is not None and "crowd" in cuts and float(crowd) <= cuts["crowd"] + 1e-12
    if kind == "lowvol":
        return ivol is not None and "ivol" in cuts and float(ivol) <= cuts["ivol"] + 1e-12
    return False


def iwm_lookback(
    iwm: dict, session: date, feats: list[date], n: int = LB
) -> tuple[float | None, float | None]:
    """iwm_15 close-to-close and sample stdev of last n one-session IWM returns."""
    closes: list[float] = []
    for k in range(-n, 1):
        dk = session_shift(session, k, feats)
        if dk is None:
            return None, None
        got = _iwm_last_close(iwm, dk)
        if got is None or got[1] <= 0:
            return None, None
        closes.append(float(got[1]))
    if len(closes) != n + 1 or closes[0] <= 0:
        return None, None
    iwm_15 = closes[-1] / closes[0] - 1.0
    rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    if len(rets) < 2:
        return iwm_15, None
    return iwm_15, float(statistics.stdev(rets))


def wednesday_features(rec: dict, iwm_15: float | None) -> tuple[float | None, int | None]:
    """width = leftover #1 minus #8 15-session return. crowd = names with ret15 >= 15%."""
    rows = list(rec.get("rows") or [])
    if iwm_15 is None:
        return None, None
    picks = select_shorts(rows, N_SHORT, None)
    width = None
    if len(picks) >= N_SHORT:
        r1 = float(picks[0]["residual"]) + float(iwm_15)
        r8 = float(picks[N_SHORT - 1]["residual"]) + float(iwm_15)
        width = r1 - r8
    crowd = sum(
        1 for row in rows if float(row["residual"]) + float(iwm_15) >= CROWD_RET - 1e-12
    )
    return width, crowd


def _median(xs: list[float]) -> float | None:
    if not xs:
        return None
    return float(statistics.median(xs))


def run_arrow72(*, workers: int | None = None) -> int:
    if tape_root(date(2026, 1, 2)) == BARS_DIR or tape_root(date(2026, 7, 1)) == BARS_DIR:
        raise RuntimeError("Arrow 72 must not read Lab A data/bars/")
    cpu = os.cpu_count() or 1
    workers = max(1, workers or min(8, cpu))
    study = combined_study_sessions()
    feats = feature_sessions()
    is_sess, oos_sess = split_is_oos(study)
    print(
        f"research start mode=arrow72 workers={workers} cpu={cpu} "
        f"study={study[0]}..{study[-1]} n={len(study)} IS n={len(is_sess)} OOS n={len(oos_sess)} "
        f"jan_tape={tape_root(date(2026, 1, 2))} jul_tape={tape_root(date(2026, 7, 1))}",
        flush=True,
    )
    print(
        "Wednesday H10 regime skips. Same leftover short as Arrow 66 h10_4k. "
        "Same fill and hold. Only whether this Wednesday exists. "
        "Did not keep/cash. Did not use an OOS month to pick a cutoff. "
        "No new ingest. No Arrow 73.",
        flush=True,
    )
    elig = _elig_frame()
    by = _by_sess(elig)
    iwm = load_combined_iwm()
    jobs = []
    weds: list[date] = []
    for d in study:
        if d.weekday() != 2:
            continue
        look15 = session_shift(d, -LB, feats)
        if look15 is None:
            continue
        i_l15 = _iwm_last_close(iwm, look15)
        i1 = _iwm_last_close(iwm, d)
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
        f"Wednesday signal n={N_SHORT} lb={LB} fill=nextrth ${NOTIONAL:.0f} hold={HOLD}  "
        f"jobs={len(jobs)}",
        flush=True,
    )
    prog = Progress(len(jobs), "arrow72")
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
        rows = list(rec.get("rows") or [])
        iwm_15, ivol = iwm_lookback(iwm, d, feats, LB)
        width, crowd = wednesday_features(rec, iwm_15)
        feat_by[d.isoformat()] = {
            "iwm_15": iwm_15,
            "width": width,
            "crowd": crowd,
            "ivol": ivol,
        }
        if (rec.get("n_res") or 0) < MIN_RESIDUAL:
            picks_by[d.isoformat()] = []
            continue
        picks_by[d.isoformat()] = select_shorts(rows, N_SHORT, None)

    chunks: dict[str, dict] = {
        d.isoformat(): {"trades": {k: [] for k in IDS}, "n_res": nres_by.get(d.isoformat(), 0)}
        for d in study
    }
    skips: dict[str, dict[str, int]] = {k: {"IS": 0, "OOS": 0} for k in IDS}
    trades_all: dict[str, list[dict]] = {k: [] for k in IDS}
    usable: dict[str, list[date]] = {k: [] for k in IDS}

    for d in weds:
        picks = picks_by.get(d.isoformat()) or []
        split = "IS" if is_is_session(d) else "OOS"
        if nres_by.get(d.isoformat(), 0) >= MIN_RESIDUAL:
            usable[CONTROL_ID].append(d)
        for h in picks:
            tr, skip_fill, _partial = _make_trade(
                h, FILL_KIND, NOTIONAL, KEEP, d, feats, hold=HOLD
            )
            if skip_fill:
                skips[CONTROL_ID][split] += 1
                continue
            if tr is None:
                continue
            chunks[d.isoformat()]["trades"].setdefault(CONTROL_ID, []).append(tr)
            trades_all[CONTROL_ID].append(tr)

    need: set[tuple[str, str]] = set()
    for t in trades_all[CONTROL_ID]:
        fill_d, exit_d = t["fill_date"], t["exit_date"]
        for x in study:
            if fill_d <= x < exit_d:
                need.add((x.isoformat(), t["symbol"]))
    last_map: dict[tuple[str, str], float] = {}
    if need:
        prog2 = Progress(len(need), "arrow72-mtm")
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

    sm_ent0, _, tr0 = _daily_and_trades(
        chunks, is_sess, CONTROL_ID, [d for d in weds if is_is_session(d)]
    )
    mtm0_all, _ = _mtm_and_peak(trades_all[CONTROL_ID], study, last_map)
    mtm0_is = [mtm0_all[study.index(d)] for d in is_sess]
    sm_mtm0 = _summarize_adv(mtm0_is, tr0, len(is_sess))
    reprint_ok = _within(sm_mtm0["per_day"], A66_H10_IS_MTM) and _within(
        sm_ent0["n_trades"], A66_H10_IS_N
    )
    reprint_line = (
        f"Id 0 {CONTROL_ID} IS MTM $/day={sm_mtm0['per_day']:.2f}/{A66_H10_IS_MTM} "
        f"n={sm_ent0['n_trades']}/{A66_H10_IS_N} "
        + (
            "— within ±10% of Arrow 66 h10_4k."
            if reprint_ok
            else "— DRIFT beyond ±10%. Regime skips not a valid read."
        )
    )
    print(reprint_line, flush=True)
    if not reprint_ok:
        text = (
            "Arrow 72 — Wednesday H10 regime skips (IS / OOS)\n"
            "VERDICT: FAIL — id 0 did not reprint Arrow 66 h10_4k. "
            "Did not score skips on a drifted control.\n"
            f"{reprint_line}\n"
            "No Arrow 73.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow72_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1

    is_w0 = [d for d in usable[CONTROL_ID] if is_is_session(d)]
    widths = [float(feat_by[d.isoformat()]["width"]) for d in is_w0 if feat_by[d.isoformat()]["width"] is not None]
    crowds = [float(feat_by[d.isoformat()]["crowd"]) for d in is_w0 if feat_by[d.isoformat()]["crowd"] is not None]
    ivols = [float(feat_by[d.isoformat()]["ivol"]) for d in is_w0 if feat_by[d.isoformat()]["ivol"] is not None]
    iwm_s = [feat_by[d.isoformat()]["iwm_15"] for d in is_w0 if feat_by[d.isoformat()]["iwm_15"] is not None]
    cuts = {
        "width": _median(widths),
        "crowd": _median(crowds),
        "ivol": _median(ivols),
    }
    if any(v is None for v in cuts.values()):
        text = (
            "Arrow 72 — Wednesday H10 regime skips (IS / OOS)\n"
            "VERDICT: FAIL — IS character medians missing. Did not freeze cutoffs.\n"
            "No Arrow 73.\n"
        )
        REPORTS.mkdir(parents=True, exist_ok=True)
        (REPORTS / "arrow72_results.txt").write_text(text, encoding="utf-8")
        print(text, flush=True)
        return 1
    frac_up = (sum(1 for x in iwm_s if x >= 0.0) / len(iwm_s)) if iwm_s else None
    char_line = (
        f"IS character on id 0 Wednesdays n={len(is_w0)}. Description. Does not pick an id. "
        f"median width={cuts['width']:.5f}  median crowd={cuts['crowd']:.2f}  "
        f"median ivol={cuts['ivol']:.5f}  frac iwm_15>=0="
        + (f"{frac_up:.3f}" if frac_up is not None else "n/a")
        + ". Those three medians are frozen cutoffs for wide / uncrowded / lowvol. "
        "Did not use an OOS month to pick a cutoff."
    )
    print(char_line, flush=True)

    for name, kind in EXPERIMENTS:
        if name == CONTROL_ID:
            continue
        for d in usable[CONTROL_ID]:
            if wednesday_exists(kind, feat_by.get(d.isoformat()), cuts):
                usable[name].append(d)
        split_weds = {d for d in usable[name]}
        for d in weds:
            split = "IS" if is_is_session(d) else "OOS"
            if d not in split_weds:
                continue
            for tr in chunks[d.isoformat()]["trades"].get(CONTROL_ID) or []:
                copy = dict(tr)
                chunks[d.isoformat()]["trades"].setdefault(name, []).append(copy)
                trades_all[name].append(copy)
            skips[name][split] = skips[CONTROL_ID][split]

    results = []
    ctrl_is = ctrl_oos = ctrl_oos_dd = None
    n0_is = sum(1 for d in usable[CONTROL_ID] if is_is_session(d))
    n0_oos = sum(1 for d in usable[CONTROL_ID] if not is_is_session(d))
    for name, kind in EXPERIMENTS:
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
                "kind": kind,
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
                "n_weds_is": len(is_w),
                "n_weds_oos": len(oos_w),
                "n_sat_is": n0_is - len(is_w),
                "n_sat_oos": n0_oos - len(oos_w),
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
            f"VERDICT: FAIL — no Arrow 72 engine has OOS MTM >= ${SEAT_FLOOR:.0f}/day AND non-red IS MTM."
        )
    beat_s = ", ".join(beats) if beats else "none"
    both_s = ", ".join(both) if both else "none"
    sat_bits = []
    for r in results:
        if r["name"] == CONTROL_ID:
            continue
        sat_bits.append(
            f"{r['name']} sat out IS {r['n_sat_is']}/{n0_is} OOS {r['n_sat_oos']}/{n0_oos} "
            f"(kept {r['n_weds_is']}+{r['n_weds_oos']})"
        )
    lead = (
        f"{reprint_line} Frozen IS medians: width={cuts['width']:.5f} crowd={cuts['crowd']:.2f} "
        f"ivol={cuts['ivol']:.5f}. Beat id 0 on both slices with DD guard: {beat_s}. "
        f"Lift-both (no DD guard): {both_s}. " + " ".join(sat_bits) + "."
    )
    honesty = (
        "Wednesday H10 regime skips. Same leftover short as Arrow 66 h10_4k: "
        "Wednesday signal, eight largest 15-session close-to-close returns, "
        "fill next session last-RTH, $4,000, hold 10. Same fill and hold. "
        "The only new knob is whether this Wednesday exists. Did not keep/cash. "
        "Did not change rank, n, hold, ticket, or fill. Did not retune frozen B/flush. "
        "Cutoffs from IS character of id 0 Wednesdays only, then freeze. "
        "Did not use an OOS month to pick a cutoff. Did not drop an id after seeing OOS. "
        "A skipped Wednesday is cash that week: no new fills. Names already on from last week "
        "still mark and exit on their own day-10. Did not flatten them early. "
        "Did not mix Sep–Dec 2025. Split on the signal Wednesday. "
        "A skip id beats id 0 only if it lifts MTM $/day on both IS and OOS "
        "and does not worsen OOS max DD by more than 25%. "
        "Do not call a CI that includes 0 EV. Combined dollars are not EV. No Arrow 73."
    )
    lines = [
        "Arrow 72 — Wednesday H10 regime skips (IS / OOS)",
        verdict,
        lead,
        char_line,
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
        f"Wednesday signal  n={N_SHORT}  lb={LB} fill=nextrth  hold={HOLD}  ${NOTIONAL:.0f}",
        "Peak live = |shares × last|. Skipped Wednesday = no new fills that week.",
        "",
        f"{'id':<12} {'split':<4} {'entry$':>9} {'MTM$':>9} {'n':>6} {'weds':>5} {'sat':>4} "
        f"{'hit':>6} {'t':>6} {'seat':>5}",
    ]
    for r in results:
        for split, ent, mtm, a, skip_a, n_a, months_s, peak_s, n_w, n_sat in (
            (
                "IS",
                r["ent_is"],
                r["mtm_is"],
                r["a_is"],
                r["skip_is"],
                r["n_a_is"],
                r["is_months"],
                r["peak_live_is"],
                r["n_weds_is"],
                r["n_sat_is"],
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
                r["n_weds_oos"],
                r["n_sat_oos"],
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
                f"{ent['n_trades']:6d} {n_w:5d} {n_sat:4d} "
                f"{ent['hit_rate']:6.3f} {mtm['t_stat']:6.2f} {flag:>5}"
            )
            lines.extend(_fmt_book48(mtm))
            lines.append(
                f"    entry $/day={ent['per_day']:.2f}  MTM $/day={mtm['per_day']:.2f}  "
                f"IWM alpha $/day={a:.2f} (n={n_a} skip={skip_a})  "
                f"kind={r['kind']}  weds={n_w} sat_out={n_sat}{_ci_note(mtm)}"
            )
            lines.append(
                f"    peak live |shares×last| ${peak_s:.0f}  all-sessions ${r['peak_live']:.0f}  "
                f"fits_100k={'yes' if r['fits'] else 'NO'}  signals={r['n_reb']}"
            )
            lines.append(f"    MTM months: {months_s}")
    lines.append("")
    text = "\n".join(lines) + "\n"
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "arrow72_results.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'arrow72_results.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 72",
        "",
        verdict,
        "",
        lead,
        char_line,
        f"Seat ${SEAT_FLOOR:.0f}: {', '.join(seats) if seats else 'none'}. "
        f"Slate ${FAILURE_LINE:.0f}: {', '.join(slates) if slates else 'none'}. "
        f"Beat id 0: {beat_s}.",
        "Wednesday H10 regime skips. Same fill/hold as Arrow 66 h10_4k. "
        "Cutoffs frozen from IS. Did not use an OOS month to pick a cutoff. "
        "No new ingest. No Arrow 73.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    marker = " — Arrow 72"
    pos = prev.rfind(marker)
    if pos != -1:
        start = prev.rfind("## ", 0, pos)
        if start != -1:
            prev = prev[:start].rstrip()
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
