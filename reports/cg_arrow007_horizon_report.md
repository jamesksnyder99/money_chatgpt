# CG Arrow 007 — Hold-Length Ladder for the Winner-Fade Short

Scored on the frozen Corrected-Universe entry ledger (`R2`), ledger hash in `cg_arrow007_manifest.json`. Within each quantity panel every hold length clones the same entries, initial shares, entry observations and entry costs; only the scheduled exit age changes. No reinvestment, replacement entry, compounding or exposure normalisation when a shorter hold frees cash.

Variants: **Equal-Dollar Short** (`PARENT`), **Volume-Sized Short** (`R4`), **Momentum+Volume-Sized Short** (`R5`). Panels: **legacy fill-close sizing** (`LEGACY_FILL_QTY`, the historical-comparison panel) and **causal pre-order sizing** (`CAUSAL_PREORDER_QTY`, a predeclared robustness panel). Splits are owned by the original signal month, so in-sample risk contains no out-of-sample position and vice versa.

## Procedure actually followed

1. All 30 in-sample cells scored per panel on in-sample-owned books only.
2. Preferred holds predeclared from the in-sample matrix alone: **8, 8 and 10 sessions**.
3. Freeze committed and pushed to `origin/main` before any out-of-sample cell was computed. The reveal script refuses to run unless the committed freeze matches the working copy byte for byte and the entry-ledger hash is unchanged.
4. Every out-of-sample cell revealed once, in a single batch, for both panels.
5. No hold length was changed after the reveal.

The 10-Session Hold reproduces the locked certified baseline exactly, difference 0.0, in all six variant and panel combinations.

## In-sample matrix, legacy panel

| Hold | Equal-Dollar | Volume-Sized | Momentum+Volume |
|---|---:|---:|---:|
| 1 session | 11,280.44 | 11,970.44 | 10,710.86 |
| 2 sessions | 24,120.16 | 26,477.92 | 27,800.80 |
| 3 sessions | 24,729.75 | 29,275.56 | 33,632.84 |
| 4 sessions | 23,817.62 | 29,186.37 | 33,258.76 |
| 5 sessions | 26,472.43 | 34,011.25 | 43,501.24 |
| 6 sessions | 34,037.39 | 39,079.62 | 48,637.57 |
| 7 sessions | 32,942.59 | 36,798.96 | 46,609.02 |
| 8 sessions | **43,411.50** | **47,470.48** | 58,288.31 |
| 9 sessions | 41,929.15 | 45,955.11 | 56,660.92 |
| 10 sessions | 41,182.52 | 47,298.09 | **58,955.44** |

## Out-of-sample matrix, legacy panel, single batch

| Hold | Equal-Dollar | Volume-Sized | Momentum+Volume |
|---|---:|---:|---:|
| 1 session | 5,502.98 | 5,165.15 | 3,050.20 |
| 2 sessions | 20,113.99 | 21,639.46 | 28,473.64 |
| 3 sessions | 33,208.94 | 33,381.11 | 36,229.02 |
| 4 sessions | 33,830.73 | 33,481.58 | 34,395.40 |
| 5 sessions | 37,638.81 | 36,259.64 | 34,029.48 |
| 6 sessions | 43,931.48 | 41,505.62 | 42,114.55 |
| 7 sessions | 54,440.12 | 53,746.92 | 55,401.19 |
| 8 sessions | 63,526.52 | 65,857.20 | 70,632.92 |
| 9 sessions | **69,928.65** | **73,936.76** | **80,281.65** |
| 10 sessions | 63,755.49 | 66,892.76 | 70,137.15 |

## Confirmation verdict

| Variant | Predeclared hold | Out-of-sample net | Its 10-Session Hold | Increment | Verdict |
|---|---|---:|---:|---:|---|
| Equal-Dollar | 8 sessions | 63,526.52 | 63,755.49 | −228.97 | **NOT REPEATED** |
| Volume-Sized | 8 sessions | 65,857.20 | 66,892.76 | −1,035.55 | **NOT REPEATED** |
| Momentum+Volume | 10 sessions | 70,137.15 | 70,137.15 | 0.00 | **NOT REPEATED** (the preference was the reference itself) |

The predeclared preference failed in every variant. The in-sample advantage of the 8-session hold did not carry, and the differences are small relative to drawdowns of 21,000 to 25,000.

**Unconfirmed observation, recorded so it is not discovered twice.** The 9-session hold is the out-of-sample peak for all three variants, beating the 10-session hold by 6,173 / 7,044 / 10,145. It was not the in-sample preference for any variant and this look is post-reveal, so it is not a finding and must not be presented as confirmed. A future arrow may predeclare it and test it on evidence that has not already been seen.

**What does repeat** is the shape rather than the point. Holds of one to two sessions are clearly inferior in both splits; the curve climbs steeply through the middle of the ladder and flattens in the 8-to-10 session region. Ten highly correlated hold lengths on one entry ledger are one family, not ten independent discoveries.

## Panel robustness

The causal pre-order sizing panel tracks the legacy panel within 0.6% at the 10-session hold for every variant (104,399.17 versus 104,938.02; 113,845.29 versus 114,190.85; 128,864.62 versus 129,092.60). The ladder shape is unchanged, so the historical fill-close sizing convention is not carrying the conclusion. Neither panel was chosen after seeing out-of-sample results.

## Event states across the ladder

Trades are never dropped from a comparison to keep the sample tidy. Each ticket carries a state at each hold length: completed scheduled exit, documented no-entry, documented halt or open obligation, or structural block. Same-trade increments report paired completed-to-completed changes separately from completed-to-open and open-to-completed transitions, with the withdrawn or added profit shown rather than silently removed. The EFTY suspension is part of the economics at every hold length.

## Accounting basis

Every per-session figure divides by the 251 account sessions of the relevant split-owned book, which is stated on each row. That is a different denominator from the 124 and 127 signal-session figures used in earlier arrows, so the numbers are not directly comparable to them. The calendar account ends 2026-08-31; the September runoff of August-signal cohorts is reported separately and never folded into the twelve-month account. Borrow remains a scenario at 0, 10 and 30% annualised, so no figure here is verified executable historical net profit.

Detailed local files: `r4r5_horizon_trade_paths.csv`, `r4r5_horizon_trade_paths_tidy.csv` and `r4r5_horizon_summary.csv` under `handoff/outgoing/cg_arrow007/`. Public safe aggregates: `cg_arrow007_horizons.csv`, `cg_arrow007_horizon_increments.csv`, `cg_arrow007_holding_age_curve.csv`.
