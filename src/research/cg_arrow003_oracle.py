"""Independent cash-minus-short-liability audit of saved execution ledgers.

The strategy scorer uses marked PnL increments. This verifier independently
credits entry sale proceeds to cash and debits cover cash, then subtracts the
remaining short liability. It verifies accounting, not the truth of stale marks.
"""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import date,datetime,timedelta
import argparse
import time

from research.cg_arrow003_data import ROOT,REPO_ROOT,FEATS,SCORE,INDEX,read,dump,digest,adjustment_factor,stamp
from research.cg_arrow003_lab import authorize,ledger


def fee(price):
    return .005+max(.01,.001*price)


def verify(name,mode):
    r=read(ROOT/"results"/(name+f"_{mode}.json"))
    path=REPO_ROOT/r["detail_path"]
    if digest(path)!=r["detail_sha256"]:raise AssertionError("Input ledger hash mismatch")
    detail=read(path)
    positions={p["id"]:p for p in detail["positions"]}
    if len(positions)!=len(detail["positions"]):raise AssertionError("Duplicate ticket id")
    events=defaultdict(list)
    for p in positions.values():
        if "original_shares" not in p and adjustment_factor(p["symbol"],date.fromisoformat(p["fill_date"]),SCORE[-1])!=1:
            raise AssertionError("Original entry units required for a split-bearing ledger")
        events[p["fill_date"]].append((datetime.fromisoformat(p["entry_ts"])+timedelta(minutes=1),"entry",p))
    for leg in detail["legs"]:
        ts=datetime.fromisoformat(leg["exit_ts"])
        if leg["reason"]=="backstop":ts+=timedelta(minutes=1)
        events[ts.date().isoformat()].append((ts,"exit",leg))
    cash=100000.
    active={}
    max_equity_error=max_gross_error=0.
    execution_checks=0
    reference={x["date"]:x for x in detail["daily"]}
    for day in SCORE:
        iso=day.isoformat()
        summaries=read(ROOT/"summaries"/(iso+".json"))
        for ticket,p in active.items():
            f=adjustment_factor(p["symbol"],FEATS[INDEX[day]-1],day)
            p["qty"]/=f
            p["mark"]*=f
        for ts,kind,record in sorted(events[iso],key=lambda x:(x[0],x[1])):
            sym=record["symbol"]
            observed=summaries.get(sym)
            if not observed:raise AssertionError("Executable event without real session observations")
            if kind=="entry":
                p=record
                qty=p.get("original_shares",p["initial_shares"])
                price=p.get("original_entry",p["entry"])
                if observed["entry_ts"]!=p["entry_ts"] or abs(observed["entry_px"]-price)>1e-9:
                    raise AssertionError("Entry is not the scheduled observed final-minute fill")
                if p["id"] in active:raise AssertionError("Ticket entered twice")
                cash+=qty*(price-fee(price))
                active[p["id"]]={"symbol":sym,"qty":qty,"mark":price,"entry_clock":ts}
            else:
                leg=record
                p=active.get(leg["ticket_id"])
                if not p or p["entry_clock"]>=ts:raise AssertionError("Cover precedes entry")
                qty=leg["shares"]
                if qty>p["qty"]+1e-8:raise AssertionError("Cover exceeds remaining short quantity")
                reason=leg["reason"]
                if reason=="backstop":
                    valid=observed.get("entry_ts")==leg["exit_ts"] and abs(observed["entry_px"]-leg["exit"])<1e-9
                elif reason=="delayed_backstop":
                    valid=observed.get("first_ts")==leg["exit_ts"] and abs(observed["open"]-leg["exit"])<1e-9
                elif reason=="half_cover" and r["spec"].get("cover_clock","checkpoint")=="checkpoint":
                    valid=observed.get("next_ts")==leg["exit_ts"] and abs(observed["next_open"]-leg["exit"])<1e-9
                    if valid and ts.hour*60+ts.minute<15*60+56:
                        raise AssertionError("Cover uses an unfinished decision minute")
                elif reason=="half_cover":
                    from research.cg_arrow003_data import minute_observations
                    valid=any(x["execution"]==leg["exit_ts"] and abs(x["fill"]-leg["exit"])<1e-9
                              and datetime.fromisoformat(x["decision"])+timedelta(minutes=1)<=ts
                              for x in minute_observations(iso,sym))
                else:raise AssertionError("Unknown exit reason")
                if not valid:raise AssertionError("Cover has no matching executable observation")
                cash-=qty*(leg["exit"]+fee(leg["exit"]))
                p["qty"]-=qty
                if p["qty"]<1e-8:del active[leg["ticket_id"]]
            execution_checks+=1
        gross=0.
        for p in active.values():
            rec=summaries.get(p["symbol"])
            if rec:p["mark"]=rec["close"]
            gross+=p["qty"]*p["mark"]
        equity=cash-gross
        max_equity_error=max(max_equity_error,abs(equity-reference[iso]["equity"]))
        max_gross_error=max(max_gross_error,abs(gross-reference[iso]["gross"]))
        if max_equity_error>1e-6 or max_gross_error>1e-6:
            raise AssertionError(f"Independent cash/liability mismatch {name} {iso}: {max_equity_error}, {max_gross_error}")
    if set(active)!={p["id"] for p in detail["terminal"]}:raise AssertionError("Terminal inventory mismatch")
    return {"book":name,"mode":mode,"calendar_sessions":len(SCORE),"observed_executions_verified":execution_checks,
            "terminal_tickets":len(active),"max_cash_equity_error":max_equity_error,
            "max_marked_gross_error":max_gross_error,"detail_sha256":r["detail_sha256"]}


def audit(mode,workers=8):
    manifest=authorize(mode)
    names=sorted(p.stem[:-3] for p in (ROOT/"results").glob("*_IS.json")) if mode=="IS" else [s["id"] for s in manifest["specs"]]
    start=time.monotonic()
    results=[]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs=[pool.submit(verify,n,mode) for n in names]
        for i,f in enumerate(as_completed(fs),1):
            results.append(f.result())
            if i%8==0 or i==len(fs):
                spent=time.monotonic()-start
                print(f"{stamp()} independent cash audit {i}/{len(fs)} ETA~{spent/i*(len(fs)-i):.1f}s",flush=True)
    payload={"timestamp":stamp(),"mode":mode,"books":sorted(results,key=lambda x:x["book"]),
             "wall_seconds":time.monotonic()-start,
             "method":"Entry sale proceeds minus cover cash and independent per-side cost formula, less open short liabilities; verify every saved fill against its actual observation and timing. Same input data, independent accounting identity.",
             "limitation":"Agreement cannot certify unobserved prices, corporate-action completeness, stock loans, dividends, actual fills or economic edge."}
    dump(REPO_ROOT/"reports"/f"cg_arrow003_cash_oracle_{mode.lower()}.json",payload)
    ledger({"event":"INDEPENDENT_CASH_AUDIT_COMPLETE","mode":mode,"book_count":len(results),
            "wall_seconds":payload["wall_seconds"],"max_equity_error":max(x["max_cash_equity_error"] for x in results)})


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=["IS","ALL"],default="IS")
    p.add_argument("--workers",type=int,default=8)
    a=p.parse_args()
    audit(a.mode,a.workers)
