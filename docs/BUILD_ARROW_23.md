# Build Arrow 23 — orthogonal rocket logics; advanced flight stats

Read `reports/arrow22_results.txt`, `reports/arrow19_survey.txt`, `docs/SUCCESS.md`.

Pass = holdout ≥ $200/day **and** develop not red. `data/full/` only. cap8, $200/idea, leak-fixed engine. Do **not** rerun: 09:29/08:00 buy-the-open of an already-extended name, A21 pullback-to-0929/VWAP, strong5, newhigh, fade-the-hot-open.

Those books all lost the same way. This arrow is six **different jobs**. Some are shorts. That is allowed.

## Shared helpers

- Premarket high/low/range: 04:00–09:29 tradeable bars.
- `pre_dv_rel` as in Arrow 20 (04:00–09:29 vs prior 10).
- Candle `close_loc` as in Arrow 15.
- IWM: use `data/full/bench` if present; if IWM is missing for a window, skip that trade in id 5 only and count skips.

## Six experiments

| id | side | job |
|---|---|---|
| 1 | long | **Coil, then break.** prior_close [$1,$20], pre_dv_rel≥3, pre_dv≥$250k, premarket range/mid **< 4%**, ext_0929 in **[−1%, +3%]**. After 09:30, first 1-min close above premarket high. Stop = premarket low. Flatten 11:59 |
| 2 | long | **Afternoon second wind.** 08:00 hot as in Arrow 22 (ext [2%,10), pre_dv_0800≥$400k, rel≥3). Do **not** enter at 08:00. After **12:00**, first 5-min close above the session high made **before 11:00**. Stop = that 5-min low. Flatten 15:59 |
| 3 | short | **Failed rocket.** ext_0929 ≥ 5%, pre_dv_rel≥3, pre_dv≥$250k. After 09:45, first 5-min close below RTH VWAP. Stop = session high at signal. Flatten 11:59 |
| 4 | long | **Flush then higher-low.** 08:00 hot (same as id 2). After 09:30, price undercuts 08:00 last_px by ≥ 2%, then a 5-min bar makes a higher low than the prior 5-min and strong-closes (close_loc≥0.75). Stop = that flush low. Flatten 11:59 |
| 5 | long | **Holds vs IWM.** prior_close [$1,$20], pre_dv_rel≥3, ext_0929 in [0%, 8%]. After 09:45, a 15-min bar closes green while the same 15-min IWM close is red. Enter next open. Stop = that 15-min low. Flatten 11:59 |
| 6 | short | **Climax tape.** prior_close [$1,$20], pre_dv_rel≥3. After 09:45, a 5-min bar with range ≥ 2× median 5-min range of 09:30–09:44 **and** close_loc ≤ 0.25. Short next open. Stop = that 5-min high. Flatten 11:59 |

No 7th.

## Advanced stats (required in the report)

For **each** id × develop and holdout:

- n trades, trades/session, hit rate
- avgR, medianR, p10 R, p90 R
- avg $ win, avg $ loss, profit factor (gross wins / abs gross losses; inf if no losses)
- % stopped vs % time-flatten vs % other
- median minutes in trade
- $/day, std_day, se_day, t_stat, bootstrap 95% CI (seed 17, 1000)
- maxDD $

Plus a short **flight** block per id: mean extension from entry to trade high (long) or trade low (short); fraction that ever reached +1R before exit.

Header: hot-or-coil name-days per session if cheap to count for ids 1–2; otherwise skip.

## Outputs

`reports/arrow23_results.txt` — pass line, then the stat block, then one paragraph: which jobs are a different *shape* of PnL vs 20–22 (not just another −$200/day).

Append RESEARCH_LOG.md.
Tests: id 1 silent if premarket range is 8%; id 2 silent before 12:00; id 3 emits only shorts; id 6 silent if the 5-min close_loc is 0.8.

Commit code + reports. No parquet. No Arrow 24.
