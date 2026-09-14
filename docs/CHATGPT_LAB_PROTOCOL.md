# money_chatgpt — research and verification protocol

This is an independent laboratory seeded from `jamesksnyder99/money`. Source provenance is in `SOURCE_MONEY_COMMIT.txt`; it is not permission to access the original local repository.

## Roles and workflow

ChatGPT is research director and auditor. It publishes detailed GitHub arrows and reviews resulting code, evidence and economics. The execution agent is named by the active arrow. **For CG Arrow 013 the executor is Opus in Claude Code.**

1. Pull current main with `git pull --ff-only origin main` without overwriting legitimate local work; confirm root/remote.
2. Read `AGENTS.md`, `docs/SUCCESS.md`, `CLAUDE.md`, and the active arrow.
3. Execute only the active scope, preserve historical evidence, test, inspect public safety, commit/push safe code and reports.
4. Verify remote equality, identify local private deliverables and unresolved evidence, then stop for audit. Do not invent the next arrow or run concurrent writers in one worktree.

## Active authority — CG Arrow 013

The user has authorized **acquisition, authentication, normalization, and certification of a new pristine historical holdout only**. Exact scope: `docs/CG_BUILD_ARROW_013.md`.

Frozen period definition:

- warmup only: **August 2024**;
- pristine OOS signal months: **September 2024 through August 2025 inclusive**;
- August 2025 is the twelfth/final OOS signal month, even though it already exists locally from the prior study's warmup;
- late-August 2025 H10 lifecycle may use verified September 2025 observations while preserving August signal ownership;
- future reveal account starts at $100,000 before the first September 2024 cohort.

Arrow 013 bulk-acquires 2024-08-01 through 2025-07-31, authenticates/reconciles the existing August 2025 block, and verifies the required September 2025 lifecycle tail. It does **not** run Winner-Fade or any challenger.

### Strict holdout embargo

Do not score, inspect, summarize, rank for strategy purposes, or learn outcomes from the new holdout. No top-eight/top-twenty strategy output, selected-name reveal, C0/C1/C2/C3 P&L, hit rate, drawdown, monthly account return, ending equity, rank-one outcome, or rule tuning is permitted. Generic validation calculations needed to prove source integrity are allowed only when they do not reveal strategy selections/outcomes.

The new year is reserved for a later one-batch reveal after certification.

## Isolation and public safety

Never access `C:\Users\james\Money`. Use independent lab inputs and acquisitions expressly authorized by the active arrow. No junctions/symlinks/hard links back to Money.

The GitHub repository is public. Never publish `.env`, credentials, raw vendor bars/quotes, proprietary detailed symbol/session observations, private account identifiers or local caches. Authorized local ThetaData credentials may be used within active scope; confirm `.env` is ignored before work/push. Store detailed files under ignored `handoff/outgoing/` / `data/`; public reports carry safe aggregates/hashes/schemas only.

## Historical Data Certification Gate

No strategy/model/parameter/OOS scoring may occur on uncertified data.

Required sequence:

**retrieval → immutable raw landing → normalization → validation → certification → testing later**.

Raw vendor data are immutable. Any repair creates a versioned derivative and retains provenance.

Certification must cover every observation capable of affecting eligibility, selection, ranking, sizing, entry, exit, valuation, corporate-action units, or risk under the future frozen reveal.

At minimum:

- authoritative exchange calendar, holidays, early closes, New York timezone and DST;
- timestamp uniqueness/order and expected RTH minute-count logic;
- missing/stale bar inventory;
- OHLC/volume sanity and source typing;
- full point-in-time universe/ranking-field completeness, not merely selected names;
- point-in-time security identity/type and test/ETP exclusions;
- documented corporate actions, identity changes and precise price/share/volume normalization;
- split-consistent volume corridors for R5's signal-day/prior-20 arithmetic-mean rule;
- distinction between vendor failure, no-data, true zero-volume, halt and suspension;
- exact exception inventory with stable IDs and fail-closed status;
- SHA-256 provenance manifest covering source/certification artifacts.

Do not infer splits from jumps, use present-day identity as historical fact, fill missing features with zero/favorable values, substitute another name because data are missing, rescue with stale prices, or omit a troublesome observation based on future knowledge.

If broad minute retrieval is not practical before strategy selection, Arrow 013 may certify the complete full-universe pre-entry/ranking layer and freeze a deterministic post-selection minute/lifecycle retrieval procedure. Missing execution/lifecycle data for a future selected name fail closed; they never trigger next-name substitution.

## Authentication / source integrity

Use the official installed ThetaData Python SDK and existing Stocks Professional entitlement. Do not launch Theta Terminal, change subscription/account settings, buy data, use options or start sub-minute ingest.

Before bulk acquisition:

- confirm `.env` is ignored;
- never print/log secrets;
- record SDK/Python/query contract and non-secret provenance;
- run a small authenticated known-period smoke;
- repeat a deterministic query to check semantic reproducibility;
- treat silent empty-success responses as failures;
- stop if entitlement or response semantics are ambiguous.

Total Theta concurrency may not exceed 8 requests across the process tree or a lower observed vendor limit.

## August 2025 overlap authentication

Existing August 2025 data are not trusted automatically. Compare a deterministic stratified vendor re-query sample against the held source across early/mid/late month, representative securities and the daily/minute forms used by the lab. Any unexplained discrepancy suggesting source revision, stale cache, timezone/unit mismatch, or normalization drift triggers full August 2025 re-retrieval into a new immutable audit partition. Never overwrite the old partition.

## Calendar policy

Nominal weekly signal anchor is Wednesday. If Wednesday is closed, roll backward to the most recent exchange session. Entry is the first exchange session after the signal. Do not skip a week solely because Wednesday is a holiday. Hn is n exchange sessions after actual fill. Preserve early-close conventions and actual session schedules.

## Scientific practice

- Preserve prior arrows and raw source trees as historical evidence; repairs are versioned and reconciled.
- A positive result never substitutes for data verification.
- Unknown data quality is neither proof of success nor proof of failure.
- An unresolved material action/identity/coverage defect blocks affected certification.
- Never hand-replace a suspicious or missing security with the next rank because of a data problem.
- Data integrity and research contamination are separate locks: certified data may still be an uninspected holdout, and Arrow 013 must preserve that status.
- Outcome/resource limits never justify false completion.

## Monthly account reporting standard

Frozen in Arrow 009 as `cg_lab_monthly_account_reporting_v1`, implemented in `src/verification/r4r5_monthly.py`.

This remains mandatory whenever a later arrow publishes strategy economics. Arrow 013 publishes **no strategy economics**, so it should not create monthly strategy-account rows for the new holdout.

## Headline cost convention

For later model evaluation, follow the Arrow 008/010 declared commission/spread convention and the standing concise footnote. Arrow 013 is a data-certification job and should not create new performance-cost scenarios.

## Naming

Use human-readable names first in future strategy reports. Preserve legacy IDs for provenance. Arrow 013 should mostly use data/certification terminology because no model is being scored.

Lab assignments live in `docs/CG_BUILD_ARROW_XXX.md`; historical arrows remain evidence, not competing current instructions.