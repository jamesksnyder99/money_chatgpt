# CG Arrow 014 — handoff for ChatGPT audit

Arrow 014 is complete. The certification gate closed, the full predeclared matrix ran once in one
batch, and every public output is committed and pushed. Nothing is in flight and no post-reveal
optimisation has begun.

## Read in this order

| what it answers | file |
|---|---|
| What was frozen before any membership existed | `reports/cg_arrow014_reveal_freeze.json` |
| Why the frozen code hashes drifted | `reports/cg_arrow014_lock1_amendment_1.md` |
| Whether the corridor is certified, and on what evidence | `reports/cg_arrow014_certification_gate.md` |
| The machine-checkable form of that gate | `reports/cg_arrow014_certification_manifest.json` |
| What the reveal found | `reports/cg_arrow014_reveal.md` |
| The eighteen cells | `reports/cg_arrow014_headline_matrix.csv` |
| Run provenance, hashes, oracle result | `reports/cg_arrow014_manifest.json` |
| The exact sequence, in order | `reports/cg_arrow014_commands.txt` |

## Verification the reveal passed

- Independent oracle recomputed all **7,344 trades** from stored inputs, maximum absolute error
  **7.3e-12**
- Account identities hold on **18 of 18** accounts
- All **18** monthly tables reconcile to their own marked account P&L at the cutoff
- Every account carries **twelve** monthly rows, 2024-09 through 2025-08
- Scored cohort ids are exactly the **frozen 52**
- C1, C2 and C3 preserve each cohort's base capital to **7.3e-12**

## Six things an auditor should attack first

These are the judgement calls. Each is a place where I decided something that a reasonable reviewer
could decide differently, and each would change the result if I got it wrong.

**1. The rule field was wrong once, and everything built on it was wrong with it.**
I first built the candidate field from Arrow 013's `eligible` column without checking its contract.
That column is an acquisition universe with a **$1.00** floor; the ranking rule is **$10–$80**, as
LOCK 1 states. Securities between $1 and $10 are exactly the ones that post enormous
fifteen-session returns, so they took over the selections — KULR entered at $1.18. I caught it by
noticing an entry price the rule cannot admit. **The first LOCK 2 and the reveal it permitted are
withdrawn** (commit `7780f95`). The corrected field carries 1,082–1,387 securities per session
against the historical study's 1,295. **Check that number first**: if the contract is right, the
field size should sit near the historical one.

**2. Gate condition G10 was restated.**
It originally required every scored cell to *have* an observed feature, entry and exit. Some do
not, because the partition was retrieved and the security did not trade. Demanding an observation
that cannot exist would block the reveal over ordinary trading behaviour, or worse invite treating
a no-trade session as a price. G10 now requires every observation to have been **retrieved**
(absent = 0); new G12 requires every untraded session to be governed by a rule frozen before the
corridor was acquired and reported rather than filled — 8 sizing-feature rows under `sizing()`'s
`vm = 1.0`, 2 unfilled entries and 21 unclosed exits under the Arrow 007 non-execution convention.
**This is the weakest link in the gate and deserves the hardest look.**

**3. A filing may be placed by the tape when it states no readable date.**
mF International announced a 1-for-8 consolidation in a 6-K whose effective date sits in prose the
parser does not reach. Such a statement is applied only when **exactly one** session in the whole
corridor carries a level change the factor flattens. Two candidate sessions means the filing does
not identify which, and it stays unapplied. 147 events applied; **5,933 filing statements recorded
and never applied**.

**4. The gap-fill gate turns on four observations, not a population.**
Of the 7,558 observations the eighteen cells read, **four** resolve to the gap-fill tree. A rate
over the whole tree measures a population the reveal does not depend on, so the gate examines those
four individually. Two — ANPA's H8 and H9 exits, which set P&L directly — disagreed with the
end-of-day layer, so they were **re-retrieved independently and reproduce bit-identically** (45
priced minutes, every timestamp matched, no price or volume mismatch). The end-of-day layer flags;
it does not adjudicate.

**5. One engine defect was fixed, and it touches no number.**
A holding window is screened in *fill* units, so a consolidation effective during the hold sits
after the as-of session where `adjustment_factor`'s backward-only form matches nothing. The ledger
was always correct — it takes its hold factor as `adjustment_factor(fill, exit)`, which does match
— so no quantity or price moves. `unit_factor` converts in either direction; `adjustment_factor` is
untouched, because prior arrows' ledgers are computed from it.

**6. The 2024 calendar was absent from the engine.**
`ingest/calendar.py` held only 2025–26, so on the two 2024 early closes the engine looked for a
15:59 print that cannot exist. Those sessions carry an entry execution, a signal ranking endpoint
and two holding exits. Fixed before any membership was generated; the frozen 52-cohort calendar is
bit-identical afterwards, and the fix is provably inert for the historical study.

## What closed Arrow 013's two blockers

| | |
|---|---|
| Point-in-time identity resolved | **1,624 / 1,634 (99.4%)** |
| Documented corporate actions applied | **147** (14 via the current ticker file alone) |
| Unexplained ranking-window discontinuities | 257 → **0** |
| Unexplained holding-window discontinuities | → **0** |
| Observations genuinely absent | **0** |
| Unresolved material exceptions | 398 → **0** |

Three of the defects in the way were mine: the resolver went straight to full-text search for
securities whose CIK was already in SEC's ticker file; it read only single-ticker display names, so
every dual-listed issuer (`FFIE, FFIEW`) looked unresolvable; and the first corroboration test had
the flattening direction inverted.

## Private files, not committed

Under `handoff/outgoing/cg_arrow014/`:
`r4r5_verified_trades.csv`, `r4r5_daily_account.csv`, `r4r5_cohort_matrix.csv`,
`r4r5_verified_cohort_audit.csv`, `r4r5_trade_exceptions.csv`, `selected_anatomy.csv`,
`selected_corridor_state.csv`, `cohort_allocation_audit.csv`, `membership.json`,
`trading_status.csv`, `august2025_pristine_audit.json`.

Under `data/holdout2024/work/`: `phase0b_membership.json`, `phase0b_field.json`,
`identity_investigation.json`, `census_symbol_scans.json`, `repair_certification.json`,
`exit_recheck.json` and the stage manifests.

The public manifest reports how much C2 substitution happened, never which securities.

## Known limitations

One twelve-month out-of-sample period. Not a forward test. Borrow availability and hard-to-borrow
cost are not modelled beyond the frozen cost model. The account convention assumes the frozen
execution and cost rules throughout, and marked equity is not subject to margin calls or forced
liquidation — several books show peak-to-trough drawdowns beyond 50%, and one path takes marked
equity close to zero before recovering, which a real account would not have survived intact. The
rank-by-rank table is a diagnostic and creates no book.
