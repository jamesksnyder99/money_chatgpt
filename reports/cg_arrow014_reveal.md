# CG Arrow 014 — the pristine reveal

Twelve out-of-sample months, September 2024 through August 2025, on data acquired and certified
without any strategy result being computed on it. 52 weekly cohorts,
416 selected positions, cutoff 2025-08-29.

The reveal specification — all eighteen cells, the cohort calendar, every formula, every frozen
cut and the historical reference values — was committed at `5b64dc6` before any
membership existed. The certification gate closed at `50677a0`. This run was a
single batch: every cell below was produced by one execution, and no cell was inspected before the
others existed.

Membership SHA-256 `3931985d9e7e4c4998fe386d973dea372f109a0a66c9b750424378086fbde4fb`.

## The eighteen frozen cells

| cell | model | view | hold | trades | eventual P&L | ending equity | return | hit rate | max drawdown |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Volume-Sized Short | FIXED_DOLLAR | 8 | 407 | 92,234.97 | 179,061.21 | 79.06% | 64.62% | -49.97 |
| 2 | Volume-Sized Short | FIXED_DOLLAR | 9 | 405 | 68,265.68 | 147,919.17 | 47.92% | 67.16% | -81.73 |
| 3 | Volume-Sized Short | FIXED_DOLLAR | 10 | 405 | 114,288.75 | 192,176.33 | 92.18% | 67.16% | -64.68 |
| 4 | Momentum+Volume-Sized Short | FIXED_DOLLAR | 8 | 407 | 93,809.80 | 183,553.78 | 83.55% | 64.62% | -60.52 |
| 5 | Momentum+Volume-Sized Short | FIXED_DOLLAR | 9 | 405 | 56,796.71 | 139,699.94 | 39.70% | 67.16% | -100.99 |
| 6 | Momentum+Volume-Sized Short | FIXED_DOLLAR | 10 | 405 | 109,989.20 | 191,517.07 | 91.52% | 67.16% | -72.77 |
| 7 | Momentum+Volume-Sized Short | EQUITY_SCALED | 8 | 407 | 87,496.00 | 171,862.53 | 71.86% | 64.62% | -56.78 |
| 8 | Momentum+Volume-Sized Short | EQUITY_SCALED | 9 | 405 | -74,389.81 | 22,089.61 | -77.91% | 67.16% | -98.15 |
| 9 | Momentum+Volume-Sized Short | EQUITY_SCALED | 10 | 405 | 76,355.10 | 151,844.61 | 51.84% | 67.16% | -72.35 |
| 10 | Rank-One 1.50x Reallocation | EQUITY_SCALED | 8 | 407 | 116,736.55 | 199,228.95 | 99.23% | 64.62% | -56.36 |
| 11 | Rank-One 1.50x Reallocation | EQUITY_SCALED | 9 | 405 | -70,890.87 | 25,041.63 | -74.96% | 67.16% | -98.33 |
| 12 | Rank-One 1.50x Reallocation | EQUITY_SCALED | 10 | 405 | 86,820.30 | 160,411.16 | 60.41% | 67.16% | -74.44 |
| 13 | Equal-Dollar Short | FIXED_DOLLAR | 10 | 405 | 109,697.69 | 184,572.75 | 84.57% | 67.16% | -68.43 |
| 14 | Rank-One 1.50x Reallocation | FIXED_DOLLAR | 10 | 405 | 121,071.44 | 202,093.34 | 102.09% | 67.16% | -72.58 |
| 15 | Off-High Substitution | FIXED_DOLLAR | 10 | 405 | 106,833.20 | 190,388.95 | 90.39% | 67.90% | -74.02 |
| 16 | Off-High Substitution | EQUITY_SCALED | 10 | 405 | 64,724.94 | 143,472.25 | 43.47% | 67.90% | -74.88 |
| 17 | Combined Reallocation and Substitution | FIXED_DOLLAR | 10 | 405 | 117,407.72 | 200,366.48 | 100.37% | 67.90% | -73.94 |
| 18 | Combined Reallocation and Substitution | EQUITY_SCALED | 10 | 405 | 71,472.39 | 148,797.64 | 48.80% | 67.90% | -77.03 |

Account quantities are reported separately throughout, under the frozen convention: A is the
eventual completed-trade P&L, B the marked account P&L at the cutoff, C the post-cutoff runoff
increment, D the eventual runoff P&L and E the open documented obligations. They appear in
`cg_arrow014_account_summary.csv`, and `cg_arrow014_monthly_account.csv` carries all twelve
monthly rows for every scored account under `cg_lab_monthly_account_reporting_v1`.

## Breadth: how many cohorts carried the result

| model | view | hold | cohorts | profitable | cohort hit rate | top cohort share | top 3 share |
|---|---|---|---|---|---|---|---|
| Rank-One 1.50x Reallocation | EQUITY_SCALED | 8 | 52 | 39 | 75.00% | 15.02% | 42.84% |
| Rank-One 1.50x Reallocation | EQUITY_SCALED | 9 | 52 | 37 | 71.15% | -8.43% | -22.11% |
| Rank-One 1.50x Reallocation | EQUITY_SCALED | 10 | 52 | 40 | 76.92% | 15.92% | 46.38% |
| Rank-One 1.50x Reallocation | FIXED_DOLLAR | 10 | 52 | 40 | 76.92% | 14.40% | 36.33% |
| Off-High Substitution | EQUITY_SCALED | 10 | 52 | 40 | 76.92% | 16.32% | 47.69% |
| Off-High Substitution | FIXED_DOLLAR | 10 | 52 | 40 | 76.92% | 16.13% | 41.96% |
| Combined Reallocation and Substitution | EQUITY_SCALED | 10 | 52 | 40 | 76.92% | 18.49% | 48.40% |
| Combined Reallocation and Substitution | FIXED_DOLLAR | 10 | 52 | 40 | 76.92% | 14.85% | 36.64% |
| Equal-Dollar Short | FIXED_DOLLAR | 10 | 52 | 37 | 71.15% | 16.13% | 39.08% |
| Volume-Sized Short | FIXED_DOLLAR | 8 | 52 | 36 | 69.23% | 16.69% | 41.75% |
| Volume-Sized Short | FIXED_DOLLAR | 9 | 52 | 37 | 71.15% | 21.44% | 56.04% |
| Volume-Sized Short | FIXED_DOLLAR | 10 | 52 | 38 | 73.08% | 16.04% | 36.87% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 8 | 52 | 39 | 75.00% | 17.36% | 46.97% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 9 | 52 | 37 | 71.15% | -8.89% | -22.98% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 10 | 52 | 40 | 76.92% | 16.12% | 45.48% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 8 | 52 | 39 | 75.00% | 18.45% | 48.28% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 9 | 52 | 37 | 71.15% | 27.76% | 76.13% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 10 | 52 | 40 | 76.92% | 15.67% | 41.73% |

A result carried by a handful of cohorts is a different claim from one carried by most of them,
which is why this table sits beside the headline rather than beneath it.

## Horizon attribution

| model | view | hold | trades | eventual P&L | ending equity | vs H8 | hit rate |
|---|---|---|---|---|---|---|---|
| Volume-Sized Short | FIXED_DOLLAR | 8 | 407 | 92,234.97 | 179,061.21 | 0.0 | 64.62% |
| Volume-Sized Short | FIXED_DOLLAR | 9 | 405 | 68,265.68 | 147,919.17 | -23,969.28 | 67.16% |
| Volume-Sized Short | FIXED_DOLLAR | 10 | 405 | 114,288.75 | 192,176.33 | 22,053.79 | 67.16% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 8 | 407 | 93,809.80 | 183,553.78 | 0.0 | 64.62% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 9 | 405 | 56,796.71 | 139,699.94 | -37,013.09 | 67.16% |
| Momentum+Volume-Sized Short | FIXED_DOLLAR | 10 | 405 | 109,989.20 | 191,517.07 | 16,179.40 | 67.16% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 8 | 407 | 87,496.00 | 171,862.53 | 0.0 | 64.62% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 9 | 405 | -74,389.81 | 22,089.61 | -161,885.81 | 67.16% |
| Momentum+Volume-Sized Short | EQUITY_SCALED | 10 | 405 | 76,355.10 | 151,844.61 | -11,140.90 | 67.16% |

## Rank by rank, against the historical reference

The Addendum 2 diagnostic. It is a measurement only: it may not create a top-five book, drop
ranks 6-8, change the C1 multiplier or introduce any allocation rule on this holdout.

| rank | n | pristine mean | median | hit rate | historical mean | historical hit | classification |
|---|---|---|---|---|---|---|---|
| 1 | 50 | 0.171798 | 0.238625 | 84.00% | 0.272 | 0.83 | PRISTINE_REPLICATION |
| 2 | 50 | -0.041263 | 0.181464 | 72.00% | 0.073 | 0.58 | NOT_REPLICATED |
| 3 | 52 | 0.097728 | 0.220456 | 69.23% | 0.039 | 0.52 | PRISTINE_REPLICATION |
| 4 | 50 | 0.137235 | 0.217105 | 68.00% | 0.027 | 0.5 | PRISTINE_REPLICATION |
| 5 | 49 | 0.095521 | 0.132651 | 71.43% | 0.092 | 0.62 | PRISTINE_REPLICATION |
| 6 | 51 | 0.045217 | 0.122807 | 60.78% | 0.026 | 0.49 | PRISTINE_REPLICATION |
| 7 | 52 | 0.045276 | 0.168057 | 69.23% | -0.015 | 0.46 | NOT_REPLICATED |
| 8 | 51 | 0.059061 | 0.023622 | 56.86% | 0.013 | 0.46 | PRISTINE_REPLICATION |

Rank-one replication: **PRISTINE_REPLICATION**.

## Mechanism

M1, the rank-one effect, is the load-bearing one. On this corridor rank one returns a mean
sizing-neutral 0.171798 against 0.06263 for ranks 2-8, an effect of
0.109168 where the historical study showed 0.235571 —
**SAME_DIRECTION_WEAKER**.

The full panel, all ten checks on their frozen features and Arrow 011's frozen cuts with no
refitting, is in `cg_arrow014_mechanism_confirmation.csv`, including the M10 holding-path anatomy
at every age 1 through 10.

## Falsification controls

C2 substitutes off-high names from ranks 9-20 for near-high names in ranks 2-8, and C3 combines
that with C1's rank-one reallocation. Both preserve each cohort's base capital exactly, so neither
can win by spending more. Across 52 cohorts they made
56 substitutions.

| cell | model | view | hold | eventual P&L | ending equity | return |
|---|---|---|---|---|---|---|
| 15 | Off-High Substitution | FIXED_DOLLAR | 10 | 106,833.20 | 190,388.95 | 90.39% |
| 16 | Off-High Substitution | EQUITY_SCALED | 10 | 64,724.94 | 143,472.25 | 43.47% |
| 17 | Combined Reallocation and Substitution | FIXED_DOLLAR | 10 | 117,407.72 | 200,366.48 | 100.37% |
| 18 | Combined Reallocation and Substitution | EQUITY_SCALED | 10 | 71,472.39 | 148,797.64 | 48.80% |

## Drawdown

The deepest episode on any scored account was -100.99% on Momentum+Volume-Sized Short / FIXED_DOLLAR / H9, from a peak on 2024-12-03 to a trough on 2024-12-26, recovered by 2025-05-13.

Every episode for every account is in `cg_arrow014_drawdown_episodes.csv`.

## Verification

An independent oracle recomputed every ledger from its stored inputs:
7,298 trades checked, maximum absolute error
7.3e-12. Account identities hold on every scored account and every
monthly table reconciles to its own marked account P&L at the cutoff.

## What this is not

This is one twelve-month out-of-sample period. It is not a forward test, it does not model
borrow availability or hard-to-borrow cost beyond the frozen cost model, and the account
convention assumes the frozen execution and cost rules throughout. The rank-by-rank table is a
diagnostic, not a proposal.

---
Generated 2026-09-15T22:14:33+00:00 from LOCK 1 `5b64dc6` and LOCK 2 `50677a0`.
