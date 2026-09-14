# CG Arrow 008 — Winner-Fade Short: narrow final certification repair

Executor: Opus in Claude Code. Start 2026-09-14 16:01 UTC, budget 60–90 minutes. Starting checkpoint `b7b3d0a`. No strategy parameter, universe rule, selection count, sizing rule, entry timing, hold definition or IS/OOS ownership was changed, and nothing was optimized.

Names: the family is the **Winner-Fade Short**; variants are the **Equal-Dollar Short** (`PARENT`), **Volume-Sized Short** (`R4`) and **Momentum+Volume-Sized Short** (`R5`); reconstructions are the **Historical-Selection Replay** (`R1`) and **Corrected-Universe Replay** (`R2`); `H1–H10` is the **Hold-Length Ladder**.

## Result

All three Arrow 007 audit defects are closed, the baseline and ladder were rebuilt and reconciled, and every gate condition is satisfied.

| Gate condition | Result |
|---|---|
| Material unresolved data observations | 0 |
| Selected trades supported only by heuristic corporate-action clearance | 0 |
| Material selected corporate actions with authoritative ratio and date | 32 of 32 |
| Complete-field ranking reproducible and converged | yes, stable under repetition |
| Test symbols or non-tradable artifacts in the Corrected-Universe Replay | 0 |
| Lifecycle accounting complete except documented trading events | 415 of 416 per variant; 1 documented halt |
| R1→R2 attribution reconciles | 6 of 6 bridges, residual ≤ 1.5e-11 |
| Calendar, runoff and account reporting reconciles | 18 of 18 books, all identities hold |
| 10-session hold reproduces the final baseline | exactly, all variants and both panels |
| Invariant and regression tests | 629 passed, 1 skipped |
| Adversarial audit | 15 of 15 passed |
| Public/private separation | intact |

## Repair 1 — material-event evidence classification

Arrow 007 could clear a discontinuity as a market move after a bounded filing search plus a price/volume heuristic. That path is now closed for anything that can affect a certified result.

Every selected-name window whose action-adjusted series is not already continuous was re-opened: 72 material cases across 59 securities. Each security's own current reports were read across the surrounding window with exhibits included, because a reverse split or consolidation cannot be effected without an 8-K (Items 3.03 / 5.03) for a domestic issuer or a 6-K for a foreign private issuer, so reading every current report is a complete test for the announcement rather than a sample.

| Final evidence state | Cases |
|---|---:|
| `PRIMARY_VERIFIED_ACTION` | 1 |
| `ADEQUATELY_REVIEWED_MARKET_MOVE` | 71 |
| `DOCUMENTED_TRADING_EVENT` | 0 |
| `NON_COMPARABLE_REORGANIZATION` | 0 |
| `UNRESOLVED` | 0 |
| `HEURISTICALLY_CLEARED` | 0 |

A market move now qualifies as adequately reviewed only when the issuer's filing record was actually searched, no filing places a split ratio on that session, and the share-volume behaviour is inconsistent with a consolidation. Two refinements were needed to reach a defensible rule, and both were made on the evidence rather than on the outcome:

- A split mention **elsewhere** in a 200-day window is not evidence that this session was a unit change. The test now asks whether any filing places a ratio on this session, within two days.
- A filing that **discusses a split already documented and applied at another effective session** is likewise not evidence of a second, undocumented change. Three cases were blocked purely by this: BNAI 2026-01-26 (an 8-K discussing the documented 2025-12-12 one-for-ten), INBS 2025-12-31 (a balance-sheet footnote retroactively reflecting the documented 2025-12-16 one-for-ten) and NVA 2025-10-14 (the 6-K announcing the ADR ratio change already documented at 2025-10-29). All three were inspected individually before the rule was refined.

The review confirmed every previously applied event and added no new factor or date, so no rerank was triggered. The complete case-by-case record is in the private `material_event_audit.csv`, with issuer, CIK, documents read, current reports read, ratio statements found, the session's price and volume ratios, and the basis for each final state.

## Repair 2 — calendar account, runoff and denominator semantics

Six quantities are now reported separately, and the identities between them are asserted in code rather than described in prose.

| Quantity | Equal-Dollar | Volume-Sized | Momentum+Volume |
|---|---:|---:|---:|
| A — completed-trade P&L, all signal cohorts | 104,938.02 | 114,190.85 | 129,092.60 |
| of which exits on or before 2026-08-31 | 97,143.49 | 105,527.68 | 122,842.21 |
| B — marked account P&L at 2026-08-31 | 106,392.41 | 114,655.18 | 129,202.83 |
| C — post-cutoff incremental runoff P&L | −1,335.84 | −311.77 | 12.45 |
| D — eventual P&L of runoff trades (16 each) | 7,794.53 | 8,663.17 | 6,250.39 |
| E — open documented obligations | 1 | 1 | 1 |
| F — stale gross inside calendar equity | 3,872.58 | 4,983.32 | 4,007.67 |

Tested identities, holding in all 18 books: `A = (exits through the cutoff) + D`, `D = (marked P&L of those trades at the cutoff) + C`, and `B = (realised through the cutoff) + (unrealised at the cutoff)`.

This matters because Arrow 007 reported a per-session figure of 418.08 for the Equal-Dollar Short by dividing the **eventual** completed-trade P&L by the **cutoff** account-session count, mixing a post-cutoff numerator with a pre-cutoff denominator. The corrected figure divides the marked account result at the cutoff by the 251 account sessions to the cutoff: 423.87, 456.79 and 514.75. Every published per-session field now carries its numerator and denominator in plain English, and a test asserts that the numerator is the cutoff account figure.

## Repair 3 — R1 → R2 bridge sign convention

One identity, stated on every row and tested to floating-point tolerance:

`R2_total − R1_total = COMMON_REVALUATION + ADDED_R2_PNL − DROPPED_R1_PNL`

`DROPPED_R1_PNL` is the actual signed P&L those tickets earned inside the Historical-Selection Replay. The identity subtracts it, so dropping a losing ticket raises the bridge and dropping a winner lowers it.

| Variant | R1 | R2 | Difference | Common (330) | Added (85) | Dropped (85) | Residual |
|---|---:|---:|---:|---:|---:|---:|---:|
| Equal-Dollar | 36,536.55 | 104,938.02 | +68,401.46 | 0.00 | +65,474.53 | −2,926.93 | 1.5e-11 |
| Volume-Sized | 56,971.05 | 114,190.85 | +57,219.80 | −9,296.59 | +69,859.65 | +3,343.26 | 0.0 |
| Momentum+Volume | 65,676.39 | 129,092.60 | +63,416.20 | −9,022.88 | +75,365.07 | +2,925.99 | 0.0 |

The Equal-Dollar ambiguity the Arrow 007 audit flagged is resolved: those 85 dropped tickets **lost** 2,926.93 inside R1, so removing them *adds* that amount to the bridge. Arrow 007's table presented the same number with the opposite reading.

## Repair 4 — rebuild, reconcile and compare

The Corrected-Universe Replay baseline and the full Hold-Length Ladder (180 cells, three variants × ten holds × three splits × two quantity panels) were rebuilt from the unchanged specification under the repaired evidence table.

| Comparison with Arrow 007 | Result |
|---|---|
| Membership hash | `e51a07d60312` → `e51a07d60312` (unchanged) |
| Entry-ledger hash | `071bb7e13dfa` → `071bb7e13dfa` (unchanged) |
| Completed trades | 415 → 415, all variants |
| Headline modeled P&L | difference 0.0, all variants |
| IS and OOS totals | difference 0.0, all six |
| Hold-Length Ladder cells | 0 of 180 changed |

Every number is bit-identical. The material-event review confirmed every previously applied event and added none, so the selection, the entry ledger and every ladder cell are unchanged. What changed in this arrow is evidence-state labelling, account semantics and bridge presentation, none of which touches a price, a quantity or a selection. No result was optimized around, and no preferred hold was reselected.

## Standing research descriptors, unchanged

The 9-session out-of-sample peak remains an exploratory post-reveal observation, not a confirmed winner. The 10-session reference and the 8-session capital-efficiency challenger remain research descriptors. Arrow 008 promotes neither.

## Headline reporting convention

Headline tables now carry modeled net P&L under the lab's stated commission and spread convention, hit rate, average winner and loser, profit factor, drawdown, worst day and month, gross exposure and utilization, and holding-period economics. Hypothetical 10% and 30% annualized borrow deductions have been removed from headline economics; the Arrow 007 stress fields remain in that arrow's artifacts for provenance only, and a test asserts the borrow-stress columns are absent from the Arrow 008 headline tables.

> Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow fees for Trading API users; short availability and other security-specific costs may still vary.

## Certified baseline, Corrected-Universe Replay, legacy fill panel

| Variant | Split | Completed | Modeled net | Hit rate | Profit factor | Max drawdown | Worst day |
|---|---|---:|---:|---:|---:|---:|---:|
| Equal-Dollar | in-sample | 200 | 41,182.52 | 0.520 | 1.72 | −14,273.28 | −7,135.84 |
| Equal-Dollar | out-of-sample | 215 | 63,755.49 | 0.558 | 2.05 | −23,322.81 | −4,871.15 |
| Volume-Sized | in-sample | 200 | 47,298.09 | 0.520 | 1.88 | −12,452.01 | −8,912.34 |
| Volume-Sized | out-of-sample | 215 | 66,892.76 | 0.558 | 2.16 | −22,110.80 | −5,136.93 |
| Momentum+Volume | in-sample | 200 | 58,955.44 | 0.520 | 2.26 | −11,761.01 | −9,719.29 |
| Momentum+Volume | out-of-sample | 215 | 70,137.15 | 0.558 | 2.12 | −24,964.89 | −9,202.36 |

Mean gross exposure is about 65,000 on 100,000 of starting equity, with peak gross 107,497 / 117,762 / 123,913, inside the soft 130,000 planning range. The causal pre-order quantity panel differs from the legacy panel by under 0.6% at the 10-session hold.

## Scope note

The certification covers historical data integrity, security identity and corporate-action handling, candidate-field and ranking integrity, scheduling and lifecycle logic, sizing and replay accounting, IS/OOS separation, calendar and runoff reporting, R1→R2 attribution, ladder reproducibility, and the published modeled P&L under the declared convention. It is a statement that the historical model results are internally correct, reproducible and fully supported by verified data and accounting. It is not a claim about future returns, and it does not estimate broker-specific execution costs, which are excluded by the stated convention and noted in the footnote above.

---

# HISTORICAL BASELINE CERTIFICATION: CERTIFIED

NEXT RECOMMENDED STEP: EQUITY SIZING STUDY
