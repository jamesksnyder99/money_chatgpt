"""One dependency-motivated advancing-day-vote fallback, then its proven overlay."""
from dataclasses import asdict,replace
from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump
from research.cg_arrow003_lab import Spec,run_is,ledger


def main():
    original=Spec(**read(ROOT/"results/A6_R5_STALL_VOTES_IS.json")["spec"])
    s=replace(original,id="A12_R5_OBSERVED_HISTORY_VOTES",momentum_missing="original_switch",
       mechanism="Dependency ablation: use advancing-day votes only when signal20-session volatility history is available; otherwise retain original ret3 switch. All entries remain. The completed attribution found1118dollars gain on182observed histories and2005on15missing histories; do not treat missingness as independent alpha.")
    dump(REPO_ROOT/"reports/cg_arrow003_history_fallback_spec.json",[asdict(s)])
    ledger({"event":"CONTINUATION_RATIONALE","phase":"ASTRA missing-history falsification",
            "notes":"Votes benefit is positive on observed history but64percent of its increment comes from sparse histories. Test the original-switch fallback before considering any modified combination. This is a causal pre-entry history predicate, not deleting outcomes or changing raw data."})
    run_is([s],workers=8)
    # The independent cover and pacing policies have already been completed.
    # Combining the tested fallback with those fixed rules tests its practical
    # continuation without choosing a new holding age, sizing curve or ceiling.
    combo=Spec(**read(ROOT/"results/AR6_R5_VOTES_COVER_PACED_IS.json")["spec"])
    combo=replace(combo,id="AR11_R5_OBSERVED_VOTES_COVER",momentum_missing="original_switch",
         mechanism="AR6 votes plus low-participation day6 half-cover and causal130k pacing, retaining original ret3 switch when20-session history is missing; no new threshold or excluded entry")
    dump(REPO_ROOT/"reports/cg_arrow003_history_fallback_combination.json",[asdict(combo)])
    run_is([combo],workers=8)


if __name__=="__main__":main()
