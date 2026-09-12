# Build Arrow 63 — SEC SIC map into `data/meta/` (ingest)

Read `docs/DATA_CONTRACT.md`, `docs/SUCCESS.md`, `AGENTS.md`,
`docs/BUILD_ARROW_62.md`.

This arrow is **ingest only**. Do not score engines. Do not tune.
Do not touch `data/full/`, `data/virgin/` bars, or Lab A `data/bars/`.

Hotel 6 needs a frozen peer map. Source is official SEC EDGAR, not a
paid EDGAR wrapper, not GICS, not Yahoo.

## Source

1. `https://www.sec.gov/files/company_tickers.json`
   (fallback `https://www.sec.gov/files/company_tickers_exchange.json`)
   ticker → CIK.
2. For each CIK: `https://data.sec.gov/submissions/CIK{cik10}.json`
   fields `sic` and `sicDescription`.

HTTP `User-Agent` must be a real contact, e.g.
`ProjectMoney research jks.michigan@gmail.com`. SEC will 403 a blank or
python-default agent.
One submissions request at a time. Sleep ≥ 0.2s between CIKs. Retry 429/503
with backoff. Do not parallel-hammer EDGAR.

Scope: tickers that appear in `data/virgin/` or `data/full/` eligibility
(unique symbols on disk). Do not scrape the entire SEC registrant universe.

## Store

`data/meta/sector_sic.parquet` (gitignore, same as other parquet).
Columns: `symbol, cik, sic4, sic2, sic_name, asof`.
`sic2` = first two digits of `sic4` (zero-pad sic4 to 4).
`asof` = UTC date of the pull. Freeze it. Do not refresh mid-study later.
Also write `data/meta/sector_sic.csv` if that helps a human glance; still
gitignore if it is large. Do not commit the data file.

## Report

`reports/tape63_sic.txt`.

Symbols on disk, symbols mapped, symbols with no CIK, symbols with CIK but
no SIC, unique sic2 buckets, median names per sic2 among mapped symbols,
HTTP failures, wall time.
State that B pulled SEC directly and did not use a paid EDGAR wrapper.

Append RESEARCH_LOG.md.

Tests:
- User-Agent header is set (unit);
- sic2 is the first two digits of sic4 (unit);
- do not write Lab A `data/bars/` or rebuild tape;
- do not score a book.

Commit code + report. No parquet. No Arrow 64 (64 is the group-leftover book).
