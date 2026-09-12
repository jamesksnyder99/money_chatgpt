# Build Arrow 66 — Wednesday hold path 5 / 10 / 15 (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_65.md`, `reports/arrow65_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Same leftover short as Arrow 65 `nextrth_4k`: Wednesday signal, 15-session
minus IWM, short eight, fill **next session last-RTH**, $4,000, drop a
name if the exit bar is missing. MTM daily equity as in Arrow 65.

This arrow is the path. It is not keep/cash and not replace.
Do not retune rank, weekday, or n. Do not retune frozen B / flush.

Odd months IS, even OOS, split on the **signal** Wednesday.
Reuse `src/research/clock.py`. No new ingest. Do not touch Lab A
`data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold. Do not pick a hold from
the OOS path.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Ids (frozen — do not add a 7th)

Hold counts sessions after the **fill** session.

| id | hold | ticket | missing exit |
|---|---|---|---|
| 0 `h10_4k` | 10 | $4,000 | drop | control. Must reprint Arrow 65 `nextrth_4k` IS MTM $/day within ±10% and n within ±10% of 116 |
| 1 `h5_4k` | 5 | $4,000 | drop |
| 2 `h15_4k` | 15 | $4,000 | drop |
| 3 `h10_3k` | 10 | $3,000 | drop |
| 4 `h15_4k_keep` | 15 | $4,000 | flatten last available RTH |
| 5 `h5_4k_keep` | 5 | $4,000 | flatten last available RTH |

## Path (IS only — description, does not pick an id)

On id 0's fills, mark each name at last-RTH of fill+1, +2, …, +15
(or last available if the name exits early). Print a 15-row table:
hold_day, n, mean MTM $ per name, mean remaining residual vs IWM,
fraction still in that session's leftover top 8.
Do not print the OOS path in a way that chooses a hold.

## Accounting

Same as Arrow 65: entry bag **and** MTM $/day. Seat and slate use MTM.
Peak live = max |shares × last| across sessions, including holds that
cross an IS/OOS month boundary. Hold 15 will stack more cohorts — say
whether it still fits $100k.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. IS path table.
3. Score all six. One OOS look.

Pass for a seat: OOS MTM $/day ≥ $100 **and** IS MTM not red.
Slate: OOS MTM ≥ $200 **and** IS MTM not red **and** peak live ≤ $100k.
A ring beats id 0 only if it lifts MTM $/day on **both** IS and OOS.
Print t and CI on the MTM daily series. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow66_results.txt`.

First paragraph: reprint, IS path in one sentence (where the mean mark
peaks), who is slate, whether hold 15 fits and lifts both slices.
Then the path table. Then each id × IS × OOS with entry $/day, MTM $/day,
n, hit, wins, losses, avgWin, avgLoss, PF, se, t, CI, MTM DD, worst day,
peak live, months.

Append RESEARCH_LOG.md.

Tests:
- id 0 next last-RTH fill, hold 10, $4000 (fixture);
- id 1 exits 5 sessions after fill; id 2 exits 15 (fixture);
- path table has 15 rows and is IS-only (fixture or log);
- even-month signal is not IS;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 67.
