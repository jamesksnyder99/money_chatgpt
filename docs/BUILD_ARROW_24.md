# Build Arrow 24 — fly vs fail, harness, then a 100-book grid

Read `reports/arrow19_survey.txt`, `reports/arrow23_results.txt`, `docs/SUCCESS.md`.

Pass = holdout ≥ $200/day **and** develop not red. `data/full/` only. Leak-fixed engine. cap8, $200/idea unless a grid filter says otherwise.

Do **not** rerun 08:00/09:29 buy-the-open of an already-extended name, A21 pullback, strong5, newhigh, fade-the-hot-open, vs_iwm, climax.

James: juxtapose rockets that **fly** against those that **launch and fail**. Then invent from that, not from another handful of cousins. Another author's ten strategies are in the grid. Holdout is not a tuner — lock the spec in this file.

## Part A — classes (develop-only tables; holdout may print as PEEK)

On study name-days with `prior_close` in [$1, $20] and ≥5 prior sessions:

**Confirmed launch:** first 1-min **close** ≥ 1.10 × prior_close whose **next** tradeable bar low ≥ 1.08 × prior_close. (Survey stays high-based; strategies use confirmed.)

**FLY:** confirmed launch AND (max_ext ≥ 0.20 OR (still ≥ +10% at 15:59 AND minutes_launch_to_peak ≥ 60))

**FAIL:** (high tagged +10% but never confirmed) OR (confirmed AND gave_back by 15:59 AND max_ext < 0.15)

At **09:29** and **09:44** (no look-ahead past the stamp) record: ext, running rel vol (04:00→stamp vs prior-10 same window), premarket $ volume, premarket range/mid, gap, 5-min OR width (09:44 only), prior-session was_rocket (confirmed ≥3× if computable), last_px.

Report develop: n FLY / n FAIL / n other; mean and quintiles of each feature for FLY vs FAIL at each stamp; 2×2×2 of the three features with the biggest FLY/FAIL gap; launch hour mix for FLY vs FAIL; one paragraph naming the cell (or "none").

## Part B — harness (must ship, with tests)

1. `stop_distance = max(structure, 1.0 × ATR of last six completed 5-min bars, 0.6% of price)`
2. Cost gate: skip if 2 × cost_per_share(entry) > 0.20 × stop_distance. Count skips.
3. Price floor **prior_close ≥ $3** on strategy ids (survey/character keep $1–20).
4. Ranked fill by explicit `score` (default = running rel vol at signal).
5. `run_rel_vol(symbol, ts)` helper as specified.
6. `halt_windows` = ≥5 consecutive zero-volume RTH minutes after ≥15 minutes with prints.
7. Day-2 flags on eligibility-adjacent table: `was_rocket_prev`, `prev_close_ext`, `prev_gave_back`.
8. Confirmed-launch helper used by every strategy id.

Rescore **flush_hl** and **am_high_pm** once under this harness as controls (same entries as A23, new stops/gates). Label `flush_hl|harness` and `am_high_pm|harness`.

## Part C — 100-book grid

Four **doors** × five **exits** × five **filters** = 100 ids. All use Part B harness. prior_close $3–20. Next-tradeable-open fills. Short doors use borrow proxy.

If Part A names a cell, apply it as an extra population cut on every long door. If it names none, use the door's own gate only.

### Doors

| door | side | trigger |
|---|---|---|
| launch | L | After 09:45, confirmed launch, run_rel_vol at launch ≥ 5, ext_0929 in [−3%, +5%] |
| volfirst | L | After 09:35, first 5-min where run_rel_vol ≥ 8 and bar closes up, ext at stamp in [−2%, +5%] |
| flush | L | A23 flush_hl entry (08:00 hot, ≥2% undercut, 5-min HL + strong close) |
| giveback | S | ext ≥ 15% at 11:00, by 13:00 ≥ 5% off session high, after 13:00 5-min close below 11:00-anchored VWAP, weak close |

### Exits

`flat1159` · `flat1559` · `t15R` (hard +1.5R) · `half1R_trail` (half off at +1R, stop to entry, ATR trail remainder) · `atr_1559` (ATR-floored stop only, flatten 15:59)

### Filters

`base` · `cost` (gate on) · `px5` (prior_close ≥ $5) · `cap3` (max_positions=3) · `nocluster` (skip session if that door's raw signal count > 15)

Id string: `{door}|{exit}|{filter}` e.g. `launch|t15R|px5`.

Also print the two harness controls outside the 100.

## Report `reports/arrow24_results.txt`

1. Part A character + the cell paragraph.
2. Harness-control two-sided rows with the Arrow 23 advanced stat block (n, hit, avgR, medR, p10/p90 R, PF, stop/time %, medMin, $/day, se, t, CI, maxDD, flight mean_ext, reached_1R).
3. 100-grid table: id, side, dev $/day, hold $/day, hold n, hit, avgR, PF, t_hold, reached_1R, >=200. Sort by holdout $/day descending. Flag both-slices-green.
4. Count how many of 100 are both-green; how many beat the matching harness control on develop.
5. One paragraph: did FLY vs FAIL give a cell, and did any **door** family look different from 20–22.

Append RESEARCH_LOG.md.

Tests: confirmed launch rejects a +12% wick that closes +6%; ATR floor widens a 0.2% structure stop; cost gate skips a $2 / 3% stop; halt helper needs 5 dead minutes; grid has 100 ids; shorts only from giveback.

Workers=8, 15-min heartbeat. Commit code + reports. No parquet. No Arrow 25.
