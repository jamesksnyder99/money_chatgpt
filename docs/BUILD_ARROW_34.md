# Build Arrow 34 — trail on repaired flush|max6

Read `docs/SUCCESS.md`, `AGENTS.md`, `reports/arrow31_results.txt`, `reports/arrow33_results.txt`.

Pass = holdout ≥ $200/day **and** develop not red. Holdout is not a tuner. Combined holdout is not expected value (EV).

Kernel: A31 `flush|max6|repaired` — 08:00 hot, FLY cell available_at=09:45, $5–20, undercut [2%, 6%], 5-min higher-low + strong close, ATR-floored stop, cap8, $200/idea, A1–A5 on. Long only. data/full/. Do not change the door. Do not rescore the B-short. No $500/idea. No virgin. No cell-buy.

Acronyms: ATR = Average True Range; MFE = maximum favorable excursion; IWM = iShares Russell 2000 ETF.

Frozen B for COMBINED: A33 `B|conj|atr1559|lock` daily series (do not replay).

Granularity: frozen five-minute flush door. Finest-tape law applies to new doors (36+).

## Ids

| id | exit |
|---|---|
| 0 | **control** flatten **11:59**. Reprint develop n within ±3 of A31 n=21 |
| 1 | after +1R, trail 1.0× ATR under the favorable high (long), flatten **15:59**. No scale-out |
| 2 | same trail, arms at **+0.5R**, flatten 15:59 |
| 3 | after +1R, trail **1.5× ATR**, flatten 15:59 |
| 4 | id 1 but flatten **13:30** |

No 6th. Locked entries = id 0 admits. Report MFE-capture (this is the point), hit, reached_1R, stop% vs time%, daily-close DD and intraday peak-to-trough, peak/mean concurrent.

Good looks like: develop ≥ +$25 and MFE-capture ≥ 0.30 without develop going red.

## COMBINED

A33 B lock + best develop-not-red flush id this file (else id 0). Honesty line. Joint peak risk if cheap.

## Outputs

`reports/arrow34_results.txt`. Append RESEARCH_LOG.md.
Tests: id 0 n near A31; trail never loosens; id 2 arms at +0.5R; id 4 flattens 13:30; A1 cell still available_at 09:45.

Commit code + reports. No parquet. No Arrow 35.
If GitHub MCP is down, commit with git/gh as usual.
