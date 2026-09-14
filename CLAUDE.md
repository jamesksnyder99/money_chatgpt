# Claude Code — money_chatgpt

Read `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, and the explicitly assigned CG arrow before acting.

**Current assignment: `docs/CG_BUILD_ARROW_013.md`. Executor: Opus in Claude Code.**

Arrow 013 is a **data acquisition, authentication, normalization, and certification assignment only** for a pristine historical holdout. No strategy scoring or research is authorized.

## Frozen holdout definition

- New pristine OOS signal months: **September 2024 through August 2025 inclusive (12 months)**.
- **August 2024 is warmup only** for ranking/feature histories.
- **August 2025 is the twelfth/final OOS signal month**, not warmup. It already exists locally from the prior study and must pass provenance/overlap authentication before reuse.
- Late-August 2025 H10 lifecycle observations may use verified September 2025 data without changing August signal ownership.
- Future reveal account starts fresh at $100,000 before the first September 2024 cohort.

## Arrow 013 acquisition scope

Bulk-acquire **2024-08-01 through 2025-07-31** under the existing authorized Theta Stocks Professional entitlement, then authenticate/reconcile the already-held August 2025 block and required September 2025 lifecycle tail.

Follow the full Historical Data Certification Gate in the active arrow: immutable raw landing, normalization, validation, exact completeness inventory, point-in-time identity, documented corporate actions, split-consistent price/share-volume units, calendar/timestamp/DST checks, minute/session reconciliation, vendor-error versus market-event distinction, exception ledger, SHA-256 manifest, and fail-closed treatment of unresolved material gaps.

Use the official installed ThetaData Python SDK. Never launch Theta Terminal, change subscriptions, buy data, use options, or start sub-minute ingest. Total Theta concurrency may not exceed 8 requests across the process tree or any lower observed vendor limit.

## STRICT HOLDOUT EMBARGO

Arrow 013 may acquire and certify data, but must NOT:

- run Winner-Fade;
- emit or inspect top-8/top-20 strategy rankings;
- reveal selected names;
- score C0/C1/C2/C3;
- calculate trade P&L, hit rate, drawdown, monthly strategy returns, ending equity, rank-one outcomes, or other performance;
- tune any rule from the new period.

Generic integrity calculations needed to validate source data are permitted only when they do not surface strategy selections/outcomes.

## Authentication / credentials

Confirm `git check-ignore -v .env` before acquisition and every push. Never print, echo, serialize, stage, commit, or expose credential values. Record SDK/Python versions, query contracts, timestamps, response counts and non-secret provenance. Perform a small authenticated known-period smoke and repeat-query consistency check before bulk retrieval. Silent empty-success responses are failures, not data.

## Data integrity

Preserve raw vendor partitions immutably. Repairs belong in versioned derivatives. Do not infer corporate actions from price jumps, backfill present-day identity into historical decisions, turn missing data into zero/favorable values, use stale prices as verified executions, treat vendor failure as a halt, or substitute another security because data are missing.

The full point-in-time universe/ranking field must be complete enough that a future top-eight cannot benefit from a competitor silently disappearing. If broad minute retrieval is deferred, freeze a deterministic selected-name retrieval/certification procedure before the future reveal; the holdout remains unscored until all required selected-name execution/lifecycle observations are certified.

## Calendar

Permanent rule remains: nominal Wednesday signal; if closed, roll backward to the most recent exchange session; entry is the first valid exchange session after the signal; Hn counts exchange sessions after actual fill. Preserve early-close and New York DST handling.

## Public/private safety

Work only in `C:\Users\james\money_chatgpt`; never access `C:\Users\james\Money`. The GitHub repo is public. Raw vendor data, detailed symbol/session inventories and proprietary files stay in ignored `data/` / `handoff/outgoing/`. Public outputs may contain safe aggregate counts, hashes, schemas, exception totals and certification state, but no future selected symbols or performance.

Preserve all Arrow 001–012 artifacts unchanged. Completed research checkpoint before Arrow 013 is `3a330fe9aca8b29f475845850d9823342b13d238`.

Arrow 013 must end with exactly one certification status from its brief, state plainly that **NO STRATEGY PERFORMANCE WAS SCORED OR REVEALED**, commit/push reviewed public-safe outputs, verify remote equality, report private deliverables/resume commands, and stop for ChatGPT audit. Do not begin the pristine reveal arrow.