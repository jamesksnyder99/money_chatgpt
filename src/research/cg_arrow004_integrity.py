"""Full-field, causal feature, inherited-file and cohort schedule audits."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import argparse,subprocess
import polars as pl
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp,schedule,ranks_for,feature_row
from research.cg_arrow004_lab import authorize,load_prepared,ledger
from research.arrow70 import _elig_year

def universe(mode='IS'):
    authorize(mode);ranks=ranks_for(mode);prepared,summaries=load_prepared(mode)
    common=set(pl.read_parquet(REPO_ROOT/'data/ref/symbols_common.parquet')['symbol'].to_list())
    etps={s.strip().upper() for s in (REPO_ROOT/'src/ingest/etp_tickers.txt').read_text().splitlines() if s.strip() and not s.startswith('#')}
    eligible=_elig_year([date.fromisoformat(d) for d in ranks]);counts=Counter(r['session_date'].isoformat() for r in eligible.iter_rows(named=True))
    field={(r['session_date'].isoformat(),r['symbol']) for r in eligible.iter_rows(named=True)};out=[];known=Counter();allsyms=set()
    for iso,r in ranks.items():
        symbols=[h['symbol'] for h in r['rows']];allsyms.update(symbols)
        assert len(symbols)==len(set(symbols))
        assert not set(symbols)&etps and set(symbols)<=common
        assert all((iso,s) in field for s in symbols)
        assert all(10<=h['prior_close']<=80 and h['prior_dv']>=10000000 for h in r['rows'])
        assert all(r['rows'][i]['raw_return']>=r['rows'][i+1]['raw_return'] for i in range(len(symbols)-1))
        for side in ('long','short'):
            rows=prepared[iso][side];assert len(rows)==20
            expect=symbols[:20] if side=='short' else list(reversed(symbols))[:20]
            assert [h['symbol'] for h in rows]==expect
            for h in rows:
                actual=feature_row(h['symbol'],date.fromisoformat(iso),summaries)
                assert h['feature']==actual
                known[side+'_pool_slots']+=1;known[side+'_missing_history20']+=not actual['history20_observed']
        out.append({'signal':iso,'entry_rule_field':counts[iso],'rankable_full_field':len(symbols),'unrankable_endpoints':counts[iso]-len(symbols)})
    p=REPO_ROOT/f'reports/cg_arrow004_universe_{mode.lower()}.json'
    dump(p,{'timestamp':stamp(),'mode':mode,'signals':out,'unique_ranked_symbols':len(allsyms),'feature_coverage':dict(known),
            'checks':'All rankable rows satisfy inherited common-stock and ETP exclusions, price/dollar-volume rules; no ticker cap; entire field ranked before twenty retained; every prepared feature recomputed using signal-bounded history',
            'limitation':'Rankable field is conditional on available endpoint observations. Acquisition max-price differences are retained as unrankable counts, not hidden eligibility changes.'})
    ledger({'event':'UNIVERSE_CAUSALITY_AUDIT','mode':mode,'signals':len(out),'feature_rows':sum(v for k,v in known.items() if k.endswith('pool_slots'))})
    print('Full-field/causality audit',mode,len(out),'signals',dict(known))

def inherited():
    names=subprocess.check_output(['git','ls-files','src/research/cg_arrow003*','reports/cg_arrow003*','tests/test_cg_arrow003*'],cwd=REPO_ROOT,text=True).splitlines()
    def check(n):
        import hashlib
        committed=subprocess.check_output(['git','show','1827380:'+n],cwd=REPO_ROOT)
        current=(REPO_ROOT/n).read_bytes()
        # Git autocrlf is allowed for historical text working copies.
        if current.replace(b'\r\n',b'\n')!=committed.replace(b'\r\n',b'\n'):raise AssertionError('Inherited tracked evidence modified: '+n)
        return n,hashlib.sha256(current).hexdigest()
    with ThreadPoolExecutor(max_workers=8) as pool:out=dict(pool.map(check,names))
    dump(REPO_ROOT/'reports/cg_arrow004_inherited_identity.json',{'timestamp':stamp(),'baseline_commit':'1827380','files':out,'all_equal_to_starting_git_content':True})
    print('Inherited evidence unchanged:',len(out),'files')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['universe','inherited']);p.add_argument('--mode',default='IS');a=p.parse_args()
    if a.command=='universe':universe(a.mode)
    else:inherited()
