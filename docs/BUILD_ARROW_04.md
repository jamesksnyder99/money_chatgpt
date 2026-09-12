# Build Arrow 4 — tighten Lab A + change the field

Read `docs/SUCCESS.md`, `docs/BUILD_ARROW_03.md`, `reports/arrow03_results.txt`, `reports/RESEARCH_LOG.md` first.

Arrow 3 died. Do **not** retry gap-fade `{3,5,8}`, open-drive `{1.5,2.0,3.0}` as a develop grid, or vwap-reclaim `{3,5,8}` on the same ~2,000-name $1–$30 book. Those exact experiments are closed.

Do **both** tracks below. Same harness as Arrow 3 (next-bar open, costs, $200 risk, 5 positions, 10 entries, $1,000 risk cap, zero-volume ≠ trade, 42/22 split, warmup = no PnL). Parallelize. Holdout scored **once** per (track, rule).

## Track A — tighter slice of existing Lab A bars (no new 1m pull)

Filter existing eligibility **in memory**:

- `prior_close >= 10` and `prior_close <= 30`
- `prior_dollar_volume >= 5_000_000`
- still common / not ETP

Use bars already on disk. If a name fails the filter that day, it is not tradable that day.

Report how many names/day survive vs Arrow 3 (~2,020).

## Track B — new field (small ingest, then same harness)

New point-in-time universe for the **same calendar** (warmup + 64 study sessions, same 07:30–12:00, `utp_cta`, 1m):

- primary common, not ETP (existing denylist + regex)
- prior official close in **[$10, $50]**
- prior-day dollar volume **≥ $5,000,000**

Reuse parquet when `(symbol, session)` already exists. Pull only missing EOD months and missing 1m partitions. Windows-safe paths. Resume + heartbeat. Do not pull July 3 or Juneteenth.

If candidate count explodes past ~800 names/day, cap Track B at the **top 400** by prior-day dollar volume that day (point-in-time). Write the cap in the report.

## Rules allowed (only these)

1. **Cash** on each track.
2. **OR break (new).** After 09:45 ET: first 15-min RTH range (09:30–09:44) high/low. First tradeable close **beyond** that range after 09:45, in that direction; stop other side of the range. Exit by 11:59 flatten. No grid (range definition is fixed).
3. **Next-open swing (new, uses this tape as a signal factory).** Signal in 11:30–11:50 RTH only: if session is up (last close vs 09:30 open) ≥ +1.5% with session volume already ≥ that name’s median full-window volume over prior 10 sessions, go long; symmetric short if ≤ −1.5%. Fill next session’s first tradeable RTH open (skip if that day ineligible). Stop = 1.5× overnight gap risk proxied as `max($0.10, 1.0% of entry)`. Flatten at that next morning’s 11:59 if still open. This is the “hold past noon” test **without** afternoon bars. Last study day has no next open — skip.
4. **Open-drive on Track A/B only at Y=2.0** (single frozen value, not a grid; new universe is the new reason). Same definition as Arrow 3.
5. **VWAP reclaim on Track A/B only at min_price=$10** (frozen). Same definition as Arrow 3.

No gap-fade. No ML. No extra indicators. No second grid search.

## Outputs

- `reports/arrow04_results.txt` — lead verdict vs $200 holdout. Table: track × rule × develop $/day × holdout $/day × trades × hit × maxDD.
- Append `reports/RESEARCH_LOG.md`.
- `reports/arrow04_universe.txt` — Track A daily count; Track B funnel + pulls + cap if used.
- Tests: OR-break does not fire before 09:45; swing does not exit same day as signal (except flatten if you never got next open — then no trade).

Commit code + reports. No parquet. No Arrow 5.
