"""Finish the already-tested practical capital policy on promising overlays."""
from dataclasses import asdict,replace
from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump
from research.cg_arrow003_lab import Spec,run_is,ledger


def main():
    pairs=[("AR2_R5_LATE_WEAK_PART_COVER","AR9_R5_LATE_COVER_PACED"),
           ("AR3_R4_LATE_COVER_CONSERVATIVE","AR10_R4_CONSERVATIVE_COVER_PACED")]
    specs=[]
    for old,new in pairs:
        s=Spec(**read(ROOT/"results"/(old+"_IS.json"))["spec"])
        specs.append(replace(s,id=new,pacing=True,origin="DERIVED",
             mechanism="Completed "+old+" with the same causal130k pro-rata new-order pacing; no new threshold, no forced exit and no OOS scaling. Intended shares determined using last pre-order marks."))
    path=REPO_ROOT/"reports/cg_arrow003_pacing_completion.json"
    dump(path,[asdict(s) for s in specs])
    ledger({"event":"CONTINUATION_RATIONALE","phase":"DIRECTED C1/C5 practical policy completion",
            "notes":"Test pacing on promising R5 cover-only and conservative R4 overlays before selection. All-signal overlap may differ from isolated IS; settle this rule before confirmation. Original uncapped controls remain valid and visible."})
    run_is(specs,workers=8)
    matches=[]
    calibration=[]
    for s in specs:
        m=read(ROOT/"results"/(s.id+"_IS.json"))["metrics"]
        c=read(ROOT/"results"/(s.control+"_IS.json"))
        base=round(c["spec"]["base"]*m["avg_exposure"]/c["metrics"]["avg_exposure"]/25)*25
        match=replace(Spec(**c["spec"]),id="MATCH_"+s.id,base=base,
             mechanism="One IS average-exposure ratio fixed-base match, nearest25, for "+s.id)
        matches.append(match)
        calibration.append({"candidate":s.id,"control":match.id,"fixed_base":base,
             "is_candidate_average_gross":m["avg_exposure"],
             "calibration":"Original base times candidate IS average gross / original IS average gross; round nearest25 once, no iterative retarget"})
    dump(REPO_ROOT/"reports/cg_arrow003_pacing_match_specs.json",[asdict(s) for s in matches])
    dump(REPO_ROOT/"reports/cg_arrow003_pacing_match_calibration.json",calibration)
    run_is(matches,workers=8)


if __name__=="__main__":main()
