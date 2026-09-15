# CG Arrow 013 — acquisition and certification of the pristine September 2024 to August 2025 holdout

Executor: Opus in Claude Code. Run head `974285a`. This arrow acquires, authenticates, normalizes and certifies data. It runs no strategy.

## The frozen period, fixed before any data were touched

| Boundary | Value |
|---|---|
| Pristine out-of-sample signal months | 2024-09 through 2025-08, 12 consecutive months |
| August 2024 | warmup only: ranking and feature history, creates no positions, owns no signal |
| August 2025 | the twelfth and final signal month, not warmup |
| New bulk acquisition | 2024-08-01 through 2025-07-31 |
| Lifecycle tail | 2025-09-01 through 2025-09-30, ten-session completion for late-August 2025 cohorts only |
| Future reveal account | starts fresh at $100,000 before the first September 2024 cohort |

The definition was committed before acquisition began and has not been altered since.

## Authentication and provenance, before any bulk retrieval

| Check | Result |
|---|---|
| Repository and remote | C:\Users\james\Money_ChatGPT, https://github.com/jamesksnyder99/money_chatgpt.git |
| Credential file git-ignored | True |
| Credential handling | resolved by name only; no value is read, printed, logged, serialized, staged or committed |
| Vendor SDK | official ThetaData Python SDK 1.0.10, Python 3.14.5 |
| Entitlement | existing authorized Stocks Professional |
| Endpoints | stock_history_ohlc, stock_history_eod, interval 1m, venue utp_cta |
| Terminal launched / subscription changed / options / sub-minute | False / False / False / False |
| Concurrency cap | 8 requests across the process tree |
| Authenticated smoke query | 720 bars returned, 12 schema fields, timestamps unique True, monotonic True, inside the declared window True |
| Repeat-query reproducibility | identical: True |
| Empty success treated as data | no; an empty success is a failure |

Two vendor conventions were discovered and recorded rather than smoothed over. Timestamps arrive at millisecond precision in New York time while the lab's landed partitions hold microseconds, so the two are cast to one explicit unit before any comparison; after the cast the instants must be identical, which is a unit alignment and not a tolerance. A minute in which a security did not trade returns not-a-number prices with zero volume, which is a real vendor state distinct from a missing bar and from a halt; the comparison treats absence on both sides as a match and absence on one side as a discrepancy, and the three states are never merged.

## What was newly downloaded and what was reused

| Layer | Source | Scope |
|---|---|---|
| End of day, full roster | newly downloaded | 1,718,304 symbol-sessions across 7,851 securities and 250 dates, 2024-08-01 to 2025-07-31 |
| One-minute bars | newly downloaded | 107 of 250 new-acquisition sessions carry a landed minute layer |
| August 2025 | reused after authentication | 21 sessions, already held from the previous study's warmup, re-verified against a fresh stratified vendor sample |
| September 2025 lifecycle tail | reused after verification | 21 sessions, required only to complete ten-session holds opened in late August 2025 |

## Certification gate

### Trading-calendar integrity

The lab calendar previously covered 2025 and 2026 only. The 2024 closures and early closes were added for this holdout. The addition is purely additive: no 2024 date falls inside any window a prior arrow froze, and a test asserts every frozen session list is unchanged.

| Calendar check | Result |
|---|---|
| Sessions in the window 2024-08-01 to 2025-09-30 | 292 |
| Independent reference | pandas_market_calendars NYSE |
| Reference sessions | 292 |
| Session lists identical | True |
| Closures inside the window | 12, each absent from the session list |
| Early closes | 2024-11-29, 2024-12-24, 2025-07-03, each carrying 210 regular-hours minutes rather than 390 |

Both New York daylight-saving transitions inside the window are covered, and landed partitions on the sessions following them carry local-time bars inside the declared schedule.

### Timestamp and minute-bar integrity

| Programmatic check | Partitions failing |
|---|---:|
| Duplicate timestamps within a symbol-session | 0 |
| Timestamps not monotonically ordered | 0 |
| Bars outside the declared 04:00 to close window | 0 |
| Open or close outside the bar's high-low range | 0 |
| Negative share volume | 0 |
| Non-positive or non-finite traded price | 0 |
| More regular-hours bars than the session schedule allows | 0 |
| Landed partition that could not be read back | 0 |

Inventory covers 75,737 landed partitions holding 54,530,640 minute rows, of which 20,165,384 regular-hours minutes carried volume and 9,372,046 did not.

Four distinct minute states are kept apart and never merged. A no-trade minute returns NaN prices with zero volume. A missing bar is absent from the partition entirely. A halt is a documented market event. And 5,527,947 regular-hours minutes carried consolidated volume with a positive trade count but no last-sale-eligible price, so their open, high, low and close are NaN. Those are real prints that do not set high, low or last under the tape's trade-condition rules, not a data defect: the frozen loader already requires a finite positive open and close, so such a minute can never become a mark or an execution. The remaining 14,637,437 regular-hours minutes carry both volume and a usable price and are the ones the integrity checks above are run against.

### Full-universe and ranking-field completeness

| Universe contract | Value |
|---|---:|
| Common-stock roster | 15,322 |
| Exchange-traded-product list size | 5,672 |
| Of those present in the roster | 0 |
| Exchange test issues excluded | 8 |
| Eligibility rows, point in time | 1,718,304 across 250 sessions |
| Eligible field per session, minimum | 902 |
| Eligible field per session, median | 1,448 |
| Eligible field per session, maximum | 2,058 |
| Union of the eligible field across the window | 4,319 securities |

One claim is deliberately not overstated. The roster is already common-stock-only: none of the 5,672 listed exchange-traded products appear in it, so that rule excludes nothing at this stage and is confirmed as a no-op rather than an active filter. It is still applied, so the contract is enforced rather than assumed. The test-issue rule does bite, removing the eight exchange test tickers.

Eligibility is point in time by construction: a session is judged on the prior session's official end-of-day close and dollar volume, never on a later or present-day state. The per-session expected field size is published for every session in the coverage inventory, so a security cannot be dropped silently. No return is computed and nothing is ranked.

### Volume integrity and aggregation reconciliation

| Reconciliation | Value |
|---|---:|
| Deterministic symbol-session samples compared | 15 of 65 |
| Regular-hours minute volume over end-of-day volume, median | 0.868652 |
| Same ratio, minimum and maximum | 0.666862 to 0.986394 |
| Last traded minute close versus end-of-day close, median absolute difference | 0.01 |

Regular-hours minute volume is compared with the vendor's end-of-day share volume. The end-of-day figure is a consolidated national total and includes prints the regular-hours minute window does not carry, so a ratio below one is expected and is documented rather than tuned away.

### Corporate actions and point-in-time identity

**The lab's certified action table covers the September 2025 to August 2026 study. No documented, dated corporate-action table has yet been assembled for September 2024 to August 2025. A price-discontinuity screen is triage and is explicitly not proof that no action occurred, so no corridor in this window is certified for unit integrity.**

Ranking and feature units, held-share normalization and point-in-time identity cannot be certified for this window until documented evidence is assembled. This is a declared remaining gap, not a silent assumption.

Staged procedure: The frozen post-selection procedure retrieves primary-source evidence from SEC EDGAR for exactly the securities the frozen models mechanically select, using the Arrow 007 and 008 machinery in src/verification/r4r5_events.py, and fails closed on any unresolved material action rather than substituting a next name.

### Exceptions and the fail-closed policy

| Exception code | Meaning | Count | Blocks certification |
|---|---|---:|---|
| ACT | corporate action evidence | 1 | True |
| COV | coverage | 2 | True |
| ID | security identity | 1 | True |

Every exception carries a stable identifier, cause, source evidence, repair status and whether it blocks certification. 4 exceptions are recorded and 4 block certification. Nothing was repaired because it produced a more convenient answer, no security was dropped without a record, and no vendor failure was reinterpreted as a market event.

## Reproducibility and hashes

| Authentication check | Sampled | Matched | Result |
|---|---:|---:|---|
| repeat query reproducibility | 1 | 1 | IDENTICAL |
| august 2025 overlap vs local | 12 | 12 | MATCH |
| minute to end of day aggregation | 65 | 0 | DOCUMENTED_CONSOLIDATED_TAPE_DIFFERENCE |
| calendar vs independent reference | 292 | 292 | IDENTICAL |

The manifest carries a SHA-256 for each of 6 certification artifacts and a partition-listing digest for each of 77 raw partition groups. Raw vendor partitions are immutable after landing; a resume skips only a partition that already exists and reads back cleanly, and writes are atomic so an interrupted run cannot leave a half-written file.

## What remains

- minute layer not yet acquired for these sessions
- minute layer present but short of the session's point-in-time eligible field
- no documented dated corporate-action table exists yet for the holdout window
- point-in-time security identity and ticker-change mapping not yet assembled for this window

## Certification status

**HOLDOUT_DATA_PARTIALLY_CERTIFIED**

The gaps above are named exactly rather than estimated. The corporate-action and identity layer is the substantive one: a price-discontinuity screen is triage and is explicitly not proof that no action occurred, so no corridor in this window is certified for unit integrity until documented dated evidence is assembled. Declaring full certification without it would be the precise mistake this gate exists to prevent.

**NO STRATEGY PERFORMANCE WAS SCORED OR REVEALED IN ARROW 013.** No strategy was replayed, no ranking or selection was produced or inspected, no security that the frozen models would choose was named, and no trade outcome, hit rate, drawdown, monthly return or ending equity was calculated on the September 2024 to August 2025 period. The holdout remains pristine.

No model is recommended here, because none was permitted to be tested.
