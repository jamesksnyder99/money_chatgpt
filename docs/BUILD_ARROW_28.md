# Build Arrow 28 — B-short on the full tape; afternoon was unreachable

Read `docs/SUCCESS.md`, `reports/arrow27_results.txt`, `docs/BUILD_ARROW_27.md`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not EV.

No rocket rings. No $500/idea. No virgin pull. No cap3-vs-cap8 on flush.

## Port

Exact B kernel on **`data/full/`**:

- Track B pop from `data/full/eligibility.parquet`: prior_close [$10, $50], dv_rank ≥ 0.80 within session, 400/day cap as today
- 15-min EMA stack on the stitched 04:00–16:00 tape (same 9/21 rules as Lab A)
- Door: first 5-min close below ema9 after **09:45**, ema9 < ema21, gap-down ≥ 1.5%, OR width > 2.5%
- Stop = max(OR high, signal 5-min high), ATR/0.6% floor if harness helpers exist; otherwise OR-high as A18
- cap8, $200/idea, borrow proxy on
- **SSR policy = B_uptick10** from Arrow 27 (session-low flag; uptick fill within 10 min). Also print one **B_reject** row at flatten 11:59 so the flag is visible.

**Row 0:** flatten **11:59**, uptick10. Must reproduce A27 `B_uptick10` trade counts within ±10% (full tape can add premarket context to EMAs — if count drifts, say why, do not silently proceed).

## Afternoon rows (uptick10, same entry)

| id | exit |
|---|---|
| 0 | flatten 11:59 (port control) |
| 1 | flatten **15:59** |
| 2 | **hold05:** keep past 11:59 only if ≥ +0.5R at 11:59; else flatten |
| 3 | after +1R, trail 1.0× ATR(6) above the favorable extreme (short: below the low), flatten 15:59 |
| 4 | flatten **13:30** |
| 5 | hold05 but flatten the remainder at **14:30** |

No 7th. Short only.

Report for every id: n, $/day, hit, avgR, PF if cheap, se, t, CI, maxDD, peak_conc, mean_conc, fraction of 11:59 exits that were ≥ +0.5R (id 0), MFE after 11:59 for id-0 trades if held to 15:59 (cheap if you already replay).

Premarket $ vol and run_rel_vol at 09:29 on each trade — report-only, no gate.

## COMBINED

End of file: `combine_books` of **best develop B row this file** (must be develop-not-red to be "best"; if all afternoon rows are red, use id 0) **plus** `flush|max6` daily series (reprint or reuse A27).
Honesty line: combined develop is the number; combined holdout is not EV.

## Outputs

`reports/arrow28_results.txt`. Append RESEARCH_LOG.md.
Tests: id 0 short only; id 2 flattens a +0.3R name at 11:59 and holds +0.7R; id 4 flattens at 13:30; id 3 trail never loosens against the short.

Commit code + reports. No parquet. No Arrow 29.
