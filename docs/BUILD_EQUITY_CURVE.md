# Sidecar — combined account equity curve

Not an engine arrow. Do not change doors. Do not ingest. Do not start Arrow 41.

Replay only:
- `B|conj|atr1559|lock` at $200/idea (A33 freeze)
- `flush|max6|repaired` at $200/idea (A31 freeze)
Combined daily PnL = sum of the two session totals (missing day = 0).
Start equity = $100,000. End-of-day mark only (the series we already use for daily-close DD). Optional second panel: running drawdown from peak.

Mark the develop/holdout cut **2026-07-31** with a vertical line. Label it stained holdout, not expected value.

Write:
- `reports/equity_combined_200.csv` (date, b_pnl, flush_pnl, combined_pnl, equity)
- `reports/equity_combined_200.png` (equity vs session date)
- three lines in `reports/equity_combined_200.txt`: start, end, min equity, max daily-close DD, develop ending equity, holdout ending equity.

Commit csv + png + txt. No parquet. No Arrow 41 in this commit.
