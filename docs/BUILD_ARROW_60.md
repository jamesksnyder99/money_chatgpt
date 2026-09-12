# Build Arrow 60 — day-two after an extreme (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_59.md`, `reports/arrow59_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Hotel 5 of 7. Hotel 4 (home hour) skipped — remote, another 1-minute
clock scan. This hotel is the session *after* a name printed a +10%
intraday high versus the prior close.

Long and short are **separate engines**. Prior rocket work longed these
names and lost. First night includes the short. Do not retune the
Friday+Wednesday leftover pair, same-slot ids, volume-pace ids, Arrow 43,
or frozen B / flush.
Same field wall: prior close on session T $10–$80, PDV on T ≥ $10M, ETP
denylist. Combined virgin+full. Odd months IS, even OOS, split on the
**entry** session (T+1).
Reuse `src/research/clock.py` and the book cost / borrow path.
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Extreme (session T)

T is an extreme if the session-T high (RTH 09:30–15:59) ≥ 1.10 × T-minus-1
last-RTH close. Skip T if that prior close is missing or the high is missing.
Entry is on T+1. Skip the name if T+1 09:30 or the required exit is missing.
If more than 8 extremes on T, take the 8 largest T highs versus prior close.
If 1–8, take them all. $3,000 a name.

## Ids (frozen — do not add a 7th)

| id | engine | entry | exit | extra |
|---|---|---|---|---|
| 0 `short_0930_1159` | short | T+1 09:30 | T+1 15:59 | all extremes |
| 1 `long_0930_1159` | long | T+1 09:30 | T+1 15:59 | all extremes |
| 2 `short_0930_next` | short | T+1 09:30 | T+2 last RTH | all extremes |
| 3 `short_still_1159` | short | T+1 09:30 | T+1 15:59 | T last-RTH close still ≥ 1.05 × T-minus-1 close |
| 4 `short_gave_1159` | short | T+1 09:30 | T+1 15:59 | T last-RTH close < 1.05 × T-minus-1 close (gave the high back) |
| 5 `long_gave_1159` | long | T+1 09:30 | T+1 15:59 | same giveback as id 4 |

## Order of work

1. IS character, description, does not pick an id: count of T extremes per
   session (mean, max); T+1 09:30→15:59 mean return and hit of those names;
   split still-extended vs gave-back.
2. Score all six on IS and OOS. One OOS look.
Print Pearson correlation of daily PnL between id 0 and id 1.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Score long and short apart. Print t, CI, peak live, n/sess.
Say when a CI excludes 0. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow60_results.txt`.

For each id × IS × OOS: $/day, n, n/sess, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak live notional,
IWM alpha skip=0, months.
First paragraph: character, which engines are seats, still-extended vs
gave-back, long vs short.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only; id 1 long-only (fixture);
- T extreme uses T high ≥ 1.10 × prior close, entry is T+1 (fixture);
- id 3 rejects a name whose T close < 1.05 × prior close (fixture);
- even-month **entry** is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 61.
