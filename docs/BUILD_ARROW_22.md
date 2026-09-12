# Build Arrow 22 — drawing board: 08:00 rockets, not the 09:29 funeral

Read `reports/arrow21_results.txt`, `reports/arrow19_survey.txt`, `docs/SUCCESS.md`.

Pass = holdout ≥ $200/day **and** develop not red. `data/full/` only. Long only. Do **not** rerun Arrow 20/21 09:29-open, pullback, strong5, newhigh, or fade-at-the-bell.

Premise: by 09:29 the overnight rocket is a crowded print. Decision stamp is **08:00**. Enter on the next tradeable open. Size off **this morning's** dollar volume, not yesterday's ADV. One variant gets off **before 09:30**.

## 08:00 hot gate

Last tradeable bar ≤ 08:00.

- `prior_close` in [$1, $20]
- `pre_dv_0800` = dollar volume 04:00 through that bar (typical × volume)
- `pre_dv_0800 ≥ $400,000`
- `pre_dv_rel_0800` = pre_dv_0800 / median of the same 04:00–08:00 window over prior 10 sessions (skip if <5 priors) ≥ **3**
- `ext_0800` in **[0.02, 0.10)** — started, not already +15%

## Sizing

`RISK_PER_IDEA=200`. Notional cap = min(10% account, **5% of pre_dv_0800**, 2% prior-day DV). The new cap is the point: a name with $400k overnight cannot take a $20k order.

## Six longs

| id | entry | flatten | extra |
|---|---|---|---|
| 1 | 08:00+ next open | **09:29** (off before the bell) | cap8 |
| 2 | same | 11:59 | cap8 |
| 3 | same | 09:29 | `pre_dv_0800 ≥ $750k` |
| 4 | same | 09:29 | ext_0800 in **[0.02, 0.06)** |
| 5 | same | 09:29 | **max_positions=3** |
| 6 | same | 09:29 | skip the session if 08:00 hot count **> 15** (no cluster days) |

No 7th. No shorts. Report 08:00 hot name-days per session. Dispersion on.

## Outputs

`reports/arrow22_results.txt`. Append RESEARCH_LOG.md.
Tests: gate rejects ext_0800=0.15 and pre_dv=$200k; notional cannot exceed 5% of pre_dv_0800 on a fixture; id 1 flattens by 09:29; id 6 silent on a 20-hot session.

Commit code + reports. No parquet. No Arrow 23.
