# Build Arrow 58 — short the loser slot (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_57.md`, `reports/arrow57_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Same hotel. Same field. Short only. The loser jersey — eight smallest
close-to-close names on session T — is the rank. Arrow 57 longed that
jersey and lost. Character: next session mean −86 bp. This arrow shorts
it. Holds 1, 5, and 10.

Do not retune the Friday+Wednesday leftover pair or frozen B / flush.
No long id. No IWM subtract (Arrow 57 showed it is a scalar on one day).
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.
Reuse `src/research/clock.py` and the book cost / borrow path.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Rank

On session T, name return = T last-RTH close ÷ prior session last-RTH close − 1.
Loser slot = 8 smallest returns unless the id says 15.
Enter short at T last-RTH close. Exit at the id's hold last-RTH close.
Skip T if fewer than 2 × n eligible names have a T return.
Skip a name if a required close is missing.

## Ids (frozen — do not add a 7th)

| id | n | hold | ticket |
|---|---|---|---|
| 0 `lose_h1` | 8 | 1 | $3,000 |
| 1 `lose_h5` | 8 | 5 | $3,000 |
| 2 `lose_h10` | 8 | 10 | $3,000 |
| 3 `lose_h10_6k` | 8 | 10 | $6,000 |
| 4 `lose_h10_n15` | 15 | 10 | $3,000 |
| 5 `lose_h5_6k` | 8 | 5 | $6,000 |

No reprint control from Arrow 57 — those ids were the other side.
Print peak live notional. Hold 10 with daily entry is many overlapping
cohorts; say whether it fits $100k.

## Order of work

1. IS character: next-session raw return of the loser eight (mean, hit).
   Must be in the same neighborhood as Arrow 57 loser-slot −0.00861 / 0.441.
   If it is not, stop and fix the rank. Description. Does not pick an id.
2. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** peak live notional ≤ $100k.
A ring counts as better only if it lifts $/day versus id 0 on **both** IS and OOS.
Print t and CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow58_results.txt`.

For each id × IS × OOS: $/day, n, n/sess, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak live notional,
IWM alpha skip=0, months.
First paragraph: character reprint vs Arrow 57, who is a seat, who is
slate and fits, whether hold 10 paid on both slices.

Append RESEARCH_LOG.md.

Tests:
- all ids short-only (fixture);
- loser slot is the 8 smallest T returns not the largest (fixture);
- h1 / h5 / h10 exit at 1 / 5 / 10 sessions (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 59.
