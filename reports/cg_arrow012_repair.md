# CG Arrow 012 Phase A — Arrow 011 measurement repair

The Arrow 011 within-cohort statistic sorted a cohort's eight rows by feature and split them at the midpoint. Where equal feature values straddled that midpoint the split fell to the original row order, so a feature that never varies inside a cohort could still report a nonzero within-cohort effect. This phase replaces that statistic with two order-invariant ones and keeps Spearman correlation on average ranks as the third view. No Arrow 011 artifact was modified and no frozen trade, quantity or account was touched; the repaired numbers are published under Arrow 012 filenames.

## The two repaired statistics

**Strict half contrast.** Sort by feature, compare the top half's mean outcome with the bottom half's, but score the cohort only when the feature values on either side of the median boundary differ. When a tie crosses that boundary the cohort is unscorable for this contrast rather than being decided by row position. Scored and excluded cohort counts are reported for every feature.

**Pairwise directional effect.** Within a cohort, take every unordered pair whose feature values differ, orient the outcome difference from the lower-feature row to the higher-feature row, and average. Ties contribute nothing, so no ordering is invented. Units are outcome units per distinct-feature pair; the outcome is the sizing-neutral ten-session short price return.

Both accumulate with exact summation, so a row permutation cannot move even the last bit. The first version of this module used a running total and drifted by about 1e-16 under permutation; the invariance test caught it and the accumulation was made exact.

## What the repair found

| Repair verdict | Features |
|---|---:|
| SURVIVES_REPAIR | 18 |
| STILL_NO_SIGNAL | 14 |
| APPEARS_ONLY_AFTER_REPAIR | 8 |
| UNSCORABLE_AFTER_REPAIR | 2 |

Every one of the 15 relationships Arrow 011 reported as replicated survives the repair with the same sign and one-sided support. The tie defect was real but it did not carry any claimed finding; it carried two features Arrow 011 had already declined to claim.

| Feature | Arrow 011 half-split | Repaired strict half | Cohorts tie-excluded | Repaired pairwise | One-sided share | Verdict |
|---|---:|---:|---:|---:|---:|---|
| sc_close_vs_high20 | -0.163 | -0.163 | 0 | -0.1363 | 0.16 | SURVIVES_REPAIR |
| sc_position_in_range20 | -0.164 | -0.164 | 0 | -0.1267 | 0.16 | SURVIVES_REPAIR |
| cx_gap_to_next_rank | +0.129 | +0.129 | 0 | +0.1238 | 0.92 | SURVIVES_REPAIR |
| sc_mean_range_pct_10 | +0.162 | +0.162 | 0 | +0.1192 | 0.88 | SURVIVES_REPAIR |
| po_partial_range_pct | +0.160 | +0.160 | 0 | +0.1097 | 0.88 | SURVIVES_REPAIR |
| sc_up_sessions_15 | -0.101 | -0.094 | 12 | -0.1027 | 0.12 | SURVIVES_REPAIR |
| sc_close_vs_max_close15 | -0.123 | -0.090 | 9 | -0.0962 | 0.36 | SURVIVES_REPAIR |
| cx_rank_in_eight | -0.086 | -0.086 | 0 | -0.0955 | 0.16 | SURVIVES_REPAIR |
| cx_ret15_field_percentile | +0.086 | +0.086 | 0 | +0.0955 | 0.84 | SURVIVES_REPAIR |
| cx_ret15_minus_cohort_median | +0.086 | +0.086 | 0 | +0.0955 | 0.84 | SURVIVES_REPAIR |
| sc_ret15 | +0.086 | +0.086 | 0 | +0.0955 | 0.84 | SURVIVES_REPAIR |
| sc_logret_std_15 | +0.137 | +0.137 | 0 | +0.0951 | 0.84 | SURVIVES_REPAIR |
| sc_signal_day_range_pct | +0.128 | +0.128 | 0 | +0.0932 | 0.76 | SURVIVES_REPAIR |
| sc_signal_close | -0.105 | -0.105 | 0 | -0.0854 | 0.20 | SURVIVES_REPAIR |

### The two features the tie defect actually carried

**Cohort ranking-return spread.** Arrow 011 reported a within-cohort effect of -0.086. The feature is the same value for all eight names in a cohort and is constant in all 25 in-sample cohorts, so it has no within-cohort variation at all. The repaired statistics report it unscorable and the reported effect was entirely row order. Arrow 011 had already flagged this row as an artifact in prose; the repair now proves it mechanically.

**Sessions since the last selection.** Arrow 011 reported -0.096 on 84 rows. Only 7 cohorts have four or more scorable rows, because the feature exists only for repeat selections. It is unscorable after repair for lack of support, not because the direction flipped.

### The direct rank-one group result is independent of any of this

| Split | Rank-one n | Rank-one mean | Rank-one hit rate |
|---|---:|---:|---:|
| IS | 25 | +0.327 | 88.0% |
| OOS | 27 | +0.221 | 77.8% |
| ALL | 52 | +0.272 | 82.7% |

This is a direct group mean over one ticket per cohort, so it uses no within-cohort contrast and no tie handling. It is unchanged by the repair, and it is the relationship the challenger phase actually tests.

## Dependence diagnostics

The Arrow 011 resampling drew whole cohorts, which preserves the eight names inside a cohort but no serial dependence between neighbouring cohorts. It is kept and now stated accurately, and contiguous moving blocks of two and four cohorts are added. Overlapping ten-session holds span adjacent cohorts, so a finding carried by one contiguous episode should widen under the larger blocks.

| Relationship | Block 1 p05..p95 | Block 2 p05..p95 | Block 4 p05..p95 | First episodes | Overlapping repeats |
|---|---:|---:|---:|---:|---:|
| cx_gap_to_next_rank | +0.097..+0.152 | +0.093..+0.148 | +0.103..+0.140 | +0.141 | +0.159 |
| cx_rank_in_eight | -0.125..-0.061 | -0.124..-0.058 | -0.131..-0.055 | -0.112 | -0.080 |
| cx_ret15_field_percentile | +0.062..+0.125 | +0.059..+0.125 | +0.056..+0.132 | +0.112 | +0.080 |
| cx_ret15_minus_cohort_median | +0.062..+0.125 | +0.059..+0.125 | +0.056..+0.132 | +0.112 | +0.080 |
| po_partial_range_pct | +0.081..+0.137 | +0.076..+0.143 | +0.080..+0.148 | +0.137 | +0.118 |
| sc_close_vs_high20 | -0.180..-0.097 | -0.184..-0.100 | -0.172..-0.115 | -0.121 | -0.082 |
| sc_close_vs_max_close15 | -0.161..-0.031 | -0.182..-0.034 | -0.156..-0.051 | -0.036 | -0.049 |
| sc_dollar_volume_cv20 | +0.027..+0.094 | +0.022..+0.086 | +0.026..+0.095 | +0.058 | +0.068 |

The spreads widen only slightly from block 1 to block 4 for the leading relationships, and the effect is present in both first selections and overlapping repeats. These diagnostics state what they preserve; they are not significance tests and they do not decide anything.

## Repair verdict

**A11_RELATIONSHIP_SURVIVES_REPAIR**

**A11_RELATIONSHIP_UNAFFECTED_DIRECT_GROUP_RESULT** for the rank-one group result, which uses no within-cohort statistic.

The repair changed no Arrow 011 conclusion that Arrow 011 claimed. It removed two rows Arrow 011 had already declined to claim, and it makes the remaining evidence order-invariant by construction rather than by inspection. No new filter or threshold was invented.

> Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills and availability are modeled, not broker execution guarantees.
