# Build Arrow 36 — regular-trading-hours birth, ungated

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow35_score.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

A35 GATE=NO — **no score decile gate**. No cell. No FLY label. No 08:00 hot. No $500/idea. No virgin. Do not rescore the B-short.

Acronyms: ATR = Average True Range; RVOL = relative volume; MFE = maximum favorable excursion.

**Granularity law:** confirmed launch is a **one-minute** close ≥ 1.10× prior_close and next tradeable one-minute low ≥ 1.08× prior_close. Entry = next one-minute open. Do not wait for a five-minute close.

## Population

prior_close [$3, $20], ≥5 prior sessions, common stock on data/full/. **No** RVOL floor (A35 quintiles were not monotone). Cap8, $200/idea, ranked by run_rel_vol at the signal if you need a tie-break. Harness stop floor on. A1-style available_at: the launch close must be complete before the order.

## Ids (long only)

| id | window | exit |
|---|---|---|
| 0 | launch in **09:45–11:59** | flatten 11:59 |
| 1 | same window | after +1R, trail 1.0× ATR, flatten 15:59 |
| 2 | launch in **09:45–10:29** | flatten 11:59 |
| 3 | launch in **10:30–11:59** | flatten 11:59 |
| 4 | launch in **12:00–15:00** | after +1R, trail 1.0× ATR, flatten 15:59 |

Stop = max(low of the 15 minutes before launch, 1.0× ATR, 0.6% of price).
If develop n < 40 on an id, SHELVE with the count — do not invent filters to fatten it.

Report harvestable captured / bucket harvestable from A35 if cheap; MFE-capture; reached_1R; peak/mean concurrent; daily-close DD and intraday trough.

## COMBINED

A33 `B|conj|atr1559|lock` reprint + best develop-not-red id this file (else A31 flush control). Honesty line.

## Outputs

`reports/arrow36_results.txt`. Append RESEARCH_LOG.md.
Tests: +12% wick closing +6% is not a launch; a 09:40 launch is not in id 0; id 4 never enters before 12:00; long only.

Commit code + reports. No parquet. No Arrow 37.
