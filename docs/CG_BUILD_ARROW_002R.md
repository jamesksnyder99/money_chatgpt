# CG Build Arrow 002R — resume recursive hold-short-for-fade laboratory after split-gate false start

Read, in this order:

1. `AGENTS.md`
2. `docs/CHATGPT_LAB_PROTOCOL.md`
3. `docs/CG_BUILD_ARROW_002.md`
4. `reports/cg_arrow001_baseline.txt`
5. `reports/cg_arrow002_recursive_lab.txt`
6. `reports/cg_arrow002_ledger.txt`
7. `reports/cg_arrow002_freeze.txt`
8. the Arrow 002 preflight code/tests added in commit `7ea04beb804da63813c4ba62680c1e14af75324b`

This is a **continuation/resume** of CG Arrow 002, not a new research mission. The first attempt stopped after roughly six minutes because the corporate-action reference was empty. The out-of-sample (OOS) firewall was not spent: no new in-sample (IS) candidate scoring occurred, no finalist was frozen, and no OOS signal cohort was scored.

Work only in `C:\Users\james\money_chatgpt`. Do not access `C:\Users\james\Money`. Do not invent CG Arrow 003.

---

## Director ruling on the corporate-action gate

The empty `data/ref/splits.parquet` remains a real **deployment-quality data caveat**, but it must **not block this discovery session**.

Reason: CG Arrow 001 proved exact reproduction of the inherited parent. This laboratory is now comparing variants under one common inherited raw-price convention. The absence of a documented split history may contaminate absolute economics or some rankings, but it does not justify spending the research budget without testing the requested hypotheses.

Therefore:

- preserve the inherited raw-price convention for the frozen parent and every candidate in this arrow;
- do not fabricate split events or factors;
- do not fetch or infer a new corporate-action table in this arrow;
- do not alter the parent merely to make it split-safe;
- keep the existing preflight report/code as an audit artifact;
- label all Arrow 002R economic conclusions **research results under the inherited raw-price convention; corporate-action integrity remains unresolved for deployment**.

You may spend at most ~5 minutes on a bounded **IS-only contamination diagnostic** if it is cheap: e.g. count candidate/ranked name-days with extreme single-session raw price moves and identify whether any dominate IS PnL. This is descriptive only. Do not use such a diagnostic to create or tune a filter in this arrow unless the underlying corporate action is independently known from an already-local documented source.

The corporate-action issue is not a valid reason to stop Arrow 002R.

---

## Time budget — 144 minutes remaining active research time

The blocked first attempt consumed about six minutes of the original 150-minute allocation. Treat this continuation as having **144 minutes of active wall-clock budget** beginning after `git pull --ff-only` and the start banner.

Suggested allocation:

- 0–8 min: resume/preflight, build or reuse the IS-only scoring harness/cache;
- 8–78 min: ChatGPT-directed corridors from Arrow 002;
- 78–124 min: protected Codex/Astra autonomous shop time;
- 124–134 min: freeze finalists + one-shot OOS confirmation;
- 134–144 min: final continuous-year reporting, tests, public-safety check, commit, push.

A modest overrun up to ~15 minutes is allowed only to finish an already-running hypothesis, the frozen OOS pass, required tests/reporting, or commit/push. Do not open a new branch after minute 144.

The intended research balance remains approximately **60% directed / 40% Astra-originated**. The 40% autonomous allocation is real protected discovery time, not merely parameter variants of directed corridors.

---

# Scientific constitution — unchanged from Arrow 002

All Arrow 002 governance remains in force except the split gate is demoted from blocking to caveat as stated above.

## Protected 12-month signal split

**IS/training signal months:**

- 2025-09
- 2025-11
- 2026-01
- 2026-03
- 2026-05
- 2026-07

**OOS/confirmation signal months:**

- 2025-10
- 2025-12
- 2026-02
- 2026-04
- 2026-06
- 2026-08

Membership is by **signal month**. Lifecycle bars required to mark/exit an IS trade may cross into an even calendar month. Before freeze, do not generate, score, tabulate, diagnose, rank, filter, or tune on even-month **signal cohorts**.

The inherited Money reports are historical provenance, not authorization to inspect new OOS candidate results during training.

## OOS firewall

Recursive search uses IS signal cohorts only.

Before any candidate sees new OOS scoring:

1. create/replace `reports/cg_arrow002_freeze.txt` with a valid freeze manifest;
2. include 3–5 finalists when justified (fewer if the frontier is genuinely sparse);
3. specify complete rules, parameters, sizing, entry, exit, capital behavior, code identifier/hash, and IS metrics;
4. record why each finalist earned the OOS look.

Then perform **one OOS scoring pass** for all frozen finalists and the frozen parent.

After OOS is revealed:

- no rule or threshold changes;
- no swapping to a nearby variant;
- no deleting losing months;
- no new hypothesis prompted by OOS;
- no second OOS pass after tuning.

If OOS disappoints, report it honestly and stop.

## Causality, costs, capital, anti-overfit rules

Retain every rule from `docs/CG_BUILD_ARROW_002.md`:

- causal signals/exits/fills only;
- inherited transaction cost model for comparable discovery economics;
- borrow-cost sensitivity at 0%, 10%, and 30% annualized for frozen finalists after OOS, reporting only;
- report average/peak marked gross exposure and live tickets/symbols;
- no candidate with peak marked exposure above the frozen parent's `$102,922` may be called an improvement;
- deployment-ready requires `<= $100,000` peak marked exposure;
- exposure-matched/size-matched controls where smoothing could simply be less risk;
- no opaque optimization or broad brute-force grid;
- every hypothesis actually opened must finish with a scored result or a genuine specific infrastructure block before the arrow ends.

No unfinished queue.

---

# Frozen parent and objective

Frozen control remains:

- Wednesday signal;
- field `$10–$80`, prior-day dollar volume `>= $10M`, inherited ETP denylist;
- eight largest 15-session close-to-close returns;
- next-session last regular-hours fill (`nextrth`);
- `$4,000` intended ticket per selected name;
- ten trading-session hold from fill;
- inherited costs;
- marked-to-market daily equity.

Arrow 001 continuous-year provenance:

- 251 sessions;
- total MTM `$51,855.71`;
- `$206.60/day`;
- max MTM drawdown `-$20,033.68`;
- worst marked day `-$6,607.31`;
- 376 trades;
- peak marked exposure `$102,922`.

Those full-year numbers are provenance, not training metrics. Build a fresh **IS-only cohort baseline** using only the six IS signal months before research.

## Pareto objective

Do not collapse the mission into one magic score.

For parent and candidates report at minimum on IS:

**Return**
- total cohort PnL;
- PnL / sessions in six IS signal months;
- profit / average gross exposure.

**Smoothness**
- number of red IS signal months;
- sum of losses across red IS signal months;
- worst IS signal month;
- continuous IS-cohort max MTM drawdown;
- worst marked day;
- best-month concentration.

A **strict dual improvement** must exceed parent IS total PnL and improve at least two smoothness measures without materially worsening the others, while not exceeding parent peak marked exposure.

Do not force a winner if none exists.

---

# Directed research — complete D1–D5 from Arrow 002

The detailed hypotheses and mechanics in `docs/CG_BUILD_ARROW_002.md` remain authoritative. Complete the core test in each of D1–D5 unless a branch has a genuine *branch-specific* infrastructure blocker unrelated to the now-demoted split gate.

For clarity, the mandatory corridors are:

- **D1 risk-balanced sizing:** same selections/entry/hold; `$32k` batch budget allocated inversely to pre-signal 20-session daily volatility, initial `$2k–$6k` clip, renormalize where possible; exposure-matched control.
- **D2 repeated-name concentration:** 8% of `$100k` per-symbol aggregate entry-value cap, both cash/no-substitute and next-ranked-substitute versions; ranking fixed at signal close; size/exposure-matched control.
- **D3 width-based soft exposure:** rank-1 minus rank-8 raw 15-session return width; single IS-median division; `$4k/name` above/equal, `$2k/name` below; compare always `$4k` and straightforward `$3k` exposure interpolation.
- **D4 spread weekly timing:** same total intended `$32k` weekly new capital distributed across actual signal sessions (or a predeclared two-pulse approximation if compute requires it); next-session last-RTH fills; ten-session holds; no increase in intended weekly allocation.
- **D5 mature-fade protection:** 20-session ATR frozen at signal; no protection before hold day 3; arm only after `2 ATR` favorable move; after arming test `1 ATR` rebound full exit and one-time half exit; decisions/executions causal and subsequent-print based; no replacement in D5.

**D6 capital recycling** remains conditional. Open it only if a completed early-exit candidate releases material capital and has credible IS economics. If opened, finish it inside this arrow using Arrow 002 mechanics.

Small neighboring checks are allowed only when motivated by a completed IS result. Do not turn any corridor into a broad parameter grid.

---

# Astra autonomous shop — approximately 40% of discovery effort

After enough directed work exists to understand the substrate, Astra must spend meaningful protected time generating its own hypotheses.

Rules:

- IS-only until freeze;
- causal and interpretable;
- same common raw-price convention/cost accounting;
- no risk inflation masquerading as alpha;
- log the economic/behavioral mechanism before or with implementation;
- genuinely new ideas preferred over tiny threshold variants;
- every opened hypothesis gets a result before arrow end;
- Astra may abandon weak branches after a completed core result and recursively pursue strong/unexpected findings.

If an autonomous idea dominates, Astra may exceed a literal 40% share; 60/40 is a planning allocation, not a quota.

Do not stop merely because one improvement is found. Use remaining IS research time to challenge/falsify it and seek alternatives.

---

# Research ledger

Replace/extend `reports/cg_arrow002_ledger.txt` so the blocked first attempt remains visible as history and every 002R branch is recorded.

For every hypothesis include:

- ID;
- DIRECTED / ASTRA / DERIVED;
- mechanism in plain English;
- exact rule/parameters;
- parent/control used;
- IS result: PnL/session, total PnL, red months, red-month loss sum, worst month, max DD, worst day, average/peak exposure, trade count;
- disposition: `REJECT`, `PROMISING`, `FRONTIER`, or `BLOCKED`;
- why;
- runtime;
- children/derived branches.

Also maintain a compact Pareto board.

The blocked corporate-action preflight must remain labeled `INFRASTRUCTURE CAVEAT`; do not relabel it as performance evidence.

---

# Freeze, OOS, and final investor table

Before OOS, write a valid freeze manifest. Favor distinct finalists, ideally representing:

1. best strict dual-improvement candidate if one exists;
2. highest-return candidate with acceptable smoothness;
3. smoothest candidate retaining substantial parent IS profit;
4. best deployment-ready `<= $100k` candidate;
5. best distinct Astra-originated candidate.

Avoid redundant parameter neighbors.

Then one-shot score parent + finalists on the six even signal months.

Report for each OOS book the same return/smoothness/exposure metrics used on IS, plus an explicit **repetition assessment**:

- `REPEATED`: direction of improvement materially carries to OOS;
- `MIXED`: some benefit survives but major part does not;
- `FAILED`: IS improvement does not repeat or economics reverse.

Do not tune these labels mechanically from one threshold; explain them.

After the one-shot OOS pass, generate the 12-month continuous investor table for the frozen parent and frozen finalists (without changing rules):

- total MTM profit;
- $/day over all 251 sessions;
- each of 12 monthly MTM contributions;
- red-month count and loss sum;
- max continuous MTM drawdown;
- worst day;
- average/peak gross exposure;
- peak live tickets/symbols;
- borrow-cost sensitivities at 0%, 10%, 30% annualized.

Label these continuous curves **post-freeze descriptive investor views**, not a second optimization surface.

---

# Tests / outputs / commit

Create or update, at minimum:

- `reports/cg_arrow002_recursive_lab.txt` — final executive research report;
- `reports/cg_arrow002_ledger.txt` — complete branch ledger;
- `reports/cg_arrow002_freeze.txt` — valid finalist freeze manifest before OOS;
- `reports/cg_arrow002_commands.txt` — exact important commands;
- focused code/tests for the IS/OOS firewall, candidate mechanics, exposure accounting, and freeze-before-OOS invariant.

The final report must begin with:

- whether strict dual improvement was found on IS;
- whether it repeated OOS;
- strongest frozen candidate and plain-English rule;
- frozen parent vs candidate IS/OOS and full-year investor metrics;
- whether candidate fits `$100k`;
- number of completed hypotheses, split directed/Astra/derived;
- corporate-action caveat still unresolved for deployment.

Run focused tests and full `tests/` suite. Preserve public-repository safety. Commit and push all intended tracked code/tests/reports to `origin/main`.

Suggested commit message:

`CG Arrow 002R: recursive fade laboratory results`

Do not start CG Arrow 003.
