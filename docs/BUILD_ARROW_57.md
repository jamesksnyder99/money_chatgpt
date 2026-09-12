# Build Arrow 57 — same-slot hotel, first night (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_56.md`, `reports/arrow56_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

New hotel. Do not retune the Friday+Wednesday leftover pair, Arrow 43
clocks, or frozen B|conj|atr1559|lock / flush|max6|repaired.
Long and short are **separate engines**. Do not build them as a sign flip
of one door and call it two books.

Slot = who is wearing yesterday's extreme close-to-close jersey in the
eligible field. Not 15-session leftover. Not versus IWM unless the id
says so.

Same field wall so the leftover pair still has its names: prior close
$10–$80, PDV ≥ $10M, ETP denylist. Combined virgin+full tape. Odd months
IS, even months OOS, split on entry session. Reuse `src/research/clock.py`
and the book cost / borrow path.
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Rank

On session T, name return = T last-RTH close ÷ T-minus-1 last-RTH close − 1.
Skip the name if either close is missing.
Winner slot = 8 largest T returns. Loser slot = 8 smallest T returns.
Enter at T last-RTH close. Exit at the id's hold.
Skip T if fewer than 16 eligible names have a T return.
$3,000 a name. Cap 8 per engine.

## Ids (frozen — do not add a 7th)

| id | engine | hold |
|---|---|---|
| 0 `short_win_h1` | short the 8 winner-slot names | next session last RTH (1 session) |
| 1 `long_lose_h1` | long the 8 loser-slot names | 1 session |
| 2 `short_win_h5` | short winner slot | 5 sessions |
| 3 `long_lose_h5` | long loser slot | 5 sessions |
| 4 `short_res_h1` | short the 8 names with largest T return minus IWM T return | 1 session |
| 5 `long_res_h1` | long the 8 names with smallest T return minus IWM T return | 1 session |

Ids 0 and 1 are the two engines of this hotel. Ids 4 and 5 ask whether
subtracting IWM changes the jersey. Ids 2 and 3 ask whether the slot
needs a week to pay.

## Order of work

1. Character on IS only, description, does not pick an id: next-session
   raw return of the winner-slot eight and of the loser-slot eight
   (mean, hit). Same for residual-vs-IWM slots.
2. Score all six on IS and OOS. One OOS look.
Print Pearson correlation of daily PnL between id 0 and id 1, IS and OOS.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate is $200/day for the shop, not this first night's job.
A long id is not judged as a failed short. Score them apart.
Print t and CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."
Print peak live notional. Two overlapping 8-name books at $3,000 = $48k
if both engines are on the same day.

## Report

`reports/arrow57_results.txt`.

For each id × IS × OOS: $/day, n, n/sess, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak live notional,
IWM alpha skip=0, months.
First paragraph: character, which engines are seats, long vs short,
correlation of the two h1 engines, whether IWM changes the jersey
(mean names in common id 0 vs id 4 on IS).

Append RESEARCH_LOG.md.

Tests:
- id 0 is short-only; id 1 is long-only (fixture);
- id 0 ranks raw return not 15-session residual (fixture);
- hold 1 exits next session; hold 5 exits five sessions later (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 58.
