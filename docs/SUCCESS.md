# money_chatgpt economic and evaluation policy

## Current user mandate — September 13, 2026

Starting account equity remains **$100,000**. The commercial ambition remains **$300-$500 net per trading session on average**, including flat and losing sessions. A useful research result may improve profitability, the monthly ride, or both. Do not discard a meaningful tradeoff merely because every metric did not improve.

The historical $200/day portfolio floor and $100/day independent-engine floor remain commercial reference points, not mechanical vetoes on component research. A lower-profit but substantially safer component can merit study. Do not call an under-target portfolio a commercial success.

**Current scope is CG Arrow 004:** R4/R5 are the paired short baselines, with capital-utilization and two-week Thursday rotation experiments, plus an explicitly authorized separate long-only loser/recovery engine. Earlier Arrow 003 restrictions on all new engines applied to that run only. Unrelated day/swing corridors remain parked. Each test starts from a standalone hypothetical $100k account; their equity cannot be added and represented as one funded portfolio.

## Soft exposure, not a $100,000 cliff

- Approximately **$130,000 gross marked exposure** is the planning range, not additional equity or an automatic broker credit line.
- Small temporary excursions, for example $132,000-$135,000, do not trigger an automatic research failure, emergency liquidation, or alarm. $135,000 is an illustration, NOT a replacement hard ceiling.
- Report peak, average, percentiles, duration and dollar-days above $130,000, cause of excursions, aggregate symbol exposure, and gross/current marked equity. Distinguish deliberate allocation from passive price drift.
- Persistent/materially larger exposure requires an explicit tradeoff assessment, not a hidden leverage increase or an automatic data-gate stop. Preserve the result as higher-exposure research when appropriate rather than quietly rescaling after OOS.
- More profit from larger positions alone is not better selection. Include fixed-size and IS-calibrated exposure-matched controls. Never normalize using realized OOS peaks.
- New-order pacing is causal: pending/unfilled exits do not free headroom; simultaneous proposals do not each get the full remaining budget. Later price drift need not force liquidation.
- Research acceptance and deployment readiness are separate. Borrow availability, fees, dividends, corporate actions, tradable fills, financing and current equity remain relevant. Gross notional alone is not margin certification.

## Cohort capital and cash — Arrow 004

Every new cohort is intended to exit two nominal Thursdays after entry; exits at 15:00 precede replacements at 15:59 under the active arrow's holiday convention. Weekly entries normally leave two overlapping cohorts: roughly half the chosen account gross target per new cohort, NOT the whole account every week. A biweekly full reset allocates on only one alternate-Thursday phase. Test both fixed phases rather than choose the lucky one retrospectively.

Equity = cash + long market value - short market value. Sale proceeds from opening shorts increase cash and a liability; they do not create additional equity. Covering shorts uses cash while removing that liability. Use marked equity and actual outstanding obligations to determine deployable research headroom, not the cash-balance number alone.

Arrow 004 defines the exact utilization and carry-forward formulas. A carry-forward policy redeploys actual remaining headroom; it does not accumulate fictitious unused-budget credits. Its equity-linked sizing must be distinguished from prior fixed tickets. Idle cash return is **0% in this run**. Do not conflate gross-target headroom, broker buying power and interest-eligible balances.

## Monthly ride and profitability

Report profit/session, total profit, red-month count/loss sum, worst/median month, continuous marked-to-market drawdown, time underwater, worst day, best-month concentration and average/peak exposure. Show differences from the relevant R4/R5 control, and from the long parent/benchmark for separate long policies.

Maintain a transparent frontier: balanced improvements, smoother variants retaining useful profit, and higher-return variants with openly stated extra risk. Report regressions as prominently as gains. Correlated downside metrics are not independent confirmations. Capital utilization is a diagnostic and possible route to better economics, not an objective that overrides net return and risk.

Preserve inherited transaction costs for reconciliation. Freeze cost scenarios before OOS: short-borrow sensitivities at 0/10/30% annualized marked short value; long margin-debit sensitivities at 0/5/10% on actual negative cash, where applicable; and doubled spread with unchanged commissions. These are hypothetical scenarios, not current quoted rates. Do not charge short borrowing on longs or assume leveraged long funding is free. Known dividends must be treated by side; incomplete action/loan/financing history stays disclosed.

## IS/OOS convention

For September 2025 through August 2026:

- **IS / training:** September and November 2025; January, March, May, July 2026.
- **OOS / internal confirmation:** October and December 2025; February, April, June, August 2026.

Membership follows the original signal date, not eventual exit. Causal lookbacks and existing positions may cross month boundaries. Do not purge or force-close positions to create artificial purity. Develop new candidates on IS, freeze rules/code/selection, then expose the new OOS batch once; no adaptive tuning afterward in the same arrow.

These months have already been inspected. They are reused INTERNAL confirmation, not pristine validation. New arrows do not refresh independence. Global alternate-week schedule phases stay fixed across the split; missing opposite-split cohorts are not topped up to a full account during training. Joint capital policies require a combined chronological replay after freeze rather than addition of isolated cohort books.

Reasonable agreement means the economic direction/tradeoff broadly repeats against the SAME comparator, not identical dollar profits despite different conditions. Show disparity and benchmark-relative long performance. Do not fit the new policy to the already-known confirmation gap.

## Input and isolation context

The lab's copied data are under repository-relative `data/virgin`, `data/full`, `data/ref`, `data/meta`, and `data/calendar`. The original Money repository is not a runtime dependency and is out of bounds. Preserve raw inputs; store derived repairs/caches separately with provenance.

Arrow 003 established substantial lifecycle gaps related to entry-universe acquisition limits. Short/reserve and long histories both require coverage beyond those limits while held. Carried marks and delayed local observations are not market fills, actual halts or reliable current valuations. Retain valid entries and terminal inventory, report uncertainty, and do not certify an edge from accounting consistency alone. Bounded acquisition authority and the common convention are specified by the active arrow.
