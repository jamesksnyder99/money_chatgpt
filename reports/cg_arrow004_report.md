# CG Arrow 004 — completed research and internal confirmation

In-sample (IS) uses odd signal months; out-of-sample (OOS) is reused even-month internal confirmation. All amounts are hypothetical net profit and loss (PnL) after inherited commission/spread, before unverified dividends and baseline financing. Drawdown (DD) is continuous marked equity. End-of-day (EOD) and mark-to-market (MTM) describe valuation checkpoints. Regular trading hours (RTH) and all market clocks use America/New_York. Every book has its own $100,000; no combined funded strategy is asserted.

Start 2026-09-13T23:13:39+00:00; hard deadline 2026-09-14T01:43:39+00:00. Freeze at 115.16 elapsed minutes, committed as `d2987a07efa5739c38696b2a1d5f78a120da58af` before the single reveal. Investor replay completed at 119.60 minutes. Final report checkpoint 120.16 minutes. Exact command, tests and effort closure are in `cg_arrow004_commands.txt` and the final handoff checkpoint. No Arrow 005 was started.

## Main finding

**Both frozen long claims failed internal confirmation and the chronological account comparison. No new policy is accepted by this arrow.** Recovery selection lost $24,247.15 OOS and $10,103.46 ALL; patient recovery lost $10,030.23 OOS and earned only $2,969.67 ALL ($11.83/session), below the commercial references and its IWM benchmark. The fixed-equity and both locked phase comparisons also fail their OOS claims. None replaces the original weekly claim.

The new short utilization mechanisms did not establish a credible improvement over the paired R4/R5 controls in IS; no new short winner was forced into confirmation. A carry startup repair removed an apparent R4 benefit. The protected long laboratory developed recovery selection and selective inactivity, then challenged them with equal sizing, known-level reclaim, path quality, phase, fixed-equity, concentration and missing-mark diagnostics. Negative findings below have the same status as positive screens.

Lifecycle gaps remain outcome-related. Accounting consistency is established separately from investment validity. Long gaps include last-known prices below the entry band; short gaps concentrate above it. Positions are retained until an actual observed authorized exit or as terminal inventory. No hindsight survivor universe, fabricated liquidation, new subscription, credential detour or source-repository access was used. See `cg_arrow004_repairs.md` and coverage artifacts.

A major limitation is the separate prior-national-EOD valuation sensitivity: S0_R4 changes from +$11,602.00 to -$58,475.98 IS and S0_R5 from +$13,086.69 to -$18,851.60. These are conditional valuation scenarios, not replacement headline results or executable exits. Later-session scope and absent adjustment declaration prevent silent baseline substitution. Positive long reference-sensitivity results are likewise kept separate. Absolute short economics under long-lived stale minute marks are heavily DATA-LIMITED. See `cg_arrow004_reference_sensitivity.json`.

## Frozen claims and confirmation

### L5_REC_SELECT8: FROZEN CLAIM DID NOT REPEAT

Frozen ride claim against L5_REC_NORM8: Select eight of the bottom twenty by observed participation/recovery confidence, retaining the same normalized cohort budget. Test whether the combined observed-history and recovery-tier selection gives a smoother ride than the original bottom-eight recovery-weighted portfolio while retaining useful profit. Acceptable tradeoff: At least 85% of positive parent profit, at least 5% lower drawdown, and no reported downside dollar amount more than 5% worse. Lower median-month profit can coexist with this claim. This is not a claim that confidence ranking beats the observation-only OBSERVED_REC_BOTTOM8 control: IS retention versus that ablation is below 85%. IWM-relative and concentration weaknesses remain explicit.

| View | Net PnL | $/session | DD | Parent delta | Numeric claim |
| --- | --- | --- | --- | --- | --- |
| IS | 17,991.64 | 145.09 | -33,133.21 | -1,310.52 | True |
| OOS | -24,247.15 | -190.92 | -34,912.20 | -14,872.64 | False |
| ALL | -10,103.46 | -40.25 | -45,906.59 | -18,883.24 | False |

The claim retains its original comparator and thresholds after reveal. Benchmark-relative profit, capital and data qualifications below can still limit an apparent numeric success.

### A8_PATIENT_RECOVERY: FROZEN CLAIM DID NOT REPEAT

Frozen balanced claim against L5: Buy at most eight fully observed recovery-qualified names from the bottom twenty at strict B/8 per name, leaving unqualified slots idle. Compare useful standalone profit and downside with the L5 mirror anchor at similar realized IS average exposure. Acceptable tradeoff: Material profit gain with at least one material downside improvement and no downside dollar amount more than 5% worse. Similar average exposure to L5 does not mean lower risk on every date: IS minute peak is about $98168 versus $70025 for L5, within the common planning range but explicitly higher. Against the direct fully allocated A6 parent, disclose substantially lower profit in exchange for much lower exposure and drawdown; no 85% retention claim against A6. The high-volume allowance has little isolated IS advantage over PATIENT_MIRROR, and this finalist does not claim otherwise.

| View | Net PnL | $/session | DD | Parent delta | Numeric claim |
| --- | --- | --- | --- | --- | --- |
| IS | 14,229.88 | 114.76 | -18,041.80 | 8,237.39 | True |
| OOS | -10,030.23 | -78.98 | -20,658.69 | -6,145.80 | False |
| ALL | 2,969.67 | 11.83 | -26,425.26 | 1,150.72 | False |

The claim retains its original comparator and thresholds after reveal. Benchmark-relative profit, capital and data qualifications below can still limit an apparent numeric success.

## Ranked short discovery — core specifications and declared neighbors

| Policy | Net PnL | $/session | DD | Utilization | Primary comparator |
| --- | --- | --- | --- | --- | --- |
| S1_R5_B | 15,224.81 | 122.78 | -14,833.09 | 45.35% | S0_R5_B |
| S1_R5_U125 | 11,654.31 | 93.99 | -22,834.38 | 44.72% | S0_R5_U125 |
| S3_R4_U125 | 10,642.00 | 85.82 | -30,936.76 | 55.00% | NORM8_R4_U125 |
| S1_R5 | 9,114.10 | 73.50 | -18,653.37 | 44.66% | S0_R5 |
| S1_R4 | 8,679.64 | 70.00 | -27,697.54 | 54.40% | S0_R4 |
| S3_R4 | 8,534.34 | 68.83 | -25,410.56 | 55.12% | NORM8_R4 |
| S3_R4_A | 8,200.09 | 66.13 | -31,482.84 | 48.47% | NORM8_R4_A |
| S4_FULL_R5 | 7,299.72 | 58.87 | -19,152.67 | 50.90% | S1_R5 |
| S4_R5 | 6,389.17 | 51.53 | -19,152.67 | 50.87% | S1_R5 |
| S3_R4_B | 5,888.34 | 47.49 | -24,603.89 | 60.40% | NORM8_R4_B |
| S2_R4 | 3,495.01 | 28.19 | -24,303.23 | 54.41% | S0_R4 |
| S2_R5 | 2,833.22 | 22.85 | -24,129.35 | 54.33% | S0_R5 |
| S4_FULL_R4 | 1,231.80 | 9.93 | -26,745.71 | 62.41% | S1_R4 |
| S3_R5 | -406.40 | -3.28 | -26,206.47 | 54.22% | NORM8_R5 |
| S1_R5_A | -2,296.14 | -18.52 | -25,759.13 | 38.68% | S0_R5_A |
| S4_R4 | -2,410.48 | -19.44 | -25,487.38 | 62.37% | S1_R4 |

Full specifications, red-month loss sums, worst/median month, worst day, underwater duration, concentration, scenarios and individual dispositions are retained in `cg_arrow004_discovery.json`. Derived phase/utilization neighbors are counted separately from core policies; controls, replays and scenarios are not new discoveries.

## Ranked long discovery — core specifications and declared neighbors

| Policy | Net PnL | $/session | DD | Utilization | Primary comparator |
| --- | --- | --- | --- | --- | --- |
| A6_RECOVERY_EQUAL | 18,689.33 | 150.72 | -32,772.83 | 48.04% | L5_REC_SELECT8 |
| L5_REC_SELECT8 | 17,991.64 | 145.09 | -33,133.21 | 47.88% | L5_REC_NORM8 |
| A5_RECOVERY_VOTES | 16,401.80 | 132.27 | -32,991.16 | 48.00% | L5_REC_SELECT8 |
| A8_PATIENT_RECOVERY | 14,229.88 | 114.76 | -18,041.80 | 22.53% | A6_RECOVERY_EQUAL |
| A4_ADVANCING_DAYS | 11,841.60 | 95.50 | -34,364.08 | 47.99% | L5_SELECT8 |
| L5_WEIGHT20 | 10,412.65 | 83.97 | -29,085.93 | 48.68% | LONG_EQ20 |
| A9_QUIET_RECOVERY | 10,400.74 | 83.88 | -31,781.64 | 50.98% | A6_RECOVERY_EQUAL |
| L5_RECOVERY | 6,336.94 | 51.10 | -20,903.27 | 25.54% | L5 |
| A3_STABLE_PATH | 5,637.06 | 45.46 | -34,719.38 | 47.85% | L5_SELECT8 |
| A2_RECLAIM_HIGH | 4,475.47 | 36.09 | -30,280.82 | 50.57% | L5_SELECT8 |
| L5_RESERVE | 3,254.70 | 26.25 | -24,945.05 | 35.76% | L5 |
| A10_RECLAIM_MEAN | 3,191.49 | 25.74 | -31,698.72 | 51.08% | A6_RECOVERY_EQUAL |
| A11_PERSISTENT_QUIET | 2,840.73 | 22.91 | -18,074.73 | 20.00% | PATIENT_MIRROR |
| L5_SELECT8 | 1,063.65 | 8.58 | -37,447.13 | 48.00% | L5_NORM8 |
| A12_MINUTE_RECOVERY | 733.92 | 5.92 | -26,834.43 | 51.32% | A6_RECOVERY_EQUAL |
| L4_RECOVERY | 318.31 | 2.57 | -32,172.48 | 42.15% | L4 |
| A1_MILD_LOSERS | -470.18 | -3.79 | -35,406.13 | 49.12% | L5_NORM8 |
| A7_MIDDLE_LOSERS | -19,985.79 | -161.18 | -41,248.05 | 48.66% | EQ_MILD_LOSERS |

Full specifications, red-month loss sums, worst/median month, worst day, underwater duration, concentration, scenarios and individual dispositions are retained in `cg_arrow004_discovery.json`. Derived phase/utilization neighbors are counted separately from core policies; controls, replays and scenarios are not new discoveries.

## Fixed-equity and phase falsification

| Finalist | Configuration | Matched control | IS claim | OOS claim | ALL claim |
| --- | --- | --- | --- | --- | --- |
| L5_REC_SELECT8 | fixed_reference_equity | FIXE_L5_REC_NORM8 | True | False | False |
| L5_REC_SELECT8 | phase_A | L5_REC_NORM8_A | True | False | False |
| L5_REC_SELECT8 | phase_B | L5_REC_NORM8_B | False | False | False |
| A8_PATIENT_RECOVERY | fixed_reference_equity | FIXE_L5 | True | False | False |
| A8_PATIENT_RECOVERY | phase_A | L5_A | False | False | False |
| A8_PATIENT_RECOVERY | phase_B | L5_B | False | False | False |

These are locked explanatory comparisons. They cannot replace a failed weekly claim or select a favorable phase after reveal. Secondary ablations and direct-parent differences are separately retained in `secondary_comparator_differences`.

## Controls and all-signal capital

| Policy | IS PnL | OOS PnL | ALL PnL | ALL $/session | ALL DD |
| --- | --- | --- | --- | --- | --- |
| BRIDGE_R4 | 12,261.13 | 53,052.86 | 65,313.99 | 260.22 | -20,365.80 |
| BRIDGE_R5 | 18,071.93 | 51,978.68 | 70,050.60 | 279.09 | -24,276.08 |
| S0_R4 | 11,602.00 | 71,987.14 | 70,811.62 | 282.12 | -27,461.14 |
| S0_R5 | 13,086.69 | 42,907.72 | 58,967.26 | 234.93 | -20,724.39 |
| L0 | -1,191.61 | -12,471.40 | -13,514.48 | -53.84 | -34,748.01 |
| L4 | -470.50 | -5,512.40 | -6,113.25 | -24.36 | -35,014.67 |
| L5 | 5,992.49 | -3,884.43 | 1,818.95 | 7.25 | -22,794.01 |
| L5_A | 1,748.68 | 11,839.94 | 13,727.49 | 54.69 | -29,543.42 |
| L5_B | 9,465.95 | -18,876.28 | -11,319.85 | -45.10 | -32,865.11 |
| LONG_EQ20 | 8,290.50 | -15,725.39 | -9,871.56 | -39.33 | -29,236.39 |
| L5_REC_NORM8 | 19,302.16 | -9,374.51 | 8,779.78 | 34.98 | -47,575.46 |
| A6_RECOVERY_EQUAL | 18,689.33 | -22,147.10 | -7,424.80 | -29.58 | -41,301.12 |
| PATIENT_MIRROR | 14,013.66 | -9,234.00 | 3,463.57 | 13.80 | -26,844.63 |
| OBSERVED_REC_BOTTOM8 | 22,596.21 | -7,292.16 | 16,603.85 | 66.15 | -40,341.99 |
| FIXE_L5 | 6,804.72 | -2,998.26 | 3,806.46 | 15.17 | -21,404.42 |
| FIXE_L5_REC_NORM8 | 21,976.81 | -6,319.36 | 14,103.26 | 56.19 | -38,187.60 |
| FIXE_L5_REC_SELECT8 | 20,760.61 | -22,414.63 | -348.28 | -1.39 | -44,425.71 |
| FIXE_A8_PATIENT_RECOVERY | 14,346.93 | -8,970.26 | 5,762.59 | 22.96 | -24,714.01 |
| L5_REC_NORM8_A | 15,511.06 | 2,843.19 | 21,319.67 | 84.94 | -60,423.58 |
| L5_REC_NORM8_B | 2,765.45 | -24,775.86 | -21,123.33 | -84.16 | -54,904.30 |
| L5_REC_SELECT8_A | 17,080.61 | -28,964.35 | -16,844.30 | -67.11 | -52,216.52 |
| L5_REC_SELECT8_B | 16,133.69 | -20,251.34 | -5,001.15 | -19.92 | -46,631.24 |
| A8_PATIENT_RECOVERY_A | 7,264.35 | 541.12 | 7,819.84 | 31.15 | -36,420.49 |
| A8_PATIENT_RECOVERY_B | 21,445.80 | -19,932.43 | -2,358.62 | -9.40 | -28,492.44 |
| L5_REC_SELECT8 | 17,991.64 | -24,247.15 | -10,103.46 | -40.25 | -45,906.59 |
| A8_PATIENT_RECOVERY | 14,229.88 | -10,030.23 | 2,969.67 | 11.83 | -26,425.26 |

ALL is one chronological account with actual cross-cohort headroom interactions. Its profit differs from adding isolated IS/OOS books; those differences are explicitly published in `chronological_minus_sum_is_oos`. Flat sessions remain in denominators: 124 IS, 127 OOS, 251 ALL. Isolated weekly books receive no missing-cohort top-up.

| Policy | Avg gross | 95% gross | Peak EOD gross | Utilization | Unused target | Days >130k | Peak gross/E | Terminal/stale |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S0_R4 | 95,612.65 | 122,165.42 | 125,735.72 | 81.71% | 21,483.13 | 0 | 107.93% | 119,908.67/55,782.77 |
| S0_R5 | 64,907.88 | 98,672.81 | 108,821.92 | 56.60% | 49,761.18 | 0 | 80.44% | 98,672.81/33,407.77 |
| L0 | 92,918.37 | 106,311.76 | 111,386.63 | 97.70% | 2,186.29 | 0 | 100.02% | 86,450.25/14,764.89 |
| L4 | 81,379.84 | 99,569.96 | 109,590.74 | 81.08% | 18,990.13 | 0 | 99.96% | 93,853.13/11,245.18 |
| L5 | 50,921.96 | 66,476.91 | 68,347.43 | 49.54% | 51,866.90 | 0 | 68.14% | 62,922.90/9,056.57 |
| L5_REC_SELECT8 | 90,729.32 | 109,981.14 | 116,240.08 | 97.34% | 2,476.83 | 0 | 100.03% | 89,832.76/6,815.93 |
| A8_PATIENT_RECOVERY | 45,879.86 | 84,398.63 | 111,884.49 | 45.62% | 54,700.56 | 0 | 95.67% | 52,890.26/7,284.20 |

Target headroom is neither interest-eligible cash nor broker buying power. New aggregate symbol orders are capped at 20% of positive current equity; later price drift is retained. Exposure duration, dollar-days, causes, occupancy, overlap, tickets, turnover and margin debit are in results/daily aggregates; synchronized minute results are in `cg_arrow004_minute_all.json`. Immediate post-entry gross at known surviving marks plus actual new fills is reported separately, including target overshoot and allocations above $130k. The $130k planning range is not a forced liquidation threshold.

## Long benchmark and financing

| Long policy | View | Stock PnL minus IWM | Stock avg gross | IWM avg gross | Stock DD | IWM DD |
| --- | --- | --- | --- | --- | --- | --- |
| L0 | IS | -11,192.54 | 50,242.93 | 45,788.61 | -30,748.32 | -9,331.48 |
| L0 | OOS | -16,805.71 | 48,952.11 | 45,673.68 | -26,567.03 | -7,829.17 |
| L0 | ALL | -26,553.05 | 92,918.37 | 85,766.34 | -34,748.01 | -10,313.52 |
| L5 | IS | -243.07 | 25,375.48 | 24,187.53 | -19,831.12 | -5,085.61 |
| L5 | OOS | -4,929.89 | 24,645.00 | 23,223.70 | -15,112.68 | -3,977.58 |
| L5 | ALL | -5,355.08 | 50,921.96 | 48,295.83 | -22,794.01 | -7,283.41 |
| L5_REC_SELECT8 | IS | 6,830.58 | 53,420.78 | 51,484.78 | -33,133.21 | -10,932.56 |
| L5_REC_SELECT8 | OOS | -28,159.08 | 41,365.32 | 41,663.03 | -34,912.20 | -7,113.41 |
| L5_REC_SELECT8 | ALL | -23,837.52 | 90,729.32 | 89,377.22 | -45,906.59 | -11,408.55 |
| A8_PATIENT_RECOVERY | IS | 7,008.41 | 24,809.39 | 22,778.35 | -18,041.80 | -4,844.25 |
| A8_PATIENT_RECOVERY | OOS | -12,078.48 | 20,709.75 | 20,879.19 | -20,658.69 | -5,038.51 |
| A8_PATIENT_RECOVERY | ALL | -6,063.02 | 45,879.86 | 44,160.86 | -26,425.26 | -7,179.63 |

Same pre-order gross commitment and prescribed clock; actual gross mismatch due to missing stock fills, gaps, integer shares and delayed held-stock exits. Not an exact daily risk match. IWM is a diagnostic benchmark, exempt from the strategy common-stock restriction and 20% single-name safeguard. It is not an additional funded engine. Positive raw long PnL alone is not stock-selection alpha.

| Policy | Base ALL | Double spread | 10% borrow / 5% debit | 30% borrow / 10% debit |
| --- | --- | --- | --- | --- |
| S0_R4 | 70,811.62 | 66,874.74 | 61,253.70 | 42,137.85 |
| S0_R5 | 58,967.26 | 56,201.83 | 52,476.46 | 39,494.87 |
| L0 | -13,514.48 | -18,032.69 | -13,514.52 | -13,514.56 |
| L4 | -6,113.25 | -10,180.44 | -6,113.25 | -6,113.25 |
| L5 | 1,818.95 | -723.57 | 1,818.95 | 1,818.95 |
| L5_REC_SELECT8 | -10,103.46 | -14,756.47 | -10,103.53 | -10,103.60 |
| A8_PATIENT_RECOVERY | 2,969.67 | 656.75 | 2,969.67 | 2,969.67 |

Commission stays unchanged in doubled-spread scenarios. Short borrowing uses preceding end-of-day short value by calendar days; long financing uses actual negative cash, with no short-loan charge on long assets. These frozen sensitivities do not resize trades, and idle yield is zero. Missing dividend entitlement/obligation and incomplete corporate-action coverage remain unresolved.

## Twelve actual calendar-month returns

| Month | S0_R4 | S0_R5 | L5 | L5_REC_SELECT8 | A8_PATIENT_RECOVERY |
| --- | --- | --- | --- | --- | --- |
| 2025-09 | -8.10% | -3.78% | 0.28% | 2.79% | 0.19% |
| 2025-10 | 25.23% | 16.48% | 6.55% | 4.06% | 0.94% |
| 2025-11 | 0.82% | 1.49% | -6.13% | -21.68% | -5.28% |
| 2025-12 | -4.12% | -4.08% | -6.44% | -9.60% | -7.15% |
| 2026-01 | -1.20% | -1.27% | 5.45% | 13.33% | 6.62% |
| 2026-02 | 1.79% | -0.92% | -3.93% | -5.03% | -3.57% |
| 2026-03 | 12.95% | 11.29% | 7.24% | 13.75% | 9.86% |
| 2026-04 | 0.60% | -0.69% | 8.62% | 16.35% | 13.46% |
| 2026-05 | 4.71% | 5.71% | 2.69% | -4.96% | -5.39% |
| 2026-06 | 10.74% | 13.30% | -0.14% | -2.53% | -3.47% |
| 2026-07 | 10.77% | 7.45% | -13.91% | -20.01% | -6.93% |
| 2026-08 | 4.60% | 4.72% | 4.15% | 12.47% | 6.28% |

Returns use each month’s actual starting equity. Starting equity, ending equity and dollar PnL for every frozen book are in `calendar_months` in the results file; signal-owned months are separately labeled `months`. Realized PnL plus retained terminal net mark-to-market reconciles with all daily/calendar totals.

## Schedule, robustness and interpretation

Nominal Thursdays remain globally anchored. Entry is the exact final RTH minute OPEN, with quantity determined from the preceding completed mark. Exit is the first observed OPEN at/after one hour before the close, two nominal Thursdays later. Holidays map at/before nominal dates; November 27 maps to November 26, and December 25 maps to the December 24 early close (12:00 exit / 12:59 entry). Every nominal schedule row, phase, duration, filled/missed/delayed count and outstanding cash/gross obligation is in `cg_arrow004_schedule.csv`.

The ordinary September 4 / September 11 / September 18 illustration is retained in the results file: at the third replacement the September 11 cohort survives while the September 4 cohort is due. Pending exits retain capacity until actually observed; there is no accumulated unused-credit balance.

Both biweekly phases are reported separately, with global phase anchors. Short phase luck is substantial; patient-long phase A/B also differs sharply. Recovery selection improves DD and profit retention in both IS phases, but phase B worsens its worst day beyond the frozen ride tolerance. No better phase was chosen from confirmation. Fixed-reference-equity comparators isolate compounding; exposure-matched legacy controls are explicitly counterfactual diagnostics, not capped deployment policies.

IS leave-one-month-out and top-contributor diagnostics are fragility checks, not edited strategy books or new validation. Recovery selection changes membership substantially but its parent-relative profit increment is negative in four of six IS signal months; its frozen thesis is a smoother ride with retained profit, not uniform extra return. Equal sizing has only a small fragile gain over the same selected names. The middle-loser window, reclaim-level, quiet-recovery, persistent-participation and minute-bar recovery branches failed to establish a better long mechanism. All launched branches were closed.

Ablations limit the interpretation: OBSERVED_REC_BOTTOM8 earns $22,596.21 IS with $35,856.87 DD, showing that excluding unavailable histories explains much apparent improvement over the original parent. PATIENT_MIRROR earns $14,013.66 with $16,804.10 DD; the high-volume allowance adds only $216.22 to the patient book while increasing DD. Neither finalist claims that these isolated submechanisms have established incremental alpha. Both finalists lose their IWM-relative advantage when the strongest IS signal month is left out, and removing their top three positive symbol contributors erases positive total profit.

Within the already scored equal-dollar bottom-twenty book, recovery-full versus other ticket returns have only a 0.12 percentage-point mean within-cohort advantage and are positive in half of 22 comparable cohorts. Known-history versus unknown-history differences are much larger. These descriptive state comparisons are not randomized effects or independent significance tests; all original lifecycle treatment remains. See `cg_arrow004_pool_evidence.json` and `cg_arrow004_long_evidence_is.json`.

Descriptive full-account daily long/short correlations: L5_REC_SELECT8/S0_R4 -0.326, L5_REC_SELECT8/S0_R5 -0.347, A8_PATIENT_RECOVERY/S0_R4 -0.225, A8_PATIENT_RECOVERY/S0_R5 -0.248. These are not joint-capital or portfolio-diversification certification.

The $300–$500/day ambition and $200/day slate / $100/day engine references remain visible. Component improvements below those references may warrant further research; this run does not certify commercial success, executable fills, margin capacity or deployment readiness. No unrelated model or next arrow was started.


## Completed account audit and actual holding durations

All 32 chronological books independently reconcile cash, gross and equity; 16 key books also reconcile all 251 sessions from synchronized minute marks. The full suite passes **549 tests** (15.62 seconds); 32 Arrow 004 focused tests passed before freeze. The full-field audit covers all 52 signals and 1,040 long plus 1,040 short pool slots. All 63 inherited evidence files remain unchanged. No economic code changed after freeze.

| ALL book | Minute peak gross | Minute DD | Minutes above $130k | Largest symbol / equity |
| --- | ---: | ---: | ---: | ---: |
| S0_R4 | 127,329.77 | -32,575.14 | 0 | 19.77% |
| S0_R5 | 109,638.02 | -25,429.85 | 0 | 15.32% |
| L5_REC_NORM8 | 138,997.79 | -50,187.62 | 5705 | 36.78% |
| L5_REC_SELECT8 | 121,007.35 | -51,645.62 | 0 | 21.46% |
| A8_PATIENT_RECOVERY | 111,884.49 | -28,350.79 | 0 | 15.95% |
| OBSERVED_REC_BOTTOM8 | 145,847.65 | -46,994.61 | 7512 | 36.33% |

The selected finalist's ALL minute drawdown is worse than its normalized parent even though its EOD drawdown is slightly smaller; minute marks strengthen the negative conclusion. The parent and observation-only control have materially larger and persistent excursions: roughly 14.6 and 19.3 full-session equivalents above $130k, respectively. Their peaks approach $139k and $146k, and largest-name exposure exceeds 36% of equity after price drift. These controls are retained as higher-exposure research, with no retrospective rescaling or promotion. Minute sampling and carried missing marks do not certify tick-level maxima or margin.

| ALL book | Filled | Missed entry | Delayed exit fills | Longest observed completed hold, calendar days | Oldest terminal age, calendar days |
| --- | ---: | ---: | ---: | ---: | ---: |
| S0_R4 | 409 | 7 | 9 | 70 | 354 |
| S0_R5 | 409 | 7 | 9 | 70 | 354 |
| L5_REC_SELECT8 | 416 | 0 | 0 | 15 | 102 |
| A8_PATIENT_RECOVERY | 186 | 0 | 0 | 15 | 102 |

Completed holding durations use actual observed exit timestamps, including daylight-saving offsets; unfinished holdings have separate censored ages and no fabricated exit. Every row also reports actual min/median/max intervening sessions and elapsed hours. A long completed hold can be 15 calendar days because of holiday mapping. Missing short exits extend some completed holds to 70 days and leave an unresolved holding aged 354 days. Each short baseline has 1,088 stale position-sessions, 966 with last-known prices above $80. The original-bottom-eight long anchors have 433 stale position-sessions, 419 last known below $10. Each finalist has 68 stale position-sessions and one overdue terminal holding aged 102 days. Other terminal tickets are ordinary not-yet-due cohorts.

The patient ALL book has seven empty allocations and averages 3.58 fills per scheduled cohort; it uses about 45.0% of intended weekly budgets. Selective inactivity was implemented and tested, but it did not establish useful incremental economics. Its ALL benchmark increment is -$6,063.02 and recovery selection's is -$23,837.52. Removing the three largest positive symbol contributors leaves both negative. These are descriptive arithmetic checks, without omitted dates or changed trades.

An ordinary three-Thursday sequence for R4 illustrates the retained cohort:

| Entry Thursday | Due cohort | Prior-week cohort retained | Surviving gross before entry | New cohort budget |
| --- | --- | --- | ---: | ---: |
| September 4, 2025 | None | None | 0.00 | 50,000.00 |
| September 11, 2025 | None | September 4 | 35,821.52 | 49,202.07 |
| September 18, 2025 | September 4 | September 11 | 31,422.96 | 48,321.62 |

On September 18, R4 cash moves from $164,755.41 before due covers to $128,066.20 afterward, while the surviving cohort remains a $31,422.96 liability at pre-order marks. Equity is $96,643.25, not that cash balance. The long L5 mirror instead receives cash from its due sale: $60,944.53 becomes $83,342.67, with $16,260.64 surviving long value and $99,603.31 equity. Detailed aggregate examples remain in results.

Research effort estimates are approximately 25 minutes of substantive short work and 55-60 minutes of substantive long discovery/falsification, within a roughly 78-minute long-phase elapsed window. These are retrospective work-category estimates, not instrumented CPU time; shared engineering, identity replays and report preparation are excluded. There were 28 new core specifications (10 short, 18 long), six short rhythm/utilization neighbors, and 77 controls/ablations/benchmarks. Twelve long branches were investigator-originated. The negative outcome closes Arrow 004; it does not authorize another arrow.

## Audit trail

The committed freeze, exact-replay proof, independent cash audits, full-field causal-feature audit, inherited-file identities, minute-risk checks and focused/full tests form separate evidence. Detailed orders, position ledgers and source summaries remain under ignored local `data/tmp/cg_arrow004`, referenced by safe paths and SHA-256 hashes. Public reports contain account aggregates, not raw vendor bars. Final command/test/public-review and push equality details are recorded in `cg_arrow004_commands.txt` and the closure checkpoint.
