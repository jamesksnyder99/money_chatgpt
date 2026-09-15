# CG Arrow 014 — Addendum 1: authoritative sequencing and completeness corrections

This addendum is part of `docs/CG_BUILD_ARROW_014.md` and controls where it is more specific or where the original arrow's section ordering could be read ambiguously. It is authored before any pristine-period strategy performance has been calculated.

## 1. Why this addendum exists

The original Arrow 014 correctly requires both an immutable pre-reveal strategy definition and a fail-closed final data-certification gate. However, the numbered section order can be read circularly: final corporate-action/security-identity certification may require mechanically generating the frozen strategy memberships to identify the exact material corridors, while those memberships must not be generated until the strategy/reveal definitions are frozen.

There is no permission to score outcomes early. The correct process is two separate locks followed by scoring.

## 2. Authoritative execution order

Use this exact order:

### Phase 0A — acquisition / source / calendar / universe preflight, no strategy outcomes

1. Finish and verify Arrow 013 acquisition completeness from the local immutable layer.
2. Recheck vendor authentication/provenance, session-resume state, silent-empty/error ledgers, partition integrity, August 2025 overlap authentication and required September 2025 lifecycle support.
3. Reassert the NYSE calendar, early closes, New York timezone/DST, timestamp semantics and the full-universe point-in-time eligibility/ranking-field data contract.
4. Audit whether August 2025 had ever previously been strategy-scored as a signal month. Warmup/lookback use is allowed; previously viewed strategy outcomes are not.
5. Do not calculate P&L, hit rate, horizon results, rank-one outcomes, monthly performance, drawdown or ending equity.

### LOCK 1 — immutable reveal specification freeze

Before generating the new holdout's selected memberships for any Arrow 014 model, create, commit and push:

`reports/cg_arrow014_reveal_freeze.json`

This is the immutable strategy/reveal specification. It must contain:

- exact Sep-2024-through-Aug-2025 signal cohort calendar;
- all model, horizon, sizing, allocation, substitution and account formulas;
- all metrics, mechanism checks and output schemas;
- exact Arrow 011/012 threshold/formula provenance;
- code hashes;
- available immutable acquisition/input hashes;
- an explicit declaration that no pristine-period strategy outcome has yet been calculated;
- the required future certification-gate artifact names/digests to be bound after corridor closure.

The freeze does **not** need to be rewritten later merely to insert the final certification digest. The final certification manifest instead references and hashes this immutable reveal freeze.

Once LOCK 1 is committed, the Arrow 014 strategy/reveal definitions can never change based on anything learned from the holdout.

### Phase 0B — membership generation and selected-corridor certification, still no outcomes

Only after LOCK 1:

1. Mechanically generate the frozen candidate rankings / memberships needed to determine the exact material corridors. This may reveal selected identities to the research process but must not calculate or summarize their outcomes.
2. Close the corporate-action/security-identity census using documented dated evidence, not price jumps as proof.
3. Normalize price/share-volume/held-share units and mechanically rerank when documented corrections change inputs.
4. Iterate to a fixed point so no newly selected or rank-9–20 control name introduces an unresolved material event capable of changing a scored cell.
5. Certify R4/R5 feature corridors, causal pre-order observations, H8/H9/H10 lifecycle/exit observations and any documented halt/open obligation.
6. Fail closed if any materially required observation remains unresolved. Missing evidence never triggers a manual next-rank substitution.

### LOCK 2 — final Historical Data Certification Gate

After Phase 0B and before any outcome calculation, create, commit and push the public-safe certification report/manifest required by Arrow 014.

It must:

- reference and hash the immutable LOCK-1 reveal freeze;
- bind the final certified-data/action/identity/lifecycle hashes;
- report exact completeness and exception counts;
- state that unresolved material exceptions capable of affecting a scored cell equal zero;
- state that no strategy performance had been calculated before gate opening;
- contain exactly the passing status:

`HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL`

Any other status stops Arrow 014 with **no performance**.

### Phase 1 — one-batch pristine reveal

Only after both LOCK 1 and LOCK 2 pass may any strategy outcome be calculated. Score the complete predeclared matrix in one controlled batch. Nothing is added, removed, retuned or redefined after the first outcome exists.

## 3. Additional predeclared diagnostic cell — C1 fixed-dollar H10

Add one diagnostic cell to the original Arrow 014 matrix:

17. **Rank-One 1.50x reallocation (C1) — fixed-dollar H10 — causal pre-order quantities.**

Purpose: separate the rank-one reallocation effect from equity compounding on the pristine year. This is the exact Arrow 012 C1 allocation rule, at H10 only, with the same cohort base-capital neutrality. It is a diagnostic companion to C1 equity H10, not a new multiplier or optimization dimension.

Do not add C1 fixed-dollar H8/H9 in this arrow.

The headline four-row H8/H9/H10 matrix remains unchanged; C1 fixed-dollar H10 appears in the diagnostic/control panel and in full-account economics.

## 4. Monthly reporting applies to every scored complete account

`cg_lab_monthly_account_reporting_v1` applies to **all 17 scored complete-account cells**, not only the four headline panels.

The four headline families should still receive the readable side-by-side monthly panels specified in the original arrow. The Equal-Dollar H10 control, C1 fixed-dollar H10 diagnostic, and C2/C3 H10 controls may be presented in a separate monthly appendix/panel, but none may omit any month if account economics are published.

Every monthly series must chain and reconcile to its own period-end marked account result and keep runoff/eventual economics separate.

## 5. C1 pristine decision must always include the fixed-dollar H10 diagnostic

The original section 12 phrase "fixed-dollar diagnostic if needed" is superseded. The fixed-dollar C1 H10 diagnostic is **mandatory and predeclared**.

When interpreting C1 H10, report both:

- R5 equity H10 versus C1 equity H10; and
- R5 fixed-dollar H10 versus C1 fixed-dollar H10.

This distinguishes whether any pristine C1 advantage exists in the underlying allocation itself as well as in its compounded account translation.

## 6. Freeze/gate timestamp and provenance invariant

Add the following audit invariant:

- LOCK-1 reveal-freeze commit precedes any holdout strategy-membership artifact used for Arrow 014 selected-corridor certification;
- LOCK-2 certification-gate commit precedes every holdout outcome/performance artifact;
- neither lock is modified after its protected stage begins;
- final reports record both commit SHAs and relevant artifact timestamps/hashes.

If the implementation necessarily creates a purely mechanical membership artifact while building LOCK 1 itself, it must be generated in a mode incapable of loading exit/outcome fields and must be deleted/rebuilt after the freeze; preferred implementation is to freeze formulas/calendar first and generate membership only afterward.

## 7. Everything else in the original Arrow 014 remains in force

In particular:

- pristine period = September 2024 through August 2025 inclusive;
- August 2024 warmup only;
- September 2025 lifecycle/runoff support only;
- core R4/R5 fixed H8/H9/H10 matrix;
- R5 equity H8/H9/H10;
- C1 equity H8/H9/H10 at exactly 1.50x;
- Equal-Dollar H10 control;
- C2/C3 H10 frozen falsification controls;
- all 12 calendar months;
- every pristine weekly cohort;
- mechanism-confirmation panel;
- rank-one/ranks-2–8 attribution;
- H8→H9→H10 attribution;
- drawdown anatomy;
- historical-versus-pristine exact-cell comparisons;
- complete-account economics and independent reconciliation;
- no post-reveal optimization on this holdout.
