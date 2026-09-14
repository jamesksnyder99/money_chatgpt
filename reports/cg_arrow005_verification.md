# CG Arrow 005 — verification of PARENT / R4 / R5 (H10) and horizon gate

Executor: Fable in Claude Code. Start 2026-09-14 06:21 ET (10:21 UTC); allocation 180 minutes. Starting snapshot `fee07b8`; plan committed at `0174e7e` before any outcome-dependent step. IS = in-sample odd signal months; OOS = out-of-sample even signal months (reused internal confirmation, not pristine validation). PnL = profit and loss; MTM = mark-to-market; RTH = regular trading hours; EOD = end of day.

## Verdict — PARTIAL VERIFICATION; horizon census NOT RUN (data gate)

| Domain | Status | Evidence |
|---|---|---|
| Historical selection provenance (R0 → R1) | **VERIFIED** | All 409 frozen Arrow 003 entries reproduced with identical quantities; all 370 scheduled-exit legs without a documented action match to 1e-12 per family; the two NVA legs differ only by the newly documented split. |
| Complete reconstructed ranking scope (R2) | **UNVERIFIED** | 13 of 52 cohorts (2026-06-03 … 2026-08-26) were ranked on a field truncated at a $50 prior close; the rule requires $10–$80. The inherited common-stock roster contains nine Nasdaq test symbols; ZVZZT was selected twice. The cached rank returns themselves are exact (1,456 sampled rows recomputed from raw bars, zero mismatches); 1,922 of 67,477 rule-eligible cohort rows lack a rank endpoint locally. |
| Entry/exit price coverage | **PARTIAL** | Per family: 372 of 416 slots priced at both scheduled ends; 37 scheduled H10 exits unresolved locally (21 in-window, 16 September runoff); 7 intended entries missing the final-minute bar. Single vendor only. |
| Corporate actions / security identity | **PARTIAL, one repair applied** | A full-year screen of held names found 11 slots with ≥2x and 7 with 1.5–2x single-session moves; earlier arrows screened IS only. Issuer evidence: NVA had an undocumented 5-for-1 forward split (first split-adjusted session 2025-10-29) that turned two mixed-unit "profits" into a small gain and a small loss; BNAI's 1-for-10 reverse split (2025-12-12) was added with no membership effect; 11 moves are documented dilution/offering/news events; ZVZZT (2 slots) is a test symbol; DFNS is unconfirmed and MXL unreviewed (both 1.5–2x). |
| Daily valuation coverage | **PARTIAL** | Stale marks flagged per session; unresolved inventory shown separately and excluded from verified totals. |
| Accounting reconciliation | **PASSED** | Independent oracle: 3,348 trade rows, 468 cohort subtotals, 9 daily books; maximum absolute difference 1.5e-10. |
| Executable fill assumptions | **MODELED** | Final-minute bar close is a simulation reference, not a broker fill. Legacy fill-close share sizing preserved and labeled; a causal pre-order quantity panel is exported separately. |
| Loan / dividend / financing | **UNKNOWN** | Null, with 0/10/30% borrow and doubled-spread scenarios; no idle yield. |
| Vendor access | **BLOCKED** | ThetaData SDK 1.0.10 is installed; no credentials exist in the lab (`.env` absent, no `THETA*` environment variables, no home config). Authentication attempt failed; no request could be made. |

**What can be claimed:** the price/quantity arithmetic and accounting of the previously intended trades are exact; 372 of 416 intended H10 slots per family have locally observed entry and scheduled exit prints from one vendor partition; one material action defect (NVA) was found and repaired with issuer evidence. **What cannot be claimed:** a verified total for any family, complete ranking scope for June–August 2026, broker-executable fills, or net economics after loans and dividends. Neither a positive nor a negative verified baseline is established.

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

The detailed manifest is local (`data/verification/r4r5/v1/required_manifest.json`). Beyond these, restoring the $10–$80 field for the 13 June–August cohorts requires EOD/eligibility and minute history for names priced $50–$80 in that period; that request set was not built because the roster must first be cleaned of test symbols and identity-checked.

## R0 — frozen legacy reproduction (read-only)

| Book | Legacy IS (Arrow 002) | Working IS (Arrow 003) | All-signal total (Arrow 003) | = scheduled-exit legs | + delayed covers (diagnostic) | + terminal MTM incl. stale |
|---|---:|---:|---:|---:|---:|---:|
| PARENT | 9,969.57 | 6,450.99 | 38,317.20 | 45,391.71 | −3,783.60 | −3,290.91 |
| R4 | 16,598.29 | 14,078.45 | 59,040.69 | 64,531.43 | −5,443.17 | −47.57 |
| R5 | 24,628.10 | 21,662.04 | 68,921.14 | 74,202.39 | −4,494.37 | −786.88 |

All three records are original fixed-ticket H10 books under the Arrow 003 working convention (fill-close quantity, delayed cover at a later open, stale marks inside totals). The Arrow 004 BRIDGE and S0 books are timing-bridge and equity-budgeted variants; they were not replayed in this pass.

## R1 — fixed historical decisions, corrected statuses and documented actions

Recorded top-eight (inherited event set), recorded features, tickets and shares; exits re-derived with explicit evidence labels and the v2 documented action set. Identity with the frozen positions is exact (409/409, zero quantity mismatches). Verified means both scheduled prints exist in one local vendor partition; it does not mean broker-executable.

| Family | Intended slots | Verified scheduled exits | Unresolved exits | Missed entries | Verified modeled net | IS / OOS | Wins / losses | NVA split delta vs frozen legs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PARENT | 416 | 372 | 37 | 7 | 40,345.81 | 6,709.89 / 33,635.93 | 185 / 187 | −5,045.90 |
| R4 | 416 | 372 | 37 | 7 | 58,006.83 | 14,239.90 / 43,766.93 | 185 / 187 | −6,524.60 |
| R5 | 416 | 372 | 37 | 7 | 65,621.93 | 22,109.04 / 43,512.90 | 185 / 187 | −8,580.46 |

The verified subtotal is a known-part subtotal, not the model result and not a bound: the 37 unresolved slots carry roughly $150k–$164k of short liability at last observed marks per family, and the earlier delayed-cover diagnostic shows those gaps resolving at a loss (−$3.8k to −$5.4k) where a later print existed. Statuses of the 44 non-verified slots per family: 35 `UNRESOLVED_NOT_PREVIOUSLY_REQUESTED`, 2 `UNRESOLVED_PARTIAL_OR_SPARSE_REVIEW`, 6 `MISSED_ENTRY_NOT_PREVIOUSLY_REQUESTED`, 1 `MISSED_ENTRY_PARTIAL_OR_SPARSE_REVIEW`.

## R2 — unchanged rules on the local field

Rankings were recomputed with the v2 event set (inherited eight plus NVA and BNAI): no cohort membership changed. Features (20-session mean volume ratio, ret3) and quantities recomputed from checked summaries show zero differences from the recorded R1 values, so on the local field R2 equals R1. The causal pre-order quantity panel changes 152/152/140 share counts and gives 40,282.99 / 58,010.79 / 65,542.20. R2 cannot be called complete: see the ranking-scope row above.

### Action / identity review (full year; flags, issuer evidence, resolution)

| Cohort | Symbol | Largest session ratio | Date | Slot status | Resolution |
|---|---|---:|---|---|---|
| 2025-10-15 | NVA | 0.208 | 2025-10-29 | verified | 5-for-1 forward split applied (issuer notice 2025-10-15) |
| 2025-10-22 | NVA | 0.208 | 2025-10-29 | verified | same; frozen +3,177 becomes −25 (PARENT) |
| 2025-10-22 | PMI | 0.300 | 2025-10-24 | verified | documented dilution sell-off |
| 2026-01-14 | NBY | 0.445 | 2026-01-20 | verified | documented ATM/warrant dilution |
| 2026-01-28 | BNAI | 0.470 | 2026-01-30 | verified | after documented 2025-12-12 reverse split; no action that date |
| 2026-04-22 / 04-29 | XNDU | 0.366 | 2026-05-04 | verified | documented resale-prospectus crash |
| 2026-05-06 | ONEG | 0.144 | 2026-05-07 | unresolved | documented registered direct offering |
| 2026-08-19 | SMJF | 0.127 | 2026-08-27 | unresolved | documented unusual market action, issuer statement |
| 2026-04-01 / 06-17 | ZVZZT | 0.178 / — | 2026-04-02 | unresolved / missed | **test symbol; unresolved identity defect** |
| 2025-12-24, 2026-01-14, 2026-03-11/18, 2026-04-22 | RGC, AHMA, BATL ×2, POET | 1.58, 1.89, 0.57, 0.53 | — | verified | documented market moves (speculative surge, earnings/holder sale, order cancellation) |
| 2026-08-12 / 2026-04-22 | DFNS / MXL | 0.54 / 1.76 | — | verified / unresolved | unconfirmed / unreviewed (1.5–2x) |

Sources are recorded in `reports/cg_arrow005_corporate_actions.json`. Excluding every flagged trade regardless of resolution leaves 22,121.26 / 32,162.45 / 30,977.86: large single-session moves account for roughly half of each family's verified profit, which is a property of the short-the-spike selection, not by itself a defect.

### Same-vendor corroboration

Where a local national EOD report exists (through May 2026), 305 entry and 275 exit final-minute closes agree within 1% of the 17:15 EOD close; 4 entries and 3 exits differ by 1.0–1.5%. 100 entries and 94 exits (June–August 2026) have no local EOD partition. This is one vendor's second endpoint, not independent validation.

## Costs and scenarios (verified subset only)

| Family | Gross | Modeled net (base) | Double spread | Borrow 10% | Borrow 30% | Tier contribution |
|---|---:|---:|---:|---:|---:|---|
| PARENT | 43,973.41 | 40,345.81 | 37,401.24 | 34,566.08 | 23,006.60 | FULL 40,345.81 |
| R4 | 61,654.34 | 58,006.83 | 55,051.21 | 52,220.34 | 40,647.38 | FULL 64,152.75 / HALF −6,145.92 |
| R5 | 69,316.99 | 65,621.93 | 62,637.55 | 59,766.00 | 48,054.13 | FULL 37,218.93 / HALF 33,545.55 / QUARTER −5,142.55 |

Borrow uses actual calendar holding days on marked gross. Dividends, locate and financing are null, not zero.

## Daily account (August 31 cutoff)

`r4r5_daily_account.csv` holds cash, short liability, equity, stale and overdue gross, identity-review gross, and equity variants excluding stale-mark and test-symbol unrealized. The equity series is contaminated by ZVZZT prints (single-session swings of −$37k/+$38k on 2026-08-18/21) and by carried stale marks; it is published for audit, not as a result. August 31 equity including stale marks: PARENT 141,761.78 (stale unrealized −8,075.98; test-symbol unrealized −482.60), R4 161,286.52 (−7,046.84; −622.30), R5 168,594.53 (−7,330.98; −501.65). Sixteen August-cohort tickets have scheduled September exits that are not locally observable; no September realization was backdated.

## Horizon release gate

`NOT_RUN_DATA_GATE`. Blocking: unresolved H10 exits (37 per family), missed entries (7), 2 unresolved identity slots (test symbol), 13 cohorts with truncated ranking scope. The H1–H10 exporter (`r4r5_export.horizon_paths`) was built and tested on synthetic data only; no real-data horizon cell was scored, and no OOS scoreboard exists.

## Old-to-new waterfall and interpretation

R0 total → remove delayed-cover and stale terminal marks → R1 scheduled-exit subtotal (exact leg identity) → documented NVA split (−5,045.90 / −6,524.60 / −8,580.46) → R2 recomputed features/quantities (no change on the local field) → causal quantity panel (−62.82 / +3.96 / −79.73) → unresolved inventory (unknown sign, ~$150k+ liability at stale marks) → ranking scope and roster identity (unquantified). Later steps interact; the order was fixed in the plan and no step was chosen by outcome.

## Not completed in this pass

Vendor acquisition (blocked); complete-field re-ranking for June–August 2026; roster cleanup of test symbols; the secondary BRIDGE/S0 reconciliation (its purpose, supplying actual exits, is blocked by the same acquisition gap). Resumable checkpoint: `data/verification/r4r5/v1/` (summaries cache, required manifest, pilot record) plus the CSVs listed in `cg_arrow005_manifest.json`.
