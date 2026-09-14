"""First protected long challenges: recovery, actual membership, and reserves."""
from dataclasses import asdict
from research.cg_arrow004_data import REPO_ROOT,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    ledger({'event':'PROTECTED_LONG_LAB_START','scope':'Independent loser/recovery engine; short discovery closed except necessary audits/comparators','planned_research_end_minute':115,
            'baseline':'L0/L4 negative; L5 positive but slightly below its timing/pre-order-gross IWM reference; do not stop at mirrors'})
    specs=[
      Spec('L4_RECOVERY',side='long',family='R4',feature='recovery',control='L4',mechanism='Restore high-volume weight only if signal rises from open and closes in upper half of RTH range; lower-volume mirror treatment unchanged'),
      Spec('L5_RECOVERY',side='long',family='R5',feature='recovery',control='L5',mechanism='High participation receives full volume weight only with positive intraday recovery/upper-half close; ret3<0 still cautious; fixed two-week exit'),
      Spec('L5_NORM8',side='long',family='R5',allocation='normalize8',origin='CONTROL',control='L5',mechanism='Original bottom-eight mirror confidence normalized to same full cohort budget; control for selection and utilization'),
      Spec('L5_REC_NORM8',side='long',family='R5',allocation='normalize8',feature='recovery',origin='CONTROL',control='L5_RECOVERY',mechanism='Original bottom-eight recovery confidence normalized at same full budget; membership comparator'),
      Spec('L5_SELECT8',side='long',family='R5',allocation='select8',control='L5_NORM8',mechanism='Choose eight from bottom twenty by observed mirror recovery/participation tiers, then original loss rank; same weighted budget'),
      Spec('L5_REC_SELECT8',side='long',family='R5',allocation='select8',feature='recovery',control='L5_REC_NORM8',mechanism='Choose eight from bottom twenty by observed intraday-recovery/participation and ret3 tiers; original loss rank ties; no later price information'),
      Spec('L5_WEIGHT20',side='long',family='R5',allocation='weighted20',control='LONG_EQ20',mechanism='Bottom twenty weighted4:2:1 by stabilized ret3 and quiet participation; unknown factor half; compare same-budget equal breadth'),
      Spec('L5_RESERVE',side='long',family='R5',allocation='reserve',control='L5',mechanism='Retain original bottom eight mirror penalties; spare common budget buys fully observed stabilized/quiet reserve ranks9-20 in original loss order'),
    ]
    dump(REPO_ROOT/'reports/cg_arrow004_long_directed_specs.json',[asdict(s) for s in specs]);run_is(specs)
