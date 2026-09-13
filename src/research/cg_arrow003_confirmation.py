"""Freeze, identical-job confirmation recovery, and chronological investor replay."""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from dataclasses import asdict
import hashlib
import json
import subprocess
import time as timer

from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump,digest,stamp,data_for,CONVENTION,SCHEMA
from research.cg_arrow003_lab import (
    FREEZE,Spec,authorize,code_identity,input_identity,elapsed,ledger,SCENARIOS,MATERIALITY,score_job,
)


def cache_identity():
    paths=list((ROOT/"summaries").glob("*.json"))+list((ROOT/"minute_paths").glob("*/*.json"))
    return {p.relative_to(REPO_ROOT).as_posix():digest(p) for p in sorted(paths)}


def freeze(selection):
    authorize("IS")
    if elapsed()<135*60:
        raise RuntimeError("Keep IS falsification open until at least minute 135")
    if not 1<=len(selection["finalists"])<=5:
        raise ValueError("Freeze requires one to five distinct finalists")
    finalists=selection["finalists"]
    finalist_ids=[x["id"] for x in finalists]
    if len(set(finalist_ids))!=len(finalist_ids):
        raise ValueError("Finalists must be distinct")
    if set(finalist_ids)&set(selection["controls"]):
        raise ValueError("New finalists cannot be counted as controls")
    names=list(dict.fromkeys(selection["controls"]+[x["id"] for x in finalists]))
    records={name:read(ROOT/"results"/(name+"_IS.json")) for name in names}
    for name,r in records.items():
        if r["code_sha256"]!=code_identity():
            raise RuntimeError(f"Exact current-code IS replay required for {name}")
        if digest(REPO_ROOT/r["detail_path"])!=r["detail_sha256"]:
            raise RuntimeError(f"IS details changed for {name}")
        if name in selection["controls"] and r["spec"]["origin"]!="CONTROL":
            raise ValueError("Only declared comparison controls may be frozen as controls")
        if name in selection["controls"]:
            s=Spec(**r["spec"])
            if s.family not in {"PARENT","R4","R5"} or s.volume!="mean" or s.momentum!="switch" or s.pacing or s.cover!="none" or s.state!="none" or s.shuffle_seed is not None:
                raise ValueError("Control slots are reserved for the original rules and fixed sizing/share-clock comparisons")
    def policy_fingerprint(record):
        s=asdict(Spec(**record["spec"]))
        for k in ("id","origin","mechanism","control"):s.pop(k)
        return json.dumps(s,sort_keys=True)
    controls={policy_fingerprint(records[n]) for n in selection["controls"]}
    seen=set()
    for name in finalist_ids:
        fingerprint=policy_fingerprint(records[name])
        if fingerprint in seen or fingerprint in controls:
            raise ValueError("Finalist policies must differ economically from controls and each other")
        seen.add(fingerprint)
    for row in finalists:
        if not all(row.get(k) for k in ("priority","primary_improvement","acceptable_tradeoff","control","reason")):
            raise ValueError("Finalist must specify primary improvement, comparator and acceptable tradeoff")
        if row["control"] not in selection["controls"]:
            raise ValueError("The same primary comparator must be included in the freeze")
    proof_path=REPO_ROOT/"reports/cg_arrow003_exact_replay.json"
    if not proof_path.exists():raise RuntimeError("Verified exact IS replay required before freeze")
    proof=read(proof_path)
    if proof["code_sha256"]!=code_identity() or proof.get("input_sha256")!=input_identity() or proof["mismatches"] or any(n not in proof["archives"] for n in names):
        raise RuntimeError("Exact IS replay proof does not cover this current freeze")
    manifest={"status":"FROZEN","timestamp":stamp(),"elapsed_minutes":elapsed()/60,
        "start":read(ROOT/"state.json")["start_utc"],"deadline":read(ROOT/"state.json")["deadline_utc"],
        "signal_rule":"Inherited full point-in-time common-stock field; Wednesday top8 15-session return after documented as-of action repair",
        "entry_rule":"Next session scheduled final RTH minute close; no earlier fallback; integer shares (preorder size under pacing)",
        "exit_rule":"H10 scheduled final minute; missing backstop stays reserved until first later eligible RTH open; terminal inventory marked, not filled",
        "holding_age_definition":"Entry session is age0; H10 is fill-session-index+10. Cover eligibility begins at min_hold; cover_on_backstop=false ends eligibility at age9, true also permits age10 before the final-minute backstop. One floor(initial shares/2) cover; no zero-share fill.",
        "split_rule":"Odd signal months train; even signal months reused internal confirmation; full lifecycles cross months",
        "finalists":finalists,"controls":selection["controls"],"specs":[r["spec"] for r in records.values()],
        "is_metrics":{name:r["metrics"] for name,r in records.items()},
        "size_matches":selection.get("size_matches",{}),"code_sha256":code_identity(),
        "dependency_identity_version":1,"input_sha256":input_identity(),"cache_sha256_at_freeze":cache_identity(),
        "data_convention":CONVENTION,"raw_summary_schema":SCHEMA,"scenarios":SCENARIOS,
        "materiality":MATERIALITY,"confirmation_exposed":False,
        "pre_reveal_commitment":"Commit this manifest and dependencies before one new OOS batch; no adaptive tuning after reveal",
        "known_confirmation_history":"All even months have been inspected in prior arrows; not pristine external validation",
        "open_data_limitations":"Partial split coverage, stale inventory, unknown dividends/loans/financing/cash-in-lieu"}
    dump(FREEZE,manifest)
    ledger({"event":"FREEZE_WRITTEN","manifest_sha256":digest(FREEZE),"finalist_ids":[x["id"] for x in finalists],
            "confirmation_exposed":False,"commit_still_required":True})
    print(f"Frozen {len(finalists)} finalists and {len(selection['controls'])} controls. Commit required before confirmation.")


def batch(mode,workers=8):
    manifest=authorize(mode)
    freeze_sha=digest(FREEZE)
    marker=ROOT/("oos_started.json" if mode=="OOS" else "investor_started.json")
    done=ROOT/("oos_complete.json" if mode=="OOS" else "investor_complete.json")
    if done.exists():
        if read(done)["freeze_sha256"]!=freeze_sha:raise RuntimeError("Completed job identity mismatch")
        print("Identical frozen job already complete; no rescore")
        return
    resumed=marker.exists()
    if resumed:
        if read(marker)["freeze_sha256"]!=freeze_sha:raise RuntimeError("Interrupted job cannot resume a different freeze")
    else:
        if mode=="OOS":
            # First verify every existing pre-freeze summary partition. New OOS
            # symbol records may subsequently extend a partition, with provenance.
            for path,expected in manifest["cache_sha256_at_freeze"].items():
                if digest(REPO_ROOT/path)!=expected:raise RuntimeError("Pre-reveal cache changed")
        dump(marker,{"timestamp":stamp(),"freeze_sha256":freeze_sha,"mode":mode,
                     "elapsed_minutes":elapsed()/60,"commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=REPO_ROOT).strip()})
    state=read(ROOT/"state.json")
    state["oos_exposed"]=True
    state["frozen_sha256"]=freeze_sha
    dump(ROOT/"state.json",state)
    ledger({"event":"CONFIRMATION_START" if mode=="OOS" else "INVESTOR_START", "mode":mode,
            "freeze_sha256":freeze_sha,"resumed_identical_job":resumed})
    start=timer.monotonic()
    ranks,summaries=data_for(mode,workers,need_minutes=any(s.get("cover_clock")=="all_minutes" for s in manifest["specs"]))
    completed=[]
    pending=[]
    for raw in manifest["specs"]:
        p=ROOT/"results"/(raw["id"]+f"_{mode}.json")
        if p.exists():
            r=read(p)
            if r["spec"]!=raw or r["code_sha256"]!=manifest["code_sha256"]:
                raise RuntimeError("Completed partial output has wrong identity")
            if digest(REPO_ROOT/r["detail_path"])!=r["detail_sha256"]:
                raise RuntimeError("Completed partial output details changed")
            completed.append(raw["id"])
        else:pending.append(raw)
    if pending:
        with ProcessPoolExecutor(max_workers=min(workers,len(pending),8)) as pool:
            fs=[pool.submit(score_job,(raw,mode,ranks,summaries)) for raw in pending]
            for f in as_completed(fs):
                r=f.result()
                completed.append(r["spec"]["id"])
                m=r["metrics"]
                ledger({"event":"FROZEN_BOOK_COMPLETE","mode":mode,"id":r["spec"]["id"],
                        "metrics":m,"detail_path":r["detail_path"],"detail_sha256":r["detail_sha256"]})
                spent=timer.monotonic()-start
                print(f"{stamp()} {mode} {len(completed)}/{len(manifest['specs'])} {r['spec']['id']}: "
                      f"PnL={m['total_pnl']:.2f} day={m['per_day']:.2f} DD={m['max_dd']:.2f} "
                      f"peak={m['peak_exposure']:.2f} ETA~{spent/max(1,len(completed))*(len(manifest['specs'])-len(completed)):.1f}s",flush=True)
    dump(done,{"timestamp":stamp(),"mode":mode,"freeze_sha256":freeze_sha,"ids":completed,
               "wall_seconds":timer.monotonic()-start,"elapsed_minutes":elapsed()/60,
               "resumed_identical_job":resumed,"cache_sha256_after":cache_identity()})
    ledger({"event":"CONFIRMATION_COMPLETE" if mode=="OOS" else "INVESTOR_COMPLETE",
            "mode":mode,"book_count":len(completed),"wall_seconds":timer.monotonic()-start})
    state=read(ROOT/"state.json")
    state["completed_"+mode.lower()]=completed
    state["elapsed_checkpoint_seconds"]=elapsed()
    dump(ROOT/"state.json",state)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["freeze","confirmation","investor"])
    p.add_argument("--selection")
    p.add_argument("--workers",type=int,default=8)
    a=p.parse_args()
    if a.command=="freeze":freeze(read(REPO_ROOT/a.selection))
    else:batch("OOS" if a.command=="confirmation" else "ALL",a.workers)


if __name__=="__main__":main()
