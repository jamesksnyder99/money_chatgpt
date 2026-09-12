# Build Arrow 67 — September–November 2025 into `data/virgin/` (ingest)

Read `docs/DATA_CONTRACT.md`, `docs/SUCCESS.md`, `AGENTS.md`,
`docs/BUILD_ARROW_41.md`, `docs/BUILD_ARROW_61.md`,
`reports/tape41_ingest.txt`, `reports/tape61_ingest.txt`,
`reports/tape17_ingest.txt`.

This arrow is **ingest only**. Do not score engines. Do not tune.
Do not touch `data/full/` or Lab A `data/bars/`.
Do not rebuild December 2025 or January–May 2026 already on virgin.

Aim: one continuous year on disk, **2025-09-01 through 2026-08-31**
(Sep–Dec 2025 + Jan–May 2026 on virgin, Jun–Aug 2026 on `data/full/`).
December 2025 is already complete (Arrows 41 + 61).

## Window

NYSE sessions **2025-09-02 through 2025-11-28** inclusive.
2025-09-01 is Labor Day — not a session. 2025-11-27 is Thanksgiving —
not a session. Keep real holidays. Do not invent bars.
Do not pull 2025-12-01 or later. Do not pull 2025-08-29 or earlier.

If a date in range is not a session, skip it and list it.
If a date is already in the virgin manifest, do not re-fetch.

## Universe (same wall as Arrow 41 / 61)

- Stocks only, common stock, same ETP denylist as Arrow 17 / 41.
- Prior close **[$1, $80]**.
- Prior-day dollar volume **≥ $1,000,000**. Store PDV. $10M is a column,
  not an ingest wall.
- Session **04:00–16:00** ET, one-minute UTP/CTA, 720-bar grid with zeros.
- Pull **IWM** 04:00–16:00 for these dates into `data/virgin/bench/`.
- Theta ≤ 8 concurrent, 429 backoff. Workers for write/validate.
- Resumable manifest. Heartbeat + ETA every 15 minutes.

## Store

Append into existing `data/virgin/` (bars, eligibility, manifest, IWM).
Same layout as Arrow 41 / 61. Gitignore parquet.

## Report

`reports/tape67_ingest.txt`.

Dates pulled, dates skipped (holiday / already on disk / not a session),
sessions, name-days, symbols, 1m rows, mean bars/name-day (expect 720),
failures, wall time, IWM sessions, name-days PDV ≥ $10M, name-days with
a 04:00 print.
State that virgin+full now cover 2025-09 through 2026-08 or list holes.

Append RESEARCH_LOG.md.

Tests:
- do not write Lab A `data/bars/`;
- do not write `data/full/`;
- 2025-09-01 and 2025-11-27 are not pulled;
- 2025-12-01 is not pulled;
- a December 2025 session already in the manifest is not re-fetched.

Commit code + report + manifest if no secrets. No parquet. No Arrow 68.
