# Build Arrow 16 — optimize the paying short; new doors, same cell

Read `docs/SUCCESS.md`, `reports/arrow15_results.txt`, `reports/rockets_scan.txt`, `reports/RESEARCH_LOG.md` first.

Pass = holdout ≥ $200/day **and** develop not red. Tracks A and B, 42/22. No 12:00–16:00. **Short only.**

## Kernel (do not drop)

Arrow 14/15 `B/c5_ema9|cap8`: develop **+$59** / holdout **+$179**. Pop: `dv_rank ≥ 0.80`, gap-down `≥ 1.5%`, OR width `> 2.5%`, ema9 < ema21. Door: first 5-min close below ema9 after **09:45**. Stop = max(OR high, that 5-min high). cap8, $200/idea, flatten 11:59.

Do **not** rerun: 09:31 early 1-min (red both tracks), Arrow 13/15 longs, Q4, cap10-as-idea, 11:30 flatten, union.

Arrow 15 leftovers worth carrying: **memory** (descending last two 5-min highs) was +$103/+$140. Weak-close faded holdout — do not promote it alone. 1-min after 09:45 ≈ same names as 5-min.

Rocket scan (context only): 47% of $1–$20 3× rockets already +10% before 09:30. This arrow stays on the **B short**. Use that fact as a **filter** (id 8), not as a new long book.

## Ten short-only experiments

Shared pop + cap8 + 09:45 + flatten 11:59 unless noted. Every id `side = -1` only.

| id | idea |
|---|---|
| 1 | **control** — exact kernel |
| 2 | control + **memory** (last two completed 5-min highs descending) |
| 3 | control + **three** consecutive down 5-min closes before the signal bar |
| 4 | control + signal 5-min close is also below **09:30-anchored VWAP** |
| 5 | control + **rel vol ≥ 3×** on this name's 07:30–11:59 volume vs median of prior 10 same-windows (same definition as the rocket scan; skip if <5 priors) |
| 6 | control, but **stop = prior session morning high** from stats if that is **above** the fill and ≥ 0.4% away; else skip |
| 7 | control, first signal **at or after 10:00** (ignore 09:45–09:59 crosses) |
| 8 | control + **not a premarket rocket**: session high from 07:30–09:29 never reached +10% vs prior close |
| 9 | control + signal 5-min **range > prior 5-min range** (expanding bar) |
| 10 | **combine** ids 2 and 4: memory + close below ema9 and below AVWAP |

No 11th. No longs. Report n vs id 1. Call out any id that beats control on **both** slices and any that clears $200 under the pass rule.

## Outputs

- `reports/arrow16_results.txt`
- Append `reports/RESEARCH_LOG.md`
- Tests: id 7 silent on a 09:50-only cross; id 8 rejects a name that printed +10% at 08:10; id 5 silent with only 2 prior windows; shorts only; id 1 still the kernel.

Commit code + reports. No parquet. No Arrow 17.
