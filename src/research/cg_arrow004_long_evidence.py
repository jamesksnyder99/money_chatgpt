"""Long recovery mechanism and fragility diagnostics; no outcome-based rules."""
from collections import defaultdict,Counter
import argparse,statistics
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,stamp
from research.cg_arrow004_lab import authorize,ledger,valid
from research.cg_arrow004_report import corr,claim_test

def state(f):
    v=f.get('volume_ratio');r=f.get('ret3');up=f.get('up_session');cl=f.get('close_location')
    if not valid(v) or not valid(r):return 'unknown'
    volume='quiet' if v<=1 else 'high_volume_recovery' if up and valid(cl) and cl>=.5 else 'high_volume_without_recovery'
    return volume+('/ret3_nonnegative' if r>=0 else '/ret3_negative')

def evidence(ids,mode='IS'):
    authorize(mode);out={}
    for n in ids:
        rec=read(ROOT/'results'/(n+'_'+mode+'.json'));d=read(REPO_ROOT/rec['detail_path']);m=rec['metrics'];groups=defaultdict(lambda:{'tickets':0,'entry_gross':0.,'net_pnl':0.,'positive_tickets':0})
        for p in d['positions']:
            g=groups[state(p['feature'])];g['tickets']+=1;g['entry_gross']+=p['original_shares']*p['original_entry'];v=d['ticket_pnl'][p['id']];g['net_pnl']+=v;g['positive_tickets']+=v>0
        for g in groups.values():g['pnl_per_entry_gross']=g['net_pnl']/g['entry_gross'] if g['entry_gross'] else None
        assert abs(sum(g['net_pnl'] for g in groups.values())-m['total_pnl'])<1e-6
        syms=sorted(d['symbol_pnl'].items(),key=lambda x:x[1],reverse=True);profit=m['total_pnl'];cohort=defaultdict(float)
        for p in d['positions']:cohort[p['nominal']]+=d['ticket_pnl'][p['id']]
        comparisons={}
        for parent in list(dict.fromkeys([rec['spec']['control'],'L5','L5_REC_NORM8'])):
            pth=ROOT/'results'/(parent+'_'+mode+'.json')
            if not pth.exists() or parent==n:continue
            cr=read(pth);cm=cr['metrics'];cd=read(REPO_ROOT/cr['detail_path']);diff={k:m['months'][k]-cm['months'][k] for k in m['months']}
            cs=set(d['symbol_pnl'])|set(cd['symbol_pnl']);increments=sorted(((s,d['symbol_pnl'].get(s,0)-cd['symbol_pnl'].get(s,0)) for s in cs),key=lambda x:x[1],reverse=True)
            comparisons[parent]={'profit_increment':profit-cm['total_pnl'],'month_increments':diff,'positive_increment_months':sum(x>0 for x in diff.values()),
                'leave_one_month_out_increment':{k:sum(diff.values())-v for k,v in diff.items()},
                'increment_without_largest_positive_contributor':profit-cm['total_pnl']-max(0,increments[0][1]) if increments else profit-cm['total_pnl'],
                'top_incremental_symbols':increments[:5],'daily_pnl_correlation':corr([r['pnl'] for r in d['daily']],[r['pnl'] for r in cd['daily']]),
                'balanced':claim_test(m,cm,'balanced'),'ride':claim_test(m,cm,'ride'),'return':claim_test(m,cm,'return')}
        benchmark=ROOT/'results'/('IWM_'+n+'_'+mode+'.json');benchmark_delta=None
        if benchmark.exists():
            bm=read(benchmark)['metrics'];dif={k:m['months'][k]-bm['months'][k] for k in m['months']}
            benchmark_delta={'total':profit-bm['total_pnl'],'months':dif,'positive_months':sum(x>0 for x in dif.values()),
                             'leave_one_month_out':{k:sum(dif.values())-v for k,v in dif.items()}}
        out[n]={'mode':mode,'side':rec['spec']['side'],'causal_state_attribution':dict(groups),'profit_without_top_symbol':profit-max(0,syms[0][1]) if syms else profit,
             'profit_without_top_three_symbols':profit-sum(max(0,v) for s,v in syms[:3]),'top_symbols':syms[:5],
             'cohort_distribution':{'cohorts_with_fills':len(cohort),'positive_cohorts':sum(v>0 for v in cohort.values()),'median_pnl':statistics.median(cohort.values()) if cohort else None,
               'best_pnl':max(cohort.values(),default=0),'worst_pnl':min(cohort.values(),default=0),'profit_without_best_cohort':profit-max(cohort.values(),default=0)},
             'capital':{'mean_filled_per_allocation':sum(c['filled'] for c in d['cohorts'])/len(d['cohorts']),'empty_allocations':sum(c['filled']==0 for c in d['cohorts']),
               'intended_budget_use':sum(c['intended'] for c in d['cohorts'])/sum(c['budget'] for c in d['cohorts']) if sum(c['budget'] for c in d['cohorts']) else None,
               'mean_surviving_gross':statistics.mean(c['surviving_gross'] for c in d['cohorts']),'mean_remaining_headroom':statistics.mean(c['headroom']-c['intended'] for c in d['cohorts'])},
             'comparisons':comparisons,'matched_iwm_increment':benchmark_delta,'local_detail_sha256':rec['detail_sha256']}
    dump(REPO_ROOT/f'reports/cg_arrow004_long_evidence_{mode.lower()}.json',{'timestamp':stamp(),'books':out,
       'interpretation':'Causal state attribution on completed fixed books, without any trade/date exclusions or rescaling. Removing a contributor is arithmetic fragility, not a revised policy. Overlapping cohorts and six reused months do not support independent-trade significance claims.'})
    ledger({'event':'LONG_MECHANISM_FALSIFICATION_COMPLETE','mode':mode,'ids':ids})
    print('Long state/benchmark/concentration evidence',len(out),'books')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ids',nargs='+',required=True);p.add_argument('--mode',default='IS');a=p.parse_args();evidence(a.ids,a.mode)
