"""One-time IS fixed-ticket comparisons and fixed-reference-equity controls."""
from dataclasses import replace,asdict
from research.cg_arrow004_lab import Spec,run_is
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump

if __name__=='__main__':
    specs=[];cal=[]
    for name in ('S0_R4','S1_R4','S4_R4','S0_R5','S0_R5_U125','S3_R4','NORM8_R4'):
        r=read(ROOT/'results'/(name+'_IS.json'));s=Spec(**r['spec'])
        specs.append(replace(s,id='FIXE_'+name,fixed_equity=True,origin='CONTROL',control=name,
                     mechanism=s.mechanism+'; reference equity fixed100k for target, actual current equity still governs symbol caps; separates equity linkage from selection'))
    for name,base in [('S4_R4','BRIDGE_R4'),('S3_R4','BRIDGE_R4'),('S0_R5_U125','BRIDGE_R5')]:
        c=read(ROOT/'results'/(name+'_IS.json'));b=read(ROOT/'results'/(base+'_IS.json'));old=Spec(**b['spec'])
        ratio=c['metrics']['avg_exposure']/b['metrics']['avg_exposure'];ticket=round(old.ticket*ratio/25)*25
        specs.append(replace(old,id='MATCH_'+name,ticket=ticket,control=name,
                      mechanism='One-time IS average-gross calibrated fixed-ticket comparison to '+name+'. Same confidence and new two-week clock; a fixed-ticket counterfactual, not a budgeted deployment policy. No OOS rescaling; exact peak/capital mismatch disclosed.'))
        cal.append({'candidate':name,'reference':base,'is_average_gross_ratio':ratio,'fixed_ticket':ticket,'calibration':'One formula, nearest25 dollars; no iterative size search or OOS maxima'})
    dump(REPO_ROOT/'reports/cg_arrow004_short_match_calibration.json',cal)
    dump(REPO_ROOT/'reports/cg_arrow004_short_match_specs.json',[asdict(s) for s in specs]);run_is(specs)
