# Build Arrow 61 — rest of December 2025 into `data/virgin/` (ingest)

Read `docs/DATA_CONTRACT.md`, `docs/SUCCESS.md`, `AGENTS.md`,
`docs/BUILD_ARROW_41.md`, `reports/tape41_ingest.txt`,
`reports/tape17_ingest.txt`.

This arrow is **ingest only**. Do not score engines. Do not tune.
Do not touch `data/full/` or Lab A `data/bars/`.
Do not rebuild sessions already on disk from Arrow 41.

Hotel 7 (last-month MAX) needs a full calendar December so January 2026
can rank December leftover. Arrow 41 only stored the last 10 NYSE days of
2025 (`2025-12-17` through `2025-12-31`). This arrow fills the missing
December sessions in front of that warmup.

## Window

NYSE sessions **2025-12-01 through 2025-12-16** inclusive.
Expected list (verify against NYSE calendar; keep real holidays; do not
invent bars): 2025-12-01, 02, 03, 04, 05, 08, 09, 10, 11, 12, 15, 16.
If a date is not a session, skip it and say so.
Do not re-pull 2025-12-17..2025-12-31 unless a session is missing from
the virgin manifest.

## Universe (same wall as Arrow 41)

- Stocks only, common stock, same ETP denylist as Arrow 17 / 41.
- Prior close **[$1, $80]**.
- Prior-day dollar volume **≥ $1,000,000**. Store PDV. $10M is a column,
  not an ingest wall.
- Session **04:00–16:00** ET, one-minute UTP/CTA, 720-bar grid with zeros,
  same as `data/virgin/` and `data/full/`.
- Pull **IWM** 04:00–16:00 for these dates into `data/virgin/bench/`.
- Theta ≤ 8 concurrent, 429 backoff. Workers for write/validate.
- Resumable manifest. Heartbeat + ETA every 15 minutes.

## Store

Append into existing `data/virgin/` (bars, eligibility, manifest, IWM).
Same layout as Arrow 41. Gitignore parquet.

## Report

`reports/tape61_ingest.txt`.

Dates pulled, dates skipped (already on disk vs not a session), sessions,
name-days, symbols, 1m rows, mean bars/name-day (expect 720), failures,
wall time, IWM sessions, name-days PDV ≥ $10M, name-days with a 04:00 print.
State that December 2025 on virgin is now complete (first December session
through 2025-12-31) or list any hole.

Append RESEARCH_LOG.md.

Tests:
- do not write Lab A `data/bars/`;
- do not write `data/full/`;
- dates before 2025-12-01 are not pulled;
- 2025-12-17 is not re-fetched if already in the manifest (fixture or log).

Commit code + report + manifest if no secrets. No parquet. No Arrow 62
(62 is the MAX book, next).
