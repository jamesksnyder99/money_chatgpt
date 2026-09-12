# Build Arrow 47 — residual-short rings off lb10 (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_46.md`, `reports/arrow46_results.txt`,
`reports/arrow45_results.txt`, `reports/arrow44_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
last-RTH fills, costs, borrow proxy. Reuse `src/research/clock.py`.

Arrow 46 parent: `n15_lb10_h10` IS +$221 / OOS +$123. Seat by the written
rule. OOS t = 1.39, CI crosses 0. This arrow asks what part of that print
is the two-week rank, the ten-session hold, the tail, or the leftover bar.
It does not add a long leg. It does not retune 43 or the frozen B / flush
books. No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction.

## Rank and hold

`lb` = sessions in the residual window. `h` = sessions from entry to exit.
Residual = name close-to-close over lb − IWM over the same stamps.
Skip a name if a required close is missing. Skip a week if fewer than
`2 × n_short` eligible names have a residual.
Threshold ids: residual ≥ the bar; do not fill under the bar. Skip that
id's week if fewer than 5 names clear the bar.
Default notional $2,000 unless an id says $3,000.

## Ids (frozen — do not add a 7th)

| id | n | lb | hold | extra |
|---|---|---|---|---|
| 0 `n15_lb10_h10` | 15 | 10 | 10 | control. Must reprint Arrow 46 IS $/day within ±10% and n within ±10% of 260 |
| 1 `n10_lb10_h10` | 10 | 10 | 10 | tighter tail on the seat rank |
| 2 `n8_lb10_h10` | 8 | 10 | 10 | tighter tail on the seat rank |
| 3 `n15_lb10_h5` | 15 | 10 | 5 | same rank, shorter hold — isolates hold vs rank |
| 4 `n15_lb10_h10_r20` | 15 | 10 | 10 | residual ≥ 0.20 |
| 5 `n15_lb10_h10_3k` | 15 | 10 | 10 | $3,000 notional |

Id 5 is size only. Same names as id 0. If it does not scale near-linear,
say so (costs or missing fills).

## Order of work

1. Id 0 reprint. If it misses the Arrow 46 band, stop and fix.
2. IS character for ids that change the population (n10, n8, r20):
   mean next-hold residual of the names that would be shorted. Description.
3. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
A ring counts as better only if it lifts $/day versus id 0 on **both**
IS and OOS.
Print t and CI on every OOS line. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow47_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, PF, se, t, CI,
daily-close DD, worst day, peak/mean concurrent, IWM alpha skip=0, months.
avgR is n/a.

First paragraph: reprint check, ids that beat control on both slices,
seat / no seat, whether id 3 (hold 5) kept the OOS lift.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only;
- even-month entry is not IS;
- r20 never shorts residual < 0.20 (fixture);
- h5 exit is five sessions after entry, h10 is ten;
- id 5 uses $3000 notional in the share count (fixture);
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 48.
