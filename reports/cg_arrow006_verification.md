# CG Arrow 006 — completed data repair, verified R1, uncertified R2, horizon census not run

Executor: Opus in Claude Code. Start 2026-09-14 11:31 UTC, hard maximum 180 minutes. Starting checkpoint `f460775` (Arrow 005 partial verification); pulled to `cf51827`. IS = in-sample odd signal months; OOS = the reused even-month internal confirmation. PnL = profit and loss; RTH = regular trading hours; EOD = end of day.

## Verdict

| Domain | Status | Evidence |
|---|---|---|
| Credentials and vendor access | **WORKING** | Local `.env` confirmed git-ignored before work and before push; API-key auth mode; 3,264 authenticated requests, zero errors. No credential value is printed, logged, staged or committed. |
| End-to-end repair pipeline | **PROVEN** | Authenticated request → immutable raw parquet → normalise/validate → per-session validated partition → cache invalidation → replay. SNDK 2025-09-25 moved from having no observation at all to a priced final-minute close of 390 regular-hours bars sourced from the validated layer, while its historical selection was untouched. Price values stay in the local proof artefact, whose hash is in the manifest. |
| Selected-trade lifecycle coverage | **COMPLETE** | 415 of 416 intended slots per family completed. The single exception is a documented SEC suspension and Nasdaq halt, not a data gap. Zero unresolved vendor responses. |
| Corrected $10–$80 ranking field | **REBUILT AND CERTIFIED** | 6,659 candidates restored, field rows 63,571 → 69,815, all 52 cohorts certified; 411 candidates are unrankable because they genuinely did not trade at a ranking endpoint, zero unresolved. |
| Test-issue and identity cleanup | **DONE** | Eight Nasdaq test issues excluded from the corrected universe; two documented ticker changes wired through the loader. |
| Corporate actions | **EXTENDED, NOT COMPLETE** | Eleven documented events, twenty dated resolutions, two identity changes, one trading event. |
| Independent reconciliation | **PASSED** | 3,735 trade rows, 468 cohort subtotals, nine daily books; maximum absolute difference 1.8e-12. |
| R1 — historically intended decisions | **VERIFIED** | All 409 frozen positions reproduced, 372 unchanged legs identical to 9e-13, seven repaired entries and 43 repaired exits, zero quantity mismatches. |
| R2 — unchanged rule on complete inputs | **NOT CERTIFIED** | 121 of 415 completed trades were ranked on a window containing an undocumented discontinuity of 2x or more and carry 88% of the total. A bounded diagnostic splits them: 30 show a share-consolidation signature, 85 show a price rise with expanding volume consistent with genuine repricing. |
| H1–H10 horizon census | **NOT RUN (data gate)** | Horizons must clone the verified R2 ledger; that ledger is not certified. No real-data cell was scored, no OOS cell revealed. |

**The repair succeeded; the economics are not yet certifiable.** Every observation the ledgers need is now retrieved and checked, and the accounting reconciles exactly. What the completed substrate reveals is that the apparent profits of both the historical and the corrected baselines are concentrated in trades whose *selection* rests on price series not certified to be in consistent units. That is a statement about evidence, not a verdict that the profits are false: the diagnostic in section 7 shows most of the flagged population behaving like genuine repricing and a minority behaving like share consolidations.

## 1. Credentials and vendor access

`git check-ignore .env` succeeds and `git ls-files` contains no `.env`. Authentication uses the installed official SDK through `src/theta/client.py` with API-key mode. Requests use the original lab conventions exactly: `stock_history_ohlc`, interval `1m`, venue `utp_cta`, window 04:00–16:00 ET, raw unadjusted prints. A parity check against the untouched local tape (SATS, 2025-09-04) matched on open, high, low, close and volume to 0.0 across every overlapping bar, so repaired partitions are interchangeable with the inherited tape. The vendor caps bulk history at one month, so requests are chunked by month.

## 2. Acquisition and validation

| Measure | Value |
|---|---:|
| Authenticated requests | 3,264 |
| Vendor errors | 0 |
| Raw rows stored | 31,692,997 |
| Raw bytes stored (local, ignored) | 304,744,337 |
| Validated symbol-sessions written | 40,093 |
| Sessions retrieved and checked | 36,843 |
| Sessions with a documented no-trading response | 3,250 |
| Unresolved vendor responses | 0 |

Validation is structural, never outcome-based: ordering, duplicate timestamps, session-date agreement, finite positive prices, OHLC consistency, non-negative volume and session-window bounds. A thinly traded session is legitimate and is not required to contain 390 bars; a zero-row response is recorded as `EMPTY_RESPONSE_UNRESOLVED` and never counts as coverage. Existing `data/full` and `data/virgin` were never written to.

## 3. Lifecycle completeness

Per family, 415 of 416 intended slots now have both scheduled endpoints priced. The residual exception is **EFTY**, under an SEC trading suspension from 2025-10-06 and a Nasdaq halt from 2025-10-18; the security did not trade again through 2026-08-31, so the resting cover order never executed. It is carried as `OPEN_AT_BOUNDARY_DOCUMENTED_HALT` with its event reference and is excluded from completed-trade totals rather than being valued at a stale mark.

Two further cases were symbol changes rather than gaps: **OCTO → ORBS** effective 2025-09-11 and **BREA → SLMT** effective 2025-10-03. Both are documented in the versioned action reference and resolved through the loader, so each security's lifecycle continues under its successor ticker.

Where a security traded during a session but had no print in the exact final minute, the execution reference falls back to that session's last regular-hours print, which is what the original engine did. The convention actually used is recorded per trade in `entry_price_field` and `exit_price_field`.

## 4. Corrected universe and ranking field

The unchanged rule is applied to complete inputs: common stock, not an exchange-traded product, not a documented Nasdaq test issue, prior close in $10–$80 and prior-day dollar volume at least $10M.

| Measure | Value |
|---|---:|
| Cohorts | 52 |
| Documented test issues excluded from the universe | 8 |
| Test-issue selections removed from the corrected field | 4 |
| Candidate rows restored | 6,659 |
| Candidate rows, old cached field → corrected field | 63,571 → 69,815 |
| Cohorts whose top eight changed | 48 |
| Names added / dropped across all cohorts | 95 / 95 |
| Cohorts with a certified rule field | 52 of 52 |
| Candidates unrankable through genuine no-trading | 411 |
| Candidates unrankable through unresolved data | 0 |

Ranking by raw 15-session return and by the historical benchmark residual give the same order within a session, because the benchmark term is a per-session constant.

## 5. R1 — historically intended decisions, repaired

| Family | Frozen positions | R1 filled | Unchanged legs matched | Max leg difference | Documented action delta | Repaired exits | Repaired-exit net | R1 completed net |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PARENT | 409 | 416 | 372 | 9.09e-13 | −5,045.90 | 43 | −3,809.26 | 36,536.55 |
| R4 | 409 | 416 | 372 | 1.82e-12 | −6,524.60 | 43 | −981.29 | 57,025.53 |
| R5 | 409 | 416 | 372 | 9.09e-13 | −8,580.46 | 43 | 54.46 | 65,676.39 |

Every frozen position is present with identical quantities. Seven entries the frozen book had missed now execute because the observation was retrieved or the thin-session reference applies: VICR, NEGG, VAL, ZVZZT, DD, SDOT and CBZ. The 43 repaired exits are scheduled covers the frozen book left open on stale marks; supplying them reduces PARENT and R4 and leaves R5 almost unchanged, which is the opposite of the direction an optimistic repair would take.

## 6. R2 — corrected rule, and why it is not certified

| Family | R2 completed net | IS | OOS | Trades on uncertified ranking units | Net carried by them | Net excluding them |
|---|---:|---:|---:|---:|---:|---:|
| PARENT | 114,855.80 | 42,761.26 | 72,094.54 | 121 of 415 | 100,884.24 | 13,971.56 |
| R4 | 127,546.11 | 51,133.88 | 76,412.22 | 121 of 415 | 112,989.11 | 14,557.00 |
| R5 | 140,256.07 | 62,051.59 | 78,204.48 | 121 of 415 | 123,292.12 | 16,963.95 |

The corrected field roughly triples the reconstructed PARENT total. That result does not survive inspection. The strategy ranks by 15-session return, so a security whose price series contains an undocumented reverse split shows an enormous apparent return and is selected almost automatically. Screening the ranking window of every selected name for a single-session ratio of 2x or more — the same threshold the inherited holding-window screen already used — flags 121 of the 415 corrected selections, and those trades carry 88% of the total.

The mechanism is demonstrated, not merely suspected. SMX entered the 2025-12-03 cohort with a 15-session return of +3,870%; the Nasdaq equity corporate action alert records a one-for-eight reverse split effective 2025-11-18, inside that ranking window. Applying the documented factor cuts the return by eight. The largest remaining flags have the same shape: FGL at 158x on 2026-02-10, DFNS at 121x on 2026-07-20, WETO at 83x on 2026-08-03 (coverage of Wetour Robotics describes a one-for-100 consolidation implemented earlier that month), TGL at 77x on 2025-12-05.

Not every flag is a split. OCTO's 31x on 2025-09-08 is the documented Worldcoin treasury announcement, and BYND's 32x is a genuine squeeze. That is exactly the point: each flagged name needs issuer or exchange evidence before its selection can be called rule-faithful, and no split may be inferred from a price move. The complete list is in `reports/cg_arrow006_manifest.json` under `ranking_window_flags`.

**The same defect is present in the inherited historical selection**, which this arrow did not create: 64 of R1's 415 completed trades carry 83% of PARENT's R1 total. Arrow 003's discontinuity screen was in-sample only and covered holding windows, not ranking windows, so this was not previously measured.

## 7. What the flagged population actually looks like

The 2x flag asks for evidence; it does not decide the answer. A bounded diagnostic records the
joint price and share-volume behaviour at each flagged session. A share consolidation multiplies
price and divides share volume by the same factor; a genuine repricing does not. Nothing here
infers a corporate action or adjusts a price.

| Class | Flags | PARENT net | R4 net | R5 net |
|---|---:|---:|---:|---:|
| Price rise with expanding volume, consistent with genuine repricing | 85 | 85,715.37 | 93,282.44 | 109,714.74 |
| Consolidation signature, entering from below the $10 eligibility floor | 28 | 12,468.24 | 16,224.89 | 9,942.79 |
| Consolidation signature, already inside the band | 2 | 2,957.00 | 3,814.40 | 3,063.93 |
| Other discontinuity | 4 | 1,581.59 | 2,038.93 | 2,872.91 |
| Endpoints unavailable | 2 | −1,837.97 | −2,371.55 | −2,302.25 |
| Certified or already resolved selections | 294 | 13,971.56 | 14,557.00 | 16,963.95 |

Three worked cases make the mechanism concrete. FGL closed at $0.0978 on 2026-02-09 and $15.44
on 2026-02-10 while share volume fell to a seventh; DFNS went from $0.0424 to $4.30 with volume
falling to a four-hundredth; WETO went from $0.0867 to $7.12 with volume falling to a
two-thousandth. Each was below the $10 eligibility floor the session before and inside the
$10–$80 band the session after, so the consolidation is what made the security eligible at all,
and its unadjusted 15-session return of several thousand percent put it at the top of a ranking
that sorts by exactly that quantity.

Against that, OCTO's 31x carried an eight-thousand-fold increase in share volume, which is the
documented Worldcoin treasury announcement rather than a consolidation. Roughly three quarters of
the flagged profit sits in that second group. The honest reading is therefore narrower than the
headline count: most of the flagged population probably is genuine, a clear minority is probably
a units artefact, and none of it is certified until each name carries issuer or exchange evidence.

Detail per flag is in the local `r4r5_ranking_window_diagnostics.csv`; counts are in
`reports/cg_arrow006_ranking_window_diagnostics.json`.

## 7. Costs and scenarios

Inherited assumptions only: $0.005 per share per side commission, a max($0.01, 0.10% of price) spread proxy per side, 0/10/30% annualised borrow on marked gross by actual calendar days, doubled-spread stress. No idle-cash yield.

| Family (R2) | Gross | Modeled net | Doubled spread | Borrow 10% | Borrow 30% |
|---|---:|---:|---:|---:|---:|
| PARENT | 119,076.21 | 114,855.80 | 111,470.72 | 108,539.18 | 95,905.95 |
| R4 | 131,703.75 | 127,546.11 | 124,208.89 | 121,239.41 | 108,626.01 |
| R5 | 144,458.29 | 140,256.07 | 136,886.24 | 133,851.69 | 121,042.94 |

Loan, locate and dividend history remain unavailable. Borrow is a scenario, so modeled net is explicitly conditional and is not verified executable historical net profit. These totals are also subject to the ranking-unit defect above.

The causal pre-order quantity bridge, which sizes from the last completed bar before the final minute instead of from the fill print, is retained as a separate panel: 114,330.25 / 127,212.83 / 140,068.81. It is a convention comparison, not a substitute headline.

## 8. Horizon release gate

**NOT_RUN_DATA_GATE.** Blocking condition: 121 corrected selections rest on ranking windows containing an undocumented discontinuity of 2x or more, so their 15-session returns are not certified to be in consistent price units. Every other gate condition is satisfied: all intended entries priced or covered by a documented event, all H10 endpoints priced or covered by a documented event, no unresolved test-security or action flag among selected R2 names, all 52 cohorts certified, the independent oracle reconciling, and no stale mark entering a completed-trade total.

Scoring thirty horizon cells on an uncertified entry ledger would inherit the defect and produce attractive numbers with no evidentiary basis, so no real-data cell was scored and no OOS cell was revealed. The horizon exporter, its H10 identity check and its same-entries invariance are exercised on synthetic data only.

## 9. What is and is not established

Established: the acquisition and validation pipeline works end to end; the selected-trade lifecycle is complete; the corrected $10–$80 field and the test-issue exclusion are rebuilt and certified; R1 reproduces the historically intended decisions exactly and repairs their observations; the accounting reconciles independently to 1.8e-12.

Not established: any verified profit figure for PARENT, R4 or R5. Both the historical and corrected baselines depend for most of their measured profit on selections whose ranking units are uncertified. The diagnostic suggests the eventual correction removes a minority rather than the majority of the flagged profit, but a suggestion is not certification, and the arithmetic of a trade selected on a fabricated return is not rescued by the trade being profitable.

## 10. Exact resumable next step

Certify or repair the ranking units of the flagged selections listed in `ranking_window_flags`, using issuer, exchange or SEC evidence, adding each documented event to `reports/cg_arrow006_corporate_actions.json`. Then rerun `scripts/cg_arrow006_run.py`; if the gate opens, run `scripts/cg_arrow006_horizons.py is`, commit the freeze, and run `scripts/cg_arrow006_horizons.py oos` for the single OOS batch. No new acquisition is required: the observation substrate is complete.
