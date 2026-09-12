# Build Arrow 69 — August 2025 warmup into `data/virgin/` (ingest)

Read `docs/DATA_CONTRACT.md`, `docs/SUCCESS.md`, `AGENTS.md`,
`docs/BUILD_ARROW_67.md`, `reports/tape67_ingest.txt`,
`docs/BUILD_ARROW_41.md`, `docs/BUILD_ARROW_61.md`.

This arrow is **ingest only**. Do not score engines. Do not tune.
Do not touch `data/full/` or Lab A `data/bars/`.
Do not rebuild September–December 2025 or 2026 already on virgin.

Purpose: 15+ prior sessions so the first Wednesday in September 2025
can rank the frozen leftover book. Full August is cheap and cleaner
than clipping 15 days.

## Window

NYSE sessions **2025-08-01 through 2025-08-29** inclusive.
Do not pull 2025-09-02 or later. Do not pull 2025-07-31 or earlier.
If a date is not a session, skip it and list it.
If a date is already in the virgin manifest, do not re-fetch.

## Universe (same wall as Arrow 41 / 61 / 67)

- Stocks only, common stock, same ETP denylist.
- Prior close **[$1, $80]**.
- Prior-day dollar volume **≥ $1,000,000**. Store PDV. $10M is a column,
  not an ingest wall.
- Session **04:00–16:00** ET, one-minute UTP/CTA, 720-bar grid with zeros.
- Pull **IWM** 04:00–16:00 for these dates into `data/virgin/bench/`.
- Theta ≤ 8 concurrent, 429 backoff. Resumable manifest.
- Heartbeat + ETA every 15 minutes.

## Store

Append into existing `data/virgin/`. Gitignore parquet.

## Report

`reports/tape69_ingest.txt`.

Dates pulled, dates skipped, sessions, name-days, symbols, 1m rows,
mean bars/name-day (expect 720), failures, wall time, IWM sessions,
name-days PDV ≥ $10M, name-days with a 04:00 print.
State that August 2025 warmup is on virgin so September 2025 leftover
lookback is complete, or list holes.

Append RESEARCH_LOG.md.

Tests:
- do not write Lab A `data/bars/` or `data/full/`;
- 2025-09-02 is not pulled;
- a September 2025 session already in the manifest is not re-fetched.

Commit code + report. No parquet. No Arrow 70.
