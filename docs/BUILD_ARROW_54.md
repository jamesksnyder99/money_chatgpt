# Build Arrow 54 — fade into the Friday fill (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_53.md`, `reports/arrow53_results.txt`,
`reports/arrow52_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
costs, borrow proxy. Reuse `src/research/clock.py`.
Lookback 15. Eight names after filters. $6,000. Friday last-RTH entry
unless an id says Wednesday. Hold 10.

New hallway: the 15-session leftover is the rank. This arrow asks whether
the name must already be giving that leftover back *on the entry day*
before we short it. Sector map is parked. No new ingest. No long leg.
No retune of 43 or frozen B / flush. Do not touch Lab A `data/bars/`
except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Rank (shared)

Residual = name 15-session close-to-close − IWM on the same stamps.
Rank eligible names on residual. Then apply the id's entry filter.
Take the 8 highest-residual names that pass the filter. If fewer than 5
pass, skip that week for that id. If 5–7 pass, take them all — do not
fill with names that failed the filter.

Skip a week if fewer than 16 eligible names have a residual.
Skip a name if a required fill is missing.

## Ids (frozen — do not add a 7th)

| id | entry filter |
|---|---|
| 0 `plain` | none | control. Must reprint Arrow 53 `vs_iwm` IS $/day within ±10% and n within ±10% of 121 |
| 1 `fade1` | last 1 session residual vs IWM < 0 (today's close/prior close − IWM same window) |
| 2 `fade2` | last 2 sessions residual vs IWM < 0 |
| 3 `rth_down` | that Friday RTH close < that Friday 09:30 open |
| 4 `no_repeat` | name was not in this id's prior Friday eight |
| 5 `wed_fade1` | Wednesday rebalance, same fade1 filter as id 1 |

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. IS character for ids 1–3: fraction of the unfiltered top 8 that would
   pass the filter. Description. Does not pick an id.
3. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** two-cohort notional ≤ $100k.
A ring counts as better only if it lifts $/day versus id 0 on **both** IS and OOS.
Print t and CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow54_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak/mean concurrent,
IWM alpha skip=0, months, deployed $, weeks skipped by the filter.

First paragraph: reprint, who beats plain on both slices, who clears
seat / slate, whether fade1 cuts n a lot or a little.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only, Friday, no fade filter (fixture);
- id 1 rejects a name whose last-session residual vs IWM is ≥ 0 (fixture);
- id 3 rejects a name whose Friday close ≥ Friday 09:30 open (fixture);
- id 4 rejects a name that was in the prior Friday eight (fixture);
- id 5 entries are Wednesdays only (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 55.
