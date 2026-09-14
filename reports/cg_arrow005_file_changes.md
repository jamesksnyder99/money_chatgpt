# CG Arrow 005 — file and function change map

No existing tracked `.py` file was modified. Frozen Arrow 003/004 dependencies, caches, results and confirmation markers are untouched (hash checks in `tests/test_cg_arrow005.py::test_original_evidence_unchanged`).

## Added code

| File | Purpose | Key functions |
|---|---|---|
| `src/verification/__init__.py` | package marker | — |
| `src/verification/r4r5_data.py` | checked observation layer | `candidate_paths` (precedence: `data/verification/r4r5/v1/validated` → canonical `virgin`/`full` minute tree by date → alternate tree); `read_bars` (RTH filter, positive volume, finite OHLC, ordering/duplicate/OHLC-consistency checks); `summarize` (final-minute close = execution reference, pre-order close, first open, volume); `eod_reference` (same-vendor 17:15 national close, reference only); `manifest_rows`/`observation_status` (PRESENT_CHECKED / NOT_PREVIOUSLY_REQUESTED / EMPTY_RESPONSE_UNRESOLVED / PARTIAL_OR_SPARSE_REVIEW / FUTURE_NOT_OBSERVABLE); `adjustment_factor`/`adjusted` (documented as-of factors); `history`/`features` (ret3, 20-session mean volume ratio); `load_summaries` (8-process pool, one writer per date partition, cache keyed by source size+mtime and version). |
| `src/verification/r4r5_replay.py` | fixed-entry ledger engine | `load_field` (historical field with documented-action rank repair), `cohorts` (52 Wednesdays, ranking-scope label), `sizing` (PARENT/R4/R5 tiers), `identity_status`, `screen_hold` (≥2x / ≥1.5x session-gap flags), `needs_for`, `replay(family, cohorts, summaries, hold, quantity, stage, recorded)` (statuses, fill and pre-order quantities, borrow base, unresolved stale liability, diagnostic delayed print), `daily_account` (cash minus liability, fresh/stale/overdue/identity-review gross). |
| `src/verification/r4r5_acquire.py` | acquisition manifest and runner | `required_windows`, `coalesce`, `pilot` (real SDK auth attempt, no secrets printed), `acquire` (≤8 concurrent, backoff via `ingest.theta_pool.call_theta`, immutable raw parquet under `data/verification/r4r5/v1/acquisition/raw`, JSONL request log; resume from log, zero rows never count as coverage). |
| `src/verification/r4r5_export.py` | private CSVs | `exceptions_rows`, `cohort_audit_rows` (TRADE rows, COHORT_SUBTOTAL, SIGNAL_MONTH/SPLIT/PERIOD totals, no double counting), `cohort_matrix_rows`, `daily_rows`, `horizon_paths` (H01..H10 wide + tidy; same shares at every horizon), `export_all`, `write_csv` (atomic). |
| `src/verification/r4r5_oracle.py` | independent calculator | `verify_trades` (Q·(entry−exit) and costs from CSV fields; rejects any net on an unverified row), `verify_cohorts`, `verify_daily` (rebuilds cash/liability/equity from trade rows and source marks), `run`. |
| `scripts/cg_arrow005_run.py` | orchestration | `r0_reproduction`, `recorded_positions`, `reconcile_r0_r1`, `compare_r1_r2`, `eod_corroboration`, `gate`, `main` (writes `reports/cg_arrow005_manifest.json`, `reports/cg_arrow005_horizon_freeze.json`). |
| `tests/test_cg_arrow005.py` | 18 focused tests | evidence unchanged; acquisition windows beyond bands and warmup; empty-file resumption; holiday/early-close/runoff calendar; action neutrality; no future-exit-dependent entry; documented-missing versus never-requested; every slot exported; sizing tiers and neutral missing history; original versus causal quantity; same shares at all horizons and H10 identity; cutoff/runoff separation; cost signs and scenarios; export + oracle + subtotal conservation; oracle rejects net on unverified rows; identity and discontinuity flags; gate/freeze consistency; pilot without secrets; private paths ignored by Git. |

## Versioned action reference

`reports/cg_arrow005_corporate_actions.json` (v2) carries the eight inherited Arrow 003 events unchanged plus two issuer-documented additions found by the full-year screen (NVA 5-for-1 forward split effective 2025-10-29, price_factor 0.2; BNAI 1-for-10 reverse split effective 2025-12-12, price_factor 10) and dated resolutions for the other flagged moves with sources. `r4r5_data.ACTION_PATH` points to v2; `ACTION_PATH_V1` keeps the inherited file, which the run script uses to pin the R1 recorded selection. `reports/cg_arrow003_corporate_actions.json` is unchanged.

## Data paths and versions

- New ignored layer `data/verification/r4r5/v1/`: `cache/summaries_r4r5_v1/<date>.json` (280 date partitions, 35,412 symbol-sessions requested, 28,213 present), `required_manifest.json`, `pilot.json`. `validated/` and `acquisition/` are empty because no vendor request could be authenticated. Bytes acquired: 0.
- Private CSVs under ignored `handoff/outgoing/cg_arrow005/` (paths and SHA-256 in `cg_arrow005_manifest.json`).
- Inputs read only: `data/tmp/cg_arrow002r/ranks_ALL_wed.json`, `data/tmp/cg_arrow003/{results,details}/*`, `data/virgin/{bars,eod,manifest.parquet}`, `data/full/{bars,manifest.parquet}`, `reports/cg_arrow003_corporate_actions.json`.
- Loader precedence and cache invalidation are described in `r4r5_data.py`; the cache key changes whenever the source file size/mtime or `VERSION` changes.

## Preserved evidence hashes

Recorded in `reports/cg_arrow005_manifest.json` (`input_sha256`) and `reports/cg_arrow005_plan.json` (`input_identity`).
