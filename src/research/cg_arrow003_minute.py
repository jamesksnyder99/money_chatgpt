"""Synchronized one-minute risk audit; no execution or policy changes.

Every symbol is valued at the same minute-close clock, carrying only last-known
marks across absent observations. Separate stock highs are never added together.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import date,datetime,time,timedelta
import json
import math
from zoneinfo import ZoneInfo

from research.cg_arrow003_data import (
    ROOT,REPO_ROOT,SCORE,FEATS,INDEX,read,dump,digest,stamp,read_bars,
    adjustment_factor,close_time,history_asof,
)
from research.cg_arrow003_lab import authorize,ledger

ET=ZoneInfo("America/New_York")


def equity_drawdown(paths):
    """Chronological global HWM, including negative-equity stress paths."""
    high=100000.
    dollars=percent=0.
    for path in paths:
        for equity in path:
            high=max(high,equity)
            dollars=min(dollars,equity-high)
            percent=min(percent,equity/high-1)
    return dollars,percent


def effective_entry(p):
    """Entry timestamps in the inherited ledger name a bar START; fill is its close."""
    return datetime.fromisoformat(p["entry_ts"])+timedelta(minutes=1)


def effective_exit(leg):
    ts=datetime.fromisoformat(leg["exit_ts"])
    return ts+timedelta(minutes=1) if leg["reason"]=="backstop" else ts


def remaining_shares(position,legs,when):
    if effective_entry(position)>when:return 0.0
    entry_d=date.fromisoformat(position["fill_date"])
    d=when.date()
    q=position.get("original_shares",position["initial_shares"])/adjustment_factor(position["symbol"],entry_d,d)
    for leg in legs:
        # A minute-close sample includes close executions, immediately BEFORE
        # an open execution at the next bar's identically labeled boundary.
        passed=effective_exit(leg)<=when if leg["reason"]=="backstop" else effective_exit(leg)<when
        if passed:
            ld=effective_exit(leg).date()
            q-=leg["shares"]/adjustment_factor(position["symbol"],ld,d)
    return max(0.0,q)


def day_job(job):
    iso,books,prior_marks=job[:3]
    accounts=job[3] if len(job)>3 else {}
    d=date.fromisoformat(iso)
    # Books contain only positions overlapping this day, not future entries.
    symbols=sorted({p["symbol"] for b in books.values() for p,_ in b})
    tapes={}
    source_counts=defaultdict(int)
    for sym in symbols:
        df,source=read_bars(d,sym)
        if df is not None:
            tapes[sym]={row["bar_start"]+timedelta(minutes=1):float(row["close"])
                        for row in df.select("bar_start","close").iter_rows(named=True)}
            source_counts["minute_tapes"]+=1
        else:
            tapes[sym]={}
            source_counts["missing_tapes"]+=1
    start=datetime.combine(d,time(9,31),ET)
    end=datetime.combine(d,close_time(d),ET)
    times=[]
    cur=start
    while cur<=end:
        times.append(cur)
        cur+=timedelta(minutes=1)
    marks=dict(prior_marks)
    last_update={sym:None for sym in symbols}
    records={name:[] for name in books}
    cash={name:accounts[name]["cash"] if name in accounts else None for name in books}
    events={}
    cursors={name:0 for name in books}
    for name,positions in books.items():
        flow=[]
        for p,legs in positions:
            if effective_entry(p).date()==d:
                q=p.get("original_shares",p["initial_shares"])
                px=p.get("original_entry",p["entry"])
                flow.append((effective_entry(p),0,q*(px-(.005+max(.01,.001*px)))))
            for leg in legs:
                if effective_exit(leg).date()==d:
                    px=leg["exit"]
                    flow.append((effective_exit(leg),0 if leg["reason"]=="backstop" else 1,
                                 -leg["shares"]*(px+.005+max(.01,.001*px))))
        events[name]=sorted(flow)
    for when in times:
        for sym in symbols:
            if when in tapes[sym]:
                marks[sym]=tapes[sym][when]
                last_update[sym]=when
        for name,positions in books.items():
            if cash[name] is not None:
                while cursors[name]<len(events[name]):
                    ts,phase,amount=events[name][cursors[name]]
                    if ts>when or (ts==when and phase==1):break
                    cash[name]+=amount
                    cursors[name]+=1
            gross=0.0
            symbol_gross=defaultdict(float)
            stale=0.0
            fresh=0.0
            tickets=0
            for p,legs in positions:
                q=remaining_shares(p,legs,when)
                if q<=1e-9:continue
                tickets+=1
                sym=p["symbol"]
                # On the entry minute its close is available; prior marking cannot
                # create a fill when tape is missing.
                px=marks.get(sym)
                if px is None:
                    px=p.get("original_entry",p["entry"])*adjustment_factor(sym,date.fromisoformat(p["fill_date"]),d)
                value=q*px
                gross+=value
                symbol_gross[sym]+=value
                if last_update[sym] is None:stale+=value
                if last_update[sym]==when:fresh+=value
            largest=max(symbol_gross.values(),default=0.0)
            equity=cash[name]-gross if cash[name] is not None else None
            records[name].append({"timestamp":when.isoformat(),"gross":gross,"largest_symbol_gross":largest,
                     "equity":equity,"gross_to_equity":gross/equity if equity is not None and equity>0 else None,
                     "largest_symbol_equity_fraction":largest/equity if equity is not None and equity>0 else None,
                     "stale_since_prior_session_gross":stale,"fresh_current_minute_gross":fresh,
                     "tickets":tickets,"symbols":len(symbol_gross),
                     "joint_stress_others10_largest50":-.1*gross-.4*largest})
    out={}
    for name,rows in records.items():
        peak=max(rows,key=lambda r:r["gross"])
        eq=[r["equity"] for r in rows if r["equity"] is not None]
        hwm=accounts[name]["equity"] if name in accounts else None
        dd=ddpct=0.
        for value in eq:
            hwm=max(hwm,value)
            dd=min(dd,value-hwm)
            if hwm>0:ddpct=min(ddpct,value/hwm-1)
        out[name]={"date":iso,"minute_peak":peak,"end_of_session_gross":rows[-1]["gross"],
                   "_equity_path":eq,"nonpositive_equity_minutes":sum(value<=0 for value in eq),
                   "end_of_session_equity":rows[-1]["equity"],
                   "max_intraday_equity":max(eq) if eq else None,"min_intraday_equity":min(eq) if eq else None,
                   "within_day_max_drawdown":dd if eq else None,"within_day_max_drawdown_percent":ddpct if eq else None,
                   "peak_gross_to_equity":max((r["gross_to_equity"] for r in rows if r["gross_to_equity"] is not None),default=None),
                   "largest_symbol_equity_fraction":max((r["largest_symbol_equity_fraction"] for r in rows if r["largest_symbol_equity_fraction"] is not None),default=None),
                   "minutes_above_130k":sum(r["gross"]>130000 for r in rows),
                   "exposure_dollar_minutes_above_130k":sum(max(0,r["gross"]-130000) for r in rows),
                   "max_symbol_gross":max(r["largest_symbol_gross"] for r in rows),
                   "worst_joint_stress":min(r["joint_stress_others10_largest50"] for r in rows)}
    path=ROOT/"minute_risk"/(iso+"_"+"_".join(sorted(books))+".json")
    # Avoid long Windows path names for large frozen batches.
    import hashlib
    path=ROOT/"minute_risk"/(iso+"_"+hashlib.sha256("|".join(sorted(books)).encode()).hexdigest()[:16]+".json")
    dump(path,{"books":records,"source_counts":dict(source_counts)})
    return iso,out,{"path":path.relative_to(REPO_ROOT).as_posix(),"sha256":digest(path),"source_counts":dict(source_counts)}


def audit(mode,ids,workers=8,all_days=False):
    authorize(mode)
    details={name:read(ROOT/"details"/(name+f"_{mode}.json")) for name in ids}
    chosen=set()
    if all_days:
        chosen=set(SCORE)
    else:
        for name,d in details.items():
            daily=sorted(d["daily"],key=lambda r:r["gross"],reverse=True)
            for row in daily[:8]:
                index=SCORE.index(date.fromisoformat(row["date"]))
                chosen.update(SCORE[max(0,index-1):min(len(SCORE),index+2)])
    days=sorted(chosen)
    # Compute previous-session carry marks causally for every held symbol. Missing
    # data is never backfilled from a later observation.
    symbols={p["symbol"] for d in details.values() for p in d["positions"]}
    previous_by_day={}
    marks={}
    for day in FEATS:
        if day in chosen:
            previous_by_day[day]=dict(marks)
        cache=ROOT/"summaries"/(day.isoformat()+".json")
        rows=read(cache) if cache.exists() else {}
        for sym in symbols:
            factor=adjustment_factor(sym,FEATS[INDEX[day]-1],day) if INDEX[day] else 1
            if sym in marks:marks[sym]*=factor
            if rows.get(sym):marks[sym]=rows[sym]["close"]
        if day in chosen:
            # Prior session marks must be expressed in today's split units.
            previous_by_day[day]={sym:price*adjustment_factor(sym,FEATS[INDEX[day]-1],day)
                                   for sym,price in previous_by_day[day].items()}
    jobs=[]
    for d in days:
        books={}
        for name,detail in details.items():
            legs=defaultdict(list)
            for leg in detail["legs"]:legs[leg["ticket_id"]].append(leg)
            positions=[]
            start=datetime.combine(d,time(9,30),ET)
            end=datetime.combine(d,close_time(d),ET)
            for p in detail["positions"]:
                ls=legs[p["id"]]
                if effective_entry(p)<=end and (remaining_shares(p,ls,start)>1e-9 or effective_entry(p).date()==d):
                    positions.append((p,ls))
            books[name]=positions
        accounts={}
        for name,detail in details.items():
            i=SCORE.index(d)
            previous=detail["daily"][i-1] if i else {"equity":100000.,"gross":0.}
            accounts[name]={"cash":previous["equity"]+previous["gross"],"equity":previous["equity"]}
        jobs.append((d.isoformat(),books,previous_by_day[d],accounts))
    combined={name:[] for name in ids}
    local=[]
    import time as timer
    started=timer.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs=[pool.submit(day_job,j) for j in jobs]
        for n,f in enumerate(as_completed(fs),1):
            iso,out,provenance=f.result()
            local.append(provenance)
            for name,row in out.items():
                expected=next(r["gross"] for r in details[name]["daily"] if r["date"]==iso)
                if abs(row["end_of_session_gross"]-expected)>1e-6:
                    raise AssertionError(f"Synchronized minute/EOD mismatch {name} {iso}: {row['end_of_session_gross']-expected}")
                expected_eq=next(r["equity"] for r in details[name]["daily"] if r["date"]==iso)
                if abs(row["end_of_session_equity"]-expected_eq)>1e-6:
                    raise AssertionError(f"Minute cash/EOD equity mismatch {name} {iso}")
                combined[name].append(row)
            if n%16==0 or n==len(fs):
                spent=timer.monotonic()-started
                print(f"{stamp()} synchronized-minute audit {n}/{len(fs)} ETA~{spent/n*(len(fs)-n):.1f}s",flush=True)
    aggregate={}
    for name,rows in combined.items():
        rows.sort(key=lambda r:r["date"])
        peak=max(rows,key=lambda r:r["minute_peak"]["gross"])["minute_peak"]
        dd,ddpct=equity_drawdown(r.pop("_equity_path") for r in rows)
        aggregate[name]={"synchronized_minute_peak":peak,"sessions_audited":len(rows),
                         "minute_sampled_max_drawdown":dd,"minute_sampled_max_drawdown_percent":ddpct,
                         "peak_gross_to_equity":max((r["peak_gross_to_equity"] for r in rows if r["peak_gross_to_equity"] is not None),default=None),
                         "largest_symbol_equity_fraction":max((r["largest_symbol_equity_fraction"] for r in rows if r["largest_symbol_equity_fraction"] is not None),default=None),
                         "nonpositive_equity_minutes":sum(r["nonpositive_equity_minutes"] for r in rows),
                         "minutes_above_130k":sum(r["minutes_above_130k"] for r in rows),
                         "dollar_minutes_above_130k":sum(r["exposure_dollar_minutes_above_130k"] for r in rows),
                         "max_symbol_gross":max(r["max_symbol_gross"] for r in rows),
                         "worst_joint_stress":min(r["worst_joint_stress"] for r in rows),"days":rows}
    payload={"timestamp":stamp(),"mode":mode,"all_calendar_sessions":all_days,"books":aggregate,
             "clock":"Synchronized minute closes including close fills, immediately before next-open executions at the same boundary; missing intraday observations carry last-known marks. Cash credits short-sale proceeds and debits actual cover cash plus baseline costs.",
             "limitation":"Minute-close marked peak is not tick-by-tick maximum; stale positions remain valuations. Peak-period sample is not full-calendar maximum unless all_calendar_sessions is true.",
             "local_provenance":local,"wall_seconds":timer.monotonic()-started}
    dump(REPO_ROOT/"reports"/f"cg_arrow003_minute_{mode.lower()}.json",payload)
    ledger({"event":"MINUTE_RISK_AUDIT_COMPLETE","mode":mode,"ids":ids,"sessions":len(days),
            "all_days":all_days,"wall_seconds":payload["wall_seconds"]})
    print(json.dumps({name:{k:v for k,v in m.items() if k!="days"} for name,m in aggregate.items()},indent=2))


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["IS","ALL"],default="IS")
    p.add_argument("--ids",nargs="+",required=True)
    p.add_argument("--workers",type=int,default=8)
    p.add_argument("--all-days",action="store_true")
    a=p.parse_args()
    audit(a.mode,a.ids,a.workers,a.all_days)


if __name__=="__main__":main()
