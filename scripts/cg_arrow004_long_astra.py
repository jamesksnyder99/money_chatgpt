"""Investigator-owned causal long alternatives, declared before outcomes."""
from dataclasses import asdict
from research.cg_arrow004_data import REPO_ROOT,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    ledger({'event':'ASTRA_LONG_DISCOVERY_START','rationale':'Recovery-tier selection improves ride over its normalized parent; test economically different loser severity, known-level reclaim and path stabilization instead of a coefficient/horizon grid'})
    specs=[
      Spec('A1_MILD_LOSERS',side='long',family='R5',allocation='normalize8',pool_start=9,origin='ASTRA',control='L5_NORM8',
           mechanism='Ranks9-16 rather than the eight deepest fifteen-session losers; same mirror confidence-normalized budget and two-week horizon. Avoid the most acute distress without outcome-based exclusions'),
      Spec('EQ_MILD_LOSERS',side='long',family='EQUAL',allocation='equal8',pool_start=9,origin='CONTROL',control='L0',
           mechanism='Equal-dollar ranks9-16, same budget/clock; separate less-extreme selection from confidence sizing'),
      Spec('A2_RECLAIM_HIGH',side='long',family='R5',allocation='select8',feature='reclaim',origin='ASTRA',control='L5_SELECT8',
           mechanism='Choose bottom-twenty recovery candidates using signal close above preceding session HIGH instead of the volume switch; retain ret3 recovery factor and original loss-rank ties; actual used features must be observed'),
      Spec('A3_STABLE_PATH',side='long',family='R5',allocation='select8',feature='stable',origin='ASTRA',control='L5_SELECT8',
           mechanism='Replace ret3>=0 with no new signal-session low and ret3>=-2percent, retaining volume penalty. A stable floor can precede a positive net rebound; no later observations or stop rules'),
      Spec('A4_ADVANCING_DAYS',side='long',family='R5',allocation='select8',feature='votes',origin='ASTRA',control='L5_SELECT8',
           mechanism='Recovery confidence from at least two positive daily close changes among last three, rather than positive net ret3; same volume state, bottom-twenty selection, budget and fixed expiry'),
    ]
    dump(REPO_ROOT/'reports/cg_arrow004_long_astra_specs.json',[asdict(s) for s in specs]);run_is(specs)
