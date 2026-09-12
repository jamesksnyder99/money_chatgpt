# Build Arrow 31 — integrity repairs; rescore both leaders

Read `docs/SUCCESS.md`, `reports/arrow28_results.txt`, `reports/arrow26_results.txt`, `src/research/book.py`, `src/research/strategies13.py`, `src/research/strategies25.py`.

This arrow does **not** invent a new engine. Pass line still exists for the rescored leaders: holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

No rocket rings. No $500/idea. No virgin pull. No cell-buy. No cap12.

Spell out acronyms on first use in the report: EMA = exponential moving average; ATR = Average True Range; SSR = Short Sale Restriction; RVOL = relative volume; MFE = maximum favorable excursion; IWM = iShares Russell 2000 ETF.

## Repairs (all must ship, each with a test)

**A1 Flush look-ahead.** Every prerequisite has `available_at`. The FLY cell (OR width, premarket dollars, ext at 09:44) is available at **09:45**, not at 09:44:00. Do not admit a flush fill whose signal time is before 09:45 using cell state from 09:44. After 09:45, re-check the live setup or wait for the next qualifying higher-low. Report count and PnL of historical flush|max6 entries that would have been rejected under this rule.

**A2 One EMA clock.** For a B-short decision, EMA9-close and 9/21 regime use the same availability cut (`bar_end`). A sparse 5-minute bucket is not “complete” at its last traded minute. Test a 15-minute boundary fixture.

**A3 last_entry_at ≠ flatten_at.** New entries stop at `last_entry_at`. Flatten only exits. Default last_entry_at = 11:59 for locked-cohort rows. Report locked-cohort vs full-book for the A28 trail row.

**A4 Trail already through price.** After a ratchet, if the new stop is already beyond the current close, queue the next-event exit now. Count crossed-at-creation. Do not switch to rolling ATR and call it the same manager.

**A5 No backdated flatten.** `liquidation_requested` vs `liquidation_filled`. If 11:59 has no print, do not execute at 11:50. Unresolved if no later event. Report affected exits.

**A6 Calendar RVOL.** Prior window = last ten **exchange sessions** with an explicit zero vs missing. Rename in the report if you cannot enforce calendar yet — do not silently keep “last ten retained rows.”

**A7 Marked equity.** One-minute marked-to-market equity on each leader. Print daily-close drawdown (old stat, renamed) **and** intraday peak-to-trough. Before any later size-up.

**C-R1 Flush vs anchor.** If the first undercut tag is before the anchor is known, ignore those bars; do not return []. Rerun A29 ids 4 and 5 (undercut of 09:44 close; undercut of OR high) as diagnostic rows only.

**C-R2 IWM tape.** If `data/full/bench` lacks 04:00–16:00 IWM, pull it (study window only). Alpha skip=0 on A28-style rows that hold past noon.

**C-R3 EMA stitch.** Rescore B row-0 flatten 11:59 and the trail-to-15:59 row on (i) 04:00 stitch (ii) 07:30+ stitch. Print n vs A27 B_uptick10. Pick neither as a new champion this arrow — print both.

**C-R4 / R5 / R6.** Every population table: n_all, FLY/n_all, FAIL/n_all, other/n_all. Stat block: MFE-capture = realised / sum(max(0,MFE_R)×risk). Combined: joint peak outstanding risk if both trade lists exist.

**C-R7.** Implement `harvestable_altitude` helper (from first fillable bar after confirm+5m, RTH for RTH launches, from 09:45 for premarket launches, volume ≥ 2000). Print a short develop table; full field scan is not required this arrow.

## Rescore (after repairs)

| id | what |
|---|---|
| flush|max6|repaired | A26 kernel, cell available 09:45, A1–A5 on |
| B|uptick10|flat1159|lock | last_entry_at=11:59, flatten 11:59, A2 clock |
| B|uptick10|atr1559|lock | last_entry_at=11:59, trail after +1R, flatten 15:59 |
| B|uptick10|atr1559|full | last_entry_at=15:59 (afternoon admits allowed) |

COMBINED: repaired flush + B atr1559 **lock** (the apples-to-apples morning book). Also print full-book combined as a second line labeled FULL, not EV.

Honesty: if repaired flush or locked trail is no longer both-green, say so in the first paragraph.

## Outputs

`reports/arrow31_results.txt`. Append RESEARCH_LOG.md.
Tests: A1 future-suffix (09:44 close flip changes admission); A2 15-minute boundary; A3 a 13:00 signal is silent when last_entry_at=11:59; A4 crossed ratchet exits next event; A5 11:59 dead ≠ 11:50 fill; C-R1 10:10 undercut fires, 09:35-only does not kill the name.

Commit code + reports. No parquet. No Arrow 32.
