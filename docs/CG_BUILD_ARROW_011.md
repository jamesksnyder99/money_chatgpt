# CG Build Arrow 011 — Winner-Fade Anatomy: Pre-Entry Characteristics and Within-Cohort Outcomes

Executor: **Fable in Claude Code**. Research director/auditor: ChatGPT.

Authorized September 14, 2026. This replaces the proposed next capital-constraint/redeployment experiments; those are parked, not rejected. The user approved a four-hour discovery assignment and changed the allocation to **70% directed work / 30% Fable-led investigation**.

## 1. Mission and success

Answer two complementary questions on the existing Winner-Fade Short sample:

1. What pre-entry characteristics are associated with the fade, and what explains differences between the existing sizing variants and their monthly results?
2. Within each weekly basket of eight, what information available BEFORE entry distinguished eventual winning shorts from losing shorts, or stronger outcomes from weaker ones?

The principal model is **Momentum+Volume-Sized Short (R5), Corrected-Universe Replay (R2), 10-Session Hold (H10)**. Volume-Sized Short (R4) and Equal-Dollar Short (PARENT) are explanatory reference books, not additional model-search programs. Fixed-dollar and equity-scaled Momentum+Volume books are two economic views of the same price opportunities, not independent discoveries.

Build a complete, auditable cohort/trade atlas; identify recurring relationships and counterexamples; distinguish stock-return predictability from sizing and account-path effects; and leave precisely specified follow-on experiments. A careful negative result is useful. A higher backtest total is not required for success.

Hypotheses are welcome; a preferred answer is not. Use interpretable comparisons, sequences, small state maps and counterexamples, not a black-box classifier or coefficient-significance mining. An observational association is not proof of why a particular stock moved. Use the terms association, recurring pattern and plausible mechanism accordingly.

## 2. Workspace, source order and frozen references

Work ONLY in `C:\Users\james\money_chatgpt`, remote `jamesksnyder99/money_chatgpt`. Never access `C:\Users\james\Money`, directly or via links/imports/caches. No live orders, broker changes, purchases, paid data upgrades or account changes.

Pull `main` with `git pull --ff-only origin main` without overwriting legitimate local work. Read:

- `CLAUDE.md`, `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, this arrow;
- `reports/cg_arrow008_verification.md`, `reports/cg_arrow008_manifest.json`, `reports/cg_arrow008_certified_baseline.csv`;
- `reports/cg_arrow009_monthly_report.md`, `reports/cg_arrow009_monthly_account.csv`, `reports/cg_arrow009_manifest.json`;
- `reports/cg_arrow010_equity_sizing.md`, `reports/cg_arrow010_manifest.json`, `reports/cg_arrow010_equity_summary.csv`, `reports/cg_arrow010_commands.txt`;
- the Arrow 007/008 horizon summaries and private paths listed in those manifests, as needed for holding-path diagnostics;
- `src/verification/r4r5_data.py`, `r4r5_rank.py`, `r4r5_replay.py`, `r4r5_accounting.py`, `r4r5_oracle.py`, `r4r5_monthly.py`, and `r4r5_equity.py` as applicable.

The last completed research checkpoint when this arrow was written is `4a4d201ea8c18c3523bc76d5894fc16a9ed0673d` (Arrow 010). Arrow 008 and Arrow 009 are the baseline and monthly-account references. Use their manifests for exact precision and provenance, not rounded prose.

### Preflight acceptance, before discovery

Verify local input hashes against the relevant manifests. Reuse the independent oracle and cached inputs to reconcile the exact books used; do not confuse successful imports or passing synthetic tests with a completed data replay.

Expected reference values, rounded only for orientation:

| Reference | Eventual completed-trade P&L | Marked account P&L at 2026-08-31 |
|---|---:|---:|
| Momentum+Volume, fixed dollars, legacy fill quantities | 129,092.60 | 129,202.83 |
| Momentum+Volume, fixed dollars, causal pre-order quantities | 128,864.62 | 128,986.40 |
| Momentum+Volume, equity-scaled, causal pre-order quantities | 230,566.36 | 230,719.74 |
| Volume-Sized, fixed dollars, legacy fill quantities | 114,190.85 | 114,655.18 |

Account for all 52 cohorts and 416 intended slots, normally 415 completed positions plus one documented halted obligation in each relevant ten-session book. Assert the actual counts and statuses; do not silently force them to expected values. Separate quantity panels and books so repeated representations of one trade are never counted as additional observations.

Arrow 010 initially loaded too little feature history and mis-sized tickets. Do not repeat that mistake: derive required observations from every feature's actual window, validate complete histories, and do not convert missing volume/momentum into zero, a favorable condition, or FULL size. The economic controls must reproduce before research scoring.

Keep all Arrow 001–010 results, frozen ledgers, source partitions and decision rules unchanged. Add an isolated Arrow 011 feature/analysis layer. If an actual inherited material defect is found, record its scope and affected claims and block those claims; do not silently repair and replace a frozen baseline to keep researching. Finite bugs in the new analysis layer may be repaired and logged.

## 3. One atlas, three outcome lenses, two information cutoffs

### Outcome lenses

Primary scientific outcome: **sizing-neutral, corporate-action-adjusted ten-session short price return**. For a pure split factor F = old shares per new share over the hold, entry price P0 and exit price P1, the comparable price return is `1 - P1 / (F * P0)`. Reconcile this to the frozen ledger's share/value transformations; preserve separately any exceptional-event treatment.

Also report modeled net P&L per actual dollar of entry exposure, under the frozen cost convention. This is distinct from dollar contribution and from return on total account equity.

Secondary lenses:

- contribution under frozen fixed-dollar Momentum+Volume sizing;
- contribution under the frozen Arrow 010 equity-scaled account.

Define a stock-price winner and a modeled-net winner separately where costs change the sign. Report absolute winner/loser/flats and continuous returns. Never train on equity-scaled dollar P&L alone and claim to have predicted which stock was a better short.

Every intended slot remains in the atlas. An unclosed documented obligation is an open/censored outcome, not a zero, loss, win, dropped row or invented exit. Preserve its available path and status at each age. Do not restrict the discovery population to eventual large winners.

### Information cutoffs

Maintain physically separate feature and outcome schemas.

**SIGNAL_CLOSE:** only information available at the signal session's actual regular-hours close, normally Wednesday. Retain the frozen holiday rollback and early-close schedule.

**PRE_ORDER:** additional information available strictly before the inherited next-session order/first possible fill. Use the timestamp of the last fully completed pre-order bar, not the entry-minute close. Freeze the precise timestamp and bar convention before scoring. On an early-close day, use that session's actual schedule.

Compare the incremental information from PRE_ORDER against SIGNAL_CLOSE on the same eligible rows. Do not use the final entry-day range, final daily volume, eventual fill price or later news as pre-order predictors. Outcome prices may appear only in outcome/accounting fields.

Each feature needs its formula, source, units, observation time, availability time, lookback, adjustment basis, missing-data rule and certification/coverage status. Filings/news require first-public-availability evidence; a fiscal date or event date is not sufficient. Date-only material cannot support same-day intraday availability: use a conservative documented lag or exclude that feature from the earlier cutoff. Retrospective reports may corroborate facts but may not introduce information not public before the decision.

Use only actions effective by the relevant feature cutoff to normalize price/share-volume units. Do not use future splits to alter historical absolute-price eligibility, float or share units. No present-day float/market cap backfilled into 2025/2026. Ticker identity must be point-in-time. Price-volume trends may use the existing certified tape; a new feature does NOT inherit certification merely because the trade ledger is certified.

### Acquisition and missingness

Reuse local caches first. Limited additional one-minute/eod/reference retrieval within the existing authorized Theta Stocks Professional entitlement and public issuer/SEC/exchange sources is permitted for these selected names, relevant context and required histories. No sub-minute ingest, options, paid new subscriptions, bulk purchases, broker borrow reconstruction or new historical test block. No new trading opportunities or universe expansion.

Validate and version all new inputs before they support findings: timestamps/calendar, source completeness, stale/missing bars, action-adjusted prices and share volumes, identities, available-at joins, and deterministic provenance. Preserve raw retrievals immutably under ignored Arrow 011 paths. A successful HTTP response or absence of a detected jump is not certification by itself.

Missing historical float, capitalization, sector, catalyst or benchmark history does not halt otherwise valid price/volume research. Mark that feature/corridor unavailable or partial, publish counts by month and outcome, and compare on explicit common masks where necessary. Never silently drop a candidate or replace it with rank 9 because enrichment is absent. Distinguish data-access limits from a tested negative result.

## 4. Directed work — approximately 168 minutes, including shared verification and delivery

### D1. Reconcile model/month differences before explaining them

Mechanically attribute the existing Volume-Sized versus Momentum+Volume-Sized differences to individual shared positions, then aggregate by calendar month AND original signal cohort. Explain base-ticket differences, the added momentum multiplier, interactions with volume state, and integer rounding without double counting.

Use same-timestamp, same-quantity-convention comparisons. The Arrow 009 legacy panel may be used to reproduce exactly the monthly differences the user saw, but must be labeled separately from the main causal-preorder atlas. Do not blend the two in one attribution.

Use an exact signed accounting identity. If a sequential counterfactual decomposition is used, state its order and show its interaction/residual; do not present dependent components as independent causal effects. A small fixed-signal sizing ablation for attribution is allowed, not a new sizing search.

All twelve months must be explained with a mechanical bridge. December, February, April and June are previously observed discussion examples, not authorized calendar filters. Develop new hypotheses on IS only; finish the full-year retrospective model/month narrative after the hypothesis freeze/reveal described below. These previously seen months cannot be called fresh discoveries.

Questions: was a monthly difference mainly less exposure to losing shorts, more exposure to winning shorts, a small number of names, or widespread reweighting? Where did lower raw-return opportunity still produce higher dollar profit because of size? Include FULL/HALF/QUARTER contribution and a sizing-neutral view.

### D2. Unpack the four existing momentum/volume states first

Read the frozen code and preserve exact definitions and comparison operators. With valid features, existing R5 uses a half multiplier when three-session return is positive, and another when volume ratio is above one. Resolve these four groups separately:

1. recent return nonpositive / volume not above reference — FULL;
2. recent return nonpositive / volume above reference — HALF from volume;
3. recent return positive / volume not above reference — HALF from momentum;
4. recent return positive / volume above reference — QUARTER.

Missing values are a separate data state, never a fifth favorable trading state.

Do the two HALF groups actually behave alike? Is the engine shorting already-weakening former winners more successfully than still-accelerating winners? Does price weakening on elevated volume behave differently from price weakening on quiet volume? Are individual reductions informative, redundant, or mainly useful together?

Measure raw/net normalized returns before dollar sizing, then dollar contribution. An apparently strong FULL bucket must not be explained solely by its bigger tickets.

### D3. Build the pre-entry feature anatomy

Cover these families without exploding into an arbitrary parameter grid:

- Run-up shape: 1/3/5/10/15-session returns; recent versus earlier return; acceleration/deceleration; steady ascent versus a small number of large jumps. These are explanatory features, not permission to replace the frozen 15-session ranking.
- Price location: distance from trailing highs and lows, drawdown already underway, close location in recent ranges, failed-high or consolidation descriptions where causal and mechanically defined.
- Gaps and volatility: gap versus continuous-session contribution to the advance, normalized ranges/volatility and run-up concentration. Derive overnight/intraday returns in consistent action-adjusted units, not naive sums across splits.
- Volume/liquidity: exact R5 volume ratio, volume trend, dollar volume and its stability, movement per unit of volume; pre-order session volume versus comparable elapsed-session history where available, never partial volume divided by a full-session average without labeling the mismatch.
- Price and reliable security context: $10–20 / $20–40 / $40–80 pre-entry price bands with nonoverlapping boundaries and an explicit outside-band group when entry price has moved outside the eligibility band; historical size/float/sector/catalyst only where adequately timestamped and verified.
- Cohort context: rank within the eight, relative extremeness, gap between neighboring ranks, concentration/dispersion of the cohort; broader field context only from adequately complete as-of candidate records.
- Event context: known split/ADR/reorganization/financing/catalyst proximity where evidenced BEFORE entry. A corrected split is not a fictitious momentum return, but a known event may be a legitimate contextual feature. Do not exclude event names merely because they look suspicious.

Begin with continuous relationships and simple low-count groups. Numeric quantiles or thresholds beyond the predeclared rules are learned on IS only and frozen for OOS. Prefer broad neighboring definitions over hunting a magic cutoff. Record all definitions tested, including failures.

### D4. Within-cohort winners versus losers — central deliverable

Produce an eight-slot page/table for every weekly cohort. Include pre-entry characteristics, actual outcome, within-cohort ranks, relative outcomes, sizing state, and verified economic contribution.

Compare absolute winners/losers and relative strength of the short outcome within the same cohort. Cohort-centered outcomes and within-cohort rank concordance are useful. Give cohorts equal weight in at least one summary so one extreme dollar winner cannot dominate every conclusion. Show pooled and within-cohort effects side by side; label a relationship that appears only BETWEEN cohorts.

Retain all-win and all-loss cohorts. A feature may identify the least bad short in a bad week without identifying a profitable short. Report mixed/all-win/all-loss/partly-censored cohort counts.

Report contributing cohort counts, securities, months and observations for each relationship. Eight simultaneous trades, repeated symbols and overlapping holding windows are not independent replications. Explain overlapping repeat selections/security episodes and distinguish persistence from genuinely new examples.

### D5. Use holding paths to explain, not leak

Use existing Hold-Length Ladder paths to describe the anatomy of outcomes: immediate fade, initial adverse move then fade, continuation/squeeze, temporary fade then reversal, or other simple descriptions justified by the data. Derive any new path categories on IS and freeze definitions before confirmation.

Report mean/median and return-distribution quantiles by holding age, incremental 1→2 through 9→10 session economics, favorable/adverse excursion at the available resolution, time to favorable movement, and aggregate 3/5/7-session profit relative to ten sessions where a positive denominator makes that ratio interpretable. Include counts and open-status transitions at every age; do not compute ratios only among eventual ten-session winners and generalize them to the whole book.

Label close-only excursions as close-only; do not call them true intraday extrema. Post-entry labels and paths are OUTCOMES, never pre-entry predictors. Do not optimize hold length, stops, partial exits or execution times in this arrow. Path findings generate later management hypotheses.

### D6. Counterexamples, stability and separation quality

For every leading pattern, inspect both supporting and contradicting cases. Seek at least two concrete examples and two counterexamples where the sample permits; say when it does not. Outcome-hidden pre-entry dossier reviews are encouraged where practical. Do not fabricate a catalyst narrative for unexplained price behavior.

Check effect direction/size across cohorts and months, repeated versus first selected episodes, and leave-one-cohort or leave-one-security-out diagnostics on IS. For uncertainty estimates, use cohort/contiguous-cohort blocks or security-aware sensitivity, not random trade-row train/test splits. Block resampling is a dependence-aware diagnostic, not proof of independent observations. Record effect sizes, sample support, uncertainty and counterexamples; statistical significance is not a mandatory discovery filter.

After freeze, report whether the same pre-entry relationship appears in even-month confirmation. A failure to separate winners and losers is a result. Do not relabel a weak result as a new mechanism merely because its story sounds plausible. This study's conclusions apply to the frozen selected population, not automatically to all stocks.

## 5. Fable-led investigation — approximately 72 minutes, at most 30% of total allowance

You have genuine intellectual freedom within the mission: form/refine hypotheses, investigate unexpected contradictions, propose an unlisted but causal descriptor, and examine small interactions/state sequences. You do not need approval for every branch. Your job is not merely to execute a list of bins.

Potential directions are suggestions, not mandatory tasks: episodic versus gradual run-ups; failed continuation before entry; prior selection episode age; move concentration versus liquidity; differences hidden within existing sizing states; entry-day information beyond Wednesday's signal; or a mechanism contradicted by a strong counterexample.

Prefer a few fully resolved questions to a large unfinished search. State each freelance question, why it is distinct from directed work, information cutoff, predicted direction, test and expected information value BEFORE scoring it. Retain every revision and failed branch in the registry.

Up to FOUR small, interpretable research-only decision probes may be frozen from IS findings to test whether descriptive separation has economic value. Their use is optional, not a requirement to produce a better model. Freeze formulas, thresholds, controls, row masks and expected effects before OOS. Use the same certified trade times and outcomes; no new entry, hold or sizing architecture. For a subset-selection probe, unused exposure stays idle; report normalized-return and exposure-matched comparisons so reduced capital alone is not mistaken for skill. Do not recompute a new compounded equity strategy around these probes. Counterfactual sub-books must be labeled exploratory and carry the monthly reporting standard if account economics are claimed.

Freelance work must not become capital redeployment, a new long strategy, a broad lookback/leverage search, broker selection, stock-loan-cost research or OOS-guided repair of a failed hypothesis. Post-reveal ideas are queue entries only, not new tests in this run.

## 6. Research sequence and IS/OOS ownership

Historical sample: September 2025–August 2026; original signal-month ownership.

- IS discovery: 2025-09, 2025-11, 2026-01, 2026-03, 2026-05, 2026-07.
- OOS internal confirmation: 2025-10, 2025-12, 2026-02, 2026-04, 2026-06, 2026-08.

These even months have repeatedly been viewed. They are NOT pristine validation. Existing A8/A9/A10 controls may be checked across the year for reproduction only; known outcomes are not a source for choosing new feature definitions, bins or probes.

1. Verify frozen sources and define target/feature schemas. Data preparation may span all months, with outcomes separated from feature generation and new OOS analysis withheld.
2. Complete directed and freelance discovery on IS. Freeze any outcome archetypes, feature transformations, thresholds, missingness masks, small probes, leading claims and expected confirmation behavior.
3. Commit AND push `reports/cg_arrow011_hypothesis_freeze.json` before scoring any new OOS relationship. It must include source/model/feature-code hashes, the full tested-hypothesis registry and both supported and rejected IS hypotheses; freeze which results will be reported. Do not silently retain only attractive survivors.
4. One OOS batch applies the fixed definitions and reports all registered comparisons with meaningful confirmatory counterparts, including non-replications. Check hashes before reveal. No re-fitting or post-reveal thresholds.
5. Finish the all-year retrospective cohort atlas and the complete model/month explanation. This final narrative can inspect all outcomes, but anything newly noticed is labeled post-reveal/exploratory and queued for a separate experiment.

Cross-month histories and holds stay intact. A SIGNAL_CLOSE feature in an IS cohort cannot contain a later observation just because a prior trade eventually closed. A performance-derived predictor, should one be proposed, must not use OOS-owned outcomes to train IS decisions. Cohort/security dependence must remain visible. Do not claim counterfactual causation from within-cohort association.

## 7. Required evidence and economic outputs

### Public-safe reports and aggregates

Publish:

- `reports/cg_arrow011_anatomy.md`: executive findings, all core questions, IS versus confirmation, counterexamples, what is not known, and next experiments ranked by information value and implementation burden.
- `reports/cg_arrow011_hypotheses.csv`: every directed/freelance hypothesis, parent/revision, feature/cutoff, test, sample, IS result, frozen expectation, OOS result, status and counterexamples.
- `reports/cg_arrow011_hypothesis_freeze.json`: pre-reveal committed manifest; preserve its original state and add reveal records separately.
- `reports/cg_arrow011_confirmation.csv`: all registered confirmatory comparisons, including failures and no-signal results.
- `reports/cg_arrow011_feature_catalog.csv`: definitions, sources/availability/unit rules, coverage, missingness and certification state; no proprietary raw values.
- `reports/cg_arrow011_within_cohort_summary.csv`: public-safe aggregates distinguishing within- and between-cohort relationships.
- `reports/cg_arrow011_model_month_attribution.csv`: complete 12-month signed contribution bridges, with explicit quantity/account conventions and residuals.
- `reports/cg_arrow011_holding_path_summary.csv`: sizing-neutral age distributions and explicit completion/open counts, plus causal feature-conditioned path summaries where supported.
- `reports/cg_arrow011_monthly_account.csv`: monthly accounts for referenced principal books and any probes making account-level economic claims.
- `reports/cg_arrow011_manifest.json`, `reports/cg_arrow011_commands.txt`, and an independent reconciliation/audit report with tested invariants and exact results.
- any isolated analysis code/tests needed to reproduce these artifacts.

Safe summaries may combine related files if schemas and manifest mappings remain explicit. No giant redundant output pack. Public reports should contain enough numeric evidence to audit conclusions without uploading private tape.

### Private atlas, individual files, git-ignored

Under `handoff/outgoing/cg_arrow011/`:

- `trade_atlas.csv`: every intended selected trade, stable identity/cohort key, features/cutoffs, linked outcomes, sizing-neutral and dollar lenses, episode/missingness/event status; one economic observation per selected ticket, not duplicates from panels.
- `cohort_atlas.md`: all 52 eight-slot cohort dossiers with compact evidence-based commentary; no invented explanations.
- `pre_entry_feature_evidence.csv`: detailed sources/timestamps and availability checks.
- `model_month_trade_bridge.csv`: trade-level contributions supporting the public bridge.
- `trade_path_atlas.csv`: available holding-age paths with statuses, no silent complete-case censoring.
- `hypothesis_casebook.md`: supporting examples and counterexamples, identifying retrospective versus truly pre-entry evidence.
- required detailed reconciliation records and an inventory with exact paths/hashes.

No ZIP required. Never commit detailed trade rows, private vendor bars, caches, credentials or account identifiers to the public repository.

### Mandatory monthly accounting and costs

Use `cg_lab_monthly_account_reporting_v1`. Every account comparison must show each of the twelve months, monthly marked P&L dollars, return on prior month-end equity, month-end equity, positive/red/flat counts, worst/best/median month and exact reconciliation. Same principal comparisons side by side; no placeholders or collapsed months. Use cent-chained account numbers consistently in CSV and prose. Keep full precision in manifests.

Calendar marked P&L, eventual completed-trade profit, incremental post-cutoff runoff, full-life runoff-trade profit and open documented obligations remain separate. A feature group without a rebuilt daily account may show trade statistics but may NOT invent account drawdown, monthly return or capital utilization from those trade statistics.

Retain the A8/A10 declared commission/spread model. No hypothetical flat 10%/30% stock-loan deductions in headline tables and no borrow-cost research. Use one concise footnote: `Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills and availability are modeled, not broker execution guarantees.` Do not reinterpret excluded costs as independently verified zero.

## 8. Audit gates

Test, rather than merely assert:

1. Baseline hashes/counts/totals and per-trade price returns are unchanged; all intended slots and documented open obligations remain represented.
2. New joins introduce no duplicate tickets, cross-panel double counting or historical-identity drift.
3. Each scored feature meets its recorded availability cutoff; explicit tests reject entry-minute/future-price/news leakage and future action contamination.
4. Insufficient lookback, missing volume, stale observations and unknown float cannot become valid zero or favorable-state predictors.
5. Four-state momentum/volume labels agree with the frozen source rule on every adequately observed ticket; HALF causes are distinct.
6. Normalized outcomes independently reconcile to shares, entry/exit prices, action factors and the declared costs. Existing equity-scaled/fixed-dollar accounts remain identical to their source references.
7. Model/month and cohort attribution sum exactly under the stated bridge, including interaction/rounding components. Dates crossing months are correctly allocated.
8. Monthly outputs chain and reconcile to the appropriate marked-account cutoff, not eventual profit; split-owned books contain the right positions and ALL is separately identified.
9. Pre-entry tables do not include post-entry outcome fields as predictors; path labels cannot leak into feature scoring.
10. IS binning/transformations/probes freeze before the OOS reveal and remain unchanged. No unexplained code/data/hash drift between freeze and confirmation.
11. Supporting and contradictory cases, failed hypotheses, sparse groups, repeated securities and open-status transitions are counted and disclosed.
12. Original baseline/report artifacts remain unchanged, and public/private separation passes content as well as filename inspection.

Run the relevant independent oracle, new tests and existing regression suite; report actual commands, counts and tolerances. Do not present self-consistent arithmetic as independent verification of all source observations. A failed enrichment feature blocks its associated finding, not unrelated verified research. A newly discovered material baseline defect blocks affected economic conclusions and must be explicit.

## 9. Runtime, discretion and completion

**Total allowance: 240 elapsed minutes, inclusive of ingestion, analysis, confirmation, tests, reports, commit and push.** This is an agent work budget, not a guarantee of success or a requirement to idle.

Approximately **168 minutes directed/shared work and at most 72 minutes Fable-led exploration**. Treat the 30% as a ceiling on independent discovery, not permission to neglect the core atlas. Record lane time and worker choices; do not double-count parallel worker time as elapsed time. Freelance work may interleave with directed work, but all new hypothesis development must precede the freeze/reveal.

Plan the final 40–50 minutes for freeze/confirmation, full-year synthesis, reconciliation/tests and delivery. Do not launch new hypotheses once that completion reserve begins. If enrichment is costly, narrow optional enrichment rather than omit the whole cohort atlas or the confirmation of already-started hypotheses. Every launched hypothesis must end with a supported result, rejection, inconclusive result or exact data-access limit inside the allowance. Unstarted ideas are a prioritized queue, not pretend-completed research.

At start, report the start/deadline, plan, likely bottleneck and concurrency. Progress at least every ten minutes with actual findings and remaining branches. Use available compute efficiently: inspect CPU/RAM; benchmark practical parallelism where needed; one writer per artifact; no oversubscribed process tree. ThetaData acquisition uses at most eight concurrent requests total, respecting lower observed limits. All other sources respect their own current rate limits. Freeze decisions and dependent stages are serial. Research subagents may receive outcome-hidden pre-entry dossiers; only the coordinator releases OOS for new analyses.

Do not end the assignment merely because the first attractive table is complete. Productive counterexample work and independent alternatives belong within the allocated block. Conversely, stop when the authorized questions are answered, checks complete and useful independent branches resolved; report why unused time was unnecessary. Do not promise an overnight/background continuation.

No new capital/redeployment/hold/timing optimization, new long model, new historical holdout scoring, production promotion, or Arrow 012. Commit and push all reviewed public-safe outputs to `origin/main`, verify remote equality, provide exact local private paths and stop for ChatGPT audit.

End with:

`BASELINE PRESERVED: YES / NO — evidence`

`ANATOMY STUDY: COMPLETE / INCOMPLETE — exact omissions if any`

`NEW RELATIONSHIPS: INTERNAL CONFIRMATION ONLY; NO PRISTINE OOS CLAIM`

`NEXT RESEARCH PROPOSALS: ranked, precisely specified, NOT EXECUTED`
