"""Reporting ONLY: read already-completed frozen snapshots; never replay or rank.

Introduced after confirmation to distinguish calendar-month investor MTM from
signal-month completed PnL. This file is not part of the frozen strategy engine.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORTS = REPO/"reports"
CACHE = REPO/"data/tmp/cg_arrow002r"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def calendar_metrics(m):
    monthly = m["monthly_mtm"]
    total = sum(monthly.values())
    if abs(total-m["total_pnl"]) > 1e-6:
        raise ValueError("Calendar MTM and completed book PnL do not reconcile")
    reds = [p for p in monthly.values() if p < 0]
    return {"total_mtm":total,"per_session":total/m["sessions"],"sessions":m["sessions"],
            "monthly_mtm":monthly,"calendar_red_months":len(reds),
            "calendar_red_loss_sum":sum(reds),"worst_calendar_month":min(monthly.values()),
            "best_calendar_month_concentration":max(monthly.values())/total if total > 0 else None,
            **{k:m[k] for k in ("max_dd","worst_day","avg_exposure","peak_exposure",
                "mean_live_tickets","peak_live_tickets","mean_live_symbols","peak_live_symbols",
                "intended_notional","profit_per_avg_exposure","trades","hit_rate","profit_factor","borrow_sensitivity")}}


def build(test_summary):
    freeze_path = REPORTS/"cg_arrow002_freeze.txt"
    manifest_hash = hashlib.sha256(freeze_path.read_bytes()).hexdigest()
    manifest = read(freeze_path)
    started = read(CACHE/"oos_started.json")
    complete = read(CACHE/"oos_complete.json")
    if started["freeze_sha256"] != manifest_hash or complete["freeze_sha256"] != manifest_hash:
        raise ValueError("Confirmation must correspond to unchanged freeze")
    ids = ["PARENT"]+[r["id"] for r in manifest["finalists"]]
    controls = [r["id"] for r in manifest["controls"] if r["id"] != "PARENT"]
    records = {}
    for mode in ("IS","OOS","ALL"):
        records[mode] = {}
        for id in ids+controls:
            r = read(CACHE/"results"/f"{id}_{mode}.json")
            if mode != "IS" and r["freeze_sha256"] != manifest_hash:
                raise ValueError("Result belongs to a different freeze")
            records[mode][id] = r["metrics"]
    investor = {id:calendar_metrics(m) for id,m in records["ALL"].items()}
    out = {"phase":"Post-freeze descriptive investor views, not a second optimization surface",
           "freeze_sha256":manifest_hash,
           "calendar_metric_semantics":"Red months/loss sum/worst month/concentration below use calendar-month MTM, not signal-month completed PnL",
           "caveat":manifest["corporate_action_caveat"],"books":investor}
    (REPORTS/"cg_arrow002_investor_metrics.json").write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8")
    alias = {"PARENT":"PARENT","R6_REJECTION_EQUAL_EXPOSURE":"R6","R5_COMBO_EQUAL_EXPOSURE":"R5",
             "R4_VOLUME_EQUAL_EXPOSURE":"R4","D6_RECYCLE":"D6"}
    now = datetime.now(timezone.utc)
    elapsed = (now-datetime.fromisoformat(manifest["session_start"])).total_seconds()/60
    lines = [
        "CG Arrow 002R -- completed recursive hold-short-for-fade laboratory",
        "VERDICT: IS strict dual improvement FOUND; admissible OOS repetition NOT FOUND (0/4 confirmed).",
        "IS = in-sample; OOS = out-of-sample; PnL = profit and loss; MTM = marked-to-market;",
        "DD = drawdown; RTH = regular trading hours; NYSE = New York Stock Exchange; EOD = end of day.",
        "PF = profit factor; H10 = ten-session holding horizon.",
        "Strongest balanced IS finalist: R6, selling rejection plus volume exhaustion at restored exposure.",
        "R6: IS $21,120.61 / $170.33 per session; OOS $53,057.38 / $417.77 per session.",
        "Parent: IS $9,969.57 / $80.40; OOS $41,886.14 / $329.81. R6 raises profit but NONE",
        "of the six OOS smoothness measures improve, and OOS peak exposure is $126,982.12.",
        "No frozen candidate fits $100,000 on its combined all-signal investor curve.",
        "Deployment-ready: NO. No capital-admissible winner, slate promotion, or new seat is claimed.",
        "27 completed hypotheses: 8 DIRECTED, 9 ASTRA, 10 DERIVED; 29 controls, 56 total IS books.",
        "IS dispositions: 18 REJECT, 6 PROMISING, 3 FRONTIER; 4 frozen (including distinct-mechanism D6).",
        "Research results under the inherited raw-price convention; corporate-action",
        "integrity remains unresolved for deployment.","",
        "Frozen rules and selection rationale",
        "------------------------------------",
        "Common: inherited point-in-time $10-$80 / >=$10M prior-dollar-volume stock field,",
        "inherited exchange-traded-product exclusions, no arbitrary name cap. Wednesday top eight",
        "15-session raw-return leaders; next-session last tradable RTH minute close; integer shares;",
        "ten trading sessions after fill to last-RTH backstop; inherited costs and missing-H10 convention.",
        "PARENT: $4,000 per name. R6: $7,050 base, half if signal close is above its RTH range",
        "midpoint, independently half if signal RTH volume exceeds the prior-20-session mean.",
        "R5: $8,300 base, half if signal-known three-session return is positive, independently half",
        "if volume is above that prior20 mean. Highest IS return, but worse worst day: NOT strict dual.",
        "R4: $5,150 base, only the volume half-size rule. Simplest Astra-originated finalist (A4 lineage).",
        "D6: original $4k entries; freeze 20-session Average True Range (ATR), arm a >=2-ATR fade",
        "from hold day 3, cover after a subsequent >=1-ATR rebound using every traded minute close",
        "and the next traded minute open. One replacement at the first 15:55 checkpoint after cover",
        "with >=3 sessions to the ORIGINAL expiry; current checkpoint top eight; next minute open;",
        "up to min($4k, freed marked dollars), $8k symbol entry-value cap, $100k new-order marked",
        "account cap. Existing scheduled primary orders reserve their signal-known nominal dollars.",
        "No second replacement, no extended horizon. Full exact numerical rules/code hashes are frozen.",
        "D6 is mathematically dominated by R6 on measured IS axes; its OOS look tested a genuinely",
        "different exit/recycling mechanism, not a claimed orthogonal engine. Avoided redundant sizes.","",
        "IS/OOS cohort comparison -- continuous lifecycle DD, SIGNAL-month completed PnL",
        "----------------------------------------------------------------------------",
        "book split       total   $/session trades        DD   worst_day    avg_gross  peak_gross",
    ]
    for mode in ("IS","OOS"):
        for id in ids:
            m = records[mode][id]
            lines.append(f"{alias[id]:6} {mode:4} {m['total_pnl']:11.2f} {m['per_day']:11.2f} {m['trades']:6} "
                         f"{m['max_dd']:11.2f} {m['worst_day']:11.2f} {m['avg_exposure']:12.2f} {m['peak_exposure']:11.2f}")
    lines.extend(["","book split red    red_loss worst_signal_month best_month/total PnL/avg_gross    hit     PF"])
    for mode in ("IS","OOS"):
        for id in ids:
            m = records[mode][id]
            lines.append(f"{alias[id]:6} {mode:4} {m['red_months']:3} {m['red_loss_sum']:11.2f} {m['worst_month']:18.2f} "
                         f"{m['best_month_concentration']:16.4f} {m['profit_per_avg_exposure']:13.4f} "
                         f"{m['hit_rate']:6.3f} {m['profit_factor']:6.3f}")
    for mode in ("IS","OOS"):
        lines.extend(["",f"{mode} SIGNAL-month completed PnL (all six months retained)",
                      "month         PARENT           R6           R5           R4           D6"])
        for month in records[mode]["PARENT"]["months"]:
            lines.append(f"{month:8} "+" ".join(f"{records[mode][id]['months'][month]:12.2f}" for id in ids))
    lines.extend(["","One-shot repetition assessment -- NO finalist is OOS CONFIRMED WITHIN THIS INTERNAL SPLIT",
        "-------------------------------------------------------------------------------------",
        "R6 MIXED: profit and exposure-normalized profit rise, but all six smoothness measures fail",
        "to improve; DD, worst day, red-month losses and concentration worsen. Peak $126,982 > $102,922.",
        "R5 MIXED: profit rises and concentration improves, but only one smoothness measure improves;",
        "DD/worst day/red-month losses worsen and peak $122,299 breaches the ceiling.",
        "R4 MIXED: closest economic repetition -- higher profit, improved red-loss sum, worst month,",
        "DD and concentration; worst day worsens and peak $106,545.47 exceeds the allowed ceiling",
        "by $3,623.47. The capital gate is binding; do not relabel it confirmed or rescale after seeing OOS.",
        "D6 FAILED: OOS profit falls to $34,989.17 versus $41,886.14; normalized economics and all",
        "six smoothness measures fail to improve. Staying within the OOS exposure ceiling is insufficient.",
        "These labels explain the outcome rather than hiding failed requirements behind a single score.","",
        "Frozen size controls -- IS-calibrated constants, NOT recalibrated to OOS",
        "id                                      fixed_ticket    OOS_PnL  OOS_avg_gross  OOS_PnL/avg"])
    for c in manifest["controls"]:
        if c["id"] == "PARENT":
            continue
        m = records["OOS"][c["id"]]
        lines.append(f"{c['id']:39} {c['ticket']:12.4f} {m['total_pnl']:10.2f} {m['avg_exposure']:14.2f} {m['profit_per_avg_exposure']:12.4f}")
    lines.extend(["","Post-freeze descriptive 12-month investor views -- NOT a second optimization surface",
        "---------------------------------------------------------------------------------",
        "These red-month statistics use CALENDAR-month MTM, not the SIGNAL-month statistics above.",
        "book        total_MTM    $/251d  red  red_loss_sum   worst_month        DD    worst_day   avg_gross  peak_gross"])
    for id in ids:
        m = investor[id]
        lines.append(f"{alias[id]:6} {m['total_mtm']:13.2f} {m['per_session']:10.2f} {m['calendar_red_months']:4} "
                     f"{m['calendar_red_loss_sum']:13.2f} {m['worst_calendar_month']:13.2f} {m['max_dd']:11.2f} "
                     f"{m['worst_day']:12.2f} {m['avg_exposure']:11.2f} {m['peak_exposure']:11.2f}")
    lines.extend(["","month         PARENT           R6           R5           R4           D6"])
    for month in investor["PARENT"]["monthly_mtm"]:
        lines.append(f"{month:8} "+" ".join(f"{investor[id]['monthly_mtm'][month]:12.2f}" for id in ids))
    lines.extend(["","book mean/peak tickets mean/peak symbols intended_new_notional calendar_best/total PnL/avg_gross"])
    for id in ids:
        m = investor[id]
        lines.append(f"{alias[id]:6} {m['mean_live_tickets']:7.3f}/{m['peak_live_tickets']:<3} "
                     f"{m['mean_live_symbols']:10.3f}/{m['peak_live_symbols']:<3} {m['intended_notional']:21.2f} "
                     f"{m['best_calendar_month_concentration']:19.4f} {m['profit_per_avg_exposure']:13.4f}")
    lines.extend(["","Borrow-cost sensitivity -- reporting only, annual marked short value over holding calendar days",
        "book       0% total / per_day          10% total / per_day          30% total / per_day"])
    for id in ids:
        m = investor[id]
        lines.append(f"{alias[id]:6} "+"   ".join(f"{m['borrow_sensitivity'][r]:12.2f} / {m['borrow_sensitivity'][r]/251:8.2f}" for r in ("0","0.1","0.3")))
    lines.extend(["Marked EOD value is carried across intervening calendar days until the next session;",
        "this is a flat-rate sensitivity, not historical locate/loan/dividend data or a live financing model.",
        "R5's raw $331.12/day is not a $100k slate success: its marked peak is $122,299.06.",
        "The goal remains $300-$500 net/day and the slate floor $200/day on $100k; no capital-admissible",
        "improvement was confirmed. No low-correlation/joint-risk seat claim was tested or made.","",
        "Scientific audit and negative findings",
        "--------------------------------------",
        "The parent reproduces the inherited continuous-year provenance exactly at reported precision:",
        "$51,855.71, $206.60/day, 376 trades, DD -$20,033.68, worst day -$6,607.31, peak $102,921.775",
        "(rounded $102,922). No frozen parent constants or inherited source files were changed.",
        "IS split: 2025-09/11 and 2026-01/03/05/07, 124 sessions; OOS: the six even signal months,",
        "127 sessions. Lifecycle chronology includes cross-month dates; no concatenated odd-day MTM.",
        "D6 cross-month checkpoint ranks are subordinate original-slot lifecycle state, not new even-month",
        "root cohorts. All new OOS root performance was protected until the recorded freeze.",
        "The inherited even months were previously inspected historically; this is internal confirmation,",
        "not pristine independent validation. Training resampling with only six months is descriptive,",
        "post-selection and uncorrected for multiplicity, NOT a valid confidence interval or expected value.",
        "D1 inverse-vol sizing, D2 repeated-symbol caps, D3 width sizing and full-daily D4 timing failed",
        "to improve the original two-axis objective. D5 daily-checkpoint protection reduced profit.",
        "Finest-minute protection retained more IS profit than daily protection (96.9% versus 89.7%)",
        "and released 6.8% average exposure, justifying conditional D6. Recycling's IS benefit did not",
        "repeat OOS. Reranking the entire eligible field by return/volatility also failed (A9 $37.09/day).",
        "Autonomous stall/rejection/volume ideas improved IS, but matching AVERAGE IS exposure did not",
        "bound future PEAK exposure. That failure is preserved, not repaired after the reveal.",
        "A5 inventory and D6 capacity-state audits corrected dependence on future missing-backstop",
        "availability before freeze; superseded aggregates remain archived. A daylight-saving checkpoint",
        "guard caught a fixed-offset bug before D6 performance was accepted. Tests cover these cases.",
        "Causal state includes all known fills, including missing-H10 shadow positions. For comparable",
        "economics, inherited missing-backstop root exclusions remain; D6 excludes their children together.",
        "This common sampling limitation, raw prices, missing loan/dividend/locate realism, and EOD rather",
        "than guaranteed intraday margin fit preclude deployment. No split factors were inferred or fetched.",
        "D6's all-signal book is re-simulated with its joint causal capacity state, not spliced from two",
        "isolated books: full PnL $53,397.27 differs from isolated IS+OOS $52,549.23. This is descriptive",
        "post-freeze reporting only. No threshold, size, winner identity, or horizon was changed.",
        "Unpursued after reveal: controlling peak rather than average exposure and independently validating",
        "the volume/exhaustion mechanism remain questions, not an opened branch or a new arrow.","",
        "Freeze, tests, public safety and clock",
        "-------------------------------------",
        f"Freeze {manifest['timestamp']}; SHA-256 {manifest_hash}.",
        "Pre-OOS checkpoint commit: 868776f0f28364fdd2d2554484260f5de479bc8a.",
        f"One OOS pass started {started['timestamp']}, completed {complete['timestamp']}; nine frozen books.",
        "Full-year investor reporting completed 2026-09-13T02:57:35Z; no second OOS optimization pass.",
        "All 56 IS books replayed without unexplained drift under the exact frozen code identity.",
        f"Tests: {test_summary}",
        "Focused tests cover cohort/firewall/freeze invariants, sizing, exposure, later-print fills,",
        "missing-backstop shadow state, daylight-saving time, full-field selection, and a synthetic",
        "end-to-end one-shot confirmation. Temporary fixtures remain under ignored local data/tmp.",
        "Independent parquet/date, minute-lifecycle and resampling work used eight process workers;",
        "chronological scalar accounting/cache ownership was serial for correctness and low overhead.",
        f"Fresh allowance began {manifest['session_start']}; freeze at minute 69.2; report at minute {elapsed:.1f}.",
        "The 180-minute allowance was a ceiling, not a consumption target. Search continued well beyond",
        "the first improvement through independent hypotheses, contradictory challenges, full-field",
        "selection, matched exposures, minute execution, recycling and causal-state/fragility audits.",
        "All opened branches finished; no overrun or unfinished queue. Remaining time did not authorize",
        "new research after OOS. Closure commands are recorded in the command log; the terminal",
        "handoff reports the pushed commit after remote verification.",
        "Work/data stayed in the lab. No live pulls, prohibited-source access, credentials, parquet or",
        "raw market payloads were added to Git. Only reviewed code/tests and aggregate reports are intended.",
        "No CG Arrow 003 was begun or invented.","",
        "Audit files: cg_arrow002_ledger.txt; cg_arrow002_is_results.json; cg_arrow002_is_robustness.json;",
        "cg_arrow002_is_month_resampling.json; cg_arrow002_freeze.txt; cg_arrow002_selection.json;",
        "cg_arrow002_confirmation_results.json (signal-cohort statistics, including ALL by signal month);",
        "cg_arrow002_investor_metrics.json (calendar-MTM investor statistics); cg_arrow002_commands.txt;",
        "cg_arrow002_parent_validation.json; cg_arrow002_superseded_is.json; cg_arrow002_preflight_history.txt.",
        "The first blocked attempt's ledger and preflight code/tests remain unchanged as historical artifacts.",""])
    (REPORTS/"cg_arrow002_recursive_lab.txt").write_text("\n".join(lines),encoding="utf-8")
    print(f"Wrote final aggregate report and calendar-correct investor metrics at minute {elapsed:.1f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--test-summary",required=True)
    args = p.parse_args()
    build(args.test_summary)
