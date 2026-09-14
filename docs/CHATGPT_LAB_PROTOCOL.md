# money_chatgpt — research and verification protocol

This is an independent laboratory seeded from `jamesksnyder99/money`. Source provenance is in `SOURCE_MONEY_COMMIT.txt`; it is not permission to access the original local repository.

## Roles and workflow

ChatGPT is research director and auditor. It publishes detailed GitHub arrows and reviews resulting code, evidence and economics. The execution agent is named by the active arrow. **For CG Arrow 011 the executor is Fable in Claude Code.**

1. Pull current main with `git pull --ff-only origin main` without overwriting legitimate local work; confirm root/remote.
2. Read `AGENTS.md`, `docs/SUCCESS.md`, `CLAUDE.md`, and the active arrow.
3. Execute only the active scope, preserve historical evidence, test, inspect public safety, commit/push safe code and reports.
4. Verify remote equality, identify local private deliverables and unresolved evidence, then stop for audit. Do not invent the next arrow or run concurrent writers in one worktree.

## Active authority — CG Arrow 011

The user has parked capital constraints and redeployment to study **Winner-Fade Anatomy: Pre-Entry Characteristics and Within-Cohort Outcomes**. Combine pre-entry feature/mechanism discovery, attribution of differences between the existing models/months, and every-cohort winner/loser comparison. Principal subject is Momentum+Volume-Sized Short; other existing books are explanatory references.

Allowance: four hours total, **70% directed/shared work / at most 30% Fable-led exploration**, including evidence, tests, reports and push. The exact assignment is `docs/CG_BUILD_ARROW_011.md`. No next arrow or production promotion is authorized.

Arrow 008 is the frozen historical baseline reference; Arrow 009 supplies the standing monthly-reporting requirement; Arrow 010 is the fixed-dollar/equity-scaled sizing reference. Preserve all recorded results. Old next-step instructions and active headers in archived arrows do not compete with the current assignment.

### Permanent calendar repair for new tests

Nominal weekly signal anchor is Wednesday. If Wednesday is closed, roll backward one calendar day at a time to the most recent exchange session. Entry is the first valid exchange session after the signal. Never skip a week solely because Wednesday is closed. Hn remains n exchange sessions after actual fill. Preserve early-close conventions. The helper was proved neutral for the September 2025–August 2026 study.

## Isolation and public safety

Never access `C:\Users\james\Money`. Use independent lab inputs and acquisitions expressly authorized by the active arrow. No junctions/symlinks/hard links back to Money.

The GitHub repository is public. Never publish `.env`, credentials, raw vendor bars/quotes, proprietary detailed trade observations, private account identifiers or local caches. Authorized local ThetaData credentials may be used within active scope; confirm `.env` is ignored before work/push. Store detailed CSVs under ignored `handoff/outgoing/`; public reports carry safe aggregates/hashes/schemas only.

## Scientific practice

- Preserve prior arrows and raw source trees as historical evidence; repairs are versioned and reconciled.
- Entry eligibility is separate from lifecycle and feature-history coverage. A documented open position is not a completed zero-return trade.
- No inferred splits, invented executions, hindsight deletion, stale marks labeled verified, or empty-file success without documented coverage.
- Never hand-replace a suspicious selected name with the next rank. Resolve/document events, normalize units, recompute eligibility/ranks/features across the complete field and let the corrected top eight emerge mechanically.
- Corporate actions before selection and while held require documented dated factors, correct share/price/volume handling, security identity and explicit event cashflows/unknowns. A jump screen is triage, not a complete event census.
- Distinguish raw historical cache, recorded historical selections and unchanged rules on repaired complete inputs. Do not confuse rank-order changes with membership changes.
- A positive return does not satisfy verification. A negative repaired result is not an engineering failure. Source-data uncertainty is neither proof of success nor proof of failure.
- Certification is scoped to the declared dataset, implementation and accounting convention. It is not proof of future performance or broker execution availability.
- Use original signal-month ownership. IS and OOS risk/account books must be separated; ALL is a distinct chronological account. Causal holdings may cross month boundaries.
- These repeatedly inspected even signal months are internal confirmation, not pristine validation. New hypothesis development stays in IS, definitions freeze before new OOS analysis, and failed confirmations cannot trigger same-batch retuning.
- Separate calendar account through the cutoff, incremental later runoff, eventual completed-trade totals and still-open obligations. Every $/session field names numerator and denominator.
- Retain all attempted hypotheses and counterexamples. Prefer interpretable mechanisms over black-box sweeps or coefficient-significance screening. Associations are not proven causal explanations.
- For pre-entry discovery, preserve separate SIGNAL_CLOSE and PRE_ORDER availability cutoffs. Outcomes/post-entry path labels must not enter predictors. Within-cohort and pooled effects are different, and repeated securities/overlapping trades are not independent observations.
- Outcomes and resource limits never justify false completion. Exact irreducible blockers remain explicit.

## Historically aware data and feature certification

Newly downloaded data are not automatically verified. Raw retrievals remain immutable; normalized/validated derivatives carry versions, coverage, sources and checks. Every new observation capable of affecting a claim's eligibility, ranking, sizing, execution, valuation or feature must meet the applicable test-specific integrity gate.

At minimum check price/timestamp completeness, missing or stale required observations, full intended candidate coverage, corporate actions within ranking/feature/holding windows, consistent prices/share volumes/held shares, historical identity/test-security exclusions, actual halts versus vendor failures, and full lifecycle coverage. Public-availability timestamps govern pre-entry news/fundamentals; current snapshots cannot be backfilled into historical decisions.

Unresolved material defects block affected claims. Do not fill missing data with favorable values, silently discard affected trades or treat retrieval failure as a market event. Missing optional enrichment can limit that feature's analysis while other verified work proceeds; its row masks and limitations must be published. If an inherited material defect is discovered, preserve originals, identify dependent claims and version any authorized correction.

## Monthly account reporting standard

Frozen in Arrow 009 as `cg_lab_monthly_account_reporting_v1`, implemented in `src/verification/r4r5_monthly.py`.

Every future arrow that publishes strategy economics and has a daily marked-account path must publish every calendar month individually, principal variants side by side, monthly marked P&L dollars, return percent on prior month-end equity, month-end equity, positive/red/flat counts, worst/best/median month, exact period reconciliation, and explicit open-position treatment. None of the months may be collapsed, skipped or replaced with placeholders.

Monthly P&L comes from the daily marked-account path, never from grouping completed trades by exit month. The months reconcile to marked account P&L at the period end, not eventual completed-trade P&L including later exits. Runoff stays separate.

Published monthly rows are stated in whole cents and chain exactly. Use those same numbers in CSV and prose; preserve full precision in the manifest. This is a reporting requirement, not an optimization dimension. Previously revealed months may be described, but may not drive new confirmed trading rules.

## Headline cost convention

Follow the Arrow 008/010 declared commission/spread model. Do not include hypothetical 10%/30% stock-loan deductions in normal tables or recurring discussion; archival stresses remain provenance only. Use a concise footnote that broker-specific locate/HTB charges, dividends, financing, forced-close effects, taxes and other execution items are excluded. Exclusion is not independent verification that a cost or availability constraint was zero. Broker reconstruction requires a separately authorized arrow.

## Naming and reporting convention

Use human-readable names first in new arrows, reports, tables and conversation. Legacy IDs remain in parentheses or filenames for provenance/code continuity:

- Winner-Fade Short — umbrella family.
- Equal-Dollar Short — PARENT.
- Volume-Sized Short — R4.
- Momentum+Volume-Sized Short — R5.
- Historical-Selection Replay — R1.
- Corrected-Universe Replay — R2.
- 10-Session Hold — H10; Hn means an n-session hold.
- Hold-Length Ladder — H1–H10.

Example: **Corrected-Universe Winner-Fade Short — Momentum+Volume sizing — 6-session hold (R2/R5/H6)**. Do not rename archival artifacts merely for readability.

Lab assignments live in `docs/CG_BUILD_ARROW_XXX.md`; historical arrows remain evidence, not competing current instructions.
