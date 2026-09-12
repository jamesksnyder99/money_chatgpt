# Build Arrow 68 — Wednesday H10 one-look on Sep–Dec 2025

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_65.md`, `reports/arrow65_results.txt`,
`docs/BUILD_ARROW_66.md`, `reports/arrow66_results.txt`,
`docs/BUILD_ARROW_67.md`, `reports/tape67_ingest.txt`,
`docs/BUILD_ARROW_69.md`, `reports/tape69_ingest.txt` (after 69 lands),
`reports/tape61_ingest.txt`, `reports/tape41_ingest.txt`.

One look of the **frozen** paper book on tape those arrows never scored.
Do not retune lookback, n, weekday, hold, ticket, or fill.
Do not walk rings. Do not use 2026 **signals** — Jan–Aug 2026 already
had its IS/OOS look. January 2026 bars may be used only as a December
signal's exit or as lookback stamps.

Frozen book: Wednesday signal, 15-session close-to-close (IWM subtract
is a scalar; rank = eight largest 15-session returns), short eight,
fill **next session last-RTH**, $4,000, hold 10 from the fill session,
drop a name if the exit bar is missing. Field $10–$80 PDV ≥ $10M ETP denylist.
MTM daily equity as Arrow 65.
Reuse `src/research/clock.py` and Arrow 65 fill/MTM path.

**Run Arrow 69 first** if August 2025 is not already on virgin. Lookback
may read August 2025 bars. Do not invent August if 69 has not landed.

Window: signal Wednesdays in **2025-09-03 through 2025-12-31**.
First legal signal = first Wednesday in September 2025 that has 15 prior
sessions on virgin (with August warmup: expect 2025-09-03).
Last signal: last Wednesday in December 2025. If that hold exits in
January 2026, read January virgin and say so.

This window is **one slice**. Print Sep, Oct, Nov, Dec. Do not treat them
as IS/OOS for promotion. Do not drop anything after seeing a month.

No new ingest inside this arrow. Do not touch Lab A `data/bars/`.
Do not touch `data/full/`.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Ids (frozen — do not add a 2nd book)

| id | what |
|---|---|
| 0 `wed_h10_4k` | frozen paper book |

## Score

Print entry-attributed $/day **and** MTM $/day (total PnL / NYSE sessions
in 2025-09-02..2025-12-31, and / sessions from first signal through last exit).
Hit, wins, losses, avgWin, avgLoss, PF, se, t, CI on the MTM daily series.
MTM DD, worst day, peak live |shares × last|.
IWM alpha. By month: Sep, Oct, Nov, Dec.
Say when a CI excludes 0. Do not call a CI that includes 0 "EV."
Do not call this window a $200 slate pass. Report dollars and whether
the sign matches 2026 Wednesday H10.

## Report

`reports/arrow68_results.txt`.

First paragraph: first signal date, n, MTM $/day, months, peak live,
whether this looks like 2026 Wednesday H10.

Append RESEARCH_LOG.md.

Tests:
- only one id;
- fill is next last-RTH not signal close (fixture);
- no signal before 15 prior sessions exist (fixture);
- 2026-01 through 2026-08 are not in the **signal** set;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet.
