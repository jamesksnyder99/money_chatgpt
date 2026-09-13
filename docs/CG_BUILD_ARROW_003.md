# CG Build Arrow 003 — deeper R4/R5 research, a softer exposure budget, and usable monthly returns

## Assignment

Run one autonomous, bounded continuation of the R4/R5 hold-short-for-fade family. Improve monthly outcomes, profitability, and/or repeatability without confusing larger positions with a better model. The user permits approximately $130,000 gross exposure on $100,000 starting equity, with small temporary overshoots tolerated. Keep reasonably clean odd-month training/even-month confirmation gates; position lifecycles may cross months. Independent new-model research is parked.

**Total allocation: at most 180 minutes elapsed wall clock, INCLUDING preparation, research, freeze, confirmation, reporting, tests, commit and push. No automatic overtime.** The prior three-hour run froze at minute 69; do not repeat that merely because all first-pass tests finished.

Work only in `C:\Users\james\money_chatgpt`. Do not access `C:\Users\james\Money`. Do not place orders. Do not begin CG Arrow 004. No per-hypothesis user approvals are needed within this assignment.

## Read first; do not reread the whole research archive

1. `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`.
2. `reports/cg_arrow002_recursive_lab.txt`, `reports/cg_arrow002_ledger.txt`, `reports/cg_arrow002_selection.json`.
3. `reports/cg_arrow002_is_robustness.json`, `reports/cg_arrow002_freeze.txt`, and the relevant R4/R5 specs in `reports/cg_arrow002_is_results.json`.
4. Relevant portions of `src/research/cg_arrow002_lab.py`, its audit/recycling helpers, and focused tests. Reuse its caches where their version/inputs match.
5. `reports/cg_arrow001_baseline.txt` for provenance only; no broad data inventory or full old reproduction project is required again.

Starting research snapshot: `368f3b2c4fc20c381907fb425420bc87a7abce39`. Preserve earlier reports, tests, and freeze manifests. New outputs and guards use `cg_arrow003` names and a separate local cache namespace. Do not delete the old OOS markers to reopen Arrow 002R. Adding new source files can change old wildcard code hashes; use an explicit versioned dependency identity for this run rather than altering historical manifests.

## 1. The comparators and what counts as progress

Keep these strategy definitions as named controls:

- **PARENT:** Wednesday's eight largest 15-session returns in the inherited point-in-time common-stock field ($10-$80 prior close; prior-day dollar volume >=$10M; inherited ETP exclusions). Enter next-session late RTH; hold ten sessions; original $4,000 tickets.
- **R4 / volume-conditioned sizing:** same selections, dates and horizon; $5,150 base, halved if signal RTH volume exceeds mean RTH volume of the PREVIOUS 20 sessions. Missing feature history neutral as inherited.
- **R5 / stall plus volume sizing:** same; $8,300 base, independently halved for positive three-session return and for above-average signal RTH volume. Possible intended tickets: $8,300/$4,150/$2,075.
- **Conservative reference:** A4's $4,000/$2,000 volume rule; also the existing unscaled R1 stall+volume $4,000/$2,000/$1,000 rule when needed. These are meaningful risk tradeoffs, not redundant solely because larger versions exist.

Arrow 002R published full-year modeled profit / DD / peak gross of PARENT $51,855.71 / -$20,033.68 / $102,921.77; R4 $69,886.70 / -$17,841.23 / $112,073.90; R5 $83,111.71 / -$19,306.99 / $122,299.06. These are ALREADY OBSERVED history, not new training targets or fresh confirmation. R4/R5 are no longer disqualified just for their previous exposure figures under the user's revised policy. That policy change itself is not newly discovered alpha.

Judge each variant against its relevant R4 or R5 parent as well as the original parent. Keep separate frontiers:

- **BALANCED:** higher modeled profit and materially better monthly/downside measures, with remaining regressions shown.
- **RIDE-FIRST:** meaningfully smaller red-month losses/worst month/DD with useful retained profit (roughly >=85-90% is a planning guide, not a hidden optimizer).
- **RETURN-FIRST:** higher profit at a reasonable, openly described extra risk/exposure cost.
- **NO PROGRESS / MIXED / DATA-LIMITED:** valid outcomes. Do not force a winner or require all metrics to improve.

Use the SAME comparison implementation in training, confirmation and reports. Remove the new run's contradictory strict-versus-confirmation flags and old hard exposure veto; do not edit their historical results. Numerical materiality guides must be recorded before candidate scoring, disclosed, and not treated as proof or independent statistical tests.

## 2. Upfront repairs: useful, bounded, and common

Allocate about 20 minutes, at most 25, to this phase. Reuse environment and caches. Run targeted tests, not another million-file filesystem walk. Record each issue as repaired, quantified/retained, or branch-specific blocker. An empty split table alone must not terminate the whole session.

### A. Fix comparisons and accounting definitions

Separate exposure from equity and remove the $100k/$102,922 promotion cliff in the NEW scorer. Report actual aggregate live tickets/symbols, not batch counts. Derive continuous DD on real chronological MTM, never concatenated alternating days. Keep completed-cohort PnL, terminal unrealized MTM, and calendar-month account returns separately labeled. Use one classifier and tests for every output.

Preserve the legacy reproduction as history. Where a shared repair changes economics, establish a **working-control version** for PARENT/R4/R5 before candidate tests and reconcile the IS difference. All new comparisons use the same data/treatment. Do not measure a repaired variant against an unrepaired baseline and call the difference a strategy improvement.

### B. Do not let future exit availability erase an entry

Prefer a thin accounting extension, not a wholesale new execution engine. Instantiate each valid executable entry without asking whether its future H10 close exists. Mark and reserve it causally until exit.

For missing internal observations: try the already-copied, compatible alternate tape partitions or documented local EOD data; distinguish real traded prices from adjusted/official EOD marks. A carried mark is a stale valuation, NOT an executable fill. If the scheduled exit lacks an executable bar, retain the position and execute at the next available eligible print at/after the scheduled exit, with gap/staleness recorded. Never backdate a fill to the last earlier observation.

Positions still open at August 31 remain open and marked at the evaluation boundary; do not remove their entries or pretend a planned September exit already happened. Report terminal inventory and uncertainty separately. Likewise, a scheduled entry with no executable observation is a missed fill, not permission to use an earlier price retrospectively.

Apply a single convention to all working controls/candidates. Add small fixtures for a missing exit, month-end carry, and terminal open inventory. If complete price history cannot be resolved, publish the missing/stale exposure and the legacy-comparable view as a separate limitation. Do not claim accurate complete economics for unresolved positions, and do not discard them silently. Unaffected mechanism work and infrastructure tests can continue.

### C. Corporate actions and historical short costs: no invented fixes

The known split file is an empty placeholder. Price and share-volume signals can BOTH be distorted by splits, and common raw conventions do not guarantee relative bias cancels.

Perform a bounded check of already-local corporate-action evidence and IS feature discontinuities. A large return only identifies a review candidate; it is not evidence of a split. You may make a small, resumable reference or missing-history request through an ALREADY authorized lab data connection, or consult primary issuer/exchange sources, only if usable without new accounts, charges, credentials from Money, or large ingest. Inspect the installed official SDK rather than guessing endpoints. No new subscription, paid vendor purchase, bulk tape acquisition, or authentication detour. All acquisition time counts in the repair budget.

Only documented events get common as-of adjustments: respect effective dates and stated factor convention, adjust historical comparison prices/volumes consistently through each decision time, and adjust held share quantities at the event. Do not use later events to exclude an earlier entry. Do not selectively repair favorable trades. Preserve raw inputs and store derived views/provenance. If coverage is partial, label it partial; it is not certification of the complete ranking universe. Unknown factors are never inferred.

If a comprehensive correction is unavailable within this bounded phase, continue explicitly conditional research with a fixed common convention and a dependency/fragility audit. Any hypothesis whose claimed benefit is shown to be a verified artifact is rejected as evidence; no deployment claims. Avoid launching additional split-sensitive feature branches that cannot be interpreted. Do not spend the whole allocation relitigating the already-known empty placeholder.

Historical borrow/locate/dividend completeness is not fabricated. Retain the existing modeled costs and post-freeze 0/10/30% annual borrow scenarios. Small documented improvements apply commonly before the new freeze. Distinguish scenario sensitivities from actual loan economics.

## 3. Soft capital policy and practical risk reporting

Starting equity stays $100,000; no extra $30,000 deposit is assumed. Target gross marked exposure around $130,000. A brief $132k-$135k observation is NOT an automatic fail, forced exit, or newly optimized threshold. Do not replace $130k with a hard $135k cliff.

Report average, 95th percentile, peak, count of sessions and longest consecutive spell above $130k, exposure-dollar-days above it, and whether peaks came from new allocation or price drift. Show gross/current marked equity and largest aggregate symbol weight. Include an illustrative simultaneous 10% adverse move in shorts and 50% adverse move in the largest name as stress arithmetic, not forecasts, margin certification, or new stop rules.

Concentrated/sustained exposure far above the intended range is a tradeoff to flag, not permission for unrestricted leverage. Evaluate dollar profit, exposure-normalized profit, worst-month/day and DD together. New larger sizes need a fixed-size or IS-derived exposure-matched comparator. Never rescale to a realized OOS maximum.

For a **pacing experiment**, target about $130k at NEW orders using only the last available pre-order marks, outstanding orders and all open cohorts. Scale a simultaneous proposed batch pro rata to remaining headroom (rather than let iteration order choose lucky names); no minimum-size top-up when headroom is exhausted. Small fill slippage/drift overshoots are recorded and do not trigger retroactive rejection. Existing positions continue under their own exit policy, not forced liquidation solely because marks cross $130k. Controls without pacing remain valid research comparators under the soft policy.

An EOD peak is not an intraday maximum. For finalists, use available synchronized minute marks to check peak periods if feasible; otherwise clearly label the EOD limitation. Never sum each stock's separate daily high and call that an observed simultaneous peak.

## 4. Reasonably clean training and confirmation

Keep the 12-month SIGNAL split:

- IS: 2025-09, 2025-11, 2026-01, 2026-03, 2026-05, 2026-07.
- OOS: 2025-10, 2025-12, 2026-02, 2026-04, 2026-06, 2026-08.

Normal causal lookbacks may read earlier even-month prices. Existing-position management, exits and marks may occur in even months. Do not censor those holdings, force month-end liquidation, or introduce a formal purge/embargo project. The original signal remains cohort owner.

New candidate performance, parameter selection, and iterative decisions use IS outcomes only. Previously published R4/R5 confirmation results are known historical context; do not pretend to unsee them or call the new run pristine. Do not adapt new thresholds to named bad OOS months. Data-quality checks independent of returns are allowed.

Freeze full rules, variants, priorities, feature cutoffs, repair version, sizing and code identity before one NEW OOS batch. After reveal, no parameter/rule repair-and-rescore loop. An infrastructure interruption may resume only the identical frozen job, reusing completed outputs and disclosing the interruption. A strategy bug found after reveal invalidates the affected result for new confirmation; disclose it rather than retuning.

Show profit/session, downside and incremental improvement against the SAME control in both splits. Show the disparity, including ratios only when denominators make them meaningful. Equal IS/OOS dollar returns are not required; weather differs. Prefer repeated direction, nontrivial performance in both samples, and no collapse of the main benefit.

For stateful exposure rules, isolated IS/OOS cohorts are not the complete live book. After confirmation, replay all signals with one chronological account and present all 12 calendar-month equity returns. Do not splice or sum two separately capital-constrained books. This final investor view is descriptive, not another optimization surface.

## 5. Directed continuation map — about 60% of discovery effort

Prioritize C1-C5. Aim to complete a core result in each; if one is genuinely data/compute blocked, document it and substitute another R4/R5-relevant mechanism. C6 is cheap and useful when capacity allows. These are hypotheses, not a brute-force Cartesian grid. Predeclare each exact implementation; recursively refine promising results, not every weak branch. Each started performance experiment closes inside this run.

### C1 — preserve the signal, find the sensible allocation scale

Compare R4 and R5 at their original intended sizes with conservative A4 and unscaled R1. Add the causal new-order pacing policy above to R4 and R5. Keep signals/exits unchanged. Include a straightforward constant-ticket parent comparison; use IS only for any one-time matched-exposure multiplier.

Question: can we preserve improved economics with a more tolerable monthly loss profile, and does pacing matter beyond merely reducing exposure? Why first: this directly uses the user's flexibility and corrects the prior finalist set's omission of a conservative implementation. Do not optimize a sequence of ceilings to the old worst day.

### C2 — test what the volume signal actually means

First attribute IS incremental profit to above/below-reference participation, with trade counts, missing-feature counts, top-symbol and top-month contributions. Compare with deterministic, seeded within-signal-batch shuffles of the size assignments as a diagnostic; this is not a new trading strategy or independent statistical proof.

Core alternative: replace prior20 MEAN RTH volume with prior20 MEDIAN, keep cutoff 1, half-size penalty and original base amount. Test R4 first, then R5 if informative. One optional persistence test uses median of each of the last three sessions' causal volume ratios; every ratio uses its own prior20 reference. Keep current-session-versus-average and truly fading multi-session participation conceptually distinct.

Question: is the benefit robust to a few historic volume spikes or driven by a single unusual session? No volume-window sweep, no assumption that lower-than-average means volume has declined for several days.

### C3 — softer penalties instead of abrupt half-size switches

For positive volume ratio v, test volume multiplier clamp(v^(-1/2), 0.5, 1.0), with neutral multiplier 1 for missing/nonpositive invalid feature values. This gives full size at/below average and tapers smoothly above it. Use unchanged R4/R5 base amounts.

In R5, test the volume taper first while keeping its original ret3 half-size switch. Then one momentum taper may be tested: clamp(1/(1+max(ret3,0)/(vol20*sqrt(3))), 0.5, 1.0), where vol20 is the signal-known sample stdev of daily returns; use neutral 1 if unavailable/nonpositive. Compare changes separately before combining. Split-sensitive volatility limitations remain disclosed.

Question: do small feature changes cause unnecessarily large exposure jumps? The stated curves are initial hypotheses, not privileged optimums. One narrowly motivated neighboring shape is permitted after a completed result; no shape grid.

### C4 — persistence of the information through the entry delay

Keep the Wednesday ranking, intended ticket policy and next-session late-RTH entry. Compare the signal-known volume state with an update at the next session's 15:55 minute CLOSE, available at 15:56; any updated decision executes strictly afterward. Use cumulative RTH volume through the checkpoint divided by the previous 20 sessions' volume through the SAME checkpoint. Do not compare a partial session with a full-day denominator.

Test R4 first; update R5's momentum component separately only if justified. Explicitly handle early-close days with a predeclared fallback such as the original signal state; do not use nonexistent 15:55 data or an earlier fallback execution after a later decision. If obtaining same-slot histories is too costly, predeclare a signal-only persistence comparator before scoring instead.

Question: does the information still matter a day later, and can the update avoid newly strengthened stocks without an indiscriminate weakness-entry filter? This is not a repeat of the failed generic entry-confirmation test.

### C5 — management of an earned fade, targeted to R4/R5 states

First produce IS incremental holding-day economics, preferably separating overnight/RTH contribution where reliable local bars permit it. Separate by entry participation state. This descriptive analysis is not permission to choose the hindsight best exit for each trade.

Core research rule: retain original entries and H10 backstop. From hold day 3 onward, at 15:55 close, allow ONE half-cover only when (a) price is at least one signal-frozen ATR20 below entry, (b) price exceeds the prior session's close, and (c) same-slot volume pace exceeds its own prior20 mean. Execute at a later available print; never the decision close. The remainder rides to the original H10 exit. Compare with no overlay on the SAME entry ledger; no replacement.

Question: can renewed buying participation after a profitable fade identify giveback risk while preserving half of a windfall position? Codex may substitute a better state-management hypothesis supported by the holding-age analysis, predeclared before scoring. Do not simply repeat universal five-day exits, scratch-on-red, or D6 replacement.

### C6 — combine the two allocation rules without double-spending

Test a fixed 50/50 R4/R5 allocation rule: each selected symbol receives the arithmetic average of the two intended ticket amounts, then apply the same chosen pacing policy. Do not add two full books or search mixture weights. Net common symbols for economic/capital accounting.

Question: can the simpler participation signal temper the aggressive stall+volume allocations? This is blending closely related sizing rules, not an independent engine or proven diversification. Judge it against both parents, not just the weaker comparator.

## 6. Astra's own shop — about 40% of discovery effort

Protect meaningful time to originate at least a few independent hypotheses WITHIN the R4/R5 family, not merely rename the directed tests. Examples of admissible territory: persistence of participation, distribution of volume within the known signal session, drawdown-sensitive NEW allocations, state-dependent use of the remaining holding horizon, alternative ordinal sizing, or risk interactions discovered in the IS diagnostics. These examples are not a mandatory checklist.

Astra may reject my proposed mechanism after completing its core test, pursue surprising IS evidence, and exceed a literal 40% share when its own branch is productive. Keep interpretability, common economics, causal decisions, and comparisons. Do not use ticker/month whitelists, a broad parameter sweep, coefficient-significance filtering, or an opaque predictor. R4/R5 are guides, not a ban on useful local structural changes, but do not drift into unrelated long engines/day books.

The new swing/day models from the director's prior report remain PARKED. Preserve useful ideas in the final backlog without testing them here.

## 7. Working frontier, resilience and finalist selection

For every completed policy, record exact rules and lineage; PnL/session; total PnL; red signal-month count/loss sum; worst/median signal month; chronological cohort DD and worst day; exposure statistics; and data caveats. Never label a merely dominated profitable branch as evidence that its mechanism fails; distinguish dominated from economically rejected.

For viable leaders, conduct paired leave-one-IS-month-out profit-difference checks, top-contributor dependence, fixed/exposure-matched controls, and narrowly motivated neighboring specifications. These are fragility diagnostics, not new independent validation. If the primary issue is uncertainty from corporate actions or stale prices, explicitly show that dependency instead of inventing significance.

Before freezing, state which PRIMARY improvement each finalist is trying to repeat and what downside tradeoff is acceptable. Default finalist mix, up to five distinct NEW policies:

1. best balanced R4 descendant;
2. best useful-profit smoother, including a conservative implementation even if it shares a signal;
3. best R5 return challenger;
4. best distinct Astra-originated continuation;
5. another genuinely different tradeoff only when earned.

Include original PARENT/R4/R5 working controls and needed frozen size matches in the confirmation batch. Do not freeze five nearly identical shapes. Do not promise simultaneous improvement everywhere. Do not eliminate useful conservative finalists merely to make room for more scaled variants.

Confirmation assessment: REPEATED, PARTIALLY REPEATED, NOT REPEATED, or INCONCLUSIVE/DATA-LIMITED, explaining return, monthly ride, risk, and exposure separately. A trivial $130k overshoot does not turn repetition into failure. Likewise a relaxed ceiling does not erase a genuine worsening of the monthly ride.

## 8. Clock, checkpoints, and interruption recovery

Start after pull/root check with UTC and ET start/deadline and an elapsed monotonic timer. Preparation, code, tests and I/O all count; this is not 180 minutes of scorer CPU time.

Planning allocation:

- 0-20 minutes: bounded repairs, cache reuse, IS working controls.
- 20-100: directed discovery and its recursive refinements.
- 100-150: protected Astra-owned continuation, plus challenges of the current frontier.
- 150-165: freeze/commit code and finalist manifest; single confirmation batch and joint investor replay.
- 165-180: final tests, reconciled reports, public-safety review, commit/push/remote verification.

The split is approximately 60/40 of actual discovery, not a quota by hypothesis count. Prefer freeze around minute 150. **Do not reveal new OOS before minute 135** merely because the first batch has completed. Use available IS time for alternatives and falsification, not deliberate idle waiting. Earlier closure is permitted only for a documented genuinely blocking execution/data failure affecting all credible comparisons, or a timing risk established by measured confirmation/reporting cost. State the reason and actual allocation; the empty split placeholder alone is not such a reason.

Finish every opened test with scored results or a specific real execution/data failure. Do not leave a queue or count untested ideas as hypotheses. Do not open work that cannot finish with closure reserve intact. If a run nevertheless times out, report it as incomplete, not a completed finding. Never fabricate a winner to satisfy the deadline.

Emit a concise progress heartbeat at least every ten minutes: elapsed, completed branch counts, current best IS tradeoffs, remaining budget. Checkpoint after each completed batch. Maintain local resumable state including code/input identity, completed results, elapsed budget, and whether OOS has been exposed. A machine interruption must not reset the research allowance or reopen OOS silently. If the identical run cannot be resumed honestly, report that.

Use safe checkpoints/commits so completed work survives an interruption, but do not automatically push unscreened caches/data. Freeze must be committed BEFORE confirmation; a final result commit follows. Never force-push or overwrite unexpected work.

## 9. Deliverables and acceptance

Publish reviewed code/tests plus these audit-friendly artifacts (combine minor text sections if clearer):

- `reports/cg_arrow003_report.md`: executive verdict, ranked candidates with plain-English pitches and tradeoffs, repair status, IS/OOS and 12-month investor tables, conclusions and next questions.
- `reports/cg_arrow003_ledger.jsonl`: every directed/Astra/derived hypothesis, predeclared mechanism, exact spec, control, timing, results and disposition; distinguish repairs/replays from new hypotheses.
- `reports/cg_arrow003_repairs.md`: legacy-to-working-control IS reconciliation, coverage, missing/terminal positions, reference provenance, and unresolved issues; no raw vendor payload.
- `reports/cg_arrow003_freeze.json`: complete specs, priorities, code/dependency hashes, input/cache identity, data-convention version, size matches, timestamp and pre-reveal commitment.
- `reports/cg_arrow003_results.json` and `reports/cg_arrow003_daily.csv`: safe aggregate IS/OOS metrics and post-freeze daily account PnL/equity/gross for all controls/finalists. Daily ACCOUNT aggregates are useful for independent audit; no raw market bar/quote export. Keep detailed position/fill ledgers local and record hashes/paths.
- `reports/cg_arrow003_commands.txt`: exact repeatable commands, tests and wall-clock reconciliation. Append a parked-ideas section without executing new models.

Final investor views: all twelve monthly MTM amounts AND returns relative to each month's starting marked equity, red-month loss sum/count, worst/median month, total profit/day, peak-to-trough DD in dollars/percent, time underwater, worst day, average/percentile/peak exposure and excursion durations, top-symbol/top-month concentration, terminal/stale inventory. Preserve the $100k starting capital and do not quietly compound ticket sizes unless an explicitly tested policy says so.

Freeze the scenario list before reveal: inherited execution costs; 0/10/30% annualized marked-value borrow; and twice the inherited one-side spread proxy with commissions unchanged. These sensitivities are reporting, not post-OOS tuning or factual historical fees. Include inherited and working controls on the same basis. Broker financing/locate/dividend and unresolved split limitations remain disclosed; no deployment certification is requested.

Focused tests must cover: unchanged legacy evidence; future-exit-independent entries/state; terminal marks versus fictitious fills; causal volume histories/checkpoint fills and early closes; pro-rata batch pacing; benign small exposure overshoots not auto-failing; classifier consistency; split provenance/adjustment conventions if implemented; new IS/OOS/freeze invariants; monthly/daily/total reconciliation. Run the complete `tests/` suite explicitly, directing temporary files inside ignored lab data/tmp.

Commit/push only intended public-safe artifacts and verify remote SHA. Terminal handoff: completion or precise blocker; commit; elapsed time; actual directed/autonomous effort; test counts; repairs/caveats; number of completed hypotheses; frozen finalists; best repeated tradeoff and its IS/OOS/full-year numbers; exposure excursions; whether any confirmation was invalidated. Then stop. Do not start Arrow 004.

## Source notes and interpretation limits

The prior CG Arrow 002R reports/specs at the starting snapshot support the historical findings summarized above. Every C1-C6 mechanism here is a proposed experiment, not an established edge. The softer exposure policy and practical signal-cohort gates implement the user's September 13, 2026 direction; they do not retroactively validate old results. Gross notional is not equivalent to broker margin approval; for actual deployment consult current applicable requirements, including FINRA Rule 4210 and the intended broker's house requirements (official reference: https://www.finra.org/rules-guidance/guidance/interps-4210).
