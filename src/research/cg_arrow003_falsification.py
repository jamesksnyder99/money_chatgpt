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
       "AR2_R5_LATE_WEAK_PART_COVER","C3_R5_TAPER_PACED","A3_R4_DRAWDOWN_NEW"]
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
    dump(REPO_ROOT/"reports/cg_arrow003_lifecycle_coverage.json",output)
    ledger({"event":"DIAGNOSTIC_COMPLETE","id":"C1_MISSING_LIFECYCLE_COVERAGE",
            "missing_backstops":len(missing),"terminal_symbols":len(terminal),
            "result_file":"reports/cg_arrow003_lifecycle_coverage.json"})
    print("Missing scheduled exits:",len(missing),"terminal names:",len(terminal),
          "terminal tickets last marked above80:",output["terminal_tickets_last_mark_above_80"])
    for row in terminal:
        print(row["symbol"],row["source_status"]["virgin"])


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["stale","execution","coverage"])
    p.add_argument("--workers",type=int,default=8)
    a=p.parse_args()
    if a.command=="stale":dynamic_stale(a.workers)
    elif a.command=="execution":execution()
    else:coverage()
