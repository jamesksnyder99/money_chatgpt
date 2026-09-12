# Build Arrow 1 — warmup pull + timing estimate

Do **only** this arrow. Do not start June–August study bars. Arrow 2 is a later human prompt.

## Goal

1. Implement the minimum ingest path in this repo to honor `docs/DATA_CONTRACT.md` for the **warmup window only**.
2. Pull real Theta data for the **10 trading sessions** `2026-05-15` … `2026-05-29` excluding `2026-05-25`.
3. Print and write a timing report good enough to estimate the full May-warmup + Jun–Aug job.

## Window (hard bound)

```
2026-05-15, 2026-05-18, 2026-05-19, 2026-05-20, 2026-05-21, 2026-05-22,
2026-05-26, 2026-05-27, 2026-05-28, 2026-05-29
```

Eligibility for session `D` still uses **prior official EOD** (`D-1`), so EOD history must cover **2026-05-14** through **2026-05-28** (prior days for those 10 sessions). Pull that extra EOD; do **not** pull 1m bars for 2026-05-14.

## Must implement

- Reuse `src/theta/client.py`. Never print `.env`.
- CLI that can run this arrow without starting Arrow 2, e.g.
  `python scripts/ingest.py --mode warmup` or equivalent.
- Calendar, eligibility, 1m OHLC (`interval=1m`, `07:30`–`12:00` ET, `venue=utp_cta`), unadjusted.
- Common stock + prior close $1–$30 + prior-day dollar volume ≥ $1M, point-in-time per session.
- Parallel by default: `workers=min(8, cpu_count)`, `theta_concurrency=8`, backoff on 429. Overlap pull and parquet write. Parallelize eligibility and validation.
- Resume-safe parquet under `data/` (gitignored). Manifest `data/manifests/pulls.jsonl`.
- Stdout progress; if wall time &gt; 15 min, heartbeat ≤ 15 min with ETA.
- Soft budgets: do not kill a healthy run. Checkpoint and print resume state if the session is long.

## Must write when the pull finishes

`reports/arrow01_timing.txt` (and stdout) including:

- start/end UTC and ET, wall seconds
- theta_concurrency, workers, machine CPU count
- sessions attempted / ok / fail
- eligible name count **per session** and mean / min / max
- 1m rows written total and per session
- mean seconds per (symbol, session) 1m request (or per batch if you batch)
- failures: symbol, session, error class/message (no secrets)
- **extrapolation (label as estimate):**
  - study sessions ~ Jun 1–Aug 31 2026 trading days (include 2026-07-03)
  - plus these 10 warmup sessions already pulled
  - `est_full_hours = wall_hours * (10 + N_study) / 10` using **this run's mean eligible count**, and a second line that scales by `mean_eligible_study / mean_eligible_warmup` if you cannot observe study eligibility yet — then say you assumed the warmup mean holds
  - list assumptions in plain English

Also write `reports/ingest_latest.txt` for this run.

## Explicitly out of scope

- 1m bars for 2026-06-01 or later
- tick / sub-minute / quotes / options / flat files / streaming
- committing `data/*.parquet` or `.env`
- Arrow 2 full fetch

## Done when

- Warmup 1m + eligibility exist locally and validate against the contract checks that apply to this window.
- Timing report is in `reports/arrow01_timing.txt`.
- Code to resume or rerun `--mode warmup` is in the repo.
- You did not start the study-window bar pull.
