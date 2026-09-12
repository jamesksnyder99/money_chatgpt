# Build Arrow 7 — same population, new manage/exit (and one new entry)

Read `docs/SUCCESS.md`, `reports/RESEARCH_LOG.md`, `reports/arrow06_results.txt` first.

Do **not** retry exact (track, rule, stance) pairs already logged as dead. Do not promote develop-red / holdout-green. Pass = holdout ≥ $200/day **and** develop not red.

The unused frontier on this tape is mostly **management and exit**. Entries 3–6 all flattened at 11:59 off a fixed stop. This arrow freezes two old chassis plus **one new entry**, and varies only manage/exit / book size.

Same field: Track A ($10–$30, ≥ $5M) and Track B ($10–$50, 400/day cap file). Same repaired engine (Trade.risk avgR, RTH VWAP, scored queue, next-open fills and next-open stops). 42/22. Warmup = features only. Parallelize. No 12:00–16:00 pull. No 11th system.

## Chassis (entries)

1. **channel_position** — same as Arrow 6 with-trend version (skip flat; stop at channel mid).
2. **yday_level_break** — Arrow 6 **free** version (side from the break, not from 10d trend).
3. **failed_yday_break** (new). First RTH close beyond prior session high (low), then a later RTH close **back inside** that level before 11:00. Enter the **reversal** (fade the failed break). Stop = the failed extreme (session high after the break for a short). No 10d-trend tether.

## Manage / exit (frozen; only these)

Label each experiment `entry|manage`.

| id | entry | manage |
|---|---|---|
| 1 | failed_yday_break | baseline: structure stop, flatten 11:59 |
| 2 | failed_yday_break | **2R**: target = entry ± 2 × (entry−stop), else 11:59 |
| 3 | failed_yday_break | **time_box**: flatten at first tradeable open ≥ 10:45 |
| 4 | channel_position | **2R** as above |
| 5 | channel_position | **trail**: after close ≥ +1R, stop to entry; then trail 0.5% from favorable extreme; 11:59 |
| 6 | yday_level_break | **tight_2R**: max **2** positions and **4** entries/session (not 5/10); 2R target |

Implement trail and 2R in the book so stops/targets still trigger on bar H/L and fill next open. Do not invent scale-outs or extra indicators.

## Outputs

- `reports/arrow07_results.txt` — verdict using the two-sided pass rule. Table track × id × develop/holdout $/day, trades, hit, avgR (actual risk), maxDD.
- Append `reports/RESEARCH_LOG.md`.
- Tests: failed_yday_break does not fire on a clean un-failed break; 2R target distance is 2× stop distance; tight book never exceeds 2 concurrent positions.

Commit code + reports. No parquet. No Arrow 8.
