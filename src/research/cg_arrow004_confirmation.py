"""Pre-reveal commitment and resumable one-shot frozen policy batches."""
from dataclasses import asdict
from concurrent.futures import ProcessPoolExecutor,as_completed
import argparse,subprocess,time as timer
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp,schedule
from research.cg_arrow004_lab import Spec,FREEZE,authorize,elapsed,ledger,code_identity,input_identity,dependency_identity,SCENARIOS,MATERIALITY,score_job,load_prepared

def cache_identity():
    return {p.relative_to(REPO_ROOT).as_posix():digest(p) for folder in ('summaries',) for p in sorted((ROOT/folder).glob('*.json'))}

def freeze(selection):
    authorize('IS')
    if elapsed()<115*60:raise RuntimeError('Protected research time: no freeze before minute115')
    finals=selection['finalists'];ids=[p['id'] for p in finals];controls=selection['controls']
    if len(ids)>6 or len(set(ids))!=len(ids) or set(ids)&set(controls):raise ValueError('At most six distinct new finalists, separate controls')
    if not ids and not selection.get('no_credible_finalist_reason'):raise ValueError('Explain empty finalist set')
    names=controls+ids
    if len(set(names))!=len(names):raise ValueError('Duplicate controls')
    records={n:read(ROOT/'results'/(n+'_IS.json')) for n in names};fingerprints=set()
    for n,r in records.items():
        if r['code_sha256']!=code_identity() or digest(REPO_ROOT/r['detail_path'])!=r['detail_sha256']:raise RuntimeError('Final current-code IS identity required')
        s=Spec(**r['spec'])
        if s.reference and s.reference not in names:raise ValueError('Frozen benchmark requires its reference policy')
        if n in ids:
            if s.allocation=='benchmark' or s.origin in {'CONTROL','DIAGNOSTIC'}:raise ValueError('Do not rename a control/benchmark as new discovery')
            econ=dict(r['spec'])
            for k in ('id','origin','control','mechanism'):econ.pop(k)
            fp=str(sorted(econ.items()))
            if fp in fingerprints:raise ValueError('Economically duplicate finalists')
            fingerprints.add(fp)
    for p in finals:
        if p['control'] not in controls:raise ValueError('Primary control absent')
        if p['primary_claim'] not in {'balanced','ride','return'} or not p.get('pitch') or not p.get('acceptable_tradeoff'):raise ValueError('Freeze complete intended claim')
        if records[p['id']]['spec']['side']=='long' and p.get('benchmark') not in controls:raise ValueError('Long benchmark absent')
        for n in p.get('secondary_controls',[])+p.get('locked_phase_companions',[]):
            if n not in names:raise ValueError('Required secondary control or phase companion absent')
        if p.get('lineage_parent') and p['lineage_parent'] not in names:raise ValueError('Direct lineage parent absent')
        from research.cg_arrow004_report import claim_test
        if not claim_test(records[p['id']]['metrics'],records[p['control']]['metrics'],p['primary_claim'])['numeric_claim_pass']:raise ValueError('Proposed finalist does not earn its declared IS claim')
    proof=read(REPO_ROOT/'reports/cg_arrow004_exact_replay.json')
    if proof['code_sha256']!=code_identity() or proof['input_sha256']!=input_identity() or proof['mismatches'] or not set(names)<=set(proof['ids']):raise RuntimeError('Current exact replay proof required')
    f={'status':'FROZEN','timestamp':stamp(),'elapsed_minutes':elapsed()/60,'start':read(ROOT/'state.json')['start_utc'],'deadline':read(ROOT/'state.json')['deadline_utc'],
       'finalists':finals,'controls':controls,'specs':[r['spec'] for r in records.values()],'schedule':schedule(),
       'rule_conventions':{'signal':'Previous trading session completed close before mapped nominal Thursday; full eligible field, $10-80 prior close, prior dollar volume>=10m, inherited common-stock/ETP exclusions',
         'ranking':'Split-consistent15-session return; top20 short, bottom20 long; signal-known features fixed until entry',
         'entry':'Exact final RTH minute OPEN; integer shares from last completed pre-order mark; absent exact bar is missed',
         'exit':'Nominal entry Thursday+14calendar days mapped at/before nominal Thursday; first observed RTH bar OPEN at/after one hour before close. No early exit. Missing remains held, later session first valid RTH open',
         'holidays':'Last trading session at/before nominal Thursday, expiry anchored to nominal date; signal previous trading session; early-close exit one hour/entry one minute before actual close',
         'capital':'Equity=cash+long value-short value. G=max(0,min(u*E,130000)), H=max(0,G-open gross), weekly B=min(G/2,H), phase B=H. Fixed-reference-E controls explicit. Pending exits do not free headroom',
         'safeguard':'New aggregate symbol notional<=20%positive current equity at pre-order marks; simultaneous proportional bounded redistribution; no forced liquidation of price drift',
         'carry':'First global nominal Thursday always strict half-target startup. Later reserve-only carry keeps strict S1 primary core and tops up qualified ranks9-20 to H/8. carry_full additionally permits H/8 for fully observed full-conviction primary names while cautious/unknown primaries keep strict-budget sizes. Incremental dollars only favorable observed states; no virtual credits',
         'missing_features':'Original control penalties neutral when unavailable; new normalized confidence factors half for each unavailable feature; reserve requires every relevant feature observed and favorable; unknown selection states after observed tiers',
         'benchmark':'IWM same clock and parent pre-order gross commitment, integer quantities from IWM pre-order mark. Actual gross mismatch from stock missed fills and gaps is disclosed; benchmark cap exemption diagnostic only',
         'data':'Inherited eight documented action events, raw independent copied bars, no invented prices/dividends/loans; stale marks not executable. Complete economics conditional',
         'split':'Odd original signal months IS, even reused internal confirmation; global phases never reset, no half-book top-up; all chronological accounts separate, not additive funding'},
       'code_sha256':code_identity(),'input_sha256':input_identity(),'dependency_identity':dependency_identity(),'cache_sha256_at_freeze':cache_identity(),'prepared_is_sha256':digest(ROOT/'prepared_IS.json'),
       'scenarios':SCENARIOS,'materiality':MATERIALITY,'oos_exposed':False,'historical_confirmation_reuse':True,
       'pre_reveal_commitment':'Commit this manifest and all code before one new OOS batch; no parameter/rule/size/priority changes after reveal',
       'selection_notes':selection.get('notes',[]),
       'claim_evaluation':'Frozen cg_arrow004_report.claim_test: 5percent/100-dollar material profit, 5percent downside materiality, ride >=85percent positive parent profit plus >=5percent DD reduction and no downside amount >5percent worse; balanced material profit plus at least one material downside improvement and none >5percent worse; return material profit and all downside amounts within20percent. Downside fields are continuous DD, signal-month red-loss sum/worst month, and actual worst calendar day. Actual calendar-month results and benchmark/data limitations are disclosed separately.',
       'data_reference_sensitivity':'Prior-session national17:15 EOD references were inspected and scored uniformly in a separate IS diagnostic. Later-session scope and adjustment declaration prevent baseline substitution; no execution or signal history synthesized. Minute-only marks remain frozen baseline, heavily data-limited for shorts.'}
    dump(FREEZE,f);ledger({'event':'FREEZE_WRITTEN','finalists':ids,'controls':controls,'manifest_sha256':digest(FREEZE),'commit_required':True})
    print(f'Frozen {len(ids)} new finalists and {len(controls)} necessary controls; commit required')

def batch(mode,workers=8):
    f=authorize(mode);sha=digest(FREEZE);label='oos' if mode=='OOS' else 'investor';marker=ROOT/(label+'_started.json');done=ROOT/(label+'_complete.json')
    if done.exists():
        if read(done)['freeze_sha256']!=sha:raise RuntimeError('Completed output identity changed')
        print('Identical frozen job already complete; no rescore');return
    resumed=marker.exists()
    if resumed:
        if read(marker)['freeze_sha256']!=sha:raise RuntimeError('Different freeze cannot resume')
    else:
        if mode=='OOS':
            if any(digest(REPO_ROOT/p)!=v for p,v in f['cache_sha256_at_freeze'].items()):raise RuntimeError('IS cache changed before reveal')
            from research.cg_arrow004_raw_audit import verify_frozen_sources
            verify_frozen_sources()
        dump(marker,{'timestamp':stamp(),'elapsed_minutes':elapsed()/60,'freeze_sha256':sha,'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO_ROOT,text=True).strip()})
    state=read(ROOT/'state.json');state['oos_exposed']=True;state['freeze_sha256']=sha;dump(ROOT/'state.json',state)
    ledger({'event':'CONFIRMATION_START' if mode=='OOS' else 'INVESTOR_START','mode':mode,'resumed_identical_job':resumed,'freeze_sha256':sha})
    start=timer.monotonic();ranks,summaries=load_prepared(mode,workers);completed=[]
    # Reference policies precede dependent IWM benchmarks; one writer per book.
    for benchmark_phase in (False,True):
        pending=[]
        for raw in f['specs']:
            if bool(raw.get('reference'))!=benchmark_phase:continue
            p=ROOT/'results'/(raw['id']+'_'+mode+'.json')
            if p.exists():
                r=read(p)
                if r['spec']!=raw or r['code_sha256']!=f['code_sha256'] or digest(REPO_ROOT/r['detail_path'])!=r['detail_sha256']:raise RuntimeError('Completed partial output mismatch')
                completed.append(raw['id'])
            else:pending.append(raw)
        if pending:
            with ProcessPoolExecutor(max_workers=min(workers,8)) as pool:
                fs=[pool.submit(score_job,(raw,mode,ranks,summaries)) for raw in pending]
                for future in as_completed(fs):
                    r=future.result();completed.append(r['spec']['id']);m=r['metrics'];spent=timer.monotonic()-start
                    ledger({'event':'FROZEN_BOOK_COMPLETE','mode':mode,'id':r['spec']['id'],'metrics':m,'detail_sha256':r['detail_sha256']})
                    print(f"{stamp()} {mode} {len(completed)}/{len(f['specs'])} {r['spec']['id']} PnL={m['total_pnl']:.2f} day={m['per_day']:.2f} DD={m['max_dd']:.2f} ETA~{spent/len(completed)*(len(f['specs'])-len(completed)):.1f}s",flush=True)
    dump(done,{'timestamp':stamp(),'elapsed_minutes':elapsed()/60,'freeze_sha256':sha,'ids':completed,'resumed_identical_job':resumed,'wall_seconds':timer.monotonic()-start})
    ledger({'event':'CONFIRMATION_COMPLETE' if mode=='OOS' else 'INVESTOR_COMPLETE','mode':mode,'books':len(completed)})
    state=read(ROOT/'state.json');state['completed_'+mode.lower()]=completed;state['elapsed_checkpoint_seconds']=elapsed();dump(ROOT/'state.json',state)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','confirmation','investor']);p.add_argument('--selection');p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    if a.command=='freeze':freeze(read(REPO_ROOT/a.selection))
    else:batch('OOS' if a.command=='confirmation' else 'ALL',a.workers)
