"""Predeclare bounded short allocation cores and separate long control anchors."""
from dataclasses import asdict
from research.cg_arrow004_lab import Spec,run_is
from research.cg_arrow004_data import REPO_ROOT,dump

def specs():
    out=[]
    for family,ticket in [('R4',5150.),('R5',8300.)]:
        control='S0_'+family
        out.extend([
          Spec('BRIDGE_'+family,family=family,allocation='fixed',ticket=ticket,origin='CONTROL',control=control,mechanism='Timing-only bridge: original intended fixed ticket, new nominal two-week clock and pre-order shares/bar-open entry'),
          Spec(control,family=family,origin='CONTROL',control=control,mechanism='Weekly half-target budget divided by eight then inherited confidence penalties; residual idle'),
          Spec('S1_'+family,family=family,allocation='reserve',control=control,mechanism='Original eight retain penalties; withheld budget buys only observed full-conviction ranks9-20 in original order'),
          Spec('BLIND_'+family,family=family,allocation='blind',origin='CONTROL',control=control,mechanism='Same primary penalties and reserve budget without favorable-state screen'),
          Spec('S2_'+family,family=family,allocation='weighted20',control=control,mechanism='Top twenty confidence-weighted at full common budget; unknown features receive half factor'),
          Spec('S3_'+family,family=family,allocation='select8',control='NORM8_'+family,mechanism='Choose eight from twenty by observed confidence tier then original rank; weight chosen names at common budget'),
          Spec('NORM8_'+family,family=family,allocation='normalize8',origin='CONTROL',control=control,mechanism='Original top eight confidence normalized to full budget; selection control'),
        ])
    out.extend([
      Spec('SHORT_EQ8',family='EQUAL',allocation='equal8',origin='CONTROL',control='S0_R4',mechanism='Equal-dollar original top eight; more utilization without additional information'),
      Spec('SHORT_EQ20',family='EQUAL',allocation='equal20',origin='CONTROL',control='SHORT_EQ8',mechanism='Equal-dollar top twenty at same cohort budget'),
      Spec('L0',side='long',family='EQUAL',allocation='equal8',origin='CONTROL',control='L0',mechanism='Independent long equal-dollar bottom-eight rebound anchor'),
      Spec('L4',side='long',family='R4',origin='CONTROL',control='L0',mechanism='Long bottom eight; low/normal participation full and high volume half; residual idle'),
      Spec('L5',side='long',family='R5',origin='CONTROL',control='L0',mechanism='Long bottom eight low participation plus ret3>=0 recovery full; still falling half; residual idle'),
      Spec('LONG_EQ20',side='long',family='EQUAL',allocation='equal20',origin='CONTROL',control='L0',mechanism='Independent equal-dollar bottom-twenty long breadth control'),
    ])
    return out

if __name__=='__main__':
    s=specs();dump(REPO_ROOT/'reports/cg_arrow004_core_specs.json',[asdict(x) for x in s]);run_is(s,workers=8)
