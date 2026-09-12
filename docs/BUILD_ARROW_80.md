# Build Arrow 80 — five frozen open leftover books, Sep 2025–Aug 2026

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_79.md`, `reports/arrow79_results.txt`,
`docs/BUILD_ARROW_78.md`, `reports/arrow78_results.txt`,
`docs/BUILD_ARROW_76.md`, `reports/arrow76_results.txt`,
`docs/BUILD_ARROW_68.md`, `reports/arrow68_results.txt`,
`docs/BUILD_ARROW_70.md`, `reports/arrow70_results.txt`,
`docs/BUILD_ARROW_65.md`, `reports/tape69_ingest.txt`,
`reports/tape67_ingest.txt`, `reports/tape41_ingest.txt`,
`reports/tape17_ingest.txt`.

One look of **five frozen** day books across the year already on disk.
Do not add a sixth. Do not gap-filter. Do not retune Wednesday H10.
Do not pick an id after seeing a month.

Chassis: 15-session leftover rank, fill first print ≥ **09:30**, field
$10–$80 PDV ≥ $10M ETP denylist, $3,000. Short only.
H10 = Arrow 65/66: Wednesday signal, next last-RTH, $4,000, hold 10.
Complement = leftover eight minus names on H10 at 09:30.
Lookback may read August 2025. Jun–Aug 2026 from `data/full/`.
Sep 2025–May 2026 from `data/virgin/`.

Window: **2025-09-02 through 2026-08-31**. First session with 15 prior
sessions on tape. Print 12 months. Odd vs even is courtesy, not a new
promotion split. Jan–Apr 2026 already had a look; Sep–Dec 2025 and
May–Aug 2026 are new for this hotel.

No new ingest. Do not touch Lab A `data/bars/`.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Ids (frozen — do not add a 6th)

| id | n | exit | days |
|---|---|---|---|
| 0 `n15_1029` | 15 | 10:29 | every session |
| 1 `n8_1029` | 8 | 10:29 | every session | parent |
| 2 `n8_1029_notue` | 8 | 10:29 | skip Tuesday |
| 3 `n8_1129` | 8 | 11:29 | every session |
| 4 `comp_1029` | leftover eight minus H10 live | 10:29 | every session |

Id 0 January $/day should sit near Arrow 76 `h1029_n15` +379.53.
Id 1 January $/day should sit near Arrow 76 `h1029_n8` +268.33.
If those miss ±20%, stop and fix the seam.

## Score

$/day = total PnL / NYSE sessions in 2025-09-02..2026-08-31, and by month.
Hit, W/L, PF, t, CI, peak live.
Daily Pearson of ids 1 and 4 vs H10 MTM (year, fall 2025, Jan–Aug 2026,
June 2026 alone). Mean overlap / 8 of id 1 vs H10 live.

Say whether June is fat for the day book the way it is for H10.
Say whether September 2025 is a hole the way it is for H10.
Do not call the year a $200 slate pass. Do not call a CI that includes 0 "EV."

## Report

`reports/arrow80_results.txt`.

First paragraph: year $/day all five, September vs June vs H10, whether
complement still looks like a second pulse on the new months.
Then 12-month table all five. Then trade stats.

Append RESEARCH_LOG.md.

Tests:
- id 4 never shorts a name on H10 at 09:30 (fixture);
- id 2 has no Tuesday fills (fixture);
- id 3 exits 11:29 not 10:29 (fixture);
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 81.
