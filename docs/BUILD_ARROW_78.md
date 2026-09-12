# Build Arrow 78 — open leftover: complement, overlap, gap

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_77.md`, `reports/arrow77_results.txt`,
`docs/BUILD_ARROW_76.md`, `reports/arrow76_results.txt`,
`docs/BUILD_ARROW_66.md`, `reports/arrow66_results.txt`,
`docs/BUILD_ARROW_65.md`, `reports/tape41_ingest.txt`.

Same hotel. Frozen chassis: 15-session leftover rank, fill first print
≥ 09:30, exit last print at **10:29**, $3,000, field $10–$80 PDV ≥ $10M
ETP denylist. Short only. Do not retune Wednesday H10. Do not change 10:29.

Window: **2026-01-02 through 2026-04-30**. Odd = Jan+Mar. Even = Feb+Apr.
Do not score May–August. Do not use April to pick a filter.

H10 = Arrow 65/66: Wednesday signal, next last-RTH, $4,000, hold 10.
A name is **on H10 at 09:30** if that short is still live from a prior fill.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Filters (known at 09:30)

Gap = 09:30 first print ÷ prior last-RTH − 1. Causal if fill is that same
09:30 print? **No.** Rank leftover off prior closes. Gap uses the 09:30
print. Fill must be the next print at or after **09:31** for every id in
this arrow so the gap is known. Id 0 reprint of 76 used 09:30 fill — that
reprint stays 09:30 so we can see whether 09:31 changes the parent.

## Ids (frozen — do not add a 7th)

| id | who |
|---|---|
| 0 `all_0930` | eight leftover, fill 09:30, exit 10:29 | reprint 76/77 parent, odd $/day within ±15% of 125.39 |
| 1 `all_0931` | eight leftover, fill 09:31, exit 10:29 | causal parent |
| 2 `complement` | leftover eight **minus** names on H10 at 09:30 (may be <8). Fill 09:31 |
| 3 `overlap_only` | leftover eight **intersect** H10 live (may be <8). Fill 09:31 |
| 4 `gap_up` | leftover eight with gap ≥ 0. Fill 09:31 |
| 5 `gap_dn` | leftover eight with gap < 0. Fill 09:31 |

If complement or overlap has 0 names that session, sit out. Do not backfill
with the next leftover name unless it already was in the eight.

## Order of work

1. Id 0 reprint. If it misses the band, stop and fix.
2. Character: mean n on complement / overlap / gap_up / gap_dn per session
   (odd only). Description. Does not pick an id.
3. Score all six on odd and even. Print months. Print daily corr of
   complement vs H10 MTM (sessions both exist).

A filter beats id 1 (causal parent) only if it lifts $/day on **both**
odd and even. Print t, CI. Say when a CI excludes 0.
Do not call a CI that includes 0 "EV." Still a sniff.

## Report

`reports/arrow78_results.txt`.

First paragraph: reprint, 09:31 vs 09:30, whether complement is the
second pulse (low corr, both slices green), gap_up vs gap_dn.
Then character. Then each id × odd × even × months.

Append RESEARCH_LOG.md.

Tests:
- id 2 never shorts a name that is on H10 at 09:30 (fixture);
- id 3 never shorts a name that is not on H10 at 09:30 (fixture);
- id 1 fill is ≥ 09:31 not 09:30 (fixture);
- May is not scored;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 79.
