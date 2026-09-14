"""Close startup repair, then test the literal qualified full-headroom core."""
from dataclasses import replace,asdict
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump
from research.cg_arrow004_lab import Spec,run_is

if __name__=='__main__':
    old={}
    for n in ('S4_R4','S4_R5','FIXE_S4_R4'):
        rs=[read(p) for p in (ROOT/'superseded').glob(n+'_*.json') if not p.name.endswith('_detail.json')]
        old[n]=[{'metrics':r['metrics'],'detail_sha256':r['detail_sha256']} for r in rs]
    stress=read(REPO_ROOT/'reports/cg_arrow004_stale_stress.json')
    dump(REPO_ROOT/'reports/cg_arrow004_superseded_repairs.json',{'status':'SUPERSEDED: carry startup violated the required half-target first cohort',
      'old_scores':old,'old_stale_diagnostics':{n:stress['books'][n] for n in ('S4_R4',)},
      'old_match_calibration':read(REPO_ROOT/'reports/cg_arrow004_short_match_calibration.json'),
      'interpretation':'Invalid startup benefit is not evidence; complete local outputs and original ledger events preserved. No OOS had been exposed.'})
    c=read(ROOT/'results/S4_R4_IS.json');b=read(ROOT/'results/BRIDGE_R4_IS.json');oldspec=Spec(**read(ROOT/'results/MATCH_S4_R4_IS.json')['spec'])
    ratio=c['metrics']['avg_exposure']/b['metrics']['avg_exposure'];ticket=round(b['spec']['ticket']*ratio/25)*25
    repaired=replace(oldspec,ticket=ticket)
    dump(REPO_ROOT/'reports/cg_arrow004_repaired_match_calibration.json',{'candidate':'S4_R4','ratio':ratio,'ticket':ticket,'rule':'Same single IS mean-gross/nearest25 calibration after the required startup repair; not a profit optimization'})
    run_is([repaired],8,replay_reason='Common startup correction changed S4 target exposure; repeat the exact original one-formula match calibration, not a size search')
    specs=[Spec('S4_FULL_'+f,family=f,allocation='carry_full',control='S1_'+f,
           mechanism='Literal qualified headroom extension: first global Thursday half-budget; later H/8 full-conviction observed primary/reserve tickets, cautious/unknown primary keeps strict B/8*m, no extra weak orders or virtual credits') for f in ('R4','R5')]
    dump(REPO_ROOT/'reports/cg_arrow004_carry_full_specs.json',[asdict(s) for s in specs]);run_is(specs)
