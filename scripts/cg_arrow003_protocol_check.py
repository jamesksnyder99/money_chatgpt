"""Audit IS predeclarations, completed jobs, split seal and preserved evidence."""
from collections import Counter,defaultdict
from dataclasses import asdict
import json

from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump,digest,stamp
from research.cg_arrow003_lab import Spec,authorize,MATERIALITY,LEDGER,ledger


def main():
    authorize("IS")
    events=[json.loads(line) for line in LEDGER.read_text(encoding="utf-8").splitlines()]
    declarations={}
    completions={}
    completed_events=0
    for event in events:
        if event["event"]=="PREDECLARE":
            spec=Spec(**event["spec"])
            if event["materiality"]!=MATERIALITY:raise AssertionError("Materiality guides changed after declaration")
            declarations[spec.id]=event
        elif event["event"]=="COMPLETE":
            name=event["id"]
            if name not in declarations:raise AssertionError("Result without prior declaration")
            if declarations[name]["elapsed_seconds"]>event["elapsed_seconds"]:raise AssertionError("Declaration after outcome")
            completions[name]=event
            completed_events+=1
    records={p.stem[:-3]:read(p) for p in (ROOT/"results").glob("*_IS.json")}
    if set(records)!=set(declarations) or set(records)!=set(completions):
        raise AssertionError("Every declared policy must have a completed result")
    fingerprints=defaultdict(list)
    origins=Counter()
    for name,r in records.items():
        if asdict(Spec(**declarations[name]["spec"]))!=asdict(Spec(**r["spec"])):
            raise AssertionError("A policy id changed its declared economic rule")
        if r["metrics"]!=completions[name]["metrics"]:raise AssertionError("Stored result differs from completed ledger event")
        if digest(REPO_ROOT/r["detail_path"])!=r["detail_sha256"]:raise AssertionError("Saved detail identity changed")
        origins[r["spec"]["origin"]]+=1
        if r["spec"]["origin"]!="CONTROL":
            spec=asdict(Spec(**r["spec"]))
            for key in ("id","origin","mechanism","control"):spec.pop(key)
            fingerprints[json.dumps(spec,sort_keys=True)].append(name)
    duplicates=[names for names in fingerprints.values() if len(names)>1]
    if duplicates:raise AssertionError("Duplicate economic policies inflated the hypothesis count")
    for rel,sha in read(REPO_ROOT/"reports/cg_arrow003_legacy_identity.json").items():
        if digest(REPO_ROOT/rel)!=sha:raise AssertionError("Frozen historical evidence changed")
    state=read(ROOT/"state.json")
    if state["oos_exposed"] or (ROOT/"oos_started.json").exists() or list((ROOT/"results").glob("*_OOS.json")):
        raise AssertionError("New confirmation has already been exposed")
    if state.get("completed_is")!=sorted(records):raise AssertionError("Checkpoint completion list is stale")
    payload={"timestamp":stamp(),"status":"PASS","policy_results":len(records),"origins":dict(origins),
             "new_distinct_hypotheses":len(records)-origins["CONTROL"],"completed_events_including_replays":completed_events,
             "unclosed_performance_tests":[],"duplicate_new_policy_definitions":duplicates,
             "materiality_predeclared_unchanged":True,"latest_specs_match_declarations":True,
             "latest_metrics_match_completion_ledger":True,"all_detail_hashes_match":True,
             "legacy_evidence_unchanged":True,"new_oos_sealed":True,
             "interpretation":"Process integrity check, not financial validation or proof of complete input data"}
    dump(REPO_ROOT/"reports/cg_arrow003_protocol_check.json",payload)
    ledger({"event":"IS_PROTOCOL_CHECK_COMPLETE",**{k:v for k,v in payload.items() if k!="timestamp"}})
    print(json.dumps(payload,indent=2))


if __name__=="__main__":main()
