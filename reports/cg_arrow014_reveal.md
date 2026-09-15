# CG Arrow 014 — the pristine reveal

Twelve out-of-sample months, September 2024 through August 2025, on data acquired and certified
without any strategy result being computed on it. 52 weekly cohorts,
416 selected positions, cutoff 2025-08-29.

The reveal specification — all eighteen cells, the cohort calendar, every formula, every frozen
cut and the historical reference values — was committed at `5b64dc6` before any
membership existed. The certification gate closed at `7780f95`. This run was a
single batch: every cell below was produced by one execution, and no cell was inspected before the
others existed.

Membership SHA-256 `339c86ca6a4362e3f7c448c49be65427d0be33b9512e071d105847e14bdbf7dc`.

## The eighteen frozen cells

| cell | model | view | hold | trades | eventual P&L | ending equity | return | hit rate | max drawdown |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Volume-Sized Short | FIXED_DOLLAR | 8 | 408 | 4,840.16 | 103,369.16 | 3.37% | 52.94% | -45.09 |
| 2 | Volume-Sized Short | FIXED_DOLLAR | 9 | 408 | -21,571.20 | 76,541.91 | -23.46% | 53.68% | -70.59 |
| 3 | Volume-Sized Short | FIXED_DOLLAR | 10 | 408 | 11,245.17 | 109,010.74 | 9.01% | 53.43% | -54.75 |
| 4 | Momentum+Volume-Sized Short | FIXED_DOLLAR | 8 | 408 | 7,758.58 | 107,452.16 | 7.45% | 52.94% | -51.07 |
| 5 | Momentum+Volume-Sized Short | FIXED_DOLLAR | 9 | 408 | -27,838.58 | 71,740.83 | -28.26% | 53.68% | -82.51 |
| 6 | Momentum+Volume-Sized Short | FIXED_DOLLAR | 10 | 408 | 12,449.24 | 111,792.52 | 11.79% | 53.43% | -59.86 |
| 7 | Momentum+Volume-Sized Short | EQUITY_SCALED | 8 | 408 | -2,172.74 | 98,217.21 | -1.78% | 52.94% | -45.10 |
| 8 | Momentum+Volume-Sized Short | EQUITY_SCALED | 9 | 408 | -45,516.36 | 54,566.04 | -45.43% | 53.68% | -70.62 |
| 9 | Momentum+Volume-Sized Short | EQUITY_SCALED | 10 | 408 | -2,347.44 | 97,322.11 | -2.68% | 53.43% | -58.28 |
| 10 | Rank-One 1.50x Reallocation | EQUITY_SCALED | 8 | 408 | 4,685.31 | 104,105.56 | 4.11% | 52.94% | -45.01 |
| 11 | Rank-One 1.50x Reallocation | EQUITY_SCALED | 9 | 408 | -44,374.01 | 55,075.25 | -44.92% | 53.68% | -72.14 |
| 12 | Rank-One 1.50x Reallocation | EQUITY_SCALED | 10 | 408 | 2,288.88 | 100,693.40 | 0.69% | 53.43% | -58.56 |
| 13 | Equal-Dollar Short | FIXED_DOLLAR | 10 | 408 | 6,823.38 | 106,046.99 | 6.05% | 53.43% | -58.69 |
| 14 | Rank-One 1.50x Reallocation | FIXED_DOLLAR | 10 | 408 | 18,686.80 | 116,794.32 | 16.79% | 53.43% | -59.78 |
| 15 | Off-High Substitution | FIXED_DOLLAR | 10 | 408 | 29,600.31 | 127,383.94 | 27.38% | 58.82% | -57.63 |
| 16 | Off-High Substitution | EQUITY_SCALED | 10 | 408 | 20,084.79 | 117,858.05 | 17.86% | 58.82% | -54.94 |
| 17 | Combined Reallocation and Substitution | FIXED_DOLLAR | 10 | 408 | 33,871.58 | 130,761.39 | 30.76% | 58.82% | -57.31 |
| 18 | Combined Reallocation and Substitution | EQUITY_SCALED | 10 | 408 | 24,351.98 | 121,028.93 | 21.03% | 58.82% | -55.02 |

Account quantities are reported separately throughout, under the frozen convention: A is the
eventual completed-trade P&L, B the marked account P&L at the cutoff, C the post-cutoff runoff
increment, D the eventual runoff P&L and E the open documented obligations. They appear in
`cg_arrow014_account_summary.csv`, and `cg_arrow014_monthly_account.csv` carries all twelve
monthly rows for every scored account under `cg_lab_monthly_account_reporting_v1`.

## Breadth: how many cohorts carried the result

| model | view | hold | cohorts | profitable | cohort hit rate | top cohort share | top 3 share |
|---|---|---|---|---|---|---|---|
| Rank-One 1.50x Reallocation | EQUITY_SCALED | 8 | 52 | 27 | 51.92% | 2.66 | 7.30 |
| Rank-One 1.50x Reallocation | EQUITY_SCALED | 9 | 52 | 26 | 50.00% | -16.06% | -44.48% |
| Rank-One 1.50x Reallocation | EQUITY_SCALED | 10 | 52 | 29 | 55.77% | 5.77 | 15.78 |
| Rank-One 1.50x Reallocation | FIXED_DOLLAR | 10 | 52 | 29 | 55.77% | 100.05% | 2.58 |
| Off-High Substitution | EQUITY_SCALED | 10 | 52 | 27 | 51.92% | 64.06% | 1.70 |
| Off-High Substitution | FIXED_DOLLAR | 10 | 52 | 27 | 51.92% | 63.91% | 1.52 |
| Combined Reallocation and Substitution | EQUITY_SCALED | 10 | 52 | 31 | 59.62% | 54.74% | 147.70% |
| Combined Reallocation and Substitution | FIXED_DOLLAR | 10 | 52 | 31 | 59.62% | 57.34% | 135.76% |
| Equal-Dollar Short | FIXED_DOLLAR | 10 | 52 | 25 | 48.08% | 2.22 | 5.47 |
| Volume-Sized Short | FIXED_DOLLAR | 8 | 52 | 24 | 46.15% | 2.66 | 7.36 |
| Volume-Sized Short | FIXED_DOLLAR | 9 | 52 | 26 | 50.00% | -76.77% | -1.75 |
| Volume-Sized Short | FIXED_DOLLAR | 10 | 52 | 27 | 51.92% | 1.73 | 3.69 |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 8 | 52 | 24 | 46.15% | -5.69 | -14.00 |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 9 | 52 | 26 | 50.00% | -15.20% | -41.18% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 10 | 52 | 29 | 55.77% | -5.12 | -13.97 |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 8 | 52 | 23 | 44.23% | 2.42 | 5.39 |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 9 | 52 | 26 | 50.00% | -62.08% | -1.58 |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 10 | 52 | 29 | 55.77% | 145.85% | 3.78 |

A result carried by a handful of cohorts is a different claim from one carried by most of them,
which is why this table sits beside the headline rather than beneath it.

## Horizon attribution

| model | view | hold | trades | eventual P&L | ending equity | vs H8 | hit rate |
|---|---|---|---|---|---|---|---|
| Volume-Sized Short | FIXED_DOLLAR | 8 | 408 | 4,840.16 | 103,369.16 | 0.0 | 52.94% |
| Volume-Sized Short | FIXED_DOLLAR | 9 | 408 | -21,571.20 | 76,541.91 | -26,411.36 | 53.68% |
| Volume-Sized Short | FIXED_DOLLAR | 10 | 408 | 11,245.17 | 109,010.74 | 6,405.02 | 53.43% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 8 | 408 | 7,758.58 | 107,452.16 | 0.0 | 52.94% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 9 | 408 | -27,838.58 | 71,740.83 | -35,597.16 | 53.68% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 10 | 408 | 12,449.24 | 111,792.52 | 4,690.66 | 53.43% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 8 | 408 | -2,172.74 | 98,217.21 | 0.0 | 52.94% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 9 | 408 | -45,516.36 | 54,566.04 | -43,343.62 | 53.68% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 10 | 408 | -2,347.44 | 97,322.11 | -174.70 | 53.43% |

## Rank by rank, against the historical reference

The Addendum 2 diagnostic. It is a measurement only: it may not create a top-five book, drop
ranks 6-8, change the C1 multiplier or introduce any allocation rule on this holdout.

| rank | n | pristine mean | median | hit rate | historical mean | historical hit | classification |
|---|---|---|---|---|---|---|---|
| 1 | 49 | 0.063914 | 0.081118 | 71.43% | 0.272 | 0.83 | SAME_DIRECTION_WEAKER |
| 2 | 49 | -0.02222 | 0.044381 | 65.31% | 0.073 | 0.58 | NOT_REPLICATED |
| 3 | 51 | 0.017035 | 0.008532 | 54.90% | 0.039 | 0.52 | SAME_DIRECTION_WEAKER |
| 4 | 52 | 0.036866 | 0.001089 | 51.92% | 0.027 | 0.5 | PRISTINE_REPLICATION |
| 5 | 52 | 0.04599 | 0.026706 | 57.69% | 0.092 | 0.62 | SAME_DIRECTION_WEAKER |
| 6 | 52 | -0.017943 | 0.004996 | 50.00% | 0.026 | 0.49 | NOT_REPLICATED |
| 7 | 52 | -0.050741 | -0.004374 | 48.08% | -0.015 | 0.46 | PRISTINE_REPLICATION |
| 8 | 51 | -0.015133 | -0.003811 | 41.18% | 0.013 | 0.46 | NOT_REPLICATED |

Rank-one replication: **SAME_DIRECTION_WEAKER**.

## Mechanism

M1, the rank-one effect, is the load-bearing one. On this corridor rank one returns a mean
sizing-neutral 0.063914 against -0.00071 for ranks 2-8, an effect of
0.064624 where the historical study showed 0.235571 —
**SAME_DIRECTION_WEAKER**.

The full panel, all ten checks on their frozen features and Arrow 011's frozen cuts with no
refitting, is in `cg_arrow014_mechanism_confirmation.csv`, including the M10 holding-path anatomy
at every age 1 through 10.

## Falsification controls

C2 substitutes off-high names from ranks 9-20 for near-high names in ranks 2-8, and C3 combines
that with C1's rank-one reallocation. Both preserve each cohort's base capital exactly, so neither
can win by spending more. Across 52 cohorts they made
120 substitutions.

| cell | model | view | hold | eventual P&L | ending equity | return |
|---|---|---|---|---|---|---|
| 15 | Off-High Substitution | FIXED_DOLLAR | 10 | 29,600.31 | 127,383.94 | 27.38% |
| 16 | Off-High Substitution | EQUITY_SCALED | 10 | 20,084.79 | 117,858.05 | 17.86% |
| 17 | Combined Reallocation and Substitution | FIXED_DOLLAR | 10 | 33,871.58 | 130,761.39 | 30.76% |
| 18 | Combined Reallocation and Substitution | EQUITY_SCALED | 10 | 24,351.98 | 121,028.93 | 21.03% |

## Drawdown

The deepest episode on any scored account was -82.51% on Momentum+Volume-Sized Short / FIXED_DOLLAR / H9, from a peak on 2024-10-07 to a trough on 2024-12-27, not recovered inside the corridor.

Every episode for every account is in `cg_arrow014_drawdown_episodes.csv`.

## Verification

An independent oracle recomputed every ledger from its stored inputs:
7,344 trades checked, maximum absolute error
7.3e-12. Account identities hold on every scored account and every
monthly table reconciles to its own marked account P&L at the cutoff.

## What this is not

This is one twelve-month out-of-sample period. It is not a forward test, it does not model
borrow availability or hard-to-borrow cost beyond the frozen cost model, and the account
convention assumes the frozen execution and cost rules throughout. The rank-by-rank table is a
diagnostic, not a proposal.

---
Generated 2026-09-15T22:31:51+00:00 from LOCK 1 `5b64dc6` and LOCK 2 `7780f95`.
