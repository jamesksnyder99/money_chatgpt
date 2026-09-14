# CG Arrow 007 — Opus: certify corporate actions, harden the engine, freeze the trustworthy baseline, then complete H1–H10

## Mission

**Executor: Opus in Claude Code.** This is the verification-completion run the user explicitly requested. The objective is not merely to reduce uncertainty; it is to remove every material, resolvable inconsistency that prevents us from believing the PARENT / R4 / R5 historical results, then complete the already-authorized H1–H10 holding-period study on the certified entry ledger.

The user is willing to spend materially more time on correctness than prior arrows. Treat scientific certainty, reproducibility and explicit unresolved evidence as higher priority than runtime. Do not protect a positive result and do not assume the remaining flags are false positives. **Repair the evidence and engine, then accept whatever the numbers say.**

Work only in `C:\Users\james\money_chatgpt`, remote `jamesksnyder99/money_chatgpt`. Never access `C:\Users\james\Money`. The repo-root `.env` is authorized local ThetaData configuration only; confirm `git check-ignore .env` at start and before every push and never print/log/stage/commit credential values. No live trades, subscription/account changes, options, or unrelated model research. Stop after Arrow 007; do not begin Arrow 008.

### Runtime policy

This is **quality-first**, not another 90-minute search. Allocate up to **300 elapsed minutes** for the complete run, including primary-source event work, reranking/replay, horizon IS/freeze/OOS, tests, reports and push. Do not burn time to satisfy a quota; finish early if all gates are genuinely closed. If minute 300 arrives while a finite, predeclared primary-source verification branch is clearly progressing and is required to close the evidence gate, finish that branch with a modest overrun and report the overrun/reason. Do not open new work after the limit. If an external source makes a material event literally irresolvable, publish the exact case/effect and stop rather than inventing a factor or hand-substituting another stock.

## Starting checkpoint

Start from the Arrow 006 public result at `dfcac94d12cfe8a5df4dd045d0beff3dd563dc76` or its descendant containing this arrow. Read:

- `CLAUDE.md`, `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, this arrow.
- `reports/cg_arrow006_verification.md`, `cg_arrow006_manifest.json`, `cg_arrow006_file_changes.md`, `cg_arrow006_commands.txt`, `cg_arrow006_corporate_actions.json`, `cg_arrow006_ranking_window_diagnostics.json`, `cg_arrow006_ranking_reconciliation.csv`.
- `src/verification/r4r5_{data,replay,repair,rank,export,oracle}.py`, `scripts/cg_arrow006_{run,acquire,horizons}.py`, and Arrow 006 tests.

Preserve all earlier reports/results as historical evidence. Do not rewrite Arrow 003–006 artifacts to match Arrow 007 conclusions.

Arrow 006 already established working authenticated acquisition, complete selected-trade lifecycle data except the documented EFTY halt, a restored `$10–$80` rule field, test-issue exclusion, 52/52 ranking fields with no unresolved vendor endpoints, exact accounting reconciliation, and a large unresolved question: ranking-window corporate actions/discontinuities. It reported 121 R2 completed trades whose selected-name 15-session ranking windows contain an unexplained `>=2x` discontinuity, plus 64 analogous R1 trades. The user specifically wants to know whether the apparent R2 upside is real after precise action handling.

## Phase 0 — freeze the weekly calendar rule before any scoring

The user has now specified a permanent weekly holiday fallback. Implement this as a common schedule helper before new scoring and test it independently:

1. Each weekly cohort has a **nominal Wednesday signal anchor**.
2. If nominal Wednesday is not an exchange session, roll **backward one calendar day at a time** until the most recent valid exchange session. Do not skip the week solely because Wednesday is closed.
3. Entry is the **first valid exchange session strictly after the signal**. Thus a normal Wednesday signal enters Thursday; a Wednesday holiday normally maps signal to Tuesday and entry to Thursday; a Thursday holiday after a normal Wednesday signal enters Friday.
4. Hn exits remain n exchange sessions after the actual fill session.
5. Early-close sessions use their actual final RTH minute.
6. Keep the nominal weekly anchor fixed; do not create two cohorts for one week or let a holiday permanently shift later weeks.

For September 2025–August 2026 this repair is expected to produce no cohort change because there is no full Wednesday closure in the study window. **Prove that expectation with a schedule-diff test.** If any current-sample cohort changes, stop and explain before mixing the calendar change into economic comparisons.

## Core principle for unresolved corporate actions — NO manual rank-9 substitution

Do **not** remove a suspicious selected stock and manually replace it with the next cached name.

The only acceptable path is:

**document/resolve the event → put all affected history into consistent units → recompute eligibility/ranking/features for the entire point-in-time field → rerank → let the corrected top eight emerge mechanically.**

If the corrected candidate falls below rank 8, the replacement is whoever naturally becomes rank 8 after full reranking. If it remains top 8, keep it. If an event remains materially unresolved, the cohort is not certifiable; do not assume the stock out and do not assume it in.

This rule applies equally to favorable and unfavorable outcomes.

## Phase 1 — build a precise corporate-action/security-identity layer

### 1A. Canonical event schema

Create/version a canonical Arrow 007 action table with at least:

- stable security identifier where available, historical ticker and successor ticker;
- event type (`reverse_split`, `forward_split`, ADS ratio change, ticker/CUSIP change, merger/exchange, spin/distribution, special dividend, delisting/suspension/halt, other quantity-changing event);
- announcement/source date, record/ex date if applicable, **effective/first-trading session**;
- exact ratio/factor and factor convention;
- authoritative source URL/type (prefer exchange, SEC or issuer; commentary is explanatory only);
- effect on price units, share units, share volume, cashflows and eligibility;
- confidence/status (`PRIMARY_VERIFIED`, `SECONDARY_CORROBORATED`, `UNRESOLVED`);
- notes for fractional/cash-in-lieu treatment when relevant.

Keep raw observed prices unchanged. Apply transformations only in derived comparison/accounting units.

### 1B. Exact split/unit mathematics

Use one tested convention consistently. The existing convention is acceptable if proved:

`price_factor = old shares per new share`.

For an event effective between an earlier observation and a later as-of date:

- convert earlier **price** into later share units by multiplying by `price_factor`;
- convert earlier **share volume** into later share units by dividing by `price_factor`;
- held **shares** crossing the event divide by `price_factor`;
- per-share basis/entry price crossing the event multiplies by `price_factor`;
- economic position value must be neutral immediately across a pure split before market movement/costs/cash-in-lieu;
- price × share-volume dollar volume should remain neutral apart from rounding/source differences.

Examples: a 1-for-100 reverse split has factor 100; a 5-for-1 forward split has factor 0.2.

Add synthetic tests for reverse split, forward split, multiple events in one lookback/hold, action exactly on signal day, exactly on fill day, exactly on exit day, and ticker change across an action.

### 1C. Selection-time handling

A split can affect selection even if it occurs before entry. For every candidate used in the 15-session ranking and R4/R5 feature histories:

- transform ranking endpoints to a common signal-session share unit using **all** documented events between them;
- transform the 20-session share-volume history to signal-session share units before computing the arithmetic mean/volume ratio;
- transform prior close used for the `$10–$80` signal-day eligibility test when an event effective by the signal changes the share unit; verify that prior-dollar-volume remains economically consistent;
- handle ticker/security identity changes so lookbacks follow the same security without stitching unrelated issuers;
- never use a future action to exclude an earlier candidate.

After applying events, recompute the 15-session return, eligibility, features and ranks from scratch.

### 1D. Holding-period handling

When an event occurs after entry and before exit:

- adjust held quantity/basis exactly on the effective trading session;
- preserve economic value across a pure split;
- apply the observed post-event exit in post-event units;
- carry documented cash distributions/merger consideration where known;
- for fractional theoretical short liabilities, seek/document event terms; if historical broker cash-in-lieu cannot be established, preserve a theoretical fractional liability and disclose the unknown broker treatment rather than rounding favorably;
- ticker changes must continue the same position under the successor security;
- suspensions/halts remain genuine market events and are not treated as missing data.

### 1E. Evidence census — not merely a `>=2x` heuristic

The Arrow 006 `>=2x` screen is triage, not proof of completeness. A 3-for-2, 4-for-3 or other smaller action can still alter ranking and eligibility.

Use the strongest machine-readable/exchange/issuer/SEC corporate-action sources available without a new paid subscription. Prefer an exchange daily-list/corporate-action source if accessible, then SEC/issuer primary evidence. The objective is a **scoped event census covering the securities/dates that can affect these 52 cohort rankings and selected holds**, not just the 121 already-flagged trade instances.

At minimum:

1. Deduplicate the 121 R2 and 64 R1 trade-instance flags into unique symbol/event-date investigations.
2. Incorporate already known NVA, BNAI, SMX and inherited events.
3. Add primary-source events already strongly indicated by Arrow 006 (including FGL, DFNS and WETO if confirmed by authoritative sources) with exact factors/effective sessions.
4. Search the relevant ranking/feature windows for additional quantity-changing events below the old 2x threshold using the authoritative event source where possible; do not rely solely on price/volume heuristics.
5. For any suspicious price/volume discontinuity without an event record, research it and classify it as documented market move or unresolved; do not infer a factor from the return.

A secondary article may explain a market move, but it does not certify that no split occurred. Prefer exchange/issuer/SEC evidence for unit-changing questions.

## Phase 2 — iterative reranking to a fixed point

Corporate-action correction can change the top eight and introduce newly selected names whose own histories need review. Therefore use an iterative fixed-point loop:

1. Apply the current canonical event/identity map to the complete `$10–$80`, `$10M+`, common-stock, non-ETP, non-test-issue field.
2. Recompute every cohort's eligibility, 15-session returns, top eight, R4/R5 features and sizing.
3. Review the newly selected names' ranking/feature/holding windows for unresolved action/identity events.
4. Resolve/add any newly material event and rerun from step 1.
5. Stop only when another complete rerank creates **no new unresolved material selected-name event and no uncertified candidate event capable of changing top-eight membership**.

Publish convergence iterations and changed memberships. Never freeze an intermediate attractive iteration.

### Ranking comparison must use three distinct baselines

Arrow 006's `old_top8` comparison was too ambiguous. Publish separately:

- `R0_RAW_CACHE_TOP8`: raw historical cached rank order before documented action repairs (diagnostic only);
- `R1_RECORDED_TOP8`: the actual historical selections used by the frozen PARENT/R4/R5 books, preserving their contemporaneous decision record for forensic reconciliation;
- `R2_CERTIFIED_TOP8`: unchanged rules on complete, action-normalized, test-cleaned, point-in-time inputs.

For each cohort distinguish:

- membership additions/drops (set change),
- order-only changes,
- field-size changes,
- action-normalization cause,
- restored-data cause,
- test/identity cause,
- feature/sizing-tier changes.

Do not count a pure order change as a membership change.

## Phase 3 — engine and acceptance-control repairs identified in the Arrow 006 audit

Repair these before any real horizon scoring:

### 3A. Structural data acceptance

A partition with `RETRIEVED_WITH_ISSUES`, duplicate/conflicting timestamps, unresolved OHLC inconsistency or other structural defects cannot silently enter a VERIFIED trade/rank. Review and resolve/re-request it, or gate the affected result. Update coverage logic so every issue-status is either explicitly accepted with reason or blocking. Add end-to-end tests.

### 3B. Action-window certification

Do not clear a ranking window merely because *some* documented event exists inside it. Apply **all** documented events in the window, recompute the adjusted series, then rescreen the adjusted path. Any remaining unexplained material discontinuity remains a review item. The event's effective date and security identity must match the observed unit change.

### 3C. IS/OOS risk-account separation

The current horizon code filters trade PnL by split but computes several risk metrics from the all-cohort daily book. Fix this.

For horizon research, build independent books by original signal ownership:

- IS-owned entries only, with their causal lookbacks and full holding lifecycles allowed to cross month boundaries;
- OOS-owned entries only;
- ALL chronological account separately.

IS DD, worst day, exposure, red-month ride and underwater time must not contain OOS-owned positions. OOS metrics must not contain IS-owned positions. The ALL account is a separate operational view.

### 3D. Runoff and denominators

Separate and label:

- calendar account through 2026-08-31;
- full scheduled runoff of August-signal cohorts into September;
- completed-trade PnL by original signal ownership;
- any still-open documented-event liability.

Do not divide September runoff PnL by 251 and call it twelve-month account income. Publish denominator/basis with every $/session metric.

### 3E. Halts/open-position handling across horizons

Do not form Hn→H(n+1) comparisons merely by intersecting the completed-trade sets and thereby drop a trade that becomes trapped at the longer horizon.

For every intended R2 trade/horizon carry a state: completed scheduled exit, documented no-entry, documented halt/open obligation, other event treatment. Same-trade horizon increments must report:

- paired completed→completed PnL change;
- completed→open/halted transition count and marked/open obligation separately;
- open→completed transition if applicable;
- no silent sample shrinkage.

EFTY and any analogous event are part of the economics, not rows to delete.

### 3F. Quantity/execution causality

Preserve two predeclared panels:

1. **LEGACY_FILL_QTY** — historical fill-close price also determines integer shares, for exact comparability with the frozen lineage.
2. **CAUSAL_PREORDER_QTY** — integer shares determined only from the last completed pre-order bar, with the same final-minute execution reference.

The causal panel is the more operationally defensible quantity convention. Do not choose between panels after seeing OOS. Publish H10 reconciliation for both. For the H1–H10 study, compute both panels if computationally trivial; if so, treat LEGACY as the historical-comparison panel and CAUSAL as a predeclared robustness panel, not as a second optimization search.

## Phase 4 — certify and freeze the baseline, including the possible upside

The user specifically wants to know whether the large Arrow 006 R2 upside is genuine.

After the fixed-point action/ranking loop and code repairs, produce a **baseline truth report** for PARENT, R4 and R5 with:

- R1 historical-decision reconstruction under repaired observations/actions;
- R2 certified unchanged-rule reconstruction on complete inputs;
- legacy-fill and causal-preorder quantity panels;
- IS, OOS, ALL completed-trade and account views;
- wins/losses/flats, hit rate, avg winner/loser, payoff ratio, profit factor;
- calendar DD/worst day/red months/time underwater;
- average/peak gross and concentration;
- inherited modeled commission/spread, double-spread, and 0/10/30% annualized borrow scenarios;
- documented open/halt liabilities;
- unknown dividend/locate/financing statuses.

### Required upside decomposition

Quantify the difference between R1 and certified R2 without overselling it as a single causal effect. At minimum show:

- net PnL from names common to R1/R2;
- net PnL from names newly added by restored/corrected ranking;
- net PnL from names dropped versus R1;
- per-cohort R1→R2 delta;
- contribution from data-field restoration;
- contribution from test-issue removal;
- contribution from documented corporate-action normalization;
- contribution from feature/sizing changes;
- concentration of the R2 uplift by symbol/cohort/month.

If the corrected R2 remains materially stronger after certification, **freeze it as the canonical verified entry ledger before horizons**, with hashes and no post-horizon membership/sizing changes. If it collapses, freeze that result just as firmly. The goal is truth, not preservation of the upside.

### Baseline release gate

Open horizons only when all of the following are true:

- complete point-in-time field for all 52 cohorts;
- no unresolved material corporate-action/security-identity event in any selected R2 ranking/feature/holding path;
- no unresolved candidate event capable of changing top-eight membership;
- all valid entries and H10 endpoints priced or governed by documented causal event treatment;
- every structural data issue accepted/resolved explicitly;
- action-adjusted ranking series pass the post-adjustment integrity screen;
- independent oracle reconciles trade/cohort/daily-account arithmetic;
- stale marks do not masquerade as completed exits;
- R2 ledger, action table, code and input hashes committed/frozen.

Unknown historical borrow/dividend/locate amounts may remain explicitly scenario-only; that prevents calling the result broker-executable historical net profit, but it does not block a price/action/model-cost horizon study.

## Phase 5 — H1–H10 completion after the certified freeze

The user wants this run to complete the horizon study if the evidence gate can be closed.

Authorized grid remains PARENT, R4, R5 × H1…H10. Hn = n exchange sessions after fill; fill = H0. All horizons within a quantity panel clone the **same frozen R2 entry ledger, entry timestamp/price, initial shares, sizing state and entry costs**. Only exit age changes.

No capital redeployment, reinvestment, compounding, reserve substitution, dynamic sizing, stops or state-dependent exits in Arrow 007. Those are intentionally parked for the next strategy arrow after we know the trustworthy horizon economics.

Before scoring IS, acquire/validate any newly required H1–H9 endpoint observations created by the final certified selection. Missing data cannot create a smaller favorable sample.

### IS/freeze/OOS procedure

1. Score all horizons on **IS-owned books only** using repaired split-specific accounting.
2. Publish the complete IS matrix, same-trade increments, holding-age curves and any profit-first/ride-first horizon interpretation.
3. Predeclare/freeze any preferred horizon(s) before viewing H1–H9 OOS. Choosing H10 or choosing none is valid. Do not fit per-tier horizons in this arrow.
4. Commit the horizon rules, baseline/action/data/code hashes, entry-ledger hash and IS interpretation.
5. Reveal **all H1–H10 OOS cells once in one batch** for both predeclared quantity panels if both are run.
6. No post-OOS horizon switching presented as confirmed.
7. Replay ALL chronologically as a separate operational account view.

H10 in each panel must reproduce its corresponding frozen certified baseline exactly.

### Horizon metrics

For every family/horizon/split/panel report:

- intended, filled, completed, documented-event/open counts;
- wins/losses/flats and hit rate;
- average winner/loser, payoff ratio, profit factor;
- gross PnL and modeled net;
- double-spread, 10% and 30% annualized borrow scenarios;
- clearly named $/session denominator;
- continuous DD $, DD %, worst day, underwater sessions;
- calendar red-month count/loss sum, worst/median month;
- average/peak gross, exposure-dollar-days and turnover;
- R4/R5 sizing-tier contributions;
- August-31 calendar account result, September runoff result, and still-open obligations separately.

Publish H1→H2 … H9→H10 same-trade deltas without silently dropping event-state transitions. Holding-age H0…H10 curves must be labeled as cross-trade age curves, not account-equity curves.

## Phase 6 — private user audit files and public evidence

Regenerate versioned private local files under `handoff/outgoing/cg_arrow007/`:

- `r4r5_verified_trades.csv` — canonical tidy certified ledger;
- `r4r5_verified_cohort_audit.csv` — eight intended slots then cohort subtotal, with signal-month/split/period totals;
- `r4r5_cohort_matrix.csv`;
- `r4r5_trade_exceptions.csv`;
- `r4r5_daily_account.csv`;
- `r4r5_corporate_action_ledger.csv` — every relevant event investigation, evidence/status/factor and affected cohorts;
- `r4r5_ranking_reconciliation.csv` — R0 raw cache vs R1 recorded vs R2 certified;
- `r4r5_r2_upside_bridge.csv` — cohort/symbol decomposition of R1→R2;
- after horizon release: `r4r5_horizon_trade_paths.csv` and `r4r5_horizon_summary.csv`.

The user's cohort audit must allow direct inspection of each entry/exit price, quantity, action adjustment, modeled PnL and subtotal. Unresolved rows may never be hidden by a subtotal labeled verified.

Public safe outputs should include:

- `reports/cg_arrow007_verification.md`;
- `reports/cg_arrow007_corporate_actions.json` and safe action-census summary;
- `reports/cg_arrow007_ranking_reconciliation.csv` without proprietary raw bar values;
- `reports/cg_arrow007_upside_bridge.csv` safe aggregates;
- `reports/cg_arrow007_manifest.json`;
- `reports/cg_arrow007_file_changes.md`;
- `reports/cg_arrow007_commands.txt`;
- `reports/cg_arrow007_horizon_freeze.json` and, if released, `reports/cg_arrow007_horizons.csv` / `cg_arrow007_horizon_report.md`.

Raw vendor data, detailed proprietary trade observations, `.env` and private CSVs remain ignored/local.

## Phase 7 — tests and adversarial audit

Add focused tests for every identified failure mode, including:

- nominal-Wednesday holiday rollback + forward next-session entry; no current-sample schedule change;
- reverse/forward/multiple split unit neutrality in ranking, volume feature and held-position accounting;
- split on signal/fill/exit boundaries;
- ticker/security identity continuity;
- full rerank after action adjustment; no manual rank-9 substitution;
- fixed-point iteration introducing a new selected name with its own event;
- test-issue exclusion;
- `RETRIEVED_WITH_ISSUES` blocks VERIFIED status unless explicitly resolved;
- post-action adjusted-series integrity rescreen;
- R0 raw/R1 recorded/R2 certified ranking comparison semantics;
- IS risk metrics contain no OOS-owned positions and vice versa;
- runoff/account denominators correct;
- documented halt not silently dropped from horizon comparisons;
- same entry ledger/shares across horizons within each panel;
- H10 identity with frozen baseline;
- independent PnL/cash/oracle and cohort subtotal conservation;
- one-batch OOS gate and no OOS-driven rewrite;
- `.env`, raw vendor data and private CSVs excluded from Git.

Run the entire `tests/` suite under ignored lab temp paths.

Then perform an explicit adversarial review before declaring completion:

- choose several high-PnL and high-loss trades and recompute entry→action→exit PnL independently from the CSV/event ledger;
- choose several split-affected ranking cases and manually reconstruct the adjusted 15-session return/volume ratio from stored observations plus documented event factors;
- verify the eighth/ninth rank boundary for several changed cohorts;
- verify R4/R5 sizing tier and quantity for several cases;
- reconcile monthly/account totals to the trade ledger and open obligations;
- prove public Git contains no credentials or proprietary detailed market data.

## Terminal handoff

Report:

1. elapsed time and any justified overrun;
2. number of unique corporate-action/security-event cases investigated, primary-source verified, market-move resolved and unresolved;
3. convergence iterations to the final R2 top eight;
4. final R1 and **certified R2** economics for PARENT/R4/R5, both quantity panels;
5. whether the Arrow 006 R2 upside survived, shrank or disappeared, with decomposition;
6. exact remaining limitations (especially borrow/dividend/locate/execution realism);
7. horizon gate result;
8. if released, complete H1–H10 IS/OOS/ALL findings and frozen preferred horizon interpretation;
9. full test count and adversarial spot-check results;
10. local private CSV paths;
11. final public commit SHA and remote equality.

Do not call the job complete merely because the numbers look plausible. Completion means the defined verification gates are actually closed or the remaining external blocker is explicit and irreducible.