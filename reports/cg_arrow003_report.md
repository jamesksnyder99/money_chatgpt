# CG Arrow 003 — R4/R5 continuation

IS = in-sample (odd signal months); OOS = out-of-sample (even signal months); PnL = profit and loss; MTM = marked-to-market; DD = drawdown; RTH = regular trading hours; EOD = end of day; ATR = Average True Range.

## Verdict

Completed 44 new policy hypotheses (12 astra, 18 derived, 14 directed), with 33 IS controls and separate diagnostics. All directed C1–C6 core tests closed. 4 distinct new finalists were frozen before the single confirmation batch. No Arrow 004 or unrelated engine was started.

These are conditional research results. Eight documented reverse splits received common as-of repairs; the split reference is still incomplete. Missing future exits no longer erase entries: unresolved positions remain in the book with stale valuations. Copied acquisition price bands caused known lifecycle gaps, potentially associated with adverse short moves; **absolute complete economics are not established**. Starting equity is $100,000, intended ticket sizes do not compound, and approximately $130,000 gross is a soft planning range, not a deposit or margin guarantee.

**Overall economic verdict: INCONCLUSIVE/DATA-LIMITED.** The relative numerical verdicts below describe fixed policies under the common incomplete-tape convention. They do not certify complete economics. No finalist reaches the $300–$500 full-account daily ambition even at zero modeled borrow, and none establishes an independent low-correlation engine.

The most useful repeated conservative tradeoff is F2, the $7,000-base observed-history R5 policy. It retains 94.2% of original R5 profit in IS and 86.7% in OOS, with smaller drawdown and worst day in both. Its chronological account earns $61,394.77 ($244.60/session), versus R5's $68,921.14 ($274.59/session); EOD drawdown is $19,626.13 versus $22,496.36. This is a lower-risk, lower-profit choice, not a dominant winner. At 10%/30% annualized borrow its modeled profit falls to $217.87/$164.41 per session.

The simpler F1 late cover fails to repeat its balanced objective: the IS gain of $2,003.96 becomes an OOS loss of $1,067.71 versus R5. F3's return direction partially repeats, but its $1,362.52 OOS increment is only 2.88%, below the frozen 5% materiality guide; its worst signal month worsens 15.25%, just beyond its declared 15% tolerance. Its $282.53/day all-signal result remains below the commercial ambition. F4 repeats a conservative ride improvement versus original R4 and has three losing calendar months versus R4's four, but the same-size comparison below does not confirm a new cover edge.

| Finalist | Plain-English policy | Same comparator | Primary objective | Confirmation |
|---|---|---|---|---|
| F1 — `AR9_R5_LATE_COVER_PACED` | Original R5 sizing; one half-cover on a profitable late rebound in low initial participation; causal 130k new-order pacing. | R5 | balanced | **NOT REPEATED** |
| F2 — `AR12_R5_OBSERVED_CONSERVATIVE` | Conservative 7000-base R5; advancing-day votes only with observed 20-session history, original switch otherwise; late half-cover and pacing. | R5 | ride | **REPEATED** |
| F3 — `AR11_R5_OBSERVED_VOTES_COVER` | Original 8300-base R5 with observed-history advancing-day votes, the same late half-cover, and causal pacing. | R5 | return | **PARTIALLY REPEATED** |
| F4 — `AR10_R4_CONSERVATIVE_COVER_PACED` | Conservative 4650-base R4 participation sizing; late low-participation half-cover and causal pacing. | R4 | ride | **REPEATED** |

The ranking and objectives above were set before confirmation. The numerical classifier is shared by IS and OOS; it has no hard gross-exposure veto. Five-percent monetary changes are descriptive materiality guides, not statistical proofs. The same even months were inspected in earlier work; this is reused internal confirmation, not pristine validation.

## Common repairs and negative findings

[Repair reconciliation](cg_arrow003_repairs.md) separates legacy, accounting-only, and action-adjusted working controls. The original PARENT/R4/R5 daily legacy curves reproduced exactly; earlier reports, tests and freeze evidence remain unchanged. All new comparisons use the working convention.

The median-volume reference and three-session participation persistence lost useful profit. Smooth volume penalties generally raised exposure and worsened the measured tradeoff. Updating volume at entry weakened R4; the observed loss was mainly from upgrading tickets after the signal. Relative participation ranks and final-hour volume-share sizing were weaker than the relevant controls. Drawdown-sensitive new allocations reduced losses but sacrificed substantial rebound profit. Profitable dominated variants remain in the ledger and frontier; they are not erased or called universal mechanism failures.

The apparent momentum-taper improvement was driven by neutral sizing when 20-session volatility was unavailable. On the 182 trades with usable volatility, the taper lost $1,837.98 versus R5; the 15 missing-history trades added $8,554.73. Preserving the original momentum switch on missing history removed the apparent improvement. This dependency is distinct from evidence that a smooth momentum curve helps.

The advancing-day-vote rule also depended partly on sparse histories: $2,004.54 of its $3,122.85 IS increment came from 15 missing-history tickets, while 182 observed histories added $1,118.31. The final observed-history versions retain original R5 sizing on sparse histories. Votes and covers are not independent edges: the unpaced combined increment was $587.54 below the sum of their separate increments. After the history fallback and pacing, the full-size combination adds only about $542 beyond the simpler paced cover policy, with a worse worst day. This modest extra benefit is a material qualification of the return challenger.

The second-half half-cover for low initial participation was more useful than the original high-volume-upturn overlay. A one-session-later neighbor preserved the IS direction. The every-minute trigger comparison lost profit and slightly worsened DD relative to the 15:55 checkpoint for both R4 and R5; this supports the checkpoint's anti-twitch role on this IS sample while retaining one-minute executable prices.

Further ablations showed that removing the low-initial-participation restriction still improved both R4 and R5: it sacrificed some profit for slightly better downside. Moving the original high-current-participation C5 rule to day 6 also improved profit. The evidence therefore supports a late management tradeoff; it does not establish that the low-volume clause uniquely causes the benefit. Halving new R5 orders when the current open book was losing sacrificed too much profit, like the earlier high-water-mark rule.

Holding age is indexed from zero on entry. The original exploratory overlays managed through age 9 and retained the age-10 backstop. A separate literal directed C5 test allowed the half-cover through age 10 inclusive: R4/R5 IS profits were $14,837.74/$22,025.08, slightly below the earlier age-9-ending versions. The frozen Astra-derived covers explicitly retain their tested ages 6–9; no boundary convention is changed after reveal.

The deterministic within-signal-batch size shuffles were diagnostics, not strategies or independent statistical validation. None of 64 shuffles per family reached the actual R4/R5 IS profit. This association does not certify corporate-action completeness, borrow economics or future returns.

## Signal-cohort training and confirmation

These totals include each signal cohort's complete observed lifecycle and terminal MTM through August 31. They are **not actual calendar-month account returns**. Profit/session divides by the 124 IS or 127 OOS signal-month sessions; drawdown and exposure walk the full uninterrupted 251-session calendar. Unless labeled minute-sampled, drawdown uses consecutive end-of-day marked equity, including all intervening sessions.

### IS

| Book | Profit | $/session | Red months / loss sum | Worst / median month | Drawdown | Worst day | Mean / peak gross |
|---|---:|---:|---:|---:|---:|---:|---:|
| PARENT | 6,450.99 | 52.02 | 2 / -23,996.95 | -15,258.42 / 5,910.71 | -26,627.08 | -4,659.12 | 41,640.85 / 109,204.27 |
| R4 | 14,078.45 | 113.54 | 2 / -19,134.21 | -10,920.95 / 6,203.26 | -21,815.66 | -4,762.13 | 40,160.23 / 114,064.92 |
| R5 | 21,662.04 | 174.69 | 2 / -16,602.92 | -9,394.61 / 5,665.04 | -18,762.71 | -5,302.88 | 40,503.65 / 119,319.56 |
| A4 | 11,018.61 | 88.86 | 2 / -14,849.19 | -8,470.89 / 4,835.12 | -16,930.70 | -3,684.69 | 31,148.74 / 88,490.04 |
| R1 | 10,453.11 | 84.30 | 2 / -7,963.54 | -4,502.79 / 2,721.24 | -9,001.46 | -2,549.44 | 19,412.47 / 57,327.90 |
| F1 | 23,666.00 | 190.85 | 2 / -15,134.21 | -9,170.01 / 6,034.26 | -17,295.84 | -5,322.09 | 39,924.16 / 117,957.96 |
| F2 | 20,406.02 | 164.56 | 2 / -12,942.57 | -7,553.48 / 5,066.22 | -15,089.03 | -4,943.66 | 34,688.21 / 93,662.26 |
| F3 | 24,207.72 | 195.22 | 2 / -15,347.70 | -8,939.86 / 6,003.12 | -17,893.58 | -5,868.41 | 41,218.83 / 111,290.46 |
| F4 | 14,662.60 | 118.25 | 2 / -16,187.04 | -9,564.94 / 5,938.76 | -18,613.09 | -4,291.56 | 35,695.85 / 101,421.07 |

### OOS — one frozen batch

| Book | Profit | $/session | Red months / loss sum | Worst / median month | Drawdown | Worst day | Mean / peak gross |
|---|---:|---:|---:|---:|---:|---:|---:|
| PARENT | 31,866.20 | 250.91 | 3 / -19,709.40 | -10,800.49 / 2,542.92 | -26,363.29 | -5,268.59 | 39,230.05 / 102,456.47 |
| R4 | 44,962.24 | 354.03 | 3 / -15,745.49 | -8,969.17 / 2,977.24 | -23,716.06 | -6,559.51 | 37,982.25 / 106,545.47 |
| R5 | 47,259.10 | 372.12 | 3 / -20,120.42 | -11,155.31 / 3,198.50 | -29,214.53 | -5,426.77 | 37,741.55 / 122,299.06 |
| A4 | 34,869.47 | 274.56 | 3 / -12,232.59 | -6,954.92 / 2,302.83 | -18,413.81 | -5,087.66 | 29,512.69 / 82,734.85 |
| R1 | 22,664.57 | 178.46 | 3 / -9,710.16 | -5,365.49 / 1,522.40 | -14,074.36 | -2,614.33 | 18,101.75 / 58,859.82 |
| F1 | 46,191.39 | 363.71 | 3 / -20,047.49 | -11,351.12 / 3,011.41 | -29,136.49 | -5,415.60 | 37,246.87 / 121,782.87 |
| F2 | 40,988.75 | 322.75 | 3 / -17,044.54 | -10,844.33 / 3,466.46 | -24,895.65 | -4,467.47 | 32,367.60 / 108,990.96 |
| F3 | 48,621.62 | 382.85 | 3 / -20,228.40 | -12,857.01 / 4,105.22 | -29,513.49 | -5,296.68 | 38,408.34 / 129,225.69 |
| F4 | 39,412.03 | 310.33 | 3 / -14,244.04 | -8,336.43 / 2,759.01 | -21,382.46 | -5,854.16 | 33,825.00 / 96,189.35 |

### Increment and repetition against the same comparator

| Finalist | Comparator | IS increment / session | OOS increment / session | OOS downside changes: red loss / worst month / DD / worst day | Numeric result |
|---|---|---:|---:|---|---|
| F1 | R5 | 16.16 | -8.41 | 0.36% / -1.76% / 0.27% / 0.21% | NOT REPEATED |
| F2 | R5 | -10.13 | -49.37 | 15.29% / 2.79% / 14.78% / 17.68% | REPEATED |
| F3 | R5 | 20.53 | 10.73 | -0.54% / -15.25% / -1.02% / 2.40% | PARTIALLY REPEATED |
| F4 | R4 | 4.71 | -43.70 | 9.54% / 7.05% / 9.84% / 10.75% | REPEATED |

Positive downside percentages mean improvement; negative values mean worse losses. A materially weaker monthly ride is not excused by the softer exposure policy. Absolute and percentage differences against PARENT, R4, R5 and the frozen size controls are retained in the machine-readable results.

### What remains after controlling for size

These comparisons were frozen before reveal. They qualify mechanism claims without changing the primary comparator or the confirmation verdict.

| Finalist | Frozen size comparator | IS profit increment | OOS profit increment | Chronological account increment | Main qualification |
|---|---|---:|---:|---:|---|
| F1 | Plain R5 base $8,175, IS exposure match | 2,386.14 | -353.48 | 1,382.36 | Cover gain does not repeat in confirmation. |
| F2 | Plain R5 base $7,000 | 2,177.61 | 1,162.75 | 3,340.37 | OOS worst signal month is 15.08% worse; OOS DD is also slightly worse. Much of the ride improvement versus full-size R5 comes from smaller sizing. |
| F3 | Plain R5 base $8,450, IS exposure match | 2,161.79 | 476.39 | 723.79 | OOS increment is small and worst signal month is 13.05% worse. |
| F4 | Plain R4 base $4,650 | 1,891.89 | -1,205.69 | 686.19 | The overlay underperforms the same-size control in confirmation; reduced size explains most repeated risk relief. |

F2's observed-history voting/cover combination is therefore useful conditional research, but not a clean repeated improvement over simply shrinking R5. F4 provides a simpler monthly-ride alternative at lower profit. No post-confirmation sizing, thresholds, candidate ranking or policy rules were changed.

## Chronological all-signal investor account

All signals were replayed together after confirmation, with one live inventory and one causal capacity policy. Constrained IS/OOS books were not added or spliced. The following monthly returns use each month's starting marked equity; all twelve months, including losing and flat months, are retained.

| Book | Profit | $/session | Red months / loss sum | Worst / median month | Drawdown | Worst day | Mean / peak gross |
|---|---:|---:|---:|---:|---:|---:|---:|
| PARENT | 38,317.20 | 152.66 | 4 / -23,851.39 | -9,775.24 / 1,279.64 | -22,989.15 | -6,607.31 | 80,870.91 / 134,692.22 |
| R4 | 59,040.69 | 235.22 | 4 / -20,819.82 | -7,102.77 / 3,548.96 | -21,297.57 | -6,768.31 | 78,142.48 / 131,125.52 |
| R5 | 68,921.14 | 274.59 | 4 / -23,365.53 | -7,875.11 / 5,817.11 | -22,496.36 | -6,885.20 | 78,245.20 / 139,810.17 |
| A4 | 45,888.08 | 182.82 | 4 / -16,150.24 | -5,495.40 / 2,750.20 | -16,523.36 | -5,250.04 | 60,661.43 / 101,813.64 |
| R1 | 33,117.68 | 131.94 | 4 / -11,253.55 | -3,781.43 / 2,787.19 | -10,817.46 | -3,303.81 | 37,514.22 / 66,991.14 |
| F1 | 69,207.09 | 275.73 | 4 / -22,559.05 | -7,923.12 / 5,896.04 | -21,621.74 | -6,231.81 | 76,263.83 / 130,088.40 |
| F2 | 61,394.77 | 244.60 | 4 / -19,034.10 | -7,748.89 / 5,320.91 | -19,626.13 | -5,497.59 | 67,055.80 / 116,439.47 |
| F3 | 70,914.94 | 282.53 | 4 / -22,407.62 | -9,043.40 / 6,413.71 | -22,916.63 | -6,222.02 | 78,401.01 / 130,068.24 |
| F4 | 54,074.63 | 215.44 | 3 / -17,738.42 | -6,098.73 / 3,459.06 | -18,535.40 | -5,854.16 | 69,520.84 / 116,857.27 |

### Twelve calendar months — original and conservative controls

Cells show MTM dollars (return on month-start equity).

| Calendar month | PARENT | R4 | R5 | A4 | R1 |
|---|---:|---:|---:|---:|---:|
| 2025-09 | -9,775.24 (-9.78%) | -6,626.57 (-6.63%) | -4,941.60 (-4.94%) | -5,142.16 (-5.14%) | -2,363.85 (-2.36%) |
| 2025-10 | 16,549.66 (18.34%) | 22,674.07 (24.28%) | 22,536.31 (23.71%) | 17,595.33 (18.55%) | 10,833.45 (11.10%) |
| 2025-11 | 664.24 (0.62%) | 2,531.56 (2.18%) | 3,519.60 (2.99%) | 1,962.36 (1.75%) | 1,697.01 (1.56%) |
| 2025-12 | -5,723.65 (-5.33%) | -7,102.77 (-5.99%) | -7,875.11 (-6.50%) | -5,495.40 (-4.80%) | -3,781.43 (-3.43%) |
| 2026-01 | 558.86 (0.55%) | 2,155.08 (1.93%) | 4,416.37 (3.90%) | 1,680.40 (1.54%) | 2,117.84 (1.99%) |
| 2026-02 | 1,895.04 (1.85%) | -45.20 (-0.04%) | -3,851.97 (-3.27%) | -40.68 (-0.04%) | -1,873.48 (-1.73%) |
| 2026-03 | 5,849.06 (5.61%) | 9,721.81 (8.56%) | 13,995.73 (12.30%) | 7,582.07 (6.86%) | 6,759.25 (6.34%) |
| 2026-04 | -8,135.96 (-7.40%) | -7,045.27 (-5.71%) | -6,696.85 (-5.24%) | -5,472.01 (-4.63%) | -3,234.79 (-2.85%) |
| 2026-05 | -216.54 (-0.21%) | 4,566.36 (3.93%) | 7,217.86 (5.96%) | 3,538.04 (3.14%) | 3,456.55 (3.14%) |
| 2026-06 | 17,100.25 (16.82%) | 17,210.24 (14.24%) | 22,100.35 (17.22%) | 13,360.40 (11.50%) | 10,617.69 (9.35%) |
| 2026-07 | 14,700.13 (12.38%) | 13,904.48 (10.07%) | 11,056.53 (7.35%) | 10,828.82 (8.36%) | 5,323.24 (4.29%) |
| 2026-08 | 4,851.35 (3.63%) | 7,096.91 (4.67%) | 7,443.92 (4.61%) | 5,490.89 (3.91%) | 3,566.21 (2.75%) |

### Twelve calendar months — frozen finalists

| Calendar month | F1 | F2 | F3 | F4 |
|---|---:|---:|---:|---:|
| 2025-09 | -4,721.16 (-4.72%) | -3,593.75 (-3.59%) | -4,241.70 (-4.24%) | -5,706.16 (-5.71%) |
| 2025-10 | 21,972.70 (23.06%) | 17,960.49 (18.63%) | 21,310.85 (22.25%) | 19,875.41 (21.08%) |
| 2025-11 | 4,604.75 (3.93%) | 3,886.24 (3.40%) | 4,595.70 (3.93%) | 2,877.30 (2.52%) |
| 2025-12 | -7,923.12 (-6.50%) | -7,748.89 (-6.55%) | -9,043.40 (-7.43%) | -6,098.73 (-5.21%) |
| 2026-01 | 4,213.61 (3.70%) | 5,122.91 (4.64%) | 6,288.50 (5.58%) | 1,720.44 (1.55%) |
| 2026-02 | -3,670.28 (-3.11%) | -2,856.80 (-2.47%) | -3,401.45 (-2.86%) | 132.64 (0.12%) |
| 2026-03 | 13,451.23 (11.75%) | 10,081.04 (8.94%) | 11,973.98 (10.37%) | 8,611.07 (7.63%) |
| 2026-04 | -6,244.50 (-4.88%) | -4,834.66 (-3.94%) | -5,721.07 (-4.49%) | -5,933.53 (-4.89%) |
| 2026-05 | 7,187.32 (5.91%) | 5,518.90 (4.68%) | 6,538.91 (5.37%) | 4,040.81 (3.50%) |
| 2026-06 | 22,373.12 (17.36%) | 20,971.60 (16.98%) | 23,434.81 (18.27%) | 16,425.49 (13.74%) |
| 2026-07 | 10,620.02 (7.02%) | 9,315.90 (6.45%) | 10,938.25 (7.21%) | 11,981.36 (8.81%) |
| 2026-08 | 7,343.38 (4.54%) | 7,571.78 (4.92%) | 8,241.55 (5.07%) | 6,148.53 (4.16%) |

All frozen matched controls also have twelve month-start-equity/MTM/return rows in `cg_arrow003_results.json`. The daily ACCOUNT aggregates for every control and finalist are in [cg_arrow003_daily.csv](cg_arrow003_daily.csv); raw market bars and position/fill ledgers are not published.

## Practical risk and inventory

| Book | DD % | Underwater sessions / longest spell | P95 / peak EOD gross | Sessions / longest above $130k | Excess dollar-days | Peak gross/equity | Largest symbol/equity | Terminal tickets / stale gross |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PARENT | -20.19% | 220 / 133 | 112,220.79 / 134,692.22 | 4 / 1 | 10,465.43 | 1.323 | 15.71% | 26 / 48,056.97 |
| R4 | -17.15% | 214 / 85 | 107,276.51 / 131,125.52 | 1 / 1 | 1,125.52 | 1.154 | 15.02% | 26 / 41,605.89 |
| R5 | -17.62% | 212 / 85 | 114,408.49 / 139,810.17 | 5 / 1 | 15,583.42 | 1.227 | 17.10% | 26 / 37,883.84 |
| A4 | -13.92% | 213 / 85 | 83,317.16 / 101,813.64 | 0 / 0 | 0.00 | 0.917 | 11.87% | 26 / 32,334.87 |
| R1 | -9.55% | 212 / 85 | 54,954.48 / 66,991.14 | 0 / 0 | 0.00 | 0.628 | 8.59% | 26 / 18,101.62 |
| F1 | -16.99% | 210 / 84 | 105,347.76 / 130,088.40 | 2 / 1 | 170.24 | 1.132 | 16.91% | 26 / 37,762.55 |
| F2 | -16.01% | 209 / 85 | 96,334.80 / 116,439.47 | 0 / 0 | 0.00 | 1.039 | 14.35% | 26 / 31,779.38 |
| F3 | -18.08% | 208 / 84 | 108,522.59 / 130,068.24 | 2 / 1 | 68.67 | 1.148 | 16.75% | 26 / 37,965.43 |
| F4 | -15.26% | 214 / 85 | 94,624.66 / 116,857.27 | 0 / 0 | 0.00 | 1.027 | 13.68% | 26 / 37,605.26 |

| Book | Fully closed ticket PnL | Realized exit-leg PnL | Terminal net unrealized MTM | Maximum terminal staleness (sessions) |
|---|---:|---:|---:|---:|
| PARENT | 41,608.11 | 41,608.11 | -3,290.91 | 243 |
| R4 | 59,088.26 | 59,088.26 | -47.57 | 243 |
| R5 | 69,708.02 | 69,708.02 | -786.88 | 243 |
| A4 | 45,955.04 | 45,955.04 | -66.95 | 243 |
| R1 | 33,501.52 | 33,501.52 | -383.84 | 243 |
| F1 | 70,025.09 | 70,025.09 | -818.00 | 243 |
| F2 | 61,131.40 | 61,131.40 | 263.37 | 243 |
| F3 | 71,469.72 | 71,469.72 | -554.77 | 243 |
| F4 | 54,169.51 | 54,169.51 | -94.89 | 243 |

Realized exit legs plus terminal net unrealized MTM reconcile to total profit. Fully closed tickets are a separate view; realized partial covers can belong to tickets still open at the boundary. Completed versus partly open signal-batch cohort PnL is also explicit in JSON. No future terminal cover fee or post-boundary loan charge is invented.

The combined book has 26 terminal tickets: ten have stale marks, while sixteen recent tickets remain open at the evaluation boundary with August 31 marks. Total terminal gross (fresh plus stale) is $99,803.45 for R4, $105,988.14 for R5, $105,347.76 for F1, $97,001.77 for F2, $103,650.56 for F3 and $90,107.98 for F4. Across the full account, all six books retain 1,090 stale position-sessions, 21 missing scheduled backstops, eleven later observed exit fills and seven missed late entries. The delayed fills span 98 aggregate delay sessions. These aggregate counts are disclosed rather than deleting the affected observations.

Dollar-days use calendar duration to the next session; dollar-session excess is also supplied in JSON. Excursion cause labels distinguish sessions with new allocation from existing-inventory drift; they are descriptive, not retroactive order rejection. Pacing uses last pre-order marks, reserves all open cohorts and due-but-unfilled closing orders, and scales a simultaneous batch pro rata. There is no minimum-size top-up or forced liquidation at a small overshoot.

All EOD excursions in these books occur on sessions containing new allocations as well as marks; intraday peaks may subsequently drift. In the combined replay pacing scales six batches for F1 and nine for F3. It never binds for conservative F2/F4, so their risk improvement cannot be credited to active capital throttling. No OOS peak was used to rescale a policy.

Five of six unresolved IS R4 tickets were last marked above $80. Across its full lifecycle, **720 of 724 stale position-sessions** have a documented price-range exclusion in at least one copied acquisition table; the remaining four have other documented exclusions. Missing rows in one source are distinguished from known exclusions in the other in `cg_arrow003_lifecycle_coverage.json`. The old acquisition bounds do not provide a complete held-position lifecycle service. A modeled delay means a missing local executable observation; it does not assert a market halt or actual inability to exit.

Fixed-quantity terminal shocks are in `cg_arrow003_stale_dependency.json`. The separate `cg_arrow003_dynamic_stale.json` diagnostic replays causal IS capacity/drawdown state under common non-compounding +10%, +50% and +100% missing-valuation errors. At +50%, original R4/R5 profits fall to $1,805.80/$9,625.58. These are hypothetical stresses, not estimates or probability bounds; actual missing prices and absolute account economics remain uncertain. A carried or stressed mark is never an executable exit.

An independent cash-minus-short-liability audit checks sale proceeds, cover payments, remaining quantities and observed execution identity. It agrees with the scorer's daily MTM accounting; agreement cannot repair missing prices, actions or loan economics. Cover-only additional execution-cost sensitivity is in `cg_arrow003_cover_execution.json`; combined-policy increments are not attributed entirely to covers.

| Book | 10% adverse move in all shorts | 50% adverse move in largest name | Joint: other names +10%, largest +50% | Best calendar month / total profit |
|---|---:|---:|---:|---:|
| PARENT | -13,469.22 | -7,022.76 | -19,087.43 | 44.63% |
| R4 | -13,112.55 | -8,022.17 | -19,201.39 | 38.40% |
| R5 | -13,981.02 | -9,348.56 | -20,807.98 | 32.70% |
| A4 | -10,181.36 | -6,251.39 | -14,876.37 | 38.34% |
| R1 | -6,699.11 | -4,489.16 | -9,958.95 | 32.71% |
| F1 | -13,008.84 | -9,302.28 | -19,660.68 | 32.33% |
| F2 | -11,643.95 | -7,821.32 | -16,918.48 | 34.16% |
| F3 | -13,006.82 | -9,302.28 | -19,934.96 | 33.05% |
| F4 | -11,685.73 | -7,284.35 | -16,376.47 | 36.76% |

### Synchronized minute risk audit

Every calendar session was checked using concurrent one-minute closes. Each close sample includes close fills and precedes the next bar's open executions at the same time boundary. Cash credits entry proceeds and debits cover cash plus costs. Missing intraday prices carry the last known mark. These are minute-close marked peaks, not tick-by-tick maxima or independent-high sums.

| Book | Minute peak gross | Peak time | Stale gross at peak | Minutes above $130k | Excess dollar-minutes |
|---|---:|---|---:|---:|---:|
| PARENT | 134,692.22 | 2026-06-04T16:00:00-04:00 | 58,248.85 | 515 | 1,107,302.32 |
| R4 | 132,928.75 | 2026-07-17T13:40:00-04:00 | 41,482.29 | 360 | 633,746.85 |
| R5 | 140,016.15 | 2025-12-12T10:49:00-05:00 | 15,759.89 | 841 | 4,866,742.29 |
| A4 | 103,213.60 | 2026-07-17T13:40:00-04:00 | 32,294.23 | 0 | 0.00 |
| R1 | 67,088.16 | 2025-12-12T10:49:00-05:00 | 7,465.19 | 0 | 0.00 |
| F1 | 131,518.76 | 2026-07-17T13:29:00-04:00 | 37,851.99 | 354 | 183,654.43 |
| F2 | 116,840.81 | 2025-12-12T10:49:00-05:00 | 13,272.38 | 0 | 0.00 |
| F3 | 131,158.52 | 2026-01-05T09:48:00-05:00 | 2,023.44 | 148 | 32,906.39 |
| F4 | 118,357.68 | 2026-07-17T13:40:00-04:00 | 37,519.26 | 0 | 0.00 |

| Book | Minute-sampled DD (dollars / %) | Peak minute gross/equity | Largest name/equity |
|---|---:|---:|---:|
| PARENT | -27,104.35 / -23.27% | 1.323 | 17.64% |
| R4 | -25,189.49 / -19.91% | 1.160 | 16.71% |
| R5 | -27,678.46 / -21.23% | 1.231 | 18.70% |
| A4 | -19,545.03 / -16.21% | 0.921 | 13.09% |
| R1 | -13,306.25 / -11.61% | 0.629 | 9.29% |
| F1 | -26,843.46 / -20.65% | 1.141 | 18.44% |
| F2 | -23,820.43 / -19.08% | 1.047 | 14.58% |
| F3 | -27,903.06 / -21.55% | 1.206 | 17.33% |
| F4 | -22,077.16 / -17.86% | 1.032 | 14.97% |

Stress amounts are arithmetic, not forecasts, margin certification or new stop rules. Largest-name and broad-book maxima can occur on different dates; the joint stress is evaluated concurrently per day. Top-symbol and top/bottom-month contribution details remain in the aggregate JSON.

## Borrow and execution-cost scenarios

Baseline commission is $0.005 per share each side plus a one-side spread proxy of max($0.01, 0.10% of price). Borrow scenarios charge 0%, 10%, or 30% annualized on preceding EOD marked gross for actual calendar holding days. Spread stress doubles only the spread proxy; commissions remain unchanged. These are sensitivities, not observed loan fees.

| Book | Baseline $/day | 10% borrow $/day | 30% borrow $/day | Double spread $/day |
|---|---:|---:|---:|---:|
| PARENT | 152.66 | 120.54 | 56.29 | 139.96 |
| R4 | 235.22 | 204.16 | 142.04 | 222.40 |
| R5 | 274.59 | 243.44 | 181.14 | 261.64 |
| A4 | 182.82 | 158.71 | 110.48 | 172.87 |
| R1 | 131.94 | 117.01 | 87.14 | 125.73 |
| F1 | 275.73 | 245.33 | 184.54 | 262.98 |
| F2 | 244.60 | 217.87 | 164.41 | 233.24 |
| F3 | 282.53 | 251.27 | 188.74 | 269.28 |
| F4 | 215.44 | 187.75 | 132.39 | 203.88 |

The full cross-product of borrow and spread scenarios is available for every frozen book. The ambition remains $300–$500 modeled net/day on $100,000. An under-target portfolio is not commercial success; the old $200/day slate and $100/day component figures are references, not automatic vetoes on useful family research. No independent-engine seat or deployment readiness is claimed.

## Resilience, overlap and interpretation

Paired leave-one-IS-month-out profit differences, contribution dependence, size matches and neighbors are recorded in `cg_arrow003_is_robustness.json` and `cg_arrow003_is_frontier.json`. The best incremental contributors still matter; multiple correlated downside metrics do not constitute independent confirmations. Signal-month ownership allows causal feature histories and existing-position management to cross even/odd boundaries; overlap counts and opposite-split lifecycle MTM are explicit JSON fields.

Daily all-signal correlation is reported in JSON. Every book is a continuation of the same hold-short-for-fade selections; combining R4 and R5 sizing is not diversification across independent engines.

F2's daily account correlation with R5 is 0.9907; F4's with R4 is 0.9989. These policies do not earn separate low-correlation seats. F2/F4 never exceed $130,000 in the synchronized minute samples. F1/F3 peak at $131,518.76/$131,158.52, with 354/148 minute samples above the planning range and only two EOD excursion sessions each. Original R5 peaks at $140,016.15 with 841 minutes above $130,000. These are observed local-tape marked exposures, still conditional on stale inventory values.

## Clock, verification and handoff

Run start: 2026-09-13T17:48:42+00:00; deadline: 2026-09-13T20:48:42+00:00. Freeze: 2026-09-13T20:17:24+00:00 (minute 148.70), committed before OOS. Confirmation start/completion: 2026-09-13T20:17:46+00:00 / 2026-09-13T20:18:25+00:00. Report written at minute 152.22.

Exact repeatable commands, test totals, effort allocation, public-safety review, commits and remote verification are in [cg_arrow003_commands.txt](cg_arrow003_commands.txt). The freeze manifest records explicit versioned dependencies, repair conventions, data/cache identity, scenarios, priorities and intended sizes. Detailed local ledger paths and hashes are in the results file. No confirmation was invalidated; any identical-job resume is explicitly recorded.

The committed freeze is `8f2fe84`. All 17 confirmation books and all 17 combined investor books completed on their first attempt; neither batch resumed or rescored. Independent cash reconciliation passed for all 17 investor books. The synchronized minute audit covered all 251 sessions for the five original/conservative controls and four finalists. Final full-suite verification passed **517 tests in 6.67 seconds**. Discovery effort was retrospectively estimated at approximately **57% directed / 43% autonomous**, excluding shared repair and closure work; timestamped policy evidence and the estimation limits are in the command log. The report's editorial interpretation was added after confirmation without changing frozen scoring code or outcomes.

## Parked questions — not executed as a new arrow

Resolve stale/delisted inventory and broader corporate-action coverage; obtain actual historical loan/dividend economics if authorized; challenge these fixed policies on genuinely new data; understand whether sparse volume histories encode missing data or an economic state. Independent swing/day models remain parked. No Arrow 004 is begun.
