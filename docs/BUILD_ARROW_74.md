# Build Arrow 74 — intradaily leftover, January / February 2026

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_66.md`, `reports/arrow66_results.txt`,
`reports/tape41_ingest.txt`.

Day frame 1. Jersey = who already ran **this morning**, not three weeks.
Long and short are **separate engines**. Do not retune Wednesday H10.
Do not keep/cash. Do not IWM-up skip the swing book.

Window only: **2026-01-02 through 2026-02-28** on `data/virgin/`.
January is the character / first look. February is the one look.
Do not treat this as the shop IS/OOS split. Do not score March–August.
Do not use February to pick a threshold.

Field at prior close: $10–$80, PDV ≥ $10M, ETP denylist.
Reuse cost / borrow path in `src/research/clock.py` / book.
No new ingest. Do not touch Lab A `data/bars/` or `data/full/`.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Rank

Morning return = last print at or before **11:00** ÷ first RTH print at or
after **09:30** − 1. IWM morning return uses the same stamps (scalar).
Short the 8 largest morning returns. Long id shorts nothing — it buys the
8 smallest morning returns.
Skip the session if fewer than 16 names have both stamps.

## Fill and exit

Do not fill the 11:00 bar used to rank.
Fill = first print at or after **11:01** (09:30 grid). If missing, skip.
Exit = last RTH 15:59 same session. If missing, last available RTH after
11:01 and flag partial. $3,000 a name.

## Ids (frozen — do not add a 7th)

| id | side | days |
|---|---|---|
| 0 `short_all` | short | every session |
| 1 `long_all` | long the 8 laggards | every session |
| 2 `short_wed` | short | Wednesday only |
| 3 `short_1100` | short | every session, fill the **11:00** rank bar (the old lie) |
| 4 `short_up` | short | every session, only if IWM morning return ≥ 0 |
| 5 `short_dn` | short | every session, only if IWM morning return < 0 |

## Order of work

1. January character: mean morning return of the eight winners and eight
   laggards from 11:01→15:59 (mean, hit). Description. Does not pick an id.
2. Score all six on January and on February separately. One February look.

Print $/day as total PnL / NYSE sessions in that month.
Print t, CI, peak live. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."
Do not call February a $200 slate pass. Two months is a sniff, not a seat.

## Report

`reports/arrow74_results.txt`.

First paragraph: January character, whether afternoon fade exists, whether
11:01 fill still prints, Wednesday vs every day, long vs short.
Then each id × January × February.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only; id 1 long-only (fixture);
- id 0 fill is ≥ 11:01, not the 11:00 rank stamp (fixture);
- March 2026 is not scored;
- do not read Lab A `data/bars/` or `data/full/`.

Commit code + reports. No parquet. No Arrow 75.
