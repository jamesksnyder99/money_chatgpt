# Build Arrow 53 — group leftover (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_52.md`, `reports/arrow52_results.txt`,
`reports/arrow51_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, costs, borrow proxy.
Reuse `src/research/clock.py`.
Eight names. $6,000. Lookback 15. Friday last-RTH entry. Hold 10.
No industry tape on disk and no new ingest. Groups are built from the
eligibility frame already on disk.

Arrow 52: leftover versus IWM is not a Friday-only object. This hallway
changes the *benchmark*, not the weekday. Control is Friday versus IWM.
No long leg. No retune of 43 or frozen B / flush. No new ingest.
Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Residual

Name return = last RTH close today ÷ last RTH close 15 sessions earlier − 1.
Skip the name if either close is missing.

Benchmark depends on the id. Residual = name return − benchmark.
Short the 8 largest residuals. Skip a Friday if fewer than 16 eligible
names have a residual. Skip a name if entry or exit close is missing.

Price buckets (prior close, point-in-time): [$10, $20), [$20, $40), [$40, $80].
PDV terciles: cut the eligible names that Friday into three equal counts on
prior-day dollar volume. A bucket with fewer than 8 names that Friday is
not used as a peer set for that name — drop the name from that id only.

## Ids (frozen — do not add a 7th)

| id | benchmark |
|---|---|
| 0 `vs_iwm` | IWM 15-session return | control. Must reprint Arrow 52 `fri_h10` IS $/day within ±10% and n within ±10% of 121 |
| 1 `vs_univ` | median 15-session return of all eligible names that Friday |
| 2 `vs_px` | median 15-session return of eligible names in the same price bucket |
| 3 `vs_pdv` | median 15-session return of eligible names in the same PDV tercile |
| 4 `vs_px_iwm` | price-bucket median, then minus IWM (name − bucket median − IWM) |
| 5 `wed_vs_univ` | same as id 1, but Wednesday rebalance instead of Friday |

Ids 0–4 are Friday. Id 5 asks whether the universe-median leftover still
prints on the weekday that won Arrow 52.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** two-cohort notional ≤ $100k.
A ring counts as better only if it lifts $/day versus id 0 on **both** IS and OOS.
Print t and CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow53_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak/mean concurrent,
IWM alpha skip=0, months, deployed $.

First paragraph: reprint, who beats vs_iwm on both slices, who clears
seat / slate, whether vs_univ is a different book than vs_iwm (print
overlap of the eight names on IS Fridays — mean names in common).

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only, Friday, lookback 15, residual subtracts IWM (fixture);
- id 1 residual is name minus eligible median, not IWM (fixture where all
  names +10% and IWM +10% → vs_univ residual 0, vs_iwm residual 0 too;
  use a fixture where names differ and IWM differs);
- id 2 uses the same price bucket (fixture);
- id 5 entries are Wednesdays only (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 54.
