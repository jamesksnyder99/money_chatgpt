# Build Arrow 27 — repairs, combined scoreboard, SSR as a fill

Read `docs/SUCCESS.md`, `reports/arrow18_results.txt`, `reports/arrow26_results.txt`, `src/research/book.py`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner.

This arrow is **repairs + measurement + one B-short model change**. No rocket rings. No $500/idea. No virgin pull.

Honesty: you may **not** write that the account is "$200 minus one improvement." Combined **develop** of B-short SSR-on (~+$59) plus flush|max6 (~+$11) is ~+$70. Combined holdout is two contaminated/cluster prints added together until `combine_books` exists. Print the sum; do not promote it as EV.

## Repairs (must ship)

**R1 SSR flag:** `ssr_active(symbol, ts)` = session low at or before ts ≤ 0.90 × prior_close **OR** prior session low ≤ 0.90 × that session's prior close. Do not change reject-vs-fill in R1 itself — research rows below choose the policy.

**R2 Grid builder:** if `flatten_at` ≤ earliest entry clock for that door, mark STRUCTURAL and exclude from both-green. No silent n=0 "tests."

**R3 Log only:** RESEARCH_LOG: launch-catch was under-sampled in A24 (cell vs launch gates almost disjoint), not refuted. Not rerun here.

**R4 Flatten fallback:** untradeable flatten bar → exit at last tradeable bar's **close**, not open.

**R5 Stats:** every id prints `peak_conc` and `mean_conc`. Do not spend ids on cap3 vs cap8 unless peak_conc > 3.

**R6:** skip β-IWM this arrow. Note in the report header.

Rescore after repairs, leak-fix close only:
- B `c5_ema9|cap8` **reject** SSR (A18 policy) and **no-filter**
- `flush|max6` on data/full (must reprint A26 within noise)

## Combined scoreboard

`combine_books(daily_series...)`: session union, missing engine = $0 that day. Print $/day, std, se, t, CI, maxDD, peak concurrent risk if available, pairwise corr. Tests: uncorrelated synthetics → combined std ≈ hypot; missing day is 0 not drop.

Every results file from this arrow on ends with:
`COMBINED` develop + holdout for (B-short best row this file, flush|max6).

## SSR policy rows (B-short only, Lab A tape)

Kernel unchanged except fill policy. Borrow proxy stays on.

| id | policy |
|---|---|
| B_reject | A18: skip if ssr_active at signal (new flag) |
| B_nofilter | ignore SSR |
| B_uptick10 | if ssr_active, fill first tradeable open within **10 min** that is > prior bar close; else ssr_nofill |
| B_uptick5 | same, **5 min** window |
| B_uptick10_cap | uptick10 plus fill open ≤ signal close + 0.5% |

Report n, $/day, avgR, IWM alpha if cheap, ssr_share, ssr_nofill, peak_conc.

## Outputs

`reports/arrow27_results.txt` — repair confirmation, B rows, flush reprint, COMBINED, honesty line.
Append RESEARCH_LOG.md (include R3 sentence).
Tests as above plus R1 fixtures.

Commit code + reports. No parquet. No Arrow 28.
