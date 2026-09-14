# money_chatgpt economic and evaluation policy

## Active mandate — CG Arrow 013, September 14, 2026

**Opus in Claude Code** is assigned acquisition, authentication, normalization, and certification of the new pristine historical holdout. Exact scope: `docs/CG_BUILD_ARROW_013.md`.

No strategy scoring or optimization is authorized in Arrow 013.

## Frozen new OOS definition

The new pristine OOS period is:

**September 2024 through August 2025 inclusive — 12 signal months.**

- **August 2024 is warmup only** for the first September 2024 ranking/feature histories.
- **August 2025 is the final OOS signal month**, not warmup. Existing August 2025 data may be reused only after provenance/overlap authentication.
- Late-August 2025 H10 lifecycle observations may use verified September 2025 data while retaining August signal ownership.
- The future holdout account starts at $100,000 before the first September 2024 cohort.

Arrow 013 newly bulk-acquires **2024-08-01 through 2025-07-31**, authenticates/reconciles existing August 2025, and verifies any required September 2025 lifecycle tail.

## Success definition for Arrow 013

Success means a believable, reproducible data foundation—not a good trading result.

The run must:

1. authenticate the vendor/SDK/entitlement without exposing credentials;
2. land raw data immutably with hashes and provenance;
3. validate calendar, timestamps, timezone/DST, bar counts, OHLC/volume integrity and missingness;
4. establish complete point-in-time universe/ranking-field coverage sufficient for the frozen future rules;
5. validate point-in-time security identity/type and documented corporate-action normalization;
6. distinguish vendor failures from market events;
7. validate split-consistent volume corridors required by R5;
8. authenticate/reconcile the existing August 2025 overlap and escalate to full re-retrieval if discrepancies appear;
9. create exact exception/completeness inventories and fail closed on unresolved material gaps;
10. preserve the Sep 2024–Aug 2025 performance block as uninspected.

The final status must be one of the Arrow 013 certification statuses. `HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL` is permitted only if the declared scope genuinely satisfies the Historical Data Certification Gate.

## Strict contamination rule

Arrow 013 must NOT:

- run Winner-Fade;
- emit top-eight/top-twenty strategy rankings or selected names;
- calculate C0/C1/C2/C3 P&L;
- calculate hit rate, profit factor, drawdown, rank-one outcomes, monthly strategy returns, or ending equity;
- tune strategy rules from the new period.

Generic calculations used strictly to validate source/unit completeness are permitted only when they do not surface strategy selections or outcomes.

## Historical Data Certification policy

No future holdout scoring until data are certified.

Required sequence:

**retrieval → immutable raw landing → normalization → validation → certification → strategy reveal later**.

Raw vendor data remain immutable. Repairs create versioned derivatives and preserve the source evidence.

Certification covers all observations capable of changing eligibility, selection, ranking, sizing, entry, exit, valuation, action units, or risk. It must not silently omit competitors from the ranking field because source data are missing.

Unresolved material corporate actions, identity ambiguity, incomplete required histories, unexplained vendor discrepancies, or missing selected-name execution/lifecycle observations block affected certification.

Never:

- infer a split factor as fact;
- treat missing volume/price as zero or favorable;
- use stale prices as verified execution;
- interpret vendor failure as a halt;
- substitute the next rank because data are missing;
- use current security metadata as historical fact without point-in-time support;
- pick a repair convention because it improves performance.

## Authentication and source policy

Use the official installed ThetaData Python SDK and the existing authorized Stocks Professional entitlement. No subscription/account changes, no new paid data, no options, no sub-minute program, no Theta Terminal.

Credentials remain in ignored `.env`; never print, log, serialize, stage, or commit them. Record only non-secret SDK/query/provenance information.

Total Theta concurrency is capped at 8 requests across the process tree or any lower observed vendor limit.

## Calendar and action policy

Nominal Wednesday signal; roll backward to the most recent exchange session when Wednesday is closed. Entry is the first exchange session after the signal. Hn counts exchange sessions after fill. Preserve actual early closes and New York DST.

Corporate-action handling must use documented dated factors/identity evidence. Earlier prices/share volume/held shares are normalized under the frozen convention only when supported by documented events. Non-comparable reorganizations remain explicit exceptions.

## Existing model hierarchy remains frozen

Arrow 012 is the latest completed research result. The incumbent remains the Momentum+Volume-Sized Winner-Fade Short with Arrow 010 equity scaling; C1 rank-one 1.50x reallocation is the strongest historical challenger, while C2/C3 remain recorded challenger evidence. None of these may be scored on the new year until Arrow 013 certification is complete and a separate reveal arrow is authorized.

Do not reinterpret or overwrite Arrow 001–012 results during data acquisition.

## Monthly reporting

`cg_lab_monthly_account_reporting_v1` remains mandatory for later strategy-economics arrows. Arrow 013 publishes no strategy economics and therefore must not create monthly strategy account results for Sep 2024–Aug 2025.

## Delivery

Public GitHub receives only safe aggregate coverage/certification reports, schemas, hashes, code and tests. Raw vendor data, detailed symbol/session inventories, authentication details, and private exception records stay in ignored `data/` and `handoff/outgoing/cg_arrow013/`.

Commit/push reviewed public-safe outputs, verify remote equality, report exact private deliverables and deterministic resume commands, then stop for ChatGPT audit. Do not begin the pristine reveal.