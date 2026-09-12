# Build Arrow 70 — compounded twelve-month Wednesday H10

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_68.md`, `reports/arrow68_results.txt`,
`docs/BUILD_ARROW_66.md`, `reports/arrow66_results.txt`,
`docs/BUILD_ARROW_65.md`, `reports/arrow65_results.txt`,
`reports/tape67_ingest.txt`, `reports/tape69_ingest.txt`,
`reports/tape41_ingest.txt`, `reports/tape17_ingest.txt`.

One look of the **frozen** paper book across Sep 2025–Aug 2026.
Do not retune rank, n, weekday, hold, fill, or base ticket.
Do not walk rings. This is size-on-equity, not a new engine.

Frozen rules: Wednesday signal, eight largest 15-session close-to-close
returns (IWM subtract is a scalar), fill next session last-RTH, hold 10,
drop missing exits. Field $10–$80 PDV ≥ $10M ETP denylist.
Start equity **$100,000** on 2025-09-02.
MTM every session as Arrow 65. Reuse `src/research/clock.py`.

Signals: first Wednesday in September 2025 that has 15 prior sessions
(expect 2025-09-03) through last Wednesday in August 2026 whose fill
exists. Lookback may read August 2025 virgin. Jun–Aug 2026 bars come from
`data/full/`. Sep 2025–May 2026 from `data/virgin/`.
A hold may cross the virgin/full seam. Mark it. Do not drop it.

No new ingest. Do not touch Lab A `data/bars/` except to read a helper.

Do not treat this year as a new IS/OOS split. Print 2025-09..12 vs
2026-01..08 as two blocks so the already-seen months are obvious.
Do not drop a month after seeing it.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Ids (frozen — do not add a 3rd)

| id | ticket |
|---|---|
| 0 `flat_4k` | $4,000 every signal | control, constant size |
| 1 `comp_4k` | `4000 × (equity at signal last-RTH / 100000)` | compound |

Equity for id 1 is the MTM equity **before** that Wednesday's new fills.
Do not resize names already on. Only new fills use the new ticket.
Clip ticket at $0 if equity ≤ 0. Do not add cash. Do not withdraw.

## Report both calendars

**12 months:** 2025-09 through 2026-08. For each month: n sessions, MTM $,
MTM $/day, end equity (id 1), peak live that month.

**52 weeks:** ISO weeks Monday–Sunday that overlap the year, or NYSE weeks
ending Friday — pick one, say which, and print all weeks that contain a
mark. For each week: MTM $, end equity (id 1).

Also print: start equity, end equity, max MTM DD $, worst day, peak live
across the year, total MTM $, MTM $/day (total / NYSE sessions in
2025-09-02..2026-08-31), hit, wins, losses, PF, t, CI on the daily MTM
series. IWM alpha at the **flat** $4k size only (do not pretend a growing
short of IWM).

Say when a CI excludes 0. Do not call a CI that includes 0 "EV."
Do not call the year a $200 slate pass. Jan–Aug 2026 already had that look.

## Order of work

1. Id 0 flat year. Sep–Dec MTM should sit in the same neighborhood as
   Arrow 68's month tape (Sep hole, Oct fat). If September is green and
   October is empty, stop and fix the seam.
2. Id 1 compound. One look.

## Report file

`reports/arrow70_results.txt`.

First paragraph: start/end equity on compound, flat-year $/day vs
compound-year $/day, max DD, whether fall 2025 still has the September hole.
Then the 12-month table for both ids. Then the 52-week table for id 1.
Then the usual trade stats.

Append RESEARCH_LOG.md.

Tests:
- id 1 ticket on a later Wednesday is not $4000 if equity ≠ $100k (fixture);
- id 0 ticket is always $4000 (fixture);
- fill is next last-RTH (fixture);
- first signal is not before 15 prior sessions;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 71.
