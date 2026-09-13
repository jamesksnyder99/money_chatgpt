"""Reporting only: consume committed frozen outcomes without rescoring policies."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import statistics
import subprocess

from research.cg_arrow003_data import ROOT,REPO_ROOT,SCORE,read,dump,digest,stamp
from research.cg_arrow003_lab import FREEZE,LEDGER,elapsed,classify,code_identity,input_identity

REPORTS=REPO_ROOT/"reports"


def money(value):
    return "n/a" if value is None else f"{value:,.2f}"


def percent(value):
    return "n/a" if value is None else f"{100*value:.2f}%"


def repetition(train,confirm,train_control,confirm_control,priority):
    """Transparent direction/tradeoff assessment under pre-reveal priorities.

    This uses the SAME comparator in both splits, and the lab's common classifier.
    It does not penalize a small gross-exposure excursion or equate reused months
    with fresh external evidence.
    """
    is_cmp=classify(train,train_control)
    oos_cmp=classify(confirm,confirm_control)
    kind=priority["primary_improvement"]["kind"]
    tolerance=priority["acceptable_tradeoff"].get("monetary_downside_worsening",.05)
    downside=oos_cmp["downside_relative"]
    improved=sum(v is not None and v>=.05 for v in downside.values())
    acceptable=all(v is None or v>=-tolerance for v in downside.values())
    profit_positive=confirm["total_pnl"]>0
    gain=oos_cmp["profit_difference"]
    gain_material=gain>=max(100,.05*abs(confirm_control["total_pnl"]))
    retained=oos_cmp["profit_retention"]
    if kind=="ride":
        minimum=priority["acceptable_tradeoff"].get("minimum_profit_retention",.85)
        primary=retained is not None and retained>=minimum and oos_cmp["classification"] in {"BALANCED","RIDE-FIRST"}
    elif kind=="balanced":
        primary=oos_cmp["classification"]=="BALANCED"
    elif kind=="return":
        primary=gain_material
    else:raise ValueError("Unknown frozen primary priority")
    if primary and acceptable and profit_positive:
        numerical="REPEATED"
    elif profit_positive and (gain>0 or improved>=2):
        numerical="PARTIALLY REPEATED"
    else:
        numerical="NOT REPEATED"
    data_limited=priority.get("missingness_dependency",False)
    verdict="INCONCLUSIVE/DATA-LIMITED" if data_limited else numerical
    is_delta_day=train["per_day"]-train_control["per_day"]
    oos_delta_day=confirm["per_day"]-confirm_control["per_day"]
    return {"assessment":verdict,"numeric_assessment":numerical,"control":priority["control"],
        "assessment_scope":"Relative numerical repetition under the common incomplete-tape convention; absolute complete economics remain data-limited",
        "primary_kind":kind,"is_comparison":is_cmp,"oos_comparison":oos_cmp,
        "is_increment_per_session":is_delta_day,"oos_increment_per_session":oos_delta_day,
        "increment_per_session_ratio":oos_delta_day/is_delta_day if is_delta_day>0 else None,
        "positive_oos_profit":profit_positive,"acceptable_monetary_downside":acceptable,
        "improved_oos_downside_axes":improved,"gross_exposure_auto_failure":False,
        "explanation":"Conditional research on the same working comparator. Profit, monthly ride, drawdown, worst day and exposure are reported separately.",
        "data_dependency":"IS gain relies on unavailable-volatility neutral sizing; it is not evidence that the taper itself helps on observed histories." if data_limited else
          "Partial corporate-action and stale-inventory limitations remain common to candidate and comparator."}


def verify_book(name,m,days):
    if [x["date"] for x in days]!=[d.isoformat() for d in SCORE]:
        raise AssertionError(f"Calendar dates lost or reordered in {name}")
    if abs(sum(x["pnl"] for x in days)-m["total_pnl"])>1e-6:
        raise AssertionError(f"Daily/total mismatch {name}")
    if abs(sum(x["pnl"] for x in m["calendar_months"])-m["total_pnl"])>1e-6:
        raise AssertionError(f"Monthly/total mismatch {name}")
    if len(m["calendar_months"])!=12:
        raise AssertionError("All twelve months required")
    equity=100000.0
    for x in days:
        equity+=x["pnl"]
        if abs(equity-x["equity"])>1e-6:raise AssertionError("Daily equity does not reconcile")
    equity=100000.0
    for row in m["calendar_months"]:
        if abs(row["starting_equity"]-equity)>1e-6:raise AssertionError("Month start equity mismatch")
        if row["return"] is not None and abs(row["return"]-row["pnl"]/equity)>1e-10:
            raise AssertionError("Monthly return denominator is not start equity")
        equity+=row["pnl"]


def csv_export(path,books):
    fields=["book","date","pnl","equity","gross","gross_to_equity","tickets","symbols",
            "largest_symbol_gross","largest_symbol_equity_fraction","stale_gross","new_gross",
            "preorder_gross","pacing_scale","above_130k","excess_130k","excursion_cause",
            "borrow_base","extra_spread"]
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        for name,rows in books.items():
            writer.writerows({"book":name,**row} for row in rows)


def performance_table(lines,names,results,mode,labels):
    lines += ["| Book | Profit | $/session | Red months / loss sum | Worst / median month | Drawdown | Worst day | Mean / peak gross |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name in names:
        m=results[name][mode]
        red=m["calendar_red_months"] if mode=="ALL" else m["red_months"]
        loss=m["calendar_red_loss_sum"] if mode=="ALL" else m["red_loss_sum"]
        worst=m["calendar_worst_month"] if mode=="ALL" else m["worst_month"]
        median=m["calendar_median_month"] if mode=="ALL" else m["median_month"]
        lines.append(f"| {labels.get(name,name)} | {money(m['total_pnl'])} | {money(m['per_day'])} | {red} / {money(loss)} | {money(worst)} / {money(median)} | {money(m['max_dd'])} | {money(m['worst_day'])} | {money(m['avg_exposure'])} / {money(m['peak_exposure'])} |")


def month_table(lines,names,results,labels):
    lines += ["| Calendar month | "+" | ".join(labels.get(n,n) for n in names)+" |",
              "|---|"+"---:|"*len(names)]
    for i in range(12):
        month=results[names[0]]["ALL"]["calendar_months"][i]["month"]
        cells=[]
        for n in names:
            r=results[n]["ALL"]["calendar_months"][i]
            cells.append(f"{money(r['pnl'])} ({percent(r['return'])})")
        lines.append("| "+month+" | "+" | ".join(cells)+" |")


def run():
    if not (ROOT/"investor_complete.json").exists():
        raise RuntimeError("Report requires the frozen chronological all-signal replay")
    freeze=read(FREEZE)
    if freeze["code_sha256"]!=code_identity() or freeze["input_sha256"]!=input_identity():
        raise RuntimeError("Reporting must use the frozen code and input convention")
    freeze_sha=digest(FREEZE)
    for p in (ROOT/"oos_complete.json",ROOT/"investor_complete.json"):
        if read(p)["freeze_sha256"]!=freeze_sha:raise RuntimeError("Outcome/freeze identity mismatch")
    names=[s["id"] for s in freeze["specs"]]
    results={}
    provenance={}
    daily={}
    for name in names:
        results[name]={}
        provenance[name]={}
        for mode in ("IS","OOS","ALL"):
            record=read(ROOT/"results"/(name+f"_{mode}.json"))
            if record["code_sha256"]!=freeze["code_sha256"] or record["spec"] not in freeze["specs"]:
                raise RuntimeError("Outcome does not belong to the frozen policy/code")
            path=REPO_ROOT/record["detail_path"]
            if digest(path)!=record["detail_sha256"]:raise RuntimeError("Detailed output was modified")
            detail=read(path)
            verify_book(name,record["metrics"],detail["daily"])
            results[name][mode]=record["metrics"]
            provenance[name][mode]={"path":record["detail_path"],"sha256":record["detail_sha256"]}
            if mode=="ALL":daily[name]=detail["daily"]
    assessments={}
    for p in freeze["finalists"]:
        name=p["id"]
        c=p["control"]
        assessments[name]=repetition(results[name]["IS"],results[name]["OOS"],results[c]["IS"],results[c]["OOS"],p)
    ids=[p["id"] for p in freeze["finalists"]]
    focus=[n for n in ("PARENT","R4","R5","A4","R1") if n in names]+ids
    minute=read(REPORTS/"cg_arrow003_minute_all.json")
    if not minute["all_calendar_sessions"] or any(n not in minute["books"] for n in focus):
        raise RuntimeError("Full-calendar synchronized minute audit required for controls/finalists")
    labels={p["id"]:f"F{i+1}" for i,p in enumerate(freeze["finalists"])}
    correlations={a:{b:statistics.correlation([r["pnl"] for r in daily[a]],[r["pnl"] for r in daily[b]])
                     for b in focus} for a in focus}
    searched={p.stem[:-3]:read(p) for p in (ROOT/"results").glob("*_IS.json")}
    hypotheses={n:r for n,r in searched.items() if r["spec"]["origin"] not in {"CONTROL","DIAGNOSTIC"}}
    origins=Counter(r["spec"]["origin"] for r in hypotheses.values())
    comparisons={n:{mode:{c:classify(results[n][mode],results[c][mode],calendar=mode=="ALL") for c in freeze["controls"]}
                    for mode in ("IS","OOS","ALL")} for n in ids}
    pair_comparisons={n:{mode:{c:classify(results[n][mode],results[c][mode],calendar=mode=="ALL") for c in ids if c!=n}
                        for mode in ("IS","OOS","ALL")} for n in ids}
    command=REPORTS/"cg_arrow003_commands.txt"
    payload={"timestamp":stamp(),"status":"COMPLETE research; final public-safety review/push recorded in command log",
        "freeze_sha256":freeze_sha,"freeze":freeze,"results":results,"assessments":assessments,
        "absolute_economics_status":"INCONCLUSIVE/DATA-LIMITED: incomplete held-position price paths, actions and loans",
        "comparisons":comparisons,"all_signal_daily_correlations":correlations,
        "finalist_pair_comparisons":pair_comparisons,
        "synchronized_minute_risk":{n:{k:v for k,v in minute["books"][n].items() if k!="days"} for n in focus},
        "is_search":{n:{"spec":r["spec"],"metrics":r["metrics"]} for n,r in searched.items()},
        "hypotheses_completed":len(hypotheses),"origins":dict(origins),"is_controls":len(searched)-len(hypotheses),
        "detailed_local_provenance":provenance,"confirmation_invalidated":False,
        "confirmation_resume":read(ROOT/"oos_complete.json")["resumed_identical_job"],
        "elapsed_minutes_at_report":elapsed()/60,"historical_confirmation_reuse":True,
        "limitations":["Partial corporate-action coverage","Stale terminal and internal marks; acquisition price bands make missingness potentially adverse","Unknown dividends, stock loans, broker financing and cash-in-lieu",
                        "Actual borrow availability and fills not certified","Same R4/R5 family; not independent engines","Repeated even months are internal confirmation"]}
    csv_path=REPORTS/"cg_arrow003_daily.csv"
    csv_export(csv_path,daily)
    payload["daily_csv"]={"path":csv_path.relative_to(REPO_ROOT).as_posix(),"sha256":digest(csv_path),"rows":sum(len(x) for x in daily.values())}
    dump(REPORTS/"cg_arrow003_results.json",payload)
    lines=["# CG Arrow 003 — R4/R5 continuation","",
        "IS = in-sample (odd signal months); OOS = out-of-sample (even signal months); PnL = profit and loss; MTM = marked-to-market; DD = drawdown; RTH = regular trading hours; EOD = end of day; ATR = Average True Range.","",
        "## Verdict","",
        f"Completed {len(hypotheses)} new policy hypotheses ({', '.join(f'{v} {k.lower()}' for k,v in origins.items())}), with {len(searched)-len(hypotheses)} IS controls and separate diagnostics. All directed C1–C6 core tests closed. {len(ids)} distinct new finalists were frozen before the single confirmation batch. No Arrow 004 or unrelated engine was started.","",
        "These are conditional research results. Eight documented reverse splits received common as-of repairs; the split reference is still incomplete. Missing future exits no longer erase entries: unresolved positions remain in the book with stale valuations. Copied acquisition price bands caused known lifecycle gaps, potentially associated with adverse short moves; **absolute complete economics are not established**. Starting equity is $100,000, intended ticket sizes do not compound, and approximately $130,000 gross is a soft planning range, not a deposit or margin guarantee.","",
        "| Finalist | Plain-English policy | Same comparator | Primary objective | Confirmation |",
        "|---|---|---|---|---|"]
    for p in freeze["finalists"]:
        a=assessments[p["id"]]
        lines.append(f"| {labels[p['id']]} — `{p['id']}` | {p['pitch']} | {p['control']} | {p['primary_improvement']['kind']} | **{a['assessment']}** |")
    lines += ["","The ranking and objectives above were set before confirmation. The numerical classifier is shared by IS and OOS; it has no hard gross-exposure veto. Five-percent monetary changes are descriptive materiality guides, not statistical proofs. The same even months were inspected in earlier work; this is reused internal confirmation, not pristine validation.","",
              "## Common repairs and negative findings","",
              "[Repair reconciliation](cg_arrow003_repairs.md) separates legacy, accounting-only, and action-adjusted working controls. The original PARENT/R4/R5 daily legacy curves reproduced exactly; earlier reports, tests and freeze evidence remain unchanged. All new comparisons use the working convention.","",
              "The median-volume reference and three-session participation persistence lost useful profit. Smooth volume penalties generally raised exposure and worsened the measured tradeoff. Updating volume at entry weakened R4; the observed loss was mainly from upgrading tickets after the signal. Relative participation ranks and final-hour volume-share sizing were weaker than the relevant controls. Drawdown-sensitive new allocations reduced losses but sacrificed substantial rebound profit. Profitable dominated variants remain in the ledger and frontier; they are not erased or called universal mechanism failures.","",
              "The apparent momentum-taper improvement was driven by neutral sizing when 20-session volatility was unavailable. On the 182 trades with usable volatility, the taper lost $1,837.98 versus R5; the 15 missing-history trades added $8,554.73. Preserving the original momentum switch on missing history removed the apparent improvement. This dependency is distinct from evidence that a smooth momentum curve helps.","",
              "The advancing-day-vote rule also depended partly on sparse histories: $2,004.54 of its $3,122.85 IS increment came from 15 missing-history tickets, while 182 observed histories added $1,118.31. The final observed-history versions retain original R5 sizing on sparse histories. Votes and covers are not independent edges: the unpaced combined increment was $587.54 below the sum of their separate increments. After the history fallback and pacing, the full-size combination adds only about $542 beyond the simpler paced cover policy, with a worse worst day. This modest extra benefit is a material qualification of the return challenger.","",
              "The second-half half-cover for low initial participation was more useful than the original high-volume-upturn overlay. A one-session-later neighbor preserved the IS direction. The every-minute trigger comparison lost profit and slightly worsened DD relative to the 15:55 checkpoint for both R4 and R5; this supports the checkpoint's anti-twitch role on this IS sample while retaining one-minute executable prices.","",
              "Further ablations showed that removing the low-initial-participation restriction still improved both R4 and R5: it sacrificed some profit for slightly better downside. Moving the original high-current-participation C5 rule to day 6 also improved profit. The evidence therefore supports a late management tradeoff; it does not establish that the low-volume clause uniquely causes the benefit. Halving new R5 orders when the current open book was losing sacrificed too much profit, like the earlier high-water-mark rule.","",
              "Holding age is indexed from zero on entry. The original exploratory overlays managed through age 9 and retained the age-10 backstop. A separate literal directed C5 test allowed the half-cover through age 10 inclusive: R4/R5 IS profits were $14,837.74/$22,025.08, slightly below the earlier age-9-ending versions. The frozen Astra-derived covers explicitly retain their tested ages 6–9; no boundary convention is changed after reveal.","",
              "The deterministic within-signal-batch size shuffles were diagnostics, not strategies or independent statistical validation. None of 64 shuffles per family reached the actual R4/R5 IS profit. This association does not certify corporate-action completeness, borrow economics or future returns.","",
              "## Signal-cohort training and confirmation","",
              "These totals include each signal cohort's complete observed lifecycle and terminal MTM through August 31. They are **not actual calendar-month account returns**. Profit/session divides by the 124 IS or 127 OOS signal-month sessions; drawdown and exposure walk the full uninterrupted 251-session calendar. Unless labeled minute-sampled, drawdown uses consecutive end-of-day marked equity, including all intervening sessions.","","### IS"]
    performance_table(lines,focus,results,"IS",labels)
    lines += ["","### OOS — one frozen batch"]
    performance_table(lines,focus,results,"OOS",labels)
    lines += ["","### Increment and repetition against the same comparator","",
              "| Finalist | Comparator | IS increment / session | OOS increment / session | OOS downside changes: red loss / worst month / DD / worst day | Numeric result |",
              "|---|---|---:|---:|---|---|"]
    for name,a in assessments.items():
        r=a["oos_comparison"]["downside_relative"]
        changes=" / ".join(percent(r[k]) for k in ("red_loss_sum","worst_month","max_dd","worst_day"))
        lines.append(f"| {labels[name]} | {a['control']} | {money(a['is_increment_per_session'])} | {money(a['oos_increment_per_session'])} | {changes} | {a['numeric_assessment']} |")
    lines += ["","Positive downside percentages mean improvement; negative values mean worse losses. A materially weaker monthly ride is not excused by the softer exposure policy. Absolute and percentage differences against PARENT, R4, R5 and the frozen size controls are retained in the machine-readable results.","",
              "## Chronological all-signal investor account","",
              "All signals were replayed together after confirmation, with one live inventory and one causal capacity policy. Constrained IS/OOS books were not added or spliced. The following monthly returns use each month's starting marked equity; all twelve months, including losing and flat months, are retained.",""]
    performance_table(lines,focus,results,"ALL",labels)
    lines += ["","### Twelve calendar months — original and conservative controls","","Cells show MTM dollars (return on month-start equity)."]
    month_table(lines,[n for n in ("PARENT","R4","R5","A4","R1") if n in names],results,labels)
    lines += ["","### Twelve calendar months — frozen finalists",""]
    month_table(lines,ids,results,labels)
    lines += ["","All frozen matched controls also have twelve month-start-equity/MTM/return rows in `cg_arrow003_results.json`. The daily ACCOUNT aggregates for every control and finalist are in [cg_arrow003_daily.csv](cg_arrow003_daily.csv); raw market bars and position/fill ledgers are not published.","",
              "## Practical risk and inventory","",
              "| Book | DD % | Underwater sessions / longest spell | P95 / peak EOD gross | Sessions / longest above $130k | Excess dollar-days | Peak gross/equity | Largest symbol/equity | Terminal tickets / stale gross |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name in focus:
        m=results[name]["ALL"]
        lines.append(f"| {labels.get(name,name)} | {percent(m['max_dd_percent'])} | {m['time_underwater_sessions']} / {m['longest_underwater_sessions']} | {money(m['p95_exposure'])} / {money(m['peak_exposure'])} | {m['above_130k_sessions']} / {m['longest_above_130k']} | {money(m['exposure_dollar_days_above_130k'])} | {m['peak_gross_to_equity']:.3f} | {percent(m['largest_symbol_equity_fraction'])} | {m['terminal_tickets']} / {money(m['terminal_stale_gross'])} |")
    lines += ["","| Book | Fully closed ticket PnL | Realized exit-leg PnL | Terminal net unrealized MTM | Maximum terminal staleness (sessions) |",
              "|---|---:|---:|---:|---:|"]
    for name in focus:
        m=results[name]["ALL"]
        lines.append(f"| {labels.get(name,name)} | {money(m['fully_closed_ticket_pnl'])} | {money(m['completed_leg_pnl'])} | {money(m['terminal_net_mtm'])} | {m['terminal_max_stale_sessions']} |")
    lines += ["","Realized exit legs plus terminal net unrealized MTM reconcile to total profit. Fully closed tickets are a separate view; realized partial covers can belong to tickets still open at the boundary. Completed versus partly open signal-batch cohort PnL is also explicit in JSON. No future terminal cover fee or post-boundary loan charge is invented.","",
              "Dollar-days use calendar duration to the next session; dollar-session excess is also supplied in JSON. Excursion cause labels distinguish sessions with new allocation from existing-inventory drift; they are descriptive, not retroactive order rejection. Pacing uses last pre-order marks, reserves all open cohorts and due-but-unfilled closing orders, and scales a simultaneous batch pro rata. There is no minimum-size top-up or forced liquidation at a small overshoot.","",
              "Five of six unresolved IS R4 tickets were last marked above $80. Across its full lifecycle, **720 of 724 stale position-sessions** have a documented price-range exclusion in at least one copied acquisition table; the remaining four have other documented exclusions. Missing rows in one source are distinguished from known exclusions in the other in `cg_arrow003_lifecycle_coverage.json`. The old acquisition bounds do not provide a complete held-position lifecycle service. A modeled delay means a missing local executable observation; it does not assert a market halt or actual inability to exit.","",
              "Fixed-quantity terminal shocks are in `cg_arrow003_stale_dependency.json`. The separate `cg_arrow003_dynamic_stale.json` diagnostic replays causal IS capacity/drawdown state under common non-compounding +10%, +50% and +100% missing-valuation errors. At +50%, original R4/R5 profits fall to $1,805.80/$9,625.58. These are hypothetical stresses, not estimates or probability bounds; actual missing prices and absolute account economics remain uncertain. A carried or stressed mark is never an executable exit.","",
              "An independent cash-minus-short-liability audit checks sale proceeds, cover payments, remaining quantities and observed execution identity. It agrees with the scorer's daily MTM accounting; agreement cannot repair missing prices, actions or loan economics. Cover-only additional execution-cost sensitivity is in `cg_arrow003_cover_execution.json`; combined-policy increments are not attributed entirely to covers.","",
              "| Book | 10% adverse move in all shorts | 50% adverse move in largest name | Joint: other names +10%, largest +50% | Best calendar month / total profit |",
              "|---|---:|---:|---:|---:|"]
    for name in focus:
        m=results[name]["ALL"]
        lines.append(f"| {labels.get(name,name)} | {money(m['stress_short_10pct'])} | {money(m['stress_largest_name_50pct'])} | {money(m['stress_joint_others10_largest50'])} | {percent(m['calendar_best_month_concentration'])} |")
    lines += ["","### Synchronized minute risk audit","",
              "Every calendar session was checked using concurrent one-minute closes. Each close sample includes close fills and precedes the next bar's open executions at the same time boundary. Cash credits entry proceeds and debits cover cash plus costs. Missing intraday prices carry the last known mark. These are minute-close marked peaks, not tick-by-tick maxima or independent-high sums.","",
              "| Book | Minute peak gross | Peak time | Stale gross at peak | Minutes above $130k | Excess dollar-minutes |",
              "|---|---:|---|---:|---:|---:|"]
    for name in focus:
        a=minute["books"][name]
        p=a["synchronized_minute_peak"]
        lines.append(f"| {labels.get(name,name)} | {money(p['gross'])} | {p['timestamp']} | {money(p['stale_since_prior_session_gross'])} | {a['minutes_above_130k']} | {money(a['dollar_minutes_above_130k'])} |")
    lines += ["","| Book | Minute-sampled DD (dollars / %) | Peak minute gross/equity | Largest name/equity |",
              "|---|---:|---:|---:|"]
    for name in focus:
        a=minute["books"][name]
        lines.append(f"| {labels.get(name,name)} | {money(a['minute_sampled_max_drawdown'])} / {percent(a['minute_sampled_max_drawdown_percent'])} | {a['peak_gross_to_equity']:.3f} | {percent(a['largest_symbol_equity_fraction'])} |")
    lines += ["","Stress amounts are arithmetic, not forecasts, margin certification or new stop rules. Largest-name and broad-book maxima can occur on different dates; the joint stress is evaluated concurrently per day. Top-symbol and top/bottom-month contribution details remain in the aggregate JSON.","",
              "## Borrow and execution-cost scenarios","",
              "Baseline commission is $0.005 per share each side plus a one-side spread proxy of max($0.01, 0.10% of price). Borrow scenarios charge 0%, 10%, or 30% annualized on preceding EOD marked gross for actual calendar holding days. Spread stress doubles only the spread proxy; commissions remain unchanged. These are sensitivities, not observed loan fees.","",
              "| Book | Baseline $/day | 10% borrow $/day | 30% borrow $/day | Double spread $/day |",
              "|---|---:|---:|---:|---:|"]
    for name in focus:
        m=results[name]["ALL"]
        s=m["scenarios"]
        lines.append(f"| {labels.get(name,name)} | {money(s['borrow_0_spread_1']/251)} | {money(s['borrow_10_spread_1']/251)} | {money(s['borrow_30_spread_1']/251)} | {money(s['borrow_0_spread_2']/251)} |")
    lines += ["","The full cross-product of borrow and spread scenarios is available for every frozen book. The ambition remains $300–$500 modeled net/day on $100,000. An under-target portfolio is not commercial success; the old $200/day slate and $100/day component figures are references, not automatic vetoes on useful family research. No independent-engine seat or deployment readiness is claimed.","",
              "## Resilience, overlap and interpretation","",
              "Paired leave-one-IS-month-out profit differences, contribution dependence, size matches and neighbors are recorded in `cg_arrow003_is_robustness.json` and `cg_arrow003_is_frontier.json`. The best incremental contributors still matter; multiple correlated downside metrics do not constitute independent confirmations. Signal-month ownership allows causal feature histories and existing-position management to cross even/odd boundaries; overlap counts and opposite-split lifecycle MTM are explicit JSON fields.","",
              "Daily all-signal correlation is reported in JSON. Every book is a continuation of the same hold-short-for-fade selections; combining R4 and R5 sizing is not diversification across independent engines.","",
              "## Clock, verification and handoff","",
              f"Run start: {freeze['start']}; deadline: {freeze['deadline']}. Freeze: {freeze['timestamp']} (minute {freeze['elapsed_minutes']:.2f}), committed before OOS. Confirmation start/completion: {read(ROOT/'oos_started.json')['timestamp']} / {read(ROOT/'oos_complete.json')['timestamp']}. Report written at minute {elapsed()/60:.2f}.","",
              "Exact repeatable commands, test totals, effort allocation, public-safety review, commits and remote verification are in [cg_arrow003_commands.txt](cg_arrow003_commands.txt). The freeze manifest records explicit versioned dependencies, repair conventions, data/cache identity, scenarios, priorities and intended sizes. Detailed local ledger paths and hashes are in the results file. No confirmation was invalidated; any identical-job resume is explicitly recorded.","",
              "## Parked questions — not executed as a new arrow","",
              "Resolve stale/delisted inventory and broader corporate-action coverage; obtain actual historical loan/dividend economics if authorized; challenge these fixed policies on genuinely new data; understand whether sparse volume histories encode missing data or an economic state. Independent swing/day models remain parked. No Arrow 004 is begun."]
    (REPORTS/"cg_arrow003_report.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print(json.dumps({"hypotheses":len(hypotheses),"assessments":{k:v["assessment"] for k,v in assessments.items()},
                      "daily_rows":payload["daily_csv"]["rows"],"elapsed_minutes":elapsed()/60},indent=2))


if __name__=="__main__":run()
