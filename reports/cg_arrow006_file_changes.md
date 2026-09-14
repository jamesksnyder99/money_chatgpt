# CG Arrow 006 — file and function change map

Arrow 003/004/005 reports, caches, freeze markers and result records are unchanged. `data/full` and `data/virgin` were never written to. The only existing test changed is one Arrow 005 runoff assertion, described below.

## Added code

| File | Purpose | Key functions |
|---|---|---|
| `src/verification/r4r5_repair.py` | acquisition repair pipeline | `month_chunks` (vendor caps bulk history at one month), `plan_requests`, `logged_requests`, `acquire` (≤8 concurrent via `ingest.theta_pool.call_theta`, immutable raw parquet, JSONL request log, resume from the log), `validate_session` (ordering, duplicates, session-date agreement, finite positive prices, OHLC consistency, non-negative volume, window bounds; thin trading is legitimate, zero rows are never coverage), `_validate_and_store` → `write_validated`, `invalidate_summaries`, `session_status_map`, `coverage_report`. |
| `src/verification/r4r5_rank.py` | corrected point-in-time ranking | `rank_cohort` (rule field, documented-unit conversion, rule-faithful no-trading versus unresolved endpoints), `corrected_cohorts` (top eight plus the old/new reconciliation), `lookback_integrity` (ranking-window discontinuity screen), `cohort_features`. |
| `scripts/cg_arrow006_acquire.py` | acquisition driver | stages `proof`, `lifecycle`, `field`, `selected`; `tradable_universe` (roster minus exchange-traded products minus documented Nasdaq test issues), `eligible_field` (unchanged $10–$80 and $10M rule), `test_issues`. |
| `scripts/cg_arrow006_run.py` | baseline, reconciliation, CSVs, gate | `candidate_meta`, `r0_reproduction`, `reconcile_r0_r1`, `waterfall`, `action_identity_review`, `selection_integrity`, `gate`, `summarize`. |
| `scripts/cg_arrow006_horizons.py` | H1–H10 census (gated) | `cell_metrics`, `same_trade_increments`, `holding_age_curve`, `build_books`, `stage_is` (30 IS cells plus the pre-reveal freeze), `stage_oos` (single-batch reveal, committed-freeze and ledger-hash checks, H10 identity). Not executed on real data: the gate did not open. |
| `tests/test_cg_arrow006.py` | 17 regression tests | secrets and ignore rules, request-log field whitelist, end-to-end proof, loader precedence, month chunking, empty response is not coverage, thin trading accepted and defects flagged, acquisition ignores entry price bands, test-issue exclusion with R1 preserved, June–August $50–$80 restoration, deterministic ranking, documented split applied in ranking units, no stale mark certified, same entries and shares at every horizon, H10 identity, single-batch OOS gate, subtotal conservation with open/closed counts, manifest gate reporting. |

## Changed code

| File | Change | Reason |
|---|---|---|
| `src/verification/r4r5_data.py` | `ACTION_PATH` now points at the Arrow 006 versioned reference (`ACTION_PATH_V1`/`V2` retained); `identity_events`, `resolved_symbol`, `trading_events`, `halted` added; `candidate_paths` resolves a symbol to its successor ticker; `summarize` emits `exec_ts`/`exec_px`/`exec_field`; `observation_status` consults the vendor status map via `set_vendor_status`; `LOCAL_TAPE_END` extended to 2026-09-11, the last required September H10 exit. | documented identity changes, thin-session execution reference, honest evidence labels, retrievable runoff. |
| `src/verification/r4r5_data.py` | `safe_path` split into a memoised `_safe_dir` plus a per-file link check; `summary_job` resolves sources first and reads them in batched polars calls. | the per-file containment walk made the loader syscall-bound; one partition of 1,400 symbols fell from minutes to about 17 seconds. Containment and link refusal are unchanged. |
| `src/verification/r4r5_replay.py` | uses the execution reference; `COMPLETED` status set added; documented-halt treatment (`NO_ENTRY_DOCUMENTED_TRADING_EVENT`, carried fill at the first later trading session, `OPEN_AT_BOUNDARY_DOCUMENTED_HALT`); ranking-window screen fields carried onto every trade; daily account closes a carried exit on its actual execution date. | a halt is a market event, not a missing observation, and must be treated causally and disclosed. |
| `src/verification/r4r5_export.py`, `r4r5_oracle.py` | count both completed statuses; new trade fields (`actual_exit_date`, `event_treatment`, `event_source`, `lookback_*`). | keep the independent calculator and the ledger in step with the event treatment. |
| `tests/test_cg_arrow005.py` | `test_cutoff_runoff_separation` now asserts that the September runoff exit is flagged post-cutoff and excluded from the calendar account, instead of asserting it is unavailable. | the runoff exit is retrievable now that credentials exist; the separation requirement is what the test should protect. |

## Versioned references

`reports/cg_arrow006_corporate_actions.json` (v3) preserves the ten Arrow 003/005 events unchanged and adds the SMX one-for-eight reverse split of 2025-11-18 (Nasdaq equity corporate action alert 2025-612), found by the ranking-window screen. It carries twenty dated screen resolutions, two documented security-identity changes (OCTO→ORBS, BREA→SLMT) and one documented trading event (EFTY suspension and halt). `reports/cg_arrow005_corporate_actions.json` and `cg_arrow003_corporate_actions.json` are unchanged.

## Data paths

- `data/verification/r4r5/v1/acquisition/raw/<SYMBOL>/<start>_<end>.parquet` — immutable raw responses, 304,744,337 bytes across 3,264 requests. Local and git-ignored.
- `data/verification/r4r5/v1/validated/<session>/<SYMBOL>.parquet` — 40,093 validated symbol-sessions. Local and git-ignored.
- `data/verification/r4r5/v1/acquisition/requests.jsonl` — request log: symbol, window, endpoint, interval, venue, row count, elapsed time, per-session status. No credential material.
- `data/verification/r4r5/v1/cache/summaries_r4r5_v1/<session>.json` — derived summaries, invalidated whenever the resolved source identity or schema version changes.
- `data/verification/r4r5/v1/work/` — cohort field, request plans, corrected selection and baseline state.
- `handoff/outgoing/cg_arrow006/` — the private CSV deliverables.

Loader precedence is validated → the date's canonical tree (virgin to 2026-05-29, full afterwards) → the alternate tree. National EOD reports remain same-vendor corroboration and never supply an execution.
