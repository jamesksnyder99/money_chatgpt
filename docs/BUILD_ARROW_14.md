# Build Arrow 14 — more seats on the paying short; one new door into the same stack

Read `docs/SUCCESS.md`, `reports/arrow13_results.txt`, `reports/RESEARCH_LOG.md` first.

Pass = holdout ≥ $200/day **and** develop not red. Same Tracks A and B, 42/22. No 12:00–16:00. **Short only.** Do not rerun the three Arrow 13 longs, Q4, 5-min ORBR, or 11:30 flatten.

## Kernel

`B/short_gap15|c5_ema9`: develop **+$57/day**, holdout **+$164/day**, 158 / 63 trades. Population: `dv_rank ≥ 0.80`, gap-down `≥ 1.5%`, 15-min OR width `> 2.5%`, `ema15` short-stack. Entry: first completed **5-min close below ema9** after 09:45. Stop = max(OR high, that 5-min high). Flatten 11:59. Book until now: 5 positions / 10 entries / $200 risk / $1,000 risk outstanding.

James: a $100k account can carry more than five names if risk stays small. Stretch capacity **in reason**. Do not go to 20 seats or $500/idea.

## Capacity presets (pass into `replay_session`)

Keep `RISK_PER_IDEA = 200`. Change only seats and outstanding risk.

| label | max_positions | max_entries | max_risk_outstanding |
|---|---:|---:|---:|
| cap5 | 5 | 10 | 1000 |
| cap8 | 8 | 16 | 1600 |
| cap10 | 10 | 20 | 2000 |

## Six short-only experiments

| id | population + entry | book | manage |
|---|---|---|---|
| 1 | exact kernel | **cap5** (control) | 11:59 |
| 2 | exact kernel | **cap8** | 11:59 |
| 3 | exact kernel | **cap10** | 11:59 |
| 4 | exact kernel | cap8 | **2R** |
| 5 | exact kernel | cap8 | **trail** after 1R |
| 6 | same pop, **new door**: after 09:45, first event that is either a 5-min close below ema9 **or** a 1-min close below the 15-min OR low (union). Still short-only. Stop = max(OR high, signal bar high) | cap8 | 11:59 |

Id 6 is the imagination ring: two ways into the same down-stack names, more fills, 8 seats. If it dilutes holdout or turns develop red, log it dead.

`Book.can_enter` must honor the cap passed in (positions, entries, **and** outstanding risk). Report trades/day vs cap5 so we can see whether extra seats actually filled.

## Outputs

- `reports/arrow14_results.txt` — two-sided pass; table track × id; n vs cap5 control; mean concurrent positions.
- Append `reports/RESEARCH_LOG.md`.
- Tests: cap5 never exceeds 5 concurrent; cap8 reaches 6+ on a 10-name fixture; id 6 fires on an OR-low break even if 5-min closes stay above ema9; shorts only.

Commit code + reports. No parquet. No Arrow 15.
