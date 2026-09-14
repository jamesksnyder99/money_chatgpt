# CG Arrow 005 — verification of PARENT / R4 / R5 (H10) and horizon gate

Executor: Fable in Claude Code. Start 2026-09-14 06:21 ET (10:21 UTC); allocation 180 minutes. Starting snapshot `fee07b8`; plan committed at `0174e7e` before any outcome-dependent step. IS = in-sample odd signal months; OOS = out-of-sample even signal months (reused internal confirmation, not pristine validation). PnL = profit and loss; MTM = mark-to-market; RTH = regular trading hours; EOD = end of day.

## Verdict — PARTIAL VERIFICATION; horizon census NOT RUN (data gate)

| Domain | Status | Evidence |
|---|---|---|
| Historical selection provenance (R0 → R1) | **VERIFIED** | All 409 frozen Arrow 003 entries reproduced with identical quantities; all 372 scheduled-exit legs match to 1e-12 per family. |
| Complete reconstructed ranking scope (R2) | **UNVERIFIED** | 13 of 52 cohorts (2026-06-03 … 2026-08-26) were ranked on a field truncated at a $50 prior close; the rule requires $10–$80. A Nasdaq test symbol (ZVZZT) sits in the inherited common-stock roster and was selected twice. |
| Entry/exit price coverage | **PARTIAL** | Per family: 372 of 416 slots priced at both scheduled ends; 37 scheduled H10 exits unresolved locally (21 in-window, 16 September runoff); 7 intended entries missing the final-minute bar. Single vendor only. |
| Corporate actions / security identity | **DEFECTIVE / PARTIAL** | Eight documented reverse splits applied. A full-year screen found 11 slots with a ≥2x single-session gap (7 of them counted as verified profits) and 6 more with 1.5–2x moves; none were reviewed against issuer evidence in earlier arrows because that screen was IS-only. Test-symbol prints (24.51 → 126.00 → 24.75) contaminate the account marks. |
| Daily valuation coverage | **PARTIAL** | Stale marks flagged per session; unresolved inventory shown separately and excluded from verified totals. |
| Accounting reconciliation | **PASSED** | Independent oracle: 3,348 trade rows, 468 cohort subtotals, 9 daily books; maximum absolute difference 1.5e-10. |
| Executable fill assumptions | **MODELED** | Final-minute bar close is a simulation reference, not a broker fill. Legacy fill-close share sizing preserved and labeled; a causal pre-order quantity panel is exported separately. |
| Loan / dividend / financing | **UNKNOWN** | Null, with 0/10/30% borrow and doubled-spread scenarios; no idle yield. |
| Vendor access | **BLOCKED** | ThetaData SDK 1.0.10 is installed; no credentials exist in the lab (`.env` absent, no `THETA*` environment variables, no home config). Authentication attempt failed; no request could be made. |

**What can be claimed:** the price/quantity arithmetic and accounting of the previously intended trades are exact, and 372 of 416 intended H10 slots per family have locally observed entry and scheduled exit prints from one vendor partition. **What cannot be claimed:** a verified total for any family, complete ranking scope for June–August 2026, action/identity cleanliness of the largest profits, broker-executable fills, or net economics after loans and dividends. A negative or positive verified baseline is therefore not yet established either way.

## Vendor access test (section 3A)

`theta.client.auth_mode()` raises `Missing Theta Data credentials in .env`. The OS environment has no `THETADATA_*`/`THETA_*` variables and there is no user-level configuration file. The lab has never held credentials: Arrow 003/004 explicitly used copied data only. Exact local setup needed: create `C:\Users\james\money_chatgpt\.env` (ignored by Git) containing `THETADATA_API_KEY=<key>` or `THETADATA_EMAIL`/`THETADATA_PASSWORD`, then run `python scripts/cg_arrow005_run.py --acquire`. The runner (`src/verification/r4r5_acquire.py`) uses `ThetaClient.stock_history_ohlc(symbol, start_date, end_date, interval="1m")`, at most eight concurrent requests with bounded backoff, immutable raw storage, and a request log that treats zero-row responses as `EMPTY_RESPONSE_UNRESOLVED`. The pilot cases SNDK 2025-09-25, DNTH 2026-04-02 and an ordinary day are wired in but were not executed.

## Required observations (section 3B)

Every symbol-session the H10 ledgers need was inventoried (feature history, fill, ten holding sessions and exit; 9,104 unique symbol-sessions across the 416 slots):

| Status | Count |
|---|---:|
| PRESENT_CHECKED | 8,683 |
| NOT_PREVIOUSLY_REQUESTED | 403 |
| PARTIAL_OR_SPARSE_REVIEW (file present, final-minute bar absent) | 18 |
| Coalesced symbol/date-window requests | 118 |

The detailed manifest is local (`data/verification/r4r5/v1/required_manifest.json`). Beyond these, restoring the $10–$80 field for the 13 June–August cohorts requires EOD/eligibility and minute history for names priced $50–$80 in that period; that request set was not built because the roster itself must first be cleaned of test symbols and identity-checked.

## R0 — frozen legacy reproduction (read-only)

| Book | Legacy IS (Arrow 002) | Working IS (Arrow 003) | All-signal total (Arrow 003) | = scheduled-exit legs | + delayed covers (diagnostic) | + terminal MTM incl. stale |
|---|---:|---:|---:|---:|---:|---:|
| PARENT | 9,969.57 | 6,450.99 | 38,317.20 | 45,391.71 | −3,783.60 | −3,290.91 |
| R4 | 16,598.29 | 14,078.45 | 59,040.69 | 64,531.43 | −5,443.17 | −47.57 |
| R5 | 24,628.10 | 21,662.04 | 68,921.14 | 74,202.39 | −4,494.37 | −786.88 |

All three records are original fixed-ticket H10 books under the Arrow 003 working convention (fill-close quantity, delayed cover at a later open, stale marks inside totals). The Arrow 004 BRIDGE and S0 books are timing-bridge and equity-budgeted variants; they were not replayed in this pass (budget).

## R1 — fixed historical decisions, corrected statuses

Recorded top-eight, recorded features, tickets and shares; exits re-derived with explicit evidence labels. Identity with the frozen positions is exact (409/409, zero quantity mismatches). Verified means both scheduled prints exist in one local vendor partition; it does not mean broker-executable.

| Family | Intended slots | Verified scheduled exits | Unresolved exits | Missed entries | Verified modeled net | IS / OOS | Wins / losses |
|---|---:|---:|---:|---:|---:|---:|---:|
| PARENT | 416 | 372 | 37 | 7 | 45,391.71 | 6,709.89 / 38,681.83 | 186 / 186 |
| R4 | 416 | 372 | 37 | 7 | 64,531.43 | 14,239.90 / 50,291.53 | 186 / 186 |
| R5 | 416 | 372 | 37 | 7 | 74,202.39 | 22,109.04 / 52,093.36 | 186 / 186 |

The verified subtotal is a known-part subtotal, not the model result and not a bound: the 37 unresolved slots carry roughly $150k–$164k of short liability at last observed marks per family, and the earlier delayed-cover diagnostic shows those gaps resolved at a loss (−$3.8k to −$5.4k) where a later print existed. Statuses of the 44 non-verified slots per family: 35 `UNRESOLVED_NOT_PREVIOUSLY_REQUESTED`, 2 `UNRESOLVED_PARTIAL_OR_SPARSE_REVIEW`, 6 `MISSED_ENTRY_NOT_PREVIOUSLY_REQUESTED`, 1 `MISSED_ENTRY_PARTIAL_OR_SPARSE_REVIEW`.

## R2 — unchanged rules on the local field

Features (20-session mean volume ratio, ret3) and quantities were recomputed from checked summaries: zero differences from the recorded R1 values, so on the local field R2 equals R1. The causal pre-order quantity panel changes 152/152/140 share counts and moves the verified net to 45,274.61 / 64,481.11 / 74,041.24. R2 cannot be called complete: see the ranking-scope and identity rows above.

### Action / identity review (full year, flag only, no inferred factors)

| Cohort | Symbol | Largest session ratio | Date | Slot status |
|---|---|---:|---|---|
| 2025-10-15 | NVA | 0.208 | 2025-10-29 | verified |
| 2025-10-22 | NVA | 0.208 | 2025-10-29 | verified |
| 2025-10-22 | PMI | 0.300 | 2025-10-24 | verified |
| 2026-01-14 | NBY | 0.445 | 2026-01-20 | verified |
| 2026-01-28 | BNAI | 0.470 | 2026-01-30 | verified |
| 2026-04-22 | XNDU | 0.366 | 2026-05-04 | verified |
| 2026-04-29 | XNDU | 0.366 | 2026-05-04 | verified |
| 2026-04-01 | ZVZZT (test symbol) | 0.178 | 2026-04-02 | unresolved |
| 2026-05-06 | ONEG | 0.144 | 2026-05-07 | unresolved |
| 2026-08-19 | SMJF | 0.127 | 2026-08-27 | unresolved |
| 2026-06-17 | ZVZZT (test symbol) | — | — | missed entry |

Six further slots (RGC, AHMA, BATL ×2, POET, MXL, DFNS) show 1.5–2x moves. Excluding only the seven verified ≥2x cases, verified net falls to 26,518.64 / 40,163.05 / 45,763.61: roughly 40% of each family's verified profit sits in trades whose price units are unconfirmed. These are review flags; nothing was deleted.

### Same-vendor corroboration

Where a local national EOD report exists (through May 2026), 305 entry and 275 exit final-minute closes agree within 1% of the 17:15 EOD close; 4 entries and 3 exits differ by 1.0–1.5%. 100 entries and 94 exits (June–August 2026) have no local EOD partition. This is one vendor's second endpoint, not independent validation.

## Costs and scenarios (verified subset only)

| Family | Gross | Modeled net (base) | Double spread | Borrow 10% | Borrow 30% | Tier contribution |
|---|---:|---:|---:|---:|---:|---|
| PARENT | 49,008.45 | 45,391.71 | 42,454.38 | 39,620.26 | 28,077.35 | FULL 45,391.71 |
| R4 | 68,164.90 | 64,531.43 | 61,585.17 | 58,755.62 | 47,204.01 | FULL 70,677.35 / HALF −6,145.92 |
| R5 | 77,878.79 | 74,202.39 | 71,230.45 | 68,363.18 | 56,684.76 | FULL 43,868.23 / HALF 35,476.71 / QUARTER −5,142.55 |

Borrow uses actual calendar holding days on marked gross. Dividends, locate and financing are null, not zero.

## Daily account (August 31 cutoff)

`r4r5_daily_account.csv` holds cash, short liability, equity, stale and overdue gross, identity-review gross and an equity variant excluding stale-mark and test-symbol unrealized. The equity series is contaminated by ZVZZT prints (single-session swings of −$37k/+$38k on 2026-08-18/21) and by carried stale marks; it is published for audit, not as a result. August 31 equity including stale marks: PARENT 146,807.68 (stale unrealized −8,075.98), R4 167,811.12 (−7,046.84), R5 177,174.99 (−7,330.98). Sixteen August-cohort tickets have scheduled September exits that are not locally observable; no September realization was backdated.

## Horizon release gate

`NOT_RUN_DATA_GATE`. Blocking: unresolved H10 exits (37 per family), missed entries (7), 11 unresolved action/identity flags, 13 cohorts with truncated ranking scope. The H1–H10 exporter (`r4r5_export.horizon_paths`) was built and tested on synthetic data only; no real-data horizon cell was scored, and no OOS scoreboard exists.

## Old-to-new waterfall and interpretation

R0 total → remove delayed-cover and stale terminal marks → R1 verified scheduled-exit subtotal (exact leg identity) → R2 recomputed features/quantities (no change on the local field) → causal quantity panel (−117 / −50 / −161) → action/identity exclusions (−18,873 / −24,368 / −28,439, review pending) → unresolved inventory (unknown sign, ~$150k+ liability at stale marks). Later steps interact; the order is fixed by the plan and no step was chosen by outcome.

## Not completed in this pass

Vendor acquisition (blocked); complete-field re-ranking for June–August 2026; issuer-evidence review of the 17 flagged names; the secondary BRIDGE/S0 reconciliation. Resumable checkpoint: `data/verification/r4r5/v1/` (summaries cache, required manifest, pilot record) plus the CSVs listed in `cg_arrow005_manifest.json`.
