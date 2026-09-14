"""Synchronized minute-close equity and gross, with actual open executions."""
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import date,datetime,time,timedelta
import argparse,time as timer
from research.cg_arrow004_data import ROOT,REPO_ROOT,SCORE,FEATS,INDEX,ET,read,dump,stamp,read_bars,read_iwm,close_time,adjustment_factor
from research.cg_arrow004_lab import authorize,ledger,load_prepared

def day_job(job):
    iso,books,prior_marks,prior_cash=job;d=date.fromisoformat(iso);symbols={p['symbol'] for b in books.values() for p,l in b['positions']};tapes={}
    for sym in symbols:
        df,_=read_iwm(d) if sym=='IWM' else read_bars(d,sym)
        tapes[sym]={t+timedelta(minutes=1):float(px) for t,px in df.select('bar_start','close').iter_rows()} if df is not None else {}
    marks=dict(prior_marks);updated=set();cash=dict(prior_cash);events={};cursors={n:0 for n in books};out={}
    for n,b in books.items():
        sign=b['sign'];flow=[]
        for p,l in b['positions']:
            if p['fill_date']==iso:
                q=p['original_shares'];px=p['original_entry'];flow.append((datetime.fromisoformat(p['entry_ts']),-sign*q*px-q*(.005+max(.01,.001*px))))
            if l and l['exit_ts'][:10]==iso:
                q=l['shares'];px=l['exit'];flow.append((datetime.fromisoformat(l['exit_ts']),sign*q*px-q*(.005+max(.01,.001*px))))
        events[n]=sorted(flow);out[n]={'date':iso,'peak_gross':0.,'peak_time':None,'peak_gross_equity':0.,'largest_name_equity':0.,'stale_gross_at_peak':0.,
            'minutes_above_130k':0,'excess_dollar_minutes':0.,'nonpositive_equity_minutes':0,'curve':[]}
    when=datetime.combine(d,time(9,31),ET);end=datetime.combine(d,close_time(d),ET)
    while when<=end:
        for sym in symbols:
            if when in tapes[sym]:marks[sym]=tapes[sym][when];updated.add(sym)
        for n,b in books.items():
            # At a shared time boundary this close observation precedes the next
            # minute's open executions. Both entries and exits are OPEN fills.
            while cursors[n]<len(events[n]) and events[n][cursors[n]][0]<when:
                cash[n]+=events[n][cursors[n]][1];cursors[n]+=1
            by=defaultdict(float);stale=0.
            for p,l in b['positions']:
                if datetime.fromisoformat(p['entry_ts'])>=when or l and datetime.fromisoformat(l['exit_ts'])<when:continue
                q=p['original_shares']/adjustment_factor(p['symbol'],date.fromisoformat(p['fill_date']),d)
                px=marks.get(p['symbol'],p['original_entry']*adjustment_factor(p['symbol'],date.fromisoformat(p['fill_date']),d));v=q*px;by[p['symbol']]+=v
                if p['symbol'] not in updated:stale+=v
            gross=sum(by.values());equity=cash[n]+b['sign']*gross;r=out[n];r['curve'].append(equity)
            if gross>r['peak_gross']:r['peak_gross']=gross;r['peak_time']=when.isoformat();r['stale_gross_at_peak']=stale
            if equity>0:
                r['peak_gross_equity']=max(r['peak_gross_equity'],gross/equity);r['largest_name_equity']=max(r['largest_name_equity'],max(by.values(),default=0.)/equity)
            else:r['nonpositive_equity_minutes']+=1
            r['minutes_above_130k']+=gross>130000;r['excess_dollar_minutes']+=max(0,gross-130000)
            r['ending_equity']=equity;r['ending_gross']=gross;r['ending_cash']=cash[n]
        when+=timedelta(minutes=1)
    return iso,out

def audit(mode,ids,workers=8):
    authorize(mode);_,summaries=load_prepared(mode,workers);details={n:read(ROOT/'details'/(n+'_'+mode+'.json')) for n in ids}
    symbols={p['symbol'] for d in details.values() for p in d['positions']};marks={};prior={}
    for day in FEATS:
        previous=FEATS[INDEX[day]-1] if INDEX[day] else day
        marks={s:px*adjustment_factor(s,previous,day) for s,px in marks.items()}
        if day in SCORE:prior[day.isoformat()]=dict(marks)
        for sym in symbols:
            rec=summaries.get((day.isoformat(),sym))
            if rec:marks[sym]=rec['close']
    jobs=[]
    for i,d in enumerate(SCORE):
        iso=d.isoformat();books={};cash={}
        for n,detail in details.items():
            exits={l['ticket_id']:l for l in detail['legs']};positions=[]
            for p in detail['positions']:
                l=exits.get(p['id'])
                if p['fill_date']<=iso and (not l or l['exit_ts'][:10]>=iso):positions.append((p,l))
            books[n]={'sign':1 if detail['side']=='long' else -1,'positions':positions};cash[n]=detail['daily'][i-1]['cash'] if i else 100000.
        jobs.append((iso,books,prior[iso],cash))
    combined={n:[] for n in ids};start=timer.monotonic()
    with ProcessPoolExecutor(max_workers=min(workers,8)) as pool:
        fs=[pool.submit(day_job,j) for j in jobs]
        for count,f in enumerate(as_completed(fs),1):
            iso,rows=f.result();idx=next(i for i,d in enumerate(SCORE) if d.isoformat()==iso)
            for n,row in rows.items():
                expected=details[n]['daily'][idx]
                if any(abs(row['ending_'+k]-expected[k])>1e-6 for k in ('equity','gross','cash')):raise AssertionError(f'Minute/EOD account mismatch {n} {iso}')
                combined[n].append(row)
            if count%32==0 or count==len(fs):print(f'{stamp()} synchronized minutes {count}/{len(fs)} ETA~{(timer.monotonic()-start)/count*(len(fs)-count):.1f}s',flush=True)
    output={}
    for n,rows in combined.items():
        rows.sort(key=lambda r:r['date']);high=100000.;dd=pct=0.
        for r in rows:
            for equity in r.pop('curve'):
                high=max(high,equity);dd=min(dd,equity-high);pct=min(pct,equity/high-1)
        peak=max(rows,key=lambda r:r['peak_gross'])
        output[n]={'sessions':len(rows),'minute_peak_gross':peak['peak_gross'],'peak_time':peak['peak_time'],'stale_gross_at_peak':peak['stale_gross_at_peak'],
             'minute_max_dd':dd,'minute_max_dd_percent':pct,'minutes_above_130k':sum(r['minutes_above_130k'] for r in rows),
             'excess_dollar_minutes':sum(r['excess_dollar_minutes'] for r in rows),'peak_gross_equity':max(r['peak_gross_equity'] for r in rows),
             'largest_name_equity':max(r['largest_name_equity'] for r in rows),'nonpositive_equity_minutes':sum(r['nonpositive_equity_minutes'] for r in rows)}
    dump(REPO_ROOT/f'reports/cg_arrow004_minute_{mode.lower()}.json',{'timestamp':stamp(),'mode':mode,'books':output,'all_sessions':True,
          'clock':'Synchronized minute closes, before simultaneous next-minute OPEN executions at the shared boundary; prior observed prices carried where missing',
          'limitation':'Minute-sampled marks are not tick maxima; missing prices remain uncertain; EOD cash/equity/gross reconciled for every book/day'})
    ledger({'event':'MINUTE_AUDIT_COMPLETE','mode':mode,'ids':ids,'sessions':len(SCORE)});print({n:round(r['minute_peak_gross'],2) for n,r in output.items()})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--mode',default='IS');p.add_argument('--ids',nargs='+',required=True);p.add_argument('--workers',type=int,default=8);a=p.parse_args();audit(a.mode,a.ids,a.workers)
