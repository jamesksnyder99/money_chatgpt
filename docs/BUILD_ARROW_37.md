# Build Arrow 37 — noon hold / afternoon continuation

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow36_results.txt`, `reports/arrow35_score.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

Do **not** rerun Arrow 36 afternoon birth (12:00–15:00 confirmed launch). That door is closed. No cell. No score gate. No $500/idea. No virgin. Do not rescore the B-short.

Acronyms: ATR = Average True Range; RVOL = relative volume; MFE = maximum favorable excursion.

Granularity: one-minute tape. Decisions at 12:00 use the completed 11:59 bar.

## Population

prior_close [$3, $20], ≥5 prior sessions, data/full/. Cap8, $200/idea, harness floor on. Long only.

## Ids

| id | door | exit |
|---|---|---|
| 0 | **noon hold tight:** at 12:00 ext ≥ +10% vs prior close **and** ext at 11:00 ≥ +8%; last 30 minutes range ≤ 4%; run_rel_vol at 12:00 ≥ 2. Enter 12:01 open. Stop = min of 11:00–11:59 lows, ATR/0.6% floor | +1R then 1.0× ATR trail, flatten 15:59 |
| 1 | same door, flatten **13:30** (trail still arms) |
| 2 | **noon hold loose:** at 12:00 ext ≥ +8% and ext at 11:00 ≥ +5%; no range cap. Same stop | trail, flatten 15:59 |
| 3 | **re-launch:** launched before 12:00, pulled back ≥ 5% from session high, then a 1-min close back above that high after 12:00. Stop = pullback low, ATR floor | trail, flatten 15:59 |
| 4 | **power hour:** at 14:30 ext ≥ +8% since 12:00, within 1.5% of session high, prior 30-min range ≤ 3%. Enter 14:31. Stop = 13:30–14:30 low, ATR floor | flatten 15:59 |

If develop n < 40, SHELVE with the count. Do not add filters to fatten.

Report MFE-capture, reached_1R, peak/mean concurrent, daily-close DD and intraday trough.

## COMBINED

A33 `B|conj|atr1559|lock` + best develop-not-red id this file (else A31 flush control). Honesty line.

## Outputs

`reports/arrow37_results.txt`. Append RESEARCH_LOG.md.
Tests: id 0 silent if 11:00 ext is +2%; id 3 silent if no 5% pullback; id 4 never enters before 14:30; long only.

Commit code + reports. No parquet. No Arrow 38.
