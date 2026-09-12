# Build Arrow 11 — concentric expansion of the only two-sided green cell

Read `docs/SUCCESS.md`, `reports/arrow10_results.txt`, `reports/RESEARCH_LOG.md` first.

Pass = holdout ≥ $200/day **and** develop not red. Same Tracks A and B, repaired engine, 42/22. No 12:00–16:00.

## Kernel (do not lose this)

Arrow 10 `B / short_hot_or15|ema`: develop **+$5.58/day**, holdout **+$21.53/day**. Only book green on both slices. Recipe: short only, hot cell (Q5 × gap-down ≥ 2% × 15-min OR width > 4%), 15-min **downside** break, `ema15` short-stack (9 < 21 on stitched morning 15m), flatten 11:59. n is tiny (58 develop / 16 holdout trades).

Do **not** expand by mirroring that recipe into longs. Do **not** rerun 5-min ORBR+retest. Do **not** stack HH/HL on top of this kernel (that starved n in Arrow 10).

## Goal

More trades **from the same side and idea**, by relaxing **one** population gate or by a **new short entry** that still requires gap-down + short ema. Performance dilution (holdout red, or develop red with a lucky holdout) is a fail for that id, not a reason to keep relaxing.

## Six short-only experiments

Every id emits `side = -1` only.

| id | population (vs kernel) | entry | manage |
|---|---|---|---|
| 1 | **control** — exact kernel on **both** tracks | 15-min OR downside break after 09:45, stop = OR high | 11:59 |
| 2 | Q5, gap-down ≥ **1%** (was 2%), OR width > 4%, ema short | same 15-min down break | 11:59 |
| 3 | Q5, gap-down ≥ 2%, OR width > **2.5%** (was 4%), ema short | same | 11:59 |
| 4 | **Q4+Q5** (`dv_rank ≥ 0.60`), gap-down ≥ 2%, OR > 4%, ema short | same | 11:59 |
| 5 | Q5, gap-down ≥ 1%, ema short, **no OR-width floor** | **new:** first two **consecutive** RTH closes below the 09:30–09:44 low; stop = OR high | 11:59 |
| 6 | Q5, gap-down ≥ 1.5%, ema short, **no OR-width floor** | **new:** first RTH close after 09:45 **below RTH VWAP**; stop = max(OR high, VWAP at signal) | 11:59 |

Report trade counts vs control so we can see which ring added names and whether $/day survived.

Reuse `ema15` and RTH VWAP from the repaired engine. No 7th id. No long ids in this arrow.

## Outputs

- `reports/arrow11_results.txt` — two-sided pass; table track × id × develop/holdout $/day, n, hit, avgR, maxDD; a line `n_vs_control` per id.
- Append `reports/RESEARCH_LOG.md` naming the kernel and which ring diluted it.
- Tests: every helper returns only `side == -1`; id-2 population accepts 1.2% down gap and rejects 0.5%; two-close entry silent after a single close below the OR low; VWAP short silent if close is still above VWAP.

Commit code + reports. No parquet. No Arrow 12.
