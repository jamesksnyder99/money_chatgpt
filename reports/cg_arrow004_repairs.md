# CG Arrow 004 — repairs, retained limitations and lifecycle evidence

In-sample (IS) means odd **original signal** months. Out-of-sample (OOS) means the reused even-month internal confirmation. Profit and loss (PnL), drawdown (DD), mark-to-market (MTM), end-of-day (EOD) and regular trading hours (RTH) are modeled account terms. This file separates changed treatment from strategy findings. Historical Arrow 003 evidence is unchanged.

## Retained treatment and timing-only bridges

The eight issuer-documented action events in `cg_arrow003_corporate_actions.json` remain the common partial action treatment. Raw prints are preserved. Known dated price factors adjust lookback comparison prices, share volumes, held quantities, entry/paid-cost basis and carried marks as of the effective session. The empty copied split placeholder does not establish absence of other actions. Unknown dividends, cash-in-lieu details and additional actions remain unresolved; there is no universe-wide action certification.

The new schedule is anchored to nominal Thursdays and nominal expiry +14 calendar days. Full holidays map to the last prior trading session; the signal is the preceding trading session, which is Tuesday for some mapped entries. Early-close entries/exits use one minute/one hour before actual close. Weekly startup receives a strict half-target cohort, and fixed biweekly phases never restart at month boundaries.

Entry is the exact last RTH minute **OPEN**, with integer quantity determined from the preceding completed mark. Exit is the first observed OPEN at/after the predetermined checkpoint. Missing exact entries are missed. Missing exits remain obligations, with no capacity credit until an actual later observed RTH execution; terminal inventory is retained. Stale valuations are not fills. The previous one-week cohort survives a normal weekly replacement.

| Control | Arrow 003 working IS PnL | Arrow 004 timing-only bridge | Timing/convention difference |
| --- | ---: | ---: | ---: |
| R4, fixed intended $5,150 ticket | 14,078.45 | 12,261.13 | -1,817.32 |
| R5, fixed intended $8,300 ticket | 21,662.04 | 18,071.93 | -3,590.11 |

These differences include the prescribed clock, holiday expiry and bar-open/pre-order quantity convention. They are not reserve-selection alpha. The legacy fixed-ticket bridges are diagnostic comparators; the new budgeted books add causal current-equity allocation and a 20% aggregate-symbol order safeguard.

## Two pre-reveal implementation repairs

**Carry startup repair, declared at 32.30 elapsed minutes.** The initial S4 implementation used all real headroom on the first global Thursday. That violated the required half-budget startup even though later carry-forward entries may use more headroom. All affected S4 IS books and the related fixed-equity comparator were archived and replayed with strict startup. The one-formula IS average-exposure calibration was rerun from the corrected book, with its old calibration retained. A second literal interpretation, S4_FULL, permits later fully favorable primary as well as reserve tickets; both interpretations have startup tests.

| Affected book | Superseded IS PnL | Corrected IS PnL |
| --- | ---: | ---: |
| S4_R4 | 10,335.62 | -2,410.48 |
| S4_R5 | 5,318.31 | 6,389.17 |
| FIXE_S4_R4 | 13,276.44 | 1,309.42 |

The apparent R4 carry benefit disappeared. The superseded results are invalid strategy evidence, prominently retained in `cg_arrow004_superseded_repairs.json`, the ledger and ignored local archives. The corrected exposure-matched R4 fixed-ticket comparator earns $17,198.86 IS; it is an uncapped legacy-ticket diagnostic, not a new deployment policy.

**Confidence-attribution metadata repair, declared at 41.87 minutes.** Normalized allocators already assigned one-half weight per unavailable feature, as required. Saved position confidence labels incorrectly used the inherited neutral-control convention. The metadata was corrected and all 23 affected existing books were archived/replayed; total PnL was unchanged in every case. This repairs attribution, not returns or allocations. Added pre-order gross commitment metadata for IWM benchmarks also reproduced the four existing long anchors without economic changes.

The final exact replay compares every prior economic metric and detailed value with current code, rather than comparing totals alone. New explanatory fields are allowed; changed prior economic values require explicit repair review before freeze.

## Full-field and causal history checks

The inherited daily entry rules remain prior close $10–$80 and prior dollar volume at least $10 million, common-stock membership and inherited exchange-traded-product exclusions. The full field is ranked before retaining the top/bottom twenty. The IS rank cache contains 2,249 distinct symbols across 25 signal cohorts; rankable field sizes range from 907 to 1,365. There is no arbitrary ticker cap.

Every cached ranked symbol was checked against the daily entry field, common-stock roster and exclusion list. All 1,000 selected long/short feature rows were recomputed from histories bounded at the signal close. Twenty of 500 long pool slots and 23 of 500 short pool slots lack complete twenty-session history. New reserve admission never treats unknown information as full conviction. The observation-only long ablation explicitly tests how much apparent selection improvement is attributable to available history.

Entry-rule counts and unavailable rank endpoints are separately reported in `cg_arrow004_universe_is.json` and the final all-signal audit. The acquisition price ceiling differs between copied periods ($80 in virgin, $50 in full), so the rankable field is conditional on endpoint availability. No hindsight clean-survivor universe was substituted.

## Missing held-position observations

The initial prepared IS cache covers 87,564 local symbol-days, including full remaining lifecycles and lookbacks; 10,491 have no usable minute summary. Compatible independent copied minute partitions are attempted when canonical files are absent. The long audit specifically examined below-band gaps rather than presuming longs have better coverage.

| Book | Missing minute position-sessions | Last known below $10 | Last known above $80 | Missing terminal gross |
| --- | ---: | ---: | ---: | ---: |
| S0_R4 | 724 | 20 | 609 | 28,950.68 |
| S0_R5 | 724 | 20 | 609 | See results |
| Corrected S4_R4 | 1,030 | 20 | 808 | See results |
| L0 / L4 / L5 | 197 each | 197 each | 0 | See results |
| L5_REC_SELECT8 | 68 | 4 | 0 | 8,012.62 |
| A8_PATIENT_RECOVERY | 68 | 4 | 0 | 7,804.50 |

The patient book's 68 missing-minute position-sessions are all reserve-rank holdings: four have another documented acquisition exclusion and a last-known price below $10; 64 are WGS after May 29 under the later period's price-range acquisition exclusion. The May 21 WGS cohort is still overdue after its June 4 scheduled exit. This is an unresolved data/execution obligation, not a demonstrated halt or successful reset. Final chronological coverage and amounts are published separately; IS counts are not substituted for all-signal coverage.

The source-reason and last-known-price classifications reconcile independently to account stale exposure. The reports distinguish missing observation, delayed observed exit, normal future expiry and overdue terminal inventory. Zero adverse-mark stress reproduces baseline. Hypothetical 10%/50% noncompounding adverse missing-mark errors recompute equity/headroom without inventing fills. They are not confidence bounds or reconstructed prices.

## Bounded local valuation-reference investigation

Long lifecycle analysis found that the eligibility files retain prior-session EOD closes even when minute acquisition excludes a name. The ingestion code copies those values into the following session's row. The national reports are produced at 17:15 and may contain later-session trades; they are not interchangeable with an RTH minute close. The local schema lacks an explicit adjustment declaration. The bounded check therefore preserves the minute-only primary convention and scores a **separate conditional prior-reference valuation sensitivity**, applied uniformly to 22 corresponding short/long controls and candidates. No signals, ranks or missing executions are supplied by these references. [ThetaData EOD documentation](https://docs.thetadata.us/operations/stock_history_eod.html), [ThetaData methodology](https://docs.thetadata.us/Articles/Data-And-Requests/OHLC-EOD.html).

There are 84,449 available prior references in the IS prepared footprint, including 7,687 missing-minute symbol-days. Across 76,401 overlapping observations, median absolute relative difference from the preceding RTH minute mark is 0.052%; the 95th percentile is 0.303% and 99th percentile 0.776%. Five exceed 5%, with a maximum 46.37%. Local national-report timestamps for three large differences show later-session trades; this supports keeping their scope distinct, without filtering inconvenient differences away.

The scenario uses a reference only on its following-session availability date and only for absent minute valuation, retaining actual inventory and recomputing account equity/headroom. Raw-price-unit compatibility remains an explicit assumption. It never supplies a 15:00/15:59 fill. This is neither a newly certified data repair nor a selectable strategy.

| Book | Minute-only baseline IS | Conditional prior-reference IS | Difference |
| --- | ---: | ---: | ---: |
| S0_R4 | 11,602.00 | -58,475.98 | -70,077.98 |
| S0_R5 | 13,086.69 | -18,851.60 | -31,938.29 |
| S1_R4 | 8,679.64 | -61,396.27 | -70,075.91 |
| S1_R5 | 9,114.10 | -26,557.18 | -35,671.27 |
| L5 | 5,992.49 | 5,999.21 | 6.72 |
| L5_REC_SELECT8 | 17,991.64 | 23,278.28 | 5,286.65 |
| A8_PATIENT_RECOVERY | 14,229.88 | 19,305.79 | 5,075.91 |

This materially undermines absolute short economics under stale minute marks. The positive long sensitivity is also kept separate; it is not substituted into the headline to improve it. `cg_arrow004_valuation_reference_audit.json` and `cg_arrow004_reference_sensitivity.json` retain assumptions, discrepancies, all 22 results and local detail hashes. No new subscription, connection credentials, Theta Terminal, bulk ingest, sub-minute tape or source-repository access was used.

## Accounting and public audit boundary

Equity is cash plus long market value minus short market value. Costs reduce both sides. Borrowing sensitivities use prior EOD short liabilities; long debit sensitivities use actual negative cash, and idle yield is zero. Independent cash reconstruction uses original quantities, dated split factors, observed executions and carried marks. All daily, signal-month, calendar-month and realized-plus-terminal totals reconcile.

Minute-risk audits synchronize actual bar-close observations with open-execution boundaries and reconcile every EOD cash/equity/gross value. The finest possessed tape remains foundational; daily EOD references are explicitly secondary diagnostics. Accounting agreement does not validate missing prices, completeness of actions, broker margin, locate availability or executable fills.

Raw source hashes and detailed trade/order ledgers stay under ignored `data/tmp/cg_arrow004`; public artifacts contain safe identities and account aggregates. Sixty-three tracked Arrow 003 code/report/test files were compared with the starting Git snapshot and are unchanged. No Arrow 003 cache or confirmation marker was rewritten.

The stale-mark stress applies its first missing-session shock at end of day; subsequent allocation headroom inherits that mark. It is not an instantaneous first-missing-minute execution stress. Schedule exports distinguish observed exit holding durations from unfinished, censored terminal ages, including daylight-saving elapsed hours.
