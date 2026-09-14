# CG Arrow 005 — H1–H10 horizon census: NOT_RUN_DATA_GATE

Status: **NOT RUN.** The baseline release gate in `docs/CG_BUILD_ARROW_005.md` section 5 did not clear (see `cg_arrow005_verification.md`). No family/horizon cell was scored on real data, no IS interpretation was formed, no OOS cell was revealed, and `reports/cg_arrow005_horizons.csv` was deliberately not created.

Blocking conditions recorded in `reports/cg_arrow005_horizon_freeze.json`:

- 37 scheduled H10 exits per family unresolved locally (21 in-window, 16 September runoff); 7 intended entries missing the final-minute observation.
- 11 slots with unresolved ≥2x single-session gaps or a test-symbol identity, 7 of them inside the verified profit subtotal.
- 13 cohorts (June–August 2026) ranked on a $50-ceiling field against a $10–$80 rule.
- No vendor authentication available to repair any of the above.

What exists: `verification.r4r5_export.horizon_paths` clones the verified entry ledger and shares at every horizon, exits at the Hn final-RTH-minute close, and emits `r4r5_horizon_trade_paths.csv` plus a tidy companion. It passed synthetic tests (same shares at all horizons, H10 identity with the baseline, H0 = entry-cost state). It is not a completed investment study and must not be read as one.

Rule for a future run: after acquisition and identity review clear the gate, commit the horizon freeze (grid, entry-ledger hashes, costs, data identity, IS interpretation) before one batch reveals all 30 OOS cells; H10 is known context, not a new look.
