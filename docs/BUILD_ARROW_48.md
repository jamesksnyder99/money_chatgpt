# Build Arrow 48 — scale and n8 on the lb10 seat (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_47.md`, `reports/arrow47_results.txt`,
`reports/arrow46_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
last-RTH fills, costs, borrow proxy. Reuse `src/research/clock.py`.

Arrow 47: $3,000 on `n15_lb10_h10` scaled 1.50× on both slices.
Hold 5 on the same rank still cleared OOS $100. `n8_lb10_h10` cleared
the seat line with a higher profit factor. This arrow scales further and
puts size on those two doors. No long leg. No retune of 43 or frozen
B / flush. No new ingest. Do not touch Lab A `data/bars/` except to read
a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction.

## Ids (frozen — do not add a 7th)

Residual lookback 10. Short residual winners only.

| id | n | hold | notional |
|---|---|---|---|
| 0 `n15_h10_3k` | 15 | 10 | $3,000 | control. Must reprint Arrow 47 `n15_lb10_h10_3k` IS $/day within ±10% and n within ±10% of 260 |
| 1 `n15_h10_4k` | 15 | 10 | $4,000 |
| 2 `n15_h10_5k` | 15 | 10 | $5,000 |
| 3 `n8_h10_3k` | 8 | 10 | $3,000 |
| 4 `n15_h5_3k` | 15 | 5 | $3,000 |
| 5 `n8_h5_3k` | 8 | 5 | $3,000 |

Skip a week if fewer than `2 × n` eligible names have a residual.
Skip a name if a required close is missing.

Print scale ratios vs id 0 for ids 1 and 2 (expected 4/3 and 5/3 if linear).
Print scale of id 3 vs Arrow 47 `n8_lb10_h10` at $2,000 (expected 1.50×).

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
A ring counts as better only if it lifts $/day versus id 0 on **both**
IS and OOS. Slate line is $200/day — say if any id clears it on OOS
with IS not red.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow48_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak/mean concurrent,
IWM alpha skip=0, months.

First paragraph: reprint, scale ratios, who clears $100, who clears $200,
ids that beat control on both slices.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only and $3000 share count (fixture);
- even-month entry is not IS;
- 4k / 5k share counts match notional (fixture);
- h5 exit is five sessions, h10 is ten;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 49.
