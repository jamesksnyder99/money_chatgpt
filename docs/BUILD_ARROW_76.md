# Build Arrow 76 — open leftover short, first hallway (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_75.md`, `reports/arrow75_results.txt`,
`reports/tape41_ingest.txt`, `reports/tape17_ingest.txt`.

Stay in the home-hour hotel. Arrow 75 showed the clock is the **open**.
This arrow is the leftover short at 09:30, flatten later — rings written
now. Longs stay off. Do not retune Wednesday H10.

Parent: eight largest 15-session close-to-close returns, fill first print
at or after **09:30**, field $10–$80 PDV ≥ $10M ETP denylist, $3,000.
Home-hour estimate is not required; 75 showed ~99% of names are 09:30.

Window: **2026-01-02 through 2026-04-30**.
January+March = odd (IS). February+April = even (OOS).
January/February already seen — print them, but a ring beats the parent
only on **both** the odd pair and the even pair, and April is new dirt.
Do not use April to pick a hold. Do not score May–August.
May tape is virgin; April is virgin. June is full — do not need it.

Reuse cost / borrow. No new ingest. Do not touch Lab A `data/bars/`.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Ids (frozen — do not add a 7th)

Exit is last print of the stamp. Do not fill a later bar than the rank
needs. Rank uses **prior** close only (15-session), so 09:30 fill is causal.

| id | n | exit | ticket |
|---|---|---|---|
| 0 `h1029_n8` | 8 | 10:29 | $3,000 | parent. January $/day should sit near Arrow 75 `short_left_open` +334.93 |
| 1 `h1129_n8` | 8 | 11:29 | $3,000 |
| 2 `h1559_n8` | 8 | 15:59 | $3,000 |
| 3 `h1029_n15` | 15 | 10:29 | $3,000 |
| 4 `h1029_n8_4k` | 8 | 10:29 | $4,000 |
| 5 `h1029_n8_wed` | 8 | 10:29 | $3,000 | Wednesday signals only |

## Order of work

1. Id 0 January vs Arrow 75 `short_left_open`. If it misses ±20%, stop and fix.
2. Score all six on odd months (Jan+Mar) and even months (Feb+Apr).
   Also print each calendar month.

$/day = total PnL / NYSE sessions in that slice.
Peak live = |shares × entry| (same-session book).
A ring beats id 0 only if it lifts $/day on **both** odd and even slices.
Print t, CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."
Two extra months is still a sniff for promotion. Say that.

## Report

`reports/arrow76_results.txt`.

First paragraph: reprint, whether holding past 10:29 lifts both slices,
n=15, Wednesday, $4k.
Then each id × odd × even × months.

Append RESEARCH_LOG.md.

Tests:
- id 0 exits 10:29 not 15:59 (fixture);
- id 2 exits 15:59 (fixture);
- id 0 is short-only (fixture);
- May is not scored;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 77.
