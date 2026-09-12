# Build Arrow 62 — last-month MAX, first night (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_61.md`, `reports/tape61_ingest.txt`,
`reports/tape41_ingest.txt`, `reports/tape17_ingest.txt`.

Hotel 7. Jersey = last **calendar month** close-to-close, not 15-session
leftover, not yesterday, not 10:00 pace.
December 2025 on `data/virgin/` is now complete (Arrow 61). January 2026
can rank December.

Long and short are **separate engines**. Do not retune the Wednesday-only
leftover paper book, the Friday+Wednesday pair, same-slot, volume-pace,
day-two, Arrow 43, or frozen B / flush.

Field at **entry** session: prior close $10–$80, PDV ≥ $10M, ETP denylist.
Odd months IS, even OOS, split on entry session.
Reuse `src/research/clock.py` and the book cost / borrow path.
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Last-month return

For calendar month M, prior-month return for a name =
last RTH close of the last NYSE session in month M-1
÷ last RTH close of the first NYSE session in month M-1 − 1.
IWM prior-month return uses the same two stamps.
Skip the name if either close is missing.
Need both stamps on `data/virgin/` or `data/full/` as appropriate
(December 2025 → virgin; June 2026 → full; January 2026 → virgin).

MAX slot = 8 largest prior-month returns.
MIN slot = 8 smallest prior-month returns.
Enter on the **first NYSE session of month M**, last RTH close.
Skip the month if fewer than 16 names have a prior-month return.
$3,000 a name unless the id says $4,000.

## Ids (frozen — do not add a 7th)

| id | engine | hold |
|---|---|---|
| 0 `short_max_m` | short MAX slot | last RTH of last session in month M |
| 1 `long_min_m` | long MIN slot | last RTH of last session in month M |
| 2 `short_max_h10` | short MAX slot | 10 sessions |
| 3 `short_max_iwm_m` | short 8 largest (name month return − IWM month return) | month M |
| 4 `short_max_n15_m` | short 15 MAX | month M |
| 5 `short_max_4k_m` | short MAX, $4,000 | month M |

Id 5 is the paper ticket size, diagnostic.

## Order of work

1. Confirm December 2025 first and last sessions exist on virgin for a
   fixture name and for IWM. If January cannot rank December, stop.
2. IS character: next-month raw return of the MAX eight and of the MIN
   eight (mean, hit). Description. Does not pick an id.
3. Score all six on IS and OOS. One OOS look.
Print Pearson correlation of daily (or monthly) PnL between id 0 and id 1.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Score long and short apart. Print t, CI, peak live, months, n.
Say when a CI excludes 0. Do not call a CI that includes 0 "EV."
There are only 4 IS months and 4 OOS months of entries — say that.
Do not dress a 4-point t-stat up as a large sample.

## Report

`reports/arrow62_results.txt`.

For each id × IS × OOS: $/day, n, hit, wins, losses, avgWin, avgLoss,
PF, se, t, CI, daily-close DD, worst day, peak live notional, IWM alpha,
months.
First paragraph: December rank works, character, who is a seat, MAX vs
IWM-MAX overlap, long vs short.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only; id 1 long-only (fixture);
- January 2026 entry uses December 2025 first/last closes from virgin (fixture);
- hold month exits last session of M; hold 10 exits 10 sessions later (fixture);
- even-month entry is not IS;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 63.
