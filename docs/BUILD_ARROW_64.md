# Build Arrow 64 — group leftover versus SIC2 (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_63.md`, `reports/tape63_sic.txt`,
`docs/BUILD_ARROW_53.md`, `reports/arrow53_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Hotel 6. Peer benchmark is **SIC2**, not IWM, not the whole eligible universe.
Map file: `data/meta/sector_sic.parquet` frozen asof 2026-09-11.
Do not refresh the map. Do not hit SEC again.

Long and short are **separate engines**. Do not retune the Wednesday-only
leftover paper book, Friday+Wednesday pair, MAX, volume-pace, day-two,
same-slot, Arrow 43, or frozen B / flush.

Same tape wall plus a SIC2: prior close $10–$80, PDV ≥ $10M, ETP denylist,
and a row in the SIC map. Skip names with no sic2.
Odd months IS, even OOS, split on entry session.
Reuse `src/research/clock.py` and the book cost / borrow path.
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; SIC = Standard Industrial
Classification; RTH = regular trading hours; EV = expected value;
SSR = Short Sale Restriction; CI = confidence interval.

## Residual

Name return = last RTH close today ÷ last RTH close 15 sessions earlier − 1.
Peer set = other eligible names **that session** with the same `sic2`
and a 15-session return. Need ≥ 8 peers or drop the name from group ids.
Group residual = name return − median peer return.
IWM residual = name return − IWM 15-session return (control only).

Short the 8 largest residuals unless the id says 15.
Enter last RTH. Hold 10. $3,000 unless the id says $4,000.
Skip a rebalance if fewer than 16 names have the id's residual.

## Ids (frozen — do not add a 7th)

| id | rank | calendar | n | ticket |
|---|---|---|---|---|
| 0 `short_iwm_fri` | IWM residual | Friday | 8 | $3,000 | control on the **SIC-mapped** field only |
| 1 `short_sic_fri` | group residual | Friday | 8 | $3,000 |
| 2 `long_sic_fri` | group residual, long the 8 smallest | Friday | 8 | $3,000 |
| 3 `short_sic_wed` | group residual | Wednesday | 8 | $3,000 |
| 4 `short_sic_fri_n15` | group residual | Friday | 15 | $3,000 |
| 5 `short_sic_fri_4k` | group residual | Friday | 8 | $4,000 |

## Order of work

1. IS character: mean SIC-mapped eligible names per Friday; mean peers
   per name that kept a group residual; overlap of id 0 eight vs id 1
   eight (mean names in common). Description. Does not pick an id.
2. Score all six on IS and OOS. One OOS look.
Print Pearson daily PnL correlation of id 0 vs id 1, and of id 1 vs id 2.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** peak live ≤ $100k.
A group id beats control only if it lifts $/day versus id 0 on **both**
IS and OOS. Score long and short apart.
Print t, CI, peak live. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow64_results.txt`.

For each id × IS × OOS: $/day, n, hit, wins, losses, avgWin, avgLoss,
PF, se, t, CI, daily-close DD, worst day, peak live, IWM alpha, months.
First paragraph: mapped-field size vs Arrow 52 field, overlap vs IWM
control, who is a seat, long vs short, Wednesday vs Friday.

Append RESEARCH_LOG.md.

Tests:
- id 1 residual subtracts same-sic2 median, not IWM (fixture);
- id 2 is long-only; ids 0,1,3,4,5 are short-only (fixture);
- a name with fewer than 8 sic2 peers is dropped from group ids (fixture);
- even-month entry is not IS;
- do not call SEC;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 65.
