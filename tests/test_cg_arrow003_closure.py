"""Synthetic freeze, interruption recovery and shared report interpretation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import importlib.util
from pathlib import Path
import subprocess

import pytest

from research import cg_arrow003_data as data
from research import cg_arrow003_lab as lab
from research import cg_arrow003_confirmation as closure


def report_module():
    spec=importlib.util.spec_from_file_location("arrow003_report",data.REPO_ROOT/"scripts/cg_arrow003_report.py")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def synthetic_comparator():
    return {"total_pnl":1000.,"per_day":10.,"red_loss_sum":-100.,"worst_month":-100.,
            "max_dd":-100.,"worst_day":-100.,"red_months":2,"peak_exposure":100000.}


@pytest.mark.parametrize("kind",["balanced","ride","return"])
def test_reporting_uses_the_frozen_same_comparator(kind):
    report=report_module()
    c=synthetic_comparator()
    m={**c,"total_pnl":1200.,"per_day":12.,"red_loss_sum":-80.,"max_dd":-80.,"peak_exposure":134000.}
    priority={"control":"R4","primary_improvement":{"kind":kind},"acceptable_tradeoff":{}}
    assessment=report.repetition(m,m,c,c,priority)
    assert assessment["is_comparison"]==assessment["oos_comparison"]==lab.classify(m,c)
    assert assessment["assessment"]=="REPEATED"
    assert not assessment["gross_exposure_auto_failure"]


def test_balanced_confirmation_cannot_use_a_looser_profit_threshold():
    report=report_module()
    c=synthetic_comparator()
    m={**c,"total_pnl":1001.,"per_day":10.01,"red_loss_sum":-80.,"max_dd":-80.}
    p={"control":"R4","primary_improvement":{"kind":"balanced"},"acceptable_tradeoff":{}}
    a=report.repetition(m,m,c,c,p)
    assert a["oos_comparison"]["classification"]=="RIDE-FIRST"
    assert a["assessment"]=="PARTIALLY REPEATED"


def test_data_dependency_is_not_erased_by_positive_confirmation():
    report=report_module()
    c=synthetic_comparator()
    m={**c,"total_pnl":2000.,"per_day":20.}
    p={"control":"R5","primary_improvement":{"kind":"return"},"acceptable_tradeoff":{},"missingness_dependency":True}
    a=report.repetition(m,m,c,c,p)
    assert a["numeric_assessment"]=="REPEATED"
    assert a["assessment"]=="INCONCLUSIVE/DATA-LIMITED"


def configure_freeze(tmp_path,monkeypatch):
    monkeypatch.setattr(closure,"ROOT",tmp_path)
    monkeypatch.setattr(closure,"REPO_ROOT",tmp_path)
    monkeypatch.setattr(closure,"FREEZE",tmp_path/"freeze.json")
    monkeypatch.setattr(closure,"authorize",lambda mode:None)
    monkeypatch.setattr(closure,"elapsed",lambda:150*60)
    monkeypatch.setattr(closure,"code_identity",lambda:{"code.py":"fixed"})
    monkeypatch.setattr(closure,"input_identity",lambda:{"input":"fixed"})
    monkeypatch.setattr(closure,"ledger",lambda record:None)
    data.dump(tmp_path/"state.json",{"start_utc":"start","deadline_utc":"end"})
    for name,origin in (("R4","CONTROL"),("candidate","ASTRA")):
        detail=tmp_path/(name+".json")
        data.dump(detail,{"synthetic":True})
        data.dump(tmp_path/"results"/(name+"_IS.json"),{
            "spec":asdict(lab.Spec(name,origin=origin)),"metrics":synthetic_comparator(),
            "code_sha256":{"code.py":"fixed"},"detail_path":detail.name,"detail_sha256":data.digest(detail)})
    return {"controls":["R4"],"finalists":[{"id":"candidate","priority":1,"control":"R4",
            "primary_improvement":{"kind":"balanced"},"acceptable_tradeoff":{"monetary_downside_worsening":.05},"reason":"Synthetic fixture"}]}


def test_freeze_validates_distinctness_comparator_and_detail_identity(tmp_path,monkeypatch):
    selection=configure_freeze(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match="distinct"):
        closure.freeze({**selection,"finalists":selection["finalists"]*2})
    with pytest.raises(ValueError,match="comparator"):
        closure.freeze({**selection,"finalists":[{**selection["finalists"][0],"control":"absent"}]})
    data.dump(tmp_path/"candidate.json",{"modified":True})
    with pytest.raises(RuntimeError,match="details changed"):
        closure.freeze(selection)


def test_freeze_not_written_before_minimum_discovery_clock(tmp_path,monkeypatch):
    selection=configure_freeze(tmp_path,monkeypatch)
    monkeypatch.setattr(closure,"elapsed",lambda:134.9*60)
    with pytest.raises(RuntimeError,match="135"):
        closure.freeze(selection)
    assert not closure.FREEZE.exists()


def test_frozen_batch_recovers_identical_outputs_without_rescoring(tmp_path,monkeypatch):
    configure_freeze(tmp_path,monkeypatch)
    specs=[asdict(lab.Spec(n,origin="CONTROL")) for n in ("one","two")]
    manifest={"specs":specs,"code_sha256":{"code.py":"fixed"},"cache_sha256_at_freeze":{}}
    data.dump(closure.FREEZE,manifest)
    monkeypatch.setattr(closure,"authorize",lambda mode:manifest)
    monkeypatch.setattr(closure,"data_for",lambda *a,**kw:({},{}))
    monkeypatch.setattr(closure,"ProcessPoolExecutor",ThreadPoolExecutor)
    monkeypatch.setattr(closure.subprocess,"check_output",lambda *a,**kw:"synthetic-commit")
    called=[]
    fail={"enabled":True}
    def job(arg):
        spec,mode,_,_=arg
        called.append(spec["id"])
        if spec["id"]=="two" and fail["enabled"]:
            raise RuntimeError("synthetic infrastructure interruption")
        detail=tmp_path/(spec["id"]+"_detail.json")
        data.dump(detail,{"synthetic":True})
        record={"spec":spec,"code_sha256":manifest["code_sha256"],"metrics":{
            "total_pnl":1,"per_day":1,"max_dd":0,"peak_exposure":1},
            "detail_path":detail.name,"detail_sha256":data.digest(detail)}
        data.dump(tmp_path/"results"/(spec["id"]+"_OOS.json"),record)
        return record
    monkeypatch.setattr(closure,"score_job",job)
    with pytest.raises(RuntimeError,match="interruption"):
        closure.batch("OOS",workers=1)
    assert (tmp_path/"oos_started.json").exists()
    assert not (tmp_path/"oos_complete.json").exists()
    fail["enabled"]=False
    closure.batch("OOS",workers=1)
    assert called==["one","two","two"]
    assert data.read(tmp_path/"oos_complete.json")["resumed_identical_job"]
    closure.batch("OOS",workers=1)
    assert called==["one","two","two"]


def test_authorization_requires_committed_unchanged_code_and_freeze(tmp_path,monkeypatch):
    def git(*args):
        return subprocess.run(["git",*args],cwd=tmp_path,check=True,capture_output=True,text=True)
    git("init","--quiet")
    git("config","user.name","Synthetic test")
    git("config","user.email","synthetic@example.invalid")
    path=tmp_path/"code.py"
    path.write_text("value=1\n",encoding="utf-8")
    frozen=tmp_path/"freeze.json"
    identity={"code.py":data.digest(path)}
    data.dump(frozen,{"status":"FROZEN","code_sha256":identity,"input_sha256":{}})
    monkeypatch.setattr(lab,"ROOT",tmp_path)
    monkeypatch.setattr(lab,"REPO_ROOT",tmp_path)
    monkeypatch.setattr(lab,"FREEZE",frozen)
    monkeypatch.setattr(lab,"elapsed",lambda:150*60)
    monkeypatch.setattr(lab,"code_identity",lambda:{"code.py":data.digest(path)})
    monkeypatch.setattr(lab,"input_identity",lambda:{})
    with pytest.raises(RuntimeError,match="committed"):
        lab.authorize("OOS")
    git("add","--","code.py","freeze.json")
    git("-c","core.autocrlf=false","commit","--quiet","-m","Synthetic frozen fixture")
    assert lab.authorize("OOS")["status"]=="FROZEN"
    with pytest.raises(RuntimeError,match="follows"):
        lab.authorize("ALL")
    path.write_text("value=2\n",encoding="utf-8")
    with pytest.raises(RuntimeError,match="identity changed"):
        lab.authorize("OOS")
