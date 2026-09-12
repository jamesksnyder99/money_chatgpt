# Build Arrow 17 — contiguous 04:00–16:00 1-minute tape

Read `docs/DATA_CONTRACT.md`, `docs/SUCCESS.md` (do not apply the $200 verdict to this arrow), `AGENTS.md`.

This is **ingest**, not a strategy book. No fills. No Arrow 16 reruns. Do not overwrite the existing 07:30–12:00 parquet. Old arrows must remain reproducible.

James wants one file family B can use for rockets, "already moving," and afternoon follow-through. Paper-Alpaca is **shelved** until later this week.

## Universe

Re-build point-in-time eligibility (do not silently reuse only Track B):

- Common stock, existing ETP denylist.
- Prior official close in **[$1, $50]**.
- Prior-day dollar volume ≥ **$1,000,000**.
- No 50-name cap. No 400-name cap on this raw tape (Track filters stay downstream).
- Sessions: 10 warmup trading days before 2026-06-01, plus study 2026-06-01..2026-08-31. Keep July 3 as the contract already treats it (closed). Use the exchange calendar for any other full close. If a session is an early close, still request 04:00 through that day's last print; do not invent 16:00 bars.

## Bars

- Theta `stock_history_ohlc` interval **1m**, venue as in DATA_CONTRACT (`utp_cta`).
- `start_time=04:00`, `end_time=16:00` ET. Last minute is 15:59.
- Tag each bar `session_part`: `pre` if < 09:30, `rth` if 09:30–15:59.
- Same split-adjust / unadjusted rules as the existing contract. Same reserved-name sanitizer.
- Concurrency **8**, 429 backoff, workers=min(8, cpu), overlapping write, 15-minute heartbeat + ETA.
- Resumable manifests. Soft time budget: print an ETA after the first 5 study sessions and keep going (do not stop for a second arrow unless the process dies).

## Layout (new tree only)

- `data/full/bars/YYYY-MM-DD/{safe_symbol}.parquet`
- `data/full/eligibility.parquet` (one row per name-day: symbol, session_date, prior_close, prior_dollar_volume, eligible flag)
- `data/full/manifest.parquet` (pulled vs missing vs empty)
- `reports/tape17_ingest.txt` — sessions attempted, name-days eligible, 1m rows, wall time, failures, mean bars/name-day, how many name-days have a 04:00 print vs first print after 07:30.

`.gitignore` must already cover `data/`. Do not commit parquet.

## Do not

- Mutate `data/bars` (the 07:30–12:00 corpus).
- Pull ticks.
- Score strategies.
- Call this a $200 pass/fail.

## Tests

- A fixture bar at 04:15 tags `pre`; 09:30 tags `rth`; 12:05 is stored (this tree allows afternoon).
- Safe symbol still maps CON → _CON.
- Resume skips an already-written name-day.

Commit **code +** `reports/tape17_ingest.txt` + any contract snippet you add under `docs/`. No parquet. No Arrow 18.
