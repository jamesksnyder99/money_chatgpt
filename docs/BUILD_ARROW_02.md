# Build Arrow 2 — optimize universe + study fetch

Do the two optimizations **first**. Only then pull June–August 1m bars. Do not start the study pull until both optimizations are in code, tested, and warmup eligibility is recomputed.

## A. Windows reserved names

Never write a parquet whose file stem is a Windows device name.

Reserved (case-insensitive): `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`.

Map to a safe stem (e.g. `_CON`) in `eod_path` / `bar_path`. Round-trip: the `symbol` column inside the file stays `CON`. Re-pull EOD (and warmup 1m if needed) for `CON` and `PRN` which failed in Arrow 1. Add a unit test that a reserved symbol does not create `CON.parquet`.

## B. Tighten to common stocks — drop ETPs

Ticker regex is not enough (`SPY`, `SOXL`, `TQQQ` all pass).

1. Persist the **raw** `stock_list_symbols` frame (all columns) under `data/ref/` and print columns + value counts of any type/name field.
2. If Theta exposes a security type, use it: keep common / CS / equity; drop ETF, ETN, ETV, ETMF, unit, warrant, preferred, right, when-issued.
3. If Theta only returns `symbol`, ship a checked-in ETP denylist (`src/ingest/etp_tickers.txt`, one ticker per line, uppercase) covering US-listed ETF/ETN/ETV products. Filter after the regex. Keep the list in git (text, not parquet).
4. Report in stdout and `reports/arrow02_universe.txt`:
   - raw list count
   - regex-kept
   - ETP/type-dropped
   - final candidate count
   - warmup eligible mean/min/max **after** the tighter filter (recompute from existing EOD parquet; do not re-pull all EOD except reserved-name retries and any new commons missed before)

Target: eligible/day should fall well below the Arrow 1 ~2,750 if ETPs and non-commons were in that set. If it barely moves, the denylist/type filter is too weak — fix before the study pull.

Zero-volume 1m bars (full 270-minute grid) stay stored but must not be treated as trades in later research. Document that in the report.

## C. Calendar correction (already in Arrow 1 code — keep it)

`2026-07-03` is a **full close** (Independence Day observed). `2026-06-19` is closed. Study sessions = NYSE open days `2026-06-01`…`2026-08-31` only (**64** days). Do not pull 1m for July 3.

## D. Study pull (only after A–C)

Same contract as warmup:

- 1m SIP OHLC, `07:30`–`12:00` ET, `venue=utp_cta`, unadjusted
- Eligibility point-in-time from **prior official EOD** ($1–$30 and ≥ $1M dollar volume)
- EOD for study must cover the prior session for June 1 (2026-05-29) through the prior session for August 31
- Month-chunk Theta history (≤ 1 month per request)
- Parallel: `workers=min(8, cpu_count)`, `theta_concurrency=8`, backoff on 429
- Resume via manifest; skip ok partitions
- Heartbeat ≤ 15 min with ETA if wall > 15 min
- Soft budgets: do not kill; checkpoint

Write 1m under `data/bars/ohlc_1m/` with `is_warmup=false` for study sessions. Do not delete valid warmup bars.

## E. Reports

- `reports/arrow02_universe.txt` — filter funnel + new eligible counts
- `reports/arrow02_timing.txt` — wall time, sessions ok/fail, rows, failures (no secrets), comparison to the 1.54h estimate
- `reports/ingest_latest.txt` — this run

Commit **code + reports + etp ticker text file**. No parquet, no `.env`.

## Out of scope

Tick/sub-minute, quotes, options, flat files, streaming, Arrow 3 research models.
