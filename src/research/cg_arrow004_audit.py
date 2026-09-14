"""IS-only mechanism attribution and independent account reconstruction."""
from __future__ import annotations
from collections import defaultdict,Counter
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import date
import argparse,statistics,time as timer
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp,SCORE,adjustment_factor
from research.cg_arrow004_lab import authorize,ledger,load_prepared,code_identity

def records(mode='IS'):
    return {p.stem[:-(len(mode)+1)]:read(p) for p in sorted((ROOT/'results').glob('*_'+mode+'.json'))}

def board():
    authorize('IS');r=records();out={}
    for n,x in r.items():
        m=x['metrics'];c=r.get(x['spec']['control'],x)['metrics'];fields=['total_pnl','red_loss_sum','worst_month','max_dd','worst_day','avg_exposure','peak_exposure','utilization']
        out[n]={'spec':x['spec'],'metrics':m,'control_differences':{k:m[k]-c[k] for k in fields},
                'disposition':'CONTROL' if x['spec']['origin']=='CONTROL' else 'ECONOMICALLY REJECTED' if m['total_pnl']<=0 else 'PROFITABLE TRADEOFF; not automatically superior'}
        print(f"{n:30s} {m['total_pnl']:10.2f} DD{m['max_dd']:10.2f} avg{m['avg_exposure']:9.2f} util{m['utilization']:.3f} delta{m['total_pnl']-c['total_pnl']:9.2f}")
    dump(REPO_ROOT/'reports/cg_arrow004_is_board.json',{'timestamp':stamp(),'policies':out})

def robustness():
    authorize('IS');r=records();out={}
    for n,x in r.items():
        if x['spec']['origin'] in {'CONTROL','DIAGNOSTIC'}:continue
        c=r.get(x['spec']['control'])
        if not c:continue
        m=x['metrics'];cm=c['metrics'];diff={k:m['months'][k]-cm['months'][k] for k in m['months']}
        d=read(REPO_ROOT/x['detail_path']);cd=read(REPO_ROOT/c['detail_path']);syms=set(d['symbol_pnl'])|set(cd['symbol_pnl'])
        contrib=sorted(((s,d['symbol_pnl'].get(s,0)-cd['symbol_pnl'].get(s,0)) for s in syms),key=lambda a:a[1],reverse=True)
        keys={p['id'] for p in d['positions']};ckeys={p['id'] for p in cd['positions']}
        out[n]={'control':x['spec']['control'],'month_differences':diff,'positive_increment_months':sum(v>0 for v in diff.values()),
          'leave_one_month_out':{k:sum(diff.values())-v for k,v in diff.items()},'top_incremental_symbols':contrib[:5],'bottom_incremental_symbols':contrib[-5:],
          'increment_without_top_symbol':sum(diff.values())-max(0,contrib[0][1]) if contrib else 0,
          'membership_overlap':len(keys&ckeys)/len(keys|ckeys) if keys|ckeys else None,
          'candidate_attribution':m['attribution'],'control_attribution':cm['attribution'],
          'primary_reserve_increment':{k:m['attribution'].get(k,{}).get('pnl',0)-cm['attribution'].get(k,{}).get('pnl',0) for k in ('primary_1_8','reserve_9_20')},
          'scenario_increments':{k:v-cm['scenarios'][k] for k,v in m['scenarios'].items() if k in cm['scenarios']},
          'interpretation':'Fragility diagnostics on inspected IS, not independent validation; no date/ticket removed from policy'}
    dump(REPO_ROOT/'reports/cg_arrow004_is_robustness.json',{'timestamp':stamp(),'candidates':out})
    ledger({'event':'ROBUSTNESS_COMPLETE','policies':len(out),'artifact':'reports/cg_arrow004_is_robustness.json'})
    print(f'Paired IS fragility closed for {len(out)} policies')

def cash_job(job):
    name,record,summaries=job;d=read(REPO_ROOT/record['detail_path']);sign=1 if record['spec']['side']=='long' else -1
    exits={l['ticket_id']:l for l in d['legs']}; cash=100000.; marks={};maxerr=maxgross=0.;events=0
    for day in d['daily']:
        iso=day['date'];today=date.fromisoformat(iso);gross=0.
        for p in d['positions']:
            if p['fill_date']>iso:continue
            q0=p['original_shares'];px0=p['original_entry'];factor=adjustment_factor(p['symbol'],date.fromisoformat(p['fill_date']),today);q=q0/factor
            if p['fill_date']==iso:
                cash-=sign*q0*px0+q0*(.005+max(.01,.001*px0));events+=1
                rec=summaries.get((iso,p['symbol']))
                if not rec or rec.get('entry_open')!=px0:raise AssertionError('Entry is not observed scheduled open')
            leg=exits.get(p['id'])
            if leg and leg['exit_ts'][:10]==iso:
                if abs(leg['shares']-q)>1e-9:raise AssertionError('Exit split quantity mismatch')
                px=leg['exit'];cash+=sign*q*px-q*(.005+max(.01,.001*px));events+=1
                rec=summaries.get((iso,p['symbol']))
                expected=rec['open'] if iso>p['expiry_date'] else rec['scheduled_exit_open']
                if abs(px-expected)>1e-9:raise AssertionError('Exit not observed at authorized open')
            if leg and leg['exit_ts'][:10]<=iso:continue
            rec=summaries.get((iso,p['symbol']))
            if rec:marks[p['id']]=(iso,rec['close'])
            observed,px=marks.get(p['id'],(p['fill_date'],px0));px*=adjustment_factor(p['symbol'],date.fromisoformat(observed),today)
            gross+=q*px
        error=abs(cash+sign*gross-day['equity']);maxerr=max(maxerr,error);maxgross=max(maxgross,abs(gross-day['gross']))
        if error>1e-6 or abs(cash-day['cash'])>1e-6 or abs(gross-day['gross'])>1e-6:raise AssertionError(f'Independent account mismatch {name} {iso}')
    return {'book':name,'observed_executions':events,'sessions':len(d['daily']),'max_equity_error':maxerr,'max_gross_error':maxgross,'detail_sha256':record['detail_sha256']}

def oracle(mode,workers=8):
    authorize(mode);_,summaries=load_prepared(mode,workers);r=records(mode);out=[];start=timer.monotonic()
    with ProcessPoolExecutor(max_workers=min(workers,8)) as pool:
        fs=[pool.submit(cash_job,(n,x,summaries)) for n,x in r.items()]
        for n,f in enumerate(as_completed(fs),1):
            out.append(f.result())
            if n%8==0 or n==len(fs):print(f'{stamp()} cash audit {n}/{len(fs)} ETA~{(timer.monotonic()-start)/n*(len(fs)-n):.1f}s',flush=True)
    dump(REPO_ROOT/f'reports/cg_arrow004_cash_{mode.lower()}.json',{'timestamp':stamp(),'mode':mode,'books':out,'code_sha256':code_identity(),
          'method':'Independent cash flows, original quantities and dated split factors, carried observed marks and actual execution references',
          'limitation':'Accounting agreement does not certify missing prices, corporate actions or actual fills.'})
    ledger({'event':'CASH_AUDIT_COMPLETE','mode':mode,'books':len(out)})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['board','robustness','oracle']);p.add_argument('--mode',default='IS');p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    if a.command=='board':board()
    elif a.command=='robustness':robustness()
    else:oracle(a.mode,a.workers)
