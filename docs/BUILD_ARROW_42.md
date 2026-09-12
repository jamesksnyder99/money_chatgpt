# Build Arrow 42 — one-look score on virgin tape

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/tape41_ingest.txt`, `reports/arrow33_results.txt`, `reports/arrow31_results.txt`.

**One look. No rings. No new door. No parameter search.**
Holdout of Jun–Aug is not this window. Combined dollars here are still one calendar, not a printer.

Tape: `data/virgin/bars`. Warmup dates stay on disk for RVOL / EMA only. Score **2026-01-02 through 2026-05-29** as **one window**. Do not split it into develop/holdout and pick a winner.

Do not touch `data/full/` or Lab A `data/bars/`.

## Frozen books ($200 / idea)

1. `B|conj|atr1559|lock` — same Track-B rules as A33 (prior close $10–$50, dv_rank ≥ 0.80 / 400 cap if that is how A33 built the list, gap ≤ −1.5%, OR > 2.5%, conjunction 5-min close < EMA9 and 15-min EMA9 < EMA21 after 09:45, last_entry_at=11:59, trail 1.0× ATR after +1R, flatten 15:59, cap8, SSR uptick10, borrow proxy).
2. `flush|max6|repaired` — same A31 door (08:00 hot, FLY cell available_at=09:45, $5–20, undercut 2–6%, flatten 11:59, cap8).

Reprint n is not required (new calendar). Do not change a threshold if n looks thin.

## Side tables (not tuners)

- Same B door on names with PDV ≥ $10M (filter only).
- Same B door on prior close $20–$80 and PDV ≥ $10M (nicer houses; SHELVE if n < 40).
- Monthly $/day for the combined $200/$200 book (description, not a pick).

## Report

`/day` mean, hit, avgR, PF, se, t, CI, daily-close DD and **intraday** trough, peak/mean concurrent, MFE-capture, IWM alpha skip=0, worst day.
COMBINED $200/$200 with correlation and joint peak risk.
Honesty: this window is the first unstained look; it is still one sample of weather.

## Outputs

`reports/arrow42_results.txt`. Equity csv optional: `reports/equity_virgin_200.csv`.
Append RESEARCH_LOG.md.
Tests: warmup dates produce no fills; a June 2026 date is not in this tape score; long flush / short B only.

Commit code + reports. No parquet. No Arrow 43.
