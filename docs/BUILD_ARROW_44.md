# Build Arrow 44 — weekly residual (IS / OOS)

Read `docs/SUCCESS.md`, `AGENTS.md`, `docs/DATA_CONTRACT.md`,
`docs/BUILD_ARROW_43.md`, `reports/arrow43_results.txt`,
`reports/tape17_ingest.txt`, `reports/tape41_ingest.txt`.

One family. One book, two legs scored together and apart.
The object is last week's leftover versus IWM, held a week.

Do not retune Arrow 43 clocks. Do not retune `B|conj|atr1559|lock` or
`flush|max6|repaired`. No FLY cell. No 08:00 hot gate. No conjunction.
No 5-minute pattern. No opening-range filter. No new ingest.
Do not touch Lab A `data/bars/` except to read an existing helper.

Acronyms: IS = in-sample; OOS = out-of-sample; PDV = prior-day dollar
volume; IWM = iShares Russell 2000 ETF; RTH = regular trading hours;
EV = expected value; SSR = Short Sale Restriction.

## Calendar

Reuse `src/research/clock.py`.

- Study: 2026-01-02 … 2026-05-29 from `data/virgin/` plus
  2026-06-01 … 2026-08-31 from `data/full/`.
- IS = odd months of the **entry** session. OOS = even months of the entry.
- Warmup dates: features only. No fills.
- Keep holidays and 2026-07-03 early close. Flatten that week at the last
  tradeable RTH minute of the early-close session if that session is an exit.

## Eligibility (point-in-time, prior session EOD)

Same wall as Arrow 43 so the name set does not drift:
common stock, Arrow 17 ETP denylist, prior close [$10, $80], PDV ≥ $10,000,000.
`data/full/` has no names above $50. Expected. Do not pull them.

## Residual

On each **rebalance session** (last NYSE session of the calendar week;
Friday, or Thursday when Friday is closed):

- Name return = that session's last tradeable RTH close ÷ the last tradeable
  RTH close five sessions earlier − 1. Skip the name if either close is missing.
- IWM return = the same two timestamps on the IWM tape already on disk.
- Residual = name return − IWM return.

Do not use 09:30. Do not use a regression. Subtract IWM. That is the residual.

## Book (frozen — do not search)

Rank eligible names on residual that session.

- Long the **15** worst residuals (`res_long`).
- Short the **15** best residuals (`res_short`).
- Combined book `res_ls` is both legs in the same week.

Fills: buy/sell the last tradeable RTH minute of the rebalance session.
Exit: last tradeable RTH minute five sessions later (the next rebalance
when the calendar is a normal week). Skip a name if either fill bar is missing.

$2,000 notional per name. Existing cost / spread / borrow-proxy model.
SSR at the next open does not block a short already on. No stop.
Do not add a cap beyond 15+15. Do not expand to a full quintile — that
would be hundreds of names and is not a $100k book.

If fewer than 40 eligible names have a residual that week, skip the week.

A week that enters 31 Jul and exits in August is an IS trade (entry month).

## Order of work

1. Character table on **IS rebalance weeks only**, full eligible universe
   (not the 15+15): mean next-week residual of this-week residual top vs
   bottom. Hit rate. By month. Description. Does not pick a book.
2. Then run `res_long`, `res_short`, `res_ls` on IS and OOS. One look on OOS.
   Do not drop a leg after seeing OOS.

Pass for a seat: OOS ≥ $100/day **and** IS not red.
`res_ls` is the seat candidate. The two legs are diagnostics.
Print daily-PnL correlation of the two legs.
Slate $200 is not this arrow's job.

## Report

`reports/arrow44_results.txt`.

For each id × IS × OOS: $/day, n, n/week, hit, PF, se, t, CI,
daily-close DD, worst day, peak/mean concurrent, IWM alpha skip=0, months.
avgR is n/a (no stop).

Honesty: no stop for a five-session hold; 30 names × $2,000 is $60k deployed;
costs on a weekly book are smaller than Arrow 43 overnight but still real.

Append RESEARCH_LOG.md.

Tests:
- warmup dates produce no fills;
- an even-month entry Friday is not in the IS scoreboard;
- residual uses IWM subtracted from the name, not raw name return alone
  (fixture where name and IWM both +10% has residual 0 and is not a tail);
- entry timestamp is last RTH minute, not 09:30;
- July weeks load from `data/full/`, January weeks from `data/virgin/`;
- do not read Lab A `data/bars/`.

Commit code + reports. No parquet. No Arrow 45.
