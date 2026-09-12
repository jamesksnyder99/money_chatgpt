# Build Arrow 79 — complement × gap, skip Tuesday

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_78.md`, `reports/arrow78_results.txt`,
`docs/BUILD_ARROW_77.md`, `reports/arrow77_results.txt`,
`docs/BUILD_ARROW_65.md`, `reports/tape41_ingest.txt`.

Same hotel. Frozen chassis: 15-session leftover, fill ≥ **09:31**,
exit **10:29**, $3,000, field $10–$80 PDV ≥ $10M. Short only.
Do not retune Wednesday H10.

Window: **2026-01-02 through 2026-04-30**. Odd = Jan+Mar. Even = Feb+Apr.
Do not score May–August. Do not use April to pick a cross.

H10 live at 09:30 as Arrow 78. Gap = 09:30 first / prior last-RTH − 1.
Complement = leftover eight minus names on H10.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Ids (frozen — do not add a 7th)

| id | who |
|---|---|
| 0 `all_0931` | eight leftover | reprint 78 id 1, odd $/day within ±15% of 122.61 |
| 1 `comp` | complement | reprint 78 complement |
| 2 `comp_gap_dn` | complement **and** gap < 0 |
| 3 `comp_gap_up` | complement **and** gap ≥ 0 |
| 4 `all_not_tue` | eight leftover, skip Tuesday |
| 5 `comp_not_tue` | complement, skip Tuesday |

Sit out if the filter leaves 0 names. Do not backfill from leftover 9–16.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Character: odd-only mean n for ids 2 and 3.
3. Score all six on odd and even. Print months. Print complement-family
   daily corr vs H10 MTM.

A cross beats id 1 only if it lifts $/day on **both** odd and even.
Print t, CI. Say when a CI excludes 0. Do not call a CI that includes 0 "EV."
Still a sniff.

## Report

`reports/arrow79_results.txt`.

First paragraph: reprint, whether comp×gap_dn lifts both vs complement,
whether skipping Tuesday lifts both vs the un-skipped parent.
Then each id × odd × even × months.

Append RESEARCH_LOG.md.

Tests:
- id 2 names are off H10 and gap < 0 (fixture);
- id 4 has no Tuesday fills (fixture);
- May is not scored;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 80.
