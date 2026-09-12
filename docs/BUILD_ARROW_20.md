# Build Arrow 20 — first swing at rocket engines (data/full)

Read `reports/arrow19_survey.txt`, `docs/SUCCESS.md`, `reports/arrow18_results.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Use **`data/full/`** only. Do not touch `data/bars`. Do not rescore the B-short.

This is the first long book aimed at the 3× rocket shape. It is **not** the 24% already-moving pile. Decision time is **09:29** (last tradeable bar ≤ 09:29). No 04:00 entries. Fills = next tradeable open. cap8, $200/idea, leak-fixed flatten.

Holdout is a first look at *this* recipe, not a tuner from Arrows 10–16. Do not add ids after seeing holdout.

## Population (point-in-time at 09:29)

Eligible from `data/full/eligibility.parquet`.

- `prior_close` in **[$1, $20]**
- `pre_dv` = dollar volume 04:00 through 09:29 (typical × volume)
- `pre_dv_rel` = pre_dv / median of that same window over prior 10 sessions (skip name-day if <5 priors)
- `ext_0929` = 09:29 last_px / prior_close − 1
- `pre_dv ≥ $250,000` (liquidity floor — not 3× full-day vol)
- **Hot:** `pre_dv_rel ≥ 3` **and** `ext_0929 ≥ 0.03` **and** `ext_0929 < 0.15`

The last cut is deliberate: already +3% with real premarket dollars, **not already +15%** (chasing the 04:00 spike that 19 said is often done by the bell).

Long only. `side = +1`.

## Six experiments

| id | entry | stop | flatten |
|---|---|---|---|
| 1 | 09:30 first tradeable open (gap-and-go) | 09:29 session low, skip if stop ≥ entry or stop distance < 0.4% | 11:59 |
| 2 | same entry/stop | same | **15:59** |
| 3 | after 09:30, first 5-min **strong close** (close_loc ≥ 0.75) that holds ≥ 09:29 last_px | that 5-min low | 11:59 |
| 4 | after 09:45, first 5-min close making a **new session high** | that 5-min low | 11:59 |
| 5 | id 1 population **plus** ext_0929 still < 0.10 (less extended) | 09:29 low | 11:59 |
| 6 | id 1 entry | 09:29 low | 11:59, **2R** |

No 7th. No shorts. No Track B cap. Report n, $/day, hit, avgR, maxDD, std/se/t/CI if `summarize` already has them.

## Outputs

`reports/arrow20_results.txt` — two-sided pass; how many name-days pass the hot gate per session (develop vs holdout); reminder that this is a first swing, not EV.

Append `reports/RESEARCH_LOG.md`.

Tests: hot gate rejects ext_0929=0.01 and ext_0929=0.20; rejects pre_dv $100k; id 1 emits no shorts; 15:59 flatten exists on a fixture that runs past noon.

Commit code + reports. No parquet. No Arrow 21.
