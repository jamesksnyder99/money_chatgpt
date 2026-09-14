"""Frozen claim evaluation and aggregate-only Arrow 004 report generation."""
from collections import Counter
from datetime import date,datetime,timedelta
from ingest.calendar import nyse_sessions
import argparse,csv,math,statistics
from research.cg_arrow004_data import ROOT,REPO_ROOT,read,dump,digest,stamp,schedule
from research.cg_arrow004_lab import FREEZE,MATERIALITY,authorize,elapsed,ledger

R=REPO_ROOT/'reports'
DOWN=('max_dd','red_loss_sum','worst_month','worst_day')

def claim_test(m,c,kind):
    """Fixed relative/absolute materiality; report every component independently."""
    gain=m['total_pnl']-c['total_pnl'];needed=max(MATERIALITY['profit_absolute'],MATERIALITY['profit_relative']*abs(c['total_pnl']))
    improvement={k:abs(c[k])-abs(m[k]) for k in DOWN}
    better={k:improvement[k]>=MATERIALITY['downside_relative']*abs(c[k]) and improvement[k]>0 for k in DOWN}
    not_worse={k:abs(m[k])<=1.05*abs(c[k])+1e-8 for k in DOWN}
    retention=m['total_pnl']/c['total_pnl'] if c['total_pnl']>0 else None
    if kind=='balanced':ok=gain>=needed and all(not_worse.values()) and any(better.values())
    elif kind=='ride':ok=c['total_pnl']>0 and retention>=MATERIALITY['ride_retention'] and better['max_dd'] and all(not_worse.values())
    elif kind=='return':ok=gain>=needed and all(abs(m[k])<=(1+MATERIALITY['return_risk_tolerance'])*abs(c[k])+1e-8 for k in DOWN)
    else:raise ValueError('Unknown frozen claim')
    return {'claim':kind,'numeric_claim_pass':bool(ok),'profit_increment':gain,'material_profit_threshold':needed,'profit_retention':retention,
            'downside_dollar_improvements':improvement,'material_downside_improvements':better,'within_5pct_downside':not_worse,
            'interpretation':'Numeric comparison only: continuous DD, signal-month red-loss sum/worst month and actual worst day. Data, costs, benchmark and concentration qualifications remain mandatory. Correlated downside metrics are not independent confirmations.'}

def corr(a,b):
    if len(a)!=len(b) or len(a)<2:raise ValueError('Aligned daily series required')
    am=statistics.mean(a);bm=statistics.mean(b);va=sum((x-am)**2 for x in a);vb=sum((x-bm)**2 for x in b)
    return sum((x-am)*(y-bm) for x,y in zip(a,b))/math.sqrt(va*vb) if va*vb>0 else None

def disposition(m,c,origin):
    if origin in {'CONTROL','DIAGNOSTIC'}:return 'CONTROL: explanatory comparator, not discovery'
    if m['total_pnl']<=0:return 'ECONOMICALLY REJECTED: nonpositive baseline net profit'
    if all(m[k]>=c[k] for k in DOWN) and m['total_pnl']>=c['total_pnl']:return 'PROFITABLE FRONTIER: numeric improvement, conditional evidence'
    if m['total_pnl']<=c['total_pnl'] and all(m[k]<=c[k] for k in DOWN):return 'DOMINATED BUT PROFITABLE: direct parent better on profit and all reported downside amounts'
    return 'PROFITABLE TRADEOFF: mixed dimensions; not blanket superiority'

def discovery():
    authorize('IS');records={p.stem[:-3]:read(p) for p in (ROOT/'results').glob('*_IS.json')};rows={}
    for n,r in sorted(records.items()):
        s=r['spec'];parent=records.get(s['control'],r);status=disposition(r['metrics'],parent['metrics'],s['origin'])
        rows[n]={'spec':s,'metrics':r['metrics'],'disposition':status,'detail_path':r['detail_path'],'detail_sha256':r['detail_sha256']}
        ledger({'event':'IS_DISPOSITION','id':n,'control':s['control'],'disposition':status,'code_sha256_identity_checked_at_final_replay':True})
    counts=Counter((r['spec']['side'],r['spec']['origin']) for r in records.values())
    dump(R/'cg_arrow004_discovery.json',{'timestamp':stamp(),'books':rows,'counts_by_side_origin':{a+'/'+b:v for (a,b),v in counts.items()},
         'new_core_policy_specifications':sum(r['spec']['origin'] in {'DIRECTED','ASTRA'} for r in records.values()),
         'derived_phase_utilization_neighbors':sum(r['spec']['origin']=='DERIVED' for r in records.values()),
         'interpretation':'Replays, financing/stale scenarios, controls and phase companions are not additional discoveries. Superseded economic repairs are preserved separately.'})
    print('Discovery closure',len(records),'books')

def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(x) for x in row)+' |' for row in rows])

def money(x):return f'{x:,.2f}'
def percent(x):return 'n/a' if x is None else f'{100*x:.2f}%'

def write_csv(path,rows,fields=None):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields or list(rows[0]));w.writeheader();w.writerows(rows)

def holding_stats(positions,exits,terminal,end_date):
    """Observed exits only; unfinished holdings have separate censored ages."""
    values={'actual_calendar_days':[],'actual_intervening_sessions':[],'actual_elapsed_hours':[]}
    dates=[];ages=[]
    for p in positions:
        entry=datetime.fromisoformat(p['entry_ts'])
        if p['id'] in exits:
            finish=datetime.fromisoformat(exits[p['id']]['exit_ts']);dates.append(finish.date().isoformat())
            values['actual_calendar_days'].append((finish.date()-entry.date()).days)
            values['actual_intervening_sessions'].append(len(nyse_sessions(entry.date()+timedelta(days=1),finish.date())))
            values['actual_elapsed_hours'].append((finish-entry).total_seconds()/3600)
        elif p['id'] in terminal:ages.append((date.fromisoformat(end_date)-entry.date()).days)
    out={'actual_exit_dates':'|'.join(sorted(set(dates))),'terminal_max_age_calendar_days':max(ages) if ages else ''}
    for key,items in values.items():
        for label,fn in [('min',min),('median',statistics.median),('max',max)]:out[key+'_'+label]=fn(items) if items else ''
    return out

def build():
    f=authorize('ALL');complete=read(ROOT/'investor_complete.json')
    if complete['freeze_sha256']!=digest(FREEZE):raise RuntimeError('Incomplete or mismatched investor replay')
    specs={s['id']:s for s in f['specs']};books={};details={};daily=[];cohorts=[]
    for n,s in specs.items():
        books[n]={};details[n]={}
        for mode in ('IS','OOS','ALL'):
            rec=read(ROOT/'results'/(n+'_'+mode+'.json'));d=read(REPO_ROOT/rec['detail_path']);m=rec['metrics']
            if rec['spec']!=s or rec['code_sha256']!=f['code_sha256'] or digest(REPO_ROOT/rec['detail_path'])!=rec['detail_sha256']:raise RuntimeError('Final output identity mismatch')
            if abs(sum(x['pnl'] for x in m['calendar_months'])-m['total_pnl'])>1e-6:raise AssertionError('Monthly conservation')
            if len(m['calendar_months'])!=12:raise AssertionError('All calendar months retained')
            books[n][mode]={'metrics':m,'detail_path':rec['detail_path'],'detail_sha256':rec['detail_sha256']};details[n][mode]=d
            for row in d['daily']:
                daily.append({'book':n,'side':s['side'],'mode':mode,**{k:row[k] for k in ('date','pnl','equity','cash','gross','target','unused_headroom','cohorts','tickets','stale_gross','overdue_tickets')}})
            exits={l['ticket_id']:l for l in d['legs']};terminal={p['id'] for p in d['terminal']}
            by={c['nominal']:c for c in d['cohorts']}
            for sched in schedule():
                c=by.get(sched['nominal']);positions=[p for p in d['positions'] if p['nominal']==sched['nominal']]
                cohorts.append({'book':n,'side':s['side'],'mode':mode,**sched,**holding_stats(positions,exits,terminal,d['daily'][-1]['date']),'scheduled_in_this_book':c is not None,
                  'filled':len(positions),'missed':c['missed'] if c else 0,'delayed_exit_fills':sum(exits.get(p['id'],{}).get('delayed',False) for p in positions),
                  'terminal_tickets':sum(p['id'] in terminal for p in positions),'terminal_overdue':sum(p['id'] in terminal and p['expiry_date']<=d['daily'][-1]['date'] for p in positions),
                  'preorder_equity':c['preorder_equity'] if c else '', 'surviving_gross':c['surviving_gross'] if c else '',
                  'cash_before_due_exits':c['cash_before_due_exits'] if c else '', 'cash_after_due_exits':c['cash_after_due_exits'] if c else '',
                  'surviving_cohorts':c['surviving_cohorts'] if c else '', 'pending_due_tickets':c['pending_due_tickets'] if c else '',
                  'target':c['target'] if c else '', 'headroom':c['headroom'] if c else '', 'budget':c['budget'] if c else '',
                  'planned_gross':c['planned_gross'] if c else '', 'filled_gross':c['filled_gross'] if c else ''})
    verdicts={};benchmark={};structural={};secondary={}
    for p in f['finalists']:
        n=p['id'];c=p['control'];v={mode:claim_test(books[n][mode]['metrics'],books[c][mode]['metrics'],p['primary_claim']) for mode in ('IS','OOS','ALL')}
        v['repeated_frozen_numeric_claim']=all(v[mode]['numeric_claim_pass'] for mode in ('IS','OOS'))
        v['frozen_pitch']=p['pitch'];v['acceptable_tradeoff']=p['acceptable_tradeoff'];v['control']=c
        v['status']='CONDITIONAL NUMERIC CLAIM REPEATED' if v['repeated_frozen_numeric_claim'] else 'FROZEN CLAIM DID NOT REPEAT'
        v['deployment']='NOT CERTIFIED: incomplete lifecycle marks, partial actions, unknown dividends/loans and bar-open fill proxy'
        verdicts[n]=v
        secondary[n]={}
        for other in p.get('secondary_controls',[]):
            secondary[n][other]={mode:{'profit_increment':books[n][mode]['metrics']['total_pnl']-books[other][mode]['metrics']['total_pnl'],
                 'dd_improvement':abs(books[other][mode]['metrics']['max_dd'])-abs(books[n][mode]['metrics']['max_dd']),
                 'average_gross_difference':books[n][mode]['metrics']['avg_exposure']-books[other][mode]['metrics']['avg_exposure'],
                 'peak_gross_difference':books[n][mode]['metrics']['peak_exposure']-books[other][mode]['metrics']['peak_exposure']} for mode in ('IS','OOS','ALL')}
        structural[n]={}
        for label,a,b in [('fixed_reference_equity','FIXE_'+n,'FIXE_'+c),('phase_A',n+'_A',c+'_A'),('phase_B',n+'_B',c+'_B')]:
            if a in books and b in books:structural[n][label]={'candidate':a,'control':b,'modes':{mode:claim_test(books[a][mode]['metrics'],books[b][mode]['metrics'],p['primary_claim']) for mode in ('IS','OOS','ALL')}}
    for n,s in specs.items():
        if not s.get('reference'):continue
        parent=s['reference'];benchmark[parent]={}
        for mode in ('IS','OOS','ALL'):
            a=books[parent][mode]['metrics'];b=books[n][mode]['metrics'];ad=details[parent][mode];bd=details[n][mode]
            benchmark[parent][mode]={'benchmark':n,'stock_minus_iwm_profit':a['total_pnl']-b['total_pnl'],
              'stock_average_gross':a['avg_exposure'],'iwm_average_gross':b['avg_exposure'],
              'stock_entry_gross':sum(c['filled_gross'] for c in ad['cohorts']),'iwm_entry_gross':sum(c['filled_gross'] for c in bd['cohorts']),
              'integer_preorder_commitment_difference':sum(c['planned_gross'] for c in ad['cohorts'])-sum(c['planned_gross'] for c in bd['cohorts']),
              'stock_max_dd':a['max_dd'],'iwm_max_dd':b['max_dd'],'daily_pnl_correlation':corr([r['pnl'] for r in ad['daily']],[r['pnl'] for r in bd['daily']])}
    correlations={}
    for p in f['finalists']:
        if specs[p['id']]['side']!='long':continue
        for short in ('S0_R4','S0_R5'):
            if short in details:correlations[p['id']+'/'+short]=corr([r['pnl'] for r in details[p['id']]['ALL']['daily']],[r['pnl'] for r in details[short]['ALL']['daily']])
    nonadditive={n:books[n]['ALL']['metrics']['total_pnl']-books[n]['IS']['metrics']['total_pnl']-books[n]['OOS']['metrics']['total_pnl'] for n in books}
    examples={n:details[n]['ALL']['cohorts'][:3] for n in ('S0_R4','S0_R5','L5') if n in details}
    counts=read(R/'cg_arrow004_discovery.json')['counts_by_side_origin']
    result={'timestamp':stamp(),'elapsed_minutes_at_report':elapsed()/60,'status':'CONFIRMATION_AND_CHRONOLOGICAL_REPLAY_COMPLETE',
       'freeze_sha256':digest(FREEZE),'freeze_commit':read(ROOT/'oos_started.json')['commit'],'confirmation_started':read(ROOT/'oos_started.json'),
       'confirmation_complete':read(ROOT/'oos_complete.json'),'investor_complete':complete,'code_sha256':f['code_sha256'],'input_sha256':f['input_sha256'],
       'books':books,'finalist_verdicts':verdicts,'benchmarks':benchmark,'descriptive_long_short_correlations':correlations,
       'secondary_comparator_differences':secondary,'matched_structural_checks':structural,
       'chronological_minus_sum_is_oos':nonadditive,'ordinary_three_thursday_examples':examples,'discovery_counts':counts,
       'funding':'Each book starts with its own hypothetical $100000. Separate long and short accounts are not added or presented as one funded portfolio.',
       'benchmark_matching':'Same pre-order gross commitment and prescribed clock; actual gross mismatch due to missing stock fills, gaps, integer shares and delayed held-stock exits. Not an exact daily risk match.',
       'validation':'Even signal months are reused internal confirmation, not pristine validation. No parameter changes after reveal.'}
    dump(R/'cg_arrow004_results.json',result);write_csv(R/'cg_arrow004_daily.csv',daily);write_csv(R/'cg_arrow004_schedule.csv',cohorts)
    disc=read(R/'cg_arrow004_discovery.json')['books'];lines=['# CG Arrow 004 — completed research and internal confirmation','',
       'In-sample (IS) uses odd signal months; out-of-sample (OOS) is reused even-month internal confirmation. All amounts are hypothetical net profit and loss (PnL) after inherited commission/spread, before unverified dividends and baseline financing. Drawdown (DD) is continuous marked equity. Regular trading hours (RTH) and all market clocks use America/New_York. Every book has its own $100,000; no combined funded strategy is asserted.','',
       f"Start {f['start']}; hard deadline {f['deadline']}. Freeze at {f['elapsed_minutes']:.2f} elapsed minutes, committed as `{result['freeze_commit']}` before the single reveal. Investor replay completed at {complete['elapsed_minutes']:.2f} minutes. Final report checkpoint {elapsed()/60:.2f} minutes. Exact command, tests and effort closure are in `cg_arrow004_commands.txt` and the final handoff checkpoint. No Arrow 005 was started.",'',
       '## Main finding','',
       'The new short utilization mechanisms did not establish a credible improvement over the paired R4/R5 controls in IS; no new short winner was forced into confirmation. A carry startup repair removed an apparent R4 benefit. The protected long laboratory developed recovery selection and selective inactivity, then challenged them with equal sizing, known-level reclaim, path quality, phase, fixed-equity, concentration and missing-mark diagnostics. Negative findings below have the same status as positive screens.','',
       'Lifecycle gaps remain outcome-related. Accounting consistency is established separately from investment validity. Long gaps include last-known prices below the entry band; short gaps concentrate above it. Positions are retained until an actual observed authorized exit or as terminal inventory. No hindsight survivor universe, fabricated liquidation, new subscription, credential detour or source-repository access was used. See `cg_arrow004_repairs.md` and coverage artifacts.','',
       'A major limitation is the separate prior-national-EOD valuation sensitivity: S0_R4 changes from +$11,602.00 to -$58,475.98 IS and S0_R5 from +$13,086.69 to -$18,851.60. These are conditional valuation scenarios, not replacement headline results or executable exits. Later-session scope and absent adjustment declaration prevent silent baseline substitution. Positive long reference-sensitivity results are likewise kept separate. Absolute short economics under long-lived stale minute marks are heavily DATA-LIMITED. See `cg_arrow004_reference_sensitivity.json`.','',
       '## Frozen claims and confirmation','']
    for n,v in verdicts.items():
        lines += [f"### {n}: {v['status']}",'',f"Frozen {v['IS']['claim']} claim against {v['control']}: {v['frozen_pitch']} Acceptable tradeoff: {v['acceptable_tradeoff']}",'',
          table(['View','Net PnL','$/session','DD','Parent delta','Numeric claim'],[[mode,money(books[n][mode]['metrics']['total_pnl']),money(books[n][mode]['metrics']['per_day']),money(books[n][mode]['metrics']['max_dd']),money(v[mode]['profit_increment']),v[mode]['numeric_claim_pass']] for mode in ('IS','OOS','ALL')]),'',
          'The claim retains its original comparator and thresholds after reveal. Benchmark-relative profit, capital and data qualifications below can still limit an apparent numeric success.','']
    for side in ('short','long'):
        chosen=[(n,r) for n,r in disc.items() if r['spec']['side']==side and r['spec']['origin'] not in {'CONTROL','DIAGNOSTIC'}]
        chosen.sort(key=lambda x:x[1]['metrics']['total_pnl'],reverse=True)
        lines += [f'## Ranked {side} discovery — core specifications and declared neighbors','',table(['Policy','Net PnL','$/session','DD','Utilization','Primary comparator'],[[n,money(r['metrics']['total_pnl']),money(r['metrics']['per_day']),money(r['metrics']['max_dd']),percent(r['metrics']['utilization']),r['spec']['control']] for n,r in chosen]),'',
          'Full specifications, red-month loss sums, worst/median month, worst day, underwater duration, concentration, scenarios and individual dispositions are retained in `cg_arrow004_discovery.json`. Derived phase/utilization neighbors are counted separately from core policies; controls, replays and scenarios are not new discoveries.','']
    lines += ['## Fixed-equity and phase falsification','',table(['Finalist','Configuration','Matched control','IS claim','OOS claim','ALL claim'],[[n,label,x['control'],*[x['modes'][mode]['numeric_claim_pass'] for mode in ('IS','OOS','ALL')]] for n,rows in structural.items() for label,x in rows.items()]),'',
      'These are locked explanatory comparisons. They cannot replace a failed weekly claim or select a favorable phase after reveal. Secondary ablations and direct-parent differences are separately retained in `secondary_comparator_differences`.','',
      '## Controls and all-signal capital','',table(['Policy','IS PnL','OOS PnL','ALL PnL','ALL $/session','ALL DD'],[[n,*[money(books[n][mode]['metrics']['total_pnl']) for mode in ('IS','OOS','ALL')],money(books[n]['ALL']['metrics']['per_day']),money(books[n]['ALL']['metrics']['max_dd'])] for n in books if not specs[n].get('reference')]),'',
      'ALL is one chronological account with actual cross-cohort headroom interactions. Its profit differs from adding isolated IS/OOS books; those differences are explicitly published in `chronological_minus_sum_is_oos`. Flat sessions remain in denominators: 124 IS, 127 OOS, 251 ALL. Isolated weekly books receive no missing-cohort top-up.','']
    focus=list(dict.fromkeys(['S0_R4','S0_R5','L0','L4','L5']+[p['id'] for p in f['finalists']]))
    focus=[n for n in focus if n in books]
    lines += [table(['Policy','Avg gross','95% gross','Peak EOD gross','Utilization','Unused target','Days >130k','Peak gross/E','Terminal/stale'],[[n,money(m['avg_exposure']),money(m['p95_exposure']),money(m['peak_exposure']),percent(m['utilization']),money(m['avg_unused_headroom']),m['above_130k_sessions'],percent(m['peak_gross_to_equity']),money(m['terminal_gross'])+'/'+money(m['terminal_stale_gross'])] for n in focus for m in [books[n]['ALL']['metrics']]]),'',
      'Target headroom is neither interest-eligible cash nor broker buying power. New aggregate symbol orders are capped at 20% of positive current equity; later price drift is retained. Exposure duration, dollar-days, causes, occupancy, overlap, tickets, turnover and margin debit are in results/daily aggregates; synchronized minute results are in `cg_arrow004_minute_all.json`. Immediate post-entry gross at known surviving marks plus actual new fills is reported separately, including target overshoot and allocations above $130k. The $130k planning range is not a forced liquidation threshold.','',
      '## Long benchmark and financing','',table(['Long policy','View','Stock PnL minus IWM','Stock avg gross','IWM avg gross','Stock DD','IWM DD'],[[n,mode,money(v['stock_minus_iwm_profit']),money(v['stock_average_gross']),money(v['iwm_average_gross']),money(v['stock_max_dd']),money(v['iwm_max_dd'])] for n,row in benchmark.items() for mode,v in row.items() if n in focus]),'',
      result['benchmark_matching']+' IWM is a diagnostic benchmark, exempt from the strategy common-stock restriction and 20% single-name safeguard. It is not an additional funded engine. Positive raw long PnL alone is not stock-selection alpha.','',
      table(['Policy','Base ALL','Double spread','10% borrow / 5% debit','30% borrow / 10% debit'],[[n,money(m['total_pnl']),money(m['scenarios'][('borrow' if specs[n]['side']=='short' else 'debit')+'_0_spread_2']),money(m['scenarios'][('borrow_10' if specs[n]['side']=='short' else 'debit_5')+'_spread_1']),money(m['scenarios'][('borrow_30' if specs[n]['side']=='short' else 'debit_10')+'_spread_1'])] for n in focus for m in [books[n]['ALL']['metrics']]]),'',
      'Commission stays unchanged in doubled-spread scenarios. Short borrowing uses preceding end-of-day short value by calendar days; long financing uses actual negative cash, with no short-loan charge on long assets. These frozen sensitivities do not resize trades, and idle yield is zero. Missing dividend entitlement/obligation and incomplete corporate-action coverage remain unresolved.','',
      '## Twelve actual calendar-month returns','']
    monthly_focus=list(dict.fromkeys(['S0_R4','S0_R5','L5']+[p['id'] for p in f['finalists']]))
    monthly_focus=[n for n in monthly_focus if n in books]
    lines += [table(['Month']+monthly_focus,[[books[monthly_focus[0]]['ALL']['metrics']['calendar_months'][i]['month']]+[percent(books[n]['ALL']['metrics']['calendar_months'][i]['return']) for n in monthly_focus] for i in range(12)]),'',
      'Returns use each month’s actual starting equity. Starting equity, ending equity and dollar PnL for every frozen book are in `calendar_months` in the results file; signal-owned months are separately labeled `months`. Realized PnL plus retained terminal net mark-to-market reconciles with all daily/calendar totals.','',
      '## Schedule, robustness and interpretation','',
      'Nominal Thursdays remain globally anchored. Entry is the exact final RTH minute OPEN, with quantity determined from the preceding completed mark. Exit is the first observed OPEN at/after one hour before the close, two nominal Thursdays later. Holidays map at/before nominal dates; November 27 maps to November 26, and December 25 maps to the December 24 early close (12:00 exit / 12:59 entry). Every nominal schedule row, phase, duration, filled/missed/delayed count and outstanding cash/gross obligation is in `cg_arrow004_schedule.csv`.','',
      'The ordinary September 4 / September 11 / September 18 illustration is retained in the results file: at the third replacement the September 11 cohort survives while the September 4 cohort is due. Pending exits retain capacity until actually observed; there is no accumulated unused-credit balance.','',
      'Both biweekly phases are reported separately, with global phase anchors. Short phase luck is substantial; patient-long phase A/B also differs sharply. Recovery selection improves DD and profit retention in both IS phases, but phase B worsens its worst day beyond the frozen ride tolerance. No better phase was chosen from confirmation. Fixed-reference-equity comparators isolate compounding; exposure-matched legacy controls are explicitly counterfactual diagnostics, not capped deployment policies.','',
      'IS leave-one-month-out and top-contributor diagnostics are fragility checks, not edited strategy books or new validation. Recovery selection changes membership substantially but its parent-relative profit increment is negative in four of six IS signal months; its frozen thesis is a smoother ride with retained profit, not uniform extra return. Equal sizing has only a small fragile gain over the same selected names. The middle-loser window, reclaim-level, quiet-recovery, persistent-participation and minute-bar recovery branches failed to establish a better long mechanism. All launched branches were closed.','',
      'Ablations limit the interpretation: OBSERVED_REC_BOTTOM8 earns $22,596.21 IS with $35,856.87 DD, showing that excluding unavailable histories explains much apparent improvement over the original parent. PATIENT_MIRROR earns $14,013.66 with $16,804.10 DD; the high-volume allowance adds only $216.22 to the patient book while increasing DD. Neither finalist claims that these isolated submechanisms have established incremental alpha. Both finalists lose their IWM-relative advantage when the strongest IS signal month is left out, and removing their top three positive symbol contributors erases positive total profit.','',
      'Within the already scored equal-dollar bottom-twenty book, recovery-full versus other ticket returns have only a 0.12 percentage-point mean within-cohort advantage and are positive in half of 22 comparable cohorts. Known-history versus unknown-history differences are much larger. These descriptive state comparisons are not randomized effects or independent significance tests; all original lifecycle treatment remains. See `cg_arrow004_pool_evidence.json` and `cg_arrow004_long_evidence_is.json`.','',
      'Descriptive full-account daily long/short correlations: '+', '.join(k+' '+('n/a' if v is None else f'{v:.3f}') for k,v in correlations.items())+'. These are not joint-capital or portfolio-diversification certification.','',
      'The $300–$500/day ambition and $200/day slate / $100/day engine references remain visible. Component improvements below those references may warrant further research; this run does not certify commercial success, executable fills, margin capacity or deployment readiness. No unrelated model or next arrow was started.','',
      '## Audit trail','',
      'The committed freeze, exact-replay proof, independent cash audits, full-field causal-feature audit, inherited-file identities, minute-risk checks and focused/full tests form separate evidence. Detailed orders, position ledgers and source summaries remain under ignored local `data/tmp/cg_arrow004`, referenced by safe paths and SHA-256 hashes. Public reports contain account aggregates, not raw vendor bars. Final command/test/public-review and push equality details are recorded in `cg_arrow004_commands.txt` and the closure checkpoint.','']
    (R/'cg_arrow004_report.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    ledger({'event':'REPORT_COMPLETE','books':len(books),'finalists':list(verdicts),'aggregate_daily_rows':len(daily),'schedule_rows':len(cohorts)})
    print('Aggregate reports complete',len(books),'books',len(daily),'daily rows')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['discovery','build']);a=p.parse_args()
    discovery() if a.command=='discovery' else build()
