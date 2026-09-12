# Economic rule

Account context: **$100,000**.

**Goal:** a process that can produce **$300–$500 net per trading day on average** (all sessions in the evaluation window, including flat and losing days). Costs, spread, and realistic fills count.

## Two floors

**Slate floor:** the live set of engines must clear **$200 net per trading day** on average. Below that the shop has failed. Do not dress up a smaller combined expectancy as success.

**Seat floor:** a new engine may join the slate under $200 only if all of the following hold:

- IS (in-sample) is not red
- OOS (out-of-sample) is green
- daily-PnL correlation to the rest of the slate is low
- joint risk fits $100k without two engines spending the same dollar at the same clock

Do not spend another research arrow on a seat under **$100/day**.

R is a diagnostic, not the goal. Size so that a $200–$500 slate day is consistent with risk the account can live with (small R per idea). A 10R day is a tail event to study, not a plan.

## Language

**IS** = in-sample (training). **OOS** = out-of-sample.
For work from Arrow 43 on: odd calendar months are IS (Jan, Mar, May, Jul); even calendar months are OOS (Feb, Apr, Jun, Aug). Split on the entry session.

Stop using develop / holdout as the names for new work. The old Jun–Aug holdout (2026-07-31 through 2026-08-31) was used to pick rings on the B-short cell. That slice is contaminated; do not treat any print from it as expected value (EV).

## Tapes

Evaluation is live-or-next-bar after costs, not an in-sample curve-fit. Lab A is the $1–$30 / 07:30–12:00 common-stock tape. Full tape is `data/full/` 04:00–16:00 (Jun–Aug 2026). Virgin tape is `data/virgin/` 04:00–16:00 (Dec 2025 warmup + Jan–May 2026). New engines from Arrow 43 on use the combined virgin + full calendar unless a brief says otherwise.

SSR (Short Sale Restriction) and borrow were unmodelled before Arrow 18.

**Granularity law:** esteem the finest granularity we have. A higher timeframe is used only when it is superior to read or execute on. The law is not “always one-minute.” Today the finest tape is one-minute; a later 1-second or 10-second tape would inherit the default.
