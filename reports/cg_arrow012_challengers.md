# CG Arrow 012 Phase B — two whole-engine challengers and their interaction

Freeze commit `8d05bcc`, scoring run `8d05bcc`. Scored on the frozen 52 cohorts from September 2025 through August 2026 only. The additional historical year is untouched: no cohort outside the frozen set was read, ranked, featurized, scored or summarized, and the guard is tested.

## Headline

| | Incumbent C0 | Rank-one 1.50x C1 | Off-high substitution C2 | Combined C3 |
|---|---:|---:|---:|---:|
| **Equity-scaled, primary** | | | | |
| Ending marked equity | 330,720 | 437,801 | 278,262 | 363,432 |
| Marked account P&L at 2026-08-31 | 230,720 | 337,801 | 178,262 | 263,432 |
| Return on starting equity | 230.7% | 337.8% | 178.3% | 263.4% |
| Max drawdown dollars | -29,173 | -35,472 | -36,894 | -36,335 |
| Max drawdown percent of peak | -20.96% | -9.45% | -27.22% | -25.90% |
| Worst day | -27,899 | -35,472 | -13,868 | -19,278 |
| Hit rate | 0.540 | 0.540 | 0.578 | 0.578 |
| Profit factor | 2.34 | 2.79 | 2.08 | 2.48 |
| Rank-one share of entry notional | 15.3% | 22.9% | 13.7% | 20.5% |
| Rank-one share of P&L | 59.5% | 71.3% | 60.5% | 71.5% |
| Mean gross over marked equity | 0.630 | 0.618 | 0.630 | 0.620 |
| Peak gross over marked equity | 1.372 | 1.425 | 1.367 | 1.419 |
| Time underwater | 71.7% | 67.3% | 76.1% | 70.9% |
| **Fixed-dollar, diagnostic** | | | | |
| Marked account P&L at 2026-08-31 | 128,986 | 160,073 | 113,414 | 142,529 |
| Max drawdown dollars | -23,309 | -22,338 | -31,016 | -29,360 |
| Worst day | -9,734 | -15,624 | -8,930 | -14,354 |

Every account holds the same 416 intended positions, 415 completed and one documented open obligation, and every cohort's base intended capital is identical across all four to floating-point precision. A challenger cannot win here by spending more.

## C0 reproduces Arrow 010 exactly

| Control | Expected | Observed |
|---|---:|---:|
| equity scaled eventual | 230,566.36 | 230,566.36 |
| equity scaled ending equity | 330,719.74 | 330,719.74 |
| fixed dollar eventual | 128,864.62 | 128,864.62 |
| fixed dollar ending equity | 228,986.40 | 228,986.40 |

## C1, rank-one 1.50x reallocation

| Attribution | Equity-scaled | Fixed-dollar |
|---|---:|---:|
| Extra P&L from the larger rank-one ticket | 104,072 | 37,575 |
| P&L change from reducing ranks 2-8 | 3,738 | -6,281 |
| Complete account marked P&L change | 107,082 | 31,087 |
| Worst single rank-one loss, incumbent | -8,097 | -5,604 |
| Worst single rank-one loss, challenger | -13,254 | -8,414 |
| Rank-one share of entry notional | 15.3% to 22.9% | 15.4% to 23.2% |
| Max drawdown | -29,173 to -35,472 | -23,309 to -22,338 |
| Worst day | -27,899 to -35,472 | -9,734 to -15,624 |
| Mean gross over marked equity | 0.6296 to 0.6175 | 0.4566 to 0.4252 |

The complete account improves in both views, and the improvement is not an artifact of compounding: the fixed-dollar account gains as well. The names, entry sessions, exit sessions and prices are identical to the incumbent, so the hit rate is unchanged and every dollar of difference is allocation.

The costs are real and belong in the same paragraph. The worst single session deepens by more than half in both views, from -27,899 to -35,472 equity-scaled. Maximum drawdown in dollars worsens in the equity-scaled account, although as a percentage of its own peak it improves sharply, from -20.96% to -9.45%, because the account is larger. Concentration rises materially: rank one moves from 15.3% to 22.9% of entry notional and from 59.5% to 71.3% of P&L. One name per week now carries close to three quarters of the result.

## C2, off-high substitution from original ranks 9-20

| Substitution | Value |
|---|---:|
| Cohorts by number of swaps | {"0": 2, "1": 7, "2": 9, "3": 22, "4": 10, "5": 2} |
| Total swaps | 141 |
| Mean original rank, outgoing | 5.69 |
| Mean original rank, incoming | 13.20 |
| Median distance from the 20-session high, outgoing | -0.022 |
| Median distance from the 20-session high, incoming | -0.093 |
| Sizing-neutral ten-session return, outgoing mean / median | +0.0050 / -0.0007 |
| Sizing-neutral ten-session return, incoming mean / median | -0.0058 / +0.0185 |
| Hit rate, outgoing / incoming | 47.5% / 57.4% |
| Profit forfeited on outgoing winners | 31,809 |
| Loss avoided on outgoing losers | 30,227 |
| Profit gained on incoming winners | 45,275 |
| Loss added on incoming losers | -44,359 |
| Net paired swap effect, fixed-dollar | -666 |

The substitution does what the Arrow 011 anatomy said it should at the name level. The incoming names are much further below their recent high, they fade more often than the names they replace (57.4% against 47.5%), and their median sizing-neutral return is better. The paired swap itself is close to a wash in dollars.

**And the complete account is materially worse.** Marked account P&L falls by 52,458 equity-scaled and 15,573 fixed-dollar. The reason is the budget neutrality the arrow correctly requires. The incoming off-high names carry higher frozen R5 tiers than the near-high names they replace, so the substituted lineup's raw base notionals are about half again as large. Normalizing back to the incumbent cohort budget therefore scales the whole lineup down by a median factor near 0.90, and that reduction falls on the retained names too, including the protected rank one, whose base allocation drops by about a tenth. Rank one supplies roughly 60% of the incumbent's P&L, so paying for the new names by shrinking it costs more than the new names earn.

Decomposed on the fixed-dollar account, the difference is not in the swap at all:

| Component | Fixed-dollar | Equity-scaled |
|---|---:|---:|
| P&L given up on the 141 removed tickets | -1,581 | -7,329 |
| P&L earned by the 141 added tickets | 915 | 3,914 |
| P&L change on the 275 retained tickets, from resizing alone | -14,162 | -47,098 |
| Total eventual completed-trade change | -14,828 | -50,513 |

This is the clearest result in the arrow, and it is exactly the scientific principle the arrow was written to enforce. A component relationship that is real at the name level became a loss once it was priced as a complete engine under an honest budget constraint.

### Sensitivity to cohorts whose lineup a data failure changed

Six cohorts had their substitution changed by unresolved candidate evidence rather than by the rule: an off-high rank 9-20 name failed certification, so either a worse-ranked replacement entered or fewer swaps happened. They were named in the committed freeze before any economics, together with a pre-declared revert sensitivity. Reverting them to the incumbent lineup:

| | C2 | C2 reverted | C3 | C3 reverted |
|---|---:|---:|---:|---:|
| Marked P&L versus incumbent, equity-scaled | -52,458 | -36,832 | 32,712 | 53,631 |
| Marked P&L versus incumbent, fixed-dollar | -15,573 | -10,243 | 13,542 | 19,013 |

The C2 conclusion does not depend on those cohorts: reverting them narrows the loss but leaves it a loss in both views. C2 is therefore scorable rather than inconclusive. C3 stays positive against the incumbent either way and well below C1 either way. Reverting helps both substitution books, which is consistent with the finding below that substitution costs rather than earns; it is reported because it was pre-declared, not because it flatters anything.

## C3 and the interaction

| View | Quantity | C0 | C1 | C2 | C3 | C1 + C2 - C0 | Interaction |
|---|---|---:|---:|---:|---:|---:|---:|
| FIXED_DOLLAR | eventual completed trade pnl | 128,865 | 160,159 | 114,037 | 143,238 | 145,331 | -2,093 |
| FIXED_DOLLAR | marked account pnl at cutoff | 128,986 | 160,073 | 113,414 | 142,529 | 144,500 | -1,972 |
| EQUITY_SCALED | eventual completed trade pnl | 230,566 | 338,377 | 180,053 | 266,026 | 287,864 | -21,838 |
| EQUITY_SCALED | marked account pnl at cutoff | 230,720 | 337,801 | 178,262 | 263,432 | 285,344 | -21,912 |

The interaction is strongly negative in the equity-scaled account and mildly negative fixed-dollar. The mechanism is direct: both changes pull the same lever, in opposite directions. C1 works by giving rank one more capital, raising its base allocation to 1.500 times the incumbent in every cohort. C2 pays for its replacements by shrinking the whole lineup, which cuts rank one to a median 0.897 times the incumbent. Combined, rank one lands at a median 1.346 times rather than 1.500, so C3 gets a diluted version of the change that actually works. Adding the component results would have overstated C3 by about 22,000 equity-scaled, which is why the arrow required C3 to be built as its own account.

For nonlinear risk metrics the four actual values are reported side by side and no additive decomposition is forced:

| View | Metric | C0 | C1 | C2 | C3 |
|---|---|---:|---:|---:|---:|
| FIXED_DOLLAR | max drawdown dollars | -23,309 | -22,338 | -31,016 | -29,360 |
| FIXED_DOLLAR | max drawdown pct of peak | -17 | -16 | -23 | -22 |
| FIXED_DOLLAR | worst day | -9,734 | -15,624 | -8,930 | -14,354 |
| FIXED_DOLLAR | peak gross over marked equity | 1.0303 | 1.0291 | 1.0979 | 1.0923 |
| FIXED_DOLLAR | mean gross over marked equity | 0.4566 | 0.4252 | 0.4770 | 0.4442 |
| FIXED_DOLLAR | hit rate | 0.5398 | 0.5398 | 0.5783 | 0.5783 |
| EQUITY_SCALED | max drawdown dollars | -29,173 | -35,472 | -36,894 | -36,335 |
| EQUITY_SCALED | max drawdown pct of peak | -21 | -9 | -27 | -26 |
| EQUITY_SCALED | worst day | -27,899 | -35,472 | -13,868 | -19,278 |
| EQUITY_SCALED | peak gross over marked equity | 1.3717 | 1.4250 | 1.3673 | 1.4187 |
| EQUITY_SCALED | mean gross over marked equity | 0.6296 | 0.6175 | 0.6302 | 0.6198 |
| EQUITY_SCALED | hit rate | 0.5398 | 0.5398 | 0.5783 | 0.5783 |

## Split description

Odd months are the Arrow 011 discovery split and even months are internal confirmation that has already been viewed many times. These are **not pristine out-of-sample**. The C0-C3 formulas were predeclared in the committed freeze and were not retuned after seeing either split.

| Config | IS marked P&L | OOS marked P&L | ALL marked P&L |
|---|---:|---:|---:|
| C0 | 74,319 | 90,159 | 230,720 |
| C1 | 106,160 | 112,828 | 337,801 |
| C2 | 61,754 | 73,414 | 178,262 |
| C3 | 89,297 | 93,564 | 263,432 |

Each split row is its own account starting at 100,000 with its own equity path, so the two splits do not add to the all-cohort account. The direction is the same in both splits for every challenger.

## Monthly accounts

Published under `cg_lab_monthly_account_reporting_v1` in `reports/cg_arrow012_monthly_account.csv` for every complete account. Rows are cent-chained and reconcile exactly to each book's marked account result at 2026-08-31, never to eventual completed-trade profit.

| Month | C0 | C1 | C2 | C3 |
|---|---:|---:|---:|---:|
| 2025-09 | 3,734.77 | 5,506.19 | 2,489.01 | 4,340.91 |
| 2025-10 | 14,425.68 | 17,117.67 | 11,339.42 | 13,430.35 |
| 2025-11 | 14,965.28 | 15,788.42 | 12,976.82 | 13,650.26 |
| 2025-12 | -14,344.05 | -17,431.43 | -18,333.75 | -20,880.43 |
| 2026-01 | 15,358.80 | 23,205.85 | 12,603.66 | 19,595.49 |
| 2026-02 | -2,753.18 | -5,532.85 | -1,036.66 | -2,762.50 |
| 2026-03 | 22,079.60 | 31,101.18 | 24,187.68 | 32,572.54 |
| 2026-04 | 1,080.46 | 3,822.76 | 2,311.58 | 4,577.74 |
| 2026-05 | 14,740.86 | 24,564.56 | 2,206.38 | 9,926.21 |
| 2026-06 | 79,654.64 | 105,473.97 | 69,965.29 | 91,399.60 |
| 2026-07 | 36,519.69 | 55,214.83 | 28,631.44 | 42,828.23 |
| 2026-08 | 45,257.19 | 78,970.30 | 30,920.93 | 54,753.11 |
| **Total** | **230,719.74** | **337,801.45** | **178,261.80** | **263,431.51** |
| Positive / red / flat months | 10 / 2 / 0 | 10 / 2 / 0 | 10 / 2 / 0 | 10 / 2 / 0 |
| Worst / best / median month | -14,344 / 79,655 / 14,853 | -17,431 / 105,474 / 20,162 | -18,334 / 69,965 / 11,972 | -20,880 / 91,400 / 13,540 |

## Verification

| Check | Result |
|---|---|
| Frozen economic controls reproduce before research | 5 of 5 |
| Arrow 011 artifacts changed | none |
| C0 reproduces Arrow 010 | 4 of 4 |
| Scored cohorts are exactly the frozen 52 | True |
| Cohort base capital T preserved in C1, C2 and C3 | all 52 cohorts, worst deviation below 1e-10 |
| Account identities hold | 20 of 20 |
| Monthly rows chain and reconcile | 12 of 12 books |
| Independent oracle across every challenger ledger | 4980 trades, max error 3.6e-12 |
| Independent allocation and share recomputation | 4992 tickets, 0 disagreements |
| Code drift between freeze and scoring | none |
| Public/private separation and credential hygiene | pass |

Every share count in every challenger book was re-derived from stored inputs by the independent oracle: the frozen base allocation times that book's own recorded equity scale, floored against the stored causal pre-order price. The oracle never consults the challenger engine.

> Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills and availability are modeled, not broker execution guarantees.

---

## Research statuses

**C1 rank-one 1.50x reallocation: CHALLENGER IMPROVES PROFIT BUT DEGRADES RISK/CONCENTRATION — AWAIT HOLDOUT WITH CAUTION.** The complete account improves in both the equity-scaled and fixed-dollar views, with no change to which names are traded. Drawdown as a share of its own peak improves. Against that, the worst single session deepens by more than half, dollar drawdown worsens equity-scaled, and one name per week rises to roughly three quarters of P&L. On one already-inspected year this is an allocation result that has not faced a pristine sample.

**C2 off-high substitution: CHALLENGER DOES NOT IMPROVE COMPLETE HISTORICAL ENGINE.** The replacement names behaved as the anatomy predicted and the complete account still lost, because funding them inside a fixed cohort budget diluted the retained names, above all the protected rank one. The conclusion survives the pre-declared revert sensitivity for the six evidence-affected cohorts.

**C3 combined: CHALLENGER IMPROVES PROFIT BUT DEGRADES RISK/CONCENTRATION — AWAIT HOLDOUT WITH CAUTION.** It beats the incumbent but is dominated by C1 alone, and the interaction is strongly negative because the two changes pull rank-one capital in opposite directions. C3 was built as its own account; inferring it from C1 and C2 would have overstated it.

No result here is a production decision. The incumbent is unchanged and remains the protected control.

NEXT STEP: PRISTINE ADDITIONAL-YEAR REVEAL OF C0/C1/C2/C3 AFTER DATA CERTIFICATION
