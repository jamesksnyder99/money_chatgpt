# CG Arrow 006 — Opus: complete R4/R5 data repair, verify baselines, then run H1–H10

## Mission

**Executor: Opus in Claude Code.** This is a bounded engineering/forensic continuation of Arrow 005, not a new strategy-discovery run. The user has now placed a local `.env` in `C:\Users\james\money_chatgpt` containing ThetaData credentials so the missing historical observations can be retrieved. The objective is to finish the historical-economics verification of the unchanged PARENT / R4 / R5 H10 controls, regenerate the user’s trade/cohort CSVs from the repaired substrate, and then run the already-authorized H1–H10 holding-period census.

Do not presume either success or failure. Repair the evidence, not the strategy.

Work only in `C:\Users\james\money_chatgpt`, remote `jamesksnyder99/money_chatgpt`. Never access `C:\Users\james\Money`. Do not read, echo, print, log, commit, or expose credential values. Before any work and before every push, verify `.env` is ignored (`git check-ignore .env`) and absent from staged content. No live trades, account/subscription changes, options, or unrelated research. Stop after Arrow 006; do not invent Arrow 007.

## Wall clock

**Hard maximum: 180 elapsed minutes including acquisition, reconstruction, horizon study, tests, reports, commit and push.** Expected path if vendor access and reconstruction are clean: roughly **90–150 minutes**. The bottleneck is expected to be ThetaData retrieval plus rebuilding the incomplete June–August ranking field, not CPU scoring.

No automatic overtime. At minute 150 decide whether clean scientific closure fits. If an external/vendor blocker prevents completion, deliver an exact resumable checkpoint and unresolved evidence; do not weaken the verification gate or run a surviving-subset horizon study merely to finish.

## Starting evidence and required reading

Pull `origin/main` with `git pull --ff-only origin main`, preserving local `.env` and any legitimate untracked local vendor data. Starting public checkpoint is the latest main containing Arrow 005 partial verification (`f46077587d059c6c31edc503b198eb9774949d99` or its descendant after this arrow commit).

Read selectively:

- `CLAUDE.md`, `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, this arrow.
- `reports/cg_arrow005_verification.md`, `cg_arrow005_file_changes.md`, `cg_arrow005_manifest.json`, `cg_arrow005_commands.txt`, `cg_arrow005_corporate_actions.json`, `cg_arrow005_horizon_freeze.json`.
- `src/verification/r4r5_{data,replay,acquire,export,oracle}.py`, `scripts/cg_arrow005_run.py`, `tests/test_cg_arrow005.py`.
- Relevant Arrow 003/004 baseline and coverage reports only as needed.

Preserve all Arrow 003/004/005 artifacts as historical evidence. Do not rewrite old reports to match repaired results.

## Existing Arrow 005 checkpoint — facts to continue from

Arrow 005 established:

- 416 intended slots per family across 52 Wednesday cohorts.
- 372 slots per family currently have both scheduled H10 endpoint prices locally.
- 37 H10 exits per family are unresolved locally; 7 intended entries per family lack the required final-minute observation.
- 403 required selected-trade symbol-sessions were never previously requested and 18 need partial/sparse review, grouped into 118 request windows.
- 13 June–August 2026 cohorts were ranked from a field truncated around the later `$50` acquisition ceiling although the strategy rule permits `$10–$80`.
- The inherited common-stock roster contains Nasdaq test issues; `ZVZZT` was selected twice and must not remain in a corrected tradable universe.
- NVA had a previously missing issuer-documented 5-for-1 ADS split effective 2025-10-29; BNAI had a documented 1-for-10 reverse split effective 2025-12-12. The Arrow 005 action file is the current partial action reference, not a complete universe census.
- Arrow 005’s H1–H10 real-data gate remained `NOT_RUN_DATA_GATE`; no real H1–H9 OOS cells were scored.
- The detailed local CSV framework already exists under `handoff/outgoing/cg_arrow005/`.

Do not treat Arrow 005’s 372-trade known-part subtotals as complete model results or bounds.

## Phase 1 — credential and end-to-end acquisition proof

First, prove the new local credential setup safely:

1. `git check-ignore .env` must succeed.
2. Use the existing official SDK client only; never print credential values.
3. Run the existing pilot against at least:
   - SNDK on 2025-09-25 (known missing scheduled exit case),
   - DNTH on 2026-04-02 (known missing scheduled exit case),
   - one ordinary already-known control day.
4. Record only auth mode, request status, row count, schema/validation status and elapsed time.

### Mandatory wiring repair before bulk retrieval

Arrow 005 currently writes authenticated downloads under `data/verification/r4r5/v1/acquisition/raw/`, while the replay loader gives precedence to `data/verification/r4r5/v1/validated/`. Do **not** simply rerun `--acquire` and assume the replay sees the new data.

Implement and test the complete path:

**authenticated raw request → immutable raw response → normalize/validate → split by trading session → write verified date/symbol parquet under the repair/validated layer → invalidate/rebuild affected summaries → replay consumes the repaired observation.**

Required end-to-end proof: one previously unresolved case (prefer SNDK) must move from unresolved to a scheduled priced endpoint after retrieval, while its untouched historical selection remains unchanged in the R1 replay. Test cache invalidation explicitly.

Raw acquired data remain local/ignored. Never overwrite `data/full/` or `data/virgin/`.

## Phase 2 — complete selected-trade lifecycle coverage

Use the Arrow 005 manifest as the starting request set, but regenerate it after the wiring fix and resolve every observation required by the PARENT/R4/R5 R1 ledgers:

- feature lookbacks needed for verification,
- intended entry session/final-minute observation,
- intervening marks needed for daily/account and borrow scenarios,
- exact scheduled H10 exit,
- August-signal runoff through the last required September 2026 H10 exits.

Eligibility after entry must never stop lifecycle acquisition. Retrieve positions even if later price is above $80/$50 or below the entry floor.

For every requested symbol-session classify the terminal source status (`RETRIEVED_CHECKED`, genuine documented no-trading/event, unresolved vendor response, etc.). Zero rows are not automatically success. Distinguish sparse legitimate trading from an omitted request. Validate calendar/timezone, ordering, duplicate/conflicting timestamps, finite/positive prices, OHLC consistency, nonnegative volume and expected session bounds. Do not require 390 positive-volume bars for a valid thin stock.

No trade with an unresolved scheduled endpoint may enter a “verified complete-model total.” A genuine market halt/delisting/event may require a documented causal order treatment; a missing local file does not.

## Phase 3 — repair the point-in-time tradable universe and ranking field

This is separate from recovering exits and is mandatory before calling R2 complete.

### Test/security issue cleanup

Build a point-in-time security-identity rule that excludes documented Nasdaq/test issues such as ZVZZT from the tradable common-stock universe. Preserve the old selection in R1 for forensic comparison, but corrected R2 must rerank without test issues. Do not remove any real security because of its outcome.

### `$50–$80` candidate restoration

For the 13 June–August cohorts where local acquisition truncated the intended `$10–$80` rule, acquire/reconstruct the missing candidate field and the causal 15-session/feature histories needed to rank all rule-eligible names. Do not infer “same top eight” from the old cached field. Rebuild the eligible field from point-in-time source data under the unchanged common-stock, ETP exclusion, prior-close `$10–$80`, prior-dollar-volume `>= $10M` rules.

Acquire only the bounded data needed to certify these cohorts and any newly competing/selected names. No arbitrary ticker cap. If the full field cannot be reconstructed from entitled data, report the exact unresolved cohort/symbol scope and keep R2 unverified.

### Rank and feature reconciliation

For every cohort export:

- old top eight,
- corrected top eight,
- field sizes,
- changed membership,
- changed ranks,
- changed R4 volume ratio / R5 ret3 if any,
- changed sizing tier and reason.

No strategy tuning follows membership changes.

## Phase 4 — corporate actions and security identity

Use issuer/SEC/authoritative security-reference evidence where available. The current Arrow 005 action file is a starting point, not certification of the full corrected ranking field.

At minimum:

- preserve the ten currently documented events unless contradicted by stronger evidence;
- resolve remaining selected-name action/identity flags that materially affect entry, exit, quantity or ranking units;
- extend event/security checks to newly added ranking competitors or newly selected R2 names whose large discontinuities or identity require review;
- never infer a split merely from a large price move;
- preserve raw contemporaneous trade prices and transform historical comparison prices/volumes/shares only from documented dated events;
- handle symbol changes, mergers/delistings, fractional share/cash-in-lieu obligations and known distributions explicitly where they affect the test; unknown amounts remain null/status, not verified zero.

Documented real market crashes/spikes are strategy outcomes, not defects to remove.

## Phase 5 — lock the baseline reconstructions

The strategy definitions are frozen. No reserve names, new signals, stops, partial covers, leverage changes or new sizing rules.

### Families

- **PARENT:** original equal-dollar `$4,000` tickets.
- **R4:** `$5,150` base; multiply by `0.5` iff signal-session RTH volume is above the arithmetic mean of the preceding 20 RTH sessions. Equality is full size.
- **R5:** `$8,300` base; independently multiply by `0.5` for positive 3-session return and `0.5` for the same above-mean volume condition; tiers `$8,300 / $4,150 / $2,075`.

Selection remains Wednesday top eight by 15-session return under the unchanged entry universe. Preserve the original late-RTH/H10 clock and historical final-minute CLOSE execution reference for the primary legacy-compatible comparison; do not substitute Arrow 004’s OPEN/Thursday-two-week convention.

### R1 — fixed historical decisions

Keep the previously intended names, recorded feature decisions and intended sizing; use repaired entry/exit observations and documented action quantities. R1 answers: **what did the historically intended trades imply once observations/actions are repaired?**

### R2 — unchanged rules on complete repaired inputs

Rebuild the eligible field, rankings, features, top eight, sizing and lifecycle from corrected as-of data. R2 answers: **what would the unchanged algorithm have selected with complete intended inputs?**

Do not collapse R1 and R2 into one number. Publish a deterministic old→R1→R2 waterfall: restored entries/exits, action/unit repairs, universe/test issue changes, ranking membership changes, feature/sizing changes, and any execution-quantity convention bridge.

### Quantity/execution convention

Keep the historical fill-close quantity convention as the primary legacy-compatible audit and label its causality limitation. Preserve the Arrow 005 causal pre-order quantity panel as a separately named bridge; do not silently switch clocks or quantities based on which result is better.

## Phase 6 — baseline verification release gate and user CSVs

Before any real H1–H10 scoring, require:

- every valid R2 intended entry either priced or supported by a documented causal non-execution/event treatment;
- every H10 endpoint priced or supported by documented event treatment;
- no unexplained test-security/identity or material action issue in selected R2 names;
- corrected ranking field certified for all 52 cohorts;
- independent oracle reconciles trade, cohort and account arithmetic;
- stale carried marks excluded from completed verified trade totals;
- exact unresolved count published (target zero for material selected endpoints).

Loan/dividend/locate history may remain scenario-only if genuinely unavailable; that does not block price/action arithmetic or the explicitly conditional model-cost horizon study, but it blocks claims of actual executable historical net profit.

Regenerate local/private CSVs under `handoff/outgoing/cg_arrow006/` (or clearly versioned Arrow 006 paths):

1. `r4r5_verified_trades.csv` — canonical tidy ledger, one row per cohort/security/replay with nulls/status for anything not verified.
2. `r4r5_verified_cohort_audit.csv` — eight intended slot rows followed by `COHORT_SUBTOTAL`, plus typed signal-month / split / period totals; unresolved subtotals cannot be called verified.
3. `r4r5_cohort_matrix.csv` — compact wide cohort presentation if useful.
4. `r4r5_trade_exceptions.csv` — initial vs final exception status for every intended slot.
5. `r4r5_daily_account.csv` — cash, liabilities, realized/unrealized modeled PnL, fresh/stale/overdue inventory and calendar equity.

The user specifically wants auditable entry and exit prices for every cohort of eight with per-name PnL and natural subtotals. Preserve full precision internally and currency rounding in presentation. Public GitHub receives only safe aggregates, schemas and hashes, not detailed proprietary market data.

## Phase 7 — H1–H10 horizon census (only if baseline gate is OPEN)

Authorized cells: **3 frozen families × 10 horizons = 30**.

Hn = n exchange sessions after fill; fill day = H0. Within each family use the SAME verified R2 entries, initial shares, entry observation and entry costs for all H1…H10 cells. Only scheduled exit age changes.

Rules:

- same late-RTH final-minute CLOSE convention as verified H10;
- no replacement entries, reinvestment, compounding or exposure normalization when short horizons free cash;
- no changed schedule, stops, partial covers, state-dependent exits, sizing-tier-specific horizons or new filters;
- acquire/verify every H1…H10 endpoint for every valid R2 trade before comparing horizons;
- no omission-based winner from a smaller surviving sample;
- documented market events handled consistently at every horizon.

### IS/OOS discipline

Signal-month split stays:

- IS: 2025-09, 2025-11, 2026-01, 2026-03, 2026-05, 2026-07.
- OOS internal confirmation: 2025-10, 2025-12, 2026-02, 2026-04, 2026-06, 2026-08.

These OOS months have already been observed historically and are not pristine. Still preserve procedure:

1. Score all 30 IS cells after baseline repair.
2. Before H1–H9 OOS, commit/publish the full horizon rules, repaired R2 entry-ledger hash, data/code identities and any preferred IS horizon(s)/claim. Choosing none is valid.
3. Reveal all 30 OOS cells once in one batch.
4. No post-reveal parameter change or horizon switch presented as confirmed.

H10 must reproduce the locked R2 H10 baseline exactly.

### Horizon outputs

For every family/horizon and IS/OOS/ALL:

- intended/filled/completed trades; wins/losses/flats; hit rate;
- average winner, average loser, payoff ratio, profit factor;
- gross and inherited modeled net PnL;
- double-spread and 0/10/30% annualized short-borrow scenarios by actual calendar holding days;
- named $/session denominator;
- maximum continuous DD dollars/percent, worst day, red calendar-month count/loss sum, worst/median month;
- average/peak gross, exposure-dollar-days, turnover, utilization/headroom descriptors;
- R4/R5 sizing-tier contributions;
- closed versus open/runoff totals.

Also publish SAME-TRADE incremental economics `H1→H2 … H9→H10`, separating price movement from additional holding cost assumptions, plus an aggregate holding-age H0…H10 curve. Do not describe ten correlated horizons as ten independent discoveries.

Generate local:

- `r4r5_horizon_trade_paths.csv` (wide H01…H10 endpoint/PnL columns and/or tidy companion),
- `r4r5_horizon_summary.csv`.

Public safe summary: `reports/cg_arrow006_horizons.csv` and narrative/report artifacts.

## Phase 8 — tests, reporting and closure

Add focused regression/integration tests for:

- `.env` ignored and secrets absent from public/staged material;
- authenticated pilot without secret output;
- raw→validated→cache→replay end-to-end repair;
- empty response never equals coverage;
- beyond-band held-position acquisition;
- June–August `$50–$80` ranking restoration;
- documented test-symbol exclusion from corrected R2, while R1 preserves forensic historical selection;
- event price/share/volume neutrality;
- no future-exit-dependent entry;
- H10 baseline identity;
- same entries/shares across all horizons;
- independent PnL/oracle and cohort subtotal conservation;
- closed/open win counts and no stale mark certified as an exit;
- one-batch horizon OOS gate;
- raw vendor and detailed private CSV exclusion from Git.

Run the full `tests/` suite with temp/cache inside ignored lab paths.

Public deliverables:

- `reports/cg_arrow006_verification.md`
- `reports/cg_arrow006_file_changes.md`
- `reports/cg_arrow006_manifest.json`
- `reports/cg_arrow006_commands.txt`
- `reports/cg_arrow006_baseline_results.json/csv` or equivalent safe aggregate
- `reports/cg_arrow006_horizon_freeze.json` and horizon outputs if gate opens; otherwise explicit NOT_RUN_DATA_GATE with blockers.

Report exact acquisition counts/bytes/statuses, ranking-field reconstruction counts, R1/R2 membership changes, action repairs, verified/unresolved endpoint counts, old→new economics, tests, local CSV paths/hashes and final git SHA.

Inspect staged PATHS AND CONTENT before committing. No `.env`, raw parquet, credentials, detailed vendor observations, caches, or private trade CSVs in the public repository. Commit safe code/tests/reports, push to `origin/main`, verify remote equality and stop. No background jobs after handoff.

## Time guidance

Suggested—not mandatory—allocation inside 180 minutes:

- 0–15: pull/read, `.env` ignore check, auth pilot, end-to-end repair proof.
- 15–75: selected-trade acquisition, validated data wiring, action/identity fixes.
- 45–105 (overlap where safe): `$50–$80` field reconstruction and complete R2 ranking/features.
- 90–120: baseline R1/R2 replay, oracle, CSVs, baseline gate/freeze.
- 120–155: H1–H10 IS, predeclare/freeze, one OOS batch, ALL replay.
- 155–180: reports, full tests, safety review, commit/push.

If reconstruction consumes the budget, **verification wins over horizons**. A complete verified baseline with `HORIZON_NOT_RUN_DATA_GATE/TIME_GATE` is preferable to an incomplete substrate plus attractive H1–H10 numbers.
