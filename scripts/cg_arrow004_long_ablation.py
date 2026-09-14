"""Causal missing-history and high-participation ablations for recovery leads."""
from dataclasses import asdict
from research.cg_arrow004_data import REPO_ROOT,dump
from research.cg_arrow004_lab import Spec,run_is,ledger

if __name__=='__main__':
    specs=[
      Spec('PATIENT_MIRROR',side='long',family='R5',allocation='qualified8',feature='mirror',origin='CONTROL',control='A8_PATIENT_RECOVERY',mechanism='Patient ablation: admit only observed low-volume/nonnegative-ret3 names; remove high-volume intraday recovery allowance, preserve bottom-twenty rank order and strict B/8 per name'),
      Spec('OBSERVED_REC_BOTTOM8',side='long',family='R5',allocation='observed8',feature='recovery',origin='CONTROL',control='L5_REC_NORM8',mechanism='Choose first eight loss-ranked names whose actually used volume/ret3 features are observed, without sorting by confidence tier; recovery weights normalized to B. Isolate missing-history exclusion from recovery ranking'),
    ]
    ledger({'event':'LONG_ABLATION_DECLARATION','ids':[s.id for s in specs],'rationale':'Patient profit is mostly the quiet nonnegative-ret3 tier; recovery-selection parent contains unknown history. Challenge each proposed source of improvement directly'})
    dump(REPO_ROOT/'reports/cg_arrow004_long_ablation_specs.json',[asdict(s) for s in specs]);run_is(specs)
