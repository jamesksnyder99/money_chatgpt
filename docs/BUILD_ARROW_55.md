# Build Arrow 55 — Friday and Wednesday as a pair (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_54.md`, `reports/arrow54_results.txt`,
`docs/BUILD_ARROW_52.md`, `reports/arrow52_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Same field. Short only. Lookback 15. Residual vs IWM. Eight names.
Hold 10. Last-RTH entry. Costs and borrow proxy as before.
Reuse `src/research/clock.py`.

New hallway: Arrow 52 scored weekdays apart and forbade stacking them.
This arrow stacks Friday and Wednesday on purpose and asks whether they
are two seats or one seat twice. No fade filter. No sector map. No long
leg. No retune of 43 or frozen B / flush. No new ingest. Do not touch
Lab A `data/bars/` except to read a helper.

OOS is one look for the family. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a threshold.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval.

## Rank (shared)

Eligible $10–$80, PDV ≥ $10M, ETP denylist. Residual = name 15-session
close-to-close − IWM. Short the 8 winners. Skip a rebalance if fewer than
16 eligible names have a residual. Skip a name if a required close is missing.

## Ids (frozen — do not add a 7th)

| id | what |
|---|---|
| 0 `fri_6k` | Friday only, $6,000 | control. Must reprint Arrow 54 `plain` / Arrow 53 `vs_iwm` IS $/day within ±10% and n within ±10% of 121 |
| 1 `wed_6k` | Wednesday only, $6,000 | must reprint Arrow 52 `wed_h10` IS $/day within ±10% and n within ±10% of 118 |
| 2 `pair_6k` | ids 0 and 1 both live at $6,000. Same name may be on from both calendars (two tickets). Paper stack. Print peak live notional. |
| 3 `pair_3k` | Friday $3,000 + Wednesday $3,000, same name may be on twice |
| 4 `pair_3k_net` | Friday $3,000 + Wednesday $3,000. If the name is already on from Friday when Wednesday ranks it, skip the Wednesday ticket. |
| 5 `pair_3k_thu` | Wednesday $3,000 + Thursday $3,000, net like id 4 (no second ticket if already on) |

Print Pearson correlation of **daily** PnL between the Friday-only book and
the Wednesday-only book at $6,000 (the two series from ids 0 and 1),
IS and OOS separately. That correlation is the hallway.

Also print mean names in common on weeks when both a Friday and the
following Wednesday (or preceding Wednesday) have an eight: IS only in
a character line.

## Order of work

1. Id 0 and id 1 reprints. If either misses its band, stop and fix.
2. Character: overlap of Friday eight and nearest Wednesday eight, IS.
3. Score all six on IS and OOS. One OOS look.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
Slate: OOS ≥ $200/day **and** IS not red **and** peak live notional ≤ $100k.
Id 2 is allowed to miss the $100k cap — say so. It is a diagnostic.
A stacked id counts as better than id 0 only if it lifts $/day on **both**
IS and OOS **and** fits $100k.
Print t and CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow55_results.txt`.

For each id × IS × OOS: $/day, n, hit, wins, losses, avgWin, avgLoss,
PF, se, t, CI, daily-close DD, worst day, peak/mean concurrent, peak live
notional, IWM alpha skip=0, months.
First paragraph: reprints, daily PnL correlation IS and OOS, whether the
$3k net pair is a slate that fits, whether they are the same eight names.

Append RESEARCH_LOG.md.

Tests:
- id 0 Friday only, $6000 (fixture);
- id 1 Wednesday only, $6000 (fixture);
- id 4 does not open a second ticket in a name already on from Friday (fixture);
- even-month entry is not IS;
- July from `data/full/`, January from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 56.
