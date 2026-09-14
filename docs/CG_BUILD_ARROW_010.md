# CG Build Arrow 010 — R5 Equity-Sizing Study

## Mission

Study **equity-responsive sizing only** on the certified Winner-Fade Short substrate.

This arrow uses only the **Momentum+Volume-Sized Short (`R5`)**, Corrected-Universe Replay (`R2`), 10-Session Hold (`H10`). Do not carry Equal-Dollar or R4 through the experiment.

The purpose is to isolate one question:

> What happens to account economics when the already-defined R5 ticket sizes scale causally with account equity instead of remaining fixed in dollars?

This is **not** a strategy-selection, holding-period, redeployment, entry-timing, signal, universe, or filter study.

Work only in:

`C:\Users\james\money_chatgpt`

Do not touch the pristine Money repository.

---

## Certified substrate — frozen

Start from the certified Arrow 008 / Arrow 009 substrate and preserve it.

Frozen:

- strategy family: Winner-Fade Short;
- variant: Momentum+Volume-Sized Short (`R5`) only;
- reconstruction: Corrected-Universe Replay (`R2`);
- hold: 10 sessions (`H10`);
- weekly cohort schedule;
- complete candidate field and top-8 selections;
- all security identities and corporate-action factors/dates;
- entry sessions and entry observations;
- exit sessions and exit observations;
- R5 momentum and volume multipliers;
- no substitutions for unavailable names;
- no OOS-driven rule changes;
- commission/spread model and the standing headline-cost footnote;
- Arrow 009 monthly-account reporting standard `cg_lab_monthly_account_reporting_v1`.

The certified R5 controls that must reproduce before experimentation are:

- legacy-fill H10 eventual completed-trade P&L: **129,092.60**;
- legacy-fill marked account P&L at 2026-08-31: **129,202.83**;
- legacy-fill Aug-31 marked equity: **229,202.83**;
- causal-preorder H10 eventual completed-trade P&L: **128,864.62**.

If these controls do not reproduce, stop and report the exact blocker. Do not proceed to sizing research.

---

# Experimental design

## Why R5 only

R5 is the certified model we currently care about most. This arrow is not asking which model is best; it is asking how one frozen model behaves when sizing responds to equity. Carrying the other sizing families would add correlated cells without answering the causal question.

## Main experimental panel: causal sizing

Use the **causal pre-order quantity convention** for the equity-responsive experiment.

Reason: an equity-responsive order must be knowable before the fill. Do not size shares from the eventual fill price or from any post-order information.

The fixed-dollar causal-preorder R5 book is the experiment's control and must reproduce the certified **128,864.62** eventual H10 completed-trade P&L.

### Equity reference

For every weekly cohort, define one common, causal equity snapshot:

**`equity_reference = marked account equity at the close of the signal session`**

That is the last fully completed account close before the next-session entry. It is known before any order in the new cohort is placed and is the same reference for all eight tickets in that cohort.

Do not use entry-day closing equity, fill-time equity, eventual P&L, future marks, or any information unavailable as of the signal-session close.

### R5 fixed-dollar control

Preserve the certified R5 intended-ticket tiers:

- FULL = **$8,300**
- HALF = **$4,150**
- QUARTER = **$2,075**

The existing R5 momentum and volume rules determine the tier exactly as before.

### Equity-scaled R5

Scale the same tier dollar amount by the causal equity reference relative to starting equity:

`scale_factor = equity_reference / 100000`

`equity_scaled_ticket_notional = fixed_R5_tier_notional * scale_factor`

Therefore at exactly $100,000 equity the equity-scaled strategy is identical in intended dollars to fixed R5:

- FULL = 8.30% of reference equity
- HALF = 4.15%
- QUARTER = 2.075%

Convert intended dollars to shares using the same causal pre-order price convention as the fixed-dollar causal control, with the same integer-share rule.

There is **no discretionary leverage multiplier, no drawdown throttle, no gross cap, no volatility target, no Kelly rule, no cohort filter and no redeployment rule in Arrow 010**.

This is deliberately one clean experiment: fixed dollars versus equivalent percentage-of-equity sizing.

---

# Required accounting

Build two causal-preorder R5 account books:

1. `R5_FIXED_DOLLAR_CONTROL`
2. `R5_EQUITY_SCALED`

For each, report both:

- eventual completed-trade economics for all signal cohorts; and
- calendar marked-account economics through 2026-08-31.

Keep Arrow 008 runoff semantics intact. Do not mix eventual post-cutoff outcomes into cutoff account-return denominators.

## Required headline metrics

For both books report at minimum:

- starting equity;
- ending marked equity at 2026-08-31;
- marked account P&L through 2026-08-31;
- eventual completed-trade P&L;
- return on starting equity;
- hit rate;
- average winner;
- average loser;
- profit factor;
- max drawdown dollars;
- max drawdown percent;
- worst day;
- worst month;
- median month;
- positive months / red months;
- sum of red months;
- mean gross exposure dollars;
- peak gross exposure dollars;
- mean gross / marked-equity ratio;
- 95th-percentile gross / marked-equity ratio;
- peak gross / marked-equity ratio;
- turnover / entry notional;
- exposure-dollar-days;
- time underwater;
- runoff-trade count and post-cutoff incremental runoff P&L;
- open documented obligations;
- stale gross at the calendar boundary.

Do not headline hypothetical 10%/30% borrow deductions.

Use the standing footnote:

> Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow fees for Trading API users; short availability and other security-specific costs may still vary.

---

# Standard monthly reporting — mandatory

Apply the frozen Arrow 009 standard `cg_lab_monthly_account_reporting_v1` to both books.

Publish every calendar month Sep 2025 through Aug 2026 with:

- monthly marked-account P&L dollars;
- monthly return % on prior month-end marked equity;
- month-end marked equity;
- both sizing modes side by side;
- positive/red-month counts;
- worst, best and median month;
- exact cent-level chaining;
- exact reconciliation to the 2026-08-31 marked-account result;
- explicit boundary/runoff treatment.

Monthly results are descriptive. **Do not use them to alter the sizing rule.**

---

# Compounding-mechanism diagnostics

The most important output is not merely whether equity scaling earns more dollars. Explain **where the difference comes from**.

For all 52 cohorts publish the causal sizing path:

- signal date;
- split ownership (IS/OOS, for description only);
- signal-session reference equity;
- scale factor versus $100,000;
- fixed-dollar intended cohort notional;
- equity-scaled intended cohort notional;
- fixed-dollar realized cohort P&L;
- equity-scaled realized cohort P&L;
- incremental P&L from equity scaling;
- pre-entry marked gross exposure if available;
- post-entry marked gross exposure;
- gross/equity ratio.

Summarize:

- min / median / max scale factor;
- first cohort whose scale exceeds 1.10x, 1.25x, 1.50x and 2.00x, if any;
- fraction of total equity-scaling uplift contributed by each calendar month;
- fraction contributed by the top 1 / 3 / 5 cohorts;
- fraction of uplift from winning trades versus additional loss from losing trades;
- incremental P&L by R5 tier (FULL / HALF / QUARTER);
- incremental drawdown caused or avoided by equity scaling;
- whether gross/equity remains approximately stable as dollar exposure grows.

Because the strongest fixed-dollar month occurs late in the sample, explicitly state how much of any compounding uplift comes from **June–August 2026**. Do not mistake favorable sequence for a universal property of the sizing rule.

---

# Split reporting and interpretation

Report IS, OOS and ALL for both books, but use careful labels.

The historical OOS months have already been repeatedly inspected in earlier research. Therefore:

- do not call this a pristine confirmation;
- do not choose or tune the sizing formula from OOS outcomes;
- do not change the formula after seeing the results;
- treat split comparisons as robustness/descriptive evidence only.

The formula in this arrow is frozen before scoring.

---

# Invariants / audit requirements

At minimum test:

1. R5 selections, symbols, cohort membership, entry dates and exit dates are identical between fixed-dollar and equity-scaled books.
2. R5 FULL/HALF/QUARTER tier assignment is identical between the two books.
3. The fixed-dollar causal-preorder control reproduces certified Arrow 008 R5 H10 causal-preorder totals exactly.
4. When reference equity equals $100,000, intended ticket notionals equal 8,300 / 4,150 / 2,075 exactly.
5. Every cohort's scale factor uses only signal-session marked equity and never future information.
6. Integer shares are derived only from causal pre-order price and intended notional.
7. Per-trade price return before sizing is identical between fixed-dollar and equity-scaled books.
8. No trade is added, removed, substituted or re-ranked because of sizing.
9. Calendar marked equity reconciles cash minus short liability every day.
10. Monthly rows chain exactly and reconcile to cutoff marked equity.
11. Eventual completed-trade P&L remains separate from cutoff marked-account P&L and runoff.
12. Public/private separation remains intact.

Run the existing independent oracle or extend it so every equity-scaled trade, cohort subtotal and daily account row is independently recomputed from stored inputs rather than trusting the new sizing engine's totals.

---

# What Arrow 010 must NOT do

Do not test or introduce:

- H8/H9 or any hold other than H10;
- capital redeployment after earlier exits;
- 15:00 / 15:30 / 15:45 / 15:59 entry timing;
- gross-exposure caps or leverage sweeps;
- volatility targeting;
- drawdown throttles;
- Kelly sizing;
- new R5 filters;
- ranking-window changes;
- signal anatomy;
- regime filters;
- winner/loser forensic rules;
- broker selection or borrow optimization;
- long-side research.

Those are separate arrows.

---

# Required outputs

Public-safe:

- `reports/cg_arrow010_equity_sizing.md`
- `reports/cg_arrow010_equity_summary.csv`
- `reports/cg_arrow010_monthly_account.csv`
- `reports/cg_arrow010_cohort_scaling.csv`
- `reports/cg_arrow010_manifest.json`
- `reports/cg_arrow010_commands.txt`
- any necessary code/tests

Private, git-ignored, individual/unzipped as needed:

- `handoff/outgoing/cg_arrow010/equity_scaled_trade_audit.csv`
- `handoff/outgoing/cg_arrow010/equity_scaled_daily_account.csv`
- `handoff/outgoing/cg_arrow010/equity_scaled_cohort_audit.csv`
- any additional row-level audit artifact needed for independent verification.

Do not commit private trade rows, vendor data or credentials.

---

# Decision language

Do not declare equity scaling "better" merely because ending dollars are higher.

The report should distinguish:

- **mechanically expected:** larger account equity creates larger later ticket sizes;
- **observed economics:** changes in P&L, drawdown, monthly path and exposure;
- **sequence dependence:** how much improvement/deterioration came from favorable or unfavorable late-period returns;
- **risk efficiency:** return versus drawdown and gross/equity behavior;
- **unresolved:** anything that requires redeployment, leverage caps, new hold lengths or new data.

Conclude with one of these research statuses:

- `EQUITY SCALING IS ECONOMICALLY ATTRACTIVE FOR FURTHER STUDY`
- `EQUITY SCALING ADDS RETURN BUT NOT RISK EFFICIENCY`
- `EQUITY SCALING IS ECONOMICALLY NEUTRAL`
- `EQUITY SCALING DEGRADES THE ACCOUNT PATH`
- `RESULT INCONCLUSIVE — exact reason`

This status is a research interpretation, not a production deployment decision.

---

# Runtime and execution discipline

This should be a focused account-replay study, not an open-ended search.

Predicted wall-clock budget: **30–60 minutes**.

Use existing certified data and account infrastructure. Parallelize independent audit/report generation where useful, but keep the causal equity path serial because each cohort's sizing depends on prior marked equity.

If a finite accounting defect is discovered, repair and report it. Do not drift into new strategy research.

Commit and push all public-safe Arrow 010 code/reports to `main` when complete.

Final report should end with:

`NEXT RECOMMENDED STEP: CAPITAL REDEPLOYMENT STUDY`
