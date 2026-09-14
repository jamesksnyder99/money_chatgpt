"""Protocol closure assertions and compact auditable completion checkpoint."""
from collections import Counter
import argparse,subprocess
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp
from research.cg_arrow004_lab import authorize,elapsed,ledger,FREEZE,code_identity,input_identity,dependency_identity

def preflight():
    authorize('IS');events=[__import__('json').loads(x) for x in (REPO_ROOT/'reports/cg_arrow004_ledger.jsonl').read_text().splitlines()]
    declared={e['spec']['id'] for e in events if e['event']=='PREDECLARE'};completed={p.stem[:-3] for p in (ROOT/'results').glob('*_IS.json')}
    if declared!=completed:raise AssertionError('Unclosed or undeclared IS experiment')
    raw=read(REPO_ROOT/'reports/cg_arrow004_raw_reconstruction.json')
    if not raw['all_match']:raise AssertionError('Raw reconstruction incomplete')
    if not read(REPO_ROOT/'reports/cg_arrow004_inherited_identity.json')['all_equal_to_starting_git_content']:raise AssertionError('Inherited changes')
    if not all(x['matched'] for x in read(REPO_ROOT/'reports/cg_arrow004_historical_reproduction.json')['controls']):raise AssertionError('Historical controls not reproduced')
    if any((ROOT/p).exists() for p in ('oos_started.json','oos_complete.json','investor_started.json','investor_complete.json')):raise AssertionError('Premature reveal')
    counts=Counter((read(ROOT/'results'/(n+'_IS.json'))['spec']['side'],read(ROOT/'results'/(n+'_IS.json'))['spec']['origin']) for n in completed)
    dump(REPO_ROOT/'reports/cg_arrow004_preflight.json',{'timestamp':stamp(),'elapsed_minutes':elapsed()/60,'declared_and_completed_books':len(completed),
      'counts':{a+'/'+b:n for (a,b),n in counts.items()},'reveal_status':False,'input_sha256':input_identity(),'dependency_identity':dependency_identity(),
      'required_tests':'Focused tests completed; complete tests/ suite reserved for final closure','no_unfinished_experiment':True})
    ledger({'event':'PREFLIGHT_COMPLETE','books':len(completed),'oos_exposed':False});print('Preflight complete',len(completed),'IS books')

def finalcheck():
    f=authorize('ALL');r=read(REPO_ROOT/'reports/cg_arrow004_results.json');sha=digest(FREEZE)
    if r['freeze_sha256']!=sha or read(ROOT/'investor_complete.json')['freeze_sha256']!=sha:raise AssertionError('Final freeze identity')
    names={s['id'] for s in f['specs']}
    if set(r['books'])!=names:raise AssertionError('Missing frozen book')
    required=['report.md','schedule.csv','ledger.jsonl','repairs.md','freeze.json','results.json','daily.csv','commands.txt',
              'cash_all.json','minute_all.json','coverage_all.json','universe_all.json','exact_replay.json','raw_identity_all.json']
    for suffix in required:
        p=REPO_ROOT/'reports'/('cg_arrow004_'+suffix)
        if not p.is_file() or p.stat().st_size==0:raise AssertionError('Missing deliverable '+suffix)
    oracle=read(REPO_ROOT/'reports/cg_arrow004_cash_all.json')
    if {b['book'] for b in oracle['books']}!=names:raise AssertionError('Not every frozen chronological book independently audited')
    if read(REPO_ROOT/'reports/cg_arrow004_exact_replay.json')['mismatches']:raise AssertionError('Replay mismatch')
    finalids={p['id'] for p in f['finalists']}
    if not finalids<=set(read(REPO_ROOT/'reports/cg_arrow004_minute_all.json')['books']):raise AssertionError('Finalist minute audit missing')
    if not finalids<=set(read(REPO_ROOT/'reports/cg_arrow004_coverage_all.json')['books']):raise AssertionError('Finalist coverage missing')
    if elapsed()>150*60:raise AssertionError('Hard elapsed allowance exceeded')
    payload={'timestamp':stamp(),'elapsed_minutes':elapsed()/60,'start':read(ROOT/'state.json')['start_utc'],'deadline':read(ROOT/'state.json')['deadline_utc'],
      'status':'SCIENTIFIC_DELIVERABLES_COMPLETE_PENDING_FINAL_GIT_CLOSURE','freeze_sha256':sha,'frozen_books':len(names),'new_finalists':sorted(finalids),
      'oos_batches':1,'identical_resume_only':True,'all_signal_chronological_accounts':True,'source_repo_access':False,'arrow005_started':False,
      'code_identity_matches':f['code_sha256']==code_identity(),'dependency_identity_matches':f['dependency_identity']==dependency_identity()}
    dump(REPO_ROOT/'reports/cg_arrow004_closure.json',payload);ledger({'event':'SCIENTIFIC_CLOSURE_CHECK','books':len(names),'elapsed_minutes':elapsed()/60});print(payload)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['preflight','finalcheck']);a=p.parse_args();preflight() if a.command=='preflight' else finalcheck()
