# CG Arrow 007 — Winner-Fade Short: certified baseline and completed Hold-Length Ladder

Executor: Opus in Claude Code. Start 2026-09-14 13:44 UTC, allowance 300 minutes. Starting checkpoint `dfcac94`, rebased onto `d55412d`.

Names used throughout, with legacy identifiers in parentheses for code continuity: the strategy family is the **Winner-Fade Short**; its three sizing variants are the **Equal-Dollar Short** (`PARENT`), the **Volume-Sized Short** (`R4`) and the **Momentum+Volume-Sized Short** (`R5`); the two reconstructions are the **Historical-Selection Replay** (`R1`) and the **Corrected-Universe Replay** (`R2`); an n-session hold is written **n-Session Hold** (`Hn`) and the whole comparison is the **Hold-Length Ladder** (`H1–H10`).

## Verdict

| Domain | Status | Evidence |
|---|---|---|
| Weekly calendar rule | **FROZEN AND PROVED NEUTRAL** | Nominal Wednesday signal, rolled backward to the prior session when closed, entry the first session after the signal. 52 weeks, identical signal set, zero rollbacks needed in this sample. |
| Corporate actions and security identity | **CERTIFIED FOR EVERY SELECTED NAME** | 1,017 unique symbol/session cases; 386 securities scanned against their own SEC filings; 32 canonical events, 22 newly primary-verified; 2 identity changes, 1 documented halt, 1 non-comparable reorganisation. |
| Ranking-window integrity | **CLEAN AFTER ADJUSTMENT** | Every selected name's action-adjusted 15-session window is continuous. The 90 remaining discontinuities are documented market moves whose issuer filing record was searched. |
| Fixed-point reranking | **CONVERGED** | Two iterations; the confirmation rerank reproduced the same membership hash and produced no new unresolved event. |
| Structural data acceptance | **ENFORCED** | A partition with duplicate, unordered, inconsistent or negative-volume bars cannot support a verified trade unless explicitly reviewed and accepted. |
| Risk accounting separation | **REPAIRED** | In-sample and out-of-sample drawdown, worst day, exposure and underwater time now come from split-owned books; the all-signal account is a separate view. |
| Audit-file consistency | **REPAIRED** | The exported ledger now carries the same certification state the gate used: zero rows read as unexplained, 321 with a continuous action-adjusted window, 88 documented market moves with the issuer filing-search count attached, 7 with dated screen resolutions. |
| Independent reconciliation | **PASSED** | 4,980 trade rows, 624 cohort subtotals, maximum absolute difference 1.8e-12. |
| Adversarial audit | **11 of 11 PASSED** | Largest winners and losers, sizing tiers, subtotals, equity identity, runoff separation, rank boundary and adjusted ranking returns all rebuilt independently from stored evidence. |
| Baseline release gate | **OPEN** | Every gate condition satisfied. |
| Hold-Length Ladder | **COMPLETE** | 30 in-sample cells scored and frozen, then every out-of-sample cell revealed in one batch, for both quantity panels. |

**The Arrow 006 upside survived certification, slightly reduced.** It is not an artefact of undocumented reverse splits: those have now been found, documented from issuer filings and applied, and the corrected selection still earns far more than the historical one. The reason is different from the one Arrow 006 feared, and is set out in section 5.

## 1. Frozen weekly calendar

Each week has a nominal Wednesday anchor. If that Wednesday is not an exchange session the signal rolls backward one calendar day at a time to the most recent session; the week is never skipped and later weeks never shift. Entry is the first exchange session strictly after the signal, so a normal Wednesday enters Thursday, and a Wednesday holiday would map the signal to Tuesday while entry stays Thursday. Exits are n exchange sessions after the actual fill, and early-close sessions use their own final regular-hours minute.

Proof before scoring: over 2025-09 to 2026-08 the rule derives 52 signal sessions identical to the study's existing set, with zero rollbacks, because no Wednesday in the window is a full closure. Boundary behaviour is exercised on real closures: the 2025-11-26 signal enters 2025-11-28 across Thanksgiving, and the 2025-12-24 early close enters 2025-12-26 across Christmas.

## 2. Corporate-action and identity certification

The Arrow 006 screen at 2x was triage. This census screened at 1.2x across the ranking windows of the top 25 ranked candidates in all 52 cohorts plus every recorded selection window, so smaller quantity-changing events could not hide, then took every case to the issuer.

| Measure | Value |
|---|---:|
| Unique symbol/session cases investigated | 1,017 |
| Securities scanned against their own SEC filings | 386 |
| Cases resolved as a primary-verified corporate action | 22 |
| Cases where filings mention a split that does not explain this session | 166 |
| Cases with no split ratio anywhere in the issuer's filings | 829 |
| Canonical events in the final table | 32 |
| Documented security-identity changes | 2 |
| Documented trading suspensions | 1 |
| Non-comparable reorganisations | 1 |

Primary evidence is the issuer's own SEC filings, fetched from EDGAR and cached. A factor is only ever taken from a filing; the observed discontinuity corroborates it and fixes the first post-event session. Acceptance requires that applying the stated ratio actually flattens the observed jump, so a filing that mentions some other split does not license an adjustment.

Newly verified events include DFNS 1-for-125, WETO 100:1, BYND 1-for-30, AGL 1-for-25, ERNA 1-for-25, ALIT 1:20, TGL 1-for-20, INBS 1-for-10, TLRY 1-for-10, REAX 10-for-1, HPP one-for-seven, MQ 1-for-4 and DD 1-for-3. Three further events were confirmed from exchange and issuer notices where the filing text did not parse: FGL one-for-one-hundred effective 2026-02-10 (Nasdaq alert 2026-78), SMX 4.8828125:1 effective 2026-02-17, and NCI one-for-eight effective 2026-05-19 (Nasdaq alert 2026-331).

Two cases needed judgement rather than a factor:

- **Wolfspeed** emerged from Chapter 11 on 2025-09-29, exchanging roughly one new share for 120 old ones while legacy holders kept only 3–5% of the new equity. Value is not preserved, so no factor converts a pre-event price into post-event units. It is recorded as a non-comparable reorganisation, and any candidate whose ranking window spans it is simply not rankable under the unchanged rule. That is a rule-faithful exclusion, not a deletion.
- **Oak Woods Acquisition** moved 2.7x on contracting volume the session before its Nasdaq delisting hearing. Forty of its own filings, exhibits included, contain no split ratio, so it is recorded as a market and liquidity move with that evidence attached.

No suspicious name was ever swapped for the next cached rank. In every case the evidence was documented, units normalised, and the whole eligible field reranked so the corrected top eight emerged mechanically.

## 3. Fixed-point reranking

Iteration one reranked the complete field under the canonical events and screened every selected name's adjusted ranking and holding window: zero unresolved. The confirmation rerank reproduced membership hash `e51a07d6`, so another complete pass introduces no new unresolved event and no new selected name.

Against the historical selections, the certified selection changes membership in 46 of 52 cohorts, with 86 names added and 86 dropped and no pure order-only changes. The three ranking baselines are published separately in `cg_arrow007_ranking_reconciliation.csv`: the raw cached order before any repair, the recorded historical selection, and the certified selection.

## 4. Certified baseline

All-signal completed trades, 415 of 416 intended slots per family; the single exception is EFTY, under an SEC suspension and Nasdaq halt that never lifted, carried as an open obligation rather than valued at a stale mark.

| Variant | Historical-Selection Replay | Corrected-Universe Replay | Doubled spread | 10% borrow | 30% borrow |
|---|---:|---:|---:|---:|---:|
| Equal-Dollar Short (`PARENT`) | 36,536.55 | **104,938.02** | 101,545.71 | 98,609.59 | 85,952.73 |
| Volume-Sized Short (`R4`) | 56,971.05 | **114,190.85** | 110,924.13 | 108,010.51 | 95,649.82 |
| Momentum+Volume-Sized Short (`R5`) | 65,676.39 | **129,092.60** | 125,796.03 | 122,817.84 | 110,268.34 |

The causal pre-order quantity panel, in which integer shares come only from the last completed bar before the order, gives 104,399.17 / 113,845.29 / 128,864.62. The two panels differ by less than 0.6%, so the historical fill-close sizing convention is not carrying the result.

Split-owned risk, Corrected-Universe Replay, legacy panel:

| Variant | Split | Net | $/session | Hit rate | Profit factor | Max drawdown | Worst day | Peak gross |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Equal-Dollar | in-sample | 41,182.52 | 164.07 | 0.520 | 1.72 | −14,273.28 | −7,135.84 | 95,763 |
| Equal-Dollar | out-of-sample | 63,755.49 | 254.01 | 0.558 | 2.05 | −23,322.81 | −4,871.15 | 104,365 |
| Volume-Sized | in-sample | 47,298.09 | 188.44 | 0.520 | 1.88 | −12,452.01 | −8,912.34 | 95,650 |
| Volume-Sized | out-of-sample | 66,892.76 | 266.51 | 0.558 | 2.16 | −22,110.80 | −5,136.93 | 115,882 |
| Momentum+Volume | in-sample | 58,955.44 | 234.88 | 0.520 | 2.26 | −11,761.01 | −9,719.29 | 97,947 |
| Momentum+Volume | out-of-sample | 70,137.15 | 279.43 | 0.558 | 2.12 | −24,964.89 | −9,202.36 | 121,182 |

Every per-session figure divides by the 251 account sessions of that split-owned book, which is a different basis from the 124/127 signal-session denominators used in earlier arrows. The all-signal account gives 418.08 / 454.94 / 514.31 per session on the same 251-session basis, with mean gross around 65,700 and peak gross 107,497 / 117,762 / 123,913, inside the soft 130,000 planning range. September runoff is reported separately: 7,794.53 / 8,663.17 / 6,250.39, and is not folded into the calendar account ending 2026-08-31.

## 5. Does the Arrow 006 upside survive? Yes, and here is where it comes from

| Variant | Historical | Certified | Change | Names common to both | Names added | Names dropped |
|---|---:|---:|---:|---:|---:|---:|
| Equal-Dollar | 36,536.55 | 104,938.02 | +68,401.46 | 330 tickets, +0.00 | 85 tickets, +65,474.53 | 85 tickets, +2,926.93 removed |
| Volume-Sized | 56,971.05 | 114,190.85 | +57,219.80 | 330 tickets, −9,296.59 | 85 tickets, +69,859.65 | 85 tickets, −3,343.26 removed |
| Momentum+Volume | 65,676.39 | 129,092.60 | +63,416.20 | 330 tickets, −9,022.88 | 85 tickets, +75,365.07 | 85 tickets, −2,925.99 removed |

The uplift is almost entirely the 85 newly selected tickets per variant, not a revaluation of shared trades. For the Equal-Dollar Short the 330 common tickets are literally unchanged, which is the expected result once actions are applied consistently to both reconstructions. For the two sized variants the common tickets are worth about 9,000 less after action normalisation, so the correction moves shared trades slightly against the strategy while the restored candidates more than offset it.

This is a coverage effect, not a split artefact. The historical cache was missing a large part of the rule-eligible field, most visibly the 50–80 dollar band for June to August 2026, and the names it was missing were disproportionately the extreme recent gainers the rule is designed to short. The undocumented reverse splits that Arrow 006 worried about were real and have now been found and applied; where a split inflated a ranking return, the adjusted return is smaller and the name usually falls out of the top eight. That correction is already inside the numbers above.

The concentration is worth stating plainly: the largest single-symbol effects are ASTC (+5,183 to +10,776 depending on variant), STI, UGRO, INBS, DFNS and RGC on the positive side and AGL (−5,245 to −5,452) on the negative side. Removing the Nasdaq test issue ZVZZT from the tradable universe costs the Momentum+Volume variant 5,904, which is a correction, not a loss of edge.

## 6. Hold-Length Ladder

The gate opened, so the ladder ran on the frozen certified entry ledger, cloning the same entries, shares, entry observations and entry costs at every hold length in each quantity panel. The 10-Session Hold reproduces the locked baseline exactly, to 0.0, in all six family and panel combinations.

In-sample, all three variants improve steeply from a 1-session hold to roughly an 8-session hold and then flatten, and the same shape repeats out of sample with the peak one session further out:

| Variant | Best in-sample hold | In-sample net | Best out-of-sample hold | Out-of-sample net | 10-Session Hold out-of-sample |
|---|---|---:|---|---:|---:|
| Equal-Dollar | 8 sessions | 43,411.50 | 9 sessions | 69,928.65 | 63,755.49 |
| Volume-Sized | 8 sessions | 47,470.48 | 9 sessions | 73,936.76 | 66,892.76 |
| Momentum+Volume | 10 sessions | 58,955.44 | 9 sessions | 80,281.65 | 70,137.15 |

The preferred holds were predeclared and committed before any out-of-sample cell was computed: 8, 8 and 10 sessions. **None of them repeated.** The Equal-Dollar preference lost 228.97 against its own 10-Session Hold out of sample, the Volume-Sized preference lost 1,035.55, and the Momentum+Volume preference was the 10-Session Hold itself, so it could not improve on it. The 9-session hold is the out-of-sample peak for all three variants, but that observation arrives after the reveal and is explicitly **not** a confirmed finding; it is recorded so the next arrow can predeclare it honestly rather than discover it twice.

What does repeat is the shape: short holds are clearly worse in both splits, the curve rises into the 8-to-10 session region, and the differences among 8, 9 and 10 sessions are small relative to their drawdowns. Ten correlated hold lengths on one entry ledger are one family, not ten discoveries.

## 7. One reporting defect found and repaired during the audit

The first export carried the raw screen label on 95 selected rows even though the gate had already
classified them, with evidence, as documented market moves. A reader of the private ledger would have
seen `UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY` on trades the run had in fact resolved. The
classification is now written back onto every selected name, so the audit file, the manifest and the
gate agree: 321 rows have a continuous action-adjusted ranking window, 88 are market moves whose
issuer filing record was searched (with the document count on the row), and 7 carry dated screen
resolutions. The frozen entry-ledger hash is unchanged by this repair, so the committed horizon freeze
and the single-batch reveal remain valid.

## 8. What is still not established

- **Borrow, locate and dividend history remain unavailable.** Every net figure is conditional on the inherited modelled commission and spread proxy plus a borrow scenario. At 30% annualised borrow the Momentum+Volume variant still earns 110,268.34, but that is a scenario, not a quoted rate, and none of this is verified executable historical net profit.
- **Single market-data vendor.** SEC filings are a genuinely independent source for events, but prices come from one vendor. A second endpoint of the same vendor is corroboration, not independent validation.
- **An observed bar price is not a guaranteed fill.** The final regular-hours minute close, or that session's last regular-hours print when a thin security did not trade in the final minute, is a simulation reference.
- **The out-of-sample months are reused internal confirmation**, inspected in earlier arrows; they are not pristine validation.
- **166 cases** have issuer filings that mention a split which does not explain the observed session. None of them touches a selected name's certified window, but they are published in the action ledger for review.
- **Cash-in-lieu and broker fractional treatment** after reverse splits remain unknown; theoretical fractional short liabilities are preserved rather than rounded favourably.
