# Build Arrow 73 — IWM-up skip, one-look Sep–Dec 2025

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_72.md`, `reports/arrow72_results.txt`,
`docs/BUILD_ARROW_68.md`, `reports/arrow68_results.txt`,
`docs/BUILD_ARROW_69.md`, `reports/tape69_ingest.txt`.

One look of two frozen books on Sep–Dec 2025. Do not retune.
Do not invent a new cutoff. Do not walk width/crowd/vol here.
Do not mix 2026 **signals** (January bars may be a December hold's exit).

Books:
- Parent: Wednesday H10, every Wednesday, next last-RTH, $4,000, hold 10.
- Skip: same, but **no new fills** on a Wednesday whose IWM 15-session
  close-to-close return is < 0. Names already on still ride to day 10.

`iwm_15` is known at Wednesday last-RTH. Rank is still the eight largest
15-session name returns. Field $10–$80 PDV ≥ $10M ETP denylist.
MTM as Arrow 65. Reuse `src/research/clock.py`.
Lookback may read August 2025. First signal 2025-09-03 if 15 sessions exist.

This window is **one slice**. Print Sep, Oct, Nov, Dec. Do not treat them
as IS/OOS. Do not drop a month after seeing it.
No new ingest. Do not touch Lab A `data/bars/` or `data/full/`.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction; CI = confidence interval;
MTM = mark-to-market.

## Ids (frozen — do not add a 3rd)

| id | Wednesday exists if |
|---|---|
| 0 `always` | always | should sit near Arrow 68 month tape (Sep hole, Oct fat) |
| 1 `iwm_up` | `iwm_15` ≥ 0 |

## Score

MTM $/day (total PnL / sessions 2025-09-02..2025-12-31, and / first
signal through last exit). Hit, W/L, PF, t, CI, MTM DD, peak live.
By month. n Wednesdays kept vs sat out for id 1.
Say whether id 1 **cuts total MTM $** vs id 0, and whether September
and December are less red. Do not call this a $200 slate pass.
Do not call a CI that includes 0 "EV."

## Report

`reports/arrow73_results.txt`.

First paragraph: Wednesdays sat out, September/October/December vs always,
whether total dollars fell, whether a parametric follow-up is even on
the table.

Append RESEARCH_LOG.md.

Tests:
- id 1 has no new fills when iwm_15 < 0 (fixture);
- id 0 has no skip (fixture);
- 2026-01..08 are not in the signal set;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 74.
