# Build Arrow 38 — premarket-high reclaim

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow35_score.txt`, `reports/arrow37_results.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

Do not rerun 36 birth or 37 noon hold. No cell. No score gate. No $500/idea. No virgin. Do not rescore the B-short.

Acronyms: ATR = Average True Range; RVOL = relative volume; MFE = maximum favorable excursion.

Granularity: one-minute tape. Reclaim = first **one-minute close** above the premarket high (max high 04:00–09:29), not a five-minute close.

## Population

prior_close [$3, $20], ≥5 prior sessions, data/full/.
Confirmed launch **before 09:30**. 09:30 open **below** the premarket high. By 10:00 the name has traded **≥ 3%** below that open. Cap8, $200/idea, harness floor. Long only.

**No RVOL floor** on the control (A35 quintiles were not monotone). Id 3 is a RVOL≥3 sensitivity only.

## Ids

| id | door | exit |
|---|---|---|
| 0 | after **10:00**, first 1-min close above the premarket high. Stop = low of prior 30 minutes, ATR / 0.6% floor | flatten 11:59 |
| 1 | same door | +1R then 1.0× ATR trail, flatten 15:59 |
| 2 | same door, dip only **≥ 2%** below the open (looser wash) | flatten 11:59 |
| 3 | id 0 + run_rel_vol at 10:00 ≥ 3 | flatten 11:59 |

If develop n < 40, SHELVE with the count.

Silent if the name never dipped the required % below the open. Silent on a reclaim of the *regular-session* high that is not the premarket high.

## COMBINED

A33 `B|conj|atr1559|lock` + best develop-not-red id this file (else A31 flush control). Honesty line.

## Outputs

`reports/arrow38_results.txt`. Append RESEARCH_LOG.md.
Tests: silent if never 3% under the open; silent if reclaim is RTH high only; a 09:50 close above pm high is not id 0 (before 10:00); long only.

Commit code + reports. No parquet. No Arrow 39.
