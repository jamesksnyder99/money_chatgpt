# Build Arrow 30 — rocket altitude rollup (diagnostic, no book)

Read `reports/arrow19_survey.txt`, `reports/arrow29_results.txt`, `docs/SUCCESS.md`.

No fills that change a verdict. No $200 pass line. No B-short rescore. No $500/idea. No virgin pull. No cell-buy. `data/full/` only.

## Definitions (freeze these)

**Rocket-day:** prior_close in [$1, $20], ≥5 prior sessions, **confirmed launch** (1-min close ≥ 1.10× prior_close and next tradeable low ≥ 1.08× prior_close). Also print a side table with the survey's high-based ∩ rel vol ≥3× set so we can compare field size.

**Sea level:** prior close.

**1R haircut:** 1.0 × ATR of the last six completed 5-min bars at launch (if <6, use 0.6% of price). Same floor as the harness.

**Gross altitude** (name-day): `max(0, (max_high / prior_close − 1) − r1)` where `max_high` is the session max high **after launch** (04:00–15:59). If the name never leaves +1R above sea, altitude = 0. Close below sea does **not** subtract — depths are ignored.

**Captured altitude:** for each name-day `flush|max6` actually traded in A25/A26 (reproduce the id, do not invent fills), `max(0, trade_MFE_R)` in **R dollars** ($200 × MFE_R) **and** as a fraction of that name-day's gross altitude in dollars (`gross_alt × prior_close × shares_if_we_had_sat_1R` is messy — report two views):

View 1 — **name-day coverage:** rocket-days traded / rocket-days in the field (develop, holdout, study).
View 2 — **extension points:** sum of gross altitude (in percent points) over the field vs sum of `max(0, MFE_pct from entry)` on flush trades. State both so we do not pretend $ and % are the same.

Also: altitude by launch hour 04..15; share of field altitude in hours we never sit (04–07, after 12:00); FLY vs FAIL if labels are cheap.

## Engine to score

`flush|max6` only (A26 kernel). If reproducing it is expensive, use the saved trade list from arrow25/26 outputs if present; otherwise replay that one id.

## Report

`reports/arrow30_altitude.txt`

- Field n, sum altitude (pct-points), median/p90 altitude
- Flush n, sum captured MFE pct-points, coverage %
- One paragraph: what fraction of the 04:00–16:00 field this specialist harvested
- Develop vs holdout separate; holdout is not EV

Tests: confirmed launch rejects a +12% wick that closes +6%; a name whose max high is +0.4% has altitude 0 if 1R is 0.6%; depths after the high do not reduce altitude.

Commit code + report. No parquet. No Arrow 31.
