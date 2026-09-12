# Build Arrow 72 — Wednesday H10 regime skips (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_66.md`, `reports/arrow66_results.txt`,
`docs/BUILD_ARROW_71.md`, `reports/arrow71_results.txt` if present,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

Same leftover short as Arrow 66 `h10_4k`. Same fill and hold.
The only new knob is **whether this Wednesday exists**.
Do not change rank, n, hold, ticket, or fill. Do not keep/cash.
Do not retune frozen B / flush.

Parent: Wednesday signal, eight largest 15-session close-to-close returns,
fill next session last-RTH, $4,000, hold 10, drop missing fill.
Field $10–$80 PDV ≥ $10M ETP denylist. MTM as Arrow 65.
Odd months IS, even OOS, split on the signal Wednesday.
Jan–Aug 2026 only (virgin + full). Do not mix Sep–Dec 2025.
Reuse `src/research/clock.py`.

OOS is one look. Do not drop an id after seeing OOS.
Do not use an OOS month to pick a cutoff. Cutoffs come from **IS
character of id 0's Wednesdays only**, then freeze.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Signals known at Wednesday last-RTH

- `iwm_15` = IWM 15-session close-to-close return.
- `width` = 15-session return of leftover #1 minus leftover #8 that day.
- `crowd` = count of eligible names whose 15-session return ≥ 15%.
- `ivol` = stdev of IWM's last 15 session close-to-close returns.

IS character (id 0 Wednesdays): median `width`, median `crowd`, median
`ivol`, fraction of Wednesdays with `iwm_15` ≥ 0. Description. Does not
pick an id. Those three medians are the frozen cutoffs for ids 3–5.

## Ids (frozen — do not add a 7th)

| id | Wednesday exists if |
|---|---|
| 0 `h10_4k` | always | reprint Arrow 66 `h10_4k` IS MTM $/day within ±10% |
| 1 `iwm_up` | `iwm_15` ≥ 0 |
| 2 `iwm_dn` | `iwm_15` < 0 |
| 3 `wide` | `width` ≥ IS median width |
| 4 `uncrowded` | `crowd` ≤ IS median crowd |
| 5 `lowvol` | `ivol` ≤ IS median ivol |

A skipped Wednesday is cash that week: no new fills. Names already on
from last week still mark and exit on their own day-10. Do not flatten
them early just because this Wednesday was skipped.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. IS character + freeze the three medians. Print them.
3. Score all six. One OOS look.

Pass for a seat: OOS MTM $/day ≥ $100 **and** IS MTM not red.
Slate: OOS MTM ≥ $200 **and** IS MTM not red **and** peak live ≤ $100k.
A skip id beats id 0 only if it lifts MTM $/day on **both** IS and OOS
and does not worsen OOS max DD by more than 25%.
Print n Wednesdays kept, t, CI. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow72_results.txt`.

First paragraph: reprint, the three IS medians, which skip beat id 0 on
both slices, how many Wednesdays each skip sat out.
Then each id × IS × OOS: MTM $/day, n trades, n Wednesdays, hit, PF, t,
CI, MTM DD, peak live, months.

Append RESEARCH_LOG.md.

Tests:
- id 0 has no Wednesday skip (fixture);
- id 1 has no new fills on a Wednesday with iwm_15 < 0 (fixture);
- even-month signal is not IS;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 73.
