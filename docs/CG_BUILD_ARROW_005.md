# CG Arrow 005 — Fable: verify H10 / R4 / R5, then census H1–H10

## Mission and authority

**Executor: Fable in Claude Code.** This is an engineering and forensic reconstruction assignment followed by ONE explicitly authorized horizon experiment. It is not another open-ended model search. The user requires an auditable answer to whether the apparent R4/R5 economics survive corrected data and accounting; either positive or negative findings are acceptable. Do not presume the answer from optimistic historical reports or pessimistic valuation sensitivities.

Work only in `C:\Users\james\money_chatgpt`, remote `jamesksnyder99/money_chatgpt`. Never access `C:\Users\james\Money`, including its credentials. No live orders, new subscriptions, account changes, or original-source modifications. Fable replaces Codex as the assigned executor. Do not run two agents that write this workspace concurrently. Stop after this arrow and hand back the reviewed result; do not begin Arrow 006.

**Initial allocation: 180 minutes elapsed, including acquisition, code, verification, the conditional horizon study, reports, tests and push.** This is a repair-first allocation, not 180 minutes of optimization. No automatic overtime. There is no 20-minute repair cap. If complete reconstruction needs more time or unavailable evidence, deliver the completed work, exact unresolved requests and resumable checkpoint, and label the pass incomplete. Never shorten verification, delete cases, or open the horizon study merely to report completion within the allocation. Do not consume all time without delivering the exception ledger and code/data manifests.

Core sequence: **preserve evidence → obtain missing observations → reconstruct unchanged H10 baselines → independently reconcile and commit their verdict/CSVs → only then compare H1–H10 with identical entries.** Baseline losses do not prevent a horizon census if the evidence is complete. Baseline profits do not excuse missing evidence.

The user's September 14 instruction authorizes H1–H10 and supersedes Arrow 004's two-week-only restriction for THIS study. Do not silently redefine earlier models. Here Hn means n exchange trading sessions AFTER the fill; fill session = H0. The equal-dollar parent is named `PARENT`, not confused with the H10 exit-horizon label shared by all three families.

## 1. Read selectively; establish the initial checkpoint

Read `CLAUDE.md`, `AGENTS.md`, `docs/CHATGPT_LAB_PROTOCOL.md`, `docs/SUCCESS.md`, and this arrow. Then:

- `reports/cg_arrow003_report.md`, `cg_arrow003_repairs.md`, `cg_arrow003_lifecycle_coverage.json`, and the relevant PARENT/R4/R5 historical specifications.
- `reports/cg_arrow004_repairs.md`, `cg_arrow004_coverage_all.json`, `cg_arrow004_valuation_reference_audit.json`, and relevant parts of `cg_arrow004_reference_sensitivity.json` and `cg_arrow004_report.md`.
- `src/ingest/eligibility.py`, `full.py`, the corresponding virgin acquisition path, `paths.py`, `manifest.py`, `src/theta/client.py`; relevant `arrow65.py`, `cg_arrow003_data.py`, `cg_arrow003_lab.py`, and Arrow 004 timing/account code.
- Historical tests and command manifests as needed, not the entire archive.

Starting evidence snapshot: `fee07b8fe25bcac31070c36931a0dbcfe54a9a63`. Pull current main with `git pull --ff-only origin main`, inspect local changes without overwriting them, verify root/remote, and record UTC/ET start, deadline, Python/SDK versions and data/code identities. Read-only prior reports are evidence, not claims to accept on faith.

Before outcome-dependent decisions, write and commit `reports/cg_arrow005_plan.json`: exact baseline specs, replay stages, source hierarchy, verification tests, comparison tolerances, missing-data policy, all 30 family/horizon cells, and cost scenarios below. Permission to inspect full-year prices for data repair does not permit discretionary strategy changes. Never reopen/delete previous arrows' freeze or OOS markers.

## 2. Precisely identify the controls

Primary verification and horizon families, all short:

- **PARENT:** inherited point-in-time common-stock/exclusion field; prior close $10–$80 and prior-day dollar volume at least $10 million; Wednesday top eight by 15-session RTH close return; original fixed $4,000 tickets.
- **R4:** same selection; intended $5,150, multiplied by 0.5 when signal-session RTH volume is ABOVE the arithmetic mean of the preceding 20 RTH sessions, excluding the signal day. Equality is full size. Preserve the documented neutral missing-feature behavior only for genuinely unavailable history, not acquisition omissions that can be repaired.
- **R5:** same selection; $8,300, independently multiplied by 0.5 for positive three-session signal-close return and by 0.5 for the same above-mean volume condition. Intended tiers $8,300 / $4,150 / $2,075. Zero ret3 is not positive.

For original H10 use the original entry date, next-session late-RTH convention and ten-session exit; the historical policy uses minute CLOSE prices, not Arrow 004's OPEN prices. Pin exact dependencies and specifications rather than relying on this summary. No compounding, replenishment, new budget normalization, stops, partial covers, reserve names, long models, or changing the entry schedule. All three controls must be evaluated on a common corrected candidate field with family-specific fixed sizing.

Preserve the historical late-print and fill-price-based share-sizing conventions as explicitly labeled modeling assumptions in a legacy-compatible replay. Audit whether they use a later-known price to choose integer shares or a retrospectively identified last print. Do not certify such a convention as a real submitted order. Where an execution-causality repair is required, isolate a separately named pre-order-quantity/fixed-time implementation and a timing/quantity reconciliation; do not hide it inside a data repair or select its clock by profitability.

Secondary reconciliation, AFTER primary H10 verification and only if budget permits: replay Arrow 004 `BRIDGE_R4/BRIDGE_R5` and budgeted `S0_R4/S0_R5` unchanged to determine how much of their stale-valuation sensitivity disappears when actual scheduled exits are supplied. They are not the same original fixed-ticket baselines and are not the main H1–H10 families. Do not let these secondary books consume the primary ledger/verification budget.

## 3. Data repair: new versioned layer, not rewriting history

Preserve all original `data/full`, `data/virgin`, `data/ref`, previous local caches and historical reports. Add `data/verification/r4r5/v1/` (or a documented subsequent version) with acquisition/raw, validated minute partitions, reference/actions, coverage manifests, derived views and run-specific caches. Store raw new responses immutably before transformation; atomic writes and one writer per partition. Use safe symbols and canonical ET/UTC timestamps. Do not create links back to Money.

A centralized new loader must resolve validated repair-layer observations first, then original observations ONLY if their identity/convention/coverage has been checked. Record which source supplied each critical observation. Do not scatter absolute paths or silently change old loaders' behavior. Reuse valid data; reacquire missing/suspect partitions rather than indiscriminately delete/rebuild the whole corpus. Invalidate new derived caches whenever input, calendar, event or transformation identities change.

### 3A. Actually test data access early

Use existing lab `.env`/environment credentials through the installed official ThetaData SDK. Check presence/auth mode without printing secret values. Do not infer credentials are missing merely because they were not committed. Do not use/copy Money credentials. If authentication is genuinely absent or entitlement fails, report the exact local setup needed without revealing secrets.

Make real small historical retrieval tests, including an ordinary known-good day and known missing-exit cases such as SNDK 2025-09-25 and DNTH 2026-04-02. Verify returned symbol/date/time/adjustment semantics, nonempty tradable observations and overlap with good local data. A cached report or an empty local file is not a successful API test.

Authorized: targeted historical one-minute data for the required candidate endpoints, selected-name features and lifecycle windows, including prices outside previous acquisition bands, and documented corporate-action/reference retrieval under existing entitlements. Targeted historical trade/quote evidence to corroborate critical execution observations is permitted if already entitled with no added charge; no new sub-minute-bar research corpus or streaming. No paid flat-file purchase, new subscription, service signup or authentication detour. Read installed method signatures/current official documentation; do not guess endpoints. At most eight concurrent vendor requests or the lower permitted limit; backoff/retry boundedly and honor vendor restrictions.

If a provider lacks a specific case, consult permitted primary sources or another already-authorized compatible source and record the hierarchy. Do not claim that a vendor has every required historical observation before testing. If new paid access is necessary, stop that acquisition branch and identify the exact symbol/date/product deficiency. Continue independent local reconstruction tasks, but no unsupported verified verdict.

### 3B. Build a manifest of what is actually required

Inventory every scheduled cohort/slot, candidate ranking endpoint, selected feature window, entry and H1–H10 exit observation, and intervening valuation session. Deduplicate requests across models/horizons. Coalesce by symbol/date window where efficient.

Acquisition eligibility is NOT lifecycle coverage. Once a security is needed, request the entire required interval despite price, dollar-volume, delisting or entry-eligibility changes. Also recover pre-signal observations when a currently eligible name was outside the bands earlier. Do not cap the reconstructed field at today's survivors or the old eight/twenty.

Required status per observation/window: PRESENT_CHECKED; NOT_PREVIOUSLY_REQUESTED; EMPTY_RESPONSE_UNRESOLVED; PARTIAL_OR_SPARSE_REVIEW; RETRIEVED_CHECKED; DOCUMENTED_NO_TRADING; CORPORATE_ACTION_OR_ID_REVIEW; UNRESOLVED. Include request identity, timestamps, source, adjustment/session convention, row/time coverage, hash, attempts and reason. These labels describe evidence, not investment outcomes.

Replace the repair path's `file exists = complete` resume logic. An empty parquet is not coverage of a requested exit. Do not demand exactly 390 positive-volume bars for every real security; legitimately sparse trading and early closes require documented handling. Check ordering, duplicate/conflicting timestamps, OHLC consistency, nonnegative volume, trading calendar, timezone, trade-condition conventions and suspicious discontinuities. A price jump is an investigation flag, never an inferred split or automatic bad-tick deletion.

### 3C. Calendar, event and identity coverage

Retain September 2025–August 2026 SIGNAL cohorts, plus sufficient August 2025 warmup. Acquire beyond August 31 through the last required H10 exit of those cohorts (normally into September 2026); derive exact dates from the verified exchange calendar and do not request/fabricate future observations. No new September signal cohorts enter the study. Identify exchange holidays, early closes and date-specific DST rather than count generic weekdays.

Audit actions for all actual trade/feature histories AND all relevant ranking competitors/endpoints. Checking only previously selected tickers cannot certify the reconstructed top eight. Obtain a scoped event/security-reference census; if unavailable, explicitly separate verified fixed-selection results from RANKING_SCOPE_UNVERIFIED. Do not represent eight previously documented events as complete coverage.

Preserve raw trade prices. Use documented as-of factors to transform historical comparison prices and share volumes into consistent units; adjust held quantities, basis, frozen price-unit features and cashflows at the effective event. Do not apply future events to exclude an earlier candidate. Resolve symbol changes through security identity. Treat mergers, delistings, dividends, special distributions and fractional-share/cash-in-lieu obligations from evidence; unknown amounts remain unknown. No guessed zero or factor. Verify eligibility price/dollar-volume units around event dates as well as return ranks.

## 4. Engine repairs and the two reconstructions

Implement a new verification runner with small reusable modules (suggested: `src/verification/r4r5_data.py`, `r4r5_replay.py`, `r4r5_oracle.py`, `r4r5_horizons.py`, `r4r5_export.py`). Exact module names are flexible; publish the actual file/function change map. Preserve old strategy modules/results as historical evidence. Shared production helpers may be changed only with regression proof and an explicit legacy compatibility path, not a silent rewrite of all old arrows.

Mandatory engine behavior:

- Candidate selection and valid entry orders never depend on future exit availability. Export every intended slot, including missed and unresolved entries.
- Explicit scheduled exit event/time for every position/horizon. Missing local data triggers retrieval/review, not deletion, backdating to an earlier print, or a claim that the market prevented execution.
- If the recovered market shows a real halt/no executable trade, follow the predeclared causal order policy and document the later actual event. If only our dataset is missing, label the intended outcome unresolved. A diagnostic carried/late observation cannot certify the scheduled trade.
- Stale prices may maintain an explicitly uncertain liability record. They cannot qualify as VERIFIED_PRICE exits/marks or silently enter verified account totals. Show unresolved inventory separately; known-part subtotal is not the total-model result and is not a conservative bound on short losses.
- Cash/equity, share quantities, event cashflows and costs reconcile independently. For ordinary shorts price PnL is Q*(entry-exit); corporate actions require actual adjusted quantities/cashflows. Shares remain fixed by the entry instruction, except documented actions. Exits do not create profits equal to their released notional.

Replay stages, with separate identities/results:

**R0 — forensic legacy reproduction:** reproduce the relevant historical PARENT/R4/R5 recorded result and preserve its known flawed sampling/treatment as history only. Use read-only frozen records or an isolated compatibility runner, not old research-gate reopening. Identify whether a record belongs to original fixed-ticket H10, timing bridge, or equity-budgeted variant.

**R1 — fixed historical decisions, corrected observation/accounting:** recover EVERY originally intended selection, including positions previously omitted for missing future data. Keep original names, signal/entry schedule and recorded signal sizing instructions. Use recovered entry/exit observations and documented actions. Apply the frozen quantity formula; show old quantity and any observation/unit-driven quantity change explicitly. Preserve recorded feature decisions here so feature repairs do not disguise exit-repair effects. If the old candidate record itself is incomplete, mark that provenance limit.

**R2 — unchanged rules, complete input reconstruction:** rebuild the intended point-in-time eligible field, ranking endpoints, top eight and features from checked inputs, without silently excluding names because their historical acquisition was incomplete. Apply unchanged PARENT/R4/R5 rules and quantity/execution convention. Export old/new memberships, rank and feature differences and reasons. Newly selected names receive the same lifecycle checks. No ticker/month whitelist, performance-based data exclusion, coefficient fitting, new thresholds or model tuning.

R1 answers what the previously intended trades actually imply; R2 answers what the unchanged algorithm with complete inputs would have selected. They are different questions. Reconcile through named steps: restored entries/exits, valuation corrections, actions, ranking/membership, feature/sizing changes, execution-convention changes if necessary, and costs. Fix the waterfall order before reading outcomes; interacting changes are order-dependent and must not be overclaimed as unique causal attribution.

An independent calculator must read the finalized event/trade CSV and source evidence without calling the primary PnL/selection helper. Verify quantities and costs, trade PnL, cohort subtotals, realized plus open inventory, daily cash-minus-liabilities and totals. Use full precision internally and explain currency rounding; require cent agreement at reporting level and tighter deterministic internal reconciliation. Separately check price observations against newly obtained/source-corroborated data; using the same source twice is an accounting cross-check, not independent price validation.

## 5. Price verification, costs and baseline release gate

For every claimed entry and exit, record observation timestamp, bar open/close/last-trade field, condition/session convention, source and hash. Critical corroboration covers ALL H10 entry/exit observations where entitled sources permit, with independent-source review of discrepancies and all previously missing/action-affected/high-impact cases. A second endpoint from the same vendor is corroboration, not a second independent vendor. If only one source is available, disclose that level rather than invent a double-check.

The observed bar price is a simulation reference, not a guaranteed historical broker fill. Pin the price and quantity convention before outcomes. Original fill-close quantity sizing is labeled as such; separately show any causally executable pre-order correction, never silently change entry timing to help results. Reconstruct close bars from trades when needed, using documented conditions. A national EOD observation is not interchangeable with an RTH/intraday fill. Test quote/spread/latency assumptions where evidence permits; no claim of historical locates from a liquidity proxy. Inspect and identify inherited borrow/SSR proxy behavior and changes across engine generations rather than assume it is actual borrow availability.

Separate:

1. Price/action/quantity-verified SIMULATED gross PnL.
2. PnL after documented or explicitly modeled commissions/execution costs, including known dividend obligations.
3. Scenario net PnL where borrow/locate/financing evidence is unavailable. Unknown values are null plus status, NOT zero verified costs.

Freeze inherited commission $0.005/share/side and spread proxy max($0.01,0.001*price)/side for the main comparable model-cost series; show base/doubled spread, commissions unchanged, and 0/10/30% annual stock-borrow scenarios by actual calendar holding days. These are assumptions, not current quoted rates. No idle cash yield. Include actual documented expenses separately without double-counting a quote execution price and the same spread proxy. Unknown loan history does not prevent verified price arithmetic or a clearly conditional model-cost horizon study; it prevents calling the result fully verified executable net economics.

Publish a baseline checkpoint before horizons with independent statuses for: historical selection provenance; complete reconstructed ranking scope; entry/exit price coverage; actions/security identity; daily valuation coverage; accounting reconciliation; executable fill assumptions; loan/dividend/financing coverage. Never compress these into a misleading all-green flag.

**Horizon release gate:** R2 primary baseline trade/feature/action observations and price-accounting must reconcile; no unexplained missing entry/exit or material corporate-action/identity/selection gap may be hidden. Each valid slot must be priced or supported by a documented non-execution/event treatment. Daily-risk claims require checked intervening marks. If material scope/data gaps remain, deliver partial verification and DO NOT use a surviving complete-trade subset to promote shorter holds. You may build/test the horizon exporter on synthetic data, but do not call it a completed investment study.

No requirement that H10 be profitable. Commit the completed baseline report, safe manifest and local-ledger hashes before beginning scored H1–H10 work. Completed baseline H10 performance, including its OOS totals, is verification context, not a new independent confirmation sample.

## 6. Mandatory user CSVs — first an exception export, then a reconciled audit

Stage detailed files locally under `handoff/outgoing/cg_arrow005/`, ignored by Git. No ZIP is required. Their entry/exit observations and detailed positions are for the user's private review, not automatic public-GitHub publication. Public reports contain safe aggregates, hashes, schemas and exact local paths. GitHub is not the only delivery requirement: identify the CSVs clearly in the final terminal handoff so the user can open/upload them individually.

Required files:

- `r4r5_trade_exceptions.csv`: initial and final status of EVERY intended slot, including missing, missed and unresolved events. Retain an initial snapshot.
- `r4r5_verified_trades.csv`: one row per cohort/security per replay version, no subtotal rows. Side-by-side PARENT/R4/R5 quantities and PnL when membership/observations are shared; explicit presence/model keys where they differ. The filename is the requested audit artifact, NOT permission to mark unresolved rows VERIFIED. Include per-domain verification status and null unverified net totals.
- `r4r5_verified_cohort_audit.csv`: eight intended TRADE rows, then COHORT_SUBTOTAL with expected/filled/closed/verified/unresolved counts. Preserve MISSED_ENTRY or NO_CANDIDATE slots rather than manufacture eight fills. Add clearly typed signal-month and IS/OOS/period totals, never count subtotals twice. Cohort is the primary natural break; calendar returns come from daily MTM, not allocating all trade profit to exit month.
- `r4r5_cohort_matrix.csv`: optional compact wide presentation if useful: one row per cohort, slot01..slot08 symbol/entry/exit/quantity/PnL fields and cohort totals. Do not sacrifice the canonical tidy ledger for this convenience view.
- `r4r5_daily_account.csv`: dated cash, realized/unrealized price PnL, model costs, events, equity, gross, fresh/stale/overdue inventory for each baseline; complete twelve calendar-month reconciliation.

Minimum trade fields: model/spec/replay/data version; cohort ID; original signal date/month and split; rank/security ID/ticker; 15-session return, ret3, volume ratio and feature availability; intended size and size tier; scheduled/order/observed entry timestamps, price field and price, quantity; scheduled/order/observed exit timestamps, price field and price, exit/event reason; entry/exit source IDs and corroboration; dated quantity adjustments/cashflows; gross PnL; per-side commission/spread; dividends; borrow/locate/financing amount or assumption/status; modeled net; actual holding sessions/calendar days; verification status/reason.

All August cohorts remain included. Show August 31 account marks and later scheduled closing outcomes in separate fields/views; do not put September realization into August calendar PnL. Follow-up dates are exits of old cohorts, not new research signals. If a required later event is not yet observable, disclose it and do not fabricate future data.

## 7. H1–H10 study — only after the baseline checkpoint

Authorized grid: **3 fixed sizing families (PARENT, R4, R5) × horizons 1,2,3,4,5,6,7,8,9,10 = 30 cells**, not an open-ended parameter search.

Within each family clone the SAME verified R2 entry ledger: identical eligible field, selected eight, signal/entry timestamps, entry observations, initial shares and entry costs. Only scheduled exit age changes. Exit on the corresponding exchange session at the SAME late-RTH price convention used for that family's verified original H10. Fill day is H0. H1 is next trading-session exit, not an intraday exit. This is not the separate Arrow 004 calendar-two-week/15:00 clock. If the causally executable quantity bridge is needed, label its fixed panel separately and never mix it with the original-convention panel.

No additional entries when a shorter hold frees capital; no proceeds reinvestment, exposure-restoring leverage, compounding, stock replacement, calendar phase changes or post-entry resizing. Weekly signal schedule stays fixed even if H1–H4 leave flat periods. An H5 book freeing exposure sooner does NOT automatically trade twice as often. Higher measured return per dollar-session is not a demonstrated reinvestment gain. The soft $130k policy is descriptive for these fixed-ledger comparisons, not a new cap that changes which entries exist by horizon.

Acquire/check all H1–H10 exit observations, not just H10. Do not compare different surviving trade samples across horizons. Unknown endpoint/action evidence invalidates the affected model-level comparison pending repair; no omission-based winner. Coherently handle documented nontrading/security events and disclose when actual durations differ from intended n.

### Practical IS/OOS process

IS: September/November 2025 and January/March/May/July 2026. OOS: October/December 2025 and February/April/June/August 2026. Membership follows original signal date; causal lookbacks and holdings may cross boundaries. No formal purity/embargo project.

Phase A repair may inspect full-year source data and unchanged H10 results, because facts must be checked consistently. Explicitly record that exposure. No repair decision or source choice may be selected for favorable profit. Previously observed OOS and repaired H10 OOS are known context; this is INTERNAL reused confirmation, not pristine validation.

Do not produce H1–H9 OOS scoreboards during repair or IS horizon exploration. After baseline gate, score the 30 IS cells. Summarize profit-first and ride-first alternatives versus each family's H10, robust neighboring horizons and horizon-contribution patterns. Predeclare any preferred horizon(s), primary claimed benefit and tolerable downside from IS only; choosing none is acceptable. Do not fit state-dependent exits or sizing-tier-specific horizons in this arrow.

Commit the complete horizon matrix rules, entry-ledger hashes, costs, data identity, preferred IS interpretations and code before **one batch revealing ALL 30 OOS cells**. H10 is already-known context, not a new independent look; verify equality with the locked baseline. Do not switch the preferred horizon after reveal and call it confirmed. No post-OOS parameter changes. If a code/data defect emerges after reveal, disclose the affected confirmation as invalid; an identical interrupted job may resume, but not a silently corrected second optimization look.

Publish post-freeze all-signal chronological accounts for each horizon. Preserve constant quantities and all calendar sessions, including flat dates. Show the twelve-month account ending August 31 AND full-runoff closed-trade totals separately. Main $/session uses the 124/127 signal-session denominators or 251 account sessions as appropriate and labels them; do not divide completed September-runoff PnL by 251 and call it twelve-month earned income. Label any full-runoff PnL per original-signal session explicitly. No truncated month concatenation in DD.

### Horizon outputs

For each family/horizon/split: entries; completed trades; wins/losses/flats; hit rate; average winner/loser; payoff ratio; profit factor (null when undefined); gross and modeled/scenario net PnL; $/session with named basis; closed versus terminal PnL; DD dollars/percent; worst day; red-month count/loss sum; worst/median month; holding days; average/peak gross; exposure-dollar-days; turnover and utilization; sizing-tier contributions. Treat open tickets separately from closed-trade win/loss counts.

Also show paired SAME-TRADE increments H1→H2 ... H9→H10, separating price movement, additional borrow/dividends and differing exit costs. H0 is entry/entry-cost state, not a fictitious round-trip. Provide a holding-age aggregate curve H0..H10 for IS and OOS, with labels distinguishing cross-trade holding-age curves from chronological account equity.

Local CSVs: `r4r5_horizon_trade_paths.csv` (cohort/slot plus H01..H10 exit date/price/PnL columns or a companion tidy version), and `r4r5_horizon_summary.csv`. Public safe aggregates: `reports/cg_arrow005_horizons.csv` and curve/report artifacts without raw vendor observations. No claim that ten highly related horizons are ten independent discoveries.

## 8. Work products, tests, clock and handoff

Public outputs:

- `reports/cg_arrow005_verification.md`: neutral verdict by domain/model, exact defects, tested vendor access, repaired coverage, R0/R1/R2 results, unresolved cases, old-to-new waterfall and what can/cannot be claimed.
- `reports/cg_arrow005_file_changes.md`: exact added/changed .py files/functions, purpose, data paths, counts/bytes acquired, loader precedence, cache/version behavior and preserved evidence hashes.
- `reports/cg_arrow005_manifest.json`: code/input/action/calendar identity, coverage and corroboration counts, safe local CSV paths/hashes, replay/verification levels.
- `reports/cg_arrow005_commands.txt` and checkpoint ledger: reproducible acquisition/replay/oracle/export commands, errors/retries, actual timings, gates and test results; never credentials.
- `reports/cg_arrow005_horizon_freeze.json` and `reports/cg_arrow005_horizon_report.md` only if the horizon gate opens; otherwise an explicit NOT_RUN_DATA_GATE status, not an empty success artifact.

Required tests: original evidence unchanged; acquisition beyond both $50/$80 ceilings and below entry floor; warmup without historical eligibility filtering; empty-file resumption; timezone/early-close/holiday calendar; price/volume/share-unit corporate-action neutrality; no future exit-dependent entry; genuine documented no-trade versus local missing data; no stale price marked verified; every intended slot exported; quarter/fractional/event cash handling where relevant; original and causal execution conventions separately reconciled; same entries/shares at all horizons; Hn shift and H10 baseline identity; cutoff/runoff separation; costs/signs/dividends; independent cash/PnL oracle; subtotal conservation and closed/open win counts; versioned gate and single batch OOS; no raw detail in public Git.

Use at most the host-appropriate compute workers and eight vendor requests total, with one writer per partition. Inspect before changing existing files; do not undertake unrelated refactors or run another million-file inventory. Safe incremental checkpoints protect useful work. State elapsed time, coverage/request progress, last verified stage and blockers at least every ten minutes.

Suggested 180-minute allocation: initial 10–15 minutes for plan/authentication/pilot/exception export; majority for lifecycle/ranking/actions/engine repair and baseline reconciliation; reserve roughly 30–40 minutes for the conditional horizon scoring/freeze/report and final tests/push. This is NOT a mandatory split: repair completion is the gate, not a clock milestone. At minute 150 assess whether verified baseline plus closure fits; never start horizons with unresolved substantive data merely to use the research allowance. A ready, predeclared horizon census can finish early; no requirement to burn time inventing variants.

Run full `tests/` suite explicitly with temp files under ignored lab data/tmp, plus focused verification tests. Inspect staged paths AND contents. Commit safe reports/code/tests and push to `origin/main`; no force push. Detailed CSVs, raw observations, vendor data and credentials stay local/ignored. Report final remote SHA equality and intended working status. No jobs continuing after handoff.

Terminal handoff: completion versus partial verification; actual elapsed time; source requests/recovered/unresolved observations; original versus reconstructed baseline economics; level of price/action/account/cost verification; test counts; horizon gate status and any result; public commit SHA; exact CSV file paths. Fable must not declare success from a positive subtotal, assume negative sensitivities are the answer, or claim broker-fill certainty from a bar replay.

## Official references and interpretation

Use current official documentation with the INSTALLED SDK; these source links describe data conventions, not instructions to launch a REST terminal:

- OHLC timestamp/interval semantics: https://docs.thetadata.us/operations/stock_history_ohlc.html
- National EOD observation scope: https://docs.thetadata.us/operations/stock_history_eod.html
- Python SDK entry point: https://docs.thetadata.us/Python-Library/Getting-Started.html

The code/report defect evidence is in the repository at the starting snapshot, especially `src/ingest/full.py`, `src/ingest/eligibility.py`, `src/research/arrow65.py`, and the Arrow 003/004 coverage/repair reports. This arrow orders verification; it does not assert that missing prices are available, that old profits are correct, or that old models are losers.
