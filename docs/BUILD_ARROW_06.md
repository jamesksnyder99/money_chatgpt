# Build Arrow 6 — engine repairs + optional trend

Read `docs/SUCCESS.md`, `docs/BUILD_ARROW_05.md`, `reports/RESEARCH_LOG.md` first.

James's intent for warmup trend was **not** "every rule may only trade with the 10-session trend." That was over-tethered in Arrow 5. Trend is a **solid stance for some variants**, not a chain on all of them.

If Arrow 5 is mid-run: finish writing code if needed, but **do not treat the Arrow 5 all-with-trend holdout as the final score**. After repairs below, re-score the ten mechanisms with the stance split in this file. If Arrow 5 already committed an all-tethered report, keep that file and add Arrow 6 results beside it.

## Engine repairs (do these first; tests required)

1. **Actual R.** Store `risk` on each `Trade`. `avgR = mean(pnl / risk)` using that trade's risk, not `pnl / 200`. If risk is 0, skip the trade in the R average.
2. **RTH VWAP.** Session VWAP for research rules uses **RTH bars only** (09:30+), unless a rule explicitly says premarket enters the VWAP.
3. **Overnight / open queue.** When staging `rth_open_entries` or same-timestamp signals, sort by `|score|` descending and call `can_enter` **before** queueing. Do not rely on dict insertion order.
4. **CLI.** `scripts/research.py --mode` includes `arrow5` and `arrow6`.
5. **Leave next-open stop fills as they are.** Slippage through the stop is intended. Document it. Do not invent magic stop fills.

## Trend definition (unchanged math, optional use)

Same 10 prior official EOD closes as Arrow 5:

- Up: `C10 > C1` and `C10 > mean(C1..C10)`
- Down: inverse
- Flat: neither

Warmup exists so session 2026-06-01 has 10 priors.

## Stance split (this is the liberation)

**With-trend (skip if flat; side must match trend):**

- trend_open
- gap_with_trend
- down_day_then_trend
- late_with_trend
- channel_position

**Free (ignore 10d trend; may trade flat names; side comes only from the setup):**

- trend_pullback — rename in code/report to `session_pullback` (pullback vs today's RTH extreme; both directions allowed)
- yday_level_break
- compression_expansion (direction = the 15-min expansion, not the EOD trend)
- rs_vs_book
- adv_expanding (direction = 09:30→10:00 session direction)

Do **not** add a "fade the 10d trend" book in this arrow. Do not invent an 11th mechanism.

Same fields as Arrow 5 (Track A and B), same harness otherwise, 42/22, holdout once after the repair.

## Outputs

- `reports/arrow06_results.txt` — verdict vs $200 holdout; table track × rule × stance × develop/holdout $/day, trades, hit, **avgR on actual risk**, maxDD.
- Append `reports/RESEARCH_LOG.md` noting the tether correction.
- Tests: avgR uses trade.risk; VWAP helper ignores premarket; queue respects can_enter and score order.

Commit code + reports. No parquet. No Arrow 7.
