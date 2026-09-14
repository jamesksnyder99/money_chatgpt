"""Causal IWM timing/pre-order-gross benchmark, diagnostic not separate engine."""
import argparse
from dataclasses import asdict
from research.cg_arrow004_lab import Spec,run_is
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--ids',nargs='+',required=True);a=p.parse_args();specs=[]
    for name in a.ids:
        parent=read(ROOT/'results'/(name+'_IS.json'))
        if parent['spec']['side']!='long':raise ValueError('Long benchmark only')
        # Older scores made before the explanatory planned-notional field can be
        # reconstructed from pre-order quantities, without reading future fills.
        detail=read(REPO_ROOT/parent['detail_path'])
        if any('planned_gross' not in c for c in detail['cohorts']):
            raise RuntimeError('Current metadata replay of the reference is required')
        specs.append(Spec('IWM_'+name,side='long',family='EQUAL',allocation='benchmark',rhythm=parent['spec']['rhythm'],u=parent['spec']['u'],
                     origin='CONTROL',control=name,reference=name,
                     mechanism='IWM at same scheduled open/expiry and matched parent pre-order gross commitment; integer shares use IWM pre-order mark. Actual gross deviations from missed fills/open gaps are reported; no later-close sizing. Single-name benchmark exempt from strategy symbol cap; diagnostic only.'))
    target=REPO_ROOT/'reports/cg_arrow004_benchmark_specs.json';prior=read(target) if target.exists() else []
    merged={s['id']:s for s in prior};merged.update({s.id:asdict(s) for s in specs})
    dump(target,list(merged.values()));run_is(specs)
