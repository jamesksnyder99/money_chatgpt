"""Read-only reproduction of the two inherited frozen IS controls."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import date
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp
from research.cg_arrow004_lab import authorize,ledger
from scripts.cg_arrow004_replay import compare

def job(n):
    from research import cg_arrow003_lab as oldlab
    from research import cg_arrow003_data as olddata
    record=read(olddata.ROOT/'results'/(n+'_IS.json'));ranks=olddata.repair_rankings(read(olddata.OLD/'ranks_IS_wed.json'));needs={}
    for iso,r in ranks.items():
        day=date.fromisoformat(iso)
        for h in r['rows'][:8]:
            for d in olddata.FEATS[max(0,olddata.INDEX[day]-22):]:needs.setdefault(d.isoformat(),set()).add(h['symbol'])
    summaries={}
    for iso,syms in needs.items():
        source=read(olddata.ROOT/'summaries'/(iso+'.json'))
        summaries.update({(iso,s):source[s] for s in syms})
    # Pure historical scorer only. check=False is its fixture/reproduction entry
    # point; no old authorization marker, result, cache or ledger is changed.
    m,d=oldlab.score(oldlab.Spec(**record['spec']),'IS',ranks,summaries,check=False)
    prior=read(REPO_ROOT/record['detail_path']);dif=compare(record['metrics'],m,'metrics')+compare(prior,d,'details')
    return {'control':n,'matched':not dif,'differences':dif,'total_pnl':m['total_pnl'],'historical_detail_sha256':record['detail_sha256'],
            'historical_record_sha256':digest(olddata.ROOT/'results'/(n+'_IS.json'))}

if __name__=='__main__':
    authorize('IS');ledger({'event':'HISTORICAL_CONTROL_REPRODUCTION_START','ids':['R4','R5'],'scope':'Pure read-only inherited IS verification; no old research or OOS gate reopened'})
    with ProcessPoolExecutor(max_workers=2) as pool:out=list(pool.map(job,['R4','R5']))
    dump(REPO_ROOT/'reports/cg_arrow004_historical_reproduction.json',{'timestamp':stamp(),'controls':out,'old_writers_called':False})
    print(out);ledger({'event':'HISTORICAL_CONTROL_REPRODUCTION_COMPLETE','all_match':all(r['matched'] for r in out)})
    if not all(r['matched'] for r in out):raise AssertionError('Historical controls changed')
