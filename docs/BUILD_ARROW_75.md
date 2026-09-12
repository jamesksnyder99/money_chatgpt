# Build Arrow 75 — home hour, January / February 2026

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_74.md`, `reports/arrow74_results.txt`,
`reports/tape41_ingest.txt`.

Day frame 2. Each name has a usual RTH hour. Trade only then.
Long and short are **separate engines**. Do not retune Wednesday H10.
Do not declare a fail in the report preamble before the numbers.

Window only: **2026-01-02 through 2026-02-28** on `data/virgin/`.
Home-hour estimate uses the prior **10** sessions (December 2025 is on
virgin). January is character + first look. February is the one look.
Do not score March–August. Do not use February to pick a bucket or n.

Field at prior close: $10–$80, PDV ≥ $10M, ETP denylist.
Reuse cost / borrow path. No new ingest. Do not touch Lab A `data/bars/`
or `data/full/`.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Home hour

RTH buckets (ET): 09:30–10:29, 10:30–11:29, 11:30–12:29, 12:30–13:29,
13:30–14:29, 14:30–15:59 (last bucket is 90 minutes; say so).
For each name, on each session T, look at the prior 10 sessions.
Score a bucket by the sum of (high−low) / open inside that bucket.
Home hour = the bucket with the largest score. Ties: earlier bucket.
Skip the name that session if fewer than 8 of the 10 days have that bucket.

## Rank at the open of hour H

Eligible names whose home hour is H. Need ≥ 8 or skip the hour.
`left` = 15-session close-to-close (eight largest).
`morn` = return from 09:30 first RTH to the last print **before** H starts.
For the 09:30 bucket, `morn` is prior-close to 09:30 (gap). Say so.

## Fill and exit

Fill = first print at or after the bucket open (09:30 / 10:30 / …).
Do not use a stamp from inside H to rank `morn`.
Exit = last print of that same bucket. $3,000 a name.
If the exit bar is missing, flatten last available print in H and flag.

## Ids (frozen — do not add a 7th)

| id | rank | side | days |
|---|---|---|---|
| 0 `short_left` | left | short | every session, every H that has 8 names |
| 1 `long_left` | left | long the 8 smallest left | every session |
| 2 `short_morn` | morn | short | every session |
| 3 `long_morn` | morn | long the 8 smallest morn | every session |
| 4 `short_left_wed` | left | short | Wednesday only |
| 5 `short_left_open` | left | short | only the 09:30 bucket |

## Order of work

1. January character: distribution of home hours; mean fraction of that
   day's RTH range that fell in the estimated home hour (is the clock
   real?); mean 11:01-style return is not required. Description.
2. Score all six on January and February separately. One February look.

$/day = total PnL / NYSE sessions in that month.
Print t, CI, peak live, n hours fired. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."
Do not call February a $200 slate pass. Two months is a sniff.

## Report

`reports/arrow75_results.txt`.

First paragraph: is range concentrated in the estimated hour, which ids
print in January, which survive February, long vs short.
Then each id × January × February.

Append RESEARCH_LOG.md.

Tests:
- home hour uses only prior 10 sessions, not T (fixture);
- id 0 short-only; id 1 long-only (fixture);
- `morn` for a 10:30 bucket does not use prints at or after 10:30 (fixture);
- March is not scored;
- do not read Lab A `data/bars/` or `data/full/`.

Commit code + reports. No parquet. No Arrow 76.
