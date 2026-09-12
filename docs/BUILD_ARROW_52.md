# Build Arrow 52 — weekday rank and standing top-8 (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_51.md`, `reports/arrow51_results.txt`,
`reports/arrow50_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Same calendar, eligibility, IWM subtraction,
costs, borrow proxy. Reuse `src/research/clock.py`.
Lookback 15. Eight names. $6,000. Residual = name close-to-close over 15
sessions minus IWM on the same stamps. Short the 8 winners.

This is a new hallway, not another lookback click. Arrow 51 left
`lb15_h10` as the Friday parent. This arrow asks whether Friday is doing
work, or whether the leftover is the object on any weekday, and whether a
standing top-8 book (rebalanced every session) is a different engine.
Do not combine the weekday books into one portfolio. Score them apart.
No long leg. No retune of 43 or frozen B / flush. No new ingest.
Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Ids (frozen — do not add a 7th)

Weekday books: rebalance only on that weekday (every Monday, every Tuesday,
…). Entry last RTH close that session. Exit last RTH close 10 sessions later.
If that weekday is a holiday, skip the week for that id. Do not roll the
rebalance onto the next day — that would mix hallways.

| id | rebalance | hold |
|---|---|---|
| 0 `fri_h10` | Friday (or existing `rebalance_sessions` last-of-week only if that last day is Friday; otherwise skip) | 10 | control. Must reprint Arrow 51 `lb15_h10` IS $/day within ±10% and n within ±10% of 129. If last-of-week includes non-Fridays in Arrow 51, reprint against the Friday-only subset — say which you did and why. |
| 1 `mon_h10` | Monday | 10 |
| 2 `tue_h10` | Tuesday | 10 |
| 3 `wed_h10` | Wednesday | 10 |
| 4 `thu_h10` | Thursday | 10 |
| 5 `stand_top8` | every study session | standing |

Id 5: each session the book *is* the current top 8. Enter names that joined
the top 8 at that session's last RTH close. Exit names that left the top 8
at that session's last RTH close. No ten-session clock. One cohort, $48k.
A name that stays in the top 8 stays on.

Skip a rebalance if fewer than 16 eligible names have a residual.
Skip a name if a required fill is missing.

Print two-cohort $ for ids 0–4 ($96k) and one-cohort $ for id 5 ($48k).

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix. If Friday-only n
   differs from Arrow 51 because 51 used last-of-week including Thursdays,
   print both numbers and still score the other ids.
2. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** live notional ≤ $100k.
A ring counts as better only if it lifts $/day versus id 0 on **both** IS and OOS.
Print t and CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow52_results.txt`.

For each id × IS × OOS: $/day, n, n/week or n/sess, hit, wins, losses,
avgWin, avgLoss, PF, se, t, CI, daily-close DD, worst day, peak/mean
concurrent, IWM alpha skip=0, months, deployed $.
For id 5 also print median days a name stays in the book (IS only in a
character line; both slices in the book lines).

First paragraph: reprint, which weekdays clear seat / slate, whether any
weekday beats Friday on both slices, whether stand_top8 is a seat.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only, lookback 15, Friday entries only (fixture);
- id 1 entries are Mondays only (fixture);
- id 5 can enter on a Tuesday (fixture);
- id 5 exits a name the session it leaves the top 8 (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 53.
