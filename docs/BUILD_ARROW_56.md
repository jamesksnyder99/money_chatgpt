# Build Arrow 56 — net-pair size and Wednesday+Monday (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_55.md`, `reports/arrow55_results.txt`,
`reports/arrow52_results.txt`, `reports/tape17_ingest.txt`,
`reports/tape41_ingest.txt`.

Same field. Short only. Lookback 15. Residual vs IWM. Eight names.
Hold 10. Last-RTH. Net rule: if the name is already on from the earlier
weekday of the pair, skip the later ticket. Reuse `src/research/clock.py`.

Arrow 55: Friday and Wednesday are two seats (daily PnL corr ≈ 0,
overlap 3.2/8). `pair_3k_net` is the slate that fits (OOS +$225, peak
live ~$81k). Wednesday+Thursday net was the weaker pair. This arrow
sizes the Friday+Wednesday net pair and asks whether Wednesday+Monday
is another pair. Monday was the unused high even-month weekday.
No fade. No sector map. No long leg. No retune of 43 or frozen B / flush.
No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Ids (frozen — do not add a 7th)

All stacked ids use the net rule unless named `dbl`.

| id | calendars | ticket |
|---|---|---|
| 0 `fw_3k_net` | Friday + Wednesday | $3,000 | control. Must reprint Arrow 55 `pair_3k_net` IS $/day within ±10% and n within ±10% of 156 |
| 1 `fw_2k_net` | Friday + Wednesday | $2,000 |
| 2 `fw_4k_net` | Friday + Wednesday | $4,000 |
| 3 `fw_4k_dbl` | Friday + Wednesday | $4,000, two tickets allowed in the same name |
| 4 `wm_3k_net` | Wednesday + Monday | $3,000, net |
| 5 `wm_3k_corr` | score Wednesday $3,000 and Monday $3,000 as separate books; print daily PnL correlation and mean name overlap; do not stack |

Id 5 is diagnostic. Print Pearson correlation IS and OOS like Arrow 55.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** peak live notional ≤ $100k.
A ring counts as better than id 0 only if it lifts $/day on **both** IS and OOS and fits $100k.
Print t, CI, peak live notional. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow56_results.txt`.

For each id × IS × OOS: $/day, n, hit, wins, losses, avgWin, avgLoss,
PF, se, t, CI, daily-close DD, worst day, peak live notional, IWM alpha,
months.
First paragraph: reprint, scale vs $3k, who fits and clears slate,
Wednesday+Monday correlation and overlap, whether Wednesday+Monday is a second pair.

Append RESEARCH_LOG.md.

Tests:
- id 0 net Friday+Wednesday $3000, no second ticket if already on (fixture);
- id 3 may open two tickets in the same name (fixture);
- id 4 Monday entries exist (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 57.
