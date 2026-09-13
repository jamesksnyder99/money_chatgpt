# CG Build Arrow 004 — two-week Thursday rotation, reserve capital, and a separate long laboratory

## Mandate and precedence

Execute one **150-minute maximum elapsed-wall-clock** research session, including preparation, data checks, discovery, freeze, confirmation, investor replay, tests, reporting, commit and push. No automatic overtime. The user's latest clarification governs: **every NEW cohort is intended to remain invested until the Thursday two calendar weeks after its nominal entry Thursday, with exits around 15:00 and replacement entries at 15:59.** Do not sweep H5/H10/H15 or add discretionary early exits in this run. Old H10 controls remain historical/matched comparators, not an override of the new clock.

Three linked tasks are authorized:

1. R4/R5 short capital utilization: primary eight plus qualified reserve names; conviction-weighted top twenty; selective carry-forward of unused headroom; and a genuinely different best-eight cohort selected from twenty.
2. Weekly staggered versus alternate-Thursday full-reset scheduling. Each cohort still has its own two-week expiry.
3. A **separate long-only mean-reversion engine**, starting from economic mirrors of R4/R5 but receiving substantial independent research and falsification, not just a sign flip.

R4 and R5 are the paired short baselines to beat, evaluated separately, not two fully funded simultaneous accounts. Each experimental book starts with its own hypothetical $100,000; these separate test allocations are not additive deployable capital. No live orders. No unrelated day-trading, options, news or industry-lead/lag engines. Work only in `C:\Users\james\money_chatgpt`; never access `C:\Users\james\Money`. Do not begin Arrow 005.

## Read and reuse

Read `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, this arrow, and then selectively:

- `reports/cg_arrow003_report.md`, `reports/cg_arrow003_repairs.md`, `reports/cg_arrow003_lifecycle_coverage.json`;
- `reports/cg_arrow003_corporate_actions.json`, `reports/cg_arrow003_commands.txt` and the relevant fixed R4/R5 definitions;
- `src/research/cg_arrow003_lab.py`, `cg_arrow003_data.py`, confirmation/accounting helpers and focused tests;
- earlier Arrow 002R ledger only for avoiding repeats, particularly the failed top-16 reranking and generic early exits.

Starting evidence snapshot: `3dd9cb7f9d1385d2e5cca121d43bf28888b48d84`. Preserve historical reports, code identities and OOS markers. New code/results/cache state use `cg_arrow004`. Reuse valid local summaries rather than rereading a million files. Do not load full historical outcome reports merely to optimize named bad months.

Acronyms: IS = in-sample; OOS = out-of-sample; RTH = regular trading hours; MTM = mark-to-market; PnL = profit and loss; DD = drawdown; ATR = Average True Range. All market-clock times below are America/New_York, with proper date-specific daylight-saving treatment.

## 1. Data integrity and a side-correct account engine — bounded preparation

Target 15-20 minutes. Build/reuse long/short accounting and schedule fixtures early so the long project is not left until the last few minutes.

Arrow 003 identified outcome-related acquisition gaps, not merely an empty split file. Positions moving outside the original price bands can lose subsequent observations. Do not erase them, assume they stopped trading, release imaginary capital, or call stale inventory a successfully reset account.

- Prioritize the already-identified missing held-position intervals and the histories needed for newly selected reserve/long names. Acquisition eligibility is an ENTRY rule, not a rule for ceasing to observe held positions.
- Compatible independent local partitions and documented local valuation data may be used. A small targeted history/reference request is authorized through an ALREADY available lab connection or primary public source, without new subscriptions, charges, source-repository credentials, bulk tape ingest, or an authentication detour. No guessed API endpoints. Acquisition time counts in the limit.
- Preserve raw data and version derived repairs. Apply known corporate actions as of their effective dates to ranking prices, share volumes, held quantities, marks and price-unit features. Never infer a split factor from a large return. Existing eight-event coverage is partial, not a universe certificate.
- Any additional common repair must be frozen before candidate scoring and applied to corresponding controls. Separate repair effects from strategy effects. If later investigation reveals a material treatment bug before freeze, archive superseded scores and rerun affected IS books consistently; no quiet patching of only winners.
- Required price history absent at the intended exit: keep the actual modeled position and capacity obligation, execute only at a later observed valid print, and flag the schedule failure. A stale mark is valuation only. Retain terminal inventory; no fictitious final liquidation. Missing the exact entry bar is a missed order, not a retrospective earlier fill.
- If full lifecycle observations remain unavailable, research may continue CONDITIONALLY with explicit stale/missing exposure, dependency stress and no deployment certification. A zero-row split reference alone is not a whole-run stop. A result substantially dependent on unobserved prices is DATA-LIMITED, not an established improvement. Do not form a hindsight 'clean survivors' investment universe.

Implement/test the accounting by side, not by mechanically reusing short PnL with its sign changed after fees: equity = cash + long market value - short market value; trade gross PnL = side * shares * (exit - entry); costs subtract for BOTH sides. Covers consume cash and release short obligations; sales of longs return cash. Short-sale proceeds are not profit or additional account equity. Track gross = abs(long value) + abs(short value); never use net exposure as spare capacity. These are standalone directional engines, not a new long/short combined book.

Include minimal synthetic long winner/loser, short winner/loser, split-neutral value, missing exit, terminal inventory and cash-equity conservation tests before interpreting new results. Do not treat synthetic tests as investment evidence.

## 2. The exact two-week rotation clock

### Common new-policy timing

- Construct an ordered **nominal Thursday calendar** over the twelve-month study. The signal is the preceding trading session's completed close, normally Wednesday. Rank and freeze the candidate list/features at that signal; allocation may subsequently use account equity/headroom known before entry.
- Entry instruction is for Thursday **15:59**. Model the OPEN/first eligible observation of the 15:59 one-minute bar, not its close known at 16:00. Determine integer share quantities using the last completed pre-order mark. Never use the entry bar's later close to choose quantity or candidate identity. Disclose the bar-open execution proxy and apply costs; it is not guaranteed broker execution.
- Exit instruction is predetermined for the nominal Thursday **14 calendar days later at 15:00**. Use the first eligible trade/bar OPEN at or after that time. Longs are sold; shorts are bought to cover. Do not use the 15:00 bar close as information for a fill at its own open.
- Successful exits before the new allocation checkpoint release capacity. At 15:59 the one-week-old cohort in a weekly book remains held; only the two-week-old cohort is due. No resizing of that surviving cohort.
- Entry-time shares and selected names remain fixed through their own scheduled exit, apart from documented corporate actions and genuinely unresolved execution exceptions. No profit-taking, trailing stops, daily reserve activation or same-week replacement policy is tested here.

### Holiday convention — fixed before scoring

Use the local verified exchange calendar. Map a nominal Thursday that is a full holiday to the last trading session at or before it. On an early-close replacement session, use **one hour before actual market close** for exits and **one minute before close** for entries. The signal is the preceding trading session's close, which may not be Wednesday. Derive expiry from the NOMINAL entry Thursday +14 calendar days, then apply the same mapping; do not reanchor the series after a holiday, delayed fill or skipped allocation. Record actual elapsed days and session counts. Two calendar weeks is normally ten intervening sessions, but not always: do not let holidays drift the intended Thursday rhythm to Friday.

If a scheduled exit has no observation before the allocation checkpoint, do not assume the account is free. Pending exits retain headroom reservations until observed execution. No retrospective credit for an exit that occurs later in the session. Publish a schedule audit and example cohort ledger proving these rules.

### Required rhythm comparison

**WEEKLY_STAGGERED:** enter on every mapped Thursday; each cohort expires two nominal Thursdays later. Normally two live cohorts coexist after replacement. Start with one half-budget cohort; do not double initial size to hide startup cash.

**BIWEEKLY_RESET:** enter on alternate nominal Thursdays only; the sole prior cohort normally expires before replacement. Test BOTH fixed calendar phases, A beginning with the first nominal Thursday in the study and B one nominal week later. Do not choose the better phase after OOS or silently average them into one account. A 50/50 combination of both phases would be a staggered architecture, not free diversification.

Produce a separate timing-only bridge from each R4/R5 working control to the new two-week/15:00-exit/15:59-open-entry convention at the SAME intended ticket sizes. Disclose execution convention changes separately from redistribution benefits. Old H10 and new two-week schedules may differ around holidays. Do not compare different conventions and attribute all differences to reserve selection.

## 3. Capital: define it once instead of chasing the apparent cash balance

No cash-yield credit in this arrow. Unused capacity earns 0% in the primary comparison. Do not invent deposits or recursively spend short-sale proceeds.

At the pre-entry allocation checkpoint, after exits already known to have executed:

- E = current marked equity, including open liabilities/assets and costs already incurred.
- Start with utilization u = 1.00. The planning gross target is **G = max(0, min(u * E, 130000))**. The $130k input is a target for NEW allocation, not a post-fill failure threshold. Cashflows/current equity, not sale proceeds, drive it.
- H = max(0, G - gross of all still-open positions - reserved outstanding entry notional). Do not double-count reservations already included in gross; pending exits do not automatically reduce gross.
- Strict weekly new-cohort budget **B = min(0.5 * G, H)**. It is NOT half of the remaining cash or half of H: the other half belongs to the other two-week cohort.
- Biweekly reset new-cohort budget **B = H** on its scheduled phase only. If a previous exit is still unresolved, this is a partial reset, not a fresh account.
- A patient carry-forward arm described below may use B = H on a future scheduled WEEKLY entry date, but only with qualifying opportunities. There is no ledger of accumulating fictional 'unused dollar credits.' Prior unused capital is already represented in H.

At E=$100k and u=1, a normally funded weekly book budgets about $50k for each new cohort; a biweekly reset can budget about $100k. At u=1.25 those planned amounts become about $62.5k/$125k before reservations. These are illustration arithmetic, not return projections or broker buying-power claims.

Build the primary mechanism comparisons at u=1.00. After completed IS evidence, one fixed u=1.25 comparison may be used for leading policies and their matched controls; no leverage grid, no OOS-maximum normalization. Equity-linked allocation is an explicit change from old fixed tickets. Report a fixed-reference-E=$100k comparator for finalists when relevant, so compounding is not sold as better selection.

As a common safeguard for NEW budgeted books, limit additional orders so a symbol's aggregate pre-order marked exposure does not intentionally exceed 20% of positive current equity. This is fixed risk policy, not a tuned signal. Count overlaps across cohorts. Do not force-liquidate later mark drift. For weighted simultaneous allocations, distribute permitted dollars pro rata with bounded redistribution among allowed names; disclose binding caps and remaining cash. Legacy controls remain unchanged and separately labeled.

Small post-fill excursions beyond ~$130k are reported, not auto-failed or backdated away. Record EOD and, for finalists where available, synchronized minute gross; average, 95th percentile, peaks, excursion duration/dollar-days, aggregate symbol concentration and gross/current equity. A soft research target is NOT broker margin certification. More utilization must earn more net profit or a useful risk tradeoff, not merely make the account look busy.

For isolated IS/OOS books, never top up the missing opposite-split cohort to 'fill the account.' Use the same weekly half-budget rule. Carry-forward capacity results from isolated books are screening views; the combined all-signal account after freeze is the authoritative operational replay. Its inherited cross-cohort interactions need not equal the sum of isolated books.

## 4. Short-engine continuation — directed core, staged not Cartesian

Retain R4 and R5 as SEPARATE short baselines. Common field: inherited point-in-time stock universe, prior close $10-$80, prior dollar volume >=$10m, inherited ETP exclusions. Generate the 15-session return rank over the full eligible field before retaining the top twenty. No arbitrary universe cap or new ticker exclusions.

R4 confidence multiplier m: 1 when signal RTH volume <= previous20-session mean; 0.5 when above. R5 multiplies this by 1 if ret3 <= 0, otherwise 0.5. Missing-feature treatment in the controls stays explicit as inherited; **missing reserve information does not qualify a name as fully favorable**. Known signal features are held fixed until the prescribed next-session entry. A full R5 conviction state requires observed nonpositive ret3 AND observed at/below-normal participation.

First score these allocation cores on the weekly schedule, for R4 and R5. Close each opened test with results. Carry only promising allocations into the rhythm/utilization comparisons; do not exhaustively cross every option.

### S0 — common-budget controls

For budget B let q=B/8. Apply q*m to the original top eight and keep residual capital idle. This preserves their relative penalties instead of normalizing them away. Also score a simple full-utilization equal-dollar top-eight book B/8 per name as the 'more exposure, no extra information' control. Historical $5150/$8300 rules remain separately reported.

### S1 — primary eight plus qualified ranks 9–20 (user's first choice)

Size original eight as S0. Spare = B - intended primary allocation after caps. Walk ranks 9–20 in original return order and allocate up to q per reserve name only when its required R4/R5 state is fully observed and full-conviction. Fill min(q, remaining budget, symbol capacity); last ticket may be partial. No second allocation to a primary name from the withheld amount. Do not force weak reserves when the qualified bench is exhausted. Cohort size may exceed eight and is at most twenty names.

Use a 'blind reserve' control deploying the same available budget down ranks 9 onward without the favorable-state screen. Report primary and reserve contributions separately, realized utilization and risk. Test whether reserve dollars add more than borrowing/trading cost and whether the effect is just extra exposure. Do not assume rank 9–20 retains rank 1–8's economics.

### S2 — conviction-weighted top-twenty portfolio (user's second choice)

Remove the privilege of the original eight. Allocate B across the full eligible top twenty in proportion to simple confidence weights: R4 2:1, R5 4:2:1. For this new allocator, an unavailable feature gives one-half of that feature's full weight, not an unearned favorable-state bonus; audit this distinct missing-history treatment separately. Apply the common aggregate-symbol safeguard with remaining allocation left in cash when redistribution is infeasible. No fitted coefficients or return-rank polynomial. Compare to equal-weight top twenty at the same B and to S0/S1.

This is a basket of up to twenty, NOT eight baskets each receiving a full B.

### S3 — genuinely change WHICH eight we hold

From the top twenty, choose the best eight by observed R4/R5 confidence tier, breaking ties by original 15-session return rank. Unknown states rank after the fully observed favorable tiers under a fixed declared rule. Use the same confidence-weighted B allocation/caps as S2, but restricted to these eight. Compare with original-top-eight confidence weights renormalized to the same B. This separates selection effects from simply normalizing a smaller book.

Publish membership overlap and contribution by ranks 1–8 / 9–20. The earlier top-16 exhaustion reranking failed; this is a larger-pool and allocation hypothesis, not license to assume a selection edge. Do not keep widening the pool until the sample looks good.

### S4 — selective carry-forward of real headroom (user's fifth choice)

Build on completed S1. On later scheduled weekly entries, permit B=H instead of the strict half-G budget; deploy incremental dollars only through fully observed favorable states and the same symbol safeguard. Existing one-week cohorts are not resized and no trades are opened between scheduled entry dates. If the qualified bench is insufficient, retain cash at zero yield and recompute actual headroom next week. No accumulating virtual budget, rolling extensions of old holds, or forced use of weak names.

Compare with strict weekly S1 and with simple exposure-matched controls calibrated on IS. Report whether any gain comes from deferred qualified opportunities, more average risk, or concentration. It is acceptable for patient allocation to remain partially idle.

### S5 — rhythm and moderate utilization

Test weekly staggered versus BOTH biweekly phases on the same fixed-control allocation and at least one completed promising reserve/selection policy. Keep each cohort's two-week horizon unchanged. Test the u=1.25 neighbor only after the u=1 cores, with matched timing/policy controls. Preserve phase A and B as predeclared evidence, not a selection contest using OOS. If neither phase is robust, do not call a lucky biweekly start date a new strategy.

## 5. Protected long-only laboratory — most of the remaining discovery time

Treat this as a new independent engine, not as a hedge automatically added to shorts. It gets approximately **60–65 minutes of actual discovery**, including substantial Astra-owned adaptation; do not stop at a losing mirror and declare the whole long idea dead. Equally, do not promise that a profitable model must exist in this sample.

Use the same field and nominal Thursday clock. Rank the FULL eligible field by ascending split-consistent 15-session return; the bottom eight are the most depressed candidates and the bottom twenty are the reserve/selection pool. Volume arithmetic is not mechanically reversed. Long R5 penalties reverse price direction: negative ret3 is still falling and receives a half multiplier; zero or positive ret3 is stabilized/recovering and receives full weight.

### Required anchors

- **L0:** equal-dollar bottom-eight long on the common weekly budget, unweighted. This tests rebound exposure without R4/R5 features.
- **L4:** same losers; full weight for at/below-reference volume, half for elevated volume.
- **L5:** L4 multiplied by full weight for ret3 >=0, half for ret3 <0. Initially keep unallocated weighted dollars idle as in S0.

Publish original-ticket $5150/$8300 mirror diagnostics only when useful for bridging; primary inference uses matched cohort budgets, not unfair long/short notional differences. Long positions do not incur short borrow fees. If buying creates a negative cash balance, record a margin debit and its financing cost; do not silently finance it for free or forbid available research merely because it is not a cash-account simulation.

### Directed challenges, then adapt recursively

1. **Exhaustion versus genuine capitulation/recovery:** contrast low-participation stabilization with an independently specified high-participation RECOVERY state. A starting hypothesis favors higher signal volume only when the signal session rises from its open and closes in the upper half of its RTH range; otherwise retain the mirror's cautious multiplier. Keep base quantities/budget/horizon controlled. Merely buying elevated-volume falling stocks is not the same mechanism. Log exact rules before score.
2. **Rebound quality can choose names, not just size:** apply a bottom-twenty-to-best-eight ranking by observed recovery/participation states; compare to original bottom eight and equal-weight bottom twenty. Use original loss rank for ties. Separately test a qualified long reserve fill when earlier results justify it.
3. **Mirror versus broader continuation:** Astra may test whether less-extreme losers within that twenty, stable price paths, reclaiming a signal-known level, or a distribution of up/down days provides a more useful two-week rebound than blindly favoring the worst fall. Distinguish economic mechanism from missing-history artifacts. Stay within this loser/recovery engine; no unrelated news/sector or intraday model.

Astra has freedom to originate at least a few genuinely new causal long hypotheses, abandon weak variants after measured results, refine promising ones, use one or two economically motivated neighbors, and challenge any winner. Around 40% of discovery effort overall is protected investigator-originated work, concentrated in this long laboratory if useful. The examples are not a mandatory exhaustive grid. Explain why a proposed volume reversal is economically different instead of mechanically changing every inequality.

Keep the two-week exit fixed. No one-, five- or fifteen-session horizon hunt, no stop/partial-cover optimization, no retrospective entry delays that shorten the fixed cohort clock. Later horizons remain a parked research idea under the user's latest clarification.

### Long comparators and honest success criteria

Compare L4/L5 descendants to L0 and their direct long parent, not only to a short strategy. Include a **same-clock, same-gross long IWM benchmark** using the already-local benchmark tape as a diagnostic. IWM is authorized as a benchmark despite the strategy's ETP exclusions. A broad point-in-time eligible-stock basket can substitute if simpler and specified before score. Report raw profit AND incremental return versus this timing/exposure benchmark; do not call passive market appreciation stock-selection alpha. Neither benchmark is a separately deployed engine.

After IS evidence, carry a small long finalist set into the same one-shot confirmation phase, with the long controls and costs fixed. The separate long engine need not beat short R4/R5 on every metric to merit further study; require useful standalone economics, an interpretable source of incremental return, and candid downside/data qualifications. If no credible long finalist exists, freeze the baseline long controls and report why; do not force a winner.

## 6. Costs, uncertainty and outcome attribution

No cash yield is included. Zero idle return isolates the utilization question.

Retain inherited commission/spread for comparable discovery. Before confirmation freeze these reporting scenarios: base and doubled one-side spread with commission unchanged; short stock-loan rates 0/10/30% annualized marked short value by calendar days; long margin-debit rates 0/5/10% annualized on actual negative cash by calendar days. These are scenario assumptions, not assertions about current rates. Do not charge stock-loan fees on long inventory. Missing dividends affect shorts and longs in different directions; do not silently omit a known documented obligation/entitlement in one arm while applying it to another. Any incomplete dividend/corporate-action/loan treatment is disclosed.

For each variant quantify dollar and percentage PnL, red signal-month count/losses, worst/median month, chronological DD and worst day, utilization (average gross/average target and datewise occupancy), peak exposure, unused target headroom and its persistence, symbol/ticket counts, turnover, same-name overlap and overdue/stale inventory. Never label gross-target headroom as interest-eligible cash or broker buying power.

For reserve policies attribute incremental PnL to primary/reserve names, by confidence tier and original rank bucket, with exposure-matched and blind-fill comparators. A fuller portfolio can still be worse. For long/short comparisons keep separate return ledgers and sign-correct financing; no implicit cross-subsidy.

High missing-data exposure can invalidate investment conclusions even when cash/quantity arithmetic reconciles. New long names may have gaps BELOW the lower price boundary, just as shorts had gaps above the upper boundary. This asymmetry must be actively checked, not assumed to improve because the side changed.

## 7. Practical IS/OOS gates

Use all 12 signal months, September 2025–August 2026:

- IS: 2025-09, 2025-11, 2026-01, 2026-03, 2026-05, 2026-07.
- OOS: 2025-10, 2025-12, 2026-02, 2026-04, 2026-06, 2026-08.

Membership is the original SIGNAL date even when holiday mapping changes its usual weekday. Normal earlier lookbacks, cross-month holdings, scheduled exits and recovery observations are allowed. Do not censor them for purity. Keep new OOS performance unavailable to parameter/selection decisions until freeze. Already-seen confirmation months remain reused internal confirmation, not pristine validation. Data coverage checks independent of performance may span the calendar.

Keep strategy-phase anchor and actual cohort schedule fixed globally; do not restart alternate-week phase at each IS month, erase flat sessions from the denominator, or top up isolated half-books. Each six-month profit/session uses all its signal-month sessions, including weeks with no entries. Cohort MTM carries real lifecycle dates, not concatenated odd/even days.

Before the single new OOS batch commit a freeze with complete side/selection/sizing/capital/schedule/holiday/entry/exit rules, references, missing-history and data conventions, input/dependency hashes, code identity, frozen costs and intended claims. Allow up to **six distinct new finalists**, ideally 2–3 short/utilization and 2–3 long, plus only necessary controls and locked phase companions. More controls are not more discoveries. Preserve a conservative/patient finalist when credible, not just maximum-utilization versions. State a primary balanced/ride/return claim for each. No relabeling after seeing results to rescue a loser.

One confirmation batch; interruption may resume identical frozen jobs without rescoring completed books. No OOS-triggered tuning. An implementation defect discovered after reveal is disclosed and invalidates the affected confirmation, not repaired into a second look in this arrow.

After confirmation, replay all twelve months as ONE chronological account PER standalone policy. Do not sum independently capital-constrained IS/OOS books. Report monthly starting equity/return, actual open cohorts, close-to-replacement cash/obligations, and realized plus terminal MTM. Show long/short daily correlations only as descriptive evidence; do not combine two fully funded accounts into a fictitious $100k portfolio.

## 8. Clock and research effort

Start a fresh 150-minute elapsed timer after pull/root check. Print UTC/ET start and hard deadline. All I/O, engineering, discovery, tests and push count. Plan:

- 0–20: bounded data/accounting/schedule work, side-correct fixtures and fast caches.
- 20–55: directed short allocation cores and selected rhythm comparisons.
- 55–120: protected long development, iteration and falsification; include substantial Astra-originated work. Start long plumbing earlier if needed so this is research time rather than only setup.
- 120–132: commit freeze, one OOS batch, chronological account replays.
- 132–150: final audit, focused/full tests, reports, public-safety review, commit/push/remote equality.

Approximately 60% director-led / 40% investigator-originated discovery remains a planning balance, not a hypothesis-count quota. If short cores require more time, reduce their neighbors/cross-products, not the long engine to a token mirror. Aim for at least 55–60 minutes of substantive long research when inputs are usable. Do not inflate hypothesis counts with replays, scenarios or bookkeeping.

Do not reveal OOS before minute 115 merely because initial mirrors fail or one challenger wins. Do useful IS work, not artificial waiting. Earlier freeze is justified only by measured completion cost or a genuine blocker, with an explicit explanation. Stop launching branches that cannot finish with closure reserve intact. Every launched experiment ends in scored results or a specific real data/execution failure; no unfinished queues. Discovery failure is a valid result; fabrication is not.

Emit progress at least every ten minutes: elapsed, short/long hypothesis counts, current IS tradeoffs, data coverage and next action. Checkpoint after completed batches with identities, elapsed budget and reveal status. An interruption does not silently reset the budget or reopen confirmation. Never force-push or overwrite unexpected local work. No background jobs continuing beyond handoff.

## 9. Deliverables and tests

Publish reviewed code/tests and concise, audit-friendly files:

- `reports/cg_arrow004_report.md`: scope/clock, repair status, ranked short and long results, investor pitches only where justified, IS/OOS comparison, all twelve monthly returns, capital utilization and what did/did not repeat.
- `reports/cg_arrow004_schedule.csv`: nominal/actual entry/signal/expiry dates and times, phase, hold duration, actual filled/failed/delayed aggregate counts. Include an ordinary three-Thursday illustration showing the retained one-week cohort.
- `reports/cg_arrow004_ledger.jsonl`: every mechanism, exact spec, source/lineage, predeclaration, controls, scores, runtime, disposition and superseded fixes. Separate genuine mechanism rejection from a dominated but profitable variant.
- `reports/cg_arrow004_repairs.md`: new versus retained common treatment; lifecycle coverage for primary/reserve/long names; unresolved observations, action evidence and materiality; no raw vendor payload.
- `reports/cg_arrow004_freeze.json`, `reports/cg_arrow004_results.json`, `reports/cg_arrow004_daily.csv`, `reports/cg_arrow004_commands.txt` with input/dependency identity, exact commands, tests, timing and interruption state.

Publish account aggregates, not raw bars, quotes, credentials or proprietary detailed trade data. Retain detailed local order/position/source ledgers with safe hashes and paths. Avoid unnecessarily huge redundant JSON output; compact metrics plus local detail references are sufficient.

Required focused tests: positive/negative side cash and liabilities; proper cost signs; Wednesday-known features; two-week nominal expiry; holiday/early-close handling; both biweekly phases fixed across month boundaries; 15:00 exits before 15:59 entries; last week's cohort survives; pending exits do not free capacity; weekly B is half G, not half cash/H; short proceeds do not double equity; no virtual accumulation of unused credits; safe simultaneous allocation; primary/reserve accounting; selection can genuinely use ranks9–20; long ret3 sign reversal; unknown reserve state not full conviction; future-exit-independent entries; terminal/stale inventory; freeze and one-shot OOS identity; monthly/daily/total conservation.

Run the complete `tests/` explicitly rather than walk all data directories. Inspect staged paths AND content for public safety. Commit the freeze before reveal and final artifacts afterward. Verify remote SHA and clean intended work. Handoff must state completion or exact failure, elapsed/short/long effort, tests, confirmed tradeoffs and caveats. No Arrow 005.

## Source/interpretation notes

The prior repository evidence is Arrow 003 at the starting snapshot, particularly its repair and lifecycle reports. All S/L mechanisms here are proposed experiments, not established edges. The two-week cohort mandate and reserve/long scope reflect the user's final September 13 instruction; this overrides the earlier tentative 5/10/15-horizon suggestion.

Official context (not signals or new requirements): NYSE regular/early-close hours, https://www.nyse.com/trade/hours-calendars ; investor account/margin distinction, https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work/types-brokerage-accounts ; long/short cash obligations, https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work/stock-purchases-and-sales-long-and . Research exposure targets and same-day margin-account redeployment are modeling assumptions, not broker approval or cash-account settlement certification.
