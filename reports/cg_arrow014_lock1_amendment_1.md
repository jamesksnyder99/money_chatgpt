# CG Arrow 014 — LOCK 1 amendment 1: a calendar defect found before any membership was generated

**Status:** the frozen reveal specification is unchanged. Three engine files changed after LOCK 1
was committed. This record says exactly which, exactly why, and proves that neither the frozen
specification nor any historical result moved.

LOCK 1 (`reports/cg_arrow014_reveal_freeze.json`, commit `5b64dc6`) recorded the 18-cell reveal
matrix, the 52-cohort calendar and a SHA-256 of every engine file the reveal would run on. Three
of those hashes no longer match. A lock whose hashes silently drift is not a lock, so the drift is
recorded here rather than absorbed, and the freeze file itself is **not** rewritten.

## What was wrong

`ingest/calendar.py` held the exchange calendar for 2025 and 2026 only. `verification/r4r5_data.py`
takes its session close time and its final regular-hours minute from that module. The pristine
corridor opens on 2024-08-01, so for every 2024 session the execution layer believed the close was
16:00.

Two 2024 sessions close at 13:00:

| session | why it closes early | what it carries in the frozen cohort calendar |
|---|---|---|
| 2024-11-29 | day after Thanksgiving | **entry execution** for the 2024-11-27 cohort; **H10 exit** for the 2024-11-13 cohort |
| 2024-12-24 | Christmas Eve | **signal ranking endpoint** for the 2024-12-25 nominal anchor; **H8 exit** for the 2024-12-11 cohort |

On those sessions the engine would have looked for a 15:59 print that cannot exist. Every name
would have fallen through to the last-regular-hours-print path and been recorded as
`last_regular_hours_print_fallback` — a thin-session execution — when in fact the 12:59 print is
the ordinary final-minute close. That is a misrecorded execution convention on six lifecycle
dates, and it would have propagated into entry prices, exit prices and the execution-quality
evidence in the certification gate.

2025-07-03 is also an early close and was already correct, because 2025 was in the table.

## What changed

| file | change |
|---|---|
| `src/ingest/calendar.py` | added `NYSE_CLOSED_2024` and `NYSE_EARLY_CLOSE_2024` and folded them into the authoritative `NYSE_CLOSED` / `NYSE_EARLY_CLOSE` unions |
| `src/ingest/holdout2024.py` | deleted its private duplicate of those two tables and re-exports the shared ones, so the ingest layer and the execution layer read one calendar |
| `src/verification/r4r5_data.py` | `eod_reference` now searches the holdout end-of-day tree as well as the study tree; records with no minute close now carry `partition_resolved` and `raw_rows` |
| `src/verification/r4r5_holdout.py` | `activate()` exports `CG_ACTION_PATH` so worker processes inherit the corridor's own action table |

The last two are additive evidence, not rule changes. `eod_reference` previously looked only under
`data/virgin/eod`, which holds nothing before August 2025, so the independent end-of-day
cross-reference was silently absent for eleven of the twelve pristine signal months — exactly the
months whose executions most need a second source. The `partition_resolved` / `raw_rows` fields let
the certification gate distinguish a security that was retrieved and did not trade from an
observation that is simply missing, instead of inferring it.

## Proof that nothing frozen moved

- **The frozen cohort calendar is bit-identical.** All 52 rows — nominal anchor, signal date,
  entry date, rollback days, H8/H9/H10 exit dates — compare equal to the list committed in LOCK 1.
- **The corridor is still 292 sessions**, and the account window still 249.
- **The reveal matrix is still the same 18 cells.**
- **No historical result can move.** The 2025-26 study window begins 2025-08-01 and contains no
  2024 date at all, and every added entry is a 2024 date. `tests/test_calendar_2024.py` asserts
  this non-overlap directly.
- **Session membership is unchanged.** `holdout2024.is_session` already excluded the 2024
  closures through its private table; folding the same dates into the shared set leaves the union
  identical.
- The full suite passes: 754 passed, 1 skipped.

## Why this was fixed rather than recorded as a limitation

The lab's standing rule is to correct the measurement rather than the verdict. The alternative —
running the reveal on a calendar known to be wrong for six lifecycle dates and disclosing it — would
have produced numbers that no later reader could separate from the defect. The fix was made before
any membership was generated and before any outcome was calculated, which is the only point at
which it can be made without the choice being informed by what it does to the result.

## What did not change

No signal rule, ranking rule, sizing rule, hold length, cost model, account identity or reveal cell.
No outcome was calculated at any point in this amendment.
