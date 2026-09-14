"""Last two independent long alternatives, then discovery branch closure."""
from dataclasses import asdict
from research.cg_arrow004_data import REPO_ROOT,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    specs=[
      Spec('A11_PERSISTENT_QUIET',side='long',family='R5',allocation='qualified8',feature='persistent',origin='ASTRA',control='PATIENT_MIRROR',mechanism='Patient observed full-conviction tickets require median of three consecutive signal-known daily volume/preceding20-session mean ratios <=1 and ret3>=0; replace a single quiet day with persistent normalization. Strict B/8, no forced utilization'),
      Spec('A12_MINUTE_RECOVERY',side='long',family='R5',allocation='select8_equal',feature='minute_flow',origin='ASTRA',control='A6_RECOVERY_EQUAL',mechanism='Replace participation tier with positive sum(sign(one-minute close-open)*minute volume)/total volume over completed signal RTH, retain nonnegative ret3 tier and equal-dollar selected eight. This is a bar-body recovery proxy, not aggressor-side order flow'),
    ]
    ledger({'event':'FINAL_LONG_BRANCH_DECLARATION','ids':[s.id for s in specs],'rationale':'Observed-history and simple patient ablations explain much apparent improvement. Test persistent participation and minute-derived directional consistency as two bounded economic alternatives; no further candidate branching'})
    dump(REPO_ROOT/'reports/cg_arrow004_long_final_branch_specs.json',[asdict(s) for s in specs]);run_is(specs)
    ledger({'event':'NEW_MECHANISM_BRANCHES_CLOSED','remaining_work':'Completed-branch falsification, necessary controls, freeze and one confirmation'})
