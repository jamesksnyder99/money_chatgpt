# CG Arrow 014 — LOCK 2 certification gate

**Status: `HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL`**

Corridor `cg_arrow014_pristine_sep2024_aug2025_v1`: 292 exchange sessions from 2024-08-01 to
2025-09-30, twelve pristine out-of-sample signal months from September 2024 through
August 2025, 52 weekly cohorts, cutoff 2025-08-29.

Arrow 013 closed at `HOLDOUT_DATA_PARTIALLY_CERTIFIED`, with its acquisition and source layer
accepted and two blockers open: documented dated corporate actions, and point-in-time security
identity. That status is preserved. This gate records only what Arrow 014 added on top of it, and
it is written by measurement rather than by judgement — every row below is read from the stage
that produced it.

## Gate conditions

| id | requirement | result |
|---|---|---|
| G1 | LOCK 1 is committed and its cohort calendar is unchanged | pass |
| G2 | the reveal matrix is still the frozen 18 cells | pass |
| G3 | Phase 0A source verification reported no blocker | pass |
| G4 | August 2025 was never previously scored as a signal month | pass |
| G5 | every gap-fill partition passes the Arrow 013 partition gate | pass |
| G6 | no ranking-stage observation is still missing | pass |
| G7 | no candidate is unrankable on an unresolved observation | pass |
| G8 | the mechanical membership has reached a fixed point | pass |
| G9 | every screened case that touches a scored cell is resolved from documented evidence | pass |
| G10 | every observation a frozen scored cell depends on was retrieved from the vendor, so nothing is missing data | pass |
| G12 | every retrieved session on which a selected security did not trade is governed by a rule frozen before this corridor was acquired, and is reported rather than filled | pass |
| G11 | no unresolved material exception remains on any scored cell | pass |

## What Arrow 014 did to close the two open blockers

**Documented dated corporate actions.** The whole corridor universe was screened for price level
changes and multi-session trading breaks — 8,024 securities
over 1,922,870 session-to-session observations, restricted to the
sessions each security's own cohorts depend on. This deliberately replaces Arrow 007's top-25
shortlist, which could only see events that inflated a candidate's measured return and was blind
to a forward split that depressed one. That produced 5,599 investigations
across 1,634 securities, every one of which was taken to the
issuer's own SEC EDGAR filings: 1,634 securities scanned,
147 events documented with a filing, a ratio and a dated
effect.

**Point-in-time security identity.** A price-ratio screen cannot see a ticker reassigned between
issuers at a similar price, so every multi-session trading gap inside a lifecycle window was
screened as an identity case in its own right and carried into the same filing census.

## The gap the August 2025 extension exposed

Extending eligibility across August 2025 admitted candidates whose minute bars no source held:
securities the Arrow 013 minute universe never contained, and securities it did contain whose
August sessions were reused from the 2025-26 study tree, which does not carry them. Candidates in
both classes could not be ranked at all.

They were acquired rather than dropped, because a candidate that cannot be ranked might belong in
the top eight and excluding it would be choosing the selection by hand. The gap-fill landed
867,600 rows over 78 vendor requests into
`data/holdout2024/repair/bars`, which resolves **last** in source precedence: it can supply an
observation nothing else has and can never replace one that already exists. Those partitions were
certified under the identical Arrow 013 partition gate
(`REPAIR_PARTITIONS_CERTIFIED`), and the end-of-day cross-check was judged inside the
$10-$80 band the ranking rule reads, against the same measurement taken on the already-certified
bulk landing.

Closing that gap changed the mechanical membership, which is the point: on the unrepaired data the
selection would have been wrong.

## The frozen membership

52 cohorts, 416 selected slots and
624 rank 9-20 control candidates, drawn from a
point-in-time eligible field of 1,082 to
1,387 securities per signal session.
Candidates unrankable on an unresolved observation: 0.
Membership SHA-256 `339c86ca6a4362e3f7c448c49be65427d0be33b9512e071d105847e14bdbf7dc`, reached as a fixed point under the
documented action table `reports/cg_arrow014_corporate_actions.json`.

## Sessions on which a selected security did not trade

Some selected names stop trading inside their own lifecycle. Every such session was retrieved from
the vendor and holds no qualifying regular-hours trade, so this is a fact about the security, not
absent data — `observations_absent` is zero. Two rules frozen long before this corridor was
acquired govern what happens, and both are reported rather than quietly applied:

- **A missing sizing feature.** `r4r5_replay.sizing` treats a missing volume ratio as `vm = 1.0`
  and a missing three-session return as `mm = 1.0`, so the name sizes at its FULL tier. That is
  the frozen rule operating, not a gap being filled.
- **An unfilled entry or an unclosed exit.** Under the Arrow 007 convention a resting order
  executes at the first later session on which the security actually trades; where no such session
  exists inside the corridor the position stays open at the boundary, is excluded from
  completed-trade totals, and appears in the account as an open obligation.

No no-trade session is ever read as a price, a zero, or a halt.

## No outcome has been calculated

Nothing in Arrow 014 up to and including this gate has calculated a return, a hit rate, a drawdown, a monthly figure or an ending equity on the pristine corridor. Memberships were generated only to identify which observations required certification.

---
Generated 2026-09-15T22:24:11+00:00 at `50677a0`.
