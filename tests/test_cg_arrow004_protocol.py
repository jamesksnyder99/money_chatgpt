from types import SimpleNamespace
import pytest
from research import cg_arrow004_lab as lab
from research import cg_arrow004_confirmation as conf
from research.cg_arrow004_data import dump,digest
from research.cg_arrow004_report import claim_test
from scripts.cg_arrow004_replay import compare

def test_claim_does_not_relabel_a_return_loss_as_balanced():
    c={'total_pnl':1000.,'max_dd':-1000.,'red_loss_sum':-500.,'worst_month':-400.,'worst_day':-200.}
    m={**c,'total_pnl':900.,'max_dd':-800.,'red_loss_sum':-400.}
    assert claim_test(m,c,'ride')['numeric_claim_pass']
    assert not claim_test(m,c,'balanced')['numeric_claim_pass']
    assert not claim_test(m,c,'return')['numeric_claim_pass']
    assert not claim_test({**m,'total_pnl':849.},c,'ride')['numeric_claim_pass']

def test_replay_detects_changed_nested_economic_values():
    assert compare({'positions':[{'quantity':100,'cost':1.}]},{'positions':[{'quantity':101,'cost':1.}]})==['/positions/0/quantity']
    assert compare({'pnl':1.},{'pnl':1.,'new_explanation':'allowed'})==[]

def test_original_signal_month_firewall():
    s=lab.Spec('F')
    with pytest.raises(RuntimeError,match='signal-month cohort firewall'):lab.score(s,'IS',{'2025-10-01':{}},{})
    with pytest.raises(RuntimeError,match='signal-month cohort firewall'):lab.score(s,'OOS',{'2025-09-03':{}},{})
    with pytest.raises(ValueError,match='Unknown score cohort'):lab.score(s,'bad',{}, {})

def test_no_early_confirmation_and_research_closes(monkeypatch,tmp_path):
    monkeypatch.setattr(lab,'ROOT',tmp_path);monkeypatch.setattr(lab,'FREEZE',tmp_path/'freeze.json');monkeypatch.setattr(lab,'elapsed',lambda:114*60)
    with pytest.raises(RuntimeError,match='minute115'):lab.authorize('OOS')
    dump(tmp_path/'oos_started.json',{'freeze_sha256':'abc'})
    with pytest.raises(RuntimeError,match='closed'):lab.authorize('IS')

def test_investor_cannot_use_other_completed_freeze(monkeypatch,tmp_path):
    f=tmp_path/'freeze.json';dump(f,{'code_sha256':{},'input_sha256':{},'dependency_identity':{}})
    monkeypatch.setattr(lab,'ROOT',tmp_path);monkeypatch.setattr(lab,'REPO_ROOT',tmp_path);monkeypatch.setattr(lab,'FREEZE',f)
    monkeypatch.setattr(lab,'elapsed',lambda:120*60);monkeypatch.setattr(lab,'code_identity',lambda:{});monkeypatch.setattr(lab,'input_identity',lambda:{})
    monkeypatch.setattr(lab,'dependency_identity',lambda:{})
    monkeypatch.setattr(lab.subprocess,'check_output',lambda *a,**k:f.read_bytes());monkeypatch.setattr(lab.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
    with pytest.raises(RuntimeError,match='follows confirmation'):lab.authorize('ALL')
    dump(tmp_path/'oos_complete.json',{'freeze_sha256':'different'})
    with pytest.raises(RuntimeError,match='identical completed'):lab.authorize('ALL')
    dump(tmp_path/'oos_complete.json',{'freeze_sha256':digest(f)})
    assert lab.authorize('ALL')['code_sha256']=={}

def test_completed_identical_confirmation_does_not_rescore(monkeypatch,tmp_path):
    f=tmp_path/'freeze.json';dump(f,{'specs':[]});dump(tmp_path/'oos_complete.json',{'freeze_sha256':digest(f)})
    monkeypatch.setattr(conf,'ROOT',tmp_path);monkeypatch.setattr(conf,'FREEZE',f);monkeypatch.setattr(conf,'authorize',lambda mode:{'specs':[]})
    def fail(*args,**kwargs):raise AssertionError('Completed books must not load or score again')
    monkeypatch.setattr(conf,'load_prepared',fail);monkeypatch.setattr(conf,'score_job',fail)
    conf.batch('OOS')
    dump(tmp_path/'oos_complete.json',{'freeze_sha256':'different'})
    with pytest.raises(RuntimeError,match='identity changed'):conf.batch('OOS')
