# Build Arrow 12 — exits and one tight ring on B/short_hot|or25

Read `docs/SUCCESS.md`, `reports/arrow11_results.txt`, `reports/RESEARCH_LOG.md` first.

Pass = holdout ≥ $200/day **and** develop not red. Same Tracks A and B, repaired engine, 42/22. No 12:00–16:00.

## Kernel

Arrow 11 `B/short_hot|or25`: develop **+$19.36/day**, holdout **+$81.56/day**, 97 / 37 trades, holdout hit 0.622. Recipe: **short only**, `dv_rank ≥ 0.80`, gap-down `≥ 2%`, 15-min OR width `> 2.5%`, `ema15` short-stack, 15-min **downside** break after 09:45, stop = OR high, flatten 11:59.

Control reproduced the Arrow 10 B-short cell. Q4 diluted. Two-close diluted holdout. 5-min ORBR is dead. Do not open those vaults again. Do not mirror into longs. Score Track A with the same ids so we can see if A stays a tax; do not tune on A.

## Six short-only experiments

Every id: `side = -1` only. Population unless noted = kernel (Q5, gap-down ≥ 2%, OR > 2.5%, ema short).

| id | change vs kernel |
|---|---|
| 1 | **control** — exact kernel, flatten 11:59 |
| 2 | **2R** target, else 11:59 |
| 3 | **trail** after +1R (Arrow 7 trail: stop to entry, then 0.5% from favorable extreme) |
| 4 | flatten at first tradeable open ≥ **11:30** (keep the 11:00 hour that holds 46% of extremes, cut the last 30 min) |
| 5 | same entry/exit as control, plus **bearish OR**: 09:44 close in the **lower half** of the 09:30–09:44 range |
| 6 | population ring only: gap-down ≥ **1.5%** (was 2%), keep OR > 2.5% and Q5 and ema short; flatten 11:59 |

Reuse book flags `take_2r`, `trail_after_1r`, `flatten_at`. No 7th id. No VWAP-as-entry rerun (Arrow 11 id 6 already logged).

## Outputs

- `reports/arrow12_results.txt` — two-sided pass; table track × id; `n_vs_control`; verdict must not promote develop-red / holdout-green.
- Append `reports/RESEARCH_LOG.md` with which exit or filter preserved B's two-sided green and whether it approached $200.
- Tests: helpers emit only shorts; bearish-OR rejects a 09:44 close in the top half; flatten_at 11:30 closes a fixture before 11:59; gap 1.5% id accepts −1.6% and rejects −1.0%.

Commit code + reports. No parquet. No Arrow 13.
