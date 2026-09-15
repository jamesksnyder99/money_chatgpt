# CG Arrow 014 — ChatGPT audit: performance withheld

Date: 2026-09-15

Reviewed snapshot: `297663414500e169cbd4261a11d6a6c7f3509125`.

**Audit verdict: `A14_AUDIT_NOT_CLEARED — PERFORMANCE_WITHHELD`.**

The user expressly requested that no performance be presented when material defects call the run into question. This document contains no strategy performance and makes no favorable or unfavorable judgment about the strategy. The submitted certificate is not accepted as sufficient evidence for the reveal. The next assignment is `docs/CG_BUILD_ARROW_014_REPAIR_ADDENDUM_1.md`, a certification-only repair pass with a mandatory stop for ChatGPT before another strategy replay.

## Review scope and limitations

This review compared the committed Arrow 014 instructions and addenda, certification report/manifest, handoff, run provenance, and relevant source code at the snapshot above. It is a source-and-evidence audit, not an independent execution of the entire backtest. The private vendor partitions and detailed private ledgers were not available to this auditor's runtime. The executor's reconciliation/oracle assertions do not by themselves establish completeness, causal input validity, corporate-action correctness, or conformity with the written gate.

The findings below are upstream of performance. Their numerical effects have not been estimated, and the direction of any correction is not asserted.

## A14-AUD-01 — Missing sizing evidence was allowed through a gate that expressly forbids the fallback

**Authority:** `docs/CG_BUILD_ARROW_014.md`, section 3.5, requires split-consistent momentum and volume features and states: "missingness remains missing, never favorable zero/FULL state." The active protocol and `AGENTS.md` make current-arrow acceptance criteria authoritative over older implementation defaults.

**Observed:** `reports/cg_arrow014_certification_manifest.json` reports eight sizing-feature rows under `RULE_DEFINED_MISSING_SIZING_FEATURE` and treats them as nonblocking. `scripts/cg_arrow014_phase0b.py::stage_certify` constructs that classification instead of counting unavailable/incomplete feature evidence as an exception. `src/verification/r4r5_replay.py::sizing` sets an unavailable volume multiplier to 1.0 and an unavailable momentum multiplier to 1.0. An unknown leg consequently avoids that leg's down-scaling. This does not establish that every affected ticket was entirely FULL: the other leg can still reduce it.

**Why it blocks:** A legacy fallback is not proof that the input is known. The submitted gate expressly accepts a state that the active arrow expressly excludes. Retrieving a session without a usable feature does not cure that conflict.

**Required closure:** Trace each affected observation and the full required feature window. Establish legitimate inputs from source evidence where possible. Distinguish a documented zero-volume session from an unavailable price, incomplete listing history, missing data, and last-sale-ineligible prints. Do not fabricate prices, default unknown inputs to favorable states, silently omit the ticket, or substitute another security. If a required feature genuinely cannot be defined under the frozen contract, report the precise unresolved policy/data question and keep the gate closed.

## A14-AUD-02 — Gate materiality excludes the substitution pool

**Authority:** Arrow 014 sections 3.3–3.6 and Addendum 1 Phase 0B cover every candidate/control/selected dependency capable of changing any scored cell, expressly including ranks 9–20.

**Observed:** `scripts/cg_arrow014_phase0b.py::stage_certify` creates rows for `TOP8` and `CONTROL_9_20`, then narrows to `t8 = [r for r in rows if r['group'] == 'TOP8']`. The absent-observation checks, unexplained ranking/holding checks, and missing-feature/non-execution counts are subsequently computed on `t8`. Writing control rows to a private CSV is not the same as including their exceptions in the pass/fail decision. The Off-High Substitution and Combined models can trade those controls.

In the same script, `stage_rank` defines its membership hash and fixed-point comparison from `top8` alone. Ranks 9–20 can change while that check still reports a fixed point.

**Why it blocks:** The certificate's claim that every scored cell is covered is not established by the implementation. This finding does not assert that a particular substituted trade is numerically wrong; it establishes that the gate can pass without proving it is right.

**Required closure:** Build and certify the complete dependency graph of the frozen matrix, including ordered replacement candidates, their selection features, and the actual replacement lineups. Cover full feature histories, causal order inputs, execution, daily marking, all relevant horizons and delayed lifecycle obligations. Establish that unresolved eligible competitors cannot change membership. Bind all material membership/control/action/identity/input state in the fixed-point and final hashes.

## A14-AUD-03 — Non-priced observations, documented events, and execution causality are not consistently enforced

**Observed source state:** `src/verification/r4r5_data.py::summary_job` filters to regular-hours rows with positive volume and finite positive open/close. If no such row survives, its summary can have `missing=True`, `partition_resolved=True`, and positive `raw_rows`. `src/verification/r4r5_holdout.py::observation_status` turns that combination into `DOCUMENTED_NO_TRADING`.

That predicate does not independently distinguish zero trading from positive-volume prints without a last-sale-eligible price, or establish a halt, ticker change, merger, delisting, or settlement. These distinctions were explicitly required by the original data contract.

**Observed gate/report versus engine:** The final gate describes unavailable entries/exits as governed documented non-execution. But `r4r5_replay.replay` does not carry an unavailable entry forward: it records a missed/no-entry status and continues. For an unavailable exit, the carried/documented-open branches require a matching `halted()` event; without one the engine produces an `UNRESOLVED_*` status. The gate does not demonstrate that the required event evidence and exact engine branch match for each row.

**Observed causal gap:** `stage_certify` records `causal_preorder_present`, but does not make its failure a blocking condition. Separately, `r4r5_data.summarize` chooses the pre-order reference from rows before the scheduled final minute, not necessarily before the actual fallback execution. If the scheduled final minute is absent and execution falls back to the last earlier print, that same print can become both `preorder` and `exec_px`, with equal timestamps. This is a source-level counterexample to the strictly pre-fill requirement; its incidence in the submitted private ledgers must be measured before declaring them causal.

**Required closure:** Publish a private, evidence-linked row reconciliation for every nonstandard observation and all pre-order/fill pairs. Prove the timestamp of information availability is strictly before the modeled fill, including sparse sessions and early closes. Match each non-execution status to the exact authorized rule and documented facts; do not infer a security's economic lifecycle from an empty usable-price subset. Genuine unresolved cases remain blocking.

## A14-AUD-04 — The replacement gate needs enforceable provenance, not descriptive assertions

**Observed:** The handoff acknowledges that a prior gate and reveal were withdrawn after the acquisition-universe floor was mistaken for the strategy's $10–$80 floor. Correcting that implementation error is appropriate. However, the replacement certification still declares that no outcome has been calculated up to and including that gate.

`cg_arrow014_lock2.py` writes `no_outcomes_calculated=True` unconditionally. Its G12 test checks that dictionaries contain `rule` and `basis` keys; it does not prove that the named evidence covers the relevant tickets or that the engine followed the rule. `phase0b.require_lock1` logs mismatched hashes rather than failing on an unapproved mismatch. Exact calendar equality and a cell count do not establish the complete freeze is unchanged.

**Why it blocks:** A corrected implementation can still be evaluated under the original predeclared strategy, but the earlier exposure cannot be erased. A gate must also fail when evidence is absent or outside its covered dependency set, not pass because an explanatory string is present.

**Required closure:** Preserve both submitted versions and the original freeze. Record an accurate withdrawal/repair/replay chronology, an append-only exposure ledger, exact approved technical changes, and matching dependency/input/code hashes. Do not label a repaired replay as a first-ever untouched reveal. Prove the pass/fail checks with adversarial regression tests rather than certificate text alone.

## Additional mandatory checks before closure

These are targeted checks raised by the inspected implementation, not claims that each has already changed an observed result:

- The handoff describes assigning an action's effective session from the tape when its filing date text was not parsed. Obtain and cite the actual effective-date evidence for each material event; a uniquely fitting jump is corroboration, not dated authority.
- Verify action/identity coverage through the entire 20-session volume baseline and all actual lifecycle extensions, not only ranking endpoints or scheduled exits.
- The summary-cache key uses file size/mtime and a version string. Establish whether changes to source resolution, action/identity tables, calendar, and summarization logic require invalidation. Rebuild affected derived caches under a new fingerprint; do not alter immutable raw files.
- Identify any shared-engine repair that could affect the historical year. Preserve every historical artifact and report the affected scope; do not silently carry a changed implementation into an allegedly exact comparison.

## Disposition

Retain authenticated raw acquisition, documented evidence that remains valid, the original specification, and all submitted artifacts with their provenance. This is not a request to discard the dataset or change the model to obtain a preferred answer.

The repair pass must restore the written measurement and certification contract, add evidence and regression tests, and stop with **no performance** for ChatGPT audit. No parked research, new filter, horizon, sizing multiplier, cost convention, or model is authorized by this disposition. A clean repaired gate, followed by a separately cleared complete replay, is required before the results can be presented.
