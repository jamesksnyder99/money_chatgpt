from datetime import date, datetime

import pytest

import research.cg_arrow002_recycle as rc
from research.cg_arrow002_lab import FEATS, INDEX


def test_recycling_never_extends_original_slot():
    d = date(2026,1,7)
    end = FEATS[INDEX[d]+11]
    contexts = [{"source_signal":d,"decision_date":FEATS[INDEX[d]+5],"scheduled_end":end}]
    rc.validate_contexts(contexts,"IS")
    contexts[0]["scheduled_end"] = FEATS[INDEX[end]+1]
    with pytest.raises(RuntimeError,match="extend"):
        rc.validate_contexts(contexts,"IS")


def test_oos_root_is_rejected_before_replacement_universe_read(monkeypatch):
    d = date(2026,2,4)
    contexts = [{"source_signal":d,"decision_date":FEATS[INDEX[d]+5],"scheduled_end":FEATS[INDEX[d]+11]}]
    monkeypatch.setattr(rc,"_elig_year",lambda *a:pytest.fail("OOS root reached universe reader"))
    with pytest.raises(RuntimeError,match="forbidden"):
        rc.lifecycle_rankings(contexts,"IS",{})


def test_cross_month_is_lifecycle_is_not_new_even_root():
    source = date(2026,1,28)
    decision = date(2026,2,3)
    rc.validate_contexts([{"source_signal":source,"decision_date":decision,
                           "scheduled_end":FEATS[INDEX[source]+11]}],"IS")


def test_need_three_remaining_sessions_and_future_checkpoint():
    end = date(2026,1,16)
    assert rc.decision_session(datetime(2026,1,13,12,0),end) == date(2026,1,13)
    assert rc.decision_session(datetime(2026,1,13,15,56),end) is None
    assert rc.decision_session(datetime(2026,1,14,12,0),end) is None


def test_capacity_mark_does_not_see_current_last_close():
    d = date(2026,1,7)
    p = {"symbol":"X","entry_ts":datetime(2026,1,6,15,59),"entry_px":10}
    summary = {(d.isoformat(),"X"):{"checkpoint":11,"close":999}}
    assert rc.marked_at_checkpoint(p,d,summary) == 11


def test_checkpoint_timezone_tracks_daylight_saving_not_entry_offset():
    entry = datetime.fromisoformat("2026-03-05T15:59:00-05:00")
    decision = datetime.combine(date(2026,3,10),rc.time(15,56),tzinfo=rc.ET)
    fill = datetime.fromisoformat("2026-03-10T15:56:00-04:00")
    assert entry.utcoffset() != decision.utcoffset()
    assert decision == fill


def test_future_missing_backstop_cannot_change_shadow_exit_or_recycling_date():
    source = date(2026,1,7)
    fill = FEATS[INDEX[source]+1]
    end = FEATS[INDEX[source]+11]
    early_day = FEATS[INDEX[fill]+3]
    h = {"symbol":"X","prior_close":20,"prior_dv":20e6}
    ranks = {source.isoformat():{"rows":[h]}}
    summaries = {(d.isoformat(),"X"):{"close":20,"open":20,"high":21,"low":19,"volume":100,
                   "ts":d.isoformat()+"T15:59:00-05:00"}
                  for d in FEATS[INDEX[source]-20:INDEX[end]+1]}
    observations = [{"hold_day":3,"decision":early_day.isoformat()+f"T10:0{i}:00-05:00",
                     "price":px,"execution":early_day.isoformat()+f"T10:0{i+1}:00-05:00","fill":px+1}
                    for i,px in enumerate([16,14,16])]
    summaries[(source.isoformat(),"X","minute_path")] = observations
    completed = [{"ticket_id":f"{source}/X","exit_ts":datetime.fromisoformat(observations[-1]["execution"]),"exit_px":17}]
    first = rc.base_capacity_positions(ranks,summaries,completed)[0]
    summaries[(end.isoformat(),"X")] = None
    second = rc.base_capacity_positions(ranks,summaries,[])[0]
    assert first["exit_ts"] == second["exit_ts"]
    assert first["exit_px"] == second["exit_px"]
    assert first["economic_cohort"] and not second["economic_cohort"]
    assert rc.decision_session(first["exit_ts"],end) == rc.decision_session(second["exit_ts"],end)
