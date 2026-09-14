# CG Arrow 011 — Winner-Fade anatomy: pre-entry characteristics and within-cohort outcomes

Executor: Fable in Claude Code. Freeze commit `5742000`, run head `5742000`. Principal subject: the certified Momentum+Volume-Sized Short (`R5`), Corrected-Universe Replay (`R2`), 10-Session Hold (`H10`), causal pre-order quantities. Volume-Sized (`R4`) and the equity-scaled book are explanatory references. Nothing in any frozen ledger, rule or account was changed; this arrow adds an isolated feature and analysis layer.

## Executive findings

1. **The basket's most extreme name is where the fade lives.** Rank 1 of 8, almost always separated from rank 2 by a wide gap in ranking return, faded on average +0.327 in IS (hit 88%) and +0.221 in internal confirmation (hit 78%), against ranks 2-8 near +0.056 in confirmation. This is a within-cohort relationship by construction and it replicated. Recurring association.
2. **Among ranks 2-8, names already off their 20-session high fade more, not less.** The prediction was the opposite. IS ranks 2-8: lowest tercile of close-versus-high +0.123 (hit 65%) versus at-the-high -0.074 (hit 25%); confirmation +0.110 versus +0.044, same direction, weaker. Recurring association.
3. **Wide recent ranges and episodic advances fade more.** Session log-return dispersion, signal-day range and the pre-order-bar partial range replicated; advances concentrated in few sessions replicated; the ten-session mean range was same-sign but below the frozen threshold. Recurring association with a plausible mechanism (the fade is a volatility event, not a drift).
4. **The momentum halving in the frozen rule is not supported as a stock-selection signal.** On IS, non-positive three-session momentum names faded more (+0.092 cohort-equal-weight difference); in confirmation the sign reversed (-0.076). The two HALF states did not behave alike on IS and were too sparse to judge on OOS (5 weak-and-loud rows). Mechanically, the momentum component of the R4-to-R5 difference is -55,010 against a base-ticket component of 69,953: the halving mostly forfeited winners. Rejected as a signal; established arithmetic as a cost.
5. **Pre-order information adds nothing within cohort.** The entry-session move from the signal close to the pre-order bar, the overnight gap and the position in the partial-day range separate nothing within a basket on IS or in confirmation. A between-cohort correlation exists and is labeled exploratory. Negative result.
6. **Price band matters mainly at the top.** The 10-20 band led on IS; in confirmation 10-20 and 20-40 were close and 40-80 lagged. The robust statement is that 40-80 names faded least. Recurring association, weaker than first seen.
7. **Repeat selections are not different.** Overlapping repeats fade like first selections in confirmation. Rejected.

Confirmation is internal only: the even months have been inspected in earlier arrows. 5 of 10 registered claims met their frozen expectation; of 42 registered feature relationships, 15 replicated, 3 were same-sign but weaker, 13 confirmed as no-signal, and 11 showed a separation only after the reveal and are queued, not claimed.

## Baseline preserved and preflight

| Check | Result |
|---|---|
| Private input hashes against the Arrow 008 and 010 manifests | 17 of 17 |
| Census per book (cohorts / intended / completed / open documented) | 52 / 416 / 415 / 1 in every principal book |
| Economic controls reproduce from the ledgers | 4 of 4 |
| Fresh replay versus the certified causal pre-order ledger | 0 mismatches on 416 tickets |
| Independent oracle, Arrow 008 R2 books and Arrow 010 books | ok, max trade error 1.8e-12 |
| Frozen four-state labels versus the ledger | 0 disagreements |
| Pre-order features available | 416 of 416 |
| Per-share marked path times quantity reproduces every daily account | worst 1.0e-09 |
| Hash drift between freeze and reveal | none |

The Arrow 010 lesson was applied: the observation set is the engine's own need set, so no volume or momentum feature was silently dropped, and a missing feature is its own state rather than a FULL-size fallback in the analysis.

## Question 1 — which pre-entry characteristics go with the fade, and what explains the model and month differences

### Model and month bridge, Volume-Sized to Momentum+Volume-Sized

Both books hold the same 416 positions with the same entry and exit observations and differ only in share count, so the difference is an exact identity per ticket: net per entry share times the share difference. The share difference is split in a declared order, raising the base ticket from 5,150 to 8,300 at the Volume-Sized multipliers first, then applying the momentum halving at the raised base, with the integer-share residual shown. The two continuous components are order-dependent, not independent causes.

| Panel | R4 eventual | R5 eventual | Difference | Base ticket | Momentum halving | Rounding | From R4 winners | From R4 losers | FULL | HALF | QUARTER |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Legacy fill (Arrow 009 panel) | 114,191 | 129,093 | 14,902 | 69,953 | -55,010 | -41 | 12,555 | 2,347 | 28,005 | -9,101 | -4,002 |
| Causal pre-order (atlas panel) | 113,845 | 128,865 | 15,019 | 69,732 | -54,608 | -104 | 12,637 | 2,382 | 28,046 | -9,057 | -3,970 |

Calendar months on the marked-account basis, legacy fill panel, which reproduces the Arrow 009 monthly differences exactly (reconciliation residual below 1e-9 in every month):

| Month | R4 marked | R5 marked | Difference | Base ticket | Momentum | From R4 winners | From R4 losers | Tickets +/- | Top-3 share |
|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 2025-09 | 2,854 | 3,733 | 878 | 1,744 | -877 | -242 | 1,121 | 21/11 | 34% |
| 2025-10 | 16,575 | 14,265 | -2,310 | 10,147 | -12,432 | -3,123 | 843 | 25/31 | 27% |
| 2025-11 | 11,413 | 12,244 | 831 | 6,993 | -6,141 | -502 | 1,333 | 23/25 | 38% |
| 2025-12 | -8,289 | -10,792 | -2,504 | -5,097 | 2,601 | -1,619 | -885 | 23/25 | 24% |
| 2026-01 | 6,507 | 12,586 | 6,079 | 3,982 | 2,101 | 4,268 | 1,811 | 29/27 | 33% |
| 2026-02 | 2,456 | -988 | -3,444 | 1,516 | -4,968 | 113 | -3,557 | 22/26 | 55% |
| 2026-03 | 12,908 | 16,734 | 3,827 | 7,907 | -4,091 | 2,777 | 1,050 | 23/25 | 56% |
| 2026-04 | -63 | 820 | 882 | -64 | 961 | -738 | 1,621 | 30/26 | 38% |
| 2026-05 | 6,893 | 8,783 | 1,889 | 4,237 | -2,366 | 2,677 | -788 | 22/26 | 40% |
| 2026-06 | 31,451 | 41,795 | 10,344 | 19,280 | -8,899 | 9,480 | 864 | 25/23 | 35% |
| 2026-07 | 15,156 | 14,859 | -297 | 9,313 | -9,635 | -302 | 4 | 23/33 | 24% |
| 2026-08 | 16,793 | 15,165 | -1,628 | 10,284 | -11,906 | -266 | -1,362 | 21/27 | 40% |

Reading the twelve months. In every month the base-ticket component is the sign of that month's book and the momentum component works against it whenever strong-momentum names were the ones fading: October 2025, July 2026 and August 2026 are months where the halving gave back more than 9,000 each, while December 2025 and January 2026 are the months where it protected the book. February 2026 is the clearest case of a small-number effect: three tickets carry 55% of the absolute difference and almost all of it came from names that lost under Volume-Sized sizing. June 2026 is the opposite, a widespread reweighting where 25 tickets gained and 23 lost and the winners supplied 9,480 of the 10,344 difference. Per tier, the FULL state contributed all of the net gain and the HALF and QUARTER states gave back part of it, which is the sizing-neutral finding below restated in dollars: the rule sizes largest exactly where the fade was strongest on IS, and smallest where confirmation later showed the fade was at least as strong.

Where lower raw-return opportunity still produced more dollars: the whole difference. Sizing-neutral outcomes are identical across the two books (mean price return +0.0659, hit rate 56%); every dollar of difference is size.

### The four momentum/volume states

| State | IS n | IS cohorts | IS mean | IS cohort-weighted | IS hit | OOS n | OOS mean | OOS cohort-weighted | OOS hit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S1_FULL_weak_quiet | 30 | 16 | +0.156 | +0.156 | 60% | 43 | +0.097 | +0.073 | 56% |
| S2_HALF_weak_loud | 11 | 9 | +0.075 | +0.071 | 64% | 5 | -0.133 | -0.133 | 60% |
| S3_HALF_strong_quiet | 70 | 24 | +0.043 | +0.017 | 50% | 66 | +0.090 | +0.123 | 59% |
| S4_QUARTER_strong_loud | 87 | 25 | +0.019 | +0.021 | 51% | 96 | +0.072 | +0.091 | 59% |
| MISSING_FEATURE | 2 | 2 | +0.318 | +0.318 | 100% | 5 | +0.041 | +0.041 | 40% |

Do the two HALF states behave alike? Not on IS: weak-and-loud (S2) sat with FULL and strong-and-quiet (S3) sat with QUARTER, so the separating dimension was the momentum sign, not the volume ratio. In confirmation S3 and S4 faded as well as or better than S1 and S2 had only five rows, so the IS separation did not carry. Is weakening on elevated volume different from weakening on quiet volume? The sample cannot say: S2 has 16 rows across the year. Are the reductions informative individually? The volume ratio is a weak, inconsistent separator (it flips sign in the 20-80 band on IS and is near zero in confirmation); the momentum sign separated on IS and reversed in confirmation. An apparently strong FULL bucket is therefore partly its bigger tickets: on a sizing-neutral basis its IS advantage did not replicate.

### Feature anatomy, leading relationships

Statistic: within-cohort mean of the top half minus bottom half by feature of the ten-session short price return, with the share of cohorts favouring one side; tercile cuts learned on IS and frozen. Positive means the higher feature value faded more.

| Feature | Cutoff | IS contrast | IS share | OOS contrast | OOS share | Status | Label |
|---|---|---:|---:|---:|---:|---|---|
| sc_position_in_range20 | SIGNAL_CLOSE | -0.164 | 0.16 | -0.063 | 0.33 | REPLICATED | recurring association |
| sc_close_vs_high20 | SIGNAL_CLOSE | -0.163 | 0.16 | -0.079 | 0.33 | REPLICATED | recurring association |
| sc_mean_range_pct_10 | SIGNAL_CLOSE | +0.162 | 0.88 | +0.077 | 0.59 | SAME_SIGN_WEAKER | recurring, weaker |
| po_partial_range_pct | PRE_ORDER | +0.160 | 0.92 | +0.126 | 0.70 | REPLICATED | recurring association |
| sc_logret_std_15 | SIGNAL_CLOSE | +0.137 | 0.76 | +0.120 | 0.74 | REPLICATED | recurring association |
| cx_gap_to_next_rank | SIGNAL_CLOSE | +0.129 | 0.92 | +0.027 | 0.70 | REPLICATED | recurring association |
| sc_signal_day_range_pct | SIGNAL_CLOSE | +0.128 | 0.76 | +0.094 | 0.74 | REPLICATED | recurring association |
| sc_close_vs_max_close15 | SIGNAL_CLOSE | -0.123 | 0.32 | -0.099 | 0.30 | REPLICATED | recurring association |
| sc_signal_close | SIGNAL_CLOSE | -0.105 | 0.24 | -0.007 | 0.48 | SAME_SIGN_WEAKER | recurring, weaker |
| sc_up_sessions_15 | SIGNAL_CLOSE | -0.101 | 0.24 | -0.094 | 0.30 | REPLICATED | recurring association |
| sc_top3_sessions_share_of_advance | SIGNAL_CLOSE | +0.097 | 0.76 | +0.114 | 0.67 | REPLICATED | recurring association |
| ep_sessions_since_last_selection | SIGNAL_CLOSE | -0.096 | 0.21 | -0.083 | 0.33 | SEPARATION_APPEARED_POST_HOC | post-reveal only, queued |
| sc_ret15 | SIGNAL_CLOSE | +0.086 | 0.64 | +0.064 | 0.74 | REPLICATED | recurring association |
| cx_rank_in_eight | SIGNAL_CLOSE | -0.086 | 0.36 | -0.064 | 0.26 | REPLICATED | recurring association |
| cx_ret15_minus_cohort_median | SIGNAL_CLOSE | +0.086 | 0.64 | +0.064 | 0.74 | REPLICATED | recurring association |
| cx_cohort_ret15_spread | SIGNAL_CLOSE | -0.086 | 0.36 | -0.064 | 0.26 | SEPARATION_APPEARED_POST_HOC | post-reveal only, queued |
| cx_ret15_field_percentile | SIGNAL_CLOSE | +0.086 | 0.64 | +0.064 | 0.74 | REPLICATED | recurring association |
| po_preorder_price | PRE_ORDER | -0.081 | 0.32 | -0.028 | 0.41 | SAME_SIGN_WEAKER | recurring, weaker |
| sc_dollar_volume_cv20 | SIGNAL_CLOSE | +0.064 | 0.68 | +0.083 | 0.74 | REPLICATED | recurring association |
| sc_volume_expansion_15 | SIGNAL_CLOSE | +0.059 | 0.64 | +0.048 | 0.70 | REPLICATED | recurring association |
| sc_largest_session_share_of_advance | SIGNAL_CLOSE | +0.043 | 0.68 | +0.092 | 0.67 | SEPARATION_APPEARED_POST_HOC | post-reveal only, queued |
| po_overnight_gap_vs_signal_close | PRE_ORDER | +0.039 | 0.64 | +0.034 | 0.44 | NO_SIGNAL_CONFIRMED | no signal |
| sc_volume_trend_5_vs_15 | SIGNAL_CLOSE | +0.022 | 0.64 | +0.002 | 0.44 | NO_SIGNAL_CONFIRMED | no signal |

Two rows need a caution. `cx_cohort_ret15_spread` is constant inside a cohort, so its within-cohort values are an artifact of tie order and only its between-cohort view is meaningful; `ep_sessions_since_last_selection` exists only for repeat selections (84 IS rows). Neither was claimed.

The full registered set, including every no-signal feature, is in `reports/cg_arrow011_confirmation.csv` and the three-split view in `reports/cg_arrow011_within_cohort_summary.csv`. Leave-one-cohort-out, leave-one-security-out, cohort-block resampling and month-by-month direction for every registered feature are in `reports/cg_arrow011_stability.csv`.

## Question 2 — within each basket of eight, what distinguished the better shorts before entry

### Rank within the eight

| Rank | IS mean | IS hit | OOS mean | OOS hit | ALL mean | ALL hit |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | +0.327 | 88% | +0.221 | 78% | +0.272 | 83% |
| 2 | +0.032 | 48% | +0.110 | 67% | +0.073 | 58% |
| 3 | +0.033 | 52% | +0.044 | 52% | +0.039 | 52% |
| 4 | -0.006 | 48% | +0.057 | 52% | +0.027 | 50% |
| 5 | +0.085 | 64% | +0.099 | 59% | +0.092 | 62% |
| 6 | -0.015 | 44% | +0.064 | 54% | +0.026 | 49% |
| 7 | -0.007 | 44% | -0.023 | 48% | -0.015 | 46% |
| 8 | -0.019 | 36% | +0.043 | 56% | +0.013 | 46% |

Each rank row has one ticket per cohort, so the mean is already cohort-equal-weighted. The gap from rank 1 to rank 2 in ranking return was the single strongest within-cohort feature on IS (share 0.92 of cohorts) and replicated at share 0.70. Rank 2 also faded in confirmation, so the pattern is extremeness, not a rank-1 accident. Six IS rank-1 names did not fade; three of them are from November 2025, the IS month where the gap effect was weakest.

### A two-by-two state map, frozen on IS

Price band of the signal close (10-20 versus 20-80) by whether the close sits below the IS median distance from the 20-session high (-0.055, that is more than about 5.5% below the high).

| Cell | IS n | IS cohorts | IS cohort-weighted | IS hit | IS net per $ | OOS n | OOS cohort-weighted | OOS hit | OOS net per $ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10-20 x off_high | 44 | 22 | +0.172 | 75% | +0.2441 | 47 | +0.116 | 72% | +0.1015 |
| 10-20 x near_high | 29 | 17 | +0.012 | 48% | +0.0503 | 27 | +0.032 | 56% | +0.0427 |
| >=20 x off_high | 51 | 19 | +0.088 | 67% | +0.0665 | 67 | +0.078 | 55% | +0.0982 |
| >=20 x near_high | 69 | 25 | -0.089 | 28% | -0.0795 | 61 | +0.039 | 54% | +0.0277 |

The best cell replicated as the best cell. The worst IS cell (20-80 and near the high, hit 28%) recovered to a small positive in confirmation, so the frozen ordering claim failed on the worst cell while the off-high-beats-near-high reading held inside both bands.

### Cohort census and dependence

Cohorts: IS {'MIXED': 24, 'ALL_LOSS': 1}, confirmation {'PARTLY_CENSORED': 1, 'MIXED': 24, 'ALL_WIN': 2}, all {'MIXED': 48, 'PARTLY_CENSORED': 1, 'ALL_WIN': 2, 'ALL_LOSS': 1}. One cohort is partly censored by the documented halt. Distinct securities 246; 101 selected at least twice and 46 at least three times, the most frequent 6 times. 146 of 416 selections are overlapping repeats whose previous ten-session hold was still open at the new signal; these are persistence of one episode, not new examples, and every relationship table reports its security count for that reason. Eight simultaneous shorts and overlapping holds are not independent replications; the cohort-block resampling in the stability table is the dependence-aware spread.

## Holding paths as outcomes

Close-only sizing-neutral short return by holding age, all completed tickets; age 0 and age 10 use the execution reference. Close-only excursions are not intraday extrema. These are outcomes and were never scored as predictors.

| Age | IS mean | IS median | IS favourable | OOS mean | OOS median | OOS favourable | ALL mean | ALL favourable |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | +0.0167 | +0.0038 | 58% | +0.0089 | +0.0061 | 54% | +0.0126 | 56% |
| 2 | +0.0327 | +0.0075 | 58% | +0.0260 | +0.0032 | 52% | +0.0293 | 55% |
| 3 | +0.0335 | +0.0109 | 57% | +0.0413 | +0.0201 | 55% | +0.0375 | 56% |
| 4 | +0.0323 | +0.0062 | 56% | +0.0420 | +0.0114 | 54% | +0.0373 | 55% |
| 5 | +0.0356 | +0.0160 | 55% | +0.0464 | +0.0211 | 56% | +0.0412 | 55% |
| 6 | +0.0451 | +0.0129 | 56% | +0.0538 | +0.0248 | 57% | +0.0496 | 56% |
| 7 | +0.0437 | +0.0201 | 58% | +0.0660 | +0.0290 | 56% | +0.0553 | 57% |
| 8 | +0.0568 | +0.0341 | 59% | +0.0766 | +0.0493 | 58% | +0.0671 | 58% |
| 9 | +0.0550 | +0.0250 | 56% | +0.0841 | +0.0390 | 59% | +0.0701 | 57% |
| 10 | +0.0540 | +0.0117 | 53% | +0.0769 | +0.0538 | 58% | +0.0659 | 56% |

Archetypes (frozen rules): ADVERSE_THEN_FADE IS 32 / OOS 37; CONTINUATION IS 58 / OOS 56; FADE_THEN_REVERSAL IS 34 / OOS 28; IMMEDIATE_FADE IS 74 / OOS 87; OTHER IS 2 / OOS 7.

On IS most of the mean fade had accrued by age 2 and the median went flat; in confirmation the fade kept accruing through age 10 (the strongest fixed-dollar months fall in the even months), so the path-shape claim did not replicate as frozen. Immediate fade was the most common archetype in both halves. Rank-1 paths keep fading through the hold (ALL mean +0.081 at age 2, +0.272 at age 10, favourable 83% at age 10) while ranks 2-8 are flat after age 2. Incremental session economics, partial-versus-ten-session ratios with explicit positive-denominator counts, and conditioned paths are in `reports/cg_arrow011_holding_path_summary.csv`. No hold, stop, partial exit or timing was optimized; these shapes are management hypotheses for a later arrow.

## Research-only probes, exposure-matched

| Probe | Split | n | Cohorts | Cohort-weighted return | Hit | Net per entry $ | Full-book net per $ | Exposure share | Outcome |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| P1 rank-1 only | IS | 25 | 25 | +0.327 | 88% | +0.3698 | +0.0762 | 15% |  |
| P1 rank-1 only | OOS | 27 | 27 | +0.221 | 78% | +0.2344 | +0.0797 | 16% | REPLICATED |
| P2 10-20 band and off-high | IS | 44 | 22 | +0.172 | 75% | +0.2441 | +0.0762 | 26% |  |
| P2 10-20 band and off-high | OOS | 47 | 20 | +0.116 | 72% | +0.1015 | +0.0797 | 24% | REPLICATED |
| P3 exclude near-high names priced 20-80 | IS | 131 | 25 | +0.109 | 66% | +0.1455 | +0.0762 | 69% |  |
| P3 exclude near-high names priced 20-80 | OOS | 155 | 27 | +0.098 | 60% | +0.0946 | +0.0797 | 78% | REPLICATED |
| P4 non-positive three-session momentum only | IS | 41 | 19 | +0.125 | 61% | +0.1413 | +0.0762 | 38% |  |
| P4 non-positive three-session momentum only | OOS | 50 | 21 | +0.012 | 56% | +0.0835 | +0.0797 | 45% | NOT_REPLICATED |

Probes are subsets of the certified trades with unused exposure idle; no compounded equity, drawdown or monthly return is claimed for them. P1, P2 and P3 replicated on net per entry dollar and hit rate; P4 (non-positive momentum only) did not. Reduced capital alone is not skill: the comparison is per dollar of entry exposure.

## Freelance lane

Four questions were registered with predictions before scoring and stayed inside the 30% ceiling. F1 (overlapping repeats fade less) showed the predicted direction weakly on IS and reversed in confirmation: rejected. F2 (steady grinders fade more) was rejected on IS in every month, and its reversal, episodic advances fade more, replicated. F3 (pre-order price near the partial-day low fades more) showed no separation. F4 (volume ratio inside the QUARTER state) showed no separation. Time on the lane, including the interaction maps, was about 12 minutes.

## Counterexamples and what is not known

Every leading pattern has documented counterexamples in the private casebook, chosen mechanically as the largest non-fades inside the pattern's cell. Rank-1 names that did not fade cluster in November 2025 on IS. Off-high names that kept rising exist in every month. No catalyst narrative is asserted for any of them: the lab holds no timestamped news, float or shares-outstanding history, so the event-context feature is limited to documented corporate actions effective by the signal (sparse) and is inconclusive.

Not known: whether the extremeness effect is a float or borrow-availability effect, because float history is not held; whether the 10-20 band effect is a price effect or a proxy for something else; and whether the between-cohort pre-order correlation is a market-regime signature. These are data-access limits, not tested negatives.

## Post-reveal observations, queued not claimed

- sc_ret10: IS contrast +0.059 (share 0.60), confirmation +0.117 (share 0.81).
- sc_largest_session_share_of_advance: IS contrast +0.043 (share 0.68), confirmation +0.092 (share 0.67).
- ep_sessions_since_last_selection: IS contrast -0.096 (share 0.21), confirmation -0.083 (share 0.33).
- po_open_to_preorder: IS contrast +0.003 (share 0.48), confirmation -0.072 (share 0.30).
- cx_cohort_ret15_spread: IS contrast -0.086 (share 0.36), confirmation -0.064 (share 0.26).
- ep_prior_selections: IS contrast -0.041 (share 0.48), confirmation -0.045 (share 0.26).

## Next research proposals, ranked by information value over burden, not executed

1. **Extremeness study with a pristine holdout.** Rank-1-with-gap and the off-high state as pre-registered selection descriptors on a genuinely unseen period; low burden, highest value, because both replicated here on inspected months only.
2. **Momentum-halving ablation as a frozen-signal sizing comparison.** The halving cost 55,010 mechanically and did not replicate as a signal; a same-trades comparison of R5 with mm fixed at 1 versus the frozen rule, with full monthly accounting; low burden.
3. **Hold-path management hypotheses.** Rank-1 paths keep fading through age 10 while ranks 2-8 are flat after age 2; a pre-registered age-conditional exit study on a holdout; medium burden.
4. **Float and borrow context acquisition.** As-of shares outstanding for the 10-20 band names, to test whether extremeness is a float effect; medium burden, data not held.
5. **Ten-session return and selection-age post-reveal separations** (queued from the reveal): register and test on a holdout only.

## Audit gates

| Gate | Test | Result |
|---|---|---|
| 1 | baseline hashes, counts, totals, per-trade returns unchanged; all slots and the open obligation represented | `tests/test_cg_arrow011.py::test_baseline_*` |
| 2 | no duplicate tickets or cross-panel double counting | `test_one_economic_observation_per_ticket` |
| 3 | availability cutoffs; entry-minute, future-price and future-action leakage rejected | `test_signal_close_feature_window_ends_at_the_signal_session and companions` |
| 4 | missing lookback/volume/float cannot become a favorable state | `test_missing_features_stay_missing_*` |
| 5 | four-state labels agree with the frozen rule on every ticket; HALF causes distinct | `test_four_state_labels_agree_*` |
| 6 | normalized outcomes reconcile; existing accounts identical to references | `test_sizing_neutral_return_reconciles_*, test_existing_accounts_*` |
| 7 | model/month and cohort attribution sum exactly with rounding and month allocation | `test_model_month_bridge_sums_exactly_*` |
| 8 | monthly outputs chain and reconcile to the marked cutoff | `test_monthly_rows_chain_*` |
| 9 | no post-entry fields as predictors; path labels cannot leak | `test_public_pre_entry_tables_*, test_path_archetype_*` |
| 10 | freeze before reveal, no drift | `test_freeze_was_committed_before_confirmation_*` |
| 11 | failures, sparse groups, repeats, open transitions disclosed | `test_registry_keeps_rejected_*, test_repeated_securities_*` |
| 12 | original artifacts unchanged; public/private separation by content | `test_original_baseline_artifacts_*, test_public_files_carry_no_symbols_*` |

## Monthly accounts, principal books

Published under `cg_lab_monthly_account_reporting_v1` in `reports/cg_arrow011_monthly_account.csv` for five books; account statistics in `reports/cg_arrow011_account_summary.csv`. Rows are cent-chained and reconcile to each book's marked account result at 2026-08-31, never to eventual profit.

| Month | R5 legacy | R5 causal | R4 legacy | R4 causal | R5 equity-scaled |
|---|---:|---:|---:|---:|---:|
| 2025-09 | 3,732.77 | 3,702.06 | 2,854.39 | 2,862.57 | 3,734.77 |
| 2025-10 | 14,264.72 | 14,275.66 | 16,574.55 | 16,550.30 | 14,425.68 |
| 2025-11 | 12,244.07 | 12,205.23 | 11,413.15 | 11,373.67 | 14,965.28 |
| 2025-12 | -10,792.40 | -10,902.96 | -8,288.75 | -8,394.74 | -14,344.05 |
| 2026-01 | 12,585.96 | 12,727.74 | 6,506.85 | 6,584.84 | 15,358.80 |
| 2026-02 | -988.00 | -915.16 | 2,456.20 | 2,500.67 | -2,753.18 |
| 2026-03 | 16,734.26 | 16,438.93 | 12,907.62 | 12,583.84 | 22,079.60 |
| 2026-04 | 819.81 | 848.44 | -62.62 | -90.40 | 1,080.46 |
| 2026-05 | 8,782.80 | 8,849.95 | 6,893.46 | 6,995.61 | 14,740.86 |
| 2026-06 | 41,794.94 | 41,830.29 | 31,451.40 | 31,445.28 | 79,654.64 |
| 2026-07 | 14,858.63 | 14,855.40 | 15,155.94 | 15,212.73 | 36,519.69 |
| 2026-08 | 15,165.27 | 15,070.82 | 16,792.99 | 16,697.10 | 45,257.19 |
| **Marked P&L at cutoff** | **129,202.83** | **128,986.40** | **114,655.18** | **114,321.47** | **230,719.74** |
| Positive / red / flat | 10 / 2 / 0 | 10 / 2 / 0 | 10 / 2 / 0 | 10 / 2 / 0 | 10 / 2 / 0 |
| Worst / best / median month | -10,792 / 41,795 / 12,415 | -10,903 / 41,830 / 12,466 | -8,289 / 31,451 / 9,153 | -8,395 / 31,445 / 9,185 | -14,344 / 79,655 / 14,853 |

> Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills and availability are modeled, not broker execution guarantees.

---

BASELINE PRESERVED: YES — all 16 private input hashes match their manifests, every control reproduces, a fresh replay matches the certified ledger on all 416 tickets, the oracle passes, and no Arrow 001-010 artifact was modified.

ANATOMY STUDY: COMPLETE — 52-cohort atlas, all directed sections, four freelance questions resolved, freeze and one confirmation batch, monthly reporting; optional enrichment (float, catalyst timestamps) not held and marked unavailable rather than omitted.

NEW RELATIONSHIPS: INTERNAL CONFIRMATION ONLY; NO PRISTINE OOS CLAIM

NEXT RESEARCH PROPOSALS: ranked, precisely specified, NOT EXECUTED
