"""Complete matched L5 phases for the already scored patient phase diagnostic."""
from dataclasses import asdict,replace
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    p=Spec(**read(ROOT/'results/L5_IS.json')['spec'])
    specs=[replace(p,id='L5_'+phase,rhythm=phase,control='L5',origin='CONTROL',mechanism='Same inherited long mirror allocation on fixed global phase '+phase+'; matched baseline for the completed patient phase falsification, no new candidate') for phase in ('A','B')]
    ledger({'event':'MATCHED_PATIENT_PHASE_CONTROL_COMPLETION','ids':[s.id for s in specs],'rationale':'Existing patient phase A/B must also be compared with the L5 baseline on the same phase, not only the weekly baseline'})
    dump(REPO_ROOT/'reports/cg_arrow004_patient_phase_controls.json',[asdict(s) for s in specs]);run_is(specs)
