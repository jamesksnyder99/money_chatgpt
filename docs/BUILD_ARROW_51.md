# Build Arrow 51 — rank 15 parent and giveback path (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_50.md`, `reports/arrow50_results.txt`,
`reports/arrow49_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
costs, borrow proxy. Reuse `src/research/clock.py`.
Eight names. $6,000. Friday last-RTH entry unless an id says otherwise.

Arrow 50: `lb15_fri_h10` was the only id that lifted both slices versus
Friday-hold-10. OOS CI left zero. `fri_give5` printed the hottest even
months and did not lift odd months. This arrow takes rank 15 as parent
and puts the hold-path knobs on that rank. No long leg. No Monday id.
No IWM 8% skip. No retune of 43 or frozen B / flush. No new ingest.
Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Rank (shared unless an id changes lookback)

Residual = name close-to-close over the lookback minus IWM on the same
stamps. Short the 8 winners. Skip a week if fewer than 16 eligible names
have a residual. Skip a name if a required fill is missing.

## Ids (frozen — do not add a 7th)

| id | lookback | exit |
|---|---|---|
| 0 `lb15_h10` | 15 | last RTH 10 sessions later | control. Must reprint Arrow 50 `lb15_fri_h10` IS $/day within ±10% and n within ±10% of 129 |
| 1 `lb15_give5` | 15 | session +5 if short is ahead (exit px < entry px); else session +10 |
| 2 `lb15_h5` | 15 | last RTH 5 sessions later |
| 3 `lb20_h10` | 20 | last RTH 10 sessions later |
| 4 `lb12_h10` | 12 | last RTH 10 sessions later |
| 5 `lb15_h15` | 15 | last RTH 15 sessions later |

Notional $6,000 on every id. Entry = last RTH close of the rebalance session.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Score all six on IS and OOS. One OOS look.
For id 1 print the fraction of names that exited at +5 vs +10 on both slices.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** two-cohort notional ≤ $100k.
A ring counts as better only if it lifts $/day versus id 0 on **both** IS and OOS.
Print t and CI on every line. Say when a CI excludes 0. Do not call a CI
that includes 0 "EV."

## Report

`reports/arrow51_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak/mean concurrent,
IWM alpha skip=0, months, one-cohort $, two-cohort $.

First paragraph: reprint, who beats control on both slices, who clears
seat / slate, whether give5 on rank 15 lifted both slices, whether any
OOS CI excludes 0.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only, $6000, lookback 15, entry last RTH (fixture);
- id 1 exits at +5 when exit_px < entry_px and at +10 otherwise (fixture);
- id 3 uses close 20 sessions back (fixture);
- id 5 exit is 15 sessions after entry (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 52.
