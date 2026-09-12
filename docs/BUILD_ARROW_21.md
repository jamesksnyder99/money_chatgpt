# Build Arrow 21 — iterate the rocket book after Arrow 20's washout

Read `reports/arrow20_results.txt`, `reports/arrow19_survey.txt`, `docs/SUCCESS.md`.

Pass = holdout ≥ $200/day **and** develop not red. `data/full/` only. Long ids 1–5. Id 6 is a **short contrast** on the same names. cap8 except id 5. $200/idea. Leak-fixed engine. Flatten 11:59 unless noted. Do not rerun Arrow 20's strong5 / newhigh / flat1559 (those were the wreck).

Arrow 20 taught: the 09:29 hot gate is real (~12 names/day develop, ~22 holdout — August was a cluster). Buying the 09:30 open of +3–15% names lost. Chasing a strong 5-min or a new high lost more. Afternoon flatten made it worse.

## Shared hot gate (09:29) unless an id tightens it

`prior_close` [$1, $20], `pre_dv ≥ $250k`, `pre_dv_rel ≥ 3`, `ext_0929` in **[0.03, 0.15)**. Same definitions as Arrow 20.

## Six experiments

| id | side | idea |
|---|---|---|
| 1 | long | **Pullback:** after 09:30, first tradeable bar that tags the 09:29 last_px **or** RTH VWAP from below, then **closes back above** that level. Stop = that bar's low. Skip if stop distance < 0.4% |
| 2 | long | 09:30 open **only if** 09:30 open / 09:29 last_px − 1 ≤ **+1%** (no extra gap-and-chase). Stop = 09:29 low |
| 3 | long | 09:30 open, hot gate tightened to ext_0929 in **[0.03, 0.08)** |
| 4 | long | 09:30 open, `pre_dv ≥ $1,000,000` (thicker book) |
| 5 | long | id 1 pullback, **max_positions=3** (do not sit eight correlated names on a 60-hot day) |
| 6 | **short** | same hot gate, short the 09:30 open, stop = 09:29 high. Contrast only: is the edge fade? |

No 7th. Report hot name-days/session again. Dispersion if summarize has it.

## Outputs

`reports/arrow21_results.txt`. Append RESEARCH_LOG.md. Tests: id 1 silent if price never tags 09:29 px or VWAP; id 2 rejects a +2% 09:30 gap vs 09:29; id 6 emits only shorts; id 5 never exceeds 3 concurrent on a 10-name fixture.

Commit code + reports. No parquet. No Arrow 22.
