# Build Arrow 8 — wide-stop opening range + selection

Read `docs/SUCCESS.md`, `reports/RESEARCH_LOG.md`, `reports/arrow07_results.txt` first.

Pass = holdout ≥ $200/day **and** develop not red. Do not retry exact dead Arrow 6/7 pairs. Do not treat channel|2R or channel|trail as new work — those overlays did not fire.

Arrow 7 taught: a mid-channel stop is too tight for 2R/trail to exist. This arrow uses an opening-range stop that is **forced into a width band**, then tests manage and **who is allowed to trade**.

Same Tracks A and B, repaired engine, 42/22, no 12:00–16:00 pull, no 11th book.

## New entry: `orb_wide` (free of 10d trend)

- Opening range = 09:30–09:44 high/low.
- Width `W = (high-low)/mid`. Require `0.010 <= W <= 0.040` (1%–4% of price). Outside the band: no trade. That is the point — skip pennies and skip chaos.
- After 09:45, first tradeable close beyond that range, in that direction.
- Stop = the other side of the opening range (so stop distance is the range itself; 2R is reachable).
- One signal per name per session.

## Second entry: `three_day_hl` (structure from the warmup tape)

- Look at the last 3 **prior** sessions' morning (07:30–12:00) lows and highs already in `stats`.
- Up: three rising lows (`L1 < L2 < L3`) and prior close ≥ L3. Enter long first tradeable 09:30. Stop = L3 (yesterday's morning low) or 1% below entry, whichever is **closer** to entry but still ≥ 0.4% of price. If the stop would be tighter than 0.4%, skip.
- Down: three falling highs, symmetric.
- Skip if the pattern is mixed. No 10d-EOD-trend tether (this *is* the structure).

## Six experiments only

| id | entry | extra |
|---|---|---|
| 1 | orb_wide | baseline flatten 11:59 |
| 2 | orb_wide | 2R target, else 11:59 |
| 3 | orb_wide | trail after +1R (same trail as Arrow 7) |
| 4 | orb_wide | **breadth**: at signal time, only take the trade if the name's side agrees with the sign of the **median** 09:30→signal return of eligible names that session |
| 5 | orb_wide | **cost gate**: skip if estimated round-trip cost at entry (`cost_per_share(entry)+cost_per_share(stop)`) > 0.25 × stop_distance |
| 6 | three_day_hl | 2R target + flatten 11:59; rth_open fill |

Reuse book flags from Arrow 7 (`take_2r`, `trail_after_1r`). Do not add scale-outs, ML, or a seventh id.

## Outputs

- `reports/arrow08_results.txt` — two-sided pass rule; table track × id × develop/holdout $/day, n, hit, avgR, maxDD. Also count how many orb_wide candidates died in the width band vs fired.
- Append `reports/RESEARCH_LOG.md`.
- Tests: orb_wide silent if W < 1% or W > 4%; 2R target = 2× opening-range height; breadth rejects a long when book median is negative; three_day_hl silent on mixed lows.

Commit code + reports. No parquet. No Arrow 9.
