# Build Arrow 43 — clock split (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

One family. Three books. The object is the clock, not a candle.

No FLY cell. No 08:00 hot gate. No conjunction. No flush wash.
Do not retune `B|conj|atr1559|lock` or `flush|max6|repaired`.
Do not reprint those two unless it is free; they are not this arrow.

No new ingest. No November/December 2025 pull (that is a later arrow).
Do not touch Lab A `data/bars/` except to read if a helper already lives there.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; EV = expected value; RTH = regular trading hours (09:30–16:00 ET);
IWM = iShares Russell 2000 ETF; SSR = Short Sale Restriction.

## Calendar

One study calendar, two tapes, no overlapping dates:

- 2026-01-02 … 2026-05-29 from `data/virgin/bars` (102 sessions).
- 2026-06-01 … 2026-08-31 from `data/full/` (same 04:00–16:00 grid as virgin).
- Warmup dates on disk stay on disk for prior close / PDV only. No fills on warmup.

Split by calendar month of the **entry** session:

- IS (odd): January, March, May, July.
- OOS (even): February, April, June, August.

A close→open book that enters 15:59 on 31 Jan and exits 09:30 on 1 Feb
is an IS trade (entry month). PnL of that trade is not an OOS print.

Put the split in a small reusable helper (session list + IS/OOS flag).
Later arrows must import it, not copy a date list.

Keep real holidays and 2026-07-03 early close. Flatten early-close sessions
at the last tradeable RTH minute.

## Eligibility (point-in-time, prior session EOD)

Common stock, same ETP denylist as Arrow 17.
Prior close in [$10, $80]. PDV ≥ $10,000,000.
`$10M` is the book wall this arrow. Store PDV; do not ingest.

`data/full/` only has prior close ≤ $50. Jun–Aug names above $50 will not
exist. That is expected. Do not pull them here.

IWM 04:00–16:00 is already on both tapes. Use it for the alpha line.

## The three books (frozen specs — do not search)

Shared:

- Rank eligible names each session by PDV. Cap **25** names.
- **$2,000** notional per name. No stop-based $200 risk size: overnight
  has no stop while the market is shut. State that in the report.
- Existing cost / spread / borrow-proxy model. Do not invent a new one.
- Skip a name-day if the required fill bar is missing.
- No 5-minute pattern. No EMA. No opening-range filter.

Ids:

1. `on_long` — buy last tradeable RTH minute (15:59 close, or last minute
   on an early close). Sell next session 09:30 open (09:30 bar open; if
   missing, first RTH print). No stop while shut.
2. `on_short` — opposite fills of `on_long`. Borrow proxy applies.
   SSR at the next open does not block a short already on from yesterday;
   do not invent an SSR block here.
3. `rth_long` — buy 09:30 open. Sell that session’s last tradeable RTH
   minute. Optional catastrophe only: flatten if the name is −8% from
   the 09:30 fill. That is a shop fuse, not a trade stop.

Do not glue 1 and 3 into an always-in long. Score them apart.
Do not add a fourth “always in” id.

## Order of work

1. Character table on **IS only** for the eligible universe (not the
   25-name cap): mean close→open return, mean 09:30→close return,
   hit rate, by month. This is description. It does not pick a book.
2. Then run the three ids on IS and OOS. One look on OOS. Do not drop
   an id after seeing OOS and keep another.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate $200 is not this arrow’s job. Combined of the three is a side
line only (they are not a diversified slate; they are the same names
on different clocks). Print correlation of daily PnL across the three.

## Report

`reports/arrow43_results.txt`.

For each id × IS × OOS: $/day, n, n/sess, hit, avgR if a stop exists
else skip avgR, PF, se, t, CI, daily-close DD, intraday trough
(RTH book only; overnight trough = close-to-open gap), peak/mean
concurrent, IWM alpha skip=0, worst day, months.

Honesty paragraph: overnight has no stop; $2,000 × 25 is $50k deployed;
costs on a 25-name overnight book can dominate the gap.

Append RESEARCH_LOG.md.

Tests:
- warmup dates produce no fills;
- an even-month entry is not in the IS scoreboard;
- `on_long` entry timestamp is 15:59 (or early close), not 09:30;
- `rth_long` PnL does not include the overnight gap;
- July 2026 sessions load from `data/full/`, January from `data/virgin/`.

Commit code + reports. No parquet. No Arrow 44.
