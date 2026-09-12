# Build Arrow 29 — FLY cell as population; new rocket radii

Read `docs/SUCCESS.md`, `reports/arrow24_results.txt`, `reports/arrow28_results.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not EV.

Do **not** rerun flush|max6 synonyms (cap3, deep3, after10, rel5, nocell). No $500/idea. No virgin pull. Frozen B-short for COMBINED = `B_uptick10|atr1559` daily series from A28 (do not rescore the short).

## Part A — develop-only, no fills (must ship first)

Cell (develop-locked A24): OR width ≥ 5.1%, pre_dv_0929 ≥ $98k, ext_0944 ≥ 3.4%.
Rows: prior_close $3–20 and $5–20.

From the **09:44 close** (not prior close): ext at 11:59, 13:30, 15:59; MAE to 11:59 vs OR low in ATR units; fraction that reach +1 ATR before tagging OR low. Split FLY vs FAIL labels inside the cell. Where FLY members printed max_ext: before 09:44 / 09:44–11:59 / after 11:59.

Paragraph: is there a **forward** return from 09:44, and does an OR-low stop survive. Holdout tables = PEEK only.

**Gate:** cell-buy ids (Part B 1–3) run **only if** develop FLY members, $5–20, median ext_1159 vs 09:44 close > 0 **and** fraction reaching +1 ATR before OR-low ≥ 0.35. If the gate fails, print SKIP and do not invent a buy.

## Part B — longs on data/full, harness on, $200, cap8, ranked by run_rel_vol

| id | door | run if |
|---|---|---|
| 1 | **cell09:45** flatten 11:59. Entry 09:45 open, cell $5–20, run_rel_vol_0944 ≥ 3. Stop max(OR low, ATR, 0.6%) | gate |
| 2 | same, **hold05** | gate |
| 3 | same, +1R then ATR trail, flatten 15:59 | gate |
| 4 | **flush no-08:00**, undercut of **09:44 close** in [2%, 6%], 5-min HL + strong close, cell $5–20. Flat 11:59 | always |
| 5 | **flush no-08:00**, undercut of **OR high** in [2%, 6%], same HL. Flat 11:59 | always |
| 6 | **launch compatible:** OR≥5.1% and pre_dv_0929≥$98k (no ext_0944 cut), ext_0929 in [−3%, +5%], after 09:45 confirmed launch, run_rel_vol_launch ≥ 5. Stop max(prior-15m low, ATR). Flat 11:59 | always |

If develop n < 40 on id 6, SHELVE not close.

peak_conc / mean_conc on every id. Flight stats.

## COMBINED

`B_uptick10|atr1559` + best develop-not-red rocket id this file (else flush|max6 reprint). Honesty line.

## Outputs

`reports/arrow29_results.txt` — Part A paragraph + gate yes/no, Part B table, COMBINED.
Append RESEARCH_LOG.md.
Tests: Part A uses 09:44 close not prior close; id 4 never reads 08:00 last_px; id 6 rejects a +12% wick that closes +6%; cell-buy silent if gate fails.

Commit code + reports. No parquet. No Arrow 30.
