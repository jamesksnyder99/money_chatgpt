"""Causal prior-session national-EOD references, never synthetic executions."""
from collections import Counter
from datetime import date
import argparse,math
import polars as pl
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp,FEATS,INDEX,adjustment_factor

def references(mode,summaries):
    path=ROOT/f'valuation_{mode}.json'
    if path.exists():return read(path)
    wanted={sym for iso,sym in summaries};raw={};out={}
    # Source preference follows the inherited calendar, without eligibility filtering.
    for tree in ('full','virgin'):
        df=pl.read_parquet(REPO_ROOT/f'data/{tree}/eligibility.parquet').filter(pl.col('symbol').is_in(sorted(wanted)))
        for r in df.select('session_date','symbol','prior_close').iter_rows(named=True):
            d=r['session_date'];px=r['prior_close']
            if (d.isoformat(),r['symbol']) not in summaries or d not in INDEX or INDEX[d]==0:continue
            if px is None or not math.isfinite(px) or px<=0:continue
            key=d.isoformat()+'|'+r['symbol']
            if key not in raw or (tree=='virgin' and d<=date(2026,5,29)):
                prev=FEATS[INDEX[d]-1]
                raw[key]={'mark':float(px)*adjustment_factor(r['symbol'],prev,d),'observed_date':prev.isoformat(),'available_date':d.isoformat(),'source':f'data/{tree}/eligibility.parquet'}
    dump(path,raw);return raw

def audit():
    from research.cg_arrow004_lab import authorize,ledger
    authorize('IS');x=read(ROOT/'prepared_IS.json');summaries={tuple(k.split('|')):v for k,v in x['summaries'].items()};refs=references('IS',summaries)
    errors=[];sources=Counter();gaps=Counter();large=[]
    for key,r in refs.items():
        iso,sym=key.split('|');d=date.fromisoformat(iso);prev=r['observed_date'];bar=summaries.get((prev,sym));sources[r['source']]+=1
        if summaries.get((iso,sym)) is None:gaps['missing_minute_with_prior_reference']+=1
        if bar:
            expected=bar['close']*adjustment_factor(sym,date.fromisoformat(prev),d);error=abs(r['mark']/expected-1);errors.append(error)
            if error>.05:large.append({'date':iso,'symbol':sym,'relative_difference':error})
    for iso,sym in summaries:
        if summaries[(iso,sym)] is None and iso+'|'+sym not in refs:gaps['missing_minute_without_reference']+=1
    errors.sort();payload={'timestamp':stamp(),'references':len(refs),'source_counts':dict(sources),'gap_counts':dict(gaps),'overlap_comparisons':len(errors),
      'relative_difference_quantiles':{str(q):errors[min(len(errors)-1,int(q*len(errors)))] for q in (.5,.95,.99,1.)},'overlap_over_5percent':large,
      'source_identity':{p:digest(REPO_ROOT/p) for p in sources},'local_reference_path':'data/tmp/cg_arrow004/valuation_IS.json','local_reference_sha256':digest(ROOT/'valuation_IS.json'),
      'provenance':'ingest.eligibility.evaluate_session copies previous-session EOD close into prior_close, including ineligible rows. The contract labels it official, but vendor/local timestamps establish national17:15 scope. References are known only on the following row session; diagnostic price-unit compatibility and dated split conversion are explicit assumptions.',
      'decision':'DIAGNOSTIC ONLY. National 17:15 reports include later-session scope and absent explicit adjustment declaration. Preserve minute-only baseline; quantify a separate causal prior-reference sensitivity under a compatible-price-unit assumption. References never substitute for intraday execution or signal/rank history.',
      'primary_source':'https://docs.thetadata.us/operations/stock_history_eod.html',
      'primary_methodology':'https://docs.thetadata.us/Articles/Data-And-Requests/OHLC-EOD.html'}
    dump(REPO_ROOT/'reports/cg_arrow004_valuation_reference_audit.json',payload);ledger({'event':'PRIOR_CLOSE_REFERENCE_AUDIT','references':len(refs),'overlap_comparisons':len(errors),'large_differences':len(large),'gap_counts':dict(gaps)})
    print({k:payload[k] for k in ('references','gap_counts','overlap_comparisons','relative_difference_quantiles')});print('Overlap differences above5percent',len(large))

if __name__=='__main__':audit()
