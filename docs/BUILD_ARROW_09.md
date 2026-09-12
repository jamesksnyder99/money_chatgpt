# Build Arrow 9 — where movement lives, then trade that population

Read `docs/SUCCESS.md`, `reports/RESEARCH_LOG.md`, `reports/arrow08_results.txt` first.

Pass = holdout ≥ $200/day **and** develop not red. Same Tracks A and B, repaired engine, 42/22. No 12:00–16:00. No Arrow 8 reruns (cost_gate, channel trail).

This arrow is not another named candlestick. It is: **measure where the dollars of range actually print (develop only), write that down, then trade a frozen subset that those tables point at.**

Holdout bars may not be used to choose buckets, thresholds, or which experiment to emphasize. If you print a holdout characterization table at all, label it `PEEK — not for selection`.

## Phase 1 — characterize (develop sessions only)

For every eligible name-day on develop, compute:

- `or_w` = 09:30–09:44 range / mid
- `or_dollar` = (09:30–09:44 high−low) × first 15-min volume × mid / max(volume,1) approximated as range × prior_dollar_volume / prior_close if 15-min volume missing; prefer actual 15-min dollar volume = sum(typical × volume) over those bars
- `post_or_range` = high−low from 09:45 through 11:59, as % of 09:44 mid
- `post_or_exc` = signed (11:59 close − 09:44 close) / 09:44 close
- `gap` = (09:30 open / prior_close) − 1
- `dv_rank` = percentile of prior_dollar_volume among that session's eligible names (0–1)
- `trend` = up/down/flat from existing 10-session EOD helper
- `max_ext_clock` = timestamp of the RTH bar that prints the session high if close>open else session low (where the extreme landed)

Write `reports/arrow09_character.txt` (develop only) with:

1. Mean `post_or_range` by `dv_rank` quintile (Q1=smallest … Q5=largest).
2. Mean `post_or_range` by `|gap|` buckets: <0.5%, 0.5–2%, ≥2%.
3. Mean `post_or_range` by `or_w` buckets: <1%, 1–4%, >4%.
4. Mean `post_or_range` by trend (up/down/flat).
5. Count of session extremes by clock hour (09, 10, 11).
6. One paragraph: which intersection of Q5 × gap × or_w actually carries the movement.

Do not look at holdout to write that paragraph.

## Phase 2 — frozen trades (thresholds declared here, not from peeking holdout)

Hypothesis from prior arrows + Phase 1's *intended* question: movement after 09:44 concentrates in **liquid names with a real opening range and/or a real gap**. Trade only that.

| id | population (point-in-time) | entry | manage |
|---|---|---|---|
| 1 | that session's **dv_rank ≥ 0.80** and `or_w` in [0.01, 0.04] | `orb_wide` as Arrow 8 | flatten 11:59 |
| 2 | same as 1 | `orb_wide` | **2R** |
| 3 | dv_rank ≥ 0.80 and `|gap| ≥ 0.02` | 09:31 **with the gap** (continuation); stop = 09:30 low (high if short) if that stop is ≥ 0.4% of price, else skip | 2R, else 11:59 |
| 4 | dv_rank ≥ 0.80 and `or_w` in [0.01, 0.04] | `orb_wide` only if break direction matches **gap sign** when `|gap|≥1%`, else skip | trail after 1R |
| 5 | dv_rank ≥ 0.80 | `three_day_hl` if it fires | 2R |
| 6 | same pop as 1 | `orb_wide` | flatten **11:00** |

Max 5 positions / 10 entries except these already sit in a small pop. Same costs. No 7th id. No ML.

## Outputs

- `reports/arrow09_character.txt` — Phase 1, develop only.
- `reports/arrow09_results.txt` — Phase 2 table track × id × develop/holdout $/day, n, hit, avgR, maxDD; two-sided pass rule.
- Append `reports/RESEARCH_LOG.md` with the one-paragraph movement finding and what died.
- Tests: dv_rank ≥ 0.80 keeps only the top fifth of a fake session; Phase 2 id 3 does not fade the gap; characterization helpers ignore holdout dates if passed a develop list.

Commit code + reports. No parquet. No Arrow 10.
