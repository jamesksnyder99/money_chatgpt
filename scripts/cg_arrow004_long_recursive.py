"""Three bounded long continuations motivated by completed IS comparisons."""
from dataclasses import asdict
from research.cg_arrow004_data import REPO_ROOT,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    specs=[
      Spec('A5_RECOVERY_VOTES',side='long',family='R5',allocation='select8',feature='recovery_votes',origin='ASTRA',control='L5_REC_SELECT8',mechanism='Combine intraday recovery volume interpretation with two advancing closes among three; test whether repeated buying improves the completed recovery selection, without changing budget or expiry'),
      Spec('A6_RECOVERY_EQUAL',side='long',family='R5',allocation='select8_equal',feature='recovery',origin='ASTRA',control='L5_REC_SELECT8',mechanism='Identical confidence-selected eight with equal dollars; isolate selected-name quality from confidence dollar weighting, motivated by the mild-loser equal-dollar control beating its weighted counterpart'),
      Spec('A7_MIDDLE_LOSERS',side='long',family='EQUAL',allocation='equal8',pool_start=5,origin='ASTRA',control='EQ_MILD_LOSERS',mechanism='One intermediate severity band, ranks5-12, after ranks9-16 equal dollars outperformed deepest-eight; no further rank-window sweep'),
    ]
    ledger({'event':'LONG_RECURSIVE_DECLARATION','ids':[s.id for s in specs],'rationale':'Separate name selection, confidence dollars, and distress severity using three bounded causal continuations'})
    dump(REPO_ROOT/'reports/cg_arrow004_long_recursive_specs.json',[asdict(s) for s in specs]);run_is(specs)
