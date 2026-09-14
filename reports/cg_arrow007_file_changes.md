# CG Arrow 007 — file and function change map

Arrow 003 to 006 reports, caches, freeze markers and result records are unchanged. `data/full` and `data/virgin` were never written to. Existing test files were changed only where Arrow 007 deliberately changed a behaviour they asserted.

## Added code

| File | Purpose | Key functions |
|---|---|---|
| `src/verification/r4r5_schedule.py` | the frozen weekly calendar rule | `nominal_anchors`, `signal_for` (backward rollback from a closed Wednesday), `entry_for` (first session strictly after the signal), `exit_for`, `weekly_schedule`, `schedule_diff` (proves the rule changes no cohort before scoring). |
| `src/verification/r4r5_events.py` | primary-source event evidence from SEC EDGAR | rate-limited cached `fetch`; `ticker_cik`, `submissions`, `filing_rows`, `doc_url`, `plain_text`; `extract_events` and `classify_factor` (ratio and direction from filing text); `scan_symbol` and `scan_symbols` (one parallel pass per security across the whole window). |
| `scripts/cg_arrow007_events.py` | the scoped census | screens at 1.2x over the top 25 ranked candidates of every cohort plus all recorded selection windows, deduplicates to symbol/session cases, then scans each security. |
| `scripts/cg_arrow007_deepscan.py` | residual-case resolution | `resolve_cik` (documented identity map, then a filing cover page carrying that trading symbol) and `deep_scan` (every document of every candidate filing, exhibits included). |
| `scripts/cg_arrow007_actions.py` | canonical action table | `pick` accepts a filing-stated factor only when applying it flattens the observed discontinuity at a filing-supported date. |
| `scripts/cg_arrow007_run.py` | certified baseline | `rank_with`, `unresolved_selected`, `volume_signature`, `classify_unresolved`, `merge_new_evidence`, the fixed-point loop with a confirmation rerank, `split_books`, `account_metrics`, `upside_bridge`, `gate`. |
| `scripts/cg_arrow007_horizons.py` | the Hold-Length Ladder | `cell_metrics` on split-owned books, `increments` with explicit state transitions, `age_curve`, `stage_is` (freeze) and `stage_oos` (single-batch reveal with committed-freeze and ledger-hash checks). |
| `scripts/cg_arrow007_exports.py` | audit exports | action ledger, three-way ranking reconciliation, upside bridge, safe account aggregates. |
| `scripts/cg_arrow007_audit.py` | adversarial audit | eleven independent checks that rebuild the published result from stored evidence without calling the replay or ranking helpers. |
| `tests/test_cg_arrow007.py` | 27 regression tests | calendar rollback and neutrality; factor convention both directions; composed events; split neutrality across a hold and on the signal, fill and exit boundaries; adjusted ranking return and volume-history conversion; adjusted-series rescreen; documented event alone does not clear a window; structural block and explicit acceptance; no manual rank-9 substitution; test-issue exclusion; split-owned book isolation; runoff separation; halt survives the ladder; identical entries and shares across holds; distinct quantity panels; oracle and subtotal conservation; three ranking baselines; one-batch reveal; git exclusions; no credentials in public artefacts. |

## Changed code

| File | Change | Reason |
|---|---|---|
| `src/verification/r4r5_data.py` | `ACTION_PATH` now points at the Arrow 007 table (`ACTION_PATH_V1`/`V2`/`V3` retained); added `non_comparable_events` and `spans_non_comparable`; added `structural_issues`, `structural_block` and `set_accepted_structural_issues`; `summary_job` records a structural status. | a reorganisation exchange has no valid factor, and a structurally defective partition must not silently support a verified trade. |
| `src/verification/r4r5_rank.py` | `rank_cohort` accepts an explicit event set and refuses to rank a candidate whose window spans a non-comparable event; `adjusted_path`, `screen_adjusted`, `lookback_integrity` and `holding_integrity` replace the raw screen. | Arrow 006 cleared a window when any documented event existed inside it. Arrow 007 applies every event and requires the adjusted series itself to be continuous. |
| `src/verification/r4r5_replay.py` | structural blocking on entry and exit observations; carries the ranking and holding integrity fields onto every trade. | keeps the certification state attached to the ledger rows the user audits. |
| `tests/test_cg_arrow005.py`, `tests/test_cg_arrow006.py` | unchanged in this arrow. | — |

## Versioned references

`reports/cg_arrow007_corporate_actions.json` preserves every inherited Arrow 003/005/006 event unchanged and adds the Arrow 007 findings, with `security_identity`, `trading_events`, `non_comparable_events` and dated `screen_resolutions`. Earlier action files are untouched.

## Data paths

- `data/verification/r4r5/v1/events/http_cache/` — cached SEC responses, the preserved evidence behind every factor. Local and git-ignored.
- `data/verification/r4r5/v1/work/event_cases.json`, `event_evidence.json`, `event_symbol_scans.json`, `deepscan_*.json`, `action_ledger.json`, `a7_baseline_state.json` — the investigation record.
- `data/verification/r4r5/v1/{acquisition,validated,cache}` — unchanged Arrow 006 acquisition layer, extended by the small top-up for newly certified selections.
- `handoff/outgoing/cg_arrow007/` — the twelve private CSV deliverables.

## Parallelism and worker choices

Eight logical cores. ThetaData top-up acquisition used the full eight concurrent requests with bounded backoff, never more. SEC EDGAR used eight worker threads behind a single shared 8 requests-per-second token bucket, below the published limit. Summary loading, ranking, replay, horizon scoring and the test suite used eight workers. The first census design issued one investigation per symbol/session case and was measured at roughly 3.9 seconds per case; restructuring to one filing scan per security cut the same work to about 2.3 seconds per security and finished 386 securities in 14.8 minutes. Dependent steps were deliberately serial: the rerank iterations, the freeze decision and the in-sample to out-of-sample reveal.
