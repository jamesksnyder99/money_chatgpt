# CG Build Arrow 008 — Winner-Fade Short: Narrow Final Certification Repair

## Mission

Close the finite remaining Arrow 007 audit defects and produce a binary final certification of the historical Winner-Fade Short research baseline and Hold-Length Ladder.

This is **not** a strategy-development arrow. Do not change the signal, universe rule, selection count, sizing logic, entry timing, hold definitions, IS/OOS ownership, or optimize any parameter.

Work only in:

`C:\Users\james\money_chatgpt`

Do not touch the pristine Money repository.

### Naming

- Winner-Fade Short = strategy family
- Equal-Dollar Short = `PARENT`
- Volume-Sized Short = `R4`
- Momentum+Volume-Sized Short = `R5`
- Historical-Selection Replay = `R1`
- Corrected-Universe Replay = `R2`
- `H1–H10` = Hold-Length Ladder

---

# Scope of certification

The requested certification is for:

1. historical data integrity used by the model;
2. security identity and corporate-action handling;
3. complete candidate-field and ranking integrity;
4. weekly scheduling and entry/exit lifecycle logic;
5. position sizing and replay accounting;
6. IS/OOS ownership separation;
7. calendar-account/runoff reporting;
8. R1→R2 attribution;
9. H1–H10 Hold-Length Ladder reproducibility; and
10. the published modeled P&L under the lab's stated commission/spread convention.

Do **not** condition certification on estimating generic stock-borrow rates.

For future research communication, generic 10%/30% annualized borrow deductions are no longer headline economics. Preserve any prior stress fields for provenance if needed, but do not present them as estimated realized costs and do not use them to weaken or qualify the certification decision.

Use this concise footnote on headline economic tables:

> Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow fees for Trading API users; short availability and other security-specific costs may still vary.

The certification question is therefore: **Are the historical model results internally correct, reproducible, and fully supported by verified data and accounting under the declared model convention?**

---

# Repair 1 — Close corporate-action / market-move evidence classification

Arrow 007 did substantial event work, but a generic path can still classify a discontinuity as a nonblocking market move after a bounded filing search plus price/volume heuristics.

For every **material selected-name discontinuity** that can affect selection, ranking, sizing, entry, exit, or H1–H10 economics:

1. Re-evaluate the evidence record.
2. A corporate action must have an authoritative ratio **and** an authoritative effective / first adjusted trading date from issuer, SEC, or exchange evidence.
3. A true market move may remain a market move, but it must be supported strongly enough that the final audited row is not merely a heuristic clearance.
4. Separate final states such as:
   - `PRIMARY_VERIFIED_ACTION`
   - `ADEQUATELY_REVIEWED_MARKET_MOVE`
   - `DOCUMENTED_TRADING_EVENT`
   - `NON_COMPARABLE_REORGANIZATION`
   - `UNRESOLVED`
5. `HEURISTICALLY_CLEARED` or equivalent may remain only for immaterial diagnostics that cannot affect any certified result. It may not support a selected trade or ranking boundary.
6. If evidence changes an event factor/date, normalize → rebuild → rerank the complete field mechanically. Never manually substitute rank 9 or another ticker.

Required invariant before certification:

**Zero unresolved or heuristic-only material event classifications in every selected ranking window and every selected H1–H10 lifecycle window.**

Publish the count by final evidence state.

---

# Repair 2 — Calendar account, runoff, and denominator semantics

Regenerate the economic reporting with explicitly distinct quantities that reconcile.

At minimum report separately:

1. **Completed-trade P&L for all signal cohorts** — eventual P&L of completed positions, including scheduled exits after 2026-08-31 where applicable.
2. **Marked account P&L / equity at 2026-08-31** — the actual calendar cutoff account state, including unrealized positions under the stated valuation convention.
3. **Post-August incremental runoff P&L** — only the change in value earned after 2026-08-31 on positions already open at the cutoff.
4. **Eventual P&L of runoff trades** — full-life P&L of trades whose exits occur after the cutoff.
5. **Open documented obligations** — separately identified and not silently valued as completed trades.
6. **Stale-mark amount/status** — explicit if any stale mark enters calendar equity.

No field called `$ / session`, `per session`, or equivalent may divide eventual post-cutoff completed-trade P&L by an August-31 account-session denominator.

Every per-session field must state both numerator and denominator in plain English.

Required identities must be tested in code, not only described in prose.

---

# Repair 3 — R1 → R2 upside bridge sign convention

Regenerate the Historical-Selection Replay → Corrected-Universe Replay bridge mechanically.

Use one explicit sign convention and make the identity impossible to misread.

Preferred representation:

`R2 - R1 = COMMON_REVALUATION + ADDED_R2_PNL - DROPPED_R1_PNL`

where `DROPPED_R1_PNL` is the actual signed P&L of tickets removed from R1.

Alternatively use a contribution convention, but define it explicitly.

For every family/panel:

- common tickets;
- added tickets;
- dropped tickets;
- exact component sums;
- exact R1 total;
- exact R2 total;
- exact reconciliation residual.

Add an invariant test requiring residual within floating-point tolerance.

Fix the Equal-Dollar dropped-ticket sign ambiguity identified in the Arrow 007 audit.

---

# Repair 4 — Rebuild and freeze final certified outputs

After the three repairs above:

1. Rebuild the Corrected-Universe Replay baseline from the unchanged strategy specification.
2. Rebuild the full H1–H10 Hold-Length Ladder.
3. Verify H10 exactly reproduces the repaired certified baseline for all three sizing variants and both quantity panels.
4. Compare the new output to Arrow 007 and publish:
   - old/new membership hash;
   - old/new entry-ledger hash;
   - old/new completed-trade counts;
   - old/new headline modeled P&L;
   - old/new IS/OOS totals;
   - old/new H1–H10 totals;
   - reason for every nonzero difference.
5. Do not optimize around any changed result.
6. Do not reselect a preferred hold from already-revealed OOS.

The 9-session OOS peak remains an exploratory post-reveal observation, not a confirmed winner.

The 10-session reference and the previously noted 8-session capital-efficiency challenger remain research descriptors only; Arrow 008 does not promote either into a new optimized strategy.

---

# Final certification gate

Output exactly one of:

## `HISTORICAL BASELINE CERTIFICATION: CERTIFIED`

Only if all of the following are true:

- zero material unresolved data observations;
- zero selected trades supported only by heuristic corporate-action clearance;
- every material selected corporate action has authoritative ratio/date support;
- complete-field ranking is reproducible and converged;
- no test symbols/non-tradable artifacts contaminate R2;
- lifecycle accounting is complete except separately documented genuine trading events;
- R1→R2 attribution reconciles exactly;
- calendar/runoff/account reporting reconciles exactly;
- H10 reproduces the final baseline exactly;
- all invariant/regression tests pass;
- adversarial audit passes;
- public/private data separation remains intact.

or:

## `HISTORICAL BASELINE CERTIFICATION: NOT CERTIFIED`

followed only by the exact finite blocker(s).

Do not use intermediate labels such as “essentially certified,” “certified except,” “close enough,” or “provisionally certified.”

---

# Headline reporting convention after certification

Headline strategy tables should present:

- modeled net P&L under the lab's stated commission/spread convention;
- hit rate;
- average winner/loss;
- profit factor;
- drawdown;
- worst day/month;
- gross exposure and utilization;
- holding-period economics.

Do **not** insert hypothetical 10%/30% borrow deductions into headline tables.

If prior 10%/30% stress results are retained for provenance, place them only in a clearly labeled historical stress appendix.

Use the standardized footnote:

> Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow fees for Trading API users; short availability and other security-specific costs may still vary.

Do not start a broker comparison or historical borrow-cost reconstruction in Arrow 008.

---

# Required outputs

Public-safe:

- `reports/cg_arrow008_verification.md`
- `reports/cg_arrow008_certified_baseline.csv`
- `reports/cg_arrow008_horizons.csv`
- `reports/cg_arrow008_r1_r2_bridge.csv`
- `reports/cg_arrow008_manifest.json`
- `reports/cg_arrow008_commands.txt`
- any necessary code/tests

Private, git-ignored, individual/unzipped as needed:

- `handoff/outgoing/cg_arrow008/certified_trade_audit.csv`
- `handoff/outgoing/cg_arrow008/certified_cohort_audit.csv`
- `handoff/outgoing/cg_arrow008/material_event_audit.csv`
- any other audit-critical detailed files

Preserve all Arrow 007 artifacts unchanged.

---

# Runtime and execution discipline

This is a **narrow final acceptance repair**, not an open-ended research project.

Predicted wall-clock budget: approximately **60–90 minutes**.

Use the available 8-way parallelism for independent evidence checks or replay work where safe. Keep dependent reranking, freeze decisions, and final reconciliation serial.

A modest overrun is acceptable only to finish an already-started finite evidence branch required for the certification gate.

Do not drift into:

- equity sizing;
- compounding;
- capital redeployment;
- execution-time optimization;
- 10/15/20 signal robustness;
- regime filters;
- signal anatomy;
- long-side research;
- broker selection;
- borrow-cost optimization.

Commit and push all public-safe Arrow 008 code/reports to `main` when complete.

Final report must end with the binary certification line and, if certified, this next-step line:

`NEXT RECOMMENDED STEP: EQUITY SIZING STUDY`
