# CG Arrow 009 — certified 12-month account results, Winner-Fade Short

Reporting only. Nothing in the certified Arrow 008 substrate was recomputed, reselected or changed. These are the calendar-month account results of the certified Corrected-Universe Replay (`R2`) at the 10-Session Hold (`H10`), legacy fill-quantity panel, read from the daily marked-account path.

Monthly P&L is the change in marked account equity across the month, so a position opened in one month and closed in the next contributes to both, exactly as an account statement would show. Monthly return divides that month's P&L by the prior month-end marked equity; September 2025 starts from the $100,000 study equity.

Published rows are stated in whole cents and chain exactly, as an account statement does. Full precision is retained in `reports/cg_arrow009_manifest.json`, which carries the exact reconciliation to the certified Arrow 008 account result.

## Monthly account P&L, dollars

| Month | Equal-Dollar H10 | R4 H10 | R5 H10 |
|---|---:|---:|---:|
| Sep 2025 | 634.49 | 2,854.39 | 3,732.77 |
| Oct 2025 | 17,869.74 | 16,574.56 | 14,264.73 |
| Nov 2025 | 9,779.45 | 11,413.15 | 12,244.07 |
| Dec 2025 | -4,139.09 | -8,288.75 | -10,792.40 |
| Jan 2026 | 6,273.59 | 6,506.84 | 12,585.96 |
| Feb 2026 | 3,939.91 | 2,456.21 | -988.00 |
| Mar 2026 | 8,619.61 | 12,907.62 | 16,734.26 |
| Apr 2026 | -3,387.93 | -62.62 | 819.81 |
| May 2026 | 3,242.74 | 6,893.46 | 8,782.81 |
| Jun 2026 | 29,883.73 | 31,451.40 | 41,794.94 |
| Jul 2026 | 17,529.25 | 15,155.94 | 14,858.63 |
| Aug 2026 | 16,146.94 | 16,792.99 | 15,165.27 |
| **Total** | **106,392.41** | **114,655.18** | **129,202.83** |

## Monthly return, percent of prior month-end equity

| Month | Equal-Dollar H10 | R4 H10 | R5 H10 |
|---|---:|---:|---:|
| Sep 2025 | 0.63% | 2.85% | 3.73% |
| Oct 2025 | 17.76% | 16.11% | 13.75% |
| Nov 2025 | 8.25% | 9.56% | 10.38% |
| Dec 2025 | -3.23% | -6.33% | -8.29% |
| Jan 2026 | 5.05% | 5.31% | 10.54% |
| Feb 2026 | 3.02% | 1.90% | -0.75% |
| Mar 2026 | 6.42% | 9.81% | 12.77% |
| Apr 2026 | -2.37% | -0.04% | 0.55% |
| May 2026 | 2.32% | 4.78% | 5.91% |
| Jun 2026 | 20.92% | 20.79% | 26.56% |
| Jul 2026 | 10.15% | 8.30% | 7.46% |
| Aug 2026 | 8.49% | 8.49% | 7.09% |

## Month-end marked equity

| Month | Equal-Dollar H10 | R4 H10 | R5 H10 |
|---|---:|---:|---:|
| Sep 2025 | 100,634.49 | 102,854.39 | 103,732.77 |
| Oct 2025 | 118,504.22 | 119,428.94 | 117,997.49 |
| Nov 2025 | 128,283.67 | 130,842.09 | 130,241.56 |
| Dec 2025 | 124,144.59 | 122,553.34 | 119,449.16 |
| Jan 2026 | 130,418.17 | 129,060.19 | 132,035.12 |
| Feb 2026 | 134,358.08 | 131,516.39 | 131,047.12 |
| Mar 2026 | 142,977.69 | 144,424.01 | 147,781.38 |
| Apr 2026 | 139,589.75 | 144,361.39 | 148,601.19 |
| May 2026 | 142,832.49 | 151,254.85 | 157,383.99 |
| Jun 2026 | 172,716.22 | 182,706.25 | 199,178.93 |
| Jul 2026 | 190,245.47 | 197,862.19 | 214,037.56 |
| Aug 2026 | 206,392.41 | 214,655.18 | 229,202.83 |

## Monthly shape

| Measure | Equal-Dollar H10 | R4 H10 | R5 H10 |
|---|---:|---:|---:|
| Positive months | 10 | 10 | 10 |
| Red months | 2 | 2 | 2 |
| Sum of red months | -7,527.02 | -8,351.37 | -11,780.40 |
| Worst month | -4,139.09 | -8,288.75 | -10,792.40 |
| Best month | 29,883.73 | 31,451.40 | 41,794.94 |
| Median month | 7,446.60 | 9,153.30 | 12,415.01 |

## Reconciliation to the certified Arrow 008 account result

The twelve calendar months reconcile to Arrow 008 quantity **B**, the marked account P&L at 2026-08-31. They deliberately do **not** reconcile to quantity **A**, eventual completed-trade P&L, because A includes exits scheduled after August closes; that runoff is reported separately.

| Book | Sum of 12 monthly P&L | Certified Arrow 008 B | Difference | Aug-2026 month-end equity |
|---|---:|---:|---:|---:|
| Equal-Dollar H10 | 106,392.41 | 106,392.41 | 0.00e+00 | 206,392.41 |
| R4 H10 | 114,655.18 | 114,655.18 | 0.00e+00 | 214,655.18 |
| R5 H10 | 129,202.83 | 129,202.83 | 0.00e+00 | 229,202.83 |

Positions still open at the boundary are carried in the August marked equity above at their last observed marks, and their eventual outcomes appear in the Arrow 008 runoff quantities C and D rather than in any month here. One documented open obligation per book remains, under a documented trading suspension.

## Reporting standard

These tables are produced by the frozen lab standard `cg_lab_monthly_account_reporting_v1` in `src/verification/r4r5_monthly.py`. Every future research arrow that publishes strategy economics and has a daily marked-account path must publish the same set: every calendar month individually, principal variants side by side, monthly P&L dollars, monthly return percent on prior month-end equity, month-end equity, positive and red month counts, worst and median month, exact reconciliation to the period's marked account result, and explicit boundary treatment. It is a reporting requirement, never an optimization dimension: monthly outcomes must not be used to select or alter a strategy.

> Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow fees for Trading API users; short availability and other security-specific costs may still vary.

