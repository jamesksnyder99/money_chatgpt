# Build Arrow 40 — session risk budget on the standing books

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow33_results.txt`, `reports/arrow31_results.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

Arrow 39 (halt / day-2) is **skipped** by James. No new rocket door. No virgin pull this arrow. No atr150. No cap12.

Frozen engines (do not change doors):
- B: `B|conj|atr1559|lock` (A32/33 conjunction, 1.0× ATR after +1R, last_entry_at=11:59, flatten 15:59, cap8, SSR uptick10)
- Flush: `flush|max6|repaired` (A31, flatten 11:59)

Acronyms: ATR = Average True Range; MFE = maximum favorable excursion; SSR = Short Sale Restriction.

Size off **intraday peak-to-trough**, not daily-close drawdown. A31 flush holdout intraday trough was about −$1,212 at $200/idea. A33 B lock develop intraday trough about −$2,122.

## Rule

`risk_per_idea = clamp(BUDGET ÷ expected_signals, $200, $600)` when the id says budget.
Expected signals, point-in-time: 08:00 hot count for flush; 09:29 Track-B gap-down-with-wide-OR count for the short (or the session's actual signal count if that is what the engine already knows before the first fill). Outstanding risk across **both** books never exceeds BUDGET on budget rows. Joint peak risk printed on every row.

## Ids

| id | short risk | flush risk | joint cap |
|---|---|---|---|
| 0 | $200 control reprint | $200 | none (today) |
| 1 | $200 | **$400** fixed | none |
| 2 | $200 | **$600** fixed | none |
| 3 | **$400** fixed | **$400** fixed | none |
| 4 | budget on **both**, BUDGET **$1,600** | same | $1,600 |
| 5 | budget on **both**, BUDGET **$2,400** | same | $2,400 |

Id 0 must reprint B develop/holdout n within ±10% of 228 / 93 and flush n within ±3 of 21 / 19.

Report for each: $/day develop and holdout, maxDD daily-close **and** intraday, maxDD as % of $100k, worst day, days at joint cap, COMBINED line, MFE-capture.

Good looks like (judgment, not a silent pass): combined develop clears **$150** with joint **intraday** maxDD under **3%** of account. If it does not, say so in the first paragraph. Do not write that $400 flush is safe because daily-close DD was small.

## Outputs

`reports/arrow40_results.txt`. Append RESEARCH_LOG.md.
Tests: id 0 reprints; id 4 never has combined outstanding risk > $1,600; id 2 flush risk is $600 on a fixture with one flush signal.

Commit code + reports. No parquet. No Arrow 41.
