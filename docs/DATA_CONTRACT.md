# Project Money — v1 data contract

Source of truth for the first research corpus. Implement this; do not invent a larger pull.

## Purpose

Local, point-in-time 1-minute US equity bars for names that were cheap and liquid *that morning*, plus a short warmup so regime/trend features can be computed before the study window.

## Scope

| Item | Value |
|---|---|
| Asset class | US common stocks only |
| Not in v1 | options, indices, ETFs, OTC, preferreds, warrants, units, when-issued, streaming, flat files, tick/sub-minute |
| Repo | `jamesksnyder99/money` only |
| Storage | local parquet under `data/` (gitignored). Git holds code, manifests, tiny fixtures |
| Clock | `America/New_York` |
| Session window | `07:30:00.000` inclusive through `12:00:00.000` exclusive of a new bar; last 1m bar starts `11:59:00` |
| Study window | `2026-06-01` … `2026-08-31` (inclusive trading days) |
| Warmup | 10 trading days before study: `2026-05-15` … `2026-05-29` excluding `2026-05-25` (Memorial Day) |
| Early close | Keep `2026-07-03`; clip bars to the actual early close |
| Venue | `utp_cta` (merged UTP + CTA) for all historical research pulls |
| Grain | 1-minute SIP OHLC (`interval=1m`) |

Labels / P&amp;L evaluation use study dates only. Warmup rows exist so features may look back; they are flagged `is_warmup=true`.

## Eligibility (point-in-time, evaluated each session)

A symbol is eligible for session `D` if **all** of the following hold using **session `D-1` official EOD** (known before 07:30 on `D`):

1. Primary-listed common stock (exclude ETF/ETN, OTC, preferred, warrant, unit, when-issued, non-standard share classes when detectable).
2. Prior official close `C_{D-1}` satisfies `1.00 <= C_{D-1} <= 30.00`.
3. Prior-day dollar volume `C_{D-1} * volume_{D-1} >= 1_000_000`.

Membership is allowed to change every day. Do **not** take the June 30 roster and backfill May.

No hard cap on name count. The filters *are* the universe.

## Endpoints (Theta v3 / official `thetadata` SDK)

Prefer the official Python SDK over launching Theta Terminal.

| Job | Endpoint / method | Notes |
|---|---|
| Symbol directory | `stock_list_symbols` | filter listing type client-side |
| Daily eligibility | `stock_history_eod` | also used for ADV and close |
| Splits | stock splits (Standard/Pro) | daily file only; do not adjust 1m prints |
| Intraday bars | `stock_history_ohlc` | `interval=1m`, `start_time=07:30:00`, `end_time=12:00:00`, `venue=utp_cta` |
| Calendar | list dates / holidays if available; else NYSE calendar | must include early closes |

Theta limits that the ingest must respect:

- Multi-day history requests max **one month**. Split May / June / July / August (May is warmup-only).
- Default API window is 09:30–16:00; **always** pass our start/end times.
- Do not request `interval=tick` or sub-minute in v1.
- Stocks Professional documents **8 concurrent requests**. Use them. See Parallelism.

## Tables

Paths are relative to repo root. Partition on `session_date` and optionally first letter of symbol if files get large.

### `data/calendar/sessions.parquet`

One row per session in warmup + study.

- `session_date` date
- `is_warmup` bool
- `is_early_close` bool
- `session_open_et` time (07:30:00 except if we later model holiday hours)
- `window_end_et` time (12:00:00, or earlier on early-close if the close is before noon)
- `regular_close_et` time (16:00:00 or early-close time)

### `data/universe/eligibility.parquet`

One row per symbol per session.

- `session_date` date
- `symbol` string
- `prior_close` float
- `prior_volume` int
- `prior_dollar_volume` float
- `eligible` bool
- `exclude_reason` string (empty if eligible)
- `is_warmup` bool

### `data/ref/splits.parquet`

- `symbol`, `ex_date`, `factor` (and native Theta fields kept raw)

### `data/bars/ohlc_1m/` (partitioned parquet)

Unadjusted traded prints.

- `symbol` string
- `bar_start` datetime64[ns, America/New_York]  (bar open; 1m bar at 11:59 covers 11:59–12:00)
- `session_date` date
- `session` string `pre` if `bar_start < 09:30:00`, else `rth`
- `open`,`high`,`low`,`close` float
- `volume` int
- `count` int
- `vwap` float
- `is_warmup` bool

Empty bars: do not fabricate OHLCV. Missing minutes are missing.

### `data/manifests/pulls.jsonl`

Append-only. One JSON object per request attempt.

- timestamp, endpoint, symbol or universe-job, start_date, end_date, interval, venue, row_count, elapsed_s, ok, error_class, error_message (no secrets)

### `reports/ingest_latest.txt`

Human summary of the last run (eligible name counts by day, rows written, failures, duration).

## Pipeline order

1. Build session calendar (warmup + study + early close).
2. Pull EOD for candidate commons across warmup+study (month chunks).
3. Write eligibility for every session.
4. **Pilot (required before full ingest):** 5 eligible names, 5 consecutive study days, 1m OHLC. Write under `data/pilot/`.
5. Full 1m pull for every eligible (symbol, session) pair.
6. Validate (below) and write `reports/ingest_latest.txt`.

Resume-safe: skip partitions whose parquet already exists and whose manifest line is `ok`, unless `--force`.

## Validation (fail the report, not silently)

- Session dates match NYSE calendar; `2026-05-25` absent; `2026-07-03` present and flagged early close.
- No bar with `bar_start` &lt; 07:30 or &ge; 12:00 (except clipped early-close).
- Eligibility never uses same-day close.
- Row counts: eligible names × ~270 minutes is an upper bound, not a requirement (premarket can be sparse).
- Duplicate `(symbol, bar_start)` = fail.
- Split on `D` must not rewrite unadjusted 1m prices.
- Manifest row_count matches written rows for that request.

## Parallelism (default everywhere)

**Rule:** if two pieces of work do not have to wait on each other, run them at the same time. Serial is the exception that must be justified.

Applies to ingest *and* later lab work: CLI entrypoints, fixture tests, validation, feature builds, tape replay from repo/parquet files, report generation, subprocesses.

| Work | How |
|---|---|
| Independent symbols, dates, partitions, files | worker pool |
| Parquet read/write, eligibility joins, validation scans | process pool (release the GIL) |
| Tape replay / bar walk over many names | partition by symbol (or by date) across cores |
| Separate program/script calls with no shared mutable state | concurrent subprocesses |
| Theta history HTTP/gRPC | concurrent up to vendor cap |

**Theta cap (the only hard limiter we did not invent):** Stocks Professional documents 8 concurrent requests. Default `--theta-concurrency=8`. On 429 / “too many concurrent” / timeout: exponential backoff, drop concurrency by half for that run, keep going. Never exceed 8 unless the user raises the flag after we measure headroom.

**Pipeline overlap:** while worker *n* writes partition *k*, worker *n+1* may already be pulling *k+1*. Pull and write are a pool, not a single file queue.

**Do not parallelize:** in-place append to the same parquet file, or two writers on one manifest without a lock. One append-only manifest with a mutex is fine.

Defaults: `workers=min(8, cpu_count)`, `theta_concurrency=8`. Print both in the start banner.

## Progress UX

Any run expected to exceed 15 minutes:

- Print a heartbeat **at least every 15 minutes** and also at each completed month/symbol-batch.
- Line format: `iso_time elapsed job_done/job_total last_item rows_written eta`.
- ETA = moving average of recent jobs; label it estimate, not promise.
- Start-of-run banner: calendar span, endpoint, workers, theta_concurrency, output path.
- End-of-run banner: ok/fail counts, output paths, duration.

Short runs (&lt;15 min) still print start, each major step, and finish — no heartbeat required.

## Soft time budgets (not hard stops)

These are planning hints for humans and for Grok Build sessions. **Do not kill a healthy pull** because a budget elapsed. Checkpoint (flush parquet + manifest) and print status instead.

| Job | Soft budget | If over budget |
|---|---|---|
| Implement ingest CLI + tests against fixtures | 45–90 min Build session | leave a working pilot path |
| Pilot 5×5 1m pull | 15–30 min wall | finish pilot; do not start full universe |
| Eligibility EOD for full calendar | 30–60 min wall | month-at-a-time resume |
| Full 1m universe Jun–Aug + warmup | several hours wall | resume from manifest; heartbeat every 15 min |
| Validation report | 15–30 min | write partial report with gaps listed |

Build should prefer **shipping a resumable tool** over finishing the full historical download in one agent turn.

## Out of scope until asked

Tick or sub-minute bars, quote-by-quote data, options, streaming, Theta flat files, adjusting intraday prices for splits/dividends, names outside the eligibility rules, writing parquet into git.
