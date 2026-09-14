# CG Build Arrow 009 — Certified Monthly Account Reporting Export

## Mission

This is a **small reporting-only arrow** on top of the now-certified Arrow 008 Winner-Fade Short substrate.

Do not change any strategy rule, universe rule, ranking, selection, sizing, entry, hold, IS/OOS ownership, price, quantity, event treatment, or accounting convention.

Work only in:

`C:\Users\james\money_chatgpt`

Do not touch the pristine Money repository.

## First: one clerical repair

In `reports/cg_arrow008_verification.md`, correct the prose test count from `628 passed, 1 skipped` to the authoritative `629 passed, 1 skipped`, matching `reports/cg_arrow008_manifest.json` and `reports/cg_arrow008_commands.txt`.

No other Arrow 008 result may change.

## Primary output — 12-month R2 / H10 account table

Using the **certified Corrected-Universe Replay (`R2`) 10-Session Hold (`H10`) legacy-fill account books**, export calendar-month account results for:

1. Equal-Dollar Short (`PARENT`)
2. Volume-Sized Short (`R4`)
3. Momentum+Volume-Sized Short (`R5`)

Months must be exactly:

- 2025-09
- 2025-10
- 2025-11
- 2025-12
- 2026-01
- 2026-02
- 2026-03
- 2026-04
- 2026-05
- 2026-06
- 2026-07
- 2026-08

For each strategy/month publish:

- monthly marked-account P&L dollars;
- monthly return percent, defined as monthly marked-account P&L divided by prior month-end marked equity;
- month-end marked equity.

For September 2025, prior month-end equity is the study starting equity of `$100,000`.

The monthly accounting must come from the **daily marked account path**, not by grouping completed trades by exit month.

### Required reconciliation

For each of the three H10 books:

`sum(monthly marked-account P&L Sep-2025 through Aug-2026) = Arrow 008 B — marked account P&L at 2026-08-31`

Expected certified Arrow 008 B values, which must be verified rather than hard-coded as output:

- Equal-Dollar H10: `$106,392.40630450024`
- R4 H10: `$114,655.1791` approximately; use the exact value from the certified account artifact
- R5 H10: `$129,202.83` approximately; use the exact value from the certified account artifact

Also verify each month-end equity chains exactly from the prior month-end equity plus that month’s P&L.

Do **not** reconcile the twelve calendar months to eventual completed-trade P&L A, because A contains post-August scheduled exits. The 12-month calendar table ends at the August 31 marked account state B.

## Human-readable table

Publish one concise side-by-side table with the three strategy columns requested by the research director:

| Month | Equal-Dollar H10 | R4 H10 | R5 H10 |
|---|---:|---:|---:|
| Sep 2025 | ... | ... | ... |
| ... | ... | ... | ... |
| Aug 2026 | ... | ... | ... |

The primary human-readable table should show **monthly P&L dollars**.

Immediately below it, publish the same 12 rows as **monthly return %**.

A machine-readable CSV should additionally contain month-end equity.

## Freeze this as a standard research reporting requirement

Add a small reusable reporting helper and/or documented standard so that **future research arrows that publish strategy economics automatically include calendar-month account reporting** when an account path exists.

The standard set is:

- every calendar month individually;
- side-by-side principal strategy/variant results;
- monthly marked-account P&L `$`;
- monthly return `%`;
- month-end marked equity;
- positive/red-month count;
- worst month;
- median month;
- exact reconciliation to the relevant calendar-period marked account result;
- explicit boundary/runoff treatment when positions remain open at the period end.

This is a reporting standard, **not a new optimization dimension**. Monthly outcomes must never be used in this arrow to alter the strategy.

## Required outputs

Public-safe:

- `reports/cg_arrow009_monthly_account.csv`
- `reports/cg_arrow009_monthly_report.md`
- `reports/cg_arrow009_manifest.json`
- any small reusable reporting helper/tests needed to make the monthly standard persistent

The CSV should be tidy/long-form with at least:

- `month`
- `strategy`
- `legacy_id`
- `replay`
- `horizon`
- `monthly_pnl`
- `monthly_return_pct`
- `month_end_equity`
- `prior_month_end_equity`

No private trade rows, vendor data, credentials, or private daily ledgers may be committed.

## Tests / invariants

At minimum assert:

1. exactly 12 months per strategy;
2. exactly the three certified R2/H10 legacy-fill books;
3. monthly P&L sums to Arrow 008 marked-account P&L B for each book within floating-point tolerance;
4. month-end equity chains exactly from prior month-end equity plus monthly P&L;
5. September starts from `$100,000`;
6. August month-end equity equals `$100,000 + B`;
7. monthly return denominator is prior month-end marked equity;
8. no strategy or trade-level certified hash changes;
9. Arrow 008 membership and entry-ledger hashes remain unchanged;
10. public/private separation remains intact.

## Scope / runtime

This should be a **very short accounting/reporting pass**, not research.

No optimization. No new backtest. No broker work. No parameter testing. No signal anatomy. No equity sizing yet.

Use the already-certified Arrow 008 account ledger and daily marked-account paths.

Commit and push all public-safe outputs to `main` when complete.

Final response should state whether all monthly/accounting invariants pass and give the commit SHA.
