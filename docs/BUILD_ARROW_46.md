# Build Arrow 46 — residual-short, second ring set (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_45.md`, `reports/arrow45_results.txt`,
`reports/arrow44_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
last-RTH fills, $2,000, costs, borrow proxy as Arrow 44/45.
Reuse `src/research/clock.py`.

Arrow 45: 4% and 8% residual bars never fired; tighter tail moved OOS
and cost IS dollars; hold 10 was the only id that lifted both slices.
This arrow turns those knobs one more click and adds the untested rank
lookback. It does not add a long leg. It does not retune 43 or the
frozen B / flush books. No new ingest. Do not touch Lab A `data/bars/`
except to read an existing helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction.

## Rank and hold

`lb` = sessions in the residual window (close today ÷ close lb sessions
earlier − 1, minus IWM on the same stamps).
`h` = sessions from entry to exit.
Default lb = 5 unless the id says lb10.

Skip a name if a required close is missing. Skip a week if fewer than
`2 × n_short` eligible names have a residual.
Threshold ids: take only residual ≥ the bar. Do not fill the seat under
the bar. If fewer than 5 names clear the bar that week, skip the week
for that id only.

## Ids (frozen — do not add a 7th)

| id | n | lb | hold | extra |
|---|---|---|---|---|
| 0 `n15_h10` | 15 | 5 | 10 | control. Must reprint Arrow 45 `n15_h10` IS $/day within ±10% and n within ±10% of 262 |
| 1 `n10_h10` | 10 | 5 | 10 | tighter tail + longer hold |
| 2 `n8_h10` | 8 | 5 | 10 | tighter tail + longer hold |
| 3 `n15_lb10_h10` | 15 | 10 | 10 | rank on two weeks, hold two weeks |
| 4 `n15_h10_r15` | 15 | 5 | 10 | residual ≥ 0.15 |
| 5 `n8_h10_r15` | 8 | 5 | 10 | residual ≥ 0.15 and n=8 |

## Order of work

1. Id 0 reprint. If it misses the Arrow 45 `n15_h10` band, stop and fix.
2. IS character for ids that change the population (n10, n8, lb10, r15):
   mean next-hold residual of the names that would be shorted. Description.
3. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
A ring counts as better only if it lifts $/day versus id 0 on **both**
IS and OOS.

## Report

`reports/arrow46_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, PF, se, t, CI,
daily-close DD, worst day, peak/mean concurrent, IWM alpha skip=0, months.
avgR is n/a.

First paragraph: reprint check, ids that beat control on both slices,
seat / no seat.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only;
- even-month entry is not IS;
- r15 never shorts residual < 0.15 (fixture);
- lb10 uses close ten sessions back, not five (fixture);
- h10 exit is ten sessions after entry;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 47.
