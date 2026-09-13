from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
import json
import math

import polars as pl
import pytest

import research.cg_arrow002_lab as lab
from research.arrow43 import last_rth
from research.costs import signed_pnl


def test_signal_firewall_and_full_calendar():
    days = lab.signal_dates("IS",check=False)
    assert len(days) == 25
    assert all(d.month % 2 for d in days)
    assert {d.strftime("%Y-%m") for d in days} == {
        "2025-09","2025-11","2026-01","2026-03","2026-05","2026-07"}
    with pytest.raises(RuntimeError,match="forbidden"):
        lab.assert_signals([date(2026,2,4)],"IS")
    with pytest.raises(RuntimeError):
        lab.assert_signals([date(2026,1,7)],"OOS")


def test_firewall_precedes_universe_read(monkeypatch):
    monkeypatch.setattr(lab,"signal_dates",lambda *a:[date(2026,2,4)])
    monkeypatch.setattr(lab,"_elig_year",lambda *a:pytest.fail("universe reader reached"))
    with pytest.raises(RuntimeError,match="forbidden"):
        lab.prepare("IS")


def test_frozen_parent_cannot_mutate():
    assert lab.PARENT.ticket == 4000
    assert lab.PARENT.schedule == "wed"
    assert lab.PARENT.cap is None
    assert lab.PARENT.protection == "none"
    with pytest.raises(FrozenInstanceError):
        lab.PARENT.ticket = 5000


def test_invalid_freeze_blocks(tmp_path):
    with pytest.raises(RuntimeError,match="freeze"):
        lab.authorize("OOS",tmp_path/"missing.txt")
    path = tmp_path/"freeze.txt"
    path.write_text("NOT FROZEN")
    with pytest.raises(RuntimeError,match="freeze"):
        lab.authorize("OOS",path)
    path.write_text(json.dumps({"status":"FROZEN","finalists":["A"],"code_sha256":{}}))
    with pytest.raises(RuntimeError,match="changed"):
        lab.authorize("OOS",path)


def test_research_closed_after_oos_start(tmp_path,monkeypatch):
    monkeypatch.setattr(lab,"ROOT",tmp_path)
    (tmp_path/"oos_started.json").write_text("{}")
    with pytest.raises(RuntimeError,match="closed"):
        lab.authorize("IS")


@pytest.mark.parametrize("vols",[[1]*8,[.01,.1,.2,.3,.4,.5,.6,9],[None]*8,[0,None,math.inf,1,2,3,4,5]])
def test_bounded_inverse_vol_budget_and_bounds(vols):
    vals = lab.bounded_inverse_vol(vols)
    assert sum(vals) == pytest.approx(32000)
    assert all(2000 <= v <= 6000 for v in vals)
    assert lab.bounded_inverse_vol([1]*8) == pytest.approx([4000]*8)


def cp(price,day=1,fill=None):
    return {"checkpoint":price,"next_open":price if fill is None else fill,
            "next_ts":f"2026-01-{day:02d}T15:56:00-05:00"}


def test_protection_must_mature_arm_and_rebound_later():
    # Early windfall cannot arm before day 3; rebound is not same checkpoint.
    assert lab.protection_exit(100,10,[(1,cp(70)),(2,cp(85)),(3,cp(90))]) is None
    got = lab.protection_exit(100,10,[(3,cp(80,3)),(4,cp(70,4)),(5,cp(80,5,81))])
    assert got == ("2026-01-05T15:56:00-05:00",81,5)


def test_protection_missing_print_and_atr_do_not_fabricate_fill():
    rec = cp(90,4)
    rec["next_ts"] = None
    assert lab.protection_exit(100,10,[(3,cp(80,3)),(4,rec)]) is None
    assert lab.protection_exit(100,None,[(3,cp(80,3)),(4,cp(90,4))]) is None


def test_same_bar_execution_rejected():
    rec = cp(90,4)
    rec["next_ts"] = "2026-01-04T15:55:00-05:00"
    with pytest.raises(RuntimeError,match="follow"):
        lab.protection_exit(100,10,[(3,cp(80,3)),(4,rec)])


def test_history_requires_consecutive_observations():
    good = {"close":10,"open":10,"high":11,"low":9,"volume":100}
    assert lab.history_features([good]*20)["vol20"] is None
    assert lab.history_features([good]*10+[None]+[good]*10)["atr20"] is None
    assert lab.history_features([good]*21)["atr20"] == 2


def test_partial_exit_preserves_pnl_costs_and_ticket_count(monkeypatch):
    days = [date(2026,1,29),date(2026,1,30),date(2026,2,2)]
    monkeypatch.setattr(lab,"SCORE",days)
    t = {"signal":days[0],"fill_date":days[0],"exit_date":days[-1],"symbol":"TEST",
         "ticket_id":"one","entry_px":100,"exit_px":80,"shares":10,
         "entry_ts":datetime(2026,1,29,15,59),"exit_ts":datetime(2026,2,2,15,59),
         "pnl":signed_pnl(-1,10,100,80)}
    legs = [lab.leg(t,5,datetime(2026,1,30,15,56),90),lab.leg(t,5,t["exit_ts"],80)]
    summaries = {(d.isoformat(),"TEST"):{"close":p} for d,p in zip(days,[100,90,80])}
    m = lab.metrics(legs,summaries,"IS",1000,{})
    assert m["trades"] == 1 and m["exit_legs"] == 2
    assert m["gross"] == [1000,450,0]
    assert sum(m["daily"]) == pytest.approx(sum(t["pnl"] for t in legs))
    assert m["total_pnl"] == m["months"]["2026-01"]
    assert m["sessions"] == 2  # lifecycle Monday is even month, still fully marked
    assert m["borrow_sensitivity"]["0.1"] == pytest.approx(m["total_pnl"]-.1*(1000+450*3)/365)


def test_summary_matches_inherited_last_print(tmp_path):
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    ts = [datetime(2026,1,2,15,m,tzinfo=et) for m in (55,56,58,59)]
    df = pl.DataFrame({"bar_start":ts,"open":[10.,11.,12.,13.],"high":[11.]*4,
                       "low":[9.]*4,"close":[10.5,11.5,12.5,13.5],"volume":[100,100,100,0]})
    path = tmp_path/"bars.parquet"
    df.write_parquet(path)
    s = lab.tape_summary(path,date(2026,1,2))
    assert s["close"] == last_rth(df,date(2026,1,2))["close"]
    assert s["checkpoint"] == 10.5
    assert s["next_open"] == 11


def test_symbol_cap_cash_and_substitution(monkeypatch):
    # Three overlapping artificial batches isolate the cap mechanics from weekdays.
    days = lab.FEATS[25:28]
    monkeypatch.setattr(lab,"signal_dates",lambda *a,**k:days)
    monkeypatch.setattr(lab,"assert_signals",lambda *a:None)
    ranks = {d.isoformat():{"rows":[{"symbol":str(j),"prior_close":20,"prior_dv":20e6,
                "raw_return":1-j*.01} for j in range(16)]} for d in days}
    summaries = {(d.isoformat(),str(j)):{"close":20,"ts":d.isoformat()+"T15:59:00-04:00"}
                 for d in lab.FEATS[25:40] for j in range(16)}
    cash, cash_trades = lab.score(lab.Spec("cash",cap=8000),"IS",ranks,summaries)
    sub, sub_trades = lab.score(lab.Spec("sub",cap=8000,substitute=True),"IS",ranks,summaries)
    assert cash["trades"] == 16
    assert sub["trades"] == 24
    assert {t["symbol"] for t in sub_trades if t["signal"] == days[-1]} == {str(j) for j in range(8,16)}
    for ds in lab.FEATS:
        for symbol in {t["symbol"] for t in sub_trades}:
            exposure = sum(t["entry_px"]*t["shares"] for t in sub_trades
                           if t["symbol"] == symbol and t["fill_date"] <= ds < t["exit_date"])
            assert exposure <= 8000


def test_daily_budget_uses_full_mixed_week(monkeypatch):
    days = [date(2026,3,30),date(2026,3,31)]  # April days deliberately not IS signals
    monkeypatch.setattr(lab,"signal_dates",lambda *a,**k:days)
    ranks = {d.isoformat():{"rows":[{"symbol":str(j),"prior_close":20,"prior_dv":20e6,
                "raw_return":1-j*.01} for j in range(16)]} for d in days}
    summaries = {(d.isoformat(),str(j)):{"close":20,"ts":d.isoformat()+"T15:59:00-04:00"}
                 for d in lab.FEATS for j in range(8)}
    m,trades = lab.score(lab.Spec("daily",schedule="daily"),"IS",ranks,summaries)
    week_days = [d for d in lab.FEATS if d.isocalendar()[:2] == days[0].isocalendar()[:2]]
    assert m["intended_notional"] == pytest.approx(32000*2/len(week_days))
    assert all(t["ticket"] == pytest.approx(32000/len(week_days)/8) for t in trades)


def test_correlation_cluster_budget_is_transitive_and_neutral_for_missing():
    a = [float(i%3) for i in range(20)]
    b = [x*2 for x in a]
    c = [x*3 for x in a]
    out = lab.correlation_caps([a,b,c,[],[]],[4000]*5)
    assert out[:3] == pytest.approx([8000/3]*3)
    assert out[3:] == [4000,4000]


def test_minute_exit_arms_before_later_rebound_and_uses_next_open():
    rows = [
        {"hold_day":3,"decision":"2026-01-07T09:30:00-05:00","price":80,
         "execution":"2026-01-07T09:31:00-05:00","fill":79},
        {"hold_day":3,"decision":"2026-01-07T09:31:00-05:00","price":70,
         "execution":"2026-01-07T09:32:00-05:00","fill":71},
        {"hold_day":3,"decision":"2026-01-07T09:32:00-05:00","price":80,
         "execution":"2026-01-07T09:33:00-05:00","fill":83}]
    assert lab.all_minute_exit(100,10,rows) == ("2026-01-07T09:33:00-05:00",83,3)
    rows[-1]["execution"] = rows[-1]["decision"]
    with pytest.raises(RuntimeError,match="precede"):
        lab.all_minute_exit(100,10,rows)


def test_incomplete_long_history_does_not_erase_short_feature():
    good = {"close":10,"open":10,"high":11,"low":9,"volume":100}
    h = lab.history_features([None]*17+[good]*4)
    assert h["vol20"] is None and h["volume_ratio"] is None
    assert h["ret3"] == 0 and h["close_location"] == .5


def test_missing_future_exit_does_not_release_cap_early(monkeypatch):
    days = lab.FEATS[25:28]
    monkeypatch.setattr(lab,"signal_dates",lambda *a,**k:days)
    monkeypatch.setattr(lab,"assert_signals",lambda *a:None)
    ranks = {d.isoformat():{"rows":[{"symbol":str(j),"prior_close":20,"prior_dv":20e6,
                "raw_return":1-j*.01} for j in range(16)]} for d in days}
    summaries = {(d.isoformat(),str(j)):{"close":20,"ts":d.isoformat()+"T15:59:00-04:00"}
                 for d in lab.FEATS[25:40] for j in range(16)}
    # Future missing H10 close of first ticket must not make room on third signal.
    summaries[(lab.FEATS[36].isoformat(),"0")] = None
    m,trades = lab.score(lab.Spec("cash",cap=8000),"IS",ranks,summaries)
    assert m["trades"] == 15
    assert not any(t["signal"] == days[-1] for t in trades)


def test_future_exit_price_does_not_affect_feature_sizing(monkeypatch):
    days = [date(2026,3,4)]
    monkeypatch.setattr(lab,"signal_dates",lambda *a,**k:days)
    ranks = {days[0].isoformat():{"rows":[{"symbol":str(j),"prior_close":20,"prior_dv":20e6,
                "raw_return":1-j*.01,"now":[days[0].isoformat()+"T15:59:00-05:00",20]}
                for j in range(16)]}}
    summaries = {(d.isoformat(),str(j)):{"close":20,"open":20,"high":21,"low":19,"volume":100,
                 "ts":d.isoformat()+"T15:59:00-05:00"} for d in lab.FEATS for j in range(8)}
    spec = lab.Spec("causal",feature_rule="ret3",feature_cut=0,feature_direction="low")
    _,first = lab.score(spec,"IS",ranks,summaries)
    end = lab.FEATS[lab.INDEX[days[0]]+11]
    for j in range(8):
        summaries[(end.isoformat(),str(j))]["close"] = 200
    _,second = lab.score(spec,"IS",ranks,summaries)
    assert [t["shares"] for t in first] == [t["shares"] for t in second]
    assert [t["ticket"] for t in first] == [t["ticket"] for t in second]


def test_risk_adjusted_ranking_has_no_top_field_cap():
    rows = [{"symbol":str(i),"raw_return":100-i} for i in range(80)]
    fs = {str(i):{"vol20":100 if i < 72 else 1} for i in range(80)}
    selected = lab.risk_adjusted_selection(rows,fs)
    assert {h["symbol"] for h in selected} == {str(i) for i in range(72,80)}
    fs = {str(i):{"vol20":None} for i in range(80)}
    assert lab.risk_adjusted_selection(rows,fs) == []


def test_oos_requires_one_active_pass_and_blocks_repeat(tmp_path,monkeypatch):
    from dataclasses import asdict
    monkeypatch.setattr(lab,"ROOT",tmp_path)
    monkeypatch.setattr(lab,"authorize",lambda mode:{"controls":[asdict(lab.PARENT)],"finalists":[]})
    with pytest.raises(RuntimeError,match="single active"):
        lab.score(lab.PARENT,"OOS",{}, {})
    (tmp_path/"oos_started.json").write_text("{}")
    (tmp_path/"results").mkdir()
    (tmp_path/"results/PARENT_OOS.json").write_text("{}")
    with pytest.raises(RuntimeError,match="already scored"):
        lab.score(lab.PARENT,"OOS",{}, {})


def test_oos_unknown_finalist_is_blocked(tmp_path,monkeypatch):
    from dataclasses import asdict
    monkeypatch.setattr(lab,"ROOT",tmp_path)
    monkeypatch.setattr(lab,"authorize",lambda mode:{"controls":[asdict(lab.PARENT)],"finalists":[]})
    with pytest.raises(RuntimeError,match="not in frozen"):
        lab.score(lab.Spec("AFTER_THE_FACT"),"OOS",{}, {})


@pytest.mark.parametrize("kwargs",[
    {"id":"../escape"},{"id":"BAD","selection_rule":"typo"},
    {"id":"BAD","feature_rule":"ret3"},{"id":"BAD","rank_pool":0},
    {"id":"BAD","ticket":float("inf")},{"id":"BAD","portfolio_rule":"typo"}])
def test_invalid_spec_cannot_silently_score_a_different_rule(kwargs):
    with pytest.raises(ValueError):
        lab.Spec(**kwargs)


def test_inventory_state_includes_future_missing_backstop_positions(monkeypatch):
    days = lab.FEATS[25:28]
    monkeypatch.setattr(lab,"signal_dates",lambda *a,**k:days)
    monkeypatch.setattr(lab,"assert_signals",lambda *a:None)
    ranks = {d.isoformat():{"rows":[{"symbol":str(j),"prior_close":20,"prior_dv":20e6,
                "raw_return":1-j*.01} for j in range(16)]} for d in days}
    summaries = {(d.isoformat(),str(j)):{"close":20,"ts":d.isoformat()+"T15:59:00-04:00"}
                 for d in lab.FEATS[25:40] for j in range(16)}
    for j in range(8):
        summaries[(days[-1].isoformat(),str(j))]["close"] = 30
    spec = lab.Spec("inventory",portfolio_rule="underwater_inventory")
    _,first = lab.score(spec,"IS",ranks,summaries)
    for j in range(8):
        summaries[(lab.FEATS[36].isoformat(),str(j))] = None
    _,second = lab.score(spec,"IS",ranks,summaries)
    assert [t["ticket"] for t in first if t["signal"] == days[-1]] == [2000]*8
    assert [t["ticket"] for t in second if t["signal"] == days[-1]] == [2000]*8


def test_freeze_closes_research_even_before_oos(tmp_path,monkeypatch):
    monkeypatch.setattr(lab,"ROOT",tmp_path)
    path = tmp_path/"freeze.txt"
    path.write_text(json.dumps({"status":"FROZEN"}))
    with pytest.raises(RuntimeError,match="finalists are frozen"):
        lab.authorize("IS",path)


def test_bar_close_not_available_partway_through_minute():
    rec = cp(90,4)
    rec["next_ts"] = "2026-01-04T15:55:30-05:00"
    with pytest.raises(RuntimeError,match="follow"):
        lab.protection_exit(100,10,[(3,cp(80,3)),(4,rec)])


def test_confirmation_end_to_end_single_pass_on_synthetic_tape(tmp_path,monkeypatch):
    from dataclasses import asdict
    root = tmp_path/"cache"
    root.mkdir()
    freeze = tmp_path/"freeze.txt"
    monkeypatch.setattr(lab,"ROOT",root)
    monkeypatch.setattr(lab,"FREEZE",freeze)
    monkeypatch.setattr(lab,"code_identity",lambda:{"synthetic":"identity"})
    original_authorize = lab.authorize
    monkeypatch.setattr(lab,"authorize",lambda mode:original_authorize(mode,freeze))
    candidate = lab.Spec("FIXTURE_ONLY",ticket=3000)
    lab.dump(freeze,{"status":"FROZEN","code_sha256":{"synthetic":"identity"},
                    "controls":[asdict(lab.PARENT)],"finalists":[{"spec":asdict(candidate)}]})
    signal = date(2026,2,4)
    end = lab.FEATS[lab.INDEX[signal]+11]
    sessions = lab.FEATS[lab.INDEX[signal]:lab.INDEX[end]+1]
    monkeypatch.setattr(lab,"SCORE",sessions)
    monkeypatch.setattr(lab,"signal_dates",lambda *a,**k:[signal])
    ranks = {signal.isoformat():{"rows":[{"symbol":str(j),"prior_close":20,"prior_dv":20e6,
                                         "raw_return":1-j*.01} for j in range(16)]}}
    summaries = {(d.isoformat(),str(j)):{"close":18 if d == end else 20,
                  "ts":d.isoformat()+"T15:59:00-05:00"} for d in sessions for j in range(8)}
    monkeypatch.setattr(lab,"data_for_specs",lambda *a,**k:({"wed":ranks},summaries))
    lab.confirmation(workers=1)
    assert lab.read(root/"oos_complete.json")["books"] == ["PARENT","FIXTURE_ONLY"]
    assert lab.read(root/"results/PARENT_OOS.json")["metrics"]["trades"] == 8
    assert lab.read(root/"results/FIXTURE_ONLY_OOS.json")["metrics"]["trades"] == 8
    with pytest.raises(RuntimeError,match="rerun forbidden"):
        lab.confirmation(workers=1)
