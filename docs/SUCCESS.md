# money_chatgpt economic and evaluation policy

## Current user mandate — September 13, 2026

Starting account equity remains **$100,000**. The commercial ambition remains **$300-$500 net per trading session on average**, including flat and losing sessions. A useful research result may improve profitability, the monthly ride, or both. Do not discard a meaningful tradeoff merely because every metric did not improve.

The historical $200/day portfolio floor and $100/day independent-engine floor remain commercial reference points, not mechanical vetoes on component research. A lower-profit but substantially safer R4/R5 component can merit study. Do not call an under-target portfolio a commercial success. No new independent engine is authorized by CG Arrow 003.

## Soft exposure, not a $100,000 cliff

- Approximately **$130,000 gross marked exposure** is the current planning range, not additional equity or an automatic broker credit line.
- Small temporary excursions, for example $132,000-$135,000, do not trigger an automatic research failure, emergency liquidation, or alarm. $135,000 is an illustration, NOT a replacement hard ceiling.
- Report exact peak, average, percentiles, duration and dollar-days above $130,000, cause of excursions, aggregate symbol exposure, and gross exposure/current marked equity. Distinguish deliberate new allocation from passive price drift.
- Persistent/materially larger exposure requires an explicit tradeoff assessment, not a hidden leverage increase or an automatic data-gate stop. Preserve the result as higher-exposure research when appropriate rather than quietly rescaling after OOS.
- A candidate does not become better merely by increasing position sizes. Compare with fixed-size and IS-calibrated exposure-matched controls. Do not normalize using realized OOS peaks.
- An optional predeclared new-order pacing rule may aim near $130,000. Subsequent price drift need not force liquidation. Such a policy must be replayed causally and reported as a strategy choice, not an assumed fill.
- Research acceptance and deployment readiness are separate. Borrow availability, fees, dividends, corporate actions, tradable fills, broker margin requirements and current equity remain relevant even below the planning range. Do not label a book deployment-ready from gross exposure alone.

This replaces the prior $100,000/$102,922 hard-cap promotion rules for NEW lab work. It does not retroactively change Arrow 002R's recorded pass/fail results or prove that those books now satisfy every investment objective.

## Monthly ride and profitability

Report all of the following rather than one opaque score: profit per session, total profit, red-month count and loss sum, worst and median month, continuous marked-to-market drawdown, time underwater, worst day, concentration in the best months, and average/peak exposure. Show amounts and percent changes from the relevant R4/R5 control and the original parent.

Retain a transparent frontier: balanced improvements, smoother variants retaining useful profit, and higher-return variants with openly stated extra risk. Report regressions as prominently as gains. Do not count multiple correlated risk metrics as independent statistical confirmations.

Preserve the inherited transaction-cost baseline for reconciliation. Show at least 0%, 10%, and 30% annualized stock-borrow sensitivities as scenarios, not factual historical borrowing costs. Add execution-cost stress as directed. Missing loan/dividend data must remain disclosed.

## IS/OOS convention

For the current twelve-month signal calendar, September 2025 through August 2026:

- **IS / training:** September and November 2025; January, March, May, July 2026.
- **OOS / internal confirmation:** October and December 2025; February, April, June, August 2026.

Membership follows the original signal date, not the eventual exit. As-of feature history and the lifecycle/management of an existing trade may cross a month boundary. Do not purge or force-close positions merely to create artificial purity. Maintain a reasonably clean workflow: develop new candidates on IS, freeze rules/code/selection, then expose the new OOS results once. No adaptive tuning after that reveal in the same arrow.

These months have already been inspected in prior work. They are reused INTERNAL confirmation, not pristine external validation. Cross-month overlap is acknowledged; a formal embargo is not required for this exploratory program. A fresh arrow does not refresh the independence of the same data.

Report both signal-cohort outcomes and post-freeze calendar-month account equity. Do not call the first an actual monthly account return. Under a joint capital policy, rerun the combined account chronologically after freeze rather than add isolated cohort books.

Reasonable IS/OOS agreement means the economic direction and tradeoff broadly repeat relative to the SAME comparator, not that dollar profits must match despite different market conditions. Show the disparity; do not tune to the confirmation gap.

## Input and isolation context

The lab's copied data are under repository-relative `data/virgin`, `data/full`, `data/ref`, `data/meta`, and `data/calendar`. Arrow 001 records their coverage and baseline provenance. The original Money repository is not a runtime dependency and is out of bounds. Preserve raw copied inputs; store derived repairs/caches separately with provenance. Consult the active CG arrow for bounded acquisition and unresolved-data handling.
