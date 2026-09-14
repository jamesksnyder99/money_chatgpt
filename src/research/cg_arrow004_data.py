"""Independent Arrow 004 caches, nominal schedule and causal stock features."""
from __future__ import annotations
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date,datetime,time,timedelta
from zoneinfo import ZoneInfo
import argparse, math, statistics, time as timer
import polars as pl
from ingest.calendar import is_nyse_session, nyse_sessions
from ingest.paths import REPO_ROOT,DATA,VIRGIN_IWM,FULL_IWM
from research.cg_arrow003_data import (read,dump,digest,stamp,safe_path,read_bars,
    summarize,close_time,adjustment_factor,history_asof,features,repair_rankings,FEATS,SCORE,INDEX)
from research.arrow70 import _elig_year
from research.arrow44 import _by_sess

ROOT=DATA/'tmp/cg_arrow004'
OLD3=DATA/'tmp/cg_arrow003'
OLD2=DATA/'tmp/cg_arrow002r'
ET=ZoneInfo('America/New_York')
SCHEMA='cg004_two_week_open_v1'

def mapped(d):
    while not is_nyse_session(d):d-=timedelta(days=1)
    return d

def clock(d,minutes_before):
    return datetime.combine(d,close_time(d),ET)-timedelta(minutes=minutes_before)

def schedule():
    d=date(2025,9,4); out=[]
    while d<=SCORE[-1]:
        entry=mapped(d); signal=mapped(entry-timedelta(days=1)); expiry=mapped(d+timedelta(days=14))
        out.append({'index':len(out),'phase':'A' if len(out)%2==0 else 'B','nominal':d.isoformat(),
          'entry_date':entry.isoformat(),'signal':signal.isoformat(),'nominal_expiry':(d+timedelta(days=14)).isoformat(),
          'expiry_date':expiry.isoformat(),'entry_ts':clock(entry,1).isoformat(),'exit_ts':clock(expiry,60).isoformat(),
          'calendar_days':(expiry-entry).days,'intervening_sessions':len(nyse_sessions(entry+timedelta(days=1),expiry))})
        d+=timedelta(days=7)
    return out

def assert_mode(mode):
    from research.cg_arrow004_lab import authorize
    authorize(mode)

def read_iwm(d):
    p=safe_path((VIRGIN_IWM if d<=date(2026,5,29) else FULL_IWM)/(d.isoformat()+'.parquet'))
    if not p.is_file():return None,None
    df=pl.read_parquet(p,columns=['bar_start','open','high','low','close','volume'])
    df=df.filter((pl.col('bar_start').dt.time()>=time(9,30))&(pl.col('bar_start').dt.time()<close_time(d))&
                 (pl.col('volume')>0)&(pl.col('open')>0)&(pl.col('close')>0)).sort('bar_start')
    return (df,p.relative_to(REPO_ROOT).as_posix()) if df.height else (None,None)

def day_job(job):
    iso,syms,execution_day=job; d=date.fromisoformat(iso); path=ROOT/'summaries'/(iso+'.json')
    cache=read(path) if path.exists() else {}
    oldpath=OLD3/'summaries'/(iso+'.json'); old=read(oldpath) if oldpath.exists() else {}
    for sym in syms:
        if sym in cache:continue
        rec=old.get(sym)
        if rec is not None and not execution_day and sym!='IWM':
            cache[sym]={**rec,'schema':SCHEMA}; continue
        df,source=read_iwm(d) if sym=='IWM' else read_bars(d,sym)
        rec=summarize(df,d,source)
        if rec:
            rec={**rec,'schema':SCHEMA,'entry_open':None,'scheduled_exit_open':None,'scheduled_exit_ts':None}
            entries=df.filter(pl.col('bar_start')==clock(d,1))
            exits=df.filter(pl.col('bar_start')>=clock(d,60))
            if entries.height:rec['entry_open']=float(entries['open'][0])
            if exits.height:
                rec['scheduled_exit_open']=float(exits['open'][0]); rec['scheduled_exit_ts']=exits['bar_start'][0].isoformat()
        cache[sym]=rec
    dump(path,cache)
    return iso,{s:cache[s] for s in syms}

def load_summaries(needs,workers=8):
    by=defaultdict(set)
    for iso,sym in needs:by[iso].add(sym)
    execution_dates={s[k] for s in schedule() for k in ('entry_date','expiry_date')}
    out={}; started=timer.monotonic()
    with ProcessPoolExecutor(max_workers=min(workers,8)) as pool:
        fs=[pool.submit(day_job,(iso,sorted(syms),iso in execution_dates)) for iso,syms in sorted(by.items())]
        for n,f in enumerate(as_completed(fs),1):
            iso,rows=f.result(); out.update({(iso,s):r for s,r in rows.items()})
            if n%32==0 or n==len(fs):
                spent=timer.monotonic()-started
                print(f'{stamp()} summaries {n}/{len(fs)} ETA~{spent/n*(len(fs)-n):.1f}s',flush=True)
    return out

def ranks_for(mode,workers=8):
    assert_mode(mode)
    dest=ROOT/f'ranks_{mode}.json'
    if dest.exists():return read(dest)
    days=[date.fromisoformat(s['signal']) for s in schedule() if mode=='ALL' or date.fromisoformat(s['signal']).month%2==(mode=='IS')]
    # Old full-field Wednesday ranks are raw market-feature caches, not outcomes.
    prior={}
    for split in (('IS','OOS') if mode=='ALL' else (mode,)):
        prior.update(read(OLD2/f'ranks_{split}_wed.json'))
    out={d.isoformat():repair_rankings({d.isoformat():prior[d.isoformat()]})[d.isoformat()] for d in days if d.isoformat() in prior}
    missing=[d for d in days if d.isoformat() not in out]
    if missing:
        field=_by_sess(_elig_year(missing)); needs={(x.isoformat(),h['symbol']) for d in missing for h in field.get(d.isoformat(),[]) for x in (d,FEATS[INDEX[d]-15])}
        summaries=load_summaries(needs,workers)
        for d in missing:
            back=FEATS[INDEX[d]-15]; rows=[]
            for h in field.get(d.isoformat(),[]):
                a=summaries.get((d.isoformat(),h['symbol'])); b=summaries.get((back.isoformat(),h['symbol']))
                if a and b:
                    ret=a['close']/(b['close']*adjustment_factor(h['symbol'],back,d))-1
                    rows.append({**h,'raw_return':ret})
            rows.sort(key=lambda h:h['raw_return'],reverse=True)
            out[d.isoformat()]={'rows':rows,'n_res':len(rows),'source':'new holiday-mapped full eligible field'}
    out=dict(sorted(out.items())); dump(dest,out); return out

def feature_row(sym,d,summaries):
    hist=history_asof(sym,FEATS[max(0,INDEX[d]-22):INDEX[d]+1],d,summaries)
    f=features(hist); now=hist[-1] if hist else None
    f['history20_observed']=len(hist)>=21 and all(hist[-21:])
    f['up_session']=now['close']>now['open'] if now else None
    f['close_location']=(now['close']-now['low'])/(now['high']-now['low']) if now and now['high']>now['low'] else None
    f['return_from_open']=now['close']/now['open']-1 if now else None
    f['reclaim_prior_high']=now['close']>hist[-2]['high'] if len(hist)>1 and now and hist[-2] else None
    f['reclaim_mean5']=now['close']>=statistics.mean(x['close'] for x in hist[-6:-1]) if len(hist)>=6 and all(hist[-6:]) else None
    f['inside_prior_range']=now['low']>=hist[-2]['low'] if len(hist)>1 and now and hist[-2] else None
    f['ret1']=now['close']/hist[-2]['close']-1 if len(hist)>1 and now and hist[-2] else None
    return f

def data_for(mode,workers=8):
    assert_mode(mode); ranks=ranks_for(mode,workers); needs=set()
    for iso,r in ranks.items():
        d=date.fromisoformat(iso)
        syms={h['symbol'] for h in r['rows'][:20]+r['rows'][-20:]}|{'IWM'}
        for sym in syms:
            for x in FEATS[max(0,INDEX[d]-22):]:needs.add((x.isoformat(),sym))
    summaries=load_summaries(needs,workers)
    prepared={}
    for iso,r in ranks.items():
        d=date.fromisoformat(iso)
        prepared[iso]={side:[{**h,'rank':i+1,'feature':feature_row(h['symbol'],d,summaries)} for i,h in enumerate(rows)]
                        for side,rows in [('short',r['rows'][:20]),('long',list(reversed(r['rows']))[:20])]}
    return prepared,summaries

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--mode',default='IS',choices=['IS','OOS','ALL']);p.add_argument('--workers',type=int,default=8);a=p.parse_args()
    ranks,summaries=data_for(a.mode,a.workers)
    dump(ROOT/f'prepared_{a.mode}.json',{'ranks':ranks,'summaries':{'|'.join(k):v for k,v in summaries.items()}})
    print(f'{stamp()} prepared {len(ranks)} signal cohorts; {len(summaries)} local symbol-days')
