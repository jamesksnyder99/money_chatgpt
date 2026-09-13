from dataclasses import replace
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
import pytest

from research import cg_arrow003_data as data
from research import cg_arrow003_lab as lab


def market(signal=date(2026,1,7), prices=None):
    ranks={signal.isoformat():{"rows":[{"symbol":str(i),"prior_close":20.0,
                "prior_dv":20e6,"raw_return":.5-i*.01} for i in range(8)]}}
    summaries={}
    for d in data.FEATS:
        for i in range(8):
            px=(prices or {}).get(d,20.)
            summaries[(d.isoformat(),str(i))]={"schema":data.SCHEMA,"mark_kind":"minute_close",
                "close":px,"open":px,"high":px+1,"low":px-1,"volume":100.,
                "ts":d.isoformat()+"T15:59:00-05:00","first_ts":d.isoformat()+"T09:30:00-05:00",
                "entry_ts":d.isoformat()+"T15:59:00-05:00","entry_px":px,
                "preorder":px,"preorder_ts":d.isoformat()+"T15:58:00-05:00",
                "checkpoint":px,"cp_volume":90.,"next_open":px,
                "next_ts":d.isoformat()+"T15:56:00-05:00","late_volume_share":.2}
    return ranks,summaries


def test_legacy_evidence_unchanged():
    path=data.REPO_ROOT/"reports/cg_arrow003_legacy_identity.json"
    for rel,expected in data.read(path).items():
        assert data.digest(data.REPO_ROOT/rel)==expected,rel


def test_missing_future_exit_never_erases_entry():
    signal=date(2026,1,7)
    ranks,s=market(signal)
    due=data.FEATS[data.INDEX[signal]+11]
    s[(due.isoformat(),"0")]=None
    m,t=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)
    assert m["trades"]==8
    assert m["counters"]["delayed_exit_fills"]==1
    leg=next(x for x in t["legs"] if x["symbol"]=="0")
    assert date.fromisoformat(leg["exit_ts"][:10])>due
    assert leg["reason"]=="delayed_backstop"


def test_terminal_open_is_mark_not_fictitious_exit():
    ranks,s=market(date(2026,8,26))
    m,t=lab.score(lab.CONTROLS[0],"OOS",ranks,s,check=False)
    assert m["trades"]==8 and m["terminal_tickets"]==8
    assert t["legs"]==[]
    assert m["completed_leg_pnl"]==0
    assert m["terminal_gross"]==32000
    assert m["total_pnl"]==pytest.approx(-40)


def test_stale_terminal_reserves_exposure_and_has_no_fill():
    signal=date(2026,7,29)
    ranks,s=market(signal)
    for d in data.FEATS[data.INDEX[signal]+2:]:
        s[(d.isoformat(),"0")]=None
    m,t=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)
    assert m["terminal_tickets"]==1 and m["terminal_stale_gross"]==4000
    assert m["terminal_max_stale_sessions"]>10
    assert all(x["symbol"]!="0" for x in t["legs"])


def test_no_earlier_fallback_at_entry_or_scheduled_exit():
    signal=date(2026,1,7)
    ranks,s=market(signal)
    fill=data.FEATS[data.INDEX[signal]+1]
    s[(fill.isoformat(),"0")]["entry_ts"]=None
    s[(fill.isoformat(),"0")]["entry_px"]=None
    m,t=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)
    assert m["trades"]==7
    assert m["counters"]["missed_late_entry"]==1


def test_month_boundary_lifecycle_is_retained():
    ranks,s=market(date(2026,1,28))
    m,t=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)
    assert all(x["exit_ts"].startswith("2026-02") for x in t["legs"])
    assert m["months"]["2026-01"]==pytest.approx(m["total_pnl"])
    assert next(x for x in m["calendar_months"] if x["month"]=="2026-02")["pnl"]<0


def test_all_calendar_months_and_totals_reconcile():
    ranks,s=market()
    m,t=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)
    assert len(m["calendar_months"])==12 and len(t["daily"])==251
    assert sum(x["pnl"] for x in t["daily"])==pytest.approx(m["total_pnl"])
    assert sum(x["pnl"] for x in m["calendar_months"])==pytest.approx(m["total_pnl"])
    assert t["daily"][-1]["equity"]==pytest.approx(100000+m["total_pnl"])
    for prev,cur in zip(m["calendar_months"],m["calendar_months"][1:]):
        assert prev["ending_equity"]==pytest.approx(cur["starting_equity"])


@pytest.mark.parametrize("used",[0,120000,130000,134000])
def test_pro_rata_pacing_has_no_top_up_or_iteration_bias(used):
    a,scale=lab.pro_rata([1000,2000,3000,4000],used)
    b,_=lab.pro_rata([4000,3000,2000,1000],used)
    assert a==list(reversed(b))
    assert sum(a)<=max(0,130000-used)+1e-7
    assert all(x==pytest.approx(y*scale) for x,y in zip(a,[1000,2000,3000,4000]))


def test_pacing_uses_preorder_price_and_tolerates_fill_drift():
    ranks,s=market()
    fill=date(2026,1,8)
    for i in range(8):
        s[(fill.isoformat(),str(i))].update(entry_px=20.5,close=20.5)
    spec=replace(lab.CONTROLS[0],base=20000,pacing=True)
    m,t=lab.score(spec,"IS",ranks,s,check=False)
    day=next(x for x in t["daily"] if x["date"]==fill.isoformat())
    assert 130000<day["gross"]<135000
    assert m["trades"]==8
    assert all(x["reason"]=="backstop" for x in t["legs"])


def test_future_missing_fill_does_not_reallocate_batch():
    ranks,s=market()
    spec=replace(lab.CONTROLS[0],base=20000,pacing=True)
    _,a=lab.score(spec,"IS",ranks,s,check=False)
    s[("2026-01-08","0")]=None
    _,b=lab.score(spec,"IS",ranks,s,check=False)
    qa={p["symbol"]:p["initial_shares"] for p in a["positions"]}
    qb={p["symbol"]:p["initial_shares"] for p in b["positions"]}
    assert all(q==qa[sym] for sym,q in qb.items())


def test_features_exclude_current_volume_from_reference():
    _,s=market()
    h=[s[(d.isoformat(),"0")] for d in data.FEATS[:23]]
    h[-1]={**h[-1],"volume":200}
    f=data.features(h)
    assert f["volume_ratio"]==2 and f["volume_median_ratio"]==2
    assert f["volume_persistence3"]==1


def test_checkpoint_history_uses_matching_slot_and_causal_dates():
    _,s=market()
    d=date(2026,1,7)
    s[(d.isoformat(),"0")]["cp_volume"]=180
    assert data.checkpoint_ratio(d,"0",s)==2
    future=data.FEATS[data.INDEX[d]+1]
    s[(future.isoformat(),"0")]["cp_volume"]=900000
    assert data.checkpoint_ratio(d,"0",s)==2
    prior=data.FEATS[data.INDEX[d]-1]
    s[(prior.isoformat(),"0")]["cp_volume"]=None
    assert data.checkpoint_ratio(d,"0",s) is None


@pytest.mark.parametrize("early",[False,True])
def test_checkpoint_fill_and_early_close(early):
    d=date(2025,11,28) if early else date(2026,1,7)
    end=12 if early else 15
    ts=[datetime.combine(d,time(end,m),ZoneInfo("America/New_York")) for m in (55,56,58,59)]
    df=pl.DataFrame({"bar_start":ts,"open":[10.,11.,12.,13.],"high":[14.]*4,
                     "low":[9.]*4,"close":[10.5,11.5,12.5,13.5],"volume":[100]*4})
    rec=data.summarize(df,d)
    assert rec["entry_px"]==13.5
    if early:
        assert rec["checkpoint"] is None and rec["next_ts"] is None
    else:
        assert rec["checkpoint"]==10.5 and rec["next_open"]==11
        assert datetime.fromisoformat(rec["next_ts"]).time()>time(15,55)


@pytest.mark.parametrize("value",[None,0,-1,float("nan")])
def test_invalid_volume_taper_is_neutral(value):
    assert lab.volume_multiplier(lab.Spec("v",volume="taper"),{"volume_ratio":value})==1


def test_taper_and_blend_exact_definitions():
    f={"volume_ratio":4,"ret3":.1,"vol20":.01}
    assert lab.intended_amount(lab.Spec("x",volume="taper"),f)==2575
    assert lab.intended_amount(lab.Spec("b",family="BLEND"),f)==pytest.approx((2575+2075)/2)
    assert lab.momentum_multiplier(lab.Spec("m",momentum="taper"),f)==.5


def test_classifier_is_consistent_and_no_hard_exposure_failure():
    c={"total_pnl":1000,"red_loss_sum":-100,"worst_month":-100,"max_dd":-100,
       "worst_day":-100,"red_months":2,"peak_exposure":100000}
    m={**c,"total_pnl":1200,"red_loss_sum":-80,"worst_month":-80,"peak_exposure":134000}
    assert lab.classify(m,c)["classification"]=="BALANCED"
    assert not lab.classify(m,c)["soft_exposure_auto_failure"]


def test_signal_firewall_before_scoring():
    ranks,s=market(date(2026,2,4))
    with pytest.raises(RuntimeError,match="firewall"):
        lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)


def test_freeze_closes_research_and_minimum_reveal_clock(tmp_path,monkeypatch):
    monkeypatch.setattr(lab,"FREEZE",tmp_path/"freeze.json")
    monkeypatch.setattr(lab,"ROOT",tmp_path)
    monkeypatch.setattr(lab,"code_identity",lambda:{"code":"fixed"})
    monkeypatch.setattr(lab,"input_identity",lambda:{"input":"fixed"})
    monkeypatch.setattr(lab,"elapsed",lambda:134*60)
    with pytest.raises(RuntimeError,match="freeze"):
        lab.authorize("OOS")
    data.dump(lab.FREEZE,{"status":"FROZEN","code_sha256":{"code":"fixed"},"input_sha256":{"input":"fixed"}})
    with pytest.raises(RuntimeError,match="closed"):
        lab.authorize("IS")
    with pytest.raises(RuntimeError,match="135"):
        lab.authorize("OOS")


def test_no_unknown_split_factor_inference():
    # Raw convention remains explicit; an empty table is never zero-event certification.
    from research.cg_arrow002_preflight import inspect_splits
    status=inspect_splits()
    assert status["rows"]==0 and status["status"]=="BLOCKED"
    assert "raw" in data.SCHEMA


def test_documented_split_is_asof_and_price_volume_consistent(monkeypatch):
    monkeypatch.setattr(data,"action_events",lambda:[{"symbol":"TEST","effective_session":"2026-01-08","price_factor":5}])
    assert data.adjustment_factor("TEST",date(2026,1,7),date(2026,1,7))==1
    assert data.adjustment_factor("TEST",date(2026,1,7),date(2026,1,8))==5
    rec={"close":10.,"volume":1000.,"cp_volume":900.}
    adjusted=data.adjusted_record(rec,5)
    assert adjusted["close"]==50 and adjusted["volume"]==200 and adjusted["cp_volume"]==180
    assert rec["close"]==10


def test_held_split_preserves_economic_units_and_entry_cost(monkeypatch):
    ranks,s=market()
    event=date(2026,1,12)
    for d in data.FEATS[data.INDEX[event]:]:
        for i in range(8):
            s[(d.isoformat(),str(i))]=data.adjusted_record(s[(d.isoformat(),str(i))],5)
    monkeypatch.setattr(data,"action_events",lambda:[{"symbol":str(i),"effective_session":event.isoformat(),"price_factor":5} for i in range(8)])
    m,t=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)
    assert m["counters"]["held_split_adjustments"]==8
    assert all(p["initial_shares"]==40 for p in t["positions"])
    assert all(x["entry"]==100 and x["exit"]==100 for x in t["legs"])
    assert m["total_pnl"]==pytest.approx(-40-8*40*.105)


def test_outside_path_rejected_before_resolution():
    with pytest.raises(ValueError,match="outside"):
        data.safe_path(data.REPO_ROOT.parent/"outside_probe.parquet")


def test_minute_audit_does_not_sum_independent_highs(tmp_path,monkeypatch):
    from research import cg_arrow003_minute as minute
    d=date(2026,1,8)
    ts=[datetime.combine(d,time(9,m),ZoneInfo("America/New_York")) for m in (30,31)]
    def tape(day,symbol):
        prices=[30.,10.] if symbol=="A" else [10.,30.]
        return pl.DataFrame({"bar_start":ts,"close":prices}),"synthetic"
    monkeypatch.setattr(minute,"read_bars",tape)
    monkeypatch.setattr(minute,"ROOT",tmp_path)
    monkeypatch.setattr(minute,"REPO_ROOT",tmp_path)
    positions=[]
    for sym in ("A","B"):
        p={"symbol":sym,"fill_date":"2026-01-07","entry_ts":"2026-01-07T15:59:00-05:00",
           "initial_shares":100,"entry":20.}
        positions.append((p,[]))
    _,out,_=minute.day_job((d.isoformat(),{"TEST":positions},{"A":20.,"B":20.}))
    assert out["TEST"]["minute_peak"]["gross"]==4000
    assert out["TEST"]["minute_peak"]["gross"]<6000  # sum of separate highs


def test_minute_share_clock_distinguishes_close_and_open_executions():
    from research import cg_arrow003_minute as minute
    p={"symbol":"TEST","fill_date":"2026-01-07","entry_ts":"2026-01-07T15:59:00-05:00",
       "initial_shares":100,"entry":20.}
    before=datetime.fromisoformat("2026-01-07T15:59:00-05:00")
    after=datetime.fromisoformat("2026-01-07T16:00:00-05:00")
    assert minute.remaining_shares(p,[],before)==0
    assert minute.remaining_shares(p,[],after)==100
    leg={"exit_ts":"2026-01-08T15:56:00-05:00","reason":"half_cover","shares":50}
    # The close sample at15:56 is immediately before the next-open cover there.
    assert minute.remaining_shares(p,[leg],datetime.fromisoformat(leg["exit_ts"]))==100
    assert minute.remaining_shares(p,[leg],datetime.fromisoformat("2026-01-08T15:57:00-05:00"))==50


def test_minute_management_causal_next_print_and_state(monkeypatch):
    ranks,s=market()
    signal=date(2026,1,7)
    fill=data.INDEX[signal]+1
    d=data.FEATS[fill+6]
    p={"symbol":"0","covered":False,"fill_index":fill,"entry":25.,"atr":2.,
       "feature":{"volume_ratio":.8}}
    spec=lab.Spec("minute",cover="low_participation",cover_clock="all_minutes",min_hold=6)
    obs=[{"decision":d.isoformat()+"T10:00:00-05:00","price":21.,
          "execution":d.isoformat()+"T10:01:00-05:00","fill":22.}]
    monkeypatch.setattr(lab,"minute_observations",lambda *a:obs)
    result=lab.cover_observation(spec,p,d,s[(d.isoformat(),"0")],s)
    assert result["next_open"]==22
    p["feature"]["volume_ratio"]=1.2
    assert lab.cover_observation(spec,p,d,s[(d.isoformat(),"0")],s) is None
    p["feature"]["volume_ratio"]=.8
    obs[0]["execution"]=obs[0]["decision"]
    with pytest.raises(RuntimeError,match="follow"):
        lab.cover_observation(spec,p,d,s[(d.isoformat(),"0")],s)


def test_stall_votes_different_from_net_return_without_long_history():
    spec=lab.Spec("votes",family="R5",base=8300,momentum="votes")
    f={"ret3":.2,"positive_days3":1,"volume_ratio":.9,"vol20":None}
    assert lab.intended_amount(spec,f)==8300
    assert lab.intended_amount(replace(spec,momentum="switch"),f)==4150
    assert lab.intended_amount(spec,{**f,"positive_days3":2})==4150
    cautious=replace(spec,momentum_missing="original_switch")
    assert lab.intended_amount(cautious,f)==4150
    assert lab.intended_amount(cautious,{**f,"vol20":.01})==8300


def test_stale_counterfactual_is_not_compounded_and_reverses_at_real_print():
    ranks,s=market()
    missing=data.FEATS[data.INDEX[date(2026,1,8)]+1:data.INDEX[date(2026,1,8)]+4]
    for d in missing:s[(d.isoformat(),"0")]=None
    base,bt=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False)
    stressed,st=lab.score(lab.CONTROLS[0],"IS",ranks,s,check=False,stale_shock=.5)
    assert stressed["total_pnl"]==pytest.approx(base["total_pnl"])
    assert st["legs"]==bt["legs"]
    daily={r["date"]:r for r in st["daily"]}
    assert daily[missing[0].isoformat()]["pnl"]==pytest.approx(-2000)
    assert daily[missing[1].isoformat()]["pnl"]==0
    assert daily[missing[2].isoformat()]["pnl"]==0
    real=data.FEATS[data.INDEX[missing[-1]]+1]
    assert daily[real.isoformat()]["pnl"]==pytest.approx(2000)
    with pytest.raises(ValueError,match="IS-only"):
        lab.score(lab.CONTROLS[0],"OOS",{},s,check=False,stale_shock=.5)


def test_stale_counterfactual_reserves_capacity_without_inventing_exits():
    ranks,s=market()
    first=date(2026,1,7)
    second=date(2026,1,14)
    ranks[second.isoformat()]={"rows":[{"symbol":str(i),"prior_close":20.,"prior_dv":20e6,"raw_return":.5}
                                             for i in range(8,16)]}
    for d in data.FEATS:
        for i in range(8,16):s[(d.isoformat(),str(i))]=dict(s[(d.isoformat(),"0")])
    for d in data.FEATS[data.INDEX[first]+2:]:
        for i in range(8):s[(d.isoformat(),str(i))]=None
    spec=lab.Spec("synthetic_paced",family="PARENT",base=8000,pacing=True)
    b,bd=lab.score(spec,"IS",ranks,s,check=False)
    m,details=lab.score(spec,"IS",ranks,s,check=False,stale_shock=.5)
    assert m["terminal_tickets"]==b["terminal_tickets"]==8
    assert all(int(leg["symbol"])>=8 for leg in details["legs"])
    assert sum(p["ticket"] for p in details["positions"] if p["signal"]==second.isoformat())==pytest.approx(34000)
    assert sum(p["ticket"] for p in bd["positions"] if p["signal"]==second.isoformat())==pytest.approx(64000)


def test_joint_calendar_account_is_not_the_sum_of_isolated_capital_books():
    first=date(2026,1,28)
    second=date(2026,2,4)
    ir,s=market(first)
    er,_=market(second)
    spec=lab.Spec("joint",family="PARENT",base=10000,pacing=True)
    im,_=lab.score(spec,"IS",ir,s,check=False)
    em,_=lab.score(spec,"OOS",er,s,check=False)
    combined,detail=lab.score(spec,"ALL",{**ir,**er},s,check=False)
    assert combined["intended_notional"]==130000
    assert im["intended_notional"]+em["intended_notional"]==160000
    assert combined["total_pnl"]!=pytest.approx(im["total_pnl"]+em["total_pnl"])
    assert combined["trades"]==16
    assert len(combined["calendar_months"])==12 and len(detail["daily"])==251


def test_pending_same_close_exits_cannot_fund_new_orders_in_advance():
    first=date(2026,1,7)
    ranks,s=market(first)
    due=data.FEATS[data.INDEX[first]+11]
    # Synthetic dense schedule exercises the order-state boundary, independently
    # of the production Wednesday selection calendar.
    second=data.FEATS[data.INDEX[due]-1]
    ranks[second.isoformat()]={"rows":[dict(x) for x in ranks[first.isoformat()]["rows"]]}
    spec=lab.Spec("pending",family="PARENT",base=16000,pacing=True)
    m,detail=lab.score(spec,"IS",ranks,s,check=False)
    d=next(x for x in detail["daily"] if x["date"]==due.isoformat())
    assert d["preorder_gross"]==128000
    assert d["new_gross"]==1920
    assert d["gross"]==1920


def test_executed_early_covers_release_capacity_before_later_new_orders():
    first=date(2026,1,7)
    ranks,s=market(first)
    fill=data.INDEX[first]+1
    cover_day=data.FEATS[fill+6]
    previous=data.FEATS[data.INDEX[cover_day]-1]
    for i in range(8):
        s[(previous.isoformat(),str(i))]["close"]=14.
        s[(cover_day.isoformat(),str(i))].update(checkpoint=15.,next_open=15.,preorder=15.,entry_px=15.,close=15.)
    ranks[previous.isoformat()]={"rows":[dict(x) for x in ranks[first.isoformat()]["rows"]]}
    spec=lab.Spec("released",family="PARENT",base=16000,pacing=True,cover="low_participation",min_hold=6)
    m,detail=lab.score(spec,"IS",ranks,s,check=False)
    d=next(x for x in detail["daily"] if x["date"]==cover_day.isoformat())
    assert d["preorder_gross"]==48000
    assert d["new_gross"]==81960
    assert d["gross"]==129960


def test_independent_cash_oracle_detects_a_balanced_ledger_error(tmp_path,monkeypatch):
    from dataclasses import asdict
    from research import cg_arrow003_oracle as oracle
    ranks,s=market()
    spec=lab.CONTROLS[0]
    m,detail=lab.score(spec,"IS",ranks,s,check=False)
    for d in data.SCORE:
        data.dump(tmp_path/"summaries"/(d.isoformat()+".json"),{str(i):s[(d.isoformat(),str(i))] for i in range(8)})
    path=tmp_path/"details.json"
    data.dump(path,detail)
    record={"spec":asdict(spec),"detail_path":"details.json","detail_sha256":data.digest(path)}
    data.dump(tmp_path/"results/PARENT_IS.json",record)
    monkeypatch.setattr(oracle,"ROOT",tmp_path)
    monkeypatch.setattr(oracle,"REPO_ROOT",tmp_path)
    assert oracle.verify("PARENT","IS")["observed_executions_verified"]==16
    detail["daily"][20]["equity"]+=1
    data.dump(path,detail)
    record["detail_sha256"]=data.digest(path)
    data.dump(tmp_path/"results/PARENT_IS.json",record)
    with pytest.raises(AssertionError,match="cash/liability mismatch"):
        oracle.verify("PARENT","IS")


def test_minute_equity_uses_cover_cash_and_separates_close_from_next_open(tmp_path,monkeypatch):
    from research import cg_arrow003_minute as minute
    d=date(2026,1,8)
    ts=[datetime.combine(d,time(9,m),ZoneInfo("America/New_York")) for m in (30,31)]
    monkeypatch.setattr(minute,"read_bars",lambda *a:(pl.DataFrame({"bar_start":ts,"close":[20.,20.]}),"synthetic"))
    monkeypatch.setattr(minute,"ROOT",tmp_path)
    monkeypatch.setattr(minute,"REPO_ROOT",tmp_path)
    p={"symbol":"A","fill_date":"2026-01-07","entry_ts":"2026-01-07T15:59:00-05:00","initial_shares":100,"entry":20.}
    leg={"exit_ts":"2026-01-08T09:31:00-05:00","reason":"half_cover","shares":50,"exit":25.}
    _,out,provenance=minute.day_job((d.isoformat(),{"TEST":[(p,[leg])]},
                              {"A":20.},{"TEST":{"cash":102000.,"equity":100000.}}))
    rows=data.read(tmp_path/provenance["path"])["books"]["TEST"]
    assert rows[0]["equity"]==100000  # previous minute close before next-open cover
    assert rows[1]["equity"]==pytest.approx(99748.5)  #250loss plus1.50 exit cost
    assert out["TEST"]["end_of_session_equity"]==pytest.approx(99748.5)
    assert out["TEST"]["within_day_max_drawdown"]==pytest.approx(-251.5)


def test_zero_share_half_cover_is_not_an_execution():
    signal=date(2026,1,7)
    ranks,s=market(signal)
    d=data.FEATS[data.INDEX[signal]+4]
    previous=data.FEATS[data.INDEX[d]-1]
    for i in range(8):
        s[(previous.isoformat(),str(i))]["close"]=14.
        s[(d.isoformat(),str(i))].update(checkpoint=15.,next_open=15.,close=15.)
    spec=lab.Spec("tiny",base=30,cover="low_participation")
    m,detail=lab.score(spec,"IS",ranks,s,check=False)
    assert m["counters"].get("half_covers",0)==0
    assert m["counters"]["zero_share_half_cover_attempts"]==8
    assert not any(leg["reason"]=="half_cover" for leg in detail["legs"])


def test_preorder_fallback_uses_entry_date_share_units(monkeypatch):
    signal=date(2026,1,7)
    ranks,s=market(signal)
    entry=data.FEATS[data.INDEX[signal]+1]
    for d in data.FEATS[data.INDEX[entry]:]:
        for i in range(8):s[(d.isoformat(),str(i))]=data.adjusted_record(s[(d.isoformat(),str(i))],5)
    for i in range(8):s[(entry.isoformat(),str(i))]["preorder"]=None
    monkeypatch.setattr(data,"action_events",lambda:[{"symbol":str(i),"effective_session":entry.isoformat(),"price_factor":5} for i in range(8)])
    spec=lab.Spec("preorder_split",family="PARENT",base=4000,pacing=True)
    m,detail=lab.score(spec,"IS",ranks,s,check=False)
    assert all(p["original_shares"]==40 for p in detail["positions"])
    assert next(r for r in detail["daily"] if r["date"]==entry.isoformat())["new_gross"]==32000


def test_backstop_day_cover_is_an_explicit_rule_and_remainder_still_exits():
    signal=date(2026,1,7)
    ranks,s=market(signal)
    due=data.FEATS[data.INDEX[signal]+11]
    prev=data.FEATS[data.INDEX[due]-1]
    for i in range(8):
        s[(prev.isoformat(),str(i))]["close"]=14.
        s[(due.isoformat(),str(i))].update(checkpoint=15.,next_open=15.,entry_px=16.,close=16.)
    spec=lab.Spec("backstop_cover",family="PARENT",base=4000,cover="low_participation")
    baseline,bd=lab.score(spec,"IS",ranks,s,check=False)
    m,detail=lab.score(replace(spec,cover_on_backstop=True),"IS",ranks,s,check=False)
    assert baseline["exit_legs"]==8 and m["exit_legs"]==16
    assert m["terminal_tickets"]==0 and m["trades"]==baseline["trades"]==8
    assert all(leg["exit_ts"][:10]==due.isoformat() for leg in detail["legs"])
    assert m["total_pnl"]>baseline["total_pnl"]


def test_fractional_split_and_partial_cover_pass_independent_cash_and_minute_audits(tmp_path,monkeypatch):
    from dataclasses import asdict
    from collections import defaultdict
    from research import cg_arrow003_oracle as oracle
    from research import cg_arrow003_minute as minute
    signal=date(2026,1,7)
    ranks,s=market(signal)
    event=date(2026,1,12)
    for d in data.FEATS[data.INDEX[event]:]:
        for i in range(8):s[(d.isoformat(),str(i))]=data.adjusted_record(s[(d.isoformat(),str(i))],5)
    monkeypatch.setattr(data,"action_events",lambda:[{"symbol":str(i),"effective_session":event.isoformat(),"price_factor":5} for i in range(8)])
    cover_day=data.FEATS[data.INDEX[signal]+7]
    previous=data.FEATS[data.INDEX[cover_day]-1]
    for i in range(8):
        s[(previous.isoformat(),str(i))]["close"]=70.
        s[(cover_day.isoformat(),str(i))].update(checkpoint=75.,next_open=75.)
    spec=lab.Spec("fractional_fixture",family="PARENT",base=1050,cover="low_participation",min_hold=6)
    m,detail=lab.score(spec,"IS",ranks,s,check=False)
    assert m["counters"]["fractional_split_liabilities"]==8
    assert m["counters"]["half_covers"]==8
    assert all(x["shares"]==5 for x in detail["legs"] if x["reason"]=="half_cover")
    assert all(x["shares"]==pytest.approx(5.4) for x in detail["legs"] if x["reason"]=="backstop")
    assert m["total_pnl"]==pytest.approx(8*(52*(20-.025)-5*(75+.08)-5.4*(100+.105)))
    for d in data.SCORE:
        data.dump(tmp_path/"summaries"/(d.isoformat()+".json"),{str(i):s[(d.isoformat(),str(i))] for i in range(8)})
    path=tmp_path/"details.json"
    data.dump(path,detail)
    data.dump(tmp_path/"results/fractional_fixture_IS.json",{
        "spec":asdict(spec),"detail_path":"details.json","detail_sha256":data.digest(path)})
    monkeypatch.setattr(oracle,"ROOT",tmp_path)
    monkeypatch.setattr(oracle,"REPO_ROOT",tmp_path)
    assert oracle.verify(spec.id,"IS")["observed_executions_verified"]==24
    monkeypatch.setattr(minute,"ROOT",tmp_path)
    monkeypatch.setattr(minute,"REPO_ROOT",tmp_path)
    ts=[datetime.combine(event,t,ZoneInfo("America/New_York")) for t in (time(9,30),time(15,59))]
    monkeypatch.setattr(minute,"read_bars",lambda *a:(pl.DataFrame({"bar_start":ts,"close":[100.,100.]}),"synthetic"))
    legs=defaultdict(list)
    for leg in detail["legs"]:legs[leg["ticket_id"]].append(leg)
    prev=detail["daily"][data.SCORE.index(event)-1]
    _,out,_=minute.day_job((event.isoformat(),{"TEST":[(p,legs[p["id"]]) for p in detail["positions"]]},
                           {str(i):100. for i in range(8)},{"TEST":{"cash":prev["equity"]+prev["gross"],"equity":prev["equity"]}}))
    assert out["TEST"]["end_of_session_equity"]==pytest.approx(prev["equity"])


def test_minute_drawdown_keeps_global_peak_when_equity_crosses_zero():
    from research.cg_arrow003_minute import equity_drawdown
    dollars,percent=equity_drawdown([[100000.,1000.],[500.,-10000.,200000.,-15000.]])
    assert dollars==-215000.
    assert percent==pytest.approx(-1.1)
