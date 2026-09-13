"""IS-only shortlist, explicit priorities, and a disposition for every policy."""
from research.cg_arrow003_data import ROOT,REPO_ROOT,read,dump,stamp
from research.cg_arrow003_lab import authorize,classify,ledger


def main():
    authorize("IS")
    rows={p.stem[:-3]:read(p) for p in (ROOT/"results").glob("*_IS.json")}
    choices=[
      ("AR9_R5_LATE_COVER_PACED","balanced","R5",.05,
       "Original R5 sizing; one half-cover on a profitable late rebound in low initial participation; causal 130k new-order pacing.",
       "Simplest material balanced continuation: higher IS profit and smaller red-month loss/DD versus the same R5. The stronger full-size R4 covers are dominated by smaller original-R5 controls, so they are not forced into a balanced-R4 slot."),
      ("AR12_R5_OBSERVED_CONSERVATIVE","ride","R5",.05,
       "Conservative 7000-base R5; advancing-day votes only with observed 20-session history, original switch otherwise; late half-cover and pacing.",
       "Retains about94percent of original R5 IS profit while reducing monetary downside and gross substantially. Uses the previously tested conservative size and removes the new votes rule's sparse-history sizing increment. Useful-profit ride is the primary target, not higher raw profit."),
      ("AR11_R5_OBSERVED_VOTES_COVER","return","R5",.15,
       "Original 8300-base R5 with observed-history advancing-day votes, the same late half-cover, and causal pacing.",
       "Higher IS return than original R5 at a disclosed roughly10percent worse worst day. Only about542dollars above the simpler paced cover policy, so added complexity is a serious qualification. Retained as one return challenger, not a claim of dominance."),
      ("AR10_R4_CONSERVATIVE_COVER_PACED","ride","R4",.05,
       "Conservative 4650-base R4 participation sizing; late low-participation half-cover and causal pacing.",
       "A distinct R4 sizing/ride option: near-original R4 useful profit with smaller red-month losses, drawdown and worst day. It earns less than the R5 candidates and is retained for that explicit risk tradeoff, not to fill a quota."),
    ]
    finalists=[]
    robustness=read(REPO_ROOT/"reports/cg_arrow003_is_robustness.json")["candidates"]
    for i,(name,kind,control,tolerance,pitch,reason) in enumerate(choices,1):
        r=rows[name]
        comparison=classify(r["metrics"],rows[control]["metrics"])
        fragility=robustness[name]["comparisons"][control]
        finalists.append({"id":name,"priority":i,"control":control,"pitch":pitch,"reason":reason,
            "primary_improvement":{"kind":kind,"definition":{
                "balanced":"Profit increment at least max(100dollars,5percent of absolute control profit), at least two5percent downside improvements, no extra red month, remaining monetary regressions within5percent",
                "ride":"Retain at least85percent of same-control positive profit, with at least two5percent downside improvements and remaining monetary regressions within5percent",
                "return":"Profit increment at least max(100dollars,5percent of absolute control profit); frozen acceptable downside regression is15percent; no hard gross-exposure veto"}[kind]},
            "acceptable_tradeoff":{"monetary_downside_worsening":tolerance,"minimum_profit_retention":.85 if kind=="ride" else 1.0,
                  "gross_exposure":"Soft130k planning; report exact drift/allocation excursions, no135k cliff",
                  "data":"Conditional shared partial-action and stale-price convention; no complete-economic or deployment claim"},
            "missingness_dependency":False,"new_sparse_history_increment":"Original ret3 switch retained on missing20-session history for vote variants; ordinary cover-only variants do not change missing-history sizing",
            "secondary_comparator":"AR9_R5_LATE_COVER_PACED" if name=="AR11_R5_OBSERVED_VOTES_COVER" else None,
            "is_comparison":comparison,"is_fragility":{"positive_profit_difference_months":fragility["positive_months"],
                 "min_leave_one_month_out_profit_difference":fragility["min_leave_one_out"],
                 "increment_without_top_positive_symbol":fragility["increment_excluding_largest_positive_symbol"]}})
    controls=["PARENT","R4","R5","A4","R1","R5_CONSERVATIVE_7000","C5_R4_SIZE_CONSERVATIVE",
              "C1_R4_PREORDER","C1_R5_PREORDER"]+["MATCH_"+p["id"] for p in finalists]
    if any(n not in rows for n in controls):raise RuntimeError("Missing selected comparator")
    matches={p["id"]:{"id":"MATCH_"+p["id"],"fixed_base":rows["MATCH_"+p["id"]]["spec"]["base"],
                "method":"One IS average-exposure ratio from original control, nearest25; no OOS scaling or iterative retarget"} for p in finalists}
    selection={"timestamp":stamp(),"status":"IS shortlist; only the later committed freeze authorizes confirmation",
               "finalists":finalists,"controls":controls,"size_matches":matches,
               "mix_explanation":"Four policies: a simple balanced R5 overlay, a conservative observed-history smoother, one bounded return challenger, and a conservative R4 alternative. No five-shape sweep. Original/conservative fixed controls remain visible.",
               "absolute_economics":"Data-limited.720of724ISstale R4 position-sessions have acquisition price-range exclusions; preserving entries fixes erasure but cannot supply actual missing prices."}
    dump(REPO_ROOT/"reports/cg_arrow003_selection.json",selection)
    selected={p["id"] for p in finalists}
    specific={
      "A1_R4_ORDINAL_PARTICIPATION":"Within-batch participation rank weakened profit and did not improve the overall risk tradeoff.",
      "A2_R4_LATE_PARTICIPATION":"Late-hour volume-share signal raised exposure and worsened losses; branch closed.",
      "A3_R4_DRAWDOWN_NEW":"HWM-based new-order cuts sacrificed too much recovery profit; also fragile to stale-valuation state.",
      "A4_R5_SYMBOL_BUDGET":"Symbol allocation budget produced a mixed tradeoff without a clear edge after fixed-size comparison.",
      "A5_R4_LATE_WEAK_PART_COVER":"Promising Astra mechanism retained in later practical/conservative variants; full-size R4 result is dominated by smaller original-R5 controls.",
      "A6_R5_STALL_VOTES":"Positive observed-history increment, but64percent of total increment comes from sparse histories; refined using the original-switch fallback.",
      "A7_R4_MINUTE_LATE_COVER":"Every-minute trigger earned less with weaker DD than the checkpoint; scored support for the checkpoint anti-twitch choice.",
      "A8_R5_MINUTE_LATE_COVER":"Same granularity comparison on R5 favored checkpoint profit and DD; profitable tradeoff remains recorded.",
      "A9_R5_ADVERSE_OPEN_BOOK":"Halving new orders on open-book adversity sacrificed about44percent of original R5 profit; not a useful retained-profit smoother.",
      "A10_R4_LATE_ALL_PARTICIPATION":"Filter ablation still helped, with less profit and slightly better downside than low-state covers; shows participation is not a unique causal explanation.",
      "A11_R5_LATE_ALL_PARTICIPATION":"R5 replication of the filter ablation; useful balanced alternative, but not sufficiently distinct/materially stronger than chosen cover tradeoffs to add another finalist.",
      "A12_R5_OBSERVED_HISTORY_VOTES":"Observed-history-only votes retain1118dollars increment; used as a building block, with concentration and worst-day limits disclosed.",
      "AR1_R4_LATE_COVER_DAY7":"One neighboring start day preserved direction; no holding-day sweep or selection of the small hindsight gain.",
      "AR2_R5_LATE_WEAK_PART_COVER":"Useful unpaced precursor; the tested paced version is the practical finalist.",
      "AR3_R4_LATE_COVER_CONSERVATIVE":"Useful unpaced conservative precursor; the tested paced implementation is the finalist.",
      "AR4_R5_VOTES_PACED":"Votes plus pacing precursor; later work separates sparse-history dependency and tests the independent cover combination.",
      "AR5_R5_VOTES_LATE_COVER":"Combined gain is non-additive; prefer the practical budget and explicit sparse-history fallback for confirmation.",
      "AR6_R5_VOTES_COVER_PACED":"Higher nominal result retains a sparse-history sizing dependency; choose the observed-history return challenger instead.",
      "AR7_R4_LATE_COVER_PACED":"Profitable balanced improvement over R4, but dominated across the chosen axes by smaller original-R5 fixed controls; not forced into the finalist mix.",
      "AR8_R5_VOTES_COVER_CONSERVATIVE":"Useful smoother precursor; choose its observed-history fallback to avoid treating sparse-history sizing as new evidence.",
      "C6_BLEND_PACED":"Closely related sizing blend, not diversification; smaller original-R5 controls provide a stronger measured tradeoff.",
    }
    frontier=read(REPO_ROOT/"reports/cg_arrow003_is_frontier.json")["policies"]
    dispositions={}
    for name,r in rows.items():
        if r["spec"]["origin"]=="CONTROL":continue
        if name in selected:
            status="SHORTLISTED FOR COMMITTED FREEZE"
            reason=next(p["reason"] for p in finalists if p["id"]==name)
        elif name.startswith("C3_R5_MOMENTUM") or name=="C3_R5_TAPER_PACED":
            status="DATA-LIMITED / REJECTED AS SMOOTHING EVIDENCE"
            reason="Apparent gain comes from neutral sizing on missing volatility; observed-history smoothing loses profit. No confirmation slot."
        elif name in specific:
            status="CLOSED / NOT SELECTED"
            reason=specific[name]
        elif name.startswith("C1_"):
            status="CLOSED / ALLOCATION INFRASTRUCTURE"
            reason="Small standalone IS increment; establishes the causal order budget/share clock used in practical descendants. No independent alpha claim."
        elif name.startswith("C2_"):
            status="CLOSED / WEAKER RULE"
            reason="Median reference or multi-session participation persistence lost useful profit versus original sizing and relevant fixed controls; no window sweep."
        elif name.startswith("C3_"):
            status="CLOSED / WEAKER RULE"
            reason="Smooth penalties or the original-switch missing-history ablation did not establish a better observed-history tradeoff."
        elif name.startswith("C4_"):
            status="CLOSED / WEAKER ENTRY UPDATE"
            reason="Same-slot entry update reduced R4 profit; upgraded tickets were the main loss source. Early-close/missing-history fallback remains explicit."
        elif name.startswith("C5_"):
            status="CLOSED / PROFITABLE BUT NOT SELECTED"
            reason="Original participation-upturn overlay, its narrow neighbor, conservative form or boundary check is recorded; the late-state continuations offer more useful tradeoffs. InclusiveH10 tests slightly reduced profit and did not repair monthly downside."
        else:raise RuntimeError("Disposition missing for "+name)
        dispositions[name]={"origin":r["spec"]["origin"],"status":status,"reason":reason,
                            "control":r["spec"]["control"],"comparison":classify(r["metrics"],rows[r["spec"]["control"]]["metrics"]),
                            "dominated_by":frontier.get(name,{}).get("dominated_by",[])}
        ledger({"event":"IS_DISPOSITION","id":name,**dispositions[name]})
    dump(REPO_ROOT/"reports/cg_arrow003_dispositions.json",{"timestamp":stamp(),"policies":dispositions,
         "note":"Every opened policy has a completed IS result. A non-selected profitable or dominated policy is not silently erased or called a universal mechanism failure."})
    ledger({"event":"IS_SHORTLIST","ids":[p["id"] for p in finalists],"controls":controls,
            "new_hypotheses_closed":len(dispositions),"new_oos_exposed":False})
    print("IS shortlist:",", ".join(selected))
    print("Closed new policies:",len(dispositions),"confirmation controls:",len(controls))


if __name__=="__main__":main()
