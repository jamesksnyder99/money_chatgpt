"""Hash only the lab inputs actually used, with no source-repository access."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor,as_completed
from datetime import date
import hashlib
import json
import time as timer

from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump,digest,safe_path,stamp,session_bar_path
from research.cg_arrow003_lab import authorize,ledger,elapsed


def hash_chunk(paths):
    out={}
    for rel in paths:
        p=safe_path(REPO_ROOT/rel)
        st=p.stat()
        if st.st_nlink!=1:
            raise RuntimeError("Input is not an independent single-link lab file")
        out[rel]={"sha256":digest(p),"bytes":st.st_size,"mtime_ns":st.st_mtime_ns}
    return out


def run(workers=8,mode="IS"):
    authorize(mode)
    sources=set()
    totals={"summary_records":0,"missing_summary_records":0,"alternate_tape_records":0}
    cache_hashes={}
    for p in sorted((ROOT/"summaries").glob("*.json")):
        cache_hashes[p.relative_to(REPO_ROOT).as_posix()]=digest(p)
        for sym,rec in read(p).items():
            totals["summary_records"]+=1
            if rec is None:
                totals["missing_summary_records"]+=1
            elif rec.get("source"):
                sources.add(rec["source"])
                canonical=session_bar_path(date.fromisoformat(p.stem),sym).relative_to(REPO_ROOT).as_posix()
                totals["alternate_tape_records"]+=rec["source"]!=canonical
    paths=sorted(sources)
    chunks=[paths[i::workers] for i in range(workers)]
    start=timer.monotonic()
    manifest={}
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs=[pool.submit(hash_chunk,c) for c in chunks]
        for n,f in enumerate(as_completed(fs),1):
            manifest.update(f.result())
            print(f"{stamp()} used-source hashes {n}/{len(fs)}; files={len(manifest)}/{len(paths)} "
                  f"ETA~{(timer.monotonic()-start)/n*(len(fs)-n):.1f}s",flush=True)
    identity=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    p=ROOT/f"source_manifest_{mode}.json"
    dump(p,{"timestamp":stamp(),"files":manifest,"cache_sha256":cache_hashes})
    public={"timestamp":stamp(),"mode":mode,"files":len(manifest),
        "bytes":sum(x["bytes"] for x in manifest.values()),"source_identity_sha256":identity,
        "local_manifest_path":p.relative_to(REPO_ROOT).as_posix(),"local_manifest_sha256":digest(p),
        "raw_inputs_modified":False,"linked_inputs":0,"source_roots":sorted({"/".join(x.split('/')[:3]) for x in paths}),
        "summary_coverage":totals,"wall_seconds":timer.monotonic()-start,"elapsed_minutes":elapsed()/60,
        "note":"Targeted source hashing for cached research inputs; no broad filesystem inventory, no raw vendor payload published"}
    dump(REPO_ROOT/"reports"/f"cg_arrow003_provenance_{mode.lower()}.json",public)
    ledger({"event":"INPUT_PROVENANCE_CHECKPOINT","result":public})
    print(json.dumps(public,indent=2))


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--workers",type=int,default=8)
    p.add_argument("--mode",choices=["IS","ALL"],default="IS")
    args=p.parse_args()
    run(args.workers,args.mode)
