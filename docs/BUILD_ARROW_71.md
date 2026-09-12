# Build Arrow 71 — Wednesday H10 keep / cash (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_66.md`, `reports/arrow66_results.txt`,
`docs/BUILD_ARROW_65.md`, `reports/arrow65_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Same leftover short as Arrow 66 `h10_4k`. Same entries. Only the exit
can change. Do not replace a flattened name with a new leftover.
Do not retune rank, n, weekday, ticket, or fill.
Do not retune frozen B / flush.

Parent: Wednesday signal, eight largest 15-session close-to-close returns,
fill next session last-RTH, $4,000, hold-10 **backstop**, drop if the
fill bar is missing. Field $10–$80 PDV ≥ $10M ETP denylist.
MTM as Arrow 65. Split on the **signal** Wednesday. Odd months IS, even OOS.
Reuse `src/research/clock.py`. Score on Jan–Aug 2026 (virgin + full) so
id 0 can reprint Arrow 66. Do not mix Sep–Dec 2025 into this family.

OOS is one look. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.
The three cash rules below are frozen. Do not search X on OOS.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Daily checkpoint

Each session the name is still on, at last-RTH, after that close exists:

**A — no longer leftover.** Recompute today's 15-session rank on the
eligible field. If the name is not in the top **20**, cash.

**B — thesis invalid.** Cash if today's last-RTH ≥ the **fill** price,
or if today's last-RTH is a new high versus the prior 5 sessions' highs
(fill session and after).

**C — no progress.** On hold-day **3** and after: cash if last-RTH is
not **below** the fill by at least **1%**. (Price has not slid. P&L of
the trade is not the trigger.)

First rule that fires, cash at that last-RTH (same cost model as any exit).
If none fire, keep. Day 10 last-RTH is always an exit if still on.
Do not enter a different name into the empty slot.

## Ids (frozen — do not add a 7th)

| id | rules |
|---|---|
| 0 `h10_4k` | hold 10 only | control. Reprint Arrow 66 `h10_4k` IS MTM $/day within ±10% and n within ±10% of 116 |
| 1 `cash_A` | A, then day-10 backstop |
| 2 `cash_B` | B, then day-10 backstop |
| 3 `cash_C` | C, then day-10 backstop |
| 4 `cash_AB` | A then B, then day-10 |
| 5 `cash_ABC` | A then B then C, then day-10 |

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. IS character: for id 0 names, fraction that would have fired A / B / C
   on each hold-day 1..10. Description. Does not pick an id.
3. Score all six. One OOS look.

Pass for a seat: OOS MTM $/day ≥ $100 **and** IS MTM not red.
Slate: OOS MTM ≥ $200 **and** IS MTM not red **and** peak live ≤ $100k.
A cash id beats id 0 only if it lifts MTM $/day on **both** IS and OOS
and does not worsen OOS max DD by more than 25%.
Print t, CI, mean hold days, n that cashed early. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow71_results.txt`.

First paragraph: reprint, who beat id 0 on both slices, mean hold,
whether ABC helped or just flattened winners.
Then each id × IS × OOS: entry $/day, MTM $/day, n, mean hold, early-cash n,
hit, wins, losses, PF, t, CI, MTM DD, worst day, peak live, months.

Append RESEARCH_LOG.md.

Tests:
- id 0 hold 10, no A/B/C (fixture);
- id 1 cashes a name that leaves the top 20 before day 10 (fixture);
- id 5 does not open a new leftover name after a cash (fixture);
- even-month signal is not IS;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 72.
