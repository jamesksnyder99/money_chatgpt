# Full-tape contract (Arrow 17) — additive, does not replace v1

Lab A (`data/bars`, 07:30–12:00, prior close $1–$30) is unchanged. This tree is a second corpus.

| Item | Value |
|---|---|
| Window | `04:00:00` inclusive through `16:00:00` exclusive; last 1m bar starts `15:59` |
| Venue | `utp_cta` |
| Grain | 1-minute SIP OHLC, unadjusted |
| Eligibility | common stock + existing ETP denylist; prior close **[$1, $50]**; prior-day dollar volume ≥ $1M |
| Caps | none on the raw tape (Track A/B stay downstream) |
| Calendar | same warmup (10 sessions before 2026-06-01) + study 2026-06-01..2026-08-31; Jul 3 closed |

Paths (gitignored parquet):

- `data/full/bars/YYYY-MM-DD/{safe_symbol}.parquet`
- `data/full/eligibility.parquet`
- `data/full/manifest.parquet` (`pulled` / `empty` / `missing`)

Each bar has `session_part`: `pre` if `bar_start < 09:30`, else `rth` (including 12:00–15:59).
