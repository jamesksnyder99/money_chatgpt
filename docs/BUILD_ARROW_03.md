# Build Arrow 3 — first research pass (structured, not a buffet)

Read `docs/SUCCESS.md` and `reports/arrow02_*.txt` first.

You do **not** invent a catalog of strategies. You implement a scoring harness and **four pre-specified hypotheses** plus a cash baseline. If none clear the failure line on the holdout, you write that down and stop. Do not add a fifth idea in this arrow.

## Goal

Answer, with costs: on this Lab A tape (commons, $1–$30 prior close, ≥ $1M prior dollar volume, 07:30–12:00 ET, Jun–Aug 2026 + May warmup), can **any** of the four named rules print **≥ $200 net per trading day on average** on the **holdout** weeks? Target remains $300–$500. Below $200 on holdout = fail for that rule.

Account: $100,000. Average = total net PnL / number of **session dates in the evaluation slice** (include flat and losing days).

## Harness (build this first; no edge search until it runs on cash)

- Replay 1m bars from `data/bars/ohlc_1m/` with eligibility from `data/universe/eligibility.parquet`.
- Parallelize by symbol or by date (`workers=min(8, cpu_count)`). Do not serial-scan 2,000 names if a pool can do it.
- **Fills:** enter/exit at **next bar open** after the signal bar close. No same-bar open/high/low fills.
- **Costs (mandatory, pessimistic):** per share `$0.005` commission-like + **1 × spread proxy**. If the bar has no quote, use `max($0.01, 0.10% of price)` each side. Round trip = both sides. Document the formula in the report.
- **Size:** risk **$200 per idea** (0.20% of $100k). Stop distance defines shares = `200 / stop_$`. Cap notional at `min(10% of $100k, 2% of that name's prior-day dollar volume)`. If shares < 1, skip.
- **Book limits:** max **5 concurrent positions**, max **10 entries per session**, max **$1,000** total risk outstanding (5 × $200).
- **Zero-volume minutes are not trades.** Ignore bars with volume==0 or null close.
- **Session:** default research book uses **RTH only (09:30–12:00)** for entries. Premarket bars may be used as **features** (gap vs prior close, pre volume) but not as fills unless the hypothesis says so.
- Warmup (May 15–29) = features / regime only. **No PnL** on warmup.
- **Split (locked):** study sessions in date order, first **42** sessions = develop, last **22** = holdout. Do not peek holdout to choose parameters.
- Parameters: at most a **3-value grid per hypothesis**, frozen before scoring develop. Pick on develop **only** with the costed metric. Then score holdout **once**.

## Four hypotheses (only these)

1. **Cash.** Always flat. $0/day. Sanity check for the harness.
2. **Gap-fade RTH.** Feature from premarket/prior close: overnight return. If gap ≥ +X% at 09:30 and first 5 RTH minutes fail to make a new high, short fade toward prior close or VWAP; stop above the 09:30–09:35 high. Symmetric long on gap-down. Exit by 12:00. X in {3, 5, 8}.
3. **Open-drive continuation.** At 09:35, if first 5 minutes close in the top (bottom) third of that range on volume ≥ Y × median first-5-min volume of prior 10 sessions for that name, go with the drive; stop other side of the 5-min range. Exit by 12:00. Y in {1.5, 2.0, 3.0}.
4. **RTH VWAP reclaim.** After 10:00, first close back above (below) session VWAP after being on the other side for ≥ 3 minutes, in the direction of reclaim; stop 1.5× ATR(20 1m) beyond VWAP. Exit by 12:00. ATR multiple fixed; only optional grid is min price $3 / $5 / $8 to avoid junk.

No other setups. No ML. No indicator soup. No “I also tried MACD.”

## Outputs

- Code under `src/research/` + CLI e.g. `python scripts/research.py --mode arrow3`.
- `reports/arrow03_results.txt` — for each hypothesis: develop $/day, holdout $/day, trade count, hit rate, avg R, max DD $, whether holdout ≥ $200. Lead with a one-line verdict.
- `reports/RESEARCH_LOG.md` — append-only. What was tried, what died, what must not be retried without a new reason.
- Fixture tests for fills (next bar, not same bar) and for “zero-volume bar is not a trade.”

Commit code + reports. No parquet.

## Soft budget

Harness + four rules + holdout report in one pass. If long, heartbeat ≤ 15 min. Do not kill a healthy replay; checkpoint. Do not start Arrow 4.
