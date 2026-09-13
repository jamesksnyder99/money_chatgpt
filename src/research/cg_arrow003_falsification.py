"""Predeclared IS counterfactuals and execution-fragility arithmetic.

These are diagnostics, not extra finalist policies or invented missing prices.
No synthetic mark becomes an executable fill or a signal-feature observation.
"""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import asdict
import argparse
import time
from datetime import date
from collections import Counter
import polars as pl

from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump,digest,data_for,stamp,FEATS,INDEX,SCORE
from research.cg_arrow003_lab import Spec,score,authorize,ledger,code_identity


BOOKS=["R4","R5","C1_R4_PACED","C1_R5_PACED","AR3_R4_LATE_COVER_CONSERVATIVE",
       "AR6_R5_VOTES_COVER_PACED","AR7_R4_LATE_COVER_PACED","AR8_R5_VOTES_COVER_CONSERVATIVE",
       "AR2_R5_LATE_WEAK_PART_COVER","C3_R5_TAPER_PACED","A3_R4_DRAWDOWN_NEW",
       "AR9_R5_LATE_COVER_PACED","AR10_R4_CONSERVATIVE_COVER_PACED",
       "AR11_R5_OBSERVED_VOTES_COVER","AR12_R5_OBSERVED_CONSERVATIVE"]
SHOCKS=[0.,.1,.5,1.]


def job(args):
    raw,shock,ranks,summaries=args
    spec=Spec(**raw)
    metrics,details=score(spec,"IS",ranks,summaries,stale_shock=shock)
    p=ROOT/"stale_counterfactual"/(spec.id+f"_{int(shock*100)}.json")
    dump(p,details)
    return {"id":spec.id,"shock":shock,"metrics":metrics,
            "detail_path":p.relative_to(REPO_ROOT).as_posix(),"detail_sha256":digest(p)}


def dynamic_stale(workers=8):
    authorize("IS")
    ledger({"event":"PREDECLARE_DIAGNOSTIC","id":"DYNAMIC_STALE_CAPACITY",
        "books":BOOKS,"shocks":SHOCKS,
        "mechanism":"At a missing pre-order or EOD observation, value existing shorts at last actual observed price times 1+shock; carry that same level until a real print returns. The shock never compounds per day, changes signal features, or invents fills. Common shock applied to every book. Recompute new-order pacing and prior-equity drawdown state causally.",
        "purpose":"Quantify how uncertainty in missing valuations can change future capacity decisions; these are hypothetical stress arithmetic, not estimated prices or strategy alternatives"})
    ranks,summaries=data_for("IS",workers)
    specs={n:read(ROOT/"results"/(n+"_IS.json"))["spec"] for n in BOOKS}
    output=[]
    start=time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs=[pool.submit(job,(s,v,ranks,summaries)) for s in specs.values() for v in SHOCKS]
        for i,f in enumerate(as_completed(fs),1):
            output.append(f.result())
            if i%8==0 or i==len(fs):
                spent=time.monotonic()-start
                print(f"{stamp()} dynamic stale diagnostic {i}/{len(fs)} ETA~{spent/i*(len(fs)-i):.1f}s",flush=True)
    books={}
    for name in BOOKS:
        rows={str(r["shock"]):r for r in output if r["id"]==name}
        original=read(ROOT/"results"/(name+"_IS.json"))["metrics"]
        zero=rows["0.0"]["metrics"]
        for key in ("total_pnl","max_dd","peak_exposure","intended_notional"):
            if abs(original[key]-zero[key])>1e-7:raise AssertionError("Zero-shock replay changed baseline")
        control=specs[name]["control"]
        for r in rows.values():
            baseline=next(x for x in output if x["id"]==control and x["shock"]==r["shock"])
            r["increment_vs_common_shock_control"]=r["metrics"]["total_pnl"]-baseline["metrics"]["total_pnl"]
            r["intended_notional_change"]=r["metrics"]["intended_notional"]-original["intended_notional"]
            r["filled_ticket_change"]=r["metrics"]["trades"]-original["trades"]
        books[name]=rows
    payload={"timestamp":stamp(),"mode":"IS diagnostic only","shocks":SHOCKS,"books":books,
             "code_sha256":code_identity(),"wall_seconds":time.monotonic()-start,
             "limitations":"Uniform non-compounding hypothetical adverse valuation errors. No distributions, probability bounds, actual missing-price estimates, or new executable bars. Signals/ranking/management features unchanged; current capacity and drawdown state respond to stressed marks. No OOS diagnostic tuning."}
    dump(REPO_ROOT/"reports/cg_arrow003_dynamic_stale.json",payload)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"DYNAMIC_STALE_CAPACITY","jobs":len(output),
            "wall_seconds":payload["wall_seconds"],"result_file":"reports/cg_arrow003_dynamic_stale.json"})
    for name,rows in books.items():
        r=rows["0.5"]
        print(name,"+50% stale marks: profit",round(r["metrics"]["total_pnl"],2),
              "increment",round(r["increment_vs_common_shock_control"],2),
              "new intended notional change",round(r["intended_notional_change"],2))


def execution():
    authorize("IS")
    names=["C5_R4_EARNED_FADE","C5_R4_FADE_ATR15","A5_R4_LATE_WEAK_PART_COVER",
           "AR2_R5_LATE_WEAK_PART_COVER","AR3_R4_LATE_COVER_CONSERVATIVE",
           "AR6_R5_VOTES_COVER_PACED","AR7_R4_LATE_COVER_PACED","AR8_R5_VOTES_COVER_CONSERVATIVE"]
    ledger({"event":"PREDECLARE_DIAGNOSTIC","id":"COVER_EXECUTION_FRAGILITY",
            "names":names,"extra_cover_bps":[5,10,25,50],
            "purpose":"Subtract an additional adverse price concession from actual partial covers only; fixed quantities and subsequent states, no invented quote or liquidity model"})
    out={}
    for name in names:
        r=read(ROOT/"results"/(name+"_IS.json"))
        detail=read(ROOT/"details"/(name+"_IS.json"))
        control=read(ROOT/"results"/(r["spec"]["control"]+"_IS.json"))
        legs=[x for x in detail["legs"] if x["reason"]=="half_cover"]
        notional=sum(x["shares"]*x["exit"] for x in legs)
        gain=r["metrics"]["total_pnl"]-control["metrics"]["total_pnl"]
        month=defaultdict(float)
        for leg in legs:month[leg["exit_ts"][:7]]+=leg["shares"]*leg["exit"]
        out[name]={"control":r["spec"]["control"],"half_covers":len(legs),"cover_notional":notional,
                   "baseline_increment":gain,"extra_adverse_cover_bps_to_erase_increment":10000*gain/notional if notional else None,
                   "increment_after_extra_cover_bps":{str(b):gain-notional*b/10000 for b in (5,10,25,50)},
                   "calendar_cover_notional":dict(month),
                   "interpretation":"For combined sizing policies, this is the whole-policy increment, not a clean causal attribution to covers alone."}
    dump(REPO_ROOT/"reports/cg_arrow003_cover_execution.json",{"timestamp":stamp(),"books":out,
          "scope":"IS fixed-execution-ledger sensitivity; baseline spread and commissions already included; no assumptions about actual fill capacity"})
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"COVER_EXECUTION_FRAGILITY","books":len(out),
            "result_file":"reports/cg_arrow003_cover_execution.json"})
    for n,r in out.items():print(n,"50bps increment",round(r["increment_after_extra_cover_bps"]["50"],2))


def coverage():
    authorize("IS")
    ledger({"event":"PREDECLARE_DIAGNOSTIC","id":"C1_MISSING_LIFECYCLE_COVERAGE",
        "purpose":"Use existing copied eligibility and ingest status to classify all working R4 missing backstops and terminal gaps. Do not acquire data, alter selections, infer missing prices or exclude any trade."})
    detail=read(ROOT/"details/R4_IS.json")
    symbols=sorted({p["symbol"] for p in detail["positions"]})
    eligibility={}
    manifest={}
    source_counts={}
    for source in ("virgin","full"):
        ef=REPO_ROOT/"data"/source/"eligibility.parquet"
        mf=REPO_ROOT/"data"/source/"manifest.parquet"
        e=pl.scan_parquet(ef).filter(pl.col("symbol").is_in(symbols)).select("symbol","session_date","eligible","exclude_reason").collect()
        m=pl.scan_parquet(mf).filter(pl.col("symbol").is_in(symbols)).select("symbol","session_date","status","rows").collect()
        eligibility[source]={(r["session_date"].isoformat(),r["symbol"]):r for r in e.iter_rows(named=True)}
        manifest[source]={(r["session_date"].isoformat(),r["symbol"]):r for r in m.iter_rows(named=True)}
        source_counts[source]={"eligibility_rows_consulted":e.height,"manifest_rows_consulted":m.height,
                               "eligibility_sha256":digest(ef),"manifest_sha256":digest(mf)}
    caches={d.isoformat():read(ROOT/"summaries"/(d.isoformat()+".json")) for d in SCORE}
    missing=[]
    for p in detail["positions"]:
        if p["due_index"]>=len(FEATS):continue
        d=FEATS[p["due_index"]]
        if d>SCORE[-1]:continue
        rec=caches[d.isoformat()].get(p["symbol"])
        if rec and rec.get("entry_ts"):continue
        reasons={}
        for source in eligibility:
            e=eligibility[source].get((d.isoformat(),p["symbol"]))
            m=manifest[source].get((d.isoformat(),p["symbol"]))
            reasons[source]={"eligible":e["eligible"] if e else None,
                             "exclusion_reason":e["exclude_reason"] if e else "not_in_table",
                             "ingest_status":m["status"] if m else "not_in_manifest"}
        missing.append({"symbol":p["symbol"],"signal_month":p["signal"][:7],
                        "scheduled_exit":d.isoformat(),"partial_session_present":bool(rec),"source_status":reasons})
    terminal=[]
    for symbol in sorted({p["symbol"] for p in detail["terminal"]}):
        ps=[p for p in detail["terminal"] if p["symbol"]==symbol]
        last=max(p["last_mark_date"] for p in ps)
        reasons={}
        for source in eligibility:
            ec=Counter()
            mc=Counter()
            for d in SCORE:
                if d.isoformat()<=last:continue
                e=eligibility[source].get((d.isoformat(),symbol))
                m=manifest[source].get((d.isoformat(),symbol))
                ec[(e["exclude_reason"] or "eligible") if e else "not_in_table"]+=1
                mc[m["status"] if m else "not_in_manifest"]+=1
            reasons[source]={"eligibility_reason_sessions":dict(ec),"ingest_status_sessions":dict(mc)}
        terminal.append({"symbol":symbol,"tickets":len(ps),"last_observation_date":last,
                         "last_observation_above_80":all(p["mark"]>80 for p in ps),"source_status":reasons})
    output={"timestamp":stamp(),"scope":"IS-owned R4 lifecycle; data-quality audit only",
            "source_counts":source_counts,"missing_backstops":missing,"terminal_symbols":terminal,
            "terminal_tickets":len(detail["terminal"]),"terminal_tickets_last_mark_above_80":sum(p["mark"]>80 for p in detail["terminal"]),
            "interpretation":"Copied acquisition eligibility was bounded ($80 virgin/$50 full), unlike a complete held-position lifecycle service. Missingness can therefore be associated with rising prices adverse to shorts. This table describes coverage, not actual unobserved returns or executable prices. Conditional mechanism increments do not certify absolute profitability."}
    from research.cg_arrow003_minute import remaining_shares,ET
    from research.cg_arrow003_data import adjustment_factor,close_time
    from datetime import datetime
    legs=defaultdict(list)
    for leg in detail["legs"]:legs[leg["ticket_id"]].append(leg)
    marks={}
    missing_sessions=defaultdict(lambda:{"position_sessions":0,"gross_dollar_sessions":0.})
    for d in SCORE:
        iso=d.isoformat()
        for sym in symbols:
            if sym in marks:marks[sym]*=adjustment_factor(sym,FEATS[INDEX[d]-1],d)
            rec=caches[iso].get(sym)
            if rec:marks[sym]=rec["close"]
        for p in detail["positions"]:
            q=remaining_shares(p,legs[p["id"]],datetime.combine(d,close_time(d),ET))
            if q<=0 or caches[iso].get(p["symbol"]):continue
            states=[eligibility[source].get((iso,p["symbol"])) for source in eligibility]
            if any(e and e["eligible"] for e in states):bucket="eligible_but_no_usable_minute_tape"
            elif any(e and e["exclude_reason"]=="prior_close_out_of_range" for e in states):bucket="documented_price_range_exclusion"
            elif any(states):bucket="other_documented_exclusion"
            else:bucket="no_copied_eligibility_row"
            missing_sessions[bucket]["position_sessions"]+=1
            missing_sessions[bucket]["gross_dollar_sessions"]+=q*marks[p["symbol"]]
    m=read(ROOT/"results/R4_IS.json")["metrics"]
    if sum(v["position_sessions"] for v in missing_sessions.values())!=m["counters"]["stale_position_sessions"]:
        raise AssertionError("Stale coverage counts do not reconcile")
    if abs(sum(v["gross_dollar_sessions"] for v in missing_sessions.values())-m["stale_exposure_dollar_sessions"])>1e-6:
        raise AssertionError("Stale coverage gross does not reconcile")
    output["all_stale_position_sessions_by_source_status"]=dict(missing_sessions)
    dump(REPO_ROOT/"reports/cg_arrow003_lifecycle_coverage.json",output)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"C1_MISSING_LIFECYCLE_COVERAGE",
            "missing_backstops":len(missing),"terminal_symbols":len(terminal),
            "result_file":"reports/cg_arrow003_lifecycle_coverage.json"})
    print("Missing scheduled exits:",len(missing),"terminal names:",len(terminal),
          "terminal tickets last marked above80:",output["terminal_tickets_last_mark_above_80"])
    for row in terminal:
        print(row["symbol"],row["source_status"]["virgin"])
    print("All stale lifecycle coverage:",dict(missing_sessions))


def interaction():
    authorize("IS")
    ledger({"event":"PREDECLARE_DIAGNOSTIC","id":"VOTES_COVER_INTERACTION_AND_MISSINGNESS",
        "purpose":"Attribute already-completed policies, with no new trading rule: base, votes-only, cover-only and combined policy. Check non-additivity and whether advancing-day-vote gains also exist on complete histories."})
    names=["R5","A6_R5_STALL_VOTES","AR2_R5_LATE_WEAK_PART_COVER","AR5_R5_VOTES_LATE_COVER",
           "C1_R5_PACED","AR4_R5_VOTES_PACED","AR9_R5_LATE_COVER_PACED","AR6_R5_VOTES_COVER_PACED"]
    records={n:read(ROOT/"results"/(n+"_IS.json")) for n in names}
    details={n:read(ROOT/"details"/(n+"_IS.json")) for n in names}
    out={"timestamp":stamp(),"mode":"IS completed-policy attribution","interactions":{},"votes_missingness":{},"borrow_increments":{}}
    for key,ids in {"unpaced":names[:4],"paced":names[4:]}.items():
        b,v,c,both=ids
        profits=[records[n]["metrics"]["total_pnl"] for n in ids]
        delta=profits[3]-profits[1]-profits[2]+profits[0]
        tickets=set().union(*(details[n]["ticket_pnl"] for n in ids))
        symbols=defaultdict(float)
        buckets=defaultdict(lambda:{"tickets":0,"interaction":0.})
        base_positions={p["id"]:p for p in details[b]["positions"]}
        vote_positions={p["id"]:p for p in details[v]["positions"]}
        cover_ids={leg["ticket_id"] for leg in details[c]["legs"] if leg["reason"]=="half_cover"}
        for t in tickets:
            values=[details[n]["ticket_pnl"].get(t,0.) for n in ids]
            interaction=values[3]-values[1]-values[2]+values[0]
            symbols[t.split("/",1)[1]]+=interaction
            q0=base_positions.get(t,{}).get("initial_shares",0)
            q1=vote_positions.get(t,{}).get("initial_shares",0)
            state=("upsized" if q1>q0 else "downsized" if q1<q0 else "unchanged")
            bucket=state+("_covered" if t in cover_ids else "_not_covered")
            buckets[bucket]["tickets"]+=1
            buckets[bucket]["interaction"]+=interaction
        if abs(sum(symbols.values())-delta)>1e-7:raise AssertionError("Interaction attribution does not reconcile")
        out["interactions"][key]={"books":ids,"votes_increment":profits[1]-profits[0],
             "cover_increment":profits[2]-profits[0],"combined_increment":profits[3]-profits[0],
             "interaction":delta,"buckets":dict(buckets),
             "largest_interaction_symbols":sorted(symbols.items(),key=lambda x:abs(x[1]),reverse=True)[:8],
             "interpretation":"Combined benefit is not the sum of independent edges. Changes to covered share quantities and, for paced books, capacity interactions create non-additivity."}
    b=details["R5"]
    v=details["A6_R5_STALL_VOTES"]
    for feature in ("vol20","volume_ratio","ret3"):
        buckets=defaultdict(lambda:{"tickets":0,"increment":0.,"candidate_pnl":0.})
        for p in v["positions"]:
            state="missing" if p["feature"].get(feature) is None else "available"
            buckets[state]["tickets"]+=1
            buckets[state]["increment"]+=v["ticket_pnl"][p["id"]]-b["ticket_pnl"].get(p["id"],0.)
            buckets[state]["candidate_pnl"]+=v["ticket_pnl"][p["id"]]
        out["votes_missingness"][feature]=dict(buckets)
    for n in names[1:]:
        c="C1_R5_PACED" if n in names[5:] else "R5"
        out["borrow_increments"][n]={"control":c,"scenario_profit_increments":{
            k:value-records[c]["metrics"]["scenarios"][k] for k,value in records[n]["metrics"]["scenarios"].items()}}
    dump(REPO_ROOT/"reports/cg_arrow003_interaction.json",out)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"VOTES_COVER_INTERACTION_AND_MISSINGNESS",
            "result_file":"reports/cg_arrow003_interaction.json","votes_missingness":out["votes_missingness"],
            "interaction":{k:v["interaction"] for k,v in out["interactions"].items()}})
    print("Interactions:",{k:round(v["interaction"],2) for k,v in out["interactions"].items()})
    print("Votes history attribution:",out["votes_missingness"])


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["stale","execution","coverage","interaction"])
    p.add_argument("--workers",type=int,default=8)
    a=p.parse_args()
    if a.command=="stale":dynamic_stale(a.workers)
    elif a.command=="execution":execution()
    elif a.command=="coverage":coverage()
    else:interaction()
