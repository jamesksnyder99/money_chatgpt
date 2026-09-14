# CG Build Arrow 013 — Acquire and Certify the Pristine Sep 2024–Aug 2025 Holdout

Executor: **Opus in Claude Code**. Research director/auditor: ChatGPT.

Authorized September 14, 2026 after Arrow 012.

This is a **data acquisition, authentication, normalization, and certification arrow only**. It must NOT score Winner-Fade, reveal selections, calculate strategy P&L, compare C0/C1/C2/C3, inspect rank-one outcomes, or otherwise consume the new holdout.

---

# 1. Frozen holdout definition — agree before touching data

The new pristine out-of-sample test period is:

**SIGNAL MONTHS: September 2024 through August 2025 inclusive — 12 consecutive calendar months.**

Clarification:

- **August 2024 is warmup only.** It supplies enough prior sessions for the first September 2024 signals to have the frozen ranking and 20-session feature histories.
- **September 2024 through August 2025 are the 12 OOS signal months.** August 2025 is NOT merely warmup in this new study; it is the twelfth and final OOS signal month.
- The repository already holds August 2025 data because it was warmup for the Sep 2025–Aug 2026 study. Arrow 013 should reuse that existing August 2025 data only after it passes overlap/provenance/integrity checks described below.
- Late-August 2025 H10 positions may require September 2025 observations for lifecycle/valuation. Existing September 2025 data may be used later for those lifecycle observations only. The signal-month ownership remains August 2025.
- The account for the future holdout reveal will start fresh at **$100,000** before the first September 2024 cohort. August 2024 creates no inherited positions; it is feature/ranking warmup only.
- Preserve the permanent calendar convention: nominal Wednesday signal; if Wednesday is closed, roll backward to the most recent exchange session; entry is the first valid exchange session after the signal; H10 means ten exchange sessions after fill. Arrow 013 may build and certify the calendar, but may not rank names or score outcomes.

Create and commit a public-safe `reports/cg_arrow013_holdout_definition.json` early in the run containing these exact boundaries and a statement that no performance/scoring is authorized. Do not later alter the definition based on what the data look like.

---

# 2. Workspace and strict isolation

Work only in:

`C:\Users\james\money_chatgpt`

Remote: `jamesksnyder99/money_chatgpt`.

Never access `C:\Users\james\Money`.

Read `AGENTS.md`, `CLAUDE.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, this arrow, the Arrow 008 certification materials, Arrow 010/012 manifests as needed for data contracts, and the existing acquisition/normalization code before acting.

The completed research checkpoint when this arrow was authored is Arrow 012 commit:

`3a330fe9aca8b29f475845850d9823342b13d238`

Preserve all Arrow 001–012 evidence unchanged.

The GitHub repository is public. Raw vendor data, detailed symbol/session inventories, credentials, private candidate/security lists, and proprietary data stay in ignored local paths. Public outputs contain safe counts, hashes, schemas, provenance, and certification status only.

---

# 3. HOLDOUT EMBARGO — do not contaminate the new year

Arrow 013 is allowed to acquire, normalize, authenticate, and validate the data needed for a future reveal. It is NOT allowed to inspect strategy outcomes.

Forbidden in Arrow 013:

- Winner-Fade strategy replay;
- top-8/top-20 ranking output or inspection;
- candidate-by-candidate winner/loser inspection;
- rank-one return/P&L summaries;
- C0/C1/C2/C3 scoring;
- monthly strategy P&L or ending equity;
- hit rates, profit factor, drawdown, trade outcomes, or any other performance metric;
- tuning thresholds, substitution rules, sizing, hold length, timing, or allocation based on the new period;
- publishing or printing the names that would be selected by the frozen strategy.

Permitted:

- market calendar construction;
- raw data retrieval;
- security-master/reference retrieval;
- point-in-time identity/security-type validation;
- corporate-action retrieval and normalization;
- full-universe coverage/completeness checks;
- deterministic calculation of generic data-integrity fields necessary to prove the dataset can support the frozen rules, provided no strategy ranking/selection/outcome is surfaced;
- per-symbol/unit continuity checks and lifecycle coverage inventories with symbols kept private;
- overlap reconciliation against already-held August/September 2025 source data.

If an integrity check internally needs a return or feature value, use it only as a validation quantity and do not rank, optimize, summarize profitable directions, or expose selected names.

---

# 4. Authentication and source-provenance gate — before bulk retrieval

The user explicitly wants to avoid discovering later that the historical data were flawed, unauthenticated, misdated, incomplete, or pulled under the wrong contract.

Before bulk acquisition:

1. Confirm repo root and remote.
2. Confirm `.env` is ignored with `git check-ignore -v .env`.
3. Never print, echo, serialize, stage, or log credential values.
4. Use the **official installed ThetaData Python SDK / authorized Stocks Professional entitlement** already used by this lab. Do not launch Theta Terminal, change subscriptions, purchase data, use options, or use sub-minute ingest.
5. Record SDK/library version, Python version, vendor product/endpoint family, query contract, timezone assumptions, and retrieval timestamp in the command/provenance log without exposing secrets.
6. Perform a small authenticated smoke query against a previously known existing period and confirm:
   - authorization succeeds;
   - expected schema/fields are returned;
   - timestamps/timezone are as expected;
   - a repeated identical query returns semantically identical observations or an explainable vendor revision;
   - no silent empty-success response is treated as valid data.
7. If authentication, entitlement, SDK contract, or vendor response semantics are ambiguous, STOP bulk acquisition and report the exact blocker.

Raw vendor responses/normalized source partitions are immutable after landing. Repair is done in versioned derivatives, never by silently rewriting raw files.

---

# 5. Acquisition window and reuse boundary

## New bulk acquisition

Acquire the new historical source span needed before the already-held August 2025 block:

**2024-08-01 through 2025-07-31 inclusive**, covering every exchange session in that span.

This span contains:

- August 2024 warmup;
- OOS signal months September 2024 through July 2025.

## Existing August 2025

August 2025 is the final OOS signal month and is already present locally from the prior study's warmup. Do NOT assume it is valid merely because previous work used it.

Authenticate the boundary as follows:

1. Verify existing August 2025 raw/source files against their recorded hashes/manifests/provenance where available.
2. Re-query a deterministic, stratified overlap sample from ThetaData across August 2025 that covers:
   - early/mid/late month;
   - ordinary full sessions and any shortened/holiday-adjacent session if applicable;
   - multiple securities across price/liquidity ranges;
   - daily/session summary and minute-bar forms used by the lab.
3. Compare timestamps, OHLC, volume, bar counts, and relevant metadata field-for-field under the declared tolerance (normally exact for integer volume/timestamps and exact or documented vendor precision for price fields).
4. If ANY unexplained overlap discrepancy suggests a vendor revision, source-contract mismatch, stale cache, timezone shift, or normalization difference, escalate to a **full August 2025 re-retrieval into a new immutable audit partition** and reconcile old versus new before certification.
5. Do not overwrite the old August 2025 source partition.

## Lifecycle tail

Inventory September 2025 source coverage needed only for late-August 2025 H10 lifecycle/valuation. Verify provenance/continuity with the certified existing period. Do not score those August cohorts in Arrow 013.

---

# 6. Required raw/source layers

Inspect the frozen R2/R5 implementation and existing data contracts first, then acquire/prepare every source layer required to reproduce the strategy later without filling gaps by assumption.

At minimum cover, as applicable to the existing lab implementation:

- exchange/trading calendar, including holidays and early closes;
- security master / symbol identity / security type history;
- common-stock versus ETP/test/security exclusions required by the frozen eligible universe;
- daily/session OHLCV or the exact source used to compute:
  - prior close price filter $10–$80,
  - prior-day dollar-volume >= $10M,
  - 15-session ranking return,
  - 3-session momentum feature,
  - signal-day volume and prior-20-session arithmetic mean volume,
  - trailing-high/off-high diagnostic data if the future frozen challenger requires it;
- one-minute RTH data/source needed for causal pre-order observations, fills, marks, and H10 lifecycle for names that will eventually be selected;
- documented corporate actions and identity changes that can alter price/share/volume units or held quantities;
- halt/suspension/event evidence required to distinguish a market event from vendor failure.

Do not weaken the future strategy because a source layer is inconvenient. If broad minute retrieval for the complete universe is impractical, it is acceptable to prepare/certify the full-universe ranking layer now and stage a deterministic **post-selection minute/lifecycle retrieval procedure for the future reveal**. However:

- that procedure must be frozen and documented before the reveal;
- it may retrieve only the names mechanically selected by already-frozen models;
- missing selected-name execution/lifecycle data must fail closed, not trigger a next-name substitution;
- the holdout remains unscored until every selected observation required for execution/accounting is certified.

The preferred overnight outcome is to have as much of the minute/lifecycle layer already present as practical without exposing strategy selections.

---

# 7. Historical Data Certification Gate — apply before any future model scoring

Use the lab's standing rule:

**retrieval → immutable raw landing → normalization → validation → certification → only then testing.**

Arrow 013 must create a certification inventory sufficient for tomorrow's reveal. Do not write `CERTIFIED_FOR_TESTING` unless the declared scope truly satisfies the gate.

## 7.1 Trading-calendar integrity

For 2024-08-01 through the required lifecycle tail:

- authoritative session list;
- holiday/closure handling;
- early closes;
- session open/close times;
- New York timezone / DST correctness;
- no weekend/non-session bars treated as RTH;
- no duplicated or missing session labels hidden by naive calendar-day logic.

Cross-check session counts against an authoritative exchange calendar source already accepted by the lab or another reliable exchange/calendar reference. Document any differences and resolve them.

## 7.2 Timestamp and minute-bar integrity

For every minute partition used:

- timestamps parse deterministically;
- timezone is explicit;
- RTH bars fall only inside the actual session schedule;
- timestamps are unique within symbol/session;
- bars are monotonically ordered;
- no duplicate minutes;
- expected bar-count rule is correct for full and early-close sessions;
- missing minutes are inventoried, never silently forward-filled as executions;
- OHLC relationships are sane (`low <= open/close <= high` where source convention requires);
- prices are positive/finite;
- volumes are nonnegative integers or correctly typed source values;
- vendor no-data responses are distinguished from zero-volume bars and true halts.

Do not use OCR or manual visual spot checks as a substitute for programmatic inventory.

## 7.3 Full-universe / ranking-field completeness

Certification must cover the entire point-in-time field that could affect frozen selection, not merely eventual selected names.

For every signal-relevant session, prove that the data contract can correctly determine:

- security identity/type eligibility;
- prior close price;
- prior-day dollar volume;
- the full 15-session ranking return field;
- all observations needed by R5 momentum/volume sizing;
- any frozen challenger feature that will be required at reveal.

No future top-eight may benefit from a competitor silently disappearing because of missing data.

Create a private exact completeness inventory: expected observations, present observations, missing/stale observations, reason/state, and whether the deficiency could affect eligibility/ranking/sizing.

## 7.4 Corporate-action and unit integrity

For every security/session corridor capable of affecting the eligible/ranking field or later lifecycle:

- use documented dated corporate-action evidence, not inferred jump factors;
- preserve point-in-time identity/ticker mapping;
- normalize historical prices/share volumes/held shares according to the frozen convention;
- verify mechanical split neutrality of price × shares / dollar volume before market movement and rounding;
- multiple actions compose exactly;
- distinguish split/reverse split from merger, ADR ratio change, distribution, symbol change, delisting, reorganization, or other non-comparable events;
- unresolved material actions that could change field membership/rank/sizing keep the affected corridor uncertified.

A discontinuity detector is triage only. It is not proof that no action occurred.

## 7.5 Volume integrity

Because R5 sizing depends on signal-day volume versus the arithmetic mean of the prior 20 RTH sessions:

- require the full 21-session volume corridor when that feature will later be used;
- verify split-consistent share-volume units;
- do not convert missing prior volume to zero or a favorable multiplier;
- reconcile aggregated minute volume to the session/daily source where both are held and explain tolerances/differences.

## 7.6 Security identity / universe integrity

Point-in-time rules only:

- no present-day security type backfilled into 2024/2025 without historical evidence;
- identify symbol changes and predecessor/successor identity correctly;
- exclude test issues/ETPs according to the frozen rules using contemporaneous evidence;
- unresolved identity ambiguity capable of changing eligibility blocks certification for that observation.

## 7.7 Exception integrity / fail-closed policy

Explicitly forbid:

- next-in-line substitution because data are missing;
- stale-price rescue labeled verified;
- future-missing-based omission;
- vendor failure interpreted as a halt;
- inferred corporate action used as fact;
- manual repair chosen because it produces a better ranking or P&L;
- dropping an inconvenient symbol/session without an explicit exception record.

All exceptions get stable IDs, cause, source evidence, affected dates, affected fields, repair status, and whether they block certification.

---

# 8. Cross-source and reproducibility authentication

Data integrity is not just internal consistency. Add independent/overlap authentication where practical without turning this into strategy research.

Required:

1. **Repeat-query reproducibility:** re-query a deterministic sample and compare to landed raw records.
2. **Known-period overlap:** compare the August 2025 overlap sample to the already-held certified-period source.
3. **Calendar cross-check:** compare expected sessions/early closes to a reliable calendar reference.
4. **Corporate-action cross-check:** for every material action encountered in validation, compare vendor/reference representation to documented primary/authoritative evidence where practical.
5. **Session aggregation check:** for sampled symbol/sessions, minute-derived OHLCV versus daily/session source under the correct aggregation rules.
6. **Hash manifest:** SHA-256 every immutable raw partition/normalized certification artifact used for the eventual reveal.

If two authoritative sources disagree, do not choose whichever favors the strategy. Document and resolve the source-contract/unit/date issue or leave it uncertified.

---

# 9. Completeness and stopping conditions

The acquisition run should be resumable and idempotent:

- deterministic partition keys;
- atomic writes / one writer per partition;
- no overwrite of valid immutable raw partitions;
- bounded retries with backoff;
- vendor errors persisted separately from market data;
- resume skips only partitions whose integrity/hash state is already verified;
- total Theta concurrency never exceeds **8 requests** across the process tree or any lower observed vendor limit;
- CPU/local validation may use the largest practical deterministic worker count without oversubscription or duplicate writes.

Do not declare success from a percentage counter alone. Publish exact inventories.

### Certification statuses

Arrow 013 must end with one of:

- `HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL`
- `HOLDOUT_DATA_PARTIALLY_CERTIFIED — exact remaining gaps`
- `HOLDOUT_DATA_NOT_CERTIFIED — exact blocker`

`HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL` means the complete data foundation needed to determine frozen selections/sizing and the staged selected-name execution/lifecycle procedure is certified under the declared contract. It does NOT mean any strategy has been run.

If broad minute bars are intentionally deferred until after frozen selection, the status may still be `PARTIALLY_CERTIFIED` unless the future retrieval protocol plus currently certified source coverage meets the lab's Historical Data Certification Gate. Be conservative.

---

# 10. Required public-safe outputs

Publish at minimum:

- `reports/cg_arrow013_holdout_definition.json`
- `reports/cg_arrow013_data_certification.md`
- `reports/cg_arrow013_coverage_summary.csv`
- `reports/cg_arrow013_calendar_audit.csv`
- `reports/cg_arrow013_overlap_authentication.csv`
- `reports/cg_arrow013_exception_summary.csv`
- `reports/cg_arrow013_manifest.json`
- `reports/cg_arrow013_commands.txt`
- acquisition/validation/certification code and tests needed to reproduce the process.

Public outputs must not reveal future selected names, top ranks, trade results, or raw proprietary bars.

Private, ignored, individual files under `handoff/outgoing/cg_arrow013/` as needed:

- exact raw/normalized partition inventory;
- per-symbol/session completeness matrix;
- corporate-action/identity exception ledger;
- overlap comparison detail;
- authentication/retry/error detail without credentials;
- exact unresolved-observation inventory;
- any staged minute/lifecycle acquisition queue **without strategy performance fields**.

Raw vendor data remain under ignored `data/` paths, immutable after landing.

---

# 11. Tests / audit gates

At minimum add tests proving:

1. holdout definition is exactly Sep 2024–Aug 2025 signal months; Aug 2024 is warmup only;
2. Arrow 013 contains no strategy scoring/P&L output for the holdout;
3. only authorized date ranges are bulk-acquired, with lifecycle-tail reads explicitly labeled;
4. `.env` / credentials are ignored and absent from public outputs;
5. raw partitions are immutable/idempotent after successful landing;
6. duplicate/missing timestamp detection works;
7. early-close/full-session bar-count logic works;
8. DST/timezone handling is correct around relevant 2024/2025 transitions;
9. daily/session and minute aggregation reconciliation works on deterministic samples;
10. missing/vendor-error/market-halt states are distinct;
11. corporate-action normalization preserves declared mechanical identities;
12. missing feature history remains missing, never zero/favorable;
13. point-in-time identity/security-type checks do not use current-state shortcuts;
14. complete-field inventory cannot silently omit a security due to missing source data;
15. August 2025 overlap discrepancies trigger escalation rather than silent acceptance;
16. SHA-256 manifest covers every source/certification artifact required by the future reveal;
17. no raw/vendor/private symbol-level file is committed publicly;
18. prior Arrow 001–012 artifacts remain unchanged.

Run the existing regression suite after new tests.

---

# 12. Runtime and execution discipline

This is an overnight-quality data job, not a quick smoke.

At start, report:

- planned stages;
- expected bottleneck;
- current CPU/logical cores;
- selected worker/concurrency settings;
- hard stop / resumable checkpoint policy.

Use the full time necessary for **finite, predeclared acquisition/certification work** within practical overnight limits. Do not stop merely because a superficial file count looks complete. Equally, do not drift into strategy research while waiting on downloads.

If the vendor/API becomes unavailable, preserve partial progress, exact last successful partition, retry/error state, and a deterministic resume command.

---

# 13. Final report language

The final report must state plainly:

- the frozen new OOS definition: **Sep 2024–Aug 2025**;
- August 2024 = warmup only;
- August 2025 = final OOS signal month, sourced from existing data only after authentication/reconciliation;
- whether September 2025 lifecycle-tail data were required and how they were verified;
- exactly what was newly downloaded versus reused;
- exact coverage and exception counts;
- exact certification status;
- **NO STRATEGY PERFORMANCE WAS SCORED OR REVEALED IN ARROW 013**.

Do not recommend a winning model because none is allowed to be tested here.

Commit and push reviewed public-safe outputs to `main`, verify remote equality, identify private deliverables/resume commands, and stop for ChatGPT audit. Do not begin the pristine reveal arrow.