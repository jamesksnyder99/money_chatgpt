# Build Arrow 25 — concentric rings on flush + FLY cell

Read `reports/arrow24_results.txt`, `docs/SUCCESS.md`.

Pass = holdout ≥ $200/day **and** develop not red. `data/full/` only. Part B harness ON (ATR/0.6% stop floor, cost gate, ranked fill, confirmed-launch helper available). $200/idea. Leak-fixed engine.

Do **not** rerun the 100-grid, giveback, launch-catch, volfirst-as-hero, 08:00 buy-the-open, vs_iwm, climax.

## Kernel (do not drop)

Closest object: `flush|flat1159|px5` develop **−$6** / holdout **+$146** (hit 63%, PF 3.8, n_hold=27). Harness control was −$20 / +$142. Develop is still red — not a pass, not EV.

**Entry (flush):** 08:00 hot as Arrow 22/23 (ext_0800 in [2%, 10), pre_dv_0800 ≥ $400k, rel_0800 ≥ 3). After 09:30, price undercuts 08:00 last_px by ≥ 2%, then a 5-min bar makes a higher low than the prior 5-min and strong-closes (close_loc ≥ 0.75). Stop = flush low, ATR-floored.

**FLY cell (develop-locked, apply unless an id drops it):** 09:30–09:44 OR width ≥ 5.1%, pre_dv_0929 ≥ $98k, ext_0944 ≥ 3.4%.

**Default book:** prior_close **[$5, $20]**, cap8, flatten **11:59**, cost gate on.

## Ten longs (side = +1 only)

| id | ring |
|---|---|
| 1 | **control** — kernel + cell + px5 + cap8 + flat 11:59 |
| 2 | control, **cap3** |
| 3 | control, flatten **15:59** |
| 4 | control, **half at +1R**, stop to entry, ATR trail remainder, flatten 15:59 |
| 5 | control, undercut must be ≥ **3%** (deeper flush) |
| 6 | control, undercut **≤ 6%** (no waterfall) |
| 7 | control, signal 5-min close_loc ≥ **0.85** and close ≥ 08:00 last_px (full reclaim) |
| 8 | control, first flush **at or after 10:00** |
| 9 | control, `run_rel_vol` at signal ≥ **5** |
| 10 | control **without** the FLY cell (px5 + flush only) — does the cell do work |

No 11th. No shorts. Advanced stats on every id (n, hit, avgR, medR, PF, stop/time %, medMin, $/day, se, t, CI, maxDD, reached_1R, flight mean_ext).

## Outputs

`reports/arrow25_results.txt` — two-sided pass; n vs id 1; which ids beat control on **both** slices; reminder +$146 is not EV.
Append RESEARCH_LOG.md.
Tests: id 6 rejects a 7% undercut; id 7 silent if close never reclaims 08:00 px; id 8 silent on a 09:50-only flush; id 10 may fire when OR width is 3%; longs only.

Commit code + reports. No parquet. No Arrow 26.
