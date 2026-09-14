"""Fixed-reference equity and globally anchored rhythm controls for long leads."""
from dataclasses import asdict,replace
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    specs=[]
    for n in ('L5','L5_REC_NORM8','L5_REC_SELECT8','A6_RECOVERY_EQUAL','A8_PATIENT_RECOVERY'):
        parent=Spec(**read(ROOT/'results'/(n+'_IS.json'))['spec'])
        specs.append(replace(parent,id='FIXE_'+n,fixed_equity=True,origin='CONTROL',control=n,mechanism='Fixed-reference E=$100000 gross target; actual cash, aggregate name cap and surviving obligations remain real. Isolate compounding from '+n))
    for n in ('L5_REC_NORM8','L5_REC_SELECT8','A8_PATIENT_RECOVERY'):
        parent=Spec(**read(ROOT/'results'/(n+'_IS.json'))['spec'])
        for phase in ('A','B'):
            specs.append(replace(parent,id=n+'_'+phase,rhythm=phase,origin='CONTROL',control=n,mechanism='Both fixed global alternate-Thursday phases; two-week horizon unchanged. Calendar-phase falsification of '+n+', not a phase-selection contest'))
    ledger({'event':'LONG_CONTROL_DECLARATION','ids':[s.id for s in specs],'rationale':'Leading recovery and patient books need compounding isolation and both-phase falsification; no phase selected from results'})
    dump(REPO_ROOT/'reports/cg_arrow004_long_control_specs.json',[asdict(s) for s in specs]);run_is(specs)
