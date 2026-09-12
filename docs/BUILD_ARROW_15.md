# Build Arrow 15 — keep the paying short; memory, candles, 1-min tape, non-mirror longs

Read `docs/SUCCESS.md`, `reports/arrow14_results.txt`, `reports/RESEARCH_LOG.md` first.

Pass = holdout ≥ $200/day **and** develop not red. Tracks A and B, 42/22. No 12:00–16:00.

Do **not** throw away the live short. Arrow 14 `B/c5_ema9|cap8` is develop **+$59** / holdout **+$179**. Id 1 is that exact book. Cap8 (8 / 16 / $1600), RISK_PER_IDEA=200, flatten 11:59.

Do not rerun Arrow 13 pullback / VWAP-reclaim / quiet-OR longs. Do not rerun union, 11:30 flatten, Q4, or cap10-as-the-idea.

James: 9/21 is one stack. Memory and candle anatomy are fair tech. The 09:45 gate and the 5-min *decision* bar are conventions, not proven essential to +$179. Fills stay next 1-min open. Decisions should be able to watch the **1-min tape we actually stored**. Longs must be different machines, not a flipped id 1.

Why 09:45 existed: the kernel's **OR-width > 2.5%** is only known when the 09:30–09:44 box is done. Early entries must either drop that gate or use a **running** box from 09:30 to *now*. Do not invent 07:30 entries in this arrow (premarket is a different sport).

## Helpers

- **Memory (5-min, completed only):** last 3 highs/lows/closes; descending last two highs.
- **Candle (signal 5-min *or* 1-min bar):** body, range, close_loc=(close-low)/range, wicks. Weak close: close_loc ≤ 0.25. Strong close: close_loc ≥ 0.75. Hammer-like: lower wick ≥ 2× body and close_loc ≥ 0.6.
- **Anchored VWAP** from 09:30 RTH (typical × volume).
- **Running OR:** from 09:30 through the current bar, width = (run_high-run_low)/mid.

## Twelve experiments

**Short 1–6** — `side = -1` only.

| id | idea |
|---|---|
| 1 | **control** — exact Arrow 14 kernel: ema9 < ema21, first **5-min** close below ema9 after **09:45**. Stop = max(OR high, that 5-min high). cap8 |
| 2 | control entry **plus memory**: last two completed 5-min highs descending |
| 3 | control entry **plus candle**: signal 5-min is a weak close |
| 4 | no 9/21. First **5-min** close below 09:30-AVWAP after 09:45, weak close. Pop = Q5, gap-down ≥ 1.5%, OR > 2.5% |
| 5 | **1-min tape, same pop:** Q5, gap-down ≥ 1.5%, completed OR > 2.5%, ema short. After **09:45**, first **1-min** close below ema9. Stop = max(OR high, that 1-min high). Do not wait for a 5-min close |
| 6 | **1-min tape, early RTH:** Q5, gap-down ≥ 1.5%, ema short. From **09:31**, first **1-min** close below ema9 whose **running** OR width so far > 2.5%. Stop = running high. No 09:45 wait. No completed-box requirement |

**Long 7–12** — `side = +1` only.

| id | idea |
|---|---|
| 7 | Washout hammer (5-min) on gap-down Q5 wide-OR names. Low ≤ OR low, close back inside OR. Stop = hammer low |
| 8 | Hold the open: gap-up ≥ 1.5%, 09:44 close in top half of OR, then first 5-min strong close above OR mid. Stop = OR mid |
| 9 | Memory grind-up: Q5, `|gap| < 1%`, three completed 5-min closes each higher, last bar strong. Stop = low of those three |
| 10 | AVWAP reclaim: Q5 gap-up ≥ 1%, lose 09:30 AVWAP once after 09:45, then a 5-min strong close back above. Stop = that 5-min low |
| 11 | Prior-day morning high: 5-min close above it, body ≥ 0.5× range, strong close. Stop = that 5-min low |
| 12 | **1-min long tape:** Q5, ema9 > ema21. After 09:45 first **1-min** hammer-like bar that tags ema9 and strong-closes. Stop = that 1-min low |

No 13th. Score A and B separately. Header: cap8, id 1 is the preserved kernel, ids 5–6 are the 1-min tape tests.

## Outputs

- `reports/arrow15_results.txt` — two-sided pass; n vs id 1 on shorts; note whether 1-min doors beat the 5-min control on both slices.
- Append `reports/RESEARCH_LOG.md`.
- Tests: weak-close rejects close_loc=0.8; hammer rejects long upper wick; id 5 silent before 09:45; id 6 may signal at 09:32 on a fixture; id 1 still 5-min + ema9 < ema21; longs emit no shorts.

Commit code + reports. No parquet. No Arrow 16.
