# Build Arrow 50 — execution and hold path on n8 (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_49.md`, `reports/arrow49_results.txt`,
`reports/arrow48_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
costs, borrow proxy. Reuse `src/research/clock.py`.
Lookback 10. Rank the eight largest residuals. Default notional $6,000.

Arrows 44–49 locked the rank, the tail, and the ticket. This arrow asks
how we get in and whether we stay ten sessions. No long leg. No retune
of 43 or frozen B / flush. No new ingest. Do not touch Lab A `data/bars/`
except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction.

## Rank (shared)

On each rebalance session, residual = name close-to-close over 10 sessions
minus IWM on the same stamps. Short the 8 winners. Skip a week if fewer
than 16 eligible names have a residual. Skip a name if a required fill is
missing.

## Ids (frozen — do not add a 7th)

| id | entry | exit |
|---|---|---|
| 0 `fri_h10` | last RTH close of the rebalance session | last RTH close 10 sessions later | control. Must reprint Arrow 49 `n8_h10_6k` IS $/day within ±10% and n within ±10% of 135 |
| 1 `mon_h10` | next session 09:30 open after the rank close | last RTH close 10 sessions after that entry session |
| 2 `fri_h5` | same as id 0 | last RTH close 5 sessions later |
| 3 `fri_give5` | same as id 0 | at session +5 if the short is ahead (exit px < entry px); else session +10 |
| 4 `fri_h10_iwm8` | same as id 0 | same as id 0 | skip the week if IWM 10-session return ≥ 0.08 |
| 5 `lb15_fri_h10` | same as id 0 | same as id 0 | rank lookback 15 sessions instead of 10 |

Id 2 is hold 5 at $6,000 — we have hold 5 at $4k/$5k, not at the $6k ticket.
Id 3 is the mid-hold mark: take the giveback if it printed by day 5; otherwise stay.
Id 4 is a market filter on IWM, not on the name.

Notional $6,000 on every id.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** two-cohort notional ≤ $100k
(hold 10 = two cohorts; hold 5 and give5-when-flat count as one cohort unless
the id still has names on after session +5 — print both).
A ring counts as better only if it lifts $/day versus id 0 on **both** IS and OOS.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow50_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak/mean concurrent,
IWM alpha skip=0, months, one-cohort $, two-cohort $.
For id 3 also print the fraction of names that exited at +5 vs +10 (IS only
in the character line; both slices in the book lines).

First paragraph: reprint, who beats control on both slices, who clears
seat / slate, whether Monday entry kept the OOS print.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only, $6000, entry last RTH not 09:30 (fixture);
- id 1 entry is 09:30 of the next session (fixture);
- id 3 exits at +5 when exit_px < entry_px and at +10 otherwise (fixture);
- id 4 does not enter when IWM 10-session return is 0.08 or more (fixture);
- id 5 uses close 15 sessions back (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 51.
