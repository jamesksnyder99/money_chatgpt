"""Bounded IS challenges to the interpretation of the promising cover rule."""
from dataclasses import asdict,replace
from research.cg_arrow003_data import REPO_ROOT,dump
from research.cg_arrow003_lab import CONTROLS,run_is,ledger


def main():
    specs=[
        replace(CONTROLS[2],id="A9_R5_ADVERSE_OPEN_BOOK",origin="ASTRA",state="adverse_inventory",pacing=True,
                mechanism="Halve new R5 orders when aggregate existing short price MTM is negative at the pre-order clock; causal130k pacing, no high-water-mark hysteresis or forced liquidation. Tests whether current open-book adversity is more useful than the weak drawdown rule."),
        replace(CONTROLS[1],id="A10_R4_LATE_ALL_PARTICIPATION",origin="ASTRA",cover="earned_rebound",min_hold=6,
                mechanism="A5 ablation: retain one earned-ATR/upturn half-cover from day6 but remove the low-initial-volume restriction. Tests whether the useful effect is simply later price management rather than participation-specific."),
        replace(CONTROLS[1],id="C5_R4_DAY6_UPTURN",origin="DIRECTED",cover="earned_fade",min_hold=6,
                mechanism="C5 attribution challenge: move the original earned-fade/high-current-participation checkpoint rule from day3 to day6, keeping its other clauses. Separates holding age from the independently proposed low-entry-participation rule; one predeclared ablation, not a holding-day sweep."),
    ]
    dump(REPO_ROOT/"reports/cg_arrow003_ablation_specs.json",[asdict(s) for s in specs])
    ledger({"event":"CONTINUATION_RATIONALE","phase":"IS mechanism falsification",
            "notes":"Challenge causal interpretation before finalist freeze: current open-book state versus drawdown hysteresis, remove initial participation restriction, and isolate later management age in the original C5 rule. No OOS results or named bad months used."})
    run_is(specs,workers=8)


if __name__=="__main__":main()
