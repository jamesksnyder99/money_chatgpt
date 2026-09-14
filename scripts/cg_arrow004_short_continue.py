"""Staged S4 carry and S5 rhythm after completed weekly allocation cores."""
from dataclasses import replace,asdict
from research.cg_arrow004_lab import Spec,run_is
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump

if __name__=='__main__':
    specs=[]
    for family in ('R4','R5'):
        specs.append(Spec('S4_'+family,family=family,allocation='carry',control='S1_'+family,mechanism='Strict S1 primary/reserve core; extra actual H only tops up fully observed favorable reserve ranks9-20 up to H/8 each; primary unchanged, no virtual credit'))
    for base in ('S0_R4','S0_R5','NORM8_R4','S3_R4','S1_R5'):
        old=Spec(**read(ROOT/'results'/(base+'_IS.json'))['spec'])
        for phase in ('A','B'):
            control=old.control+'_'+phase if old.control in ('S0_R4','S0_R5','NORM8_R4') else old.control
            specs.append(replace(old,id=base+'_'+phase,rhythm=phase,origin='CONTROL' if old.origin=='CONTROL' else 'DERIVED',control=control,
                          mechanism=old.mechanism+f'; fixed global biweekly phase {phase}, full actual headroom on selected Thursdays'))
    for base in ('S0_R5','S1_R5','S3_R4','NORM8_R4'):
        old=Spec(**read(ROOT/'results'/(base+'_IS.json'))['spec'])
        specs.append(replace(old,id=base+'_U125',u=1.25,origin='CONTROL' if old.origin=='CONTROL' else 'DERIVED',
                     control=old.control+'_U125' if old.control in ('S0_R5','NORM8_R4') else old.control,
                     mechanism=old.mechanism+'; single predeclared u=1.25 neighbor after u=1 core; same 130k planning maximum'))
    dump(REPO_ROOT/'reports/cg_arrow004_short_continuation_specs.json',[asdict(s) for s in specs]);run_is(specs,8)
