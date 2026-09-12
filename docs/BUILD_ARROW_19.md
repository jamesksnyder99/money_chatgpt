# Build Arrow 19 — survey on data/full (04:00–16:00)

Read `docs/BUILD_ARROW_ROCKETS.md`, `reports/rockets_scan.txt`, `reports/tape17_ingest.txt`.

Diagnostic only. No fills. No $200 verdict. Do not touch `data/bars`. Do not rescore the kernel.

Use `data/full/eligibility.parquet` and `data/full/bars`. Study sessions 2026-06-01..2026-08-31; warmup is history for medians only. Split develop / holdout in the report the same dates as before.

## A — Rockets on the full clock

Same definitions as the stub scan, now 04:00–15:59:

- `prior_close` in [$1, $20]
- Rocket: tradeable **high** ≥ 1.10 × prior_close
- Rel vol: today's 04:00–15:59 volume / median of that window over prior 10 sessions; skip if <5 priors
- Report ≥+10/15/20/50%, ∩ ≥3× and ≥5×
- `launch_ts` = first bar whose high tags +10%
- Launch hour 04..15; buckets: pre-07:30, 07:30–09:29, 09:30–09:44, 09:45–15:59
- Median/p90 max_ext, minutes_to_peak, ext at 09:30, ext at 15:59
- Fraction still ≥+10% at 09:30 and at 15:59; gave_back by 15:59 (end_ext < 0.5×max_ext)
- How many ≥3× rockets pass Track A / Track B gates (same gates as stub scan)

## B — Already-moving snapshots

Point-in-time, no look-ahead past the stamp.

At **08:00** and at **09:29** (last tradeable bar ≤ that clock), for each eligible name-day with prior_close in [$1, $50]:

- `gap_so_far` = last_px / prior_close − 1
- `already_up10` / `already_down10`
- `pre_dv_so_far` = dollar volume from 04:00 through that stamp (typical×volume)
- `pre_dv_rel` = that / median of the same-window dollar volume over prior 10 sessions (skip if <5)
- Flag `mover` if `|gap_so_far| ≥ 0.05` **or** `pre_dv_rel ≥ 3` **or** `already_up10` **or** `already_down10`

Report counts of movers at 08:00 and 09:29, overlap with §A 3× rockets, how many movers have prior_close <$10 vs $10–50, how many would be Track B eligible that day.

## Outputs

`reports/arrow19_survey.txt` — study-wide + develop + holdout. One paragraph: did 04:00 move the launch clock vs the stub scan; is "already moving" at 09:29 mostly the rocket set or a wider field.

Workers=8, 15-min heartbeat if long. Tests: +10% high at 05:12 counts as launch hour 05; 08:00 snapshot ignores a 09:00 print; rel vol with 2 priors skipped.

Commit code + report. No parquet. No Arrow 20.
