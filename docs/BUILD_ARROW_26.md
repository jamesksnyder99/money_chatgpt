# Build Arrow 26 — acceleration / deceleration on the first both-green flush

Read `reports/arrow25_results.txt`, `docs/SUCCESS.md`.

Pass = holdout ≥ $200/day **and** develop not red. `data/full/`. Harness ON. Long only. $200/idea. Flatten 11:59 unless noted.

Do **not** rerun nocell, after10, giveback, launch-catch, 08:00 open-buy, vs_iwm, climax, the 100-grid.

## Kernel (do not drop)

`flush|max6`: 08:00 hot, FLY cell, prior_close [$5,$20], undercut of 08:00 px in **[2%, 6%]**, 5-min higher-low + strong close, cap8, flat 11:59. Arrow 25: develop **+$11** / holdout **+$117**. Both green. Not $200. Not EV. ~0.6–1.0 trades/day.

Id 1 is that exact book.

## Ten longs

| id | ring |
|---|---|
| 1 | **control** — exact max6 kernel |
| 2 | control + **cap3** |
| 3 | **Range accel into the wash:** the 5-min bar that makes the flush low has range ≥ 1.2× the prior 5-min range |
| 4 | **Decel into the HL:** signal 5-min range ≤ 0.8× the flush-low bar's range (selling dried up) |
| 5 | **Volume accel on reclaim:** signal 5-min volume ≥ 1.3× the flush-low bar's volume |
| 6 | **Slow wash:** minutes from first tag of −2% to the flush low ≥ **15** (not a one-bar crash) |
| 7 | **Two higher lows:** after the flush low, two completed 5-min higher lows before entry; enter on the second strong close |
| 8 | **Open-noise skip:** ignore flushes whose low prints before **09:50** |
| 9 | control, flatten **15:59** only if trade is ≥ +0.5R at 11:59; else flatten 11:59 (conditional hold) |
| 10 | **Loser cut from A25 flights:** skip if signal close_loc ≥ 0.75 but close is still **below** 08:00 last_px (strong candle, no reclaim) |

No 11th. Flight stats on every id. n vs id 1. Which ids beat control on **both** slices; which stay both-green.

## Outputs

`reports/arrow26_results.txt`. Append RESEARCH_LOG.md.
Tests: id 4 silent if signal range is wider than the flush bar; id 6 silent if the −2%→low drop is 5 minutes; id 7 silent after a single HL; id 10 silent when close < 08:00 px; longs only; id 1 still max6.

Commit code + reports. No parquet. No Arrow 27.
