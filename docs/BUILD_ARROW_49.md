# Build Arrow 49 — n8 scale toward slate (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_48.md`, `reports/arrow48_results.txt`,
`reports/arrow47_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
last-RTH fills, costs, borrow proxy. Reuse `src/research/clock.py`.
Lookback 10. Short residual winners.

Arrow 48: n15 hold-10 scaled linearly through $5k. OOS $4k = +$247 and
$5k = +$309 both clear slate $200. n8 hold-10 at $3k is a seat (OOS +$154,
April green). Two overlapping 15-name cohorts at $4k–$5k do not fit $100k.
Eight names do. This arrow scales n8. No long leg. No retune of 43 or
frozen B / flush. No new ingest. Do not touch Lab A `data/bars/` except
to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction.

## Ids (frozen — do not add a 7th)

| id | n | hold | notional |
|---|---|---|---|
| 0 `n8_h10_3k` | 8 | 10 | $3,000 | control. Must reprint Arrow 48 `n8_h10_3k` IS $/day within ±10% and n within ±10% of 135 |
| 1 `n8_h10_4k` | 8 | 10 | $4,000 |
| 2 `n8_h10_5k` | 8 | 10 | $5,000 |
| 3 `n8_h10_6k` | 8 | 10 | $6,000 |
| 4 `n8_h5_4k` | 8 | 5 | $4,000 |
| 5 `n8_h5_5k` | 8 | 5 | $5,000 |

Skip a week if fewer than 16 eligible names have a residual.
Skip a name if a required close is missing.

Print scale vs id 0 for ids 1–3 (expected 4/3, 5/3, 2.00 if linear).
Print deployed notional = n × notional and the two-cohort figure (2 × that)
against $100k.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** two-cohort notional ≤ $100k.
A ring counts as better only if it lifts $/day versus id 0 on **both** IS and OOS.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow49_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak/mean concurrent,
IWM alpha skip=0, months, one-cohort $ deployed, two-cohort $ deployed.

First paragraph: reprint, scale ratios, who clears $100, who clears $200
with two-cohort fit, ids that beat control on both slices.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only and $3000 share count (fixture);
- even-month entry is not IS;
- 4k / 5k / 6k share counts match notional (fixture);
- h5 exit is five sessions, h10 is ten;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 50.
