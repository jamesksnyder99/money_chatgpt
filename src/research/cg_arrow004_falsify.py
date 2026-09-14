"""Predetermined missing-price stresses and lifecycle coverage diagnostics."""
from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import date
import argparse,time as timer
import polars as pl
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,stamp,adjustment_factor
from research.cg_arrow004_lab import Spec,score,authorize,ledger,load_prepared

def stress_job(job):
    raw,shock,ranks,summaries=job;s=Spec(**raw);m,_=score(s,'IS',ranks,summaries,stale_shock=shock)
    keys=['total_pnl','per_day','max_dd','red_loss_sum','worst_month','worst_day','avg_exposure','peak_exposure','utilization','terminal_stale_gross','counters']
    return s.id,shock,{k:m[k] for k in keys}

def stale(ids,workers):
    authorize('IS');ranks,summaries=load_prepared('IS',workers)
    specs=[read(ROOT/'results'/(n+'_IS.json'))['spec'] for n in ids];shocks=[0.,.1,.5]
    ledger({'event':'PREDECLARE_DIAGNOSTIC','id':'DYNAMIC_STALE_'+str(len(ids)), 'ids':ids,'adverse_fractions':shocks,
            'rule':'Noncompounding adverse errors to last observed marks only when no current valuation; shorts up, longs down; recompute equity/headroom; no invented executable fills'})
    out={};start=timer.monotonic()
    with ProcessPoolExecutor(max_workers=min(workers,8)) as pool:
        fs=[pool.submit(stress_job,(s,x,ranks,summaries)) for s in specs for x in shocks]
        for n,f in enumerate(as_completed(fs),1):
            name,x,m=f.result();out.setdefault(name,{})[str(x)]=m
            if n%8==0 or n==len(fs):print(f'{stamp()} adverse stale stress {n}/{len(fs)} ETA~{(timer.monotonic()-start)/n*(len(fs)-n):.1f}s',flush=True)
    for name,row in out.items():
        base=read(ROOT/'results'/(name+'_IS.json'))['metrics']
        if abs(row['0.0']['total_pnl']-base['total_pnl'])>1e-6:raise AssertionError('Zero shock must reproduce baseline')
    path=REPO_ROOT/'reports/cg_arrow004_stale_stress.json'
    previous=read(path).get('books',{}) if path.exists() else {};previous.update(out)
    dump(path,{'timestamp':stamp(),'books':previous,'interpretation':'Hypothetical adverse missing-mark errors, not reconstructed prices or probability bounds; outcomes remain conditional'})
    ledger({'event':'DIAGNOSTIC_COMPLETE','id':'DYNAMIC_STALE_'+str(len(ids)),'jobs':len(specs)*len(shocks)})

def coverage(ids,mode='IS'):
    authorize(mode);_,summaries=load_prepared(mode);details={n:read(ROOT/'details'/(n+'_'+mode+'.json')) for n in ids}
    symbols={p['symbol'] for d in details.values() for p in d['positions']};elig={}
    for source in ('virgin','full'):
        df=pl.read_parquet(REPO_ROOT/f'data/{source}/eligibility.parquet').filter(pl.col('symbol').is_in(sorted(symbols)))
        for r in df.select('symbol','session_date','eligible','exclude_reason','prior_close').iter_rows(named=True):elig.setdefault((r['session_date'].isoformat(),r['symbol']),[]).append(r)
    out={}
    for n,d in details.items():
        exits={l['ticket_id']:l['exit_ts'][:10] for l in d['legs']};groups=defaultdict(lambda:{'position_sessions':0,'gross_dollar_sessions':0.})
        for p in d['positions']:
            observed=p['fill_date'];mark=p['original_entry'];fill=date.fromisoformat(p['fill_date'])
            for day in d['daily']:
                iso=day['date']
                if iso<p['fill_date'] or (p['id'] in exits and iso>=exits[p['id']]):continue
                today=date.fromisoformat(iso);rec=summaries.get((iso,p['symbol']))
                if rec:observed=iso;mark=rec['close'];continue
                states=elig.get((iso,p['symbol']),[])
                if any(r['eligible'] for r in states):cause='eligible_but_missing_tape'
                elif any(r['exclude_reason']=='prior_close_out_of_range' for r in states):cause='documented_price_range_exclusion'
                elif states:cause='other_documented_exclusion'
                else:cause='no_eligibility_row'
                current=mark*adjustment_factor(p['symbol'],date.fromisoformat(observed),today)
                band='last_below_10' if current<10 else 'last_above_80' if current>80 else 'last_inside_10_80'
                rank='primary' if p['rank']<=8 else 'reserve'
                q=p['original_shares']/adjustment_factor(p['symbol'],fill,today)
                for key in (cause,band,rank):groups[key]['position_sessions']+=1;groups[key]['gross_dollar_sessions']+=q*current
        m=read(ROOT/'results'/(n+'_'+mode+'.json'))['metrics']
        source_keys=['eligible_but_missing_tape','documented_price_range_exclusion','other_documented_exclusion','no_eligibility_row']
        if sum(groups[k]['position_sessions'] for k in source_keys)!=m['counters'].get('stale_position_sessions',0):raise AssertionError('Coverage counts mismatch')
        if abs(sum(groups[k]['gross_dollar_sessions'] for k in source_keys)-m['stale_exposure_dollar_sessions'])>1e-6:raise AssertionError('Coverage gross mismatch')
        out[n]={'side':d['side'],'groups':dict(groups),'terminal_tickets':m['terminal_tickets'],'terminal_stale_gross':m['terminal_stale_gross'],
                 'missing_scheduled_exits':m['counters'].get('missing_scheduled_exit',0),'delayed_fills':m['counters'].get('delayed_exit_fills',0)}
        print(n,d['side'],'stale position-sessions',m['counters'].get('stale_position_sessions',0),'last below10',groups['last_below_10']['position_sessions'],'last above80',groups['last_above_80']['position_sessions'])
    path=REPO_ROOT/f'reports/cg_arrow004_coverage_{mode.lower()}.json';previous=read(path).get('books',{}) if path.exists() else {};previous.update(out)
    dump(path,{'timestamp':stamp(),'mode':mode,'books':previous,'interpretation':'Source reasons and last known price bands, not guesses about unobserved prices; entry eligibility is not held-position coverage'})
    ledger({'event':'COVERAGE_DIAGNOSTIC_COMPLETE','mode':mode,'ids':ids})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['stale','coverage']);p.add_argument('--ids',nargs='+',required=True);p.add_argument('--workers',type=int,default=8);p.add_argument('--mode',default='IS');a=p.parse_args()
    if a.command=='stale':stale(a.ids,a.workers)
    else:coverage(a.ids,a.mode)
