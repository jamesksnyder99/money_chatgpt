# Build Arrow ROCKETS — diagnostic scan, not a trading book

Read `docs/DATA_CONTRACT.md` so you know what is on disk. This is **not** Arrow 16 and **not** a $200 pass/fail book. No fills, no cap8, no shorts.

James wants to know whether a "$1–$20, +10% from prior close, high relative volume" field exists **inside the 07:30–12:00 parquet we already have**. Float is unavailable. Do not pull new days or 12:00–16:00.

## Universe

- File: full eligibility (`eligibility.parquet`), **not** Track A/B caps.
- Sessions: every **study** session 2026-06-01..2026-08-31 (keep July 3 as in the contract). Warmup days are history for relative volume only — do not count warmup name-days as rockets.
- Price: `prior_close` in **[$1, $20]** inclusive.
- Rocket mark: session **high** (07:30–11:59, tradeable bars) ≥ `1.10 * prior_close`. That is "up ~10% or more from prior close" at some print in our window.
- Relative volume: `today_vol / med_vol` where `today_vol` = sum of 1-min volume 07:30–11:59 and `med_vol` = median of that same-window volume over the name's **prior 10 sessions** already on disk (warmup + earlier study). If fewer than 5 prior sessions, skip the name-day (do not invent rel vol).
- Rel-vol bands to report separately: `≥ 3x`, `≥ 5x`, and the intersection rocket ∩ ≥ 3x / rocket ∩ ≥ 5x.

## For each rocket name-day (high ≥ +10% and prior_close in band)

Compute:

- `max_ext` = session_high / prior_close − 1
- `launch_ts` = timestamp of the first tradeable bar whose **high** ≥ 1.10 * prior_close
- `launch_clock` = ET hour of `launch_ts` (07, 08, 09, 10, 11)
- `peak_ts` = timestamp of the bar that prints `session_high`
- `minutes_to_peak` = peak_ts − launch_ts in minutes (≥ 0)
- `end_ext` = 11:59 tradeable close / prior_close − 1 (still flying vs given back)
- `gave_back` = 1 if end_ext < 0.5 * max_ext else 0
- `rel_vol` as above
- `pre_or_rth`: launch_ts before 09:30 vs 09:30–09:44 vs ≥ 09:45

## Report `reports/rockets_scan.txt`

Plain text, study-wide and split develop (through 2026-07-30) / holdout (from 2026-07-31) so we can see if August was different.

Must include:

1. Eligible name-days in $1–$20 with enough history.
2. Count and % with max_ext ≥ 10%, ≥ 15%, ≥ 20%, ≥ 50%.
3. Count of those with rel_vol ≥ 3x and ≥ 5x.
4. Launch-clock histogram (07..11) for rockets with rel_vol ≥ 3x.
5. Pre / first-15 / after-09:45 launch mix for that same set.
6. Median and p90 of max_ext, minutes_to_peak, end_ext.
7. Fraction still ≥ +10% at 11:59; fraction that gave_back.
8. How many of the ≥ 3x rockets would have survived Track A / Track B gates (prior close $10+ and $5M ADV, B's 400 cap that day) — that answers "did our lab tracks delete them."
9. One paragraph: are they in the file, and if so when they launch in *our* window.

No strategy ids. No SUCCESS.md verdict line. Workers=8, 15-min heartbeat if the scan is long.

## Tests

A fixture with prior_close=10, high=11.20 at 10:03, volume 4× median → counted, launch hour 10. A name that only reaches +8% → not a rocket. Rel vol with 2 prior sessions → skipped.

Commit code + `reports/rockets_scan.txt`. No parquet. No Arrow 16.
