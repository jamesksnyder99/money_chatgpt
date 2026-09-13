# Arrow 003 common repairs and IS reconciliation

IS means in-sample, odd SIGNAL months. PnL means profit and loss; MTM means marked-to-market. All figures are modeled dollars. Historical Arrow 002 evidence is unchanged.

## Legacy reproduction and reconciliation

Original PARENT/R4/R5 were independently reproduced with the inherited `_make_trade` implementation and copied canonical tape. Completed profit and every lifecycle daily value match the frozen local results within 1e-6. No historical OOS gate or marker was changed.

Arrow 001 had already established the historical reproduction. This run repeated the targeted legacy check during the bounded repair phase, before candidate scoring; it was not a second broad archive-reproduction project.

| Control | Legacy IS | Accounting only | Working IS | Accounting delta | Documented-action delta |
|---|---:|---:|---:|---:|---:|
| PARENT | 9969.57 | 10425.92 | 6450.99 | 456.35 | -3974.93 |
| R4 | 16598.29 | 17358.98 | 14078.45 | 760.68 | -3280.53 |
| R5 | 24628.10 | 25654.37 | 21662.04 | 1026.28 | -3992.33 |

These common changes are not strategy alpha. Every new candidate uses the working convention and the same working comparator.

## Accounting convention

REPAIRED: Entry existence is independent of future exit availability. Fixed last regular-hours minute is required for a late entry; no earlier fallback fill. Missing scheduled ten-session exits stay open and reserve marked exposure, then cover at the first available later regular-hours print. Terminal entries are retained at August 31. Carried marks are stale valuations, never executable fills. Half-covers preserve proportional entry costs. Continuous drawdown uses the full 251-session lifecycle chronology.

REPAIRED: Live ticket/symbol counts use actual inventory, gross is distinct from the original $100,000 equity, and all outputs share one soft-exposure classifier. Calendar-month MTM and month-start-equity returns are separate from signal-cohort ownership.

QUANTIFIED/RETAINED: Compatible alternate copied minute partitions are attempted when canonical data are absent. National EOD partitions were inspected for unresolved terminal symbols; their later-session scope and absent adjustment declaration prevent silent substitution. No new data connection, credentials, terminal, or subscription was used.

| Control | Open terminal tickets | Terminal gross | Stale terminal gross | Stale position-sessions | Delayed exit fills |
|---|---:|---:|---:|---:|---:|
| PARENT | 6 | 25367.99 | 25367.99 | 724 | 9 |
| R4 | 6 | 24545.29 | 24545.29 | 724 | 9 |
| R5 | 6 | 24072.92 | 24072.92 | 724 | 9 |

## Partial corporate-action repair

The copied split table has zero rows and is not zero-event evidence. A bounded discontinuity screen flagged candidates for source review; it never inferred a factor. Eight issuer-documented reverse splits were applied across the full inherited eligible ranking rows and selected price/volume features as of each decision. Before an effective trading session, historical comparison prices multiply by old-shares/new-share and share volumes divide by that factor. Held shares divide and entry basis, paid entry-cost basis, marks and frozen price-unit ATR multiply at the event. Raw execution prints remain unchanged.

| Symbol | First adjusted trading session | Price factor | Primary provenance |
|---|---|---:|---|
| LCID | 2025-09-02 | 10 | [Issuer evidence](https://ir.lucidmotors.com/news-releases/news-release-details/lucid-group-inc-announces-effective-date-reverse-stock-split) |
| OXLC | 2025-09-08 | 5 | [Issuer evidence](https://ir.oxfordlanecapital.com/stock/dividends-splits) |
| VOR | 2025-09-19 | 20 | [Issuer evidence](https://www.sec.gov/Archives/edgar/data/1817229/000119312525205553/d945826d8k.htm) |
| GMRE | 2025-09-22 | 5 | [Issuer evidence](https://s21.q4cdn.com/118490706/files/doc_news/Global-Medical-REIT-Inc--Completes-One-for-Five-Reverse-Stock-Split-09-19-2025-2025.pdf) |
| ETHZ | 2025-10-20 | 10 | [Issuer evidence](https://www.prnewswire.com/news-releases/ethzilla-corporation-announces-1-for-10-reverse-stock-split-302584765.html) |
| LXP | 2025-11-11 | 5 | [Issuer evidence](https://www.globenewswire.com/news-release/2025/11/10/3185113/19004/en/LXP-Industrial-Trust-Completes-Reverse-Share-Split.html/) |
| AMCR | 2026-01-15 | 5 | [Issuer evidence](https://www.amcor.com/media/news/amcor-completes-one-for-five-reverse-stock-split) |
| FUBO | 2026-03-24 | 12 | [Issuer evidence](https://www.sec.gov/Archives/edgar/data/1484769/000149315226011823/form8-k.htm) |

PARTIAL, not universe certification: other splits, mergers, symbol transitions, cash-in-lieu, dividends, loan availability, fees and financing remain unresolved. Theoretical fractional short liabilities are retained if a documented reverse split crosses a holding; broker cash-in-lieu is not fabricated. Remaining discontinuities are dependency diagnostics, not ticker exclusions or evidence of splits. New economic claims are conditional on this coverage.

All detailed positions, missing observations and source tape paths remain under ignored `data/tmp/cg_arrow003/`; public manifests carry their hashes. Raw copied data and earlier reports remain unchanged.

Bounded repair audit checkpoint: 2026-09-13T18:06:07+00:00, elapsed 17.43 minutes. Focused accounting/action fixtures passed before the working controls were used for discovery.

## Subsequent in-sample dependency audits

The fixed treatment above was retained during discovery. The copied ingest's price-range eligibility also limits lifecycle coverage: five of six unresolved R4 tickets (four of five distinct names) were last marked above $80. Existing eligibility records explicitly show `prior_close_out_of_range` during many missing periods; later absent eligibility rows are distinguished from known exclusions. All 15 missing scheduled backstops are classified in `cg_arrow003_lifecycle_coverage.json`. Missingness is therefore potentially associated with adverse moves in shorts, rather than random. Neither carried prices nor uniform shocks certify absolute profit.

`cg_arrow003_stale_dependency.json` holds terminal quantities fixed. `cg_arrow003_dynamic_stale.json` additionally recomputes causal capacity and drawdown state under common, non-compounding +10%, +50%, and +100% errors at missing valuation observations. These are hypothetical stresses, not estimated missing prices, new signals, or executable fills. The +50% diagnostic leaves the original R4/R5 IS profits at $1,805.80/$9,625.58; candidate increments are reported against equally stressed controls. Actual stock loans, dividends, cash-in-lieu and unobserved prices remain unresolved.

An independent cash-minus-short-liability reconstruction verified all 62 IS books and their observed executions. Agreement validates accounting and event identity; it cannot repair the input limitations. Windows freeze serialization and interrupted-job guards were also tested before confirmation. Later changes to guards/report fields are engineering verification, not additional action acquisition or hidden economic repairs.

Final pre-freeze verification expanded the cash reconstruction to all 77 IS books. Two exact replays preserved every existing economic metric and execution-ledger value (absolute tolerance $0.0000001); the final replay also verifies the final code and input identities. New explanatory risk fields were allowed, but economic changes were not. The complete test suite passed 517 tests before freeze.

The full lifecycle coverage audit attributes 720 of 724 stale position-sessions to documented acquisition price-range exclusions; the remaining four have other documented exclusions. This is stronger evidence of outcome-related coverage bias than an empty split table alone. Complete absolute economics remain INCONCLUSIVE/DATA-LIMITED.

A targeted universe check found 25 IS Wednesday batches and 30,973 eligible ranking rows, spanning 2,245 unique candidates. Per-batch eligible counts ranged from 907 to 1,342 (median 1,304). Every eligible row and all 200 top-eight selections satisfied the inherited prior-close $10–$80 and prior-dollar-volume $10 million requirements. No arbitrary 50-name cap was imposed. This eligibility check does not certify corporate-action completeness or subsequent held-position coverage.
