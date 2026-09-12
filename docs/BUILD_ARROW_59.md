# Build Arrow 59 — volume-pace hotel, first night (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_58.md`, `reports/arrow58_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

New hotel. Not leftover versus IWM. Not yesterday's return jersey.
Pace = how fast today's tape is versus that name's own recent tape
at the same clock.

Long and short are **separate engines**. Do not build them as a sign flip.
Do not retune the Friday+Wednesday leftover pair, Arrow 43 clocks,
same-slot ids, or frozen B / flush.
Same field wall: prior close $10–$80, PDV ≥ $10M, ETP denylist.
Combined virgin+full tape. Odd months IS, even OOS, split on entry session.
Reuse `src/research/clock.py` and the book cost / borrow path.
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Pace

Clock = 10:00 ET.
Today's pace window = RTH dollar volume from 09:30 through the 09:59 bar
(30 one-minute bars). If the 09:30 open print is missing, skip the name.
Baseline = median of that same 09:30–09:59 dollar volume over the prior
20 sessions that have the window. Need at least 10 of those 20.
Pace = today_window ÷ baseline. Skip if baseline ≤ 0.

Hot slot = 8 largest pace. Quiet slot = 8 smallest pace.
Fill at the 10:00 bar (first bar at or after 10:00 ET). If that bar is
missing, skip the name.
$3,000 a name.

## Ids (frozen — do not add a 7th)

| id | engine | exit |
|---|---|---|
| 0 `short_hot_1159` | short the 8 hot names | 15:59 same session |
| 1 `long_quiet_1159` | long the 8 quiet names | 15:59 same session |
| 2 `short_hot_next` | short the 8 hot names | next session last RTH |
| 3 `long_quiet_next` | long the 8 quiet names | next session last RTH |
| 4 `short_hot_up_1159` | short hot names whose 10:00 last ≥ prior last-RTH close | 15:59 |
| 5 `long_quiet_dn_1159` | long quiet names whose 10:00 last ≤ prior last-RTH close | 15:59 |

Ids 4 and 5 are confirmation, not a sign flip of each other: hot-and-up
is a running tape; quiet-and-down is a dead tape. Skip the id's day if
fewer than 5 names clear that extra filter; if 5–7, take them all.
Skip a session if fewer than 16 names have a pace.

## Order of work

1. IS character, description, does not pick an id: from 10:00 to 15:59,
   mean return and hit of the hot eight and of the quiet eight.
2. Score all six on IS and OOS. One OOS look.
Print Pearson correlation of daily PnL between id 0 and id 1, IS and OOS.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate is $200 for the shop, not this first night's job.
Score long and short apart. Print t, CI, peak live notional.
Say when a CI excludes 0. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow59_results.txt`.

For each id × IS × OOS: $/day, n, n/sess, hit, wins, losses, avgWin,
avgLoss, PF, se, t, CI, daily-close DD, worst day, peak live notional,
IWM alpha skip=0, months.
First paragraph: character, which engines are seats, whether hot-and-up
or quiet-and-down changed the book, correlation of the two same-day engines.

Append RESEARCH_LOG.md.

Tests:
- id 0 short-only; id 1 long-only (fixture);
- pace uses 09:30–09:59 dollar volume over a 10:00 fill, not a 15-session
  residual (fixture);
- id 4 rejects a hot name whose 10:00 last < prior close (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 60.
