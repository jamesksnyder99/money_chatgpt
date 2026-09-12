# Build Arrow 77 — open leftover short: H10 overlap + weekdays

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_76.md`, `reports/arrow76_results.txt`,
`docs/BUILD_ARROW_66.md`, `reports/arrow66_results.txt`,
`docs/BUILD_ARROW_65.md`, `reports/arrow65_results.txt`,
`reports/tape41_ingest.txt`.

Same hotel. Frozen day book: eight largest 15-session close-to-close,
fill first print ≥ 09:30, exit last print at **10:29**, $3,000, field
$10–$80 PDV ≥ $10M ETP denylist. Short only.
Do not retune Wednesday H10. Do not change the 10:29 exit.

Window: **2026-01-02 through 2026-04-30** on virgin (same as Arrow 76).
Odd = Jan+Mar. Even = Feb+Apr. Do not score May–August.
Do not use April to pick a weekday.

Reuse `src/research/clock.py` and Arrow 65/66 H10 definition:
Wednesday signal, next last-RTH fill, $4,000, hold 10, drop missing exits.
Build H10 MTM daily PnL on this window so correlation is the same calendar.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Character (id 0 vs H10) — does not pick an id

Each session the day book has names on:
- count of those eight that are also on the H10 book that session
  (H10 hold still live at 09:30).
- mean overlap / 8.
Pearson correlation of **daily** day-book PnL vs H10 MTM PnL on sessions
both exist. Print odd and even separately.
Description: same eight names or a second pulse.

## Ids (frozen — do not add a 7th)

| id | days |
|---|---|
| 0 `all` | every session | reprint Arrow 76 `h1029_n8` odd $/day within ±15% of 125.39 |
| 1 `mon` | Monday |
| 2 `tue` | Tuesday |
| 3 `wed` | Wednesday |
| 4 `thu` | Thursday |
| 5 `fri` | Friday |

Weekday ids still flatten 10:29 same day. $/day = total PnL / NYSE
sessions in the **slice** (same denominator as id 0), so a quiet weekday
looks small because it sits fewer days — also print $/day among sessions
that weekday fired.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Overlap + correlation character.
3. Score all six on odd and even. Print months.

A weekday beats id 0 only if it lifts $/day on both odd and even using the
**fired-day** denominator — do not crown Monday because the slice
denominator hid zeros. Print t, CI on the fired-day series if n allows.
Say when a CI excludes 0. Do not call a CI that includes 0 "EV."
Still a sniff. Say that.

## Report

`reports/arrow77_results.txt`.

First paragraph: reprint, mean overlap vs H10, daily corr, which weekdays
print on both slices.
Then character block. Then each id × odd × even × months.

Append RESEARCH_LOG.md.

Tests:
- id 0 every session, exit 10:29 (fixture);
- id 3 Wednesday only (fixture);
- H10 fill is not the day-book 09:30 fill (fixture);
- May is not scored;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 78.
