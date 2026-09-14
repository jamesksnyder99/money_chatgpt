"""Lossless final IS replay: verification, never a new hypothesis."""
from dataclasses import asdict
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,stamp,digest
from research.cg_arrow004_lab import Spec,run_is,authorize,code_identity,input_identity,ledger

def compare(a,b,path='',out=None):
    out=[] if out is None else out
    if isinstance(a,dict):
        for k,v in a.items():
            if k not in b:out.append(path+'/'+k+' missing')
            else:compare(v,b[k],path+'/'+k,out)
    elif isinstance(a,list):
        if len(a)!=len(b):out.append(path+' length')
        else:
            for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i),out)
    elif isinstance(a,(int,float)) and not isinstance(a,bool):
        if not isinstance(b,(int,float)) or abs(a-b)>1e-7:out.append(path)
    elif a!=b:out.append(path)
    return out

def main():
    authorize('IS');inputs=input_identity();paths=sorted((ROOT/'results').glob('*_IS.json'));before={p.stem[:-3]:read(p) for p in paths};old_details={}
    for n,r in before.items():
        detail=read(REPO_ROOT/r['detail_path']);old_details[n]=detail
        dump(ROOT/'replay_archive'/(n+'_'+r['detail_sha256'][:12]+'.json'),detail)
    for dependent in (False,True):
        specs=[Spec(**r['spec']) for r in before.values() if bool(r['spec'].get('reference'))==dependent]
        if specs:run_is(specs,8,replay_reason='Exact final current-code/input identity verification; preserve all prior metrics and detailed economic values')
    mismatches={}
    for n,r in before.items():
        now=read(ROOT/'results'/(n+'_IS.json'));diff=compare(r['metrics'],now['metrics'],'metrics')+compare(old_details[n],read(REPO_ROOT/now['detail_path']),'details')
        if diff:mismatches[n]=diff
    if inputs!=input_identity():raise RuntimeError('Inputs changed during exact replay')
    payload={'timestamp':stamp(),'ids':list(before),'mismatches':mismatches,'code_sha256':code_identity(),'input_sha256':inputs,'absolute_tolerance':1e-7,
             'interpretation':'Every existing economic metric and detail compared; new explanatory fields allowed. Original complete records archived under ignored local data.'}
    dump(REPO_ROOT/'reports/cg_arrow004_exact_replay.json',payload);ledger({'event':'EXACT_REPLAY_COMPLETE','books':len(before),'mismatch_books':len(mismatches)})
    print('Exact replay books',len(before),'mismatch books',len(mismatches))
    if mismatches:raise RuntimeError('Exact economic replay failed; review before any freeze')

if __name__=='__main__':main()
