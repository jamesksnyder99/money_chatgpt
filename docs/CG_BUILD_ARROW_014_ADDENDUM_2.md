# CG Arrow 014 — Addendum 2: A13 Audit Transition + Frozen Rank-by-Rank Diagnostic

This addendum is authoritative where it is more specific than `docs/CG_BUILD_ARROW_014.md` or Addendum 1. It is committed **before any September 2024–August 2025 strategy outcome is calculated**.

## 1. A13 audit transition status

ChatGPT audit accepts Arrow 013 as complete for its acquisition/generic-integrity mission and safe to hand into Arrow 014's two-lock reveal process.

The audit does **not** relabel A13 as fully certified for performance. Preserve its honest terminal status:

`HOLDOUT_DATA_PARTIALLY_CERTIFIED`

The final A13 source layer establishes, without strategy scoring:

- 1,079,750 / 1,079,750 expected newly acquired minute partitions;
- all 250 newly acquired sessions present, with authenticated August 2025 reuse and September 2025 lifecycle support contributing to the full 292-session calendar corridor;
- zero vendor errors on the final acquisition run;
- zero duplicate timestamps, unordered partitions, out-of-window bars, OHLC inconsistencies, negative volume, non-finite traded-price defects, schedule overruns, and unreadable partitions under the declared checks;
- authenticated August 2025 overlap sample with no discrepancies;
- independent NYSE calendar agreement;
- full-universe/ranking-field inventory sufficient to freeze mechanical memberships without silently dropping competitors;
- no Winner-Fade rankings, selected-name outcomes, trade P&L, hit rates, drawdowns, monthly strategy returns, or ending equity were calculated in A13.

Two and only two blocking evidence layers remain from A13:

1. documented dated corporate actions for the new holdout corridors;
2. point-in-time security identity / ticker-change mapping for the new holdout corridors.

These are exactly the blockers Arrow 014 must close after the immutable reveal specification is committed and frozen memberships are mechanically generated without outcomes. If any newly required feature/entry/lifecycle observation then proves unresolved, it becomes an additional Arrow 014 certification blocker and performance remains locked.

The A13 report phrase `292 of 250 new-acquisition sessions` is a wording defect, not an inventory rule. The correct distinction is 250 newly acquired sessions (2024-08-01 through 2025-07-31) plus authenticated/reused August 2025 and September 2025 support within the overall 292-session 2024-08-01 through 2025-09-30 calendar corridor. Arrow 014 reporting must preserve this distinction.

## 2. Arrow 014 activation sequence

Addendum 1's two-lock ordering remains authoritative:

1. verify the audited A13 source/calendar/universe state without outcomes;
2. commit/push the immutable Arrow 014 reveal specification and exact cohort calendar before generating selected memberships;
3. mechanically generate memberships only to identify the exact corporate-action, identity, feature, causal-entry, and H8/H9/H10 lifecycle corridors requiring closure; still no strategy outcomes;
4. resolve every material corridor with documented evidence, rerank mechanically if normalization changes inputs, and iterate until no unresolved observation can alter a frozen scored cell;
5. audit August 2025 prior-use/pristine status;
6. commit the exact final status `HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL` with unresolved material exceptions affecting scored cells = 0;
7. only then calculate all frozen results in one batch.

No performance may exist before step 6 passes.

## 3. Frozen full rank 1–8 diagnostic

Arrow 011 already published a rank-by-rank H10 sizing-neutral table for ranks 1 through 8 across the historical 52 cohorts. Therefore the same diagnostic is pre-registered here for the pristine September 2024–August 2025 reveal. It is a replication diagnostic, not a new model or selection rule.

For each original corrected top-eight ordinal rank 1, 2, 3, 4, 5, 6, 7, and 8, publish on the pristine year:

- cohort count / completed count / censored-or-open count;
- mean sizing-neutral H10 short return;
- median sizing-neutral H10 short return;
- H10 favourable/hit rate;
- mean sizing-neutral H8 and H9 short return as secondary frozen-horizon diagnostics;
- fixed-dollar R5 H10 aggregate contribution;
- equity-scaled R5 H10 aggregate contribution, clearly separated from sizing-neutral stock behaviour;
- number of positive/negative cohorts for that rank;
- historical Arrow 011 ALL-year mean/hit as a labeled reference, with no refitting.

The principal replication table should show at least:

| Rank | Historical H10 mean | Historical hit | Pristine H10 mean | Pristine hit | Pristine median | Pristine R5 fixed contribution |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | +0.272 | 83% | | | | |
| 2 | +0.073 | 58% | | | | |
| 3 | +0.039 | 52% | | | | |
| 4 | +0.027 | 50% | | | | |
| 5 | +0.092 | 62% | | | | |
| 6 | +0.026 | 49% | | | | |
| 7 | -0.015 | 46% | | | | |
| 8 | +0.013 | 46% | | | | |

Historical values above are descriptive references already exposed in Arrow 011. They do not create a top-five, rank-five, rank-seven, or any other new trading rule.

Explicitly answer after the reveal:

- Does rank one remain exceptional relative to the other seven?
- Does the historical non-monotonic shape (including relatively strong rank five and weak rank seven) repeat, weaken, or disappear?
- Is any rank-level result carried by a small number of cohorts?

Do **not** use this table to introduce a top-5-only book, drop ranks 6–8, change C1's 1.50x multiplier, or create another allocation rule on this holdout. Any such idea belongs to a future development sample.

## 4. Required artifacts/tests addition

Add to the Arrow 014 public-safe outputs:

- `reports/cg_arrow014_rank_by_rank.csv`

And test that:

- each pristine cohort contributes at most one original top-eight observation to each rank;
- ranks are assigned from the frozen corrected 15-session ranking before any outcome is read;
- the eight rank rows reconcile to the principal original top-eight H10 ticket census, subject only to explicitly documented open/censored obligations;
- sizing-neutral, fixed-dollar, and equity-scaled quantities are never mixed;
- no rank-level result can mutate selection, sizing, horizon, or the reveal specification after outcomes exist.
