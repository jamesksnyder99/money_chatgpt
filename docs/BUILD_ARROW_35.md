# Build Arrow 35 — harvestable altitude + point-in-time score (develop-only)

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow30_altitude.txt`, `reports/arrow34_results.txt`.

No new engine. No $200 verdict on a book. No B-short rescore. No flush rings. No $500/idea. No virgin. No cell-buy.

Acronyms: ATR = Average True Range; RVOL = relative volume; MAE = maximum adverse excursion.

Granularity: compute on the finest tape we have (one-minute). Do not roll up to five-minute to save work.

## Harvestable altitude (R7 full field)

Rocket-day = confirmed launch (1-min close ≥ 1.10× prior_close and next tradeable low ≥ 1.08× prior_close), prior_close [$1,$20], ≥5 prior sessions.

`harvestable` = max(0, max_high after first **fillable** bar ÷ price at that bar − 1 − r1).
Fillable bar: launch_confirm_ts + 5 minutes for regular-trading-hours launches; **09:45** for launches before 09:30. Only bars with volume ≥ 2,000 shares. r1 = 1.0× ATR of last six completed 5-min bars at the fillable stamp, floored at 0.6% of price.

Report develop and holdout **separately**. Holdout tables = PEEK, not a tuner.
By launch hour, prior-close band ($1–3, $3–5, $5–10, $10–20), and RVOL quintile at launch.
Also the ≥3× survey field as a side table if cheap.

Paragraph: how much of Arrow 30's gross mountain is actually sit-able by a next-open engine.

## Point-in-time score (develop-only features)

Universe: eligible name-days, prior_close $3–20, at two stamps: **09:44** and (for RTH launches) **launch_confirm + 5 min**.

Features at the stamp, no look-ahead: ext vs prior close, OR width if known, pre_dv_0929, run_rel_vol, gap, price, prior DV, was_rocket_prev, prev_close_ext, minutes since launch (0 if not launched), distance from session high, above/below RTH VWAP if RTH, halt seen, launch hour.

Score = rank-average of the **five** develop features with largest Spearman correlation to harvestable altitude. Freeze those five. No fitted model.

Report harvestable altitude and MAE-to-OR-low (or to fillable-stamp low) by score **decile over ALL members**. FLY / FAIL / other share per decile (labels may use the future — they are description, not the score).
Holdout deciles PEEK only.

**Gate for Arrow 36:** top develop decile median harvestable > 2× r1 **and** MAE ≤ 1 ATR on ≥ 50% of members. Print GATE=YES or NO. If NO, 36 runs ungated by hour bucket.

## COMBINED

Reprint A33 B lock + A31 flush control daily totals. Do not replay. Honesty: not EV.

## Outputs

`reports/arrow35_score.txt`. Append RESEARCH_LOG.md.
Tests: 04:05 launch peaking 04:20 has harvestable measured from 09:45; a +12% wick closing +6% is not a confirmed launch; decile table n sums to n_all.

Commit code + report. No parquet. No Arrow 36.
