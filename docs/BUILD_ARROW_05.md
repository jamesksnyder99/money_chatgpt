# Build Arrow 5 — ten mechanisms, warmup trend, orthogonal to Arrows 3–4

Read `docs/SUCCESS.md`, `reports/RESEARCH_LOG.md`, `reports/arrow03_results.txt`, `reports/arrow04_results.txt` first.

Do **not** implement gap-fade, first-5-min open-drive, VWAP reclaim, 09:30–09:44 OR-break, or the Arrow 4 +1.5% same-session next-open swing. Those experiments are closed.

James added the 10 May warmup sessions so each name has a **pre-study regime**. Use them. Default stance: **trade with the 10-session trend or stand aside.** Do not fade the 10-session trend in this arrow.

## Trend (one definition, all rules)

For session D, use official EOD **closes** on the 10 NYSE sessions immediately before D (warmup covers June 1). Let `C1..C10` be those closes oldest→newest (`C10` = prior official close).

- **Up:** `C10 > C1` and `C10 > mean(C1..C10)`
- **Down:** `C10 < C1` and `C10 < mean(C1..C10)`
- **Flat:** else — **no trade** that name that day

If fewer than 10 prior EOD closes, skip the name that day. Intraday 1m is for timing only; trend is EOD.

## Field

Run all 10 rules on **both** existing books (no new price band):

- **A:** Lab A bars with that day `prior_close in [10,30]` and `prior_dollar_volume >= 5e6`
- **B:** Track B eligibility already built ([$10,$50], ≥ $5M, cap 400/day if that file exists; else same cap rule as Arrow 4)

Same harness as Arrow 3/4: next-bar open fills, costs, $200 risk, 5 positions, 10 entries, $1k risk cap, zero-volume ≠ trade, RTH entries, flatten 11:59, warmup = **no PnL**, 42/22 split, holdout **once**. Parallelize. Rank same-bar signals by `|score|`.

## Ten mechanisms (frozen; no 11th)

Each rule may only take the side of that day’s EOD trend (or skip if flat).

1. **trend_open** — At first tradeable 09:30 bar, enter **with** trend. Stop = `max($0.10, 1% of entry)` against the trend. Score = `|C10/C1 - 1|`.
2. **trend_pullback** — After 10:00, first pullback of ≥ 1% from the session RTH extreme *in the trend direction* (from RTH high if up, from RTH low if down). Enter with trend. Stop beyond that pullback extreme.
3. **yday_level_break** — First RTH close beyond **prior session’s** high (up) or low (down) from our 07:30–12:00 tape. Stop at that prior extreme.
4. **gap_with_trend** — 09:30 open vs prior close gaps ≥ 1.5% **in the trend direction**. Enter next tradeable bar with trend. Stop other side of 09:30 open. This is continuation, not fade.
5. **compression_expansion** — 10 prior sessions’ morning range (high−low in window) median = M. If prior session range ≤ 0.7×M (compressed) and first 15 RTH minutes range ≥ 1.2×M, enter close of 09:44 bar **with trend**. Stop other side of that 15-min range.
6. **rs_vs_book** — At 10:15, each name’s return from 09:30 open vs the **median** 09:30–10:15 return of eligible names that session. If trend up, signal only if name return ≥ 70th percentile of the book; if down, ≤ 30th. Enter next bar with trend. Stop = 1% against.
7. **down_day_then_trend** — Prior session morning was **against** the still-intact 10d trend (prior 07:30–12:00 close vs prior 09:30 open). Today enter 09:31 with the 10d trend (failed opposite day into trend).
8. **adv_expanding** — Prior-day dollar volume > median of that name’s prior 10 prior-day dollar volumes. After 10:00, first RTH close vs 09:30 open still with the 10d trend. Enter that next bar. Stop 1% against.
9. **late_with_trend** — No entry before 11:00. If 11:00 close is still on the trend side of the 09:30 open, enter 11:01 with trend. Stop 09:30 open.
10. **channel_position** — 10 prior sessions’ window high H and low L. Mid = (H+L)/2. After 09:45, if trend up and last close ≥ mid and ≤ H, long; if trend down and last close ≤ mid and ≥ L, short. One signal per name at first qualifying bar. Stop = mid.

No grids. No ML. No extra indicators. Do not combine two mechanisms into a 11th system in this arrow (report them separately).

## Outputs

- `reports/arrow05_results.txt` — lead verdict vs $200 holdout. Table track × rule × develop $/day × holdout $/day × trades × hit × avgR × maxDD. Flag any holdout ≥ $200. Also list how many name-days were flat/up/down.
- Append `reports/RESEARCH_LOG.md` (what died; do not retry exact (track, rule) without a new reason).
- Tests: flat trend ⇒ no signals from rule 1; gap_with_trend does not fire on a gap **against** trend; pullback does not fire before 10:00.

Commit code + reports. No parquet. No Arrow 6.
