# Build Arrow 41 — virgin ingest January–May 2026 (Dec 2025 warmup)

Read `docs/DATA_CONTRACT.md`, `docs/SUCCESS.md`, `AGENTS.md`, `reports/tape17_ingest.txt`.

This arrow is **ingest only**. Do not score engines. Do not tune. Do not touch `data/full/` or Lab A `data/bars/`.

## Window

- Warmup: **last 10 NYSE trading days of 2025** (on disk for prior-day dollar volume and EMA stitch; **do not score**).
- Study (the one look, later): **first NYSE session of 2026 through the last full session in May 2026** (expected last study day **2026-05-29** if that is a session). All of January is in the scored window.
- Keep real holidays. Do not invent bars.

## Universe (pull)

- Stocks only, common stock, same ETP denylist as Arrow 17.
- Prior close **[$1, $80]** (keeps today’s $1–$50 names; adds $50–$80).
- Prior-day dollar volume **≥ $1,000,000**. Store PDV on each name-day. **$10M is a filter column, not an ingest wall.**
- Session **04:00–16:00** ET, one-minute UTP/CTA, 720-bar grid with zeros, same as `data/full/`.
- Also pull **IWM** 04:00–16:00 for warmup + study dates into `data/virgin/bench/`.

## Store

`data/virgin/` (bars + manifest). Gitignore parquet. Resumable manifest. Theta ≤8 concurrent, 429 backoff. Workers for write/validate. Heartbeat + ETA every 15 minutes.

Report: warmup dates, study dates, sessions, name-days, symbols, row count, bars/name-day, failures, wall time, name-days with PDV ≥ $10M, name-days with prior_close > $50.

## Outputs

`reports/tape41_ingest.txt`. Append RESEARCH_LOG.md.
No engine replay. No Arrow 42 in this commit (42 is the one-look score).

Commit code + report + manifest if no secrets. No parquet.
