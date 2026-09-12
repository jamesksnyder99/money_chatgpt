# Build Arrow 45 — residual-short rings (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_44.md`, `reports/arrow44_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Same field as Arrow 44. Short last week's residual winners only.
Rings locked from the IS character and the IS `res_short` print.
OOS is one look for the whole family. Do not drop an id after seeing OOS.
Do not use June, August, or any OOS month to pick a threshold.

Do not retune Arrow 43 clocks. Do not bring back `res_long`.
Do not retune `B|conj|atr1559|lock` or `flush|max6|repaired`.
No FLY. No 08:00. No conjunction. No new ingest.
Do not touch Lab A `data/bars/` except to read an existing helper.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction.

## Calendar and residual

Reuse `src/research/clock.py` (`rebalance_sessions`, `session_shift`, tape roots).

Same study calendar, IS/OOS split on entry session, eligibility wall,
IWM subtraction, last-RTH fills, $2,000 notional, costs, borrow proxy
as Arrow 44. Residual = name 5-session close-to-close − IWM same window
unless an id says lookback 10.

Lookback 5: close today ÷ close five sessions earlier − 1.
Lookback 10: close today ÷ close ten sessions earlier − 1.
Hold 5: exit last RTH five sessions later.
Hold 10: exit last RTH ten sessions later.

Skip a name if a required close is missing. Skip a week if fewer than
`2 × n_short` eligible names have a residual.

## Ids (frozen — do not search, do not add a 7th)

Short only. Rank eligible names on residual, high = winner.

| id | n short | hold | extra |
|---|---|---|---|
| 0 `n15_h5` | 15 | 5 | control. Must reprint Arrow 44 `res_short` IS $/day within ±10% and n within ±10% of 272 |
| 1 `n10_h5` | 10 | 5 | tighter tail |
| 2 `n8_h5` | 8 | 5 | tighter tail |
| 3 `n15_h5_r04` | 15 | 5 | keep only residual ≥ 0.04 |
| 4 `n15_h5_r08` | 15 | 5 | keep only residual ≥ 0.08 |
| 5 `n15_h10` | 15 | 10 | same rank as control, longer hold |

If a threshold id has fewer than 8 names that week, take what clears the
bar. Do not fill the seat with names under the bar.

## Order of work

1. Id 0 reprint. If it misses the Arrow 44 `res_short` reprint band, stop
   and fix the runner. Do not score rings on a drifted control.
2. IS character for the rings that change the population (n10, n8, r04,
   r08): mean next-hold residual of the names that would be shorted.
   Description. Does not pick an id.
3. Score all six ids on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Goal of the rings: lift $/day versus control on **both** IS and OOS.
Print that comparison. An id that lifts IS and cuts OOS is not an
improvement. An id that lifts OOS and turns IS red is not a seat.

Slate $200 is not this arrow's job.

## Report

`reports/arrow45_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, PF, se, t, CI,
daily-close DD, worst day, peak/mean concurrent, IWM alpha skip=0, months.
avgR is n/a.

First paragraph: reprint check, then which ids beat control on both slices,
then seat / no seat.

Append RESEARCH_LOG.md.

Tests:
- id 0 is short-only (no long fills);
- even-month entry is not IS;
- r04 / r08 never short a name with residual under the bar (fixture);
- h10 exit is ten sessions after entry, not five;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 46.
