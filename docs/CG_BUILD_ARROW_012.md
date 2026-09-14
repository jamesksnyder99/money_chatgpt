# CG Build Arrow 012 — A11 Measurement Repair + Two Whole-Engine Challengers

Executor: **Opus in Claude Code**. Research director/auditor: ChatGPT.

Authorized September 14, 2026 after Arrow 011. This is a **narrow repair/research arrow**, not a broad optimization search.

## Mission

Do two things, in this order:

1. **Repair Arrow 011's measurement layer** where the audit found tie-order dependence and weak behavioral leakage tests. The repair must improve reliability only. It must not alter the frozen Winner-Fade trading engine, historical selections, prices, quantities, P&L, or account paths.
2. On the already-studied September 2025–August 2026 sample only, score exactly two predeclared challenger ideas and their interaction as complete engines:
   - **Rank-One Reallocation:** retain all eight names, give the original rank-one name 1.50x its existing relative ticket allocation, funded entirely by proportional reductions to ranks 2–8 so the cohort's intended base capital is unchanged.
   - **Off-High Substitution:** protect rank one, but allow weaker-ranked near-high names in ranks 2–8 to be replaced by the best-ranked qualifying names from original ranks 9–20 that were already farther below their recent high. Preserve the cohort's intended base capital.
   - Also score the **combined** challenger using both changes together.

The incumbent remains **Momentum+Volume-Sized Winner-Fade Short (R5), Corrected-Universe Replay (R2), 10-Session Hold (H10), causal pre-order quantities, with the Arrow 010 equity-scaling rule**. Nothing in this arrow displaces the incumbent. Challenger results are research evidence only.

### Scientific principle

Component improvements do not count as model improvements. Every serious challenger must be replayed as a **complete chronological account**. Do not add isolated component gains together and assume the combined engine earns their sum. Explicitly measure the interaction between the two changes.

---

# 1. Workspace, references, and strict holdout embargo

Work only in:

`C:\Users\james\money_chatgpt`

Remote: `jamesksnyder99/money_chatgpt`.

Never access `C:\Users\james\Money`.

Read `AGENTS.md`, `CLAUDE.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, this arrow, and the public/private manifests and reports from Arrows 008–011 that are needed for exact reproduction.

Starting checkpoint at assignment creation: Arrow 011 completed at commit `e1701d21331fb8b2cc4ecd1741776cab75e23b25`.

## CRITICAL: new-year holdout embargo

The user is acquiring an additional historical year for a future pristine confirmation batch. **Arrow 012 must not score, inspect, summarize, rank, feature-engineer, or otherwise learn outcomes from any new signal cohort outside the existing frozen 52 cohorts from September 2025 through August 2026.**

This applies even if new files appear locally while Arrow 012 is running.

- Enumerate Arrow 012 cohorts from the frozen Arrow 008/011 52-cohort membership, not by scanning all available dates.
- Do not list or open a newly added future-holdout trade/result file merely out of curiosity.
- Existing lookback observations and September runoff needed for the frozen 52 cohorts remain permitted.
- Add a hard test that all scored signal/cohort IDs belong to the frozen 52-cohort set.
- Do not create any performance summary for the new year.

The purpose is to leave the new year genuinely untouched for the next reveal.

---

# 2. Frozen controls — reproduce before repair or challenger scoring

Preserve every Arrow 001–011 artifact. Do not overwrite or retroactively rewrite Arrow 011 reports. Any corrected analysis is published under Arrow 012 filenames.

Before work proceeds, reproduce the relevant certified controls from source ledgers/caches and manifests. At minimum:

- 52 cohorts, 416 intended selections, 415 completed, 1 documented open obligation in the principal R5/R2 books;
- R5/R2/H10 causal-preorder eventual completed-trade P&L: **128,864.62**;
- R5/R2/H10 causal-preorder marked account P&L at 2026-08-31: **128,986.40**;
- Arrow 010 equity-scaled R5 marked P&L at 2026-08-31: **230,719.74**;
- Arrow 010 equity-scaled ending marked equity: **330,719.74**;
- Arrow 010 equity-scaled eventual completed-trade P&L: **230,566.36**;
- all relevant membership/input hashes from Arrows 008, 010, and 011.

If a frozen economic control fails, stop research scoring and diagnose it. Do not repair a baseline merely to make Arrow 012 run.

---

# 3. Phase A — repair the Arrow 011 analysis layer only

The audit found that the existing `within_cohort_top_half_minus_bottom_half` statistic can depend on original row order when equal feature values straddle the half split. A feature constant within a cohort must never acquire a nonzero within-cohort effect because of row ordering.

## A1. Tie-safe within-cohort statistics

Keep Spearman correlation with average ranks as one transparent within-cohort relationship measure.

Replace or supplement the unsafe half-split magnitude statistic with an order-invariant implementation. Use both of the following where meaningful:

1. **Strict half contrast:** sort by feature, but score a top-half-minus-bottom-half contrast only when no equal feature value crosses the median boundary. If a tie crosses that boundary, mark that cohort unscorable for this contrast rather than breaking the tie by row order. Report scored/excluded cohort counts.
2. **Pairwise directional effect:** within a cohort, consider unordered pairs with unequal feature values only. For each pair, orient the outcome difference from lower-feature to higher-feature and average those oriented differences. Feature ties contribute no arbitrary ordering. State formula and units explicitly.

Required invariants:

- permuting rows cannot change any reported relationship;
- a feature constant within a cohort yields no within-cohort contrast/effect;
- reversing the same rows cannot reverse an effect;
- repeated/tied discrete features report their usable-cohort support honestly;
- cohort-wide constants are never treated as within-cohort predictors.

Regenerate the Arrow 011 feature relationships under repaired statistics **without modifying Arrow 011 artifacts**. Publish exactly which prior labels survive, weaken, disappear, or were previously affected by the tie defect. The direct rank-one group result must be independently checked but should not be forced to change merely because a different statistic was repaired.

## A2. Stronger behavioral no-leakage tests

Replace source-code-string tests with behavioral tests wherever practical. At minimum prove:

- changing the final entry minute after `preorder_ts` cannot change any PRE_ORDER feature;
- changing bars after `preorder_ts` cannot change PRE_ORDER features;
- adding/changing post-signal bars cannot change SIGNAL_CLOSE features;
- inserting a synthetic corporate action effective after the signal cannot alter a SIGNAL_CLOSE feature, while an action effective inside the legitimate pre-signal normalization window is handled according to the declared unit convention;
- missing features remain missing and cannot become a favorable analysis state;
- early-close/pre-order clock handling is tested with an actual or controlled synthetic early-close case;
- outcome/path fields cannot enter pre-entry feature schemas.

These are analysis tests. Do not change entry timing or execution rules.

## A3. Dependence diagnostics

The existing whole-cohort resampling preserves the eight names in a cohort but not serial dependence across neighboring cohorts. Keep it, rename it accurately if needed, and add:

- contiguous **2-cohort** moving-block resampling;
- contiguous **4-cohort** moving-block resampling;
- a repeated-security / overlapping-episode sensitivity summary for leading relationships.

These diagnostics do not need p-value worship and do not decide the strategy. Their job is to show whether a finding is carried by a narrow episode or remains visible when obvious dependence is respected.

## A4. Repair outcome

Produce a concise repair verdict before challenger interpretation:

- `A11_RELATIONSHIP_SURVIVES_REPAIR`
- `A11_RELATIONSHIP_WEAKENS_AFTER_REPAIR`
- `A11_RELATIONSHIP_INVALIDATED_BY_REPAIR`
- `A11_RELATIONSHIP_UNAFFECTED_DIRECT_GROUP_RESULT`

Do not use repair as permission to invent new filters or retune thresholds.

---

# 4. Phase B preflight — certify original ranks 9–20 for the substitution study

The substitution challenger creates potential trades that were not in the frozen top-eight ledger. Therefore the relevant original ranks 9–20 are **new research observations** and must be verified before they can affect economics.

For every frozen cohort, reconstruct the corrected original rank order through rank 20 using the same point-in-time universe/ranking rules as R2. Do not rerank with a new factor.

For any rank 9–20 name that the frozen substitution rule could choose, verify to the same practical standard needed for scoring:

- point-in-time security identity and common-stock eligibility;
- complete ranking and feature history needed by the frozen rules;
- corporate actions affecting ranking/feature units and the H10 lifecycle;
- entry-session causal pre-order observation;
- H10 exit/lifecycle data, including documented halt/open status;
- no manual next-name substitution for a data failure.

If the rule would choose a replacement whose evidence cannot be resolved, that challenger/cohort is **unscorable until resolved**. Do not silently keep the original name, skip to the next substitute, or treat missing data as a strategy condition.

Limited retrieval within the already-authorized Theta Stocks Professional entitlement and public issuer/SEC/exchange evidence is permitted for these existing-period candidate names only. No new paid subscription, no new holdout scoring, no options/sub-minute program.

---

# 5. Challenger definitions — frozen before any economics are scored

Write and commit `reports/cg_arrow012_challenger_freeze.json` after Phase A and candidate certification but **before** computing challenger outcomes. It must contain formulas, exact A11 threshold source/value, cohort IDs, code/input hashes, and the holdout embargo declaration.

No thresholds or formulas may change after challenger scoring begins.

## C0 — Incumbent control

**Incumbent Momentum+Volume Equity-Scaled R5**

- original corrected top eight;
- original R5 FULL/HALF/QUARTER rules;
- H10;
- causal pre-order quantity convention;
- Arrow 010 equity reference: marked challenger-account equity at signal-session close;
- equity scale = reference equity / 100,000;
- causal share flooring from the same pre-order price convention.

Reproduce Arrow 010 exactly.

Also keep the causal **fixed-dollar R5** version as a noncompounded diagnostic so stock/selection effects can be distinguished from compounding effects.

## C1 — Rank-One 1.50x Reallocation

Purpose: test whether the strongest observed component deserves more of the **same cohort capital**, without dropping the other seven names or adding leverage at the base-allocation layer.

For each cohort, let the incumbent R5 base-dollar intended notionals at $100,000 be `b1 ... b8`, where `b1` belongs to original rank one. Let:

`T = sum(b1 ... b8)`

Set:

`rank1_target = 1.50 * b1`

Fund the increase entirely from ranks 2–8:

`other_scale = (T - rank1_target) / sum(b2 ... b8)`

Then:

- rank-one base allocation = `rank1_target`;
- each rank 2–8 base allocation = original `bi * other_scale`;
- assert the sum equals `T` at full precision before integer-share flooring;
- all eight names remain in the cohort;
- original R5 tier information is otherwise preserved;
- if the formula would create a nonpositive other scale, fail the cohort rather than invent a cap.

For the equity-scaled account, multiply these base allocations by that challenger account's causal signal-close equity scale, then derive causal integer shares. Thus C1 changes **relative allocation**, not the cohort's base intended capital at a given equity.

No 1.25x/1.75x sweep. **1.50x is the only rank-one overweight tested in Arrow 012.**

## C2 — Off-High Substitution from Original Ranks 9–20

Purpose: test the user's question: can weaker slots 2–8 be improved by trading a little less prior-return extremeness for stronger evidence that the reversal has already begun?

Use the exact Arrow 011 frozen value `close_vs_high20_is_median` from `reports/cg_arrow011_hypothesis_freeze.json` as threshold `M` (approximately 5.5% below the recent high, but use the stored exact value).

For each frozen cohort:

1. **Original rank one is protected and can never be replaced.**
2. Among original ranks 2–8, define a removable candidate as one with `close_vs_high20 >= M` (the A11 "near-high" side).
3. Among original ranks 9–20, define a replacement candidate as one with `close_vs_high20 < M` (the A11 "off-high" side) and complete/certified required evidence.
4. Let `k = min(number of removable originals, number of eligible replacements)`.
5. If `k > 0`, remove the `k` removable original names with the **worst original ranking positions first** (rank 8 before 7 before ... before 2).
6. Add the `k` eligible replacement names with the **best original ranking positions first** (rank 9 before 10 before ... before 20).
7. Never search below rank 20. Never replace rank one. Never choose among candidates using outcomes.
8. Resulting cohort must contain exactly eight unique names.

### C2 sizing and cohort-budget neutrality

Compute the frozen R5 momentum/volume tier for every name in the substituted lineup using that name's own pre-entry features. Let the raw R5 base notionals for the new lineup sum to `S`.

Let `T` be the original incumbent top-eight R5 base-dollar cohort total for that cohort.

Normalize every substituted-lineup raw R5 base notional by:

`budget_scale = T / S`

so that the substituted cohort's base intended total equals the incumbent's `T`, while the new lineup retains the relative R5 tier information of its actual names.

Then apply the fixed-dollar or equity-scaled account rules normally.

This prevents the substitution result from winning simply because the replacement names happened to generate larger raw R5 tier totals.

## C3 — Combined Rank-One Reallocation + Off-High Substitution

Start from the C2 substituted lineup and its budget-normalized R5 base allocations summing to incumbent `T`.

Rank one remains the original protected rank-one name. Apply the same C1 1.50x rank-one reallocation to those normalized allocations, proportionally reducing the other seven so the total still equals `T`.

Then apply the account's causal equity scaling and share flooring.

This is the interaction test. Do not infer C3 by adding C1 and C2 results; build its own chronological account.

---

# 6. Scoring design — existing year only

Score C0, C1, C2, and C3 on the already-exposed September 2025–August 2026 sample.

Report odd-month IS, even-month internal confirmation, and ALL for description, but state clearly that the even months have already been viewed many times and are **not pristine OOS**. Because the challenger formulas are predeclared in this arrow, do not retune them based on either split.

The future additional year is not part of Arrow 012.

## Primary economic view

Primary: **complete equity-scaled chronological account**, starting at $100,000, with each challenger's own signal-close equity path.

This is essential: changed early P&L changes later position sizes. Do not apply challenger trade P&L to the incumbent equity path.

## Secondary diagnostic view

Also run the same C0–C3 base allocations under causal fixed-dollar sizing. This helps isolate underlying trade/selection/allocation effects from compounding.

Do not run legacy-fill, H8/H9, new timing, leverage caps, redeployment, Kelly, volatility targeting, long-side research, or broad threshold grids.

---

# 7. Whole-engine outputs and interaction accounting

For C0–C3 publish side by side, for both fixed-dollar and equity-scaled views where applicable:

- intended / filled / completed / open counts;
- starting and ending marked equity;
- marked account P&L at 2026-08-31;
- eventual completed-trade P&L;
- return on starting equity;
- wins/losses/flats, hit rate, average winner/loser, payoff ratio, profit factor;
- maximum drawdown dollars and percent of peak;
- worst day;
- time underwater;
- mean / 95th-percentile / peak gross exposure and gross/marked-equity ratio;
- entry turnover / notional;
- single-name and rank-one concentration metrics;
- positive/red/flat months, red-month sum, worst/best/median month;
- runoff and open-obligation treatment;
- exact daily cash-minus-short-liability reconciliation.

Apply `cg_lab_monthly_account_reporting_v1` to every complete account comparison: all 12 individual months, monthly P&L, monthly return, month-end equity, exact chaining/reconciliation.

### Rank-one reallocation attribution

For C1 versus C0 report:

- extra P&L from the increased rank-one allocation;
- P&L surrendered or gained by proportionally reducing ranks 2–8;
- change in worst rank-one loss contribution;
- change in concentration, drawdown, worst day, and gross/equity;
- whether the complete account improves, not merely the rank-one subset.

### Substitution attribution

For C2 versus C0 report:

- number of cohorts with 0/1/2/... substitutions;
- number and original rank of outgoing names and replacement ranks;
- average/median distance-from-high of outgoing versus incoming names;
- paired sizing-neutral H10 return of outgoing versus incoming trades;
- paired modeled net contribution at equalized cohort budget;
- profit forfeited on outgoing winners and profit gained by incoming winners;
- whether substitutions improve the complete fixed-dollar and equity-scaled account.

Detailed symbol-level paired records stay private.

### Interaction

For key additive quantities such as eventual completed-trade P&L and cutoff marked P&L, publish:

`interaction = C3 - C1 - C2 + C0`

A nonzero interaction is expected because lineup changes, integer shares, overlapping positions, and equity compounding can make effects non-additive. Explain rather than hide it.

For nonlinear risk metrics such as max drawdown, report the four actual values side by side; do not force an additive decomposition.

---

# 8. Scientific safeguards

The incumbent is protected throughout this arrow.

- No Arrow 008/009/010/011 artifact is overwritten.
- No existing strategy rule is changed in place.
- Challengers receive new IDs/configs and separate ledgers.
- A repair to analysis statistics cannot alter a frozen trade or account.
- A candidate that looks good as a subset must still prove itself in a complete account.
- A candidate with more profit solely because it uses more base cohort capital fails the intended comparison; cohort base budgets are explicitly equalized.
- Do not describe a challenger as "better" merely because one summary statistic is higher.
- Preserve negative findings and interaction failures.
- If C1 and C2 individually help but C3 hurts, that is an important result, not a reason to retune C3.
- Do not invent a fourth challenger after seeing results.

All C0–C3 formulas are to be preserved for the future untouched-year reveal. **Arrow 012 must not choose new thresholds after scoring.** The next holdout can test all four as pre-registered configurations in one batch.

---

# 9. Audit requirements

At minimum test and document:

1. All frozen baseline hashes/economics reproduce before research.
2. Arrow 011 original files remain byte-identical.
3. Row permutation cannot change repaired relationship results.
4. Constant/tied feature tests cannot create arbitrary within-cohort separation.
5. PRE_ORDER and SIGNAL_CLOSE behavioral leakage tests pass.
6. Scored cohorts are exactly the frozen 52; no new-year signal cohort is read/scored.
7. Original C0 lineup and allocations reproduce Arrow 010 exactly.
8. C1 keeps all eight names and preserves each cohort's base intended total `T` before flooring.
9. C2 protects rank one, uses only original ranks 9–20, follows the deterministic outgoing/incoming priority, and produces exactly eight unique names.
10. Every actually selected C2/C3 replacement has complete required certification; data failure never becomes a strategy choice.
11. C2 base allocations preserve original cohort budget `T` after R5-relative normalization.
12. C3 preserves `T` and is built independently rather than arithmetically inferred.
13. Equity-scaled sizing uses each challenger's own causal signal-close marked equity and no future information.
14. Daily account identities, monthly cent chaining, runoff/open treatment, and independent trade/cohort/account reconciliation pass for every book.
15. Public/private separation and credential hygiene pass.

Extend the independent oracle rather than trusting new engine outputs. Recompute lineup, base budget, reallocation/substitution decisions, integer shares, trade P&L, cohort subtotals, and daily marked equity from stored inputs wherever practical.

---

# 10. Required outputs

Public-safe:

- `reports/cg_arrow012_repair.md`
- `reports/cg_arrow012_repaired_relationships.csv`
- `reports/cg_arrow012_challenger_freeze.json` — committed before challenger scoring
- `reports/cg_arrow012_challengers.md`
- `reports/cg_arrow012_account_summary.csv`
- `reports/cg_arrow012_monthly_account.csv`
- `reports/cg_arrow012_substitution_summary.csv`
- `reports/cg_arrow012_interaction.csv`
- `reports/cg_arrow012_manifest.json`
- `reports/cg_arrow012_commands.txt`
- relevant code/tests.

Private, ignored, individual files under `handoff/outgoing/cg_arrow012/`:

- repaired row/cohort diagnostic tables as needed;
- `top20_candidate_audit.csv`;
- `substitution_pairs.csv`;
- per-challenger trade ledgers;
- per-challenger cohort allocation audits;
- per-challenger daily account ledgers;
- independent oracle/reconciliation rows.

Do not commit symbols/trade-level proprietary rows, raw vendor data, credentials, or holdout-year results.

---

# 11. Interpretation statuses

For Phase A findings use the repair statuses in section 3.

For C1/C2/C3, conclude separately:

- `CHALLENGER IMPROVES COMPLETE HISTORICAL ENGINE — AWAIT PRISTINE HOLDOUT`
- `CHALLENGER IMPROVES PROFIT BUT DEGRADES RISK/CONCENTRATION — AWAIT HOLDOUT WITH CAUTION`
- `CHALLENGER DOES NOT IMPROVE COMPLETE HISTORICAL ENGINE`
- `CHALLENGER INCONCLUSIVE — exact reason`

These labels are research statuses only. No production promotion is authorized.

End the report with:

`NEXT STEP: PRISTINE ADDITIONAL-YEAR REVEAL OF C0/C1/C2/C3 AFTER DATA CERTIFICATION`

---

# 12. Runtime and execution discipline

This is narrow but includes candidate verification and four complete account replays.

**Planning allocation: target 75–90 elapsed minutes; hard stop 120 minutes including tests, reports, commits, and push.**

Use available concurrency for independent candidate/data verification and replay support, bounded by the host and existing source limits. Keep dependent account compounding serial per challenger. Do not start unrelated mechanism research if the core work finishes early.

If candidate certification creates a finite evidence branch that cannot be closed within the hard stop, report the exact blocker and leave the affected challenger inconclusive rather than weakening the evidence standard.

Commit and push the pre-score challenger freeze, then commit and push final public-safe Arrow 012 outputs. Verify remote equality and stop for ChatGPT audit. Do not begin the future-year reveal.