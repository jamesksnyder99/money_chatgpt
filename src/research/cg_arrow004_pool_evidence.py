"""Within-cohort long state comparisons from the already completed equal20 book."""
from collections import defaultdict
import statistics,math
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,stamp
from research.cg_arrow004_lab import authorize,ledger,Spec,confidence,valid
from research.cg_arrow004_long_evidence import state

def stats(values):
    return {'n':len(values),'mean':statistics.mean(values) if values else None,'median':statistics.median(values) if values else None,
            'positive_fraction':sum(v>0 for v in values)/len(values) if values else None,'minimum':min(values,default=None),'maximum':max(values,default=None)}

def main():
    authorize('IS');r=read(ROOT/'results/LONG_EQ20_IS.json');d=read(REPO_ROOT/r['detail_path']);groups=defaultdict(list);cohorts=defaultdict(lambda:defaultdict(list));months=defaultdict(lambda:defaultdict(list))
    spec=Spec('DIAG',side='long',family='R5',feature='recovery')
    ledger({'event':'PREDECLARE_DIAGNOSTIC','id':'WITHIN_COHORT_LONG_POOL_STATES','rationale':'Use completed equal-dollar bottom-twenty tickets, normalize each existing net ticket PnL by entry gross, compare signal-known states within each cohort. No new policy, exclusions or reconstructed fills'})
    for p in d['positions']:
        value=d['ticket_pnl'][p['id']]/(p['original_shares']*p['original_entry']);f=p['feature'];c,observed,favorable=confidence(spec,{'feature':f})
        keys=[state(f),'rank1_8' if p['rank']<=8 else 'rank9_20','known' if observed else 'unknown','recovery_full' if favorable else 'not_recovery_full']
        for key in keys:groups[key].append(value);cohorts[p['nominal']][key].append(value);months[p['signal'][:7]][key].append(value)
    paired={};pairs=[('recovery_full','not_recovery_full'),('known','unknown'),('rank9_20','rank1_8'),('quiet/ret3_nonnegative','quiet/ret3_negative')]
    for a,b in pairs:
        vals={n:statistics.mean(g[a])-statistics.mean(g[b]) for n,g in cohorts.items() if g[a] and g[b]}
        paired[a+' minus '+b]={'distribution':stats(list(vals.values())),'cohort_differences':vals,
            'month_differences':{n:statistics.mean(g[a])-statistics.mean(g[b]) for n,g in months.items() if g[a] and g[b]}}
    dump(REPO_ROOT/'reports/cg_arrow004_pool_evidence.json',{'timestamp':stamp(),'source_book':'LONG_EQ20_IS','source_detail_sha256':r['detail_sha256'],
      'ticket_return_groups':{k:stats(v) for k,v in groups.items()},'paired_cohort_groups':paired,
      'interpretation':'Descriptive unit-entry-gross net ticket returns from the already scored full long pool. Paired comparisons share signal cohorts but are not randomized causal effects or independent statistical validation. All missed/terminal lifecycle treatment remains as modeled; no outcome-based survivor filter. Returns are not a funded combined portfolio.'})
    ledger({'event':'DIAGNOSTIC_COMPLETE','id':'WITHIN_COHORT_LONG_POOL_STATES','tickets':len(d['positions']),'cohorts':len(cohorts)})
    print({k:v['distribution'] for k,v in paired.items()})

if __name__=='__main__':main()
