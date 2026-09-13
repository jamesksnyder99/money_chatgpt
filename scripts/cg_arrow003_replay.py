"""Final pre-freeze identity replay with lossless archives and equality checks."""
from collections import Counter
import math
import shutil

from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump,digest,stamp
from research.cg_arrow003_lab import Spec,run_is,authorize,ledger,code_identity


def compare(old,new,path="root",differences=None):
    differences=[] if differences is None else differences
    if isinstance(old,dict):
        if not isinstance(new,dict):differences.append(path+": type")
        else:
            for k,v in old.items():
                if k not in new:differences.append(path+"."+k+": removed")
                else:compare(v,new[k],path+"."+k,differences)
    elif isinstance(old,list):
        if not isinstance(new,list) or len(old)!=len(new):differences.append(path+": length/type")
        else:
            for i,(a,b) in enumerate(zip(old,new)):compare(a,b,f"{path}[{i}]",differences)
    elif isinstance(old,(int,float)) and not isinstance(old,bool):
        if not isinstance(new,(int,float)) or not math.isclose(old,new,rel_tol=0,abs_tol=1e-7):
            differences.append(path+": numeric change")
    elif old!=new:differences.append(path+": value change")
    return differences


def main():
    authorize("IS")
    paths=sorted((ROOT/"results").glob("*_IS.json"))
    before={p.stem[:-3]:read(p) for p in paths}
    archived={}
    for name,r in before.items():
        detail=REPO_ROOT/r["detail_path"]
        if digest(detail)!=r["detail_sha256"]:raise RuntimeError("Current local ledger identity mismatch")
        target=ROOT/"replay_archive"/(name+"_"+r["detail_sha256"][:16])
        target.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(detail,target/"details.json")
        shutil.copyfile(ROOT/"results"/(name+"_IS.json"),target/"result.json")
        archived[name]={"detail_path":(target/"details.json").relative_to(REPO_ROOT).as_posix(),
                        "detail_sha256":digest(target/"details.json"),
                        "result_sha256":digest(target/"result.json")}
    ledger({"event":"EXACT_IDENTITY_REPLAY_START","books":len(before),
            "reason":"Final current-code replay; preserve every prior metric and ledger value. New explanatory fields allowed; economic drift is an error requiring investigation before any freeze.",
            "code_sha256":code_identity()})
    run_is([Spec(**r["spec"]) for r in before.values()],workers=8,
           replay_reason="Exact current-code identity replay; lossless result/detail archive and recursive equality verification")
    mismatches={}
    for name,old in before.items():
        new=read(ROOT/"results"/(name+"_IS.json"))
        diff=compare(old["metrics"],new["metrics"],"metrics")
        old_detail=read(REPO_ROOT/archived[name]["detail_path"])
        diff+=compare(old_detail,read(REPO_ROOT/new["detail_path"]),"detail")
        if diff:mismatches[name]=diff
    payload={"timestamp":stamp(),"books":len(before),"origins":dict(Counter(r["spec"]["origin"] for r in before.values())),
             "tolerance_absolute":1e-7,"mismatches":mismatches,"archives":archived,
             "code_sha256":code_identity(),"interpretation":"Every prior metric, entry/cover/terminal field, daily row and feature value recursively preserved; new explanatory fields permitted. This is verification, not additional hypotheses."}
    dump(REPO_ROOT/"reports/cg_arrow003_exact_replay.json",payload)
    ledger({"event":"EXACT_IDENTITY_REPLAY_COMPLETE","books":len(before),"mismatch_books":len(mismatches),
            "result_file":"reports/cg_arrow003_exact_replay.json"})
    if mismatches:raise RuntimeError("Replay drift detected; review the archived before/after records")
    print(f"Exact identity replay: {len(before)} books, zero economic or existing-ledger differences")


if __name__=="__main__":main()
