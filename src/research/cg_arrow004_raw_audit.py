"""Raw copied-source identities and independent IS rank/feature reconstruction."""
from concurrent.futures import ThreadPoolExecutor,ProcessPoolExecutor,as_completed
from collections import Counter
from datetime import date
import argparse,math,time
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp,safe_path,read_bars,read_iwm,summarize,FEATS,INDEX,adjustment_factor,feature_row
from research.cg_arrow004_lab import authorize,load_prepared,ledger

def hash_one(rel):return rel,digest(safe_path(REPO_ROOT/rel))

def verify_frozen_sources():
    expected=read(ROOT/'raw_sources_IS.json');start=time.monotonic();mismatch=[]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for n,(rel,sha) in enumerate(pool.map(hash_one,expected),1):
            if sha!=expected[rel]:mismatch.append(rel)
            if n%8192==0 or n==len(expected):print(f'{stamp()} pre-reveal source verification {n}/{len(expected)} ETA~{(time.monotonic()-start)/n*(len(expected)-n):.1f}s',flush=True)
    dump(REPO_ROOT/'reports/cg_arrow004_raw_pre_reveal_check.json',{'timestamp':stamp(),'files':len(expected),'mismatch_count':len(mismatch),'manifest_sha256':digest(ROOT/'raw_sources_IS.json')})
    if mismatch:raise AssertionError('Frozen raw source bytes changed')

def manifest(mode='IS',verify=False):
    authorize(mode);_,summaries=load_prepared(mode);path=ROOT/f'raw_sources_{mode}.json'
    sources=sorted({r['source'] for r in summaries.values() if r and r.get('source')});out={};start=time.monotonic()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for n,(rel,sha) in enumerate(pool.map(hash_one,sources),1):
            out[rel]=sha
            if n%8192==0 or n==len(sources):print(f'{stamp()} raw source hashes {n}/{len(sources)} ETA~{(time.monotonic()-start)/n*(len(sources)-n):.1f}s',flush=True)
    if verify:
        if read(path)!=out:raise AssertionError('Raw source bytes changed')
    else:dump(path,out)
    payload={'timestamp':stamp(),'mode':mode,'source_files':len(out),'source_tree_counts':dict(Counter('/'.join(p.split('/')[:2]) for p in out)),
             'local_manifest':path.relative_to(REPO_ROOT).as_posix(),'manifest_sha256':digest(path),'verified_again':verify,
             'interpretation':'SHA-256 of every raw copied file referenced by the prepared mode cache, including reused summary sources; no market payload is published.'}
    dump(REPO_ROOT/f'reports/cg_arrow004_raw_identity_{mode.lower()}.json',payload);ledger({'event':'RAW_SOURCE_IDENTITY','mode':mode,'files':len(out),'verify':verify,'manifest_sha256':digest(path)})

def reconstruct_job(args):
    iso,rank,prepared=args;day=date.fromisoformat(iso);back=FEATS[INDEX[day]-15];need={}
    for h in rank['rows']:
        for d in (back,day):need[(d.isoformat(),h['symbol'])]=None
    selected={h['symbol'] for side in ('long','short') for h in prepared[side]}
    for sym in selected:
        for d in FEATS[max(0,INDEX[day]-22):INDEX[day]+1]:need[(d.isoformat(),sym)]=None
    for (d,sym) in need:
        bars,source=read_bars(date.fromisoformat(d),sym);need[(d,sym)]=summarize(bars,date.fromisoformat(d),source)
    rank_error=0.;missing=0;features=0;feature_error=0.;bad=[]
    for h in rank['rows']:
        a=need[(iso,h['symbol'])];b=need[(back.isoformat(),h['symbol'])]
        if not a or not b:missing+=1;continue
        value=a['close']/(b['close']*adjustment_factor(h['symbol'],back,day))-1;error=abs(value-h['raw_return']);rank_error=max(rank_error,error)
        if error>1e-10:bad.append({'kind':'rank','symbol':h['symbol'],'absolute_error':error})
    for side in ('long','short'):
        for h in prepared[side]:
            f=feature_row(h['symbol'],day,need);features+=1
            for k,v in h['feature'].items():
                actual=f[k]
                if isinstance(v,(float,int)) and not isinstance(v,bool) and isinstance(actual,(float,int)):
                    error=abs(actual-v);feature_error=max(feature_error,error)
                    if error>1e-8:bad.append({'kind':'feature','symbol':h['symbol'],'field':k,'absolute_error':error})
                elif actual!=v:bad.append({'kind':'feature','symbol':h['symbol'],'field':k,'absolute_error':None})
    return {'signal':iso,'full_rank_rows':len(rank['rows']),'missing_rank_endpoints':missing,'max_rank_error':rank_error,
            'selected_feature_rows':features,'max_feature_error':feature_error,'mismatches':bad,'raw_symbol_days_read':len(need)}

def reconstruct():
    authorize('IS');prepared,_=load_prepared('IS');ranks=read(ROOT/'ranks_IS.json');out=[];start=time.monotonic()
    with ProcessPoolExecutor(max_workers=8) as pool:
        fs=[pool.submit(reconstruct_job,(iso,rank,prepared[iso])) for iso,rank in ranks.items()]
        for n,f in enumerate(as_completed(fs),1):
            row=f.result();out.append(row);print(f'{stamp()} raw full-field reconstruction {n}/{len(fs)} errors={len(row["mismatches"])} ETA~{(time.monotonic()-start)/n*(len(fs)-n):.1f}s',flush=True)
    out.sort(key=lambda x:x['signal']);payload={'timestamp':stamp(),'signals':out,'all_match':not any(r['mismatches'] or r['missing_rank_endpoints'] for r in out),
       'interpretation':'Read raw copied minute files independently of cached summaries: full eligible rank endpoints and all selected long/short signal-history features. No outcomes used to alter membership.'}
    dump(REPO_ROOT/'reports/cg_arrow004_raw_reconstruction.json',payload);ledger({'event':'RAW_RECONSTRUCTION_COMPLETE','signals':len(out),'all_match':payload['all_match']})
    if not payload['all_match']:raise AssertionError('Raw reconstruction mismatch; review before freeze')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['manifest','reconstruct']);p.add_argument('--mode',default='IS');p.add_argument('--verify',action='store_true');a=p.parse_args()
    reconstruct() if a.command=='reconstruct' else manifest(a.mode,a.verify)
