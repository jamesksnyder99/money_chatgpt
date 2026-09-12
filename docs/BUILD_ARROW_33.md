# Build Arrow 33 — hygiene, cap/rank on the standing short, depth rollup

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow32_results.txt`, `reports/arrow31_results.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

Frozen leader: `B|conj|atr1559|lock` from A32 (conjunction door, 1.0× ATR trail after +1R, last_entry_at=11:59, flatten 15:59). Do **not** promote A32 `atr150` (holdout-shaped). A1–A5 on. SSR (Short Sale Restriction) = uptick10. $200/idea unless an id says otherwise. data/full/. No virgin. No cell-buy. No $500/idea grid.

Acronyms: EMA = exponential moving average; ATR = Average True Range; MFE = maximum favorable excursion; RVOL = relative volume; IWM = iShares Russell 2000 ETF.

Granularity: frozen five-minute door. Finest-tape law applies to new doors after this family.

## Must-ship hygiene

**Unresolved flatten.** If a later tradeable print exists, fill there (`unresolved_late`). Else mark last tradeable **close**, tag `unresolved`, real timestamps. Never `exit_px = entry_px`. Update `test_flatten_zero_volume_1159_uses_1158` (or equivalent). `pytest` green.

**RVOL.** Skip candidates with <5 prior exchange sessions. Print the skip share.

**Drift diagnostic.** One row `drift_elig`: same leader on full tape with eligibility clipped toward Lab-A / A27 prior_close band so we can see whether holdout n 94 vs 75 is the pool. Not a champion.

## Ids

| id | what |
|---|---|
| 0 | **control** — exact A32 conjunction + 1.0× ATR lock. Reprint n within ±10% of 244 / 98 |
| 1 | control, **cap12** |
| 2 | control, **cap16** |
| 3 | cap8, rank by **gap size** (largest down-gap first) |
| 4 | cap8, rank by **RVOL at 09:29** |
| 5 | cap8, rank by **opening-range width** |

Locked last_entry_at=11:59. Peak/mean concurrent, days at cap, joint peak risk vs A31 flush series.

## Depth rollup (develop-only, no new champion)

Field: Track-B name-days with gap ≤ −1.5% and OR width > 2.5%.
Depth = how far below the 09:45 price the name went after a 1R haircut, regular trading hours only.
Coverage: leader name-days / field; MFE-from-entry points / field depth points; depth by hour of the low and by SSR flag.
One paragraph: is the leftover lever the door or the exit?

## COMBINED

Best develop-not-red B id + A31 `flush|max6|repaired`. Honesty line.

## Outputs

`reports/arrow33_results.txt`. Append RESEARCH_LOG.md.
Tests: unresolved policy; pytest green; id 1 admits a 9th name on a 9-signal fixture; id 3 fills larger gaps first; id 0 reprints A32 conj n.

Commit code + reports. No parquet. No Arrow 34.
