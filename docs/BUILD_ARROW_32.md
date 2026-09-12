# Build Arrow 32 — B-short: first full conjunction, trail rings, unarmed-red cut

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow31_results.txt`, `docs/BUILD_ARROW_31.md`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

A1–A5 remain on. `last_entry_at` = 11:59. Flatten 15:59 on trail rows. SSR (Short Sale Restriction) policy = uptick10. Borrow proxy on. $200/idea. cap8. data/full/. No flush rings. No $500/idea. No virgin pull. No cell-buy.

Acronyms on first use: EMA = exponential moving average; ATR = Average True Range; MFE = maximum favorable excursion; RVOL = relative volume; IWM = iShares Russell 2000 ETF.

**Granularity:** this arrow isolates conjunction and exit on the **frozen repaired leader** (five-minute close below EMA9). Do not change the door to one-minute here. Finest-tape law applies to new doors after this arrow.

## Must-ship before the six ids (small, not a seventh engine)

**Unresolved flatten.** Do not book an unresolved position at `exit_px = entry_px`, `exit_ts = entry_ts`, pnl = −costs. Policy: if a later tradeable print exists, fill there and tag `unresolved_late`. If none exists through 15:59, mark at the last tradeable **close**, tag `unresolved`, keep the real timestamps. Update or replace `test_flatten_zero_volume_1159_uses_1158` so the suite is green. `pytest` must pass.

**RVOL priors.** Print the share of candidate windows with <5 prior exchange sessions; skip those names (original sufficiency rule).

**Holdout n drift (diagnostic row, not a champion).** One extra print: same lock trail on the **full tape** but eligibility clipped to Lab-A style prior_close [$1,$30] (or the A27 Track-B rule if that file still exists) so we can see whether the 94 vs 75 holdout gap is the pool, not the stitch. Label `drift_elig`. Do not pick it on holdout.

## Ids (six, short only)

| id | what |
|---|---|
| 0 | **control** — exact A31 `B\|uptick10\|atr1559\|lock`. Must reprint develop/holdout n within ±10% of 216 / 94 |
| 1 | **conjunction** — same population and gap/OR gates; scan completed 5-minute bars after 09:45 until **both** close < EMA9 **and** EMA9 < EMA21 at the same `bar_end`. One entry per name-day. No re-entry after a stop. Ledger: first primitive time, veto reason, first full-conjunction time |
| 2 | control trail **0.75× ATR** after +1R |
| 3 | control trail **1.5× ATR** after +1R |
| 4 | control trail starts at **+0.5R** (1.0× ATR) |
| 5 | control + **unarmed-red 20 min**: if 20 minutes after fill the trade is still not +1R and marked PnL is negative after estimated round-trip cost, exit next event. Do not flatten winners. Do not change the trail |

No 7th strategy. Locked entry cohort for 2–5 (same admits as id 0). Id 1 may add names; report incremental n and whether they displace cap8 seats.

Stat block: $/day, hit, avgR, PF, se, t, CI, daily-close DD **and** intraday peak-to-trough, peak/mean concurrent, MFE-capture, IWM alpha (skip=0).

## COMBINED

Best develop-not-red B id this file + `flush|max6|repaired` daily series from A31 (do not rescore flush). Honesty line.

## Outputs

`reports/arrow32_results.txt`. Append RESEARCH_LOG.md.
Tests: id 0 reprints A31 lock n; id 1 fixture — 09:50 below EMA9 but long regime, 10:05 both true → only conjunction emits 10:05; id 5 silent on a trade already +1R at minute 15; ids 2–3 trail never loosens; A3 last_entry_at blocks a 13:00 signal; unresolved flatten test green.

Commit code + reports. No parquet. No Arrow 33.
