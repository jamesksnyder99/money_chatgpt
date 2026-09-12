# Build Arrow 18 — repairs, then rescore the kernel only

Read `docs/SUCCESS.md`, `src/research/book.py`, `reports/arrow16_results.txt`, `AGENTS.md`.

Not a discovery grid. Fix the engine, put honesty in the reports, rescore **one** book: `B/c5_ema9|cap8` (and Track A same recipe for contrast). Do not rerun 190 (track, id) pairs. No 09:31. No longs. No $179 cited as expected value.

Claude's review is the spec. Agree with it except: holdout avgR on the kernel was ~0.23, not 0.1 — the ceiling note should use both slices.

## 1. Flatten leak (must ship)

`_flatten_open` only closes if the flatten bar is tradeable. A live position on a zero-volume 11:59 bar is dropped with no `Trade`. That is a bug.

Fix: at `flatten_at`, close every open position at the flatten bar's open if tradeable; else the **last tradeable bar at or before flatten_at after entry**; else the last tradeable bar of the session after entry. If none exist, still emit a Trade at entry_px with tag `orphan_flat` (PnL 0 except costs if you charge a round-trip — prefer last tradeable). After the time loop, assert `positions` is empty; any leftover gets the same treatment.

Test: fixture long/short still open at 11:59 with volume 0 on that bar and volume > 0 at 11:58 → one Trade, exit 11:58 (or 11:58 open), not missing.

## 2. SSR + borrow (short only, must ship)

On **short** signals only, before `can_enter`:

- **SSR proxy (Reg SHO 201):** if the name's last tradeable **close at or before signal_ts** is `≤ 0.90 * prior_close`, **reject** the short. (Circuit is −10% from yesterday; we do not model upticks.)
- **Borrow proxy:** if gap `≤ −5%` **and** `prior_dollar_volume < $10M`, reject. Crude. Document it as crude. Do not invent an HTB fee table.

Flags on `replay_session`: `ssr_filter=True`, `borrow_filter=True`. Kernel rescore runs **with both on** and prints a **no-filter** control so we can see the damage.

Tests: prior_close=20, close=17.90 → short rejected; close=18.20 → not rejected by SSR. Gap −6% and DV $8M → borrow reject; DV $20M → not.

## 3. Dispersion (must ship)

Every `summarize` / results line grows: `std_day`, `se_day` (std/sqrt(n_sessions)), `t_stat` (mean_day / se_day), bootstrap 95% CI on $/day (1000 resamples of daily pnl, seed 17). Print them on develop and holdout.

## 4. IWM horse-race (must ship)

IWM is an ETP — not in the stock eligibility list. Pull **only IWM** 1-minute 07:30–11:59 (Lab A window is enough) for warmup+study, `data/full/bench/IWM/` or similar, gitignored. For each kernel Trade, IWM return over the same `[entry_ts, exit_ts]` on IWM's next-open-to-exit-open. `alpha = trade.pnl - side * shares * entry_px * iwm_ret` (same notional, IWM short if we were short). Report kernel $/day and alpha $/day.

If IWM bar missing for a window, drop that trade from the alpha column only and count skips.

## 5. Honesty block in the report header

Write verbatim-ish:

- Holdout has been used to pick rings (or25 → c5_ema9 → cap8). `+$179` is **not** an expected value. It is a contaminated holdout print.
- Arithmetic: $200 risk × avgR × trades/day. Develop avgR ~0.05 and ~5 fills/day ≈ $50. Holdout avgR ~0.23 × ~3.5 ≈ $160. $300/day on this cell needs more R, more fills, or more dollars at risk — not another 5-min pattern.
- SSR/borrow were unmodelled before this arrow.

## 6. What to rescore

Two tracks × two variants = four rows:

| row | track | filters |
|---|---|---|
| 1 | B | kernel, no SSR/borrow (leak-fixed engine only) |
| 2 | B | kernel, SSR + borrow on |
| 3 | A | leak-fixed only |
| 4 | A | SSR + borrow on |

Same 42/22 split, cap8, flatten 11:59. `reports/arrow18_results.txt`. Append RESEARCH_LOG. Update SUCCESS.md with one paragraph: holdout is contaminated; do not cite +$179 as EV.

## Do not

- Rescore Arrow 3–16 grids.
- Touch `data/bars`.
- Pull a new full-market tape.
- Claim the leak-fix "saves" $179.

Commit code + reports + SUCCESS.md paragraph. IWM parquet stays gitignored. No Arrow 19.
