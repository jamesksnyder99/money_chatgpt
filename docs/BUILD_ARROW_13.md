# Build Arrow 13 — combine the paying short; hunt longs that are not a mirror

Read `docs/SUCCESS.md`, `reports/arrow12_results.txt`, `reports/RESEARCH_LOG.md` first.

Pass = holdout ≥ $200/day **and** develop not red. Same Tracks A and B, repaired engine, 42/22. No 12:00–16:00.

## What is live

Track B short, Q5, gap-down, OR width > 2.5%, ema15 short-stack, 15-min downside break, hold to 11:59. Arrow 12: control +$19/+$82; **2R +$28/+$80**; **gap15 +$40/+$73**. Flatten 11:30 hurt. Bearish-OR starved develop. Track A develop stayed red.

Do not rerun Q4, 5-min ORBR, two-close, 11:30 flatten, or a long that is `side = +1` on the short predicate.

## Six experiments

**Short ids (1–3)** — `side = -1` only. Base pop: `dv_rank ≥ 0.80`, gap-down `≥ 1.5%`, OR width `> 2.5%`, `ema15` short-stack.

| id | side | idea |
|---|---|---|
| 1 | short | **control** = gap15 kernel, 15-min down break, flatten 11:59 |
| 2 | short | same pop and entry, **2R** (combine the two Arrow 12 helps) |
| 3 | short | same pop, **new entry**: after 09:45, first **completed 5-min close below ema9** of the stitched 15m stack (not an OR-low break). Stop = max(OR high, that 5-min high). Flatten 11:59 |

**Long ids (4–6)** — `side = +1` only. None of these is the short recipe flipped.

| id | side | idea |
|---|---|---|
| 4 | long | Q5, gap-**up** ≥ 1.5%, `ema15` **long**-stack. **Pullback:** after 09:45 a tradeable low touches OR mid or last completed ema9, then that bar **closes back above** that level. Stop = that low. Flatten 11:59 |
| 5 | long | Q5, gap-up ≥ 1.5%, ema long-stack. **VWAP reclaim:** at least one RTH close below RTH VWAP, then first later close back above it. Stop = that VWAP. Flatten 11:59. This is not Arrow 3's whole-book vwap_reclaim |
| 6 | long | Q5, **quiet open** (`|gap| < 0.5%`), ema long-stack, OR width in `[1%, 4%]`, 15-min **upside** break. Trend-without-a-gap. Stop = OR low. Flatten 11:59 |

No 7th id. Report n vs short control for ids 1–3. Score A and B separately; do not average them.

## Outputs

- `reports/arrow13_results.txt` — two-sided pass; table track × id × side; n_vs_control on shorts.
- Append `reports/RESEARCH_LOG.md`.
- Tests: short helpers emit no longs; long helpers emit no shorts; id 3 silent if 5-min closes stay above ema9; id 4 silent if price never tags OR mid/ema9; id 5 silent if price never loses VWAP; id 6 silent on a 2% gap.

Commit code + reports. No parquet. No Arrow 14.
