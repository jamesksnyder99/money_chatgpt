"""Patient recovery and two independent quality falsifications, predeclared."""
from dataclasses import asdict
from research.cg_arrow004_data import REPO_ROOT,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    specs=[
      Spec('A8_PATIENT_RECOVERY',side='long',family='R5',allocation='qualified8',feature='recovery',origin='ASTRA',control='A6_RECOVERY_EQUAL',mechanism='Only fully observed full-conviction recovery names from bottom twenty, original loss-rank order, at most eight each at strict B/8; unused slots remain idle. No normalization into cautious names and no extraordinary headroom'),
      Spec('A9_QUIET_RECOVERY',side='long',family='R5',allocation='select8_equal',feature='quiet_recovery',origin='ASTRA',control='A6_RECOVERY_EQUAL',mechanism='Require low participation AND up-from-open upper-half close for favorable volume tier; distinguish an actual quiet recovery from merely low-volume continuing declines. Retain positive-ret3 tier and equal-dollar selected eight'),
      Spec('A10_RECLAIM_MEAN',side='long',family='R5',allocation='select8_equal',feature='mixed_recovery',origin='ASTRA',control='A6_RECOVERY_EQUAL',mechanism='Replace participation switch with up-from-open upper-half close AND reclaim of previous five-session mean close; retain ret3 and equal dollars. Test signal-known price recovery quality rather than participation alone'),
    ]
    ledger({'event':'LONG_PATIENT_DECLARATION','ids':[s.id for s in specs],'rationale':'Full-confidence recovery tier carries most positive PnL; test selective inactivity and challenge volume with causal recovery-quality conditions. No horizon or coefficient grid'})
    dump(REPO_ROOT/'reports/cg_arrow004_long_patient_specs.json',[asdict(s) for s in specs]);run_is(specs)
