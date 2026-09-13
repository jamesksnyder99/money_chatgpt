"""IS diagnostics and repair reconciliation; detailed ledgers stay in ignored data."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date
import json
from pathlib import Path
import statistics

import polars as pl

from research.cg_arrow003_data import (
    ROOT,OLD,REPO_ROOT,FEATS,SCORE,INDEX,read,dump,digest,stamp,data_for,
    history_asof,features,action_events,CONVENTION,
)
from research.cg_arrow003_lab import authorize,ledger,elapsed,classify,score,Spec
from dataclasses import asdict,replace
from research.costs import cost_per_share
from research.cg_arrow002_lab import history_features
from research.arrow65 import _make_trade,_mtm_and_peak


def legacy_job(job):
    iso,h,amount = job
    return _make_trade(h,"nextrth",amount,False,date.fromisoformat(iso),FEATS,hold=10)[0]


def repair_audit(workers=8):
    authorize("IS")
    ranks=read(OLD/"ranks_IS_wed.json")
    old_summaries={}
    for iso in {x.isoformat() for x in FEATS}:
        p=OLD/"summaries"/(iso+".json")
        if p.exists():
            old_summaries.update({(iso,s):v for s,v in read(p).items()})
    jobs=[]
    for name,base in (("PARENT",4000),("R4",5150),("R5",8300)):
        for iso,rec in ranks.items():
            d=date.fromisoformat(iso)
            for h in rec["rows"][:8]:
                f=history_features([old_summaries.get((x.isoformat(),h["symbol"]))
                    for x in FEATS[max(0,INDEX[d]-20):INDEX[d]+1]])
                amount=base
                if name!="PARENT" and f["volume_ratio"] is not None and f["volume_ratio"]>1:
                    amount*=.5
                if name=="R5" and f["ret3"] is not None and f["ret3"]>0:
                    amount*=.5
                jobs.append((name,(iso,h,amount)))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        trades=list(pool.map(legacy_job,[j for _,j in jobs]))
    grouped=defaultdict(list)
    for (name,_),t in zip(jobs,trades):
        if t:
            grouped[name].append(t)
    old_ids={"PARENT":"PARENT","R4":"R4_VOLUME_EQUAL_EXPOSURE","R5":"R5_COMBO_EQUAL_EXPOSURE"}
    reconcile={}
    raw_stage={}
    for p in (ROOT/"superseded").glob("*_IS.json"):
        r=read(p)
        if r["spec"]["id"] in old_ids:
            raw_stage[r["spec"]["id"]]=r["metrics"]
    fields=("total_pnl","per_day","max_dd","worst_day","red_loss_sum","avg_exposure","peak_exposure","trades")
    for name,ts in grouped.items():
        expected=read(OLD/"results"/(old_ids[name]+"_IS.json"))["metrics"]
        got=sum(t["pnl"] for t in ts)
        if abs(got-expected["total_pnl"])>1e-6:
            raise AssertionError(f"Legacy reproduction drift {name}")
        marks={key:v["close"] for key,v in old_summaries.items() if v}
        daily,peak=_mtm_and_peak(ts,SCORE,marks)
        if max(abs(a-b) for a,b in zip(daily,expected["daily"]))>1e-6:
            raise AssertionError(f"Legacy daily reproduction drift {name}")
        current=read(ROOT/"results"/(name+"_IS.json"))["metrics"]
        reconcile[name]={"legacy_reproduced_pnl":got,"legacy_count":len(ts),
             "maximum_legacy_daily_difference":max(abs(a-b) for a,b in zip(daily,expected["daily"])),
             "legacy":{k:expected[k] for k in fields},
             "accounting_only":{k:raw_stage[name][k] for k in fields},
             "working":{k:current[k] for k in fields},
             "accounting_delta":raw_stage[name]["total_pnl"]-got,
             "documented_action_delta":current["total_pnl"]-raw_stage[name]["total_pnl"],
             "total_common_repair_delta":current["total_pnl"]-got,
             "terminal_tickets":current["terminal_tickets"],"terminal_gross":current["terminal_gross"],
             "terminal_stale_gross":current["terminal_stale_gross"],"counters":current["counters"]}
    # Bounded local EOD inspection for unresolved terminal names only. Schema/date
    # diagnostics, no guess at adjustment conventions and no executable substitution.
    detail=read(ROOT/"details/PARENT_IS.json")
    eod=[]
    for sym in sorted({p["symbol"] for p in detail["terminal"]}):
        available=[]
        for chunk in ("2026-03","2026-04","2026-05"):
            p=REPO_ROOT/"data/virgin/eod"/chunk/(sym+".parquet")
            if p.exists():
                frame=pl.read_parquet(p)
                if frame.height and "eod_date" in frame.columns:
                    available.append({"chunk":chunk,"rows":frame.height,
                         "last_date":str(frame["eod_date"].max()),"explicit_adjustment_field":"adjusted" in frame.columns})
        eod.append({"symbol":sym,"partitions":available,"treatment":"not substituted: national EOD may include later-session trades and lacks declared adjustment metadata"})
    out={"timestamp":stamp(),"elapsed_minutes":elapsed()/60,"convention":CONVENTION,
         "reconciliation":reconcile,"local_eod_checks":eod,
         "split_coverage":"partial documented events; placeholder remains immutable",
         "sdk":"thetadata 1.0.10 inspected locally; no split endpoint exposed, no authentication/live request attempted",
         "original_rank_cache":"preserved complete inherited eligibility rows; reranked after known as-of factors, no arbitrary cap"}
    dump(REPO_ROOT/"reports/cg_arrow003_repair_metrics.json",out)
    lines=["# Arrow 003 common repairs and IS reconciliation","",
           "IS means in-sample, odd SIGNAL months. PnL means profit and loss; MTM means marked-to-market. All figures are modeled dollars. Historical Arrow 002 evidence is unchanged.","",
           "## Legacy reproduction and reconciliation","",
           "Original PARENT/R4/R5 were independently reproduced with the inherited `_make_trade` implementation and copied canonical tape. Completed profit and every lifecycle daily value match the frozen local results within 1e-6. No historical OOS gate or marker was changed.","",
           "| Control | Legacy IS | Accounting only | Working IS | Accounting delta | Documented-action delta |",
           "|---|---:|---:|---:|---:|---:|"]
    for name,r in reconcile.items():
        lines.append(f"| {name} | {r['legacy']['total_pnl']:.2f} | {r['accounting_only']['total_pnl']:.2f} | {r['working']['total_pnl']:.2f} | {r['accounting_delta']:.2f} | {r['documented_action_delta']:.2f} |")
    lines += ["","These common changes are not strategy alpha. Every new candidate uses the working convention and the same working comparator.","",
              "## Accounting convention","",
              "REPAIRED: Entry existence is independent of future exit availability. Fixed last regular-hours minute is required for a late entry; no earlier fallback fill. Missing scheduled ten-session exits stay open and reserve marked exposure, then cover at the first available later regular-hours print. Terminal entries are retained at August 31. Carried marks are stale valuations, never executable fills. Half-covers preserve proportional entry costs. Continuous drawdown uses the full 251-session lifecycle chronology.","",
              "REPAIRED: Live ticket/symbol counts use actual inventory, gross is distinct from the original $100,000 equity, and all outputs share one soft-exposure classifier. Calendar-month MTM and month-start-equity returns are separate from signal-cohort ownership.","",
              "QUANTIFIED/RETAINED: Compatible alternate copied minute partitions are attempted when canonical data are absent. National EOD partitions were inspected for unresolved terminal symbols; their later-session scope and absent adjustment declaration prevent silent substitution. No new data connection, credentials, terminal, or subscription was used.","",
              "| Control | Open terminal tickets | Terminal gross | Stale terminal gross | Stale position-sessions | Delayed exit fills |",
              "|---|---:|---:|---:|---:|---:|"]
    for name,r in reconcile.items():
        lines.append(f"| {name} | {r['terminal_tickets']} | {r['terminal_gross']:.2f} | {r['terminal_stale_gross']:.2f} | {r['counters'].get('stale_position_sessions',0)} | {r['counters'].get('delayed_exit_fills',0)} |")
    lines += ["","## Partial corporate-action repair","",
              "The copied split table has zero rows and is not zero-event evidence. A bounded discontinuity screen flagged candidates for source review; it never inferred a factor. Eight issuer-documented reverse splits were applied across the full inherited eligible ranking rows and selected price/volume features as of each decision. Before an effective trading session, historical comparison prices multiply by old-shares/new-share and share volumes divide by that factor. Held shares divide and entry basis, paid entry-cost basis, marks and frozen price-unit ATR multiply at the event. Raw execution prints remain unchanged.","",
              "| Symbol | First adjusted trading session | Price factor | Primary provenance |","|---|---|---:|---|"]
    for e in action_events():
        lines.append(f"| {e['symbol']} | {e['effective_session']} | {e['price_factor']} | [Issuer evidence]({e['source']}) |")
    lines += ["","PARTIAL, not universe certification: other splits, mergers, symbol transitions, cash-in-lieu, dividends, loan availability, fees and financing remain unresolved. Theoretical fractional short liabilities are retained if a documented reverse split crosses a holding; broker cash-in-lieu is not fabricated. Remaining discontinuities are dependency diagnostics, not ticker exclusions or evidence of splits. New economic claims are conditional on this coverage.","",
              "All detailed positions, missing observations and source tape paths remain under ignored `data/tmp/cg_arrow003/`; public manifests carry their hashes. Raw copied data and earlier reports remain unchanged.","",
              f"Bounded repair audit checkpoint: {out['timestamp']}, elapsed {out['elapsed_minutes']:.2f} minutes. Focused accounting/action fixtures passed before the working controls were used for discovery."]
    (REPO_ROOT/"reports/cg_arrow003_repairs.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    ledger({"event":"REPAIR_PHASE_COMPLETE","repair_metrics":out,"status":"repaired accounting; partial documented actions; stale-data limitations quantified"})
    print(json.dumps(reconcile,indent=2))


def board():
    authorize("IS")
    rows={p.stem[:-3]:read(p) for p in (ROOT/"results").glob("*_IS.json")}
    for name,r in sorted(rows.items(),key=lambda x:x[1]["metrics"]["total_pnl"],reverse=True):
        m=r["metrics"]
        c=rows[r["spec"]["control"]]["metrics"]
        cl=classify(m,c)
        print(f"{name:28} {m['total_pnl']:10.2f} DD {m['max_dd']:10.2f} redloss {m['red_loss_sum']:10.2f} "
              f"worstday {m['worst_day']:9.2f} avg {m['avg_exposure']:9.2f} peak {m['peak_exposure']:10.2f} {cl['classification']}")


def diagnostics(workers=8):
    authorize("IS")
    _,summaries=data_for("IS",workers)
    output={"timestamp":stamp(),"cohort":"IS only","holding":{},"attribution":{},
            "interpretation":"Descriptive attribution, not hindsight exits, exclusions or independent validation"}
    for name in ("R4","R5"):
        detail=read(ROOT/"details"/(name+"_IS.json"))
        # Control has no partial management; exit or terminal outcome per ticket.
        exits={x["ticket_id"]:x for x in detail["legs"]}
        ages=defaultdict(lambda:defaultdict(float))
        bystate=defaultdict(lambda:defaultdict(float))
        parent=read(ROOT/"details/PARENT_IS.json")["ticket_pnl"]
        symbols=defaultdict(float)
        months=defaultdict(float)
        for p in detail["positions"]:
            vol=p["feature"].get("volume_ratio")
            state="missing" if vol is None else ("above_reference" if vol>1 else "at_or_below_reference")
            delta=detail["ticket_pnl"][p["id"]]-parent.get(p["id"],0)
            bystate[state]["tickets"]+=1
            bystate[state]["incremental_profit_vs_parent"]+=delta
            bystate[state]["candidate_profit"]+=detail["ticket_pnl"][p["id"]]
            symbols[p["symbol"]]+=delta
            months[p["signal"][:7]]+=delta
            leg=exits.get(p["id"])
            end=date.fromisoformat(leg["exit_ts"][:10]) if leg else SCORE[-1]
            previous=p["entry"]
            q=p["initial_shares"]
            for d in SCORE:
                if not p["fill_date"]<=d.isoformat()<=end.isoformat():continue
                age=INDEX[d]-p["fill_index"]
                key=f"{state}/"+(str(age) if age<=10 else "11_plus_delayed")
                row=ages[key]
                row["position_sessions"]+=1
                if age==0:
                    row["costs"]-=q*cost_per_share(p["entry"])
                    continue
                rec=summaries.get((d.isoformat(),p["symbol"]))
                if not rec or not rec.get("first_ts"):
                    row["stale_position_sessions"]+=1
                    continue
                row["overnight"]+=q*(previous-rec["open"])
                exit_day=bool(leg and d==end)
                px=leg["exit"] if exit_day else rec["close"]
                row["rth"]+=q*(rec["open"]-px)
                if exit_day:row["costs"]-=q*cost_per_share(px)
                previous=px
        total=sum(v.get("overnight",0)+v.get("rth",0)+v.get("costs",0) for v in ages.values())
        actual=read(ROOT/"results"/(name+"_IS.json"))["metrics"]["total_pnl"]
        if abs(total-actual)>1e-6:
            raise AssertionError(f"Holding-age attribution does not reconcile: {name} {total-actual}")
        output["holding"][name]={"age_state":dict(ages),"reconciled_total":total,"difference":total-actual}
        output["attribution"][name]={"states":dict(bystate),"top_symbol_deltas":sorted(symbols.items(),key=lambda x:x[1],reverse=True)[:8],
             "bottom_symbol_deltas":sorted(symbols.items(),key=lambda x:x[1])[:8],"month_deltas":dict(months),
             "comparator":"working constant $4000 parent; includes intended-scale and feature effects, matched controls separate"}
    dump(REPO_ROOT/"reports/cg_arrow003_is_diagnostics.json",output)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"C2_VOLUME_ATTRIBUTION_AND_C5_HOLDING_AGE","result":output})
    for name,rows in output["holding"].items():
        age=defaultdict(float)
        for k,v in rows["age_state"].items():
            age[k.split('/')[-1]]+=sum(v.get(x,0) for x in ("overnight","rth","costs"))
        print(name,"holding-day net",dict(age))
        print(name,"volume-state attribution",output["attribution"][name]["states"])


def shuffle_job(job):
    spec,ranks,summaries=job
    m,_=score(Spec(**spec),"IS",ranks,summaries)
    return {"seed":spec["shuffle_seed"],"family":spec["family"],"metrics":m}


def shuffles(workers=8):
    authorize("IS")
    ledger({"event":"PREDECLARE_DIAGNOSTIC","id":"C2_BATCH_SIZE_SHUFFLES",
        "mechanism":"64 deterministic seeds (3000..3063) per R4/R5, permute the complete intended ticket amounts only within the original signal batch; fixed nominal sum, integer shares and actual gross need not be identical",
        "purpose":"Association and concentration diagnostic, not a new strategy or independent statistical validation"})
    ranks,summaries=data_for("IS",workers)
    specs=[]
    for name in ("R4","R5"):
        base=Spec(**read(ROOT/"results"/(name+"_IS.json"))["spec"])
        specs += [replace(base,id=f"DIAG_{name}_{seed}",origin="DIAGNOSTIC",shuffle_seed=seed) for seed in range(3000,3064)]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results=[]
        for i,out in enumerate(pool.map(shuffle_job,[(asdict(s),ranks,summaries) for s in specs]),1):
            results.append(out)
            if i%16==0:print(f"{stamp()} shuffle diagnostic {i}/{len(specs)} ETA bounded under 2 minutes",flush=True)
    aggregate={}
    for name in ("R4","R5"):
        real=read(ROOT/"results"/(name+"_IS.json"))["metrics"]
        selected=[r for r in results if r["family"]==name]
        profits=sorted(r["metrics"]["total_pnl"] for r in selected)
        aggregate[name]={"real_profit":real["total_pnl"],"shuffle_mean_profit":statistics.mean(profits),
                        "shuffle_median_profit":statistics.median(profits),"shuffle_min_profit":min(profits),
                        "shuffle_max_profit":max(profits),"shuffles_at_least_real_profit":sum(x>=real["total_pnl"] for x in profits),
                        "seeds":len(profits),"real_minus_shuffle_median":real["total_pnl"]-statistics.median(profits)}
    payload={"timestamp":stamp(),"scope":"IS only","aggregate":aggregate,"seeds":results,
             "warning":"Finite permutation diagnostic; not probability of a tradable edge, not independent validation"}
    dump(REPO_ROOT/"reports/cg_arrow003_is_shuffles.json",payload)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"C2_BATCH_SIZE_SHUFFLES","results":aggregate,
            "seed_result_count":len(results),"result_file":"reports/cg_arrow003_is_shuffles.json"})
    print(json.dumps(aggregate,indent=2))


def robustness():
    authorize("IS")
    rows={p.stem[:-3]:read(p) for p in (ROOT/"results").glob("*_IS.json")}
    out={"timestamp":stamp(),"cohort":"IS only","candidates":{},
         "interpretation":"Paired contribution diagnostics, not month/ticker deletions in any strategy or independent validation"}
    for name,r in rows.items():
        if r["spec"]["origin"] in {"CONTROL","DIAGNOSTIC"}:continue
        m=r["metrics"]
        comparisons={}
        extra=["R4","R5"] if r["spec"]["family"]=="BLEND" else []
        for cid in dict.fromkeys([r["spec"]["control"],"PARENT","MATCH_"+name]+extra):
            if cid not in rows:continue
            c=rows[cid]["metrics"]
            delta={k:m["months"][k]-c["months"][k] for k in m["months"]}
            loo={k:sum(delta.values())-v for k,v in delta.items()}
            d=read(ROOT/"details"/(name+"_IS.json"))
            cd=read(ROOT/"details"/(cid+"_IS.json"))
            symbol_delta={s:d["symbol_pnl"].get(s,0)-cd["symbol_pnl"].get(s,0)
                         for s in set(d["symbol_pnl"])|set(cd["symbol_pnl"])}
            sorted_delta=sorted(symbol_delta.items(),key=lambda x:x[1],reverse=True)
            comparisons[cid]={**classify(m,c),"month_differences":delta,"leave_one_month_out_differences":loo,
                "positive_months":sum(v>0 for v in delta.values()),"positive_leave_one_out":sum(v>0 for v in loo.values()),
                "min_leave_one_out":min(loo.values()),"top_symbol_differences":sorted_delta[:5],
                "bottom_symbol_differences":sorted_delta[-5:],
                "increment_excluding_largest_positive_symbol":sum(symbol_delta.values())-max(symbol_delta.values()),
                "increment_excluding_three_largest_positive_symbols":sum(symbol_delta.values())-sum(max(0,v) for _,v in sorted_delta[:3])}
        f=[]
        for p in read(ROOT/"details"/(name+"_IS.json"))["positions"]:
            f.append({"ticket":p["id"],"vol20_missing":p["feature"].get("vol20") is None,
                      "volume_missing":p["feature"].get("volume_ratio") is None})
        out["candidates"][name]={"comparisons":comparisons,"missing_features":dict(Counter(
                "vol20_missing" if p["vol20_missing"] else "vol20_available" for p in f))}
        c=comparisons[r["spec"]["control"]]
        print(f"{name}: versus {r['spec']['control']} delta {c['profit_difference']:.2f}, "
              f"positive months {c['positive_months']}/6, positive leave-one-out {c['positive_leave_one_out']}/6, "
              f"without top contributor {c['increment_excluding_largest_positive_symbol']:.2f}")
    dump(REPO_ROOT/"reports/cg_arrow003_is_robustness.json",out)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"PAIRED_IS_ROBUSTNESS","candidate_count":len(out["candidates"]),
            "result_file":"reports/cg_arrow003_is_robustness.json"})


def mechanism_attribution():
    authorize("IS")
    pairs=[("C3_R5_MOMENTUM_TAPER","R5"),("C4_R4_ENTRY_UPDATE","R4"),("C5_R4_EARNED_FADE","R4")]
    payload={}
    for name,control in pairs:
        d=read(ROOT/"details"/(name+"_IS.json"))
        c=read(ROOT/"details"/(control+"_IS.json"))
        groups=defaultdict(lambda:defaultdict(float))
        for p in d["positions"]:
            delta=d["ticket_pnl"][p["id"]]-c["ticket_pnl"].get(p["id"],0)
            if name.startswith("C3"):
                key="missing_vol20" if p["feature"].get("vol20") is None else "available_vol20"
            elif name.startswith("C5"):
                key="half_cover_triggered" if p["covered"] else "no_cover"
            else:
                original=next(x for x in c["positions"] if x["id"]==p["id"])
                key="upsized" if p["initial_shares"]>original["initial_shares"] else ("downsized" if p["initial_shares"]<original["initial_shares"] else "unchanged")
            groups[key]["count"]+=1
            groups[key]["increment"]+=delta
            groups[key]["candidate_pnl"]+=d["ticket_pnl"][p["id"]]
        payload[name]=dict(groups)
    dump(REPO_ROOT/"reports/cg_arrow003_mechanism_attribution.json",payload)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"DIRECTED_MECHANISM_ATTRIBUTION","results":payload})
    print(json.dumps(payload,indent=2))


def stale_dependency():
    """Common-symbol valuation errors, not invented price outcomes or strategy fills."""
    authorize("IS")
    rows={p.stem[:-3]:read(p) for p in (ROOT/"results").glob("*_IS.json")}
    books={}
    for name,r in rows.items():
        d=read(ROOT/"details"/(name+"_IS.json"))
        gross=defaultdict(float)
        for p in d["terminal"]:
            if p["last_mark_date"]!=SCORE[-1].isoformat():
                gross[p["symbol"]]+=p["shares"]*p["mark"]
        books[name]=dict(gross)
    output={"timestamp":stamp(),"cohort":"IS only","books":{},
            "convention":"Shock each unresolved terminal valuation by a shared relative error across policies; no trade is deleted and no exit is invented",
            "shocks":[-.5,.1,.5,1.0],"warning":"Arithmetic sensitivity, not probabilities, observed prices, loan quotes or certified bounds. Executed quantities are fixed: changed earlier pacing/drawdown decisions under alternative missing marks are not quantified."}
    for name,r in rows.items():
        c=r["spec"]["control"]
        if c not in rows:continue
        delta=r["metrics"]["total_pnl"]-rows[c]["metrics"]["total_pnl"]
        difference={s:books[name].get(s,0)-books[c].get(s,0) for s in set(books[name])|set(books[c])}
        g=sum(books[name].values())
        output["books"][name]={"control":c,"stale_terminal_by_symbol":books[name],"stale_total":g,
             "total_pnl":r["metrics"]["total_pnl"],"base_increment":delta,
             "pnl_after_uniform_stale_price_shock":{str(s):r["metrics"]["total_pnl"]-s*g for s in output["shocks"]},
             "increment_after_common_symbol_shock":{str(s):delta-s*sum(difference.values()) for s in output["shocks"]},
             "absolute_increment_sensitivity_per_100pct_independent_symbol_error":sum(abs(x) for x in difference.values()),
             "stale_symbol_gross_difference":difference}
    dump(REPO_ROOT/"reports/cg_arrow003_stale_dependency.json",output)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"STALE_TERMINAL_VALUATION_DEPENDENCY",
            "books":len(output["books"]),"result_file":"reports/cg_arrow003_stale_dependency.json"})
    for name in ("PARENT","R4","R5","C3_R5_TAPER_PACED","C5_R4_FADE_CONSERVATIVE"):
        if name in output["books"]:
            r=output["books"][name]
            print(name,"stale gross",round(r["stale_total"],2),"profit after +50% stale-price error",round(r["pnl_after_uniform_stale_price_shock"]["0.5"],2),
                  "increment after shared shock",round(r["increment_after_common_symbol_shock"]["0.5"],2))


def frontier():
    authorize("IS")
    rows={p.stem[:-3]:read(p) for p in (ROOT/"results").glob("*_IS.json")}
    def axes(m):
        return [m["total_pnl"],-m["red_months"],m["red_loss_sum"],m["worst_month"],m["max_dd"],
                m["worst_day"],-m["avg_exposure"],-m["peak_exposure"],m["profit_per_avg_exposure"] or 0]
    out={"timestamp":stamp(),"cohort":"IS only","frontier":[],"policies":{},
         "axes":"profit, red-month count/loss, worst month, drawdown, worst day, average/peak gross, profit per average gross",
         "interpretation":"No scalar score and no hard gross ceiling. Dominated profitable mechanisms are distinguished from economic rejection."}
    for name,r in rows.items():
        m=r["metrics"]
        a=axes(m)
        dominators=[]
        for other,s in rows.items():
            if other==name:continue
            b=axes(s["metrics"])
            if all(y>=x-1e-7 for x,y in zip(a,b)) and any(y>x+1e-7 for x,y in zip(a,b)):
                dominators.append(other)
        if not dominators:out["frontier"].append(name)
        c=rows[r["spec"]["control"]]["metrics"]
        out["policies"][name]={"spec":r["spec"],"classification":classify(m,c),"dominated_by":dominators,
            "disposition":"CONTROL" if r["spec"]["origin"]=="CONTROL" else (
                "DOMINATED PROFITABLE POLICY" if dominators and m["total_pnl"]>0 else (
                "ECONOMICALLY REJECTED" if m["total_pnl"]<=0 else "FRONTIER / TRADEOFF")),"metrics":m}
    dump(REPO_ROOT/"reports/cg_arrow003_is_frontier.json",out)
    ledger({"event":"FRONTIER_CHECKPOINT","ids":out["frontier"],"policy_count":len(rows),
            "notes":"Dominance is descriptive; finalists also require interpretable mechanisms, fragility checks, and distinct tradeoffs"})
    print("Nondominated:",", ".join(out["frontier"]))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["repairs","board","diagnostics","shuffles","robustness","attribution","stale","frontier"])
    p.add_argument("--workers",type=int,default=8)
    args=p.parse_args()
    if args.command=="repairs":repair_audit(args.workers)
    elif args.command=="diagnostics":diagnostics(args.workers)
    elif args.command=="shuffles":shuffles(args.workers)
    elif args.command=="robustness":robustness()
    elif args.command=="attribution":mechanism_attribution()
    elif args.command=="stale":stale_dependency()
    elif args.command=="frontier":frontier()
    else:board()


if __name__=="__main__":main()
