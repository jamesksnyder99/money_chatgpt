"""One bounded allocation continuation and IS-derived comparison sizes."""
from dataclasses import asdict,replace
from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump
from research.cg_arrow003_lab import Spec,CONTROLS,run_is,ledger


def main():
    # The votes+cover combination earns more than R5 while its worst day worsens.
    # A single round-number conservative size asks whether that gain can buy ride.
    prior=Spec(**read(ROOT/"results/AR6_R5_VOTES_COVER_PACED_IS.json")["spec"])
    specs=[replace(prior,id="AR8_R5_VOTES_COVER_CONSERVATIVE",base=7000,
              mechanism="One conservative $7000 R5 votes plus late-cover package, causal130k pacing; use the observed return gain to reduce dollar downside, without a ceiling or size sweep"),
           replace(CONTROLS[2],id="R5_CONSERVATIVE_7000",base=7000,
              mechanism="Fixed $7000 original R5 comparator for the conservative votes-cover package")]
    path=REPO_ROOT/"reports/cg_arrow003_allocation_continuation.json"
    dump(path,[asdict(s) for s in specs])
    ledger({"event":"CONTINUATION_RATIONALE","id":specs[0].id,"basis":"AR6 improves profit but worsens worst-day loss; one conservative round-number scale tests retained useful economics. No OOS outcomes used.","phase":"DIRECTED C1 allocation continuation using independently completed Astra mechanisms"})
    run_is(specs)
    targets=["AR3_R4_LATE_COVER_CONSERVATIVE","AR6_R5_VOTES_COVER_PACED",
             "AR7_R4_LATE_COVER_PACED","AR8_R5_VOTES_COVER_CONSERVATIVE","AR2_R5_LATE_WEAK_PART_COVER"]
    matches=[]
    records=[]
    for target in targets:
        r=read(ROOT/"results"/(target+"_IS.json"))
        control=read(ROOT/"results"/(r["spec"]["control"]+"_IS.json"))
        base=round(control["spec"]["base"]*r["metrics"]["avg_exposure"]/control["metrics"]["avg_exposure"]/25)*25
        s=replace(Spec(**control["spec"]),id="MATCH_"+target,base=base,
                  mechanism="Single IS average-exposure ratio match rounded to nearest $25 for "+target)
        matches.append(s)
        records.append({"candidate":target,"control":s.id,"fixed_base":base,
                        "is_candidate_average_gross":r["metrics"]["avg_exposure"],
                        "calibration":"original base * candidate IS avg gross / original IS avg gross; nearest $25 once; no iterative retarget and no OOS peak normalization"})
    dump(REPO_ROOT/"reports/cg_arrow003_final_match_specs.json",[asdict(s) for s in matches])
    dump(REPO_ROOT/"reports/cg_arrow003_size_match_calibration.json",records)
    run_is(matches)


if __name__=="__main__":main()
