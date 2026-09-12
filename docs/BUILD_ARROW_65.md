# Build Arrow 65 — Wednesday leftover plumbing (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_56.md`, `reports/arrow56_results.txt`,
`docs/BUILD_ARROW_52.md`, `reports/arrow52_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Plumbing only. Same leftover short. Do not change rank, n, lookback,
weekday, or hold. Do not open keep/cash or replace. Do not walk hold 5/15.
Those are later arrows.

Paper parent: Wednesday only, 15-session name return minus IWM, short
eight, hold 10, field $10–$80 PDV ≥ $10M ETP denylist.
Do not retune Friday+Wednesday pair, SIC group, MAX, volume-pace,
day-two, same-slot, Arrow 43, or frozen B / flush.

Odd months IS, even OOS, split on **signal** session (the Wednesday the
rank is known). Reuse `src/research/clock.py`.
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Rank (shared)

Wednesday last-RTH close is the **signal**. Residual = name 15-session
close-to-close − IWM. Short the 8 winners. Skip if fewer than 16 names
have a residual. Skip a name if a required **signal** close is missing.

## Fills

- `close` = fill the signal last-RTH close (old lie).
- `open` = fill the **next** session 09:30 last (first print at or after 09:30). If that bar is missing, skip the name and count the skip.
- `nextrth` = fill the next session last-RTH close.

Exit: last-RTH close of the session that is 10 sessions after the **fill**
session, unless the id says keep-missing.
`keep` ids: if that exit bar is missing, flatten at the last available
RTH close on or before that session and flag `exit_partial`. Do **not**
delete the trade.

## Ids (frozen — do not add a 7th)

| id | fill | ticket | missing exit |
|---|---|---|---|
| 0 `close_3k` | close | $3,000 | drop (old behavior) | control. Must reprint Arrow 56 `wm_wed_3k` IS $/day within ±10% and n within ±10% of 118 |
| 1 `close_4k` | close | $4,000 | drop |
| 2 `open_4k` | open | $4,000 | drop |
| 3 `nextrth_4k` | nextrth | $4,000 | drop |
| 4 `open_4k_keep` | open | $4,000 | flatten last available RTH |
| 5 `nextrth_4k_keep` | nextrth | $4,000 | flatten last available RTH |

## Accounting (every id)

Print **both**:

1. Entry-attributed $/day as prior arrows (PnL bagged on the signal session).
2. MTM $/day: mark every open short at last-RTH each session; daily book PnL is the sum of those marks plus that day's fills/exits minus costs as they hit. Equity, daily-close DD, and worst day must come from this series.

Peak live notional = max across sessions of |shares × last| for names still on, including holds that cross an IS/OOS month boundary. `fits_100k` uses that number.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Score all six. One OOS look.

Pass for a seat: OOS MTM $/day ≥ $100 **and** IS MTM $/day not red.
Slate: OOS MTM $/day ≥ $200 **and** IS MTM not red **and** peak live ≤ $100k.
Print t and CI on the MTM daily series. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow65_results.txt`.

For each id × IS × OOS: entry $/day and MTM $/day, n, skips, exit_partial count, hit, wins, losses, avgWin, avgLoss, PF, se, t, CI, MTM daily-close DD, worst day, peak live, IWM alpha, months.
First paragraph: reprint, whether next-open still seats, whether keep-missing changed n, peak live vs the old $69–$72k mark.

Append RESEARCH_LOG.md.

Tests:
- id 0 Wednesday only, $3000, close fill (fixture);
- id 2 fill is next session 09:30, not the signal close (fixture);
- id 4 keeps a trade whose day-10 exit bar is missing (fixture);
- even-month **signal** is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 66.
