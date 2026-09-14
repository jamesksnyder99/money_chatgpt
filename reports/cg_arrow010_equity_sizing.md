# CG Arrow 010 — R5 equity-sizing study

Executor: Opus in Claude Code. Starting checkpoint `0e125de`. One experiment on the certified substrate: the frozen Momentum+Volume-Sized Short (`R5`), Corrected-Universe Replay (`R2`), 10-Session Hold (`H10`), causal pre-order quantities, sized either in fixed dollars or as the equivalent percentage of account equity. No hold, entry time, selection, filter, cap, throttle or redeployment rule was introduced or tested.

## The rule, frozen before scoring

For every weekly cohort the reference is the marked account equity at the close of the signal session, the last completed account close before the next-session entry. It is the same reference for all eight tickets in the cohort.

```
scale_factor    = equity at signal-session close / 100,000
intended ticket = fixed R5 tier notional * scale_factor
FULL 8,300 -> 8.300%   HALF 4,150 -> 4.150%   QUARTER 2,075 -> 2.075%   of reference equity
```

At exactly 100,000 the two books are identical in intended dollars, and the first cohort confirms it. Shares remain floored from the causal pre-order price, so an equity-responsive order is still knowable before its fill.

## Certified controls reproduced first

| Certified Arrow 008 control | Expected | Observed | Reproduces |
|---|---:|---:|---|
| legacy fill eventual completed trade pnl | 129,092.60 | 129,092.60 | yes |
| legacy fill marked account pnl at cutoff | 129,202.83 | 129,202.83 | yes |
| legacy fill marked equity at cutoff | 229,202.83 | 229,202.83 | yes |
| causal preorder eventual completed trade pnl | 128,864.62 | 128,864.62 | yes |

The fixed-dollar control was then rebuilt cohort by cohort through the same serial path the equity-scaled book uses, and reproduces the certified batch causal pre-order total exactly: true. The difference between the two books is therefore sizing alone.

## Headline account results, account of record

| Measure | Fixed-dollar R5 | Equity-scaled R5 | Difference |
|---|---:|---:|---:|
| Starting equity | 100,000.00 | 100,000.00 | 0.00 |
| Ending marked equity at 2026-08-31 | 228,986.40 | 330,719.74 | 101,733.34 |
| Marked account P&L at 2026-08-31 | 128,986.40 | 230,719.74 | 101,733.34 |
| Eventual completed-trade P&L | 128,864.62 | 230,566.36 | 101,701.73 |
| Return on starting equity | 128.99% | 230.72% | 101.73% |
| Hit rate | 0.540 | 0.540 | 0.000 |
| Average winner | 1,062.31 | 1,798.91 | 736.60 |
| Average loser | -571.17 | -902.56 | -331.39 |
| Profit factor | 2.181 | 2.337 | 0.156 |
| Max drawdown dollars | -23,309.47 | -29,172.81 | -5,863.34 |
| Max drawdown percent of peak | -17.29% | -20.96% | -3.66 pp |
| Worst day | -9,733.97 | -27,899.26 | -18,165.29 |
| Worst month | -10,902.96 | -14,344.05 | -3,441.09 |
| Median month | 12,466.49 | 14,853.07 | 2,386.59 |
| Sum of red months | -11,818.12 | -17,097.23 | -5,279.11 |
| Positive months | 10 | 10 | +0 |
| Red months | 2 | 2 | +0 |
| Mean gross exposure | 64,972.90 | 105,126.67 | 40,153.77 |
| Peak gross exposure | 123,797.77 | 262,305.20 | 138,507.43 |
| Mean gross / marked equity | 0.457 | 0.630 | 0.173 |
| 95th percentile gross / marked equity | 0.693 | 0.930 | 0.236 |
| Peak gross / marked equity | 1.030 | 1.372 | 0.341 |
| Turnover, entry notional | 1,650,681.64 | 2,779,070.46 | 1,128,388.82 |
| Exposure dollar-sessions | 16,308,198.50 | 26,386,794.40 | 10,078,595.90 |
| Time underwater | 71.71% | 71.71% | 0.00% |
| Runoff trades | 16 | 16 | 0 |
| Post-cutoff incremental runoff P&L | -0.92 | -28.86 | -27.93 |
| Open documented obligations | 1 | 1 | 0 |
| Stale gross at the calendar boundary | 3,947.63 | 4,067.71 | 120.08 |

Gross exposure is divided by the **same session's** marked equity, never by starting equity, because the question an equity-responsive rule raises is whether leverage stays put while dollars grow. It does not stay put here: mean gross against marked equity rises from 0.457 to 0.630, and the worst single session deepens from -9,733.97 to -27,899.26, a larger multiple than the account itself grew by. Both facts belong beside the higher ending equity.

## Monthly account results

Published under the frozen lab standard `cg_lab_monthly_account_reporting_v1`. Rows are stated in whole cents and chain exactly. Monthly P&L is the change in marked account equity across the month, so a position opened in one month and closed in the next contributes to both.

| Month | Fixed-dollar P&L | Equity-scaled P&L | Fixed return | Equity-scaled return |
|---|---:|---:|---:|---:|
| 2025-09 | 3,702.06 | 3,734.77 | 3.70% | 3.73% |
| 2025-10 | 14,275.66 | 14,425.68 | 13.77% | 13.91% |
| 2025-11 | 12,205.23 | 14,965.28 | 10.35% | 12.67% |
| 2025-12 | -10,902.96 | -14,344.05 | -8.38% | -10.77% |
| 2026-01 | 12,727.74 | 15,358.80 | 10.67% | 12.93% |
| 2026-02 | -915.16 | -2,753.18 | -0.69% | -2.05% |
| 2026-03 | 16,438.93 | 22,079.60 | 12.54% | 16.80% |
| 2026-04 | 848.44 | 1,080.46 | 0.58% | 0.70% |
| 2026-05 | 8,849.95 | 14,740.86 | 5.96% | 9.54% |
| 2026-06 | 41,830.29 | 79,654.64 | 26.60% | 47.05% |
| 2026-07 | 14,855.40 | 36,519.69 | 7.46% | 14.67% |
| 2026-08 | 15,070.82 | 45,257.19 | 7.05% | 15.85% |
| **Total** | **128,986.40** | **230,719.74** | | |

| Month-end marked equity | Fixed-dollar R5 | Equity-scaled R5 |
|---|---:|---:|
| 2025-09 | 103,702.06 | 103,734.77 |
| 2025-10 | 117,977.72 | 118,160.45 |
| 2025-11 | 130,182.95 | 133,125.73 |
| 2025-12 | 119,279.99 | 118,781.68 |
| 2026-01 | 132,007.73 | 134,140.48 |
| 2026-02 | 131,092.57 | 131,387.30 |
| 2026-03 | 147,531.50 | 153,466.90 |
| 2026-04 | 148,379.94 | 154,547.36 |
| 2026-05 | 157,229.89 | 169,288.22 |
| 2026-06 | 199,060.18 | 248,942.86 |
| 2026-07 | 213,915.58 | 285,462.55 |
| 2026-08 | 228,986.40 | 330,719.74 |

Both books reconcile exactly to their own marked account result at 2026-08-31: true and true. They deliberately do not reconcile to eventual completed-trade P&L, which contains exits scheduled after August closes. Positions still open at the boundary are carried in the August equity at their last observed marks, and one documented open obligation remains under a documented trading suspension in each book.

## Where the difference comes from

Total incremental P&L from equity scaling: **101,701.69**.

| Diagnostic | Value |
|---|---:|
| Scale factor, first cohort | 1.000x |
| Scale factor, minimum | 1.000x |
| Scale factor, median | 1.385x |
| Scale factor, maximum | 3.159x |
| Scale factor, final cohort | 3.159x |
| First cohort at or above 1.10x | 2025-10-22 |
| First cohort at or above 1.25x | 2025-11-05 |
| First cohort at or above 1.50x | 2026-03-25 |
| First cohort at or above 2.00x | 2026-06-17 |
| Uplift share, June-August 2026 signals | 84.94% |
| Uplift share, top 1 cohort | 18.12% |
| Uplift share, top 3 cohorts | 41.97% |
| Uplift share, top 5 cohorts | 62.42% |
| Uplift from trades that won under fixed dollars | 164,997.67 |
| Extra loss from trades that lost under fixed dollars | -63,295.94 |
| Incremental P&L, FULL tier | 51,017.60 |
| Incremental P&L, HALF tier | 33,926.05 |
| Incremental P&L, QUARTER tier | 16,758.08 |
| Incremental max drawdown dollars | -5,863.34 |
| Incremental max drawdown, percent of peak | -3.66 pp |
| Mean gross / equity, fixed vs scaled | 0.457 vs 0.630 |

### Does leverage stay put as dollars grow?

This is a question about each book's own path over time, not about the gap between the books. Comparing the two averages would mistake the fixed book's de-levering for drift in the scaled book, which gets the causation backwards.

| Gross / marked equity | First half of sessions | Second half | Drift |
|---|---:|---:|---:|
| Fixed-dollar R5 | 0.520 | 0.394 | -0.126 |
| Equity-scaled R5 | 0.621 | 0.638 | +0.017 |

The equity-scaled book holds the leverage it was designed to hold: its gross/equity ratio drifts by +0.017 between the halves. The fixed-dollar book drifts by -0.126, because its tickets do not follow the account, so it sheds leverage as equity grows. The higher mean ratio in the scaled book is therefore the absence of that de-levering, not new leverage on top of the design. What the design itself permits is visible at the peak: gross exposure reaches 1.372 times marked equity, above one, against 1.030 fixed.

Per-cohort sizing paths for all 52 cohorts, including reference equity, scale factor, intended cohort notional under each rule, realized cohort P&L under each rule and the post-entry gross/equity ratio, are in `reports/cg_arrow010_cohort_scaling.csv`.

## Reading the result

**Mechanically expected.** A rule that multiplies ticket size by account equity will place larger dollar tickets once the account grows. None of the uplift is evidence that the signal improved; the per-trade price return before sizing is identical between the two books to 0.0e+00, and no trade was added, removed, substituted or re-ranked.

**Sequence dependence.** The strongest fixed-dollar month of this sample falls late, so the largest tickets and the strongest returns coincide. 84.94% of the total uplift comes from June through August 2026 signals alone. That is a property of this sample's ordering, not of the sizing rule. A sample with the same months in a different order would compound differently, and a sample whose losses fell late would compound the losses instead.

**Risk efficiency.** Marked account P&L per dollar of maximum drawdown is 5.534 fixed and 7.909 scaled, so the return bought more per dollar of drawdown than it cost. The costs are real and belong in the same sentence. Maximum drawdown deepens from -23,309.47 to -29,172.81 and from -17.29% to -20.96% of its own peak, the worst single session deepens from -9,733.97 to -27,899.26, and peak gross exposure reaches 1.372 times marked equity against 1.030 fixed. A short book carrying more gross than its own equity is a financing and locate question this arrow does not answer.

**Unresolved and out of scope.** This arrow answers nothing about capital redeployment after early exits, gross-exposure caps, leverage sweeps, drawdown throttles, volatility targeting, other hold lengths or broker-specific short availability at larger ticket sizes. Those require their own arrows and, in the case of borrow capacity at scale, data this lab does not hold.

## Split reporting

The historical out-of-sample months have already been inspected repeatedly in earlier research, so the split comparison below is descriptive robustness evidence and **not** a pristine confirmation. The sizing formula was frozen before scoring and was not chosen, tuned or changed after seeing any result. Each split row is a standalone book that restarts at 100,000 starting equity, so its scale path is its own; the account of record is the all-cohort row.

| Sizing mode | Split | Marked account P&L | Return on starting equity | Max drawdown | Mean gross / equity |
|---|---|---:|---:|---:|---:|
| Fixed-dollar R5 | IS | 58,670.34 | 58.67% | -11,773.84 | 0.238 |
| Fixed-dollar R5 | OOS | 70,316.06 | 70.32% | -24,773.16 | 0.289 |
| Fixed-dollar R5 | ALL | 128,986.40 | 128.99% | -23,309.47 | 0.457 |
| Equity-scaled R5 | IS | 74,319.31 | 74.32% | -16,988.65 | 0.286 |
| Equity-scaled R5 | OOS | 90,159.19 | 90.16% | -30,162.86 | 0.347 |
| Equity-scaled R5 | ALL | 230,719.74 | 230.72% | -29,172.81 | 0.630 |

## Verification

| Check | Result |
|---|---|
| Certified Arrow 008 controls reproduce | 4 of 4 |
| Selection, tiers, sessions and prices identical between books | yes |
| Per-trade price return before sizing identical | max gap 0.0e+00 |
| Causality violations in the sizing path | 0 |
| Pricing-window observations missing | 0 |
| Account identities hold | 6 of 6 |
| Monthly rows chain and reconcile | 2 of 2 books |
| Independent oracle | trades 830 checked, max error 3.6e-12 |
| Independent equity-sizing recomputation | 416 tickets, 0 disagreements |
| Public/private separation | intact |

Every equity-scaled share count was re-derived by the independent oracle from stored inputs only: for each cohort it rebuilds the account from strictly earlier cohorts, reads marked equity at the signal close, and floors the scaled tier notional against the stored causal pre-order price. It never consults the sizing engine or the scale factors that engine recorded, so a look-ahead, a wrong reference or a wrong integer rule would surface there.

> Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow fees for Trading API users; short availability and other security-specific costs may still vary.

---

# RESEARCH STATUS: EQUITY SCALING IS ECONOMICALLY ATTRACTIVE FOR FURTHER STUDY

This is a research interpretation of one historical sample, not a production deployment decision and not a claim about future returns.

NEXT RECOMMENDED STEP: CAPITAL REDEPLOYMENT STUDY
