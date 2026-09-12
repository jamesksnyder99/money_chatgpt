# CG Build Arrow 002 — 150-minute recursive laboratory for hold-short-for-fade

Read, in this order:

1. `AGENTS.md`
2. `docs/CHATGPT_LAB_PROTOCOL.md`
3. `reports/cg_arrow001_baseline.txt`
4. `docs/SUCCESS.md`
5. `reports/arrow66_results.txt`
6. `reports/arrow70_results.txt`
7. `reports/arrow71_results.txt`
8. `reports/arrow72_results.txt`
9. `src/research/arrow65.py`
10. `src/research/arrow66.py`
11. `src/research/arrow70.py`
12. `src/research/arrow71.py`
13. `src/research/arrow72.py`

CG Arrow 001 established an exact independent reproduction. This arrow is the first **bounded recursive research laboratory**.

Do not access `C:\Users\james\Money`. Work only in `money_chatgpt` and its copied data.

Do not invent or begin CG Arrow 003.

---

## Mission

Improve the frozen **hold-short-for-fade** engine in two dimensions at once:

1. **larger fully modeled profit**, and
2. **a smoother investor ride** — fewer/redder months becoming less negative or green, smaller continuous marked-to-market drawdown, smaller worst month/day, and less dependence on a single windfall month.

The frozen economic idea remains the control:

- Wednesday signal;
- eligible common-stock field `$10–$80`, prior-day dollar volume `>= $10M`, inherited ETP denylist;
- rank the eight largest 15-session close-to-close returns;
- fill next session last regular-hours print (`nextrth`);
- `$4,000` nominal ticket;
- hold ten trading sessions from fill;
- inherited transaction-cost model;
- marked-to-market daily equity.

You may alter those rules in variants where this arrow expressly permits research, but the frozen parent itself must remain available and unchanged as a control.

CG Arrow 001 reproduced the continuous 12-month parent at:

- 251 NYSE sessions, 2025-09-02 through 2026-08-31;
- total MTM profit `$51,855.71`;
- `$206.60/day`;
- max MTM drawdown `-$20,033.68`;
- worst marked day `-$6,607.31`;
- 376 completed trades;
- peak marked live exposure `$102,922`.

Those are provenance checks, not fresh evidence.

---

# Scientific constitution — non-negotiable

## 1. Twelve-month IS/OOS split

Use the full available 12-month signal calendar.

**IS / training signal months:**

- 2025-09
- 2025-11
- 2026-01
- 2026-03
- 2026-05
- 2026-07

**OOS / confirmation signal months:**

- 2025-10
- 2025-12
- 2026-02
- 2026-04
- 2026-06
- 2026-08

The split is by the **signal date/month**, consistent with the inherited research convention.

A trade opened from an IS signal may require later bars from an even calendar month to complete its fixed lifecycle or mark its path. Those lifecycle bars are permitted. What is forbidden before freeze is scoring, ranking, diagnosing, filtering, or tuning on **even-month signal cohorts**.

Likewise, do not inspect candidate performance tables for even-month signal cohorts, even if convenient code already exists to print them.

These even months have been seen historically in the Money project; therefore they are **not pristine external validation**. In this arrow they are nevertheless protected confirmation data and must remain outside this run's training loop.

## 2. OOS firewall

During recursive research, use **IS signal cohorts only**.

Before any finalist sees OOS:

- write a freeze manifest containing every finalist's complete rules, parameters, sizing, entry/exit behavior, capital rule, and code identifier;
- include the Git hash / code state used for freeze;
- after that manifest is written, do not alter finalist rules based on OOS results.

Then score all frozen finalists on the six OOS signal months **once**.

After OOS is revealed:

- no threshold changes;
- no deleting a bad month;
- no switching finalist identity because another nearby version would have done better;
- no new hypothesis prompted by OOS within this arrow;
- no second OOS look after repair/tuning.

If OOS disappoints, report it and stop.

## 3. Causality

Every signal, state variable, exit decision, and size decision must use only information available before its execution.

If a rule makes a decision using a 15:55 checkpoint, execute no earlier than a subsequent tradable print.

Do not rank using a bar and fill that same bar unless the rule is explicitly a noncausal diagnostic, in which case it cannot be a finalist.

## 4. Costs / economics

Use inherited transaction costs for comparability. Do not claim this is fully loaded live short economics: historical stock-loan fees/dividend obligations are not available in the copied model.

For frozen finalists, also print a simple **borrow-cost sensitivity** at 0%, 10%, and 30% annualized short market value, prorated by holding days. This sensitivity is reporting only and must not be used to tune a finalist.

## 5. Capital / risk inflation guard

A candidate does not improve merely because it takes more exposure.

For every candidate report:

- average marked gross exposure;
- peak marked gross exposure;
- mean and maximum simultaneously live symbols/tickets;
- total intended new-ticket notional;
- profit divided by average gross exposure where meaningful.

No variant with peak marked exposure above the frozen parent's `$102,922` may be called an improvement.

A **deployment-ready** finalist should fit at or below `$100,000` peak marked exposure. If the best research finalist still exceeds `$100,000`, label it research-only.

Where a rule reduces exposure substantially, include an exposure-matched or size-matched control when practical so smoothing is not falsely credited to the signal.

## 6. No opaque optimization

Prefer causal, interpretable rules/state machines. Small neighboring parameter checks are allowed inside IS when motivated by a completed branch, but do not launch broad brute-force grids, regressions optimized to this tape, or black-box models whose economic mechanism cannot be stated plainly.

## 7. Every tested hypothesis closes inside this arrow

Every hypothesis actually tested must have a completed result before this arrow ends.

No unfinished research queue, no “promising branch — score later,” and no deferred backtest.

If time becomes scarce, reduce the number of new hypotheses. **Reduce breadth, not completeness.**

Infrastructure work is not a tested hypothesis. If a branch cannot be scored because of a genuine infrastructure/data blocker, record it as `NOT TESTED — BLOCKED` and do not count it as evidence.

---

# Time budget — 150 minutes wall clock

Treat 150 minutes as a disciplined soft wall-clock allocation beginning after `git pull --ff-only` and the start banner.

Suggested allocation:

- **0–10 min:** integrity/preflight + build/reuse fast IS research harness/cache;
- **10–80 min:** ChatGPT-directed corridors below;
- **80–130 min:** Codex/Astra autonomous shop time;
- **130–140 min:** freeze finalists + single OOS confirmation;
- **140–150 min:** final report, focused tests, public-safety check, commit, push.

The intent is approximately **60% directed / 40% Codex-directed discovery** during the actual research portion. This is a planning ratio, not a rigid stopwatch quota.

A modest overrun of up to roughly 15 minutes is permitted only to finish:

- a hypothesis already executing before the budget expired;
- the frozen OOS pass;
- required tests/report/commit/push.

Do not open a new research branch after the 150-minute mark.

Do not stop early merely because one improvement is found. Use remaining research time to challenge it, search for alternatives, test nearby robustness, and try to falsify it.

---

# Step 0 — preflight and a clean split harness

Start by reproducing enough of CG Arrow 001 to ensure the frozen parent has not drifted.

Build/reuse a research harness that can score **signal cohorts by month** without accidentally exposing OOS cohorts during development.

For IS-only research, the engine should instantiate trades only from the six IS signal months. It may read later lifecycle bars needed to mark/exit those trades, but it must not generate or score even-month signals.

For each split-book compute at minimum:

- total completed PnL;
- PnL divided by the number of NYSE sessions in its six signal months;
- completed trade count;
- hit rate / profit factor;
- continuous MTM max drawdown across the actual lifecycle of those cohort trades;
- worst marked day;
- per-**signal-month** completed-trade PnL and dollars per session, so the six training months can be compared without mixing in even-month signal cohorts;
- red signal-month count;
- sum of losses across red signal months;
- worst signal month;
- average and peak marked gross exposure.

Also keep the inherited full-year continuous parent series for final, post-OOS investor reporting.

### Split/corporate-action integrity gate

Use `data/ref/splits.parquet` to determine whether split events can contaminate the 15-session return ranking or held positions during this 12-month study.

Do not inspect OOS candidate performance while doing this reference-data check.

If split handling is already safe, document why. If there are affected names and the inherited code would treat mechanical split price changes as economic returns, implement one common causal derived-price/position treatment before recursive search and rebaseline the parent. Apply that common repair to every candidate. Do not optimize the repair.

Keep this gate bounded; the purpose is to avoid optimizing a known data artifact, not to consume the research session.

---

# IS objective / Pareto board

Do not collapse the mission into one arbitrary magic score. Maintain a Pareto board.

For the IS parent and every viable candidate track:

### Return axis

- total IS cohort PnL;
- IS cohort `$ / signal-month-session`;
- profit per average gross exposure.

### Smoothness axis

- red IS signal-month count;
- total loss across red IS signal months;
- worst IS signal month;
- continuous IS-cohort max MTM drawdown;
- worst marked day;
- concentration of total PnL in the best IS month.

A **strict dual-improvement** candidate must:

- exceed the parent on IS total PnL, and
- improve at least two smoothness measures without materially worsening the others, and
- not increase peak marked exposure above the parent's `$102,922`.

Do not force the search to produce a strict winner if none exists.

Before OOS, freeze a small finalist set, ideally 3–5, representing useful frontiers such as:

1. best strict dual-improvement candidate, if one exists;
2. highest-return candidate whose drawdown is not materially worse;
3. smoothest candidate retaining at least ~90% of parent IS profit;
4. best deployment-ready candidate fitting `<= $100k` peak marked exposure;
5. best genuinely Codex-originated candidate if distinct and credible.

Avoid freezing multiple nearly identical parameter neighbors.

---

# Directed research block — approximately 60% of discovery time

These are **hypothesis corridors, not a mechanical grid**. Complete the core test in each corridor you choose to open. You may kill weak branches quickly after a completed result. You may refine a promising corridor recursively on IS.

At minimum, complete the first five directed corridors below unless a genuine infrastructure blocker makes one impossible. Corridor 6 is conditional on earlier exits actually releasing useful capital.

## D1 — risk-balanced sizing under the same economic idea

Hypothesis: equal-dollar `$4k` tickets allow volatile names to dominate risk; pre-signal risk balancing may smooth the ride without sacrificing the fade edge.

Core test:

- same Wednesday selections, delayed fill, hold 10;
- same intended `$32k` new-batch budget before account constraints;
- estimate each selected name's prior 20-session daily close-to-close volatility using information known by the signal close;
- allocate the `$32k` inversely to volatility;
- clip initial per-name intended allocation to `$2k–$6k`, then renormalize among the eight where possible;
- compare with equal-dollar parent and an exposure-matched control.

Small IS-only neighboring variants are allowed if the core result is promising, but do not grid-search clipping bands.

## D2 — repeated-name / symbol concentration control

Hypothesis: overlapping weekly cohorts can accumulate risk in the same persistent winner and worsen drawdowns.

Core tests:

- **cap/no-substitute:** at a new fill, clip the new ticket so aggregate entry-value exposure in that symbol cannot exceed 8% of `$100k`; unused allocation remains cash;
- **cap/next-ranked substitute:** same cap, but if a selected name has no capacity, walk down the precomputed Wednesday ranking to the next eligible name not already at its symbol cap until eight slots or the `$32k` batch budget is exhausted.

The ranking used for substitutes must be fixed from the signal close; no hindsight.

Compare both with a size/exposure-matched parent.

## D3 — cross-sectional width as soft exposure, not a binary hindsight filter

Hypothesis: a wide separation between the #1 and #8 15-session winners may identify cleaner fade opportunities and/or periods when the whole winner complex is unusually stretched.

Using IS only, define Wednesday **width** as raw 15-session return of rank #1 minus rank #8.

Core test:

- freeze the IS median width as the single regime dividing line;
- `$4k/name` when width is at/above the median;
- `$2k/name` when below;
- same entries/exits otherwise.

Compare against:

- always `$4k` parent;
- always `$3k` parent or another straightforward exposure-matched interpolation.

Do not import an even-month-optimized cutoff from inherited Arrow 72. The inherited result is motivation only.

## D4 — spread weekly timing without increasing intended weekly new capital

Hypothesis: one Wednesday batch creates avoidable timing concentration; distributing the same intended weekly allocation may smooth cohort luck.

Core test:

- generate the same 15-session top-eight signal on each actual trading session;
- fill next session last-RTH;
- hold ten sessions;
- intended total new-ticket notional for the week remains `$32,000` before capital constraints;
- divide that weekly amount across the actual number of signal sessions in that NYSE week and eight names per signal session;
- do not retroactively change the week's allocation based on later returns;
- enforce/measure aggregate account exposure.

If computational cost is excessive, a predeclared two-pulse approximation (e.g. two evenly spaced signal days with half weekly budget each) is acceptable, but document the choice before scoring it.

This corridor is about timing diversification, not adding five full-size books.

## D5 — protect an established fade, not an unproven one

Hypothesis: aggressive early exits failed because they removed trades before the fade matured; a giveback rule armed only after substantial favorable movement may preserve windfalls while reducing reversals.

Core test:

- freeze a 20-session Average True Range (ATR) at the signal date from information available then;
- original entry remains unchanged;
- no protective exit before hold day 3;
- arm only after a causal checkpoint observes price at least `2.0 ATR` below entry;
- after arming, track the most favorable observed checkpoint price;
- if a later causal checkpoint rebounds by `1.0 ATR` from that favorable low, exit on the next executable print;
- compare full exit versus one-time half exit with the remainder held to the original day-10 backstop.

Use a fixed intraday checkpoint supported by the one-minute tape (for example 15:55 decision / >=15:56 execution) and keep it constant in the core test.

A small IS-only neighboring check is permitted if core results strongly motivate it; do not build a large ATR grid.

## D6 — released-capital replacement (conditional)

Open this corridor only if a completed early-exit/protection candidate releases material capital while retaining credible IS economics.

Hypothesis: some performance lost by early exits can be recovered by redeploying released capital into a current stronger opportunity.

Core rule:

- candidate exit rule must already be frozen from IS work;
- replacement considered only if at least three sessions remain before the original slot's scheduled day-10 exit;
- at a fixed daily checkpoint, use the current causal top-eight ranking;
- choose the strongest eligible candidate not already held at its symbol/account cap;
- fill after the decision;
- at most one replacement per original slot;
- replacement inherits the **original slot's scheduled exit date**, so the test does not secretly extend capital duration.

Compare early-exit-to-cash vs early-exit-plus-replacement.

---

# Codex/Astra autonomous shop block — approximately 40% of discovery time

This time is protected for your own hypotheses.

Do not merely spend it walking parameters around D1–D6. Originate genuinely additional explanations for why the fade works in some periods and fails in others.

You may use any causal information already present in the copied laboratory data, including price path, volume, IWM context, cross-sectional state, SIC metadata, and the open portfolio state, subject to all governance above.

You may also combine two mechanisms after both have independently completed results and there is an economic reason for interaction.

Good autonomous research asks questions such as:

- What state distinguishes persistent winners that keep squeezing from exhausted winners that finally fade?
- Is the path to a 15-session gain (smooth grind vs one/few explosive days) more informative than total return alone?
- Is exposure to a common industry/crowd making drawdowns worse?
- Do entry-day or post-entry liquidity/volume states predict whether patience is rewarded?
- Can capital be withheld or resized in a causal state without simply deleting the bad months after seeing them?

These examples are not assignments. You own this block.

For each autonomous branch, write one sentence **before scoring** stating the causal/economic hypothesis being tested. Log whether it was your own (`ASTRA`) or derived from a prior branch.

Aim for substantive hypotheses, not cosmetic aliases.

---

# Research ledger — mandatory

Maintain `reports/cg_arrow002_research_ledger.csv` or `.txt` with one row/block per completed hypothesis.

At minimum record:

- hypothesis ID;
- origin: `DIRECTED`, `ASTRA`, or `DERIVED`;
- time started / completed or runtime;
- plain-English mechanism;
- exact rule/parameters;
- parent/control used;
- IS total PnL and `$ / session`;
- red IS month count;
- sum red-month losses;
- worst IS month;
- IS max MTM drawdown;
- worst day;
- average / peak gross exposure;
- result: `REJECT`, `PROMISING`, `FRONTIER`, or `BLOCKED`;
- reason for disposition;
- any child hypothesis opened from it.

Negative results belong in the ledger. Do not delete failed experiments from the record.

Every tested hypothesis must have a terminal disposition by the end of the arrow.

---

# Freeze and one-shot OOS

By approximately minute 130, stop new hypothesis generation.

Create `reports/cg_arrow002_freeze.txt` **before OOS scoring**. Include:

- timestamp;
- current Git working-tree diff hash or equivalent code identity;
- each finalist ID;
- full plain-English strategy rule;
- every numerical parameter;
- sizing/capital logic;
- exact IS metrics that justified finalist status;
- a statement that no OOS signal-cohort performance has yet been scored/inspected in this arrow.

Then score the frozen parent and all frozen finalists on the six OOS signal months once.

For OOS report the same metrics as IS.

### Confirmation language

A finalist may be called **OOS CONFIRMED WITHIN THIS INTERNAL SPLIT** only if:

- OOS total PnL exceeds the OOS parent;
- at least two OOS smoothness measures improve;
- it does not take more peak exposure than the allowed parent ceiling;
- the improvement is not solely a consequence of materially lower exposure without better exposure-normalized economics.

A deployment-ready label additionally requires peak marked exposure `<= $100k`.

If no finalist meets that bar, say so plainly. Do not tune again.

After the frozen OOS pass, also print a **combined all-signal 12-month continuous investor curve** for the parent and each finalist — monthly MTM PnL, total PnL, `$ / day`, max drawdown, worst day, peak exposure, and best-month profit concentration. This combined view is reporting only; do not use it to alter the strategy.

---

# Final report

Create `reports/cg_arrow002_recursive_lab.txt`.

Lead with a concise verdict answering:

1. Did any candidate improve **both** return and smoothness on IS?
2. Did that improvement repeat on protected OOS signal cohorts?
3. What is the strongest frozen candidate, if any?
4. Is it deployment-ready under the `$100k` peak-exposure criterion?
5. How much of the discovery came from directed corridors vs Astra-originated work?

Then include:

- exact 12-month split definition;
- parent clean-split baseline;
- directed corridor results;
- Astra autonomous results;
- Pareto frontier before OOS;
- freeze manifest pointer;
- one-shot OOS table;
- final continuous 12-month investor comparison;
- borrow-cost sensitivity for finalists;
- negative findings worth preserving;
- unexpected findings/new research corridors discovered but **not pursued after the OOS reveal**;
- wall-clock accounting and any overrun reason.

Do not hide the research multiplicity. Report how many hypotheses were completed, rejected, promoted to frontier, and frozen.

---

# Tests / auditability

Add focused tests for new reusable mechanics, especially:

- odd/even signal-cohort firewall;
- no OOS signal generation in IS research mode;
- causal checkpoint -> later fill behavior;
- sizing/capital rules;
- no variant can silently mutate the frozen parent constants;
- freeze manifest exists before the OOS scorer is allowed to run, if practical to enforce in code.

Run focused tests during research as needed.

Before final push, run the full inherited suite plus new tests unless doing so would exceed the permitted modest finish-only overrun. If full-suite runtime would breach that overrun, run all directly affected tests and document why the full suite was deferred; do not misstate PASS.

---

# Git / public safety / stop

Before commit:

- inspect `git status`;
- inspect staged filenames/diff;
- no parquet/data, `.env`, credentials, API keys, caches, or `.venv`;
- reports/code/tests only.

Suggested commit message:

`CG Arrow 002: recursive IS fade laboratory`

Push to `origin/main`.

Terminal summary should contain only:

- hypotheses completed / directed / Astra-originated;
- IS strict dual-improvement found: yes/no;
- number of frozen finalists;
- OOS-confirmed finalist(s), if any;
- strongest candidate IS vs OOS headline metrics;
- deployment-ready yes/no;
- tests status;
- wall-clock minutes;
- pushed commit SHA.

Then stop. No CG Arrow 003.
