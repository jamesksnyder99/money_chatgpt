from datetime import date,datetime,timedelta
import pytest
from research import cg_arrow004_lab as lab
from research import cg_arrow004_data as data
from ingest.calendar import nyse_sessions

def row(symbol='AAA',rank=1,v=.8,r=0.):
    return {'symbol':symbol,'rank':rank,'prior_close':10.,'feature':{'volume_ratio':v,'ret3':r,'up_session':True,'close_location':.8,'history20_observed':True}}

def toy(monkeypatch,side='long',exit_price=12.,missing=False,delayed=False):
    days=nyse_sessions(date(2025,9,2),date(2025,9,19) if delayed else date(2025,9,18))
    monkeypatch.setattr(lab,'SCORE',days)
    ranks={'2025-09-03':{side:[row()]}}
    summaries={}
    for d in days:
        px=exit_price if d>=date(2025,9,18) else 10.
        summaries[(d.isoformat(),'AAA')]={'open':px,'close':px,'preorder':px,'entry_open':px,
          'first_ts':datetime.combine(d,datetime.min.time().replace(hour=9,minute=30),data.ET).isoformat(),
          'scheduled_exit_open':px,'scheduled_exit_ts':data.clock(d,60).isoformat()}
    if missing:summaries.pop(('2025-09-18','AAA'))
    spec=lab.Spec('TOY',side=side,family='EQUAL',allocation='fixed',ticket=1000.)
    return lab.score(spec,'IS',ranks,summaries)

@pytest.mark.parametrize('side,price,expected',[('long',12,196.8),('long',8,-203.),('short',12,-203.2),('short',8,197.)])
def test_side_cash_and_costs(monkeypatch,side,price,expected):
    m,d=toy(monkeypatch,side,price)
    assert m['total_pnl']==pytest.approx(expected)
    for r in d['daily']:
        assert r['equity']==pytest.approx(r['cash']+(1 if side=='long' else -1)*r['gross'])
    assert m['terminal_tickets']==0

def test_short_proceeds_not_equity(monkeypatch):
    m,d=toy(monkeypatch,'short')
    entry=next(r for r in d['daily'] if r['date']=='2025-09-04')
    assert entry['cash']==pytest.approx(100998.5)
    assert entry['equity']==pytest.approx(99998.5)

def test_future_missing_exit_retains_entry_and_terminal(monkeypatch):
    m,d=toy(monkeypatch,missing=True)
    assert m['trades']==1 and m['terminal_tickets']==1
    assert m['terminal_stale_gross']==1000
    assert not d['legs']
    assert m['total_pnl']==pytest.approx(-1.5)

def test_later_exit_never_backdates(monkeypatch):
    m,d=toy(monkeypatch,missing=True,delayed=True)
    assert m['trades']==1 and m['terminal_tickets']==0
    assert d['legs'][0]['exit_ts'].startswith('2025-09-19T09:30')
    assert m['counters']['delayed_exit_fills']==1

def test_nominal_schedule_and_global_phases():
    s=data.schedule();assert s[0]['nominal']=='2025-09-04' and s[0]['phase']=='A'
    for i,c in enumerate(s):
        assert date.fromisoformat(c['nominal_expiry'])-date.fromisoformat(c['nominal'])==timedelta(days=14)
        assert c['phase']==('A' if i%2==0 else 'B')
        assert datetime.fromisoformat(c['exit_ts']).hour in (12,15)
        assert datetime.fromisoformat(c['entry_ts']).minute==59
    x=next(c for c in s if c['nominal']=='2025-11-27')
    assert x['entry_date']=='2025-11-26' and x['signal']=='2025-11-25'
    x=next(c for c in s if c['nominal']=='2025-12-25')
    assert x['entry_date']=='2025-12-24' and x['entry_ts'].endswith('12:59:00-05:00')
    x=next(c for c in s if c['nominal']=='2025-12-11')
    assert x['expiry_date']=='2025-12-24' and x['exit_ts'].endswith('12:00:00-05:00')

def test_weekly_budget_half_target_not_half_headroom_or_cash():
    spec=lab.Spec('B')
    assert lab.capital(100000,30000,spec)==(100000,70000,50000)
    assert lab.capital(100000,90000,spec)==(100000,10000,10000)
    assert lab.capital(100000,30000,spec,10000)==(100000,60000,50000)
    assert lab.capital(100000,30000,lab.Spec('C',rhythm='A'))==(100000,70000,70000)

def test_no_virtual_unused_credit():
    spec=lab.Spec('P',allocation='carry')
    assert lab.capital(100000,80000,spec)[1]==20000
    assert lab.capital(90000,80000,spec)[1]==10000

def test_recovery_requires_direction_and_equal_sizing_keeps_membership():
    s=lab.Spec('R',side='long',family='R5',allocation='select8',feature='recovery')
    h=row(v=2,r=.1)
    assert lab.confidence(s,h)==(1.,True,True)
    h['feature']['up_session']=False
    assert lab.confidence(s,h)==(.5,True,False)
    rows=[row(str(i),i,2.,-.1) for i in range(1,21)]
    for h in rows[8:12]:h['feature']['ret3']=.1
    a=lab.allocate(s,rows,50000,100000,100000,{})
    eq=lab.Spec('E',side='long',family='R5',allocation='select8_equal',feature='recovery')
    b=lab.allocate(eq,rows,50000,100000,100000,{})
    assert [h['symbol'] for h,v in a]==[h['symbol'] for h,v in b]
    assert [v for h,v in b]==[6250.]*8
    assert len(set(v for h,v in a))==2

def test_patient_leaves_unqualified_slots_idle():
    rows=[row(str(i),i,2.,-.1) for i in range(1,21)]
    rows[8]['feature']['ret3']=.1
    rows[9]['feature']['ret3']=None
    s=lab.Spec('P',side='long',family='R5',allocation='qualified8',feature='recovery')
    a=lab.allocate(s,rows,50000,100000,100000,{})
    assert [(h['rank'],v) for h,v in a]==[(9,6250.)]

def test_signal_features_ignore_future_observations():
    signal=date(2025,9,3)
    prior=data.FEATS[data.INDEX[signal]-22:data.INDEX[signal]+1]
    summaries={(d.isoformat(),'AAA'):{'mark_kind':'minute_close','open':10.,'high':12.,'low':9.,'close':11.,'volume':1000.} for d in prior}
    expected=data.feature_row('AAA',signal,summaries)
    assert expected['volume_ratio']==1. and expected['ret3']==0.
    summaries[('2025-09-04','AAA')]={'open':1.,'high':10000.,'low':.01,'close':9999.,'volume':1e12}
    assert data.feature_row('AAA',signal,summaries)==expected

def test_month_daily_terminal_conservation(monkeypatch):
    m,d=toy(monkeypatch,missing=True)
    assert sum(x['pnl'] for x in d['daily'])==pytest.approx(sum(m['months'].values()))
    assert sum(x['pnl'] for x in m['calendar_months'])==pytest.approx(m['total_pnl'])
    assert m['realized_pnl']+m['terminal_net_mtm']==pytest.approx(m['total_pnl'])

def test_prior_reference_is_valuation_only_and_cannot_fill_missing_exit(monkeypatch):
    days=nyse_sessions(date(2025,9,2),date(2025,9,19));monkeypatch.setattr(lab,'SCORE',days)
    summaries={('2025-09-04','AAA'):{'open':10.,'close':10.,'preorder':10.,'entry_open':10.,'first_ts':'2025-09-04T09:30:00-04:00'}}
    refs={'2025-09-18|AAA':{'mark':12.,'observed_date':'2025-09-17','available_date':'2025-09-18'}}
    ranks={'2025-09-03':{'long':[row()]}}
    s=lab.Spec('L',side='long',family='EQUAL',allocation='fixed',ticket=1000)
    m,d=lab.score(s,'IS',ranks,summaries,valuation_refs=refs)
    assert m['total_pnl']==pytest.approx(198.5) and m['terminal_tickets']==1
    assert not d['legs'] and m['counters']['valuation_reference_position_sessions']==1
    assert m['terminal_stale_gross']==1200
    refs['2025-09-18|AAA']['observed_date']='2025-09-18'
    with pytest.raises(AssertionError,match='already be known'):lab.score(s,'IS',ranks,summaries,valuation_refs=refs)

def test_simultaneous_caps_and_redistribution():
    a=lab.weighted_alloc([1,1,1],100,[10,100,100])
    assert a==pytest.approx([10,45,45])
    assert lab.weighted_alloc([1,1],100,[10,20])==pytest.approx([10,20])

def test_reserve_unknown_not_favorable_and_rank9_can_replace():
    spec=lab.Spec('R',allocation='reserve',family='R5')
    rows=[row(str(i),i,2.,.1) for i in range(1,9)]+[row('nine',9,.8,-.1),row('unknown',10,None,None)]
    a=lab.allocate(spec,rows,50000,100000,100000,{})
    assert dict((h['symbol'],v) for h,v in a)['nine']==6250
    assert 'unknown' not in dict((h['symbol'],v) for h,v in a)
    s=lab.Spec('S',allocation='select8',family='R5')
    chosen=lab.allocate(s,rows,50000,100000,100000,{})
    assert 'nine' in [h['symbol'] for h,v in chosen]
    assert len(chosen)==8

def test_long_momentum_reversal_and_missing_weight():
    short=lab.Spec('S',family='R5');long=lab.Spec('L',side='long',family='R5')
    assert lab.confidence(short,row(r=-.1))[0]==1
    assert lab.confidence(long,row(r=-.1))[0]==.5
    assert lab.confidence(long,row(r=.1))[0]==1
    assert lab.confidence(long,row(v=None,r=None),True)==(.25,False,False)

def test_margin_financing_is_side_correct(monkeypatch):
    days=nyse_sessions(date(2025,9,2),date(2025,9,5));monkeypatch.setattr(lab,'SCORE',days)
    s=lab.Spec('L',side='long',family='EQUAL',allocation='fixed',ticket=120000)
    ranks={'2025-09-03':{'long':[row()]}};summaries={(d.isoformat(),'AAA'):{'open':10.,'close':10.,'preorder':10.,'entry_open':10.,'first_ts':data.clock(d,390).isoformat()} for d in days}
    m,d=lab.score(s,'IS',ranks,summaries)
    assert m['negative_cash_sessions']==2 and m['long_debit_base']>0 and m['short_borrow_base']==0
    assert m['scenarios']['debit_10_spread_1']<m['scenarios']['debit_0_spread_1']

def test_entry_quantities_do_not_use_entry_bar_close(monkeypatch):
    days=nyse_sessions(date(2025,9,2),date(2025,9,4));monkeypatch.setattr(lab,'SCORE',days)
    s=lab.Spec('L',side='long',family='EQUAL',allocation='fixed',ticket=1000)
    ranks={'2025-09-03':{'long':[row()]}};summaries={('2025-09-04','AAA'):{'open':10.,'close':100.,'preorder':10.,'entry_open':11.,'first_ts':'2025-09-04T09:30:00-04:00'}}
    m,d=lab.score(s,'IS',ranks,summaries)
    assert d['positions'][0]['original_shares']==100
    assert d['positions'][0]['original_entry']==11

def test_week_old_cohort_survives_and_due_exit_releases_actual_capacity(monkeypatch):
    days=nyse_sessions(date(2025,9,2),date(2025,9,18));monkeypatch.setattr(lab,'SCORE',days)
    ranks={s:{'long':[row(str(i),i) for i in range(1,9)]} for s in ('2025-09-03','2025-09-10','2025-09-17')}
    summaries={(d.isoformat(),str(i)):{'open':10.,'close':10.,'preorder':10.,'entry_open':10.,'first_ts':data.clock(d,390).isoformat(),
                  'scheduled_exit_open':10.,'scheduled_exit_ts':data.clock(d,60).isoformat()} for d in days for i in range(1,9)}
    m,detail=lab.score(lab.Spec('W',side='long',family='EQUAL',allocation='equal8'),'IS',ranks,summaries)
    last=detail['cohorts'][-1]
    assert last['surviving_cohorts']==1 and last['pending_due_tickets']==0
    assert {p['nominal'] for p in detail['terminal']}=={'2025-09-11','2025-09-18'}
    assert all(x['exit_ts']<'2025-09-18T15:59:00-04:00' for x in detail['legs'])
    for i in range(1,9):summaries[('2025-09-18',str(i))]['scheduled_exit_ts']='2025-09-18T15:59:00-04:00'
    m,detail=lab.score(lab.Spec('D',side='long',family='EQUAL',allocation='equal8'),'IS',ranks,summaries)
    assert detail['cohorts'][-1]['pending_due_tickets']==8
    assert detail['cohorts'][-1]['budget']<500

def test_split_neutral_value_and_quantities(monkeypatch):
    monkeypatch.setattr(lab,'adjustment_factor',lambda sym,a,b:2. if a<date(2025,9,10)<=b else 1.)
    days=nyse_sessions(date(2025,9,2),date(2025,9,18));monkeypatch.setattr(lab,'SCORE',days)
    summaries={}
    for d in days:
        px=20. if d>=date(2025,9,10) else 10.
        summaries[(d.isoformat(),'AAA')]={'open':px,'close':px,'preorder':px,'entry_open':px,'first_ts':data.clock(d,390).isoformat(),
                 'scheduled_exit_open':px,'scheduled_exit_ts':data.clock(d,60).isoformat()}
    for side in ('long','short'):
        m,detail=lab.score(lab.Spec('X',side=side,family='EQUAL',allocation='fixed',ticket=1000),'IS',{'2025-09-03':{side:[row()]}},summaries)
        assert detail['legs'][0]['shares']==50
        assert m['total_pnl']==pytest.approx(-2.75)

@pytest.mark.parametrize('allocation',['carry','carry_full'])
def test_carry_cannot_hide_half_budget_startup(monkeypatch,allocation):
    days=nyse_sessions(date(2025,9,2),date(2025,9,11));monkeypatch.setattr(lab,'SCORE',days)
    ranks={s:{'short':[row(str(i),i,.8,-.1) for i in range(1,21)]} for s in ('2025-09-03','2025-09-10')}
    summaries={(d.isoformat(),str(i)):{'open':10.,'close':10.,'preorder':10.,'entry_open':10.,'first_ts':data.clock(d,390).isoformat()} for d in days for i in range(1,21)}
    m,detail=lab.score(lab.Spec('C',family='R5',allocation=allocation),'IS',ranks,summaries)
    assert detail['cohorts'][0]['budget']==50000
    assert detail['cohorts'][0]['intended']<=50000
    assert detail['cohorts'][1]['budget']==pytest.approx(detail['cohorts'][1]['headroom'])
