"""Uniform prior-reference valuation sensitivity; isolated from baseline evidence."""
from concurrent.futures import ProcessPoolExecutor,as_completed
import time
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,stamp,digest
from research.cg_arrow004_lab import Spec,score,load_prepared,authorize,ledger
from research.cg_arrow004_valuation import references

def job(args):
    raw,ranks,summaries,refs=args
    m,d=score(Spec(**raw),'IS',ranks,summaries,valuation_refs=refs)
    path=ROOT/'diagnostics'/('reference_'+raw['id']+'.json');dump(path,d)
    return raw['id'],{'metrics':m,'detail_path':path.relative_to(REPO_ROOT).as_posix(),'detail_sha256':digest(path)}

if __name__=='__main__':
    authorize('IS');ranks,summaries=load_prepared('IS');refs=references('IS',summaries)
    ids=['S0_R4','S0_R5','S1_R4','S1_R5','S2_R4','S2_R5','S3_R4','S3_R5','S4_R4','S4_R5','S4_FULL_R4','S4_FULL_R5',
         'BRIDGE_R4','BRIDGE_R5','L0','L4','L5','LONG_EQ20','L5_REC_NORM8','L5_REC_SELECT8','A6_RECOVERY_EQUAL','A8_PATIENT_RECOVERY']
    ledger({'event':'PREDECLARE_DIAGNOSTIC','id':'PRIOR_NATIONAL_EOD_REFERENCE','ids':ids,'rule':'Only absent intraday valuation, row-date-known prior-session national EOD reference; no new executions/features. Raw-unit compatibility assumed conditionally, not certified. Same rule all controls/candidates; primary frozen convention stays unchanged'})
    out={};start=time.monotonic()
    with ProcessPoolExecutor(max_workers=8) as pool:
        fs=[pool.submit(job,(read(ROOT/'results'/(n+'_IS.json'))['spec'],ranks,summaries,refs)) for n in ids]
        for count,f in enumerate(as_completed(fs),1):
            n,r=f.result();base=read(ROOT/'results'/(n+'_IS.json'))['metrics'];r['profit_delta_from_minute_only']=r['metrics']['total_pnl']-base['total_pnl'];out[n]=r
            print(f"{stamp()} prior-reference diagnostic {count}/{len(fs)} {n} PnL={r['metrics']['total_pnl']:.2f} delta={r['profit_delta_from_minute_only']:.2f} ETA~{(time.monotonic()-start)/count*(len(fs)-count):.1f}s",flush=True)
    dump(REPO_ROOT/'reports/cg_arrow004_reference_sensitivity.json',{'timestamp':stamp(),'books':out,'reference_sha256':digest(ROOT/'valuation_IS.json'),
      'interpretation':'Conditional prior-national-EOD valuation scenario; not a data repair or additional candidate. No exact missing exit is supplied. Baseline trades remain in their original records; scenario recursively recomputes equity/headroom, so new sizes can differ. Adjustment declaration and RTH equivalence are not established.'})
    ledger({'event':'DIAGNOSTIC_COMPLETE','id':'PRIOR_NATIONAL_EOD_REFERENCE','books':len(out)})
