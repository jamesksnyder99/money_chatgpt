"""Causal standalone long/short two-week capital accounts; Arrow 004 only."""
from __future__ import annotations
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import dataclass,asdict
from datetime import date,datetime,timezone
import argparse,json,math,re,statistics,subprocess,time as timer
import importlib.metadata,platform
from research.cg_arrow004_data import ROOT,REPO_ROOT,DATA,read,dump,digest,stamp,schedule,SCORE,FEATS,INDEX,adjustment_factor
from research.costs import cost_per_share,spread_proxy

REPORTS=REPO_ROOT/'reports'; FREEZE=REPORTS/'cg_arrow004_freeze.json'; LEDGER=REPORTS/'cg_arrow004_ledger.jsonl'
MATERIALITY={'profit_relative':.05,'profit_absolute':100.,'downside_relative':.05,'ride_retention':.85,'return_risk_tolerance':.20}
SCENARIOS={'short_borrow':[0,.10,.30],'long_debit':[0,.05,.10],'spread':[1,2],'idle_yield':0,
           'clock':'calendar days on preceding EOD short value or actual negative cash; sensitivities do not resize frozen baseline trades'}

def elapsed():
    s=read(ROOT/'state.json'); wall=(datetime.now(timezone.utc)-datetime.fromisoformat(s['start_utc'])).total_seconds(); mono=timer.monotonic()-s['start_monotonic']
    return max(wall,mono) if mono>=0 else wall

def ledger(r):
    with LEDGER.open('a',encoding='utf-8') as f:f.write(json.dumps({'timestamp':stamp(),'elapsed_seconds':elapsed(),**r},allow_nan=False)+'\n')

def code_identity():
    paths=[p for folder in ['src/research','src/ingest'] for p in sorted((REPO_ROOT/folder).glob('*.py'))]
    paths+=sorted((REPO_ROOT/'scripts').glob('cg_arrow004*.py'))
    return {p.relative_to(REPO_ROOT).as_posix():digest(p) for p in paths}

def input_identity():
    paths=['data/virgin/eligibility.parquet','data/full/eligibility.parquet','data/ref/symbols_common.parquet','data/ref/splits.parquet',
           'reports/cg_arrow003_corporate_actions.json','data/tmp/cg_arrow002r/ranks_IS_wed.json','data/tmp/cg_arrow002r/ranks_OOS_wed.json',
           'src/ingest/etp_tickers.txt']
    result={p:digest(REPO_ROOT/p) for p in paths}
    raw=ROOT/'raw_sources_IS.json'
    if raw.exists():result[raw.relative_to(REPO_ROOT).as_posix()]=digest(raw)
    return result

def dependency_identity():
    return {'python':platform.python_version(),'implementation':platform.python_implementation(),
            'packages':{n:importlib.metadata.version(n) for n in ('polars','numpy','pytest','tzdata','thetadata')},
            'requirements_sha256':digest(REPO_ROOT/'requirements.txt')}

def authorize(mode):
    if mode not in {'IS','OOS','ALL'}:raise ValueError('Unknown split')
    if mode=='IS':
        if FREEZE.exists() or (ROOT/'oos_started.json').exists():raise RuntimeError('IS research is closed')
        return
    if not FREEZE.exists() or elapsed()<115*60:raise RuntimeError('Committed freeze and minute115 required')
    f=read(FREEZE)
    if f['code_sha256']!=code_identity() or f['input_sha256']!=input_identity():raise RuntimeError('Frozen identity changed')
    if f.get('dependency_identity')!=dependency_identity():raise RuntimeError('Frozen dependency identity changed')
    rel=FREEZE.relative_to(REPO_ROOT).as_posix()
    if subprocess.check_output(['git','show',f'HEAD:{rel}'],cwd=REPO_ROOT)!=FREEZE.read_bytes():raise RuntimeError('Freeze not committed unchanged')
    paths=list(f['code_sha256'])
    if subprocess.run(['git','diff','--quiet','HEAD','--',*paths],cwd=REPO_ROOT).returncode:raise RuntimeError('Uncommitted frozen code')
    if subprocess.run(['git','ls-files','--error-unmatch','--',*paths],cwd=REPO_ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:raise RuntimeError('Untracked frozen code')
    if mode=='ALL':
        if not (ROOT/'oos_complete.json').exists():raise RuntimeError('Investor replay follows confirmation')
        if read(ROOT/'oos_complete.json')['freeze_sha256']!=digest(FREEZE):raise RuntimeError('Investor replay requires identical completed confirmation')
    return f

@dataclass(frozen=True)
class Spec:
    id:str
    side:str='short'
    family:str='R4'
    allocation:str='s0'
    rhythm:str='weekly'
    u:float=1.
    fixed_equity:bool=False
    budget_scale:float=1.
    ticket:float=5150.
    feature:str='mirror'
    threshold:float=1.
    pool_start:int=1
    origin:str='DIRECTED'
    control:str='S0_R4'
    mechanism:str='Common-budget participation sizing'
    reference:str|None=None
    def __post_init__(self):
        if not re.fullmatch(r'[A-Za-z0-9_]{1,70}',self.id):raise ValueError('Invalid ID')
        if self.side not in {'long','short'} or self.family not in {'R4','R5','EQUAL'}:raise ValueError('Invalid side/family')
        if self.rhythm not in {'weekly','A','B'}:raise ValueError('Invalid global phase')
        if self.allocation not in {'fixed','s0','equal8','reserve','blind','weighted20','equal20','select8','select8_equal','qualified8','observed8','normalize8','carry','carry_full','benchmark'}:raise ValueError('Invalid allocation')
        if self.feature not in {'mirror','recovery','recovery_votes','reclaim','votes','stable','intraday','quiet_recovery','mixed_recovery','observed_only','median','range_recovery','persistent','minute_flow'}:raise ValueError('Invalid feature')
        if self.origin not in {'CONTROL','DIRECTED','ASTRA','DERIVED','DIAGNOSTIC'}:raise ValueError('Invalid origin')
        if self.u not in {1.,1.25} or not 0<self.budget_scale<=1 or not 1<=self.pool_start<=13:raise ValueError('Invalid size/pool')

def valid(v):return v is not None and isinstance(v,(float,int)) and math.isfinite(v)

def confidence(spec,h,unknown_half=False):
    f=h['feature']; v=f.get('volume_ratio'); r=f.get('ret3')
    if spec.family=='EQUAL':return 1.,True,True
    observed=valid(v) and v>0 and (spec.family!='R5' or valid(r))
    vol=1. if valid(v) and v<=1 else .5 if valid(v) or unknown_half else 1.
    momentum=1.
    if spec.family=='R5':momentum=1. if valid(r) and (r<=0 if spec.side=='short' else r>=0) else .5 if valid(r) or unknown_half else 1.
    favorable=observed and vol==1 and momentum==1
    if spec.side=='long' and spec.feature!='mirror':
        recovery=bool(f.get('up_session') and valid(f.get('close_location')) and f['close_location']>=.5)
        if spec.feature in {'recovery','recovery_votes'}:
            if valid(v) and v>spec.threshold and recovery:vol=1.
            if spec.feature=='recovery_votes':momentum=1. if valid(f.get('positive_days3')) and f['positive_days3']>=2 else .5
        elif spec.feature=='reclaim':
            vol=1. if f.get('reclaim_prior_high') else .5; observed=f.get('reclaim_prior_high') is not None and (spec.family!='R5' or valid(r))
        elif spec.feature=='votes':momentum=1. if valid(f.get('positive_days3')) and f['positive_days3']>=2 else .5
        elif spec.feature=='stable':
            momentum=1. if f.get('inside_prior_range') and valid(r) and r>=-0.02*spec.threshold else .5; observed=observed and f.get('inside_prior_range') is not None
        elif spec.feature=='intraday':
            vol=1. if recovery else .5; observed=f.get('up_session') is not None and valid(f.get('close_location')) and (spec.family!='R5' or valid(r))
        elif spec.feature=='quiet_recovery':vol=1. if valid(v) and v<=spec.threshold and recovery else .5
        elif spec.feature=='mixed_recovery':
            vol=1. if recovery and f.get('reclaim_mean5') else .5; observed=f.get('up_session') is not None and valid(f.get('close_location')) and f.get('reclaim_mean5') is not None and (spec.family!='R5' or valid(r))
        elif spec.feature=='observed_only':
            if not f.get('history20_observed'):return .25,False,False
        elif spec.feature=='median':
            mv=f.get('volume_median_ratio'); vol=1. if valid(mv) and mv<=1 else .5; observed=valid(mv) and valid(r)
        elif spec.feature=='range_recovery':vol=1. if f.get('inside_prior_range') and recovery else .5
        elif spec.feature=='persistent':
            value=f.get('volume_persistence3');vol=1. if valid(value) and value<=1 else .5;observed=valid(value) and valid(r)
        elif spec.feature=='minute_flow':
            value=f.get('signed_volume_ratio');vol=1. if valid(value) and value>0 else .5;observed=valid(value) and valid(r)
        favorable=observed and vol==1 and momentum==1
    return vol*momentum,observed,favorable

def weighted_alloc(weights,budget,caps):
    """Simultaneous capped proportional allocation with bounded redistribution."""
    amounts=[0.]*len(weights); remaining=max(0,budget)
    for _ in range(len(weights)+1):
        ids=[i for i,w in enumerate(weights) if w>0 and caps[i]-amounts[i]>1e-8]
        if not ids or remaining<1e-8:break
        total=sum(weights[i] for i in ids); spent=0.
        for i in ids:
            add=min(caps[i]-amounts[i],remaining*weights[i]/total);amounts[i]+=add;spent+=add
        remaining-=spent
    return amounts

def capital(equity,gross,spec,reserved=0.):
    target=max(0,min(spec.u*(100000. if spec.fixed_equity else equity),130000.))
    headroom=max(0,target-gross-reserved)
    strict=min(.5*target,headroom) if spec.rhythm=='weekly' else headroom
    return target,headroom,min(headroom,strict*spec.budget_scale)

def allocate(spec,rows,budget,headroom,equity,by_symbol):
    rows=rows[spec.pool_start-1:]; primary=rows[:8]; conf={h['symbol']:confidence(spec,h,spec.allocation in {'weighted20','select8','select8_equal','normalize8'}) for h in rows}
    cap=lambda h:max(0,.2*max(equity,0)-by_symbol.get(h['symbol'],0))
    if spec.allocation=='fixed':return [(h,spec.ticket*confidence(spec,h)[0]) for h in primary]
    if spec.allocation=='qualified8':
        selected=[h for h in rows if confidence(spec,h)[2]][:8]
        return [(h,min(budget/8,cap(h))) for h in selected]
    if spec.allocation=='observed8':
        selected=[h for h in rows if confidence(spec,h)[1]][:8]
        return list(zip(selected,weighted_alloc([confidence(spec,h)[0] for h in selected],budget,[cap(h) for h in selected])))
    if spec.allocation in {'weighted20','select8','select8_equal','normalize8','equal20','equal8'}:
        selected=rows if spec.allocation in {'weighted20','equal20'} else primary
        if spec.allocation in {'select8','select8_equal'}:selected=sorted(rows,key=lambda h:(not conf[h['symbol']][1],-conf[h['symbol']][0],h['rank']))[:8]
        weights=[1. if spec.allocation.startswith('equal') or spec.allocation=='select8_equal' else conf[h['symbol']][0] for h in selected]
        return list(zip(selected,weighted_alloc(weights,budget,[cap(h) for h in selected])))
    q=budget/8; amounts={h['symbol']:min(q*confidence(spec,h)[0],cap(h)) for h in primary}
    if spec.allocation=='carry_full':
        for h in primary:
            if confidence(spec,h)[2]:amounts[h['symbol']]=min(headroom/8,cap(h))
    if spec.allocation in {'reserve','blind','carry','carry_full'}:
        remaining=max(0,(headroom if spec.allocation=='carry_full' else budget)-sum(amounts.values()))
        for h in rows[8:]:
            if spec.allocation=='blind' or confidence(spec,h)[2]:
                a=min(headroom/8 if spec.allocation=='carry_full' else q,remaining,cap(h)); amounts[h['symbol']]=a; remaining-=a
    if spec.allocation=='carry':
        # Strict S1 core remains intact; extra actual headroom only buys qualified
        # reserve names. No primary top-up or virtual unused-credit ledger.
        extra=max(0,headroom-sum(amounts.values())); qextra=headroom/8
        for h in rows[8:]:
            if confidence(spec,h)[2]:
                have=amounts.get(h['symbol'],0.); a=min(max(0,qextra-have),extra,max(0,cap(h)-have)); amounts[h['symbol']]=have+a;extra-=a
    return [(h,amounts[h['symbol']]) for h in rows if h['symbol'] in amounts]

def longest(values):
    best=now=0
    for x in values:now=now+1 if x else 0;best=max(best,now)
    return best

def score(spec,mode,ranks,summaries,reference=None,stale_shock=None,valuation_refs=None):
    if mode not in {'IS','OOS','ALL'}:raise ValueError('Unknown score cohort')
    if any(mode!='ALL' and date.fromisoformat(iso).month%2!=(mode=='IS') for iso in ranks):raise RuntimeError('Original signal-month cohort firewall')
    sign=1 if spec.side=='long' else -1; cash=equity=100000.; active=[];positions=[];legs=[];daily=[];cohorts=[];orders=[]
    counts=Counter(); ticket_pnl=defaultdict(float); symbol_pnl=defaultdict(float)
    months={d.strftime('%Y-%m'):0. for d in SCORE if mode=='ALL' or d.month%2==(mode=='IS')}
    entries={s['entry_date']:s for s in schedule() if s['signal'] in ranks and (spec.rhythm=='weekly' or s['phase']==spec.rhythm)}
    for di,d in enumerate(SCORE):
        iso=d.isoformat(); prev=equity; prior_cash=cash; prior_gross=sum(p['shares']*p['mark'] for p in active)
        gap=(d-SCORE[di-1]).days if di else 0; short_base=prior_gross*gap/365 if sign<0 else 0.;debit_base=max(0,-prior_cash)*gap/365 if sign>0 else 0.
        extra_spread=turnover=new_gross=0.; day_pnl=defaultdict(float)
        def book(p,value):
            day_pnl[p['id']]+=value;ticket_pnl[p['id']]+=value;symbol_pnl[p['symbol']]+=value;months[p['signal'][:7]]+=value
        for p in active:
            factor=adjustment_factor(p['symbol'],SCORE[di-1] if di else d,d)
            if factor!=1:
                p['shares']/=factor;p['entry']*=factor;p['mark']*=factor;p['last_observed_mark']*=factor;p['entry_cost']*=factor
        due=[]
        for p in active:
            rec=summaries.get((iso,p['symbol'])); ts=px=None
            if p['expiry_date']<iso and rec:ts=rec['first_ts'];px=rec['open']
            elif p['expiry_date']==iso:
                if rec:ts=rec.get('scheduled_exit_ts');px=rec.get('scheduled_exit_open')
                if not ts:counts['missing_scheduled_exit']+=1
            if ts and px:due.append((ts,p,px))
        checkpoint=entries.get(iso,{}).get('entry_ts')
        def close_position(ts,p,px):
            nonlocal cash,extra_spread,turnover
            qty=p['shares'];cost=cost_per_share(px);cash+=sign*qty*px-qty*cost
            book(p,sign*qty*(px-p['mark'])-qty*cost);extra_spread+=qty*spread_proxy(px);turnover+=qty*px
            legs.append({'ticket_id':p['id'],'symbol':p['symbol'],'signal':p['signal'],'side':spec.side,'shares':qty,'entry':p['entry'],'exit':px,'exit_ts':ts,
                         'pnl':sign*qty*(px-p['entry'])-qty*(p['entry_cost']+cost),'delayed':ts[:10]>p['expiry_date']})
            if ts[:10]>p['expiry_date']:counts['delayed_exit_fills']+=1;counts['delay_calendar_days']+=(date.fromisoformat(ts[:10])-date.fromisoformat(p['expiry_date'])).days
            p['shares']=0.
        for ts,p,px in due:
            if not checkpoint or ts<checkpoint:close_position(ts,p,px)
        active=[p for p in active if p['shares']>0]
        before_cash=cash; by_symbol=defaultdict(float); pre_value=0.
        for p in active:
            rec=summaries.get((iso,p['symbol'])); mark=rec.get('preorder') if rec and checkpoint else p['mark']
            ref=(valuation_refs or {}).get(iso+'|'+p['symbol'])
            if not rec and ref and ref['observed_date']>=p['last_mark_date']:
                if ref['available_date']!=iso or ref['observed_date']>=iso:raise AssertionError('Prior reference must already be known')
                mark=ref['mark']
            if not valid(mark):mark=p['last_observed_mark']*(1+sign*-stale_shock) if stale_shock is not None else p['mark']
            pre_value+=p['shares']*mark;by_symbol[p['symbol']]+=p['shares']*mark
        pre_equity=cash+sign*pre_value; target,headroom,budget=capital(pre_equity,pre_value,spec)
        proposals=[];cohort=None
        if checkpoint:
            cohort=entries[iso]; rows=ranks[cohort['signal']][spec.side]
            carry_limit=min(headroom,budget) if cohort['index']==0 else headroom
            if spec.allocation=='benchmark':
                ref=next((c for c in (reference or []) if c['nominal']==cohort['nominal']),None)
                proposals=[({'symbol':'IWM','rank':0,'feature':{},'prior_close':1.},ref['planned_gross'] if ref else 0.)]
            else:proposals=allocate(spec,rows,budget,carry_limit,pre_equity,by_symbol)
            cohort={**cohort,'preorder_equity':pre_equity,'cash_before_due_exits':prior_cash,'cash_after_due_exits':before_cash,'surviving_gross':pre_value,'target':target,'headroom':headroom,
                    'budget':carry_limit if spec.allocation in {'carry','carry_full'} else budget,'intended':sum(a for _,a in proposals),'planned_gross':0.,'filled_gross':0.,'filled':0,'missed':0,
                    'surviving_cohorts':len({p['nominal'] for p in active}),'pending_due_tickets':sum(p['expiry_date']<=iso for p in active)}
            counts['allocation_batches']+=1
            if spec.allocation not in {'fixed','benchmark'}:
                counts['symbol_cap_binding_orders']+=sum(a>0 and a>=max(0,.2*max(pre_equity,0)-by_symbol.get(h['symbol'],0))-1e-7 for h,a in proposals)
            for h,amount in proposals:
                if amount<=0:continue
                sym=h['symbol'];rec=summaries.get((iso,sym));signal=date.fromisoformat(cohort['signal']); prior=rec.get('preorder') if rec else None
                if not valid(prior):
                    old=summaries.get((signal.isoformat(),sym));prior=old['close']*adjustment_factor(sym,signal,d) if old else h.get('prior_close')
                qty=math.floor(amount/prior) if valid(prior) and prior>0 else 0
                cohort['planned_gross']+=qty*prior if valid(prior) else 0.
                orders.append({'nominal':cohort['nominal'],'symbol':sym,'intended':amount,'quantity':qty,'preorder_price':prior,'rank':h['rank']})
                if qty<=0:counts['zero_share_order']+=1;continue
                if not rec or rec.get('entry_open') is None:counts['missed_entry']+=1;cohort['missed']+=1;continue
                px=rec['entry_open'];cost=cost_per_share(px);cash-=sign*qty*px+qty*cost;extra_spread+=qty*spread_proxy(px);turnover+=qty*px;new_gross+=qty*px
                p={'id':cohort['nominal']+'/'+sym,'symbol':sym,'nominal':cohort['nominal'],'signal':cohort['signal'],'fill_date':iso,
                   'expiry_date':cohort['expiry_date'],'entry_ts':checkpoint,'entry':px,'original_entry':px,'original_shares':qty,'shares':float(qty),
                   'entry_cost':cost,'mark':px,'last_observed_mark':px,'last_mark_date':iso,'rank':h['rank'],'feature':h['feature'],
                   'confidence':confidence(spec,h,spec.allocation in {'weighted20','select8','select8_equal','normalize8'})[0] if sym!='IWM' else 1.,
                   'feature_observed':confidence(spec,h)[1] if sym!='IWM' else True}
                positions.append(p);active.append(p);book(p,-qty*cost);cohort['filled']+=1;cohort['filled_gross']+=qty*px
            cohorts.append(cohort)
        # Due exits observed only at/after the entry checkpoint had no capacity credit.
        for ts,p,px in due:
            if checkpoint and ts>=checkpoint and p['shares']:close_position(ts,p,px)
        active=[p for p in active if p['shares']>0]; stale=0.;by=defaultdict(float)
        for p in active:
            rec=summaries.get((iso,p['symbol'])); mark=rec['close'] if rec else p['last_observed_mark']*(1-sign*stale_shock) if stale_shock is not None else p['mark']
            ref=(valuation_refs or {}).get(iso+'|'+p['symbol'])
            if not rec and ref and ref['observed_date']>=p['last_mark_date']:
                if ref['available_date']!=iso or ref['observed_date']>=iso:raise AssertionError('Prior reference must already be known')
                mark=ref['mark'];counts['valuation_reference_position_sessions']+=1
            book(p,sign*p['shares']*(mark-p['mark']));p['mark']=mark
            if rec:p['last_mark_date']=iso;p['last_observed_mark']=mark
            else:stale+=p['shares']*mark;counts['stale_position_sessions']+=1
            by[p['symbol']]+=p['shares']*mark
        gross=sum(by.values());equity=cash+sign*gross;pnl=equity-prev
        if abs(sum(day_pnl.values())-pnl)>1e-6:raise AssertionError('Daily side-cash conservation')
        target_eod=max(0,min(spec.u*(100000 if spec.fixed_equity else equity),130000));largest=max(by.values(),default=0.)
        daily.append({'date':iso,'pnl':pnl,'equity':equity,'cash':cash,'gross':gross,'target':target_eod,'occupancy':gross/target_eod if target_eod else None,
                      'unused_headroom':max(0,target_eod-gross),'gross_to_equity':gross/equity if equity>0 else None,'largest_symbol_gross':largest,
                      'largest_symbol_equity_fraction':largest/equity if equity>0 else None,'tickets':len(active),'symbols':len(by),
                      'cohorts':len({p['nominal'] for p in active}),'overlapping_symbol_tickets':len(active)-len(by),'stale_gross':stale,
                      'overdue_tickets':sum(p['expiry_date']<=iso for p in active),'new_gross':new_gross,'preorder_gross':pre_value,
                      'preorder_equity':pre_equity,'budget':cohort['budget'] if cohort else 0.,'short_borrow_base':short_base,'long_debit_base':debit_base,
                      'extra_spread':extra_spread,'turnover':turnover,'above_130k':gross>130000,
                      'excursion_cause':('new_allocation_and_marks' if new_gross else 'existing_inventory_drift') if gross>130000 else 'none'})
    details={'side':spec.side,'positions':positions,'terminal':active,'legs':legs,'daily':daily,'cohorts':cohorts,'orders':orders,'ticket_pnl':dict(ticket_pnl),'symbol_pnl':dict(symbol_pnl)}
    return metrics(spec,mode,details,months,counts),details

def metrics(spec,mode,detail,months,counts):
    daily=detail['daily'];active=detail['terminal'];positions=detail['positions'];sign=1 if spec.side=='long' else -1
    pnl=sum(r['pnl'] for r in daily);realized=sum(l['pnl'] for l in detail['legs']);terminal=sum(p['shares']*(sign*(p['mark']-p['entry'])-p['entry_cost']) for p in active)
    if abs(pnl-realized-terminal)>1e-6 or abs(pnl-sum(months.values()))>1e-6:raise AssertionError('Realized/terminal/cohort conservation')
    calendar=defaultdict(float);high=100000.;dd=ddpct=0.;under=[]
    for r in daily:
        calendar[r['date'][:7]]+=r['pnl'];high=max(high,r['equity']);dd=min(dd,r['equity']-high);ddpct=min(ddpct,r['equity']/high-1);under.append(r['equity']<high-1e-8)
    eq=100000.;cal=[]
    for m,v in calendar.items():cal.append({'month':m,'starting_equity':eq,'pnl':v,'return':v/eq if eq>0 else None,'ending_equity':eq+v});eq+=v
    gross=[r['gross'] for r in daily];targets=[r['target'] for r in daily];reds=[v for v in months.values() if v<0];cred=[v for v in calendar.values() if v<0]
    ndays=sum(mode=='ALL' or d.month%2==(mode=='IS') for d in SCORE);b=sum(r['short_borrow_base'] for r in daily);debit=sum(r['long_debit_base'] for r in daily);spread=sum(r['extra_spread'] for r in daily)
    attrs=defaultdict(lambda:{'trades':0,'pnl':0.,'entry_gross':0.})
    for p in positions:
        for key in ('primary_1_8' if p['rank']<=8 else 'reserve_9_20','observed' if p['feature_observed'] else 'unknown',f"confidence_{p['confidence']}"):
            attrs[key]['trades']+=1;attrs[key]['pnl']+=detail['ticket_pnl'][p['id']];attrs[key]['entry_gross']+=p['original_shares']*p['original_entry']
    symbol=sorted(detail['symbol_pnl'].items(),key=lambda x:x[1],reverse=True)
    return {'total_pnl':pnl,'per_day':pnl/ndays,'return':pnl/100000,'sessions':ndays,'trades':len(positions),'realized_pnl':realized,'terminal_net_mtm':terminal,
      'red_months':len(reds),'red_loss_sum':sum(reds),'worst_month':min(months.values()),'median_month':statistics.median(months.values()),'months':months,
      'calendar_months':cal,'calendar_red_months':len(cred),'calendar_red_loss_sum':sum(cred),'calendar_worst_month':min(calendar.values()),'calendar_median_month':statistics.median(calendar.values()),
      'max_dd':dd,'max_dd_percent':ddpct,'worst_day':min(r['pnl'] for r in daily),'time_underwater_sessions':sum(under),'longest_underwater_sessions':longest(under),
      'avg_exposure':statistics.mean(gross),'p95_exposure':sorted(gross)[math.ceil(.95*len(gross))-1],'peak_exposure':max(gross),'avg_target':statistics.mean(targets),
      'utilization':sum(gross)/sum(targets) if sum(targets)>0 else None,'mean_occupancy':statistics.mean(r['occupancy'] for r in daily if r['occupancy'] is not None),
      'avg_unused_headroom':statistics.mean(r['unused_headroom'] for r in daily),'longest_under_half_target':longest(r['gross']<.5*r['target'] for r in daily),
      'above_130k_sessions':sum(x>130000 for x in gross),'longest_above_130k':longest(x>130000 for x in gross),
      'exposure_dollar_days_above_130k':sum(max(0,r['gross']-130000)*((SCORE[i+1]-SCORE[i]).days if i+1<len(SCORE) else 0) for i,r in enumerate(daily)),
      'excursion_causes':dict(Counter(r['excursion_cause'] for r in daily if r['above_130k'])),
      'peak_gross_to_equity':max((r['gross_to_equity'] for r in daily if r['gross_to_equity'] is not None),default=None),
      'largest_symbol_equity_fraction':max((r['largest_symbol_equity_fraction'] for r in daily if r['largest_symbol_equity_fraction'] is not None),default=None),
      'peak_live_tickets':max(r['tickets'] for r in daily),'mean_live_tickets':statistics.mean(r['tickets'] for r in daily),'peak_live_symbols':max(r['symbols'] for r in daily),
      'peak_post_entry_gross_at_known_marks':max((c['surviving_gross']+c['filled_gross'] for c in detail['cohorts']),default=0.),
      'post_entry_above_130k_allocations':sum(c['surviving_gross']+c['filled_gross']>130000 for c in detail['cohorts']),
      'post_entry_peak_target_overshoot':max((max(0,c['surviving_gross']+c['filled_gross']-c['target']) for c in detail['cohorts']),default=0.),
      'post_entry_mark_convention':'Surviving inventory at last completed pre-order marks plus actual newly filled entry-open gross; pending simultaneous exits remain conservative obligations',
      'peak_live_cohorts':max(r['cohorts'] for r in daily),'same_symbol_overlap_sessions':sum(r['overlapping_symbol_tickets']>0 for r in daily),
      'turnover':sum(r['turnover'] for r in daily),'profit_per_avg_exposure':pnl/statistics.mean(gross) if sum(gross)>0 else None,
      'terminal_tickets':len(active),'terminal_gross':gross[-1],'terminal_stale_gross':daily[-1]['stale_gross'],'terminal_overdue':daily[-1]['overdue_tickets'],
      'stale_exposure_dollar_sessions':sum(r['stale_gross'] for r in daily),'attribution':dict(attrs),'counters':dict(counts),
      'short_borrow_base':b,'long_debit_base':debit,'negative_cash_sessions':sum(r['cash']<0 for r in daily),'max_margin_debit':max(max(0,-r['cash']) for r in daily),
      'scenarios':{f"{'borrow' if spec.side=='short' else 'debit'}_{int(rate*100)}_spread_{spreadmult}":pnl-rate*(b if spec.side=='short' else debit)-(spreadmult-1)*spread for rate in SCENARIOS['short_borrow' if spec.side=='short' else 'long_debit'] for spreadmult in SCENARIOS['spread']},
      'top_symbol_profit':symbol[:5],'bottom_symbol_profit':symbol[-5:],'top_symbol_concentration':symbol[0][1]/pnl if symbol and pnl>0 else None,
      'best_month_concentration':max(calendar.values())/pnl if pnl>0 else None,
      'adverse_10pct_all':-.1*max(gross),'adverse_50pct_largest':-.5*max(r['largest_symbol_gross'] for r in daily),
      'joint_adverse_other10_largest50':min(-.1*r['gross']-.4*r['largest_symbol_gross'] for r in daily),
      'absolute_economics':'CONDITIONAL: partial actions, missing held-position observations, unknown dividends/loans/financing'}

def score_job(job):
    raw,mode,ranks,summaries=job;spec=Spec(**raw);start=timer.monotonic();reference=None
    if spec.reference:reference=read(ROOT/'details'/(spec.reference+'_'+mode+'.json'))['cohorts']
    m,d=score(spec,mode,ranks,summaries,reference);path=ROOT/'details'/(spec.id+'_'+mode+'.json');dump(path,d)
    r={'spec':raw,'mode':mode,'metrics':m,'timestamp':stamp(),'score_seconds':timer.monotonic()-start,'code_sha256':code_identity(),
       'detail_path':path.relative_to(REPO_ROOT).as_posix(),'detail_sha256':digest(path)}
    dump(ROOT/'results'/(spec.id+'_'+mode+'.json'),r);return r

def load_prepared(mode,workers=8):
    authorize(mode);p=ROOT/f'prepared_{mode}.json'
    if not p.exists():
        from research.cg_arrow004_data import data_for
        r,s=data_for(mode,workers);dump(p,{'ranks':r,'summaries':{'|'.join(k):v for k,v in s.items()}})
    x=read(p);return x['ranks'],{tuple(k.split('|')):v for k,v in x['summaries'].items()}

def run_is(specs,workers=8,replay_reason=None):
    authorize('IS')
    for s in specs:
        p=ROOT/'results'/(s.id+'_IS.json')
        if p.exists():
            if not replay_reason:raise RuntimeError('Existing policy: new ID or explicit replay required')
            old=read(p);archive=ROOT/'superseded'/(s.id+'_'+digest(p)[:12]+'.json');dump(archive,old)
            old_detail=REPO_ROOT/old['detail_path'];dump(ROOT/'superseded'/(s.id+'_'+old['detail_sha256'][:12]+'_detail.json'),read(old_detail))
            ledger({'event':'REPLAY','id':s.id,'reason':replay_reason,'archive':archive.relative_to(REPO_ROOT).as_posix()})
        else:ledger({'event':'PREDECLARE','spec':asdict(s),'materiality':MATERIALITY})
    ranks,summaries=load_prepared('IS',workers);start=timer.monotonic();results=[]
    with ProcessPoolExecutor(max_workers=min(workers,8)) as pool:
        fs=[pool.submit(score_job,(asdict(s),'IS',ranks,summaries)) for s in specs]
        for n,f in enumerate(as_completed(fs),1):
            r=f.result();results.append(r);m=r['metrics'];ledger({'event':'COMPLETE','id':r['spec']['id'],'spec':r['spec'],'metrics':m,'score_seconds':r['score_seconds'],'detail_sha256':r['detail_sha256']})
            spent=timer.monotonic()-start
            print(f"{stamp()} IS {n}/{len(fs)} {r['spec']['id']} PnL={m['total_pnl']:.2f} day={m['per_day']:.2f} DD={m['max_dd']:.2f} util={m['utilization']:.3f} ETA~{spent/n*(len(fs)-n):.1f}s",flush=True)
    state=read(ROOT/'state.json');state.update(completed_is=sorted(p.stem[:-3] for p in (ROOT/'results').glob('*_IS.json')),elapsed_checkpoint_seconds=elapsed(),code_sha256=code_identity(),input_sha256=input_identity());dump(ROOT/'state.json',state)
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--specs',required=True);p.add_argument('--workers',type=int,default=8);p.add_argument('--replay-reason');a=p.parse_args()
    run_is([Spec(**s) for s in read(REPO_ROOT/a.specs)],a.workers,a.replay_reason)
