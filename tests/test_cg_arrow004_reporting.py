"""End-to-end aggregate export smoke test using flat synthetic books only."""
import csv
from dataclasses import asdict
from research import cg_arrow004_lab as lab
from research import cg_arrow004_report as report
from research.cg_arrow004_data import dump,read,digest

def test_report_exports_all_modes_and_months_without_market_payload(monkeypatch,tmp_path):
    root=tmp_path/'data';reports=tmp_path/'reports';reports.mkdir();freeze=reports/'cg_arrow004_freeze.json'
    specs=[lab.Spec('S0_R4',origin='CONTROL'),lab.Spec('S0_R5',family='R5',origin='CONTROL'),
       lab.Spec('L5',side='long',family='R5',origin='CONTROL',control='L5'),
       lab.Spec('A8_PATIENT_RECOVERY',side='long',family='R5',allocation='qualified8',feature='recovery',origin='ASTRA',control='L5'),
       lab.Spec('IWM_A8_PATIENT_RECOVERY',side='long',family='EQUAL',allocation='benchmark',origin='CONTROL',control='A8_PATIENT_RECOVERY',reference='A8_PATIENT_RECOVERY')]
    f={'start':'SYNTHETIC','deadline':'SYNTHETIC','elapsed_minutes':120,'code_sha256':{},'input_sha256':{},'specs':[asdict(s) for s in specs],
       'finalists':[{'id':'A8_PATIENT_RECOVERY','control':'L5','primary_claim':'balanced','pitch':'SYNTHETIC EXPORT TEST','acceptable_tradeoff':'SYNTHETIC'}]}
    dump(freeze,f);sha=digest(freeze);disc={}
    for s in specs:
        for mode in ('IS','OOS','ALL'):
            m,d=lab.score(s,mode,{},{});path=root/'details'/(s.id+'_'+mode+'.json');dump(path,d)
            rec={'spec':asdict(s),'metrics':m,'code_sha256':{},'detail_path':path.relative_to(tmp_path).as_posix(),'detail_sha256':digest(path)}
            dump(root/'results'/(s.id+'_'+mode+'.json'),rec)
            if mode=='IS':disc[s.id]=rec
    dump(reports/'cg_arrow004_discovery.json',{'books':disc,'counts_by_side_origin':{'synthetic':5}})
    for name in ('oos_started','oos_complete','investor_complete'):dump(root/(name+'.json'),{'freeze_sha256':sha,'elapsed_minutes':120,'commit':'SYNTHETIC_NO_GIT_COMMIT'})
    for name,value in [('ROOT',root),('REPO_ROOT',tmp_path),('R',reports),('FREEZE',freeze)]:monkeypatch.setattr(report,name,value)
    monkeypatch.setattr(report,'authorize',lambda mode:f);monkeypatch.setattr(report,'ledger',lambda row:None);monkeypatch.setattr(report,'elapsed',lambda:120*60)
    report.build();result=read(reports/'cg_arrow004_results.json')
    assert len(result['books'])==5
    assert all(len(b[mode]['metrics']['calendar_months'])==12 for b in result['books'].values() for mode in ('IS','OOS','ALL'))
    with (reports/'cg_arrow004_daily.csv').open(newline='') as fh:rows=list(csv.DictReader(fh))
    assert len(rows)==5*3*len(lab.SCORE) and {r['mode'] for r in rows}=={'IS','OOS','ALL'}
    assert all(float(r['pnl'])==0 for r in rows)
    assert 'original_entry' not in (reports/'cg_arrow004_results.json').read_text()
    assert (reports/'cg_arrow004_report.md').is_file() and (reports/'cg_arrow004_schedule.csv').is_file()
