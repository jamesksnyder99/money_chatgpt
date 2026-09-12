# Build Arrow 10 — hot cell, 15m EMA trend, asymmetric long vs short

Read `docs/SUCCESS.md`, `reports/arrow09_character.txt`, `reports/arrow09_results.txt`, `reports/RESEARCH_LOG.md` first.

Pass = holdout ≥ $200/day **and** develop not red. Same Tracks A/B, repaired engine, 42/22. No 12:00–16:00. Do not rerun Arrow 9's Q5+1–4% books.

James's correction: prior arrows used **one** 10-day EOD recipe and a **symmetric** `side = ±1` engine. That is not good enough. Long and short are different trades. Trend can be finer than C10 vs C1.

## Data constraint (do not invent afternoon 15m bars)

On disk: 07:30–11:59 1m only. Build a 15-minute series by resampling those bars (07:30, 07:45, … 11:45) and **stitch prior sessions** (warmup + earlier study days) so a 21-period EMA exists by 2026-06-01. Never use holdout sessions as history for a develop day; never use same-session 15m bars that have not closed.

## Trend flags (compute these; do not add a fourth)

1. **`ema15`** — on the stitched 15-min close: `ema9` and `ema21` (standard EMA, span 9 and 21). At a decision bar, use the last **completed** 15-min close **before** that bar.
   - Long-stack: `ema9 > ema21`
   - Short-stack: `ema9 < ema21`
2. **`hhhl3`** — last 3 **prior** sessions' morning high/low (07:30–12:00 extremes already in stats).
   - Long-structure: `L1 < L2 < L3` (rising lows)
   - Short-structure: `H1 > H2 > H3` (falling highs)
3. **`eod10`** — keep the existing helper as a **tag only** in the report (how often it agrees with ema15). Do not use it as the entry filter except where the table says so.

## Hot cell (unchanged from character)

`dv_rank ≥ 0.80` and `|gap| ≥ 0.02` and 15-min OR width (09:30–09:44)/mid `> 0.04`.

## 5-min ORBR + retest

Range = 09:30–09:34. Range/mid ≥ 0.004. Break = first close beyond the range after 09:35. Retest = later bar touches the broken level from the outside and does not close back through the far side. Signal on retest close. Stop = far side of the 5-min range. No retest by 11:00 → no trade.

## Six experiments — long books and short books are **not** mirrors

A long id may only open `side = +1`. A short id may only open `side = -1`. Do not generate the opposite side from the same predicate.

| id | side | population | entry | required stance | manage |
|---|---|---|---|---|---|
| 1 | **long** | hot cell **and** gap **up** | 15-min OR **upside** break after 09:45 | `ema15` long-stack | flatten 11:59 |
| 2 | **long** | hot cell and gap up | 15-min OR upside break | `ema15` long-stack **and** `hhhl3` rising lows | 2R, else 11:59 |
| 3 | **long** | dv_rank ≥ 0.80 | 5-min ORBR + retest **of the high** | `ema15` long-stack | flatten 11:59 |
| 4 | **short** | hot cell **and** gap **down** | 15-min OR **downside** break after 09:45 | `ema15` short-stack | flatten 11:59 |
| 5 | **short** | hot cell and gap down | 15-min OR downside break | `ema15` short-stack **and** `hhhl3` falling highs | 2R, else 11:59 |
| 6 | **short** | dv_rank ≥ 0.80 | 5-min ORBR + retest **of the low** | `ema15` short-stack | flatten 11:59 |

Why they differ: longs require a **gap up** into the hot cell (or a high-retest) plus a rising 15m stack. Shorts require a **gap down** plus a falling stack. Shorts do **not** use rising-low logic. Longs do **not** use falling-high logic. No 11:00 flatten. No 7th id.

## Outputs

- `reports/arrow10_results.txt` — two-sided pass; table **by id and side**; hot-cell counts; how often `ema15` agrees with `eod10` on develop (descriptive, not a filter except as tabled).
- Append `reports/RESEARCH_LOG.md`.
- Tests: 15m EMA uses only completed bars; long id emits no shorts; 5-min ORBR silent with no retest; hot-cell rejects 3% OR; hhhl3 rising lows do not arm a short id.

Commit code + reports. No parquet. No Arrow 11.
