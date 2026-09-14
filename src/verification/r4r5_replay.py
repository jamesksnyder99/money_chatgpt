"""Arrow 005 replay engine: fixed-entry short ledgers with explicit statuses.

Entries never depend on future exit availability. Every intended slot is a row.
Exits are scheduled at the Hn final-RTH-minute close (fill = H0); a missing
observation stays UNRESOLVED and is never backdated. Quantities are fixed by the
entry instruction; only documented actions change units. Price PnL is
Q*(entry-exit). Costs are modeled: $0.005/share/side commission plus a
max($0.01, 0.001*price) spread proxy per side; borrow is a scenario on the
preceding marked gross by calendar days. Unknown loans/dividends are null.
"""
from __future__ import annotations

from datetime import date
import math
import re

from research.book import borrow_blocks_short
from verification.r4r5_data import (
    CUTOFF, FEATS, INDEX, LOCAL_TAPE_END, RANKS_PATH, SCORE, adjustment_factor, features, halted, history, observation_status, present, read_json, resolved_symbol, split_of, structural_block,
)

FAMILIES = {"PARENT": 4000.0, "R4": 5150.0, "R5": 8300.0}
COMMISSION = 0.005
SLOTS = 8
VERIFIED = "VERIFIED_PRICE_LOCAL_SINGLE_SOURCE"
CARRIED_STATUS = "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT"
# Both statuses carry a real observed execution price; they are counted together in totals.
COMPLETED = (VERIFIED, CARRIED_STATUS)


def spread(px: float) -> float:
    return max(0.01, 0.001 * px) if math.isfinite(px) and px > 0 else 0.01


def side_cost(px: float) -> float:
    return COMMISSION + spread(px)


def load_field(path=RANKS_PATH, events=None) -> dict:
    """Historical candidate field with the common documented-action repair (Arrow 003 convention)."""
    ranks = read_json(path)
    out = {}
    for iso, rec in ranks.items():
        d = date.fromisoformat(iso)
        back = FEATS[INDEX[d] - 15]
        rows = []
        for h in rec["rows"]:
            f = adjustment_factor(h["symbol"], back, d, events)
            ret = (1 + h["raw_return"]) / f - 1
            rows.append({**h, "raw_return": ret, "documented_rank_factor": f})
        rows.sort(key=lambda h: h["raw_return"], reverse=True)
        out[iso] = {"rows": rows, "n_field": len(rows), "field_ceiling": max(h["prior_close"] for h in rows) if rows else None}
    return dict(sorted(out.items()))


def cohorts(field: dict) -> list[dict]:
    out = []
    for iso, rec in field.items():
        signal = date.fromisoformat(iso)
        fill = FEATS[INDEX[signal] + 1]
        out.append({"signal": signal, "signal_iso": iso, "split": split_of(signal), "fill": fill,
                    "rows": rec["rows"][:SLOTS], "n_field": rec["n_field"], "field_ceiling": rec["field_ceiling"],
                    "ranking_scope": "RANKING_SCOPE_UNVERIFIED_CEILING_50" if rec["field_ceiling"] is not None and rec["field_ceiling"] < 60
                    else "LOCAL_FIELD_CEILING_80_ACTIONS_PARTIAL"})
    return out


def sizing(family: str, f: dict) -> tuple[float, str, float, float]:
    base = FAMILIES[family]
    if family == "PARENT":
        return base, "FULL", 1.0, 1.0
    v = f.get("volume_ratio")
    vm = 0.5 if (v is not None and math.isfinite(v) and v > 1) else 1.0
    if family == "R4":
        return base * vm, "HALF" if vm < 1 else "FULL", vm, 1.0
    r = f.get("ret3")
    mm = 0.5 if (r is not None and math.isfinite(r) and r > 0) else 1.0
    tier = {1.0: "FULL", 0.5: "HALF", 0.25: "QUARTER"}[vm * mm]
    return base * vm * mm, tier, vm, mm


TEST_SYMBOL = re.compile(r"^Z[A-Z]ZZT$")


def identity_status(symbol: str) -> str:
    if TEST_SYMBOL.match(symbol):
        return "TEST_SYMBOL_ID_REVIEW"
    return "INHERITED_ROSTER_UNVERIFIED"


def screen_hold(symbol: str, fill: date, last: date, summaries: dict) -> dict:
    """Largest session-to-session price ratio over [fill-1, last]; a flag, never an inferred split."""
    i = INDEX[fill]
    prev = None
    worst = 1.0
    worst_date = None
    for j in range(i - 1, INDEX[last] + 1):
        d = FEATS[j]
        if d > LOCAL_TAPE_END:
            break
        r = summaries.get((d.isoformat(), symbol))
        if not present(r):
            continue
        if prev is not None:
            for px in (r["open"], r["close"]):
                ratio = px / prev
                if max(ratio, 1 / ratio) > max(worst, 1 / worst):
                    worst, worst_date = ratio, d.isoformat()
        prev = r["close"]
    big = max(worst, 1 / worst)
    flag = "ACTION_OR_ID_REVIEW" if big >= 2.0 else ("LARGE_MOVE_REVIEW" if big >= 1.5 else "NONE")
    return {"max_session_ratio_in_hold": worst, "max_session_ratio_date": worst_date, "discontinuity_flag": flag}


def needs_for(cohort_list: list[dict], hold: int = 10) -> set[tuple[str, str]]:
    """Every observation the ledger requires: features, fill, marks and Hn exits, plus post-due sessions."""
    needs = set()
    for c in cohort_list:
        i = INDEX[c["signal"]]
        for h in c["rows"]:
            for x in FEATS[max(0, i - 22): min(len(FEATS), i + 2 + hold)]:
                needs.add((x.isoformat(), h["symbol"]))
            for x in FEATS[i + 2 + hold:]:
                if x <= LOCAL_TAPE_END:
                    needs.add((x.isoformat(), h["symbol"]))
    return needs


def _base_row(family, stage, c, rank, h, hold, quantity):
    return {"model": family, "replay_stage": stage, "data_version": "r4r5_v1", "quantity_convention": quantity,
            "horizon": hold, "cohort_id": c["signal_iso"], "signal_date": c["signal_iso"], "signal_month": c["signal_iso"][:7],
            "split": c["split"], "rank": rank, "symbol": h["symbol"], "security_id": h["symbol"],
            "prior_close": h["prior_close"], "prior_dollar_volume": h["prior_dv"], "ret15": h["raw_return"],
            "ranking_scope": c["ranking_scope"], "field_size": c["n_field"], "security_identity_status": identity_status(h["symbol"]),
            "lookback_flag": h.get("lookback_flag"), "lookback_max_ratio": h.get("lookback_max_ratio"),
            "lookback_ratio_date": h.get("lookback_ratio_date"),
            "lookback_resolution": h.get("lookback_resolution"),
            "lookback_evidence_classification": h.get("lookback_evidence_classification"),
            "lookback_issuer_filings_searched": h.get("lookback_issuer_filings_searched"),
            "lookback_filings_scanned": h.get("lookback_filings_scanned"),
            "lookback_volume_ratio_at_flag": h.get("lookback_volume_ratio_at_flag"),
            "holding_flag": h.get("holding_flag"), "holding_max_ratio": h.get("holding_max_ratio"),
            "holding_ratio_date": h.get("holding_ratio_date"),
            "holding_resolution": h.get("holding_resolution"),
            "holding_evidence_classification": h.get("holding_evidence_classification"),
            "scheduled_entry_date": c["fill"].isoformat()}


def replay(family: str, cohort_list: list[dict], summaries: dict, *, hold: int = 10, quantity: str = "fill",
           stage: str = "R2", recorded: dict | None = None, scale: dict | None = None,
           allocation: dict | None = None) -> dict:
    """Return {'trades': [...], 'daily': [...]} for one family and horizon.

    `recorded` (stage R1) supplies the frozen Arrow 003 position record per ticket id so
    that recorded features, tickets and quantities are preserved; otherwise features and
    quantities are recomputed from checked inputs.

    `scale` (Arrow 010) maps a cohort's signal ISO date to a sizing multiplier applied to the
    intended ticket notional, and to nothing else. It is the single injection point for
    equity-responsive sizing: the tier, the multipliers, the selection, the entry and exit
    sessions and every observed price are untouched, so a scaled book differs from its
    fixed-dollar control only in share counts and in the amounts that are proportional to
    them. The caller owns causality; see verification.r4r5_equity.

    `allocation` (Arrow 012) maps a ticket id to the base intended notional at 100,000 equity,
    replacing the frozen family rule's own base amount for that ticket and nothing else. It is
    the single injection point for a challenger's relative allocation or substituted lineup:
    the name's own tier, multipliers, entry and exit sessions and observed prices are still
    computed by the unchanged engine, and the recorded tier fields describe the name, not the
    allocation. A ticket absent from the map keeps the frozen rule's amount.
    """
    if quantity not in {"fill", "preorder"}:
        raise ValueError("Unknown quantity convention")
    if scale is not None and recorded is not None:
        raise ValueError("A recorded R1 book has frozen tickets and cannot be equity-scaled")
    trades = []
    for c in cohort_list:
        signal, fill = c["signal"], c["fill"]
        for rank, h in enumerate(c["rows"], 1):
            sym = h["symbol"]
            t = _base_row(family, stage, c, rank, h, hold, quantity)
            tid = f"{c['signal_iso']}/{sym}"
            t["ticket_id"] = tid
            rec = summaries.get((fill.isoformat(), sym))
            f = features(history(sym, FEATS[INDEX[signal] - 20: INDEX[signal] + 1], signal, summaries))
            old = (recorded or {}).get(tid)
            if old is not None:
                f = {"ret3": old["feature"].get("ret3"), "volume_ratio": old["feature"].get("volume_ratio"),
                     "history_sessions": None}
            amount, tier, vm, mm = sizing(family, f)
            if old is not None:
                amount = old["ticket"]
            fixed_amount = amount if allocation is None else float(allocation.get(tid, amount))
            factor = 1.0 if scale is None else float(scale[c["signal_iso"]])
            amount = fixed_amount * factor
            t.update({"ret3": f.get("ret3"), "volume_ratio": f.get("volume_ratio"),
                      "feature_history_sessions": f.get("history_sessions"),
                      "volume_feature_available": f.get("volume_ratio") is not None,
                      "momentum_feature_available": f.get("ret3") is not None,
                      "intended_size_fixed_dollar": fixed_amount, "sizing_scale_factor": factor,
                      "frozen_rule_base_notional": amount if allocation is None else sizing(family, f)[0],
                      "intended_size": amount, "size_tier": tier, "volume_multiplier": vm, "momentum_multiplier": mm,
                      "entry_status": observation_status(fill, sym, rec, need_final_minute=True)})
            if not present(rec) or rec.get("exec_px") is None:
                ev = halted(sym, fill)
                t.update({"status": ("NO_ENTRY_DOCUMENTED_TRADING_EVENT" if ev else
                                     "MISSED_ENTRY_" + t["entry_status"]),
                          "quantity": 0, "gross_pnl": None, "modeled_net": None,
                          "event_treatment": (ev["event"] if ev else None),
                          "event_source": (ev["source"] if ev else None)})
                trades.append(t)
                continue
            blocked = structural_block(sym, fill, rec)
            if blocked:
                t.update({"status": "BLOCKED_STRUCTURAL_ENTRY", "quantity": 0, "gross_pnl": None,
                          "modeled_net": None, "structural_issue": blocked,
                          "verification_status": "BLOCKED_STRUCTURAL",
                          "verification_reason": "entry partition carries an unreviewed structural defect"})
                trades.append(t)
                continue
            px = rec["exec_px"]
            t.update({"entry_ts": rec["exec_ts"], "entry_price_field": rec["exec_field"], "entry_price": px,
                      "entry_source": rec["path"], "preorder_price": rec.get("preorder"), "preorder_ts": rec.get("preorder_ts"),
                      "entry_eod_reference": rec.get("eod_close")})
            gap = px / h["prior_close"] - 1 if h["prior_close"] > 0 else None
            if borrow_blocks_short(gap, h["prior_dv"]):
                t.update({"status": "BLOCKED_INHERITED_BORROW_PROXY", "quantity": 0, "gross_pnl": None, "modeled_net": None})
                trades.append(t)
                continue
            q_fill = math.floor(amount / px)
            q_pre = math.floor(amount / rec["preorder"]) if rec.get("preorder") else None
            qty = q_fill if quantity == "fill" else q_pre
            if old is not None and quantity == "fill":
                qty = old["original_shares"]
            t.update({"quantity_fill_convention": q_fill, "quantity_preorder_convention": q_pre, "quantity": qty})
            if not qty or qty <= 0:
                t.update({"status": "ZERO_SHARE_ORDER", "quantity": 0, "gross_pnl": None, "modeled_net": None})
                trades.append(t)
                continue
            fi = INDEX[fill]
            exit_d = FEATS[fi + hold]
            t["security_identity_status"] = identity_status(sym)
            t.update(screen_hold(sym, fill, min(exit_d, FEATS[min(len(FEATS) - 1, fi + hold)]), summaries))
            xrec = summaries.get((exit_d.isoformat(), sym))
            factor = adjustment_factor(sym, fill, exit_d)
            q_exit = qty / factor
            entry_adj = px * factor
            t.update({"scheduled_exit_date": exit_d.isoformat(), "exit_status": observation_status(exit_d, sym, xrec, need_final_minute=True),
                      "action_factor_over_hold": factor, "quantity_at_exit": q_exit, "entry_price_exit_units": entry_adj,
                      "exit_after_cutoff": exit_d > CUTOFF, "holding_sessions_intended": hold,
                      "holding_calendar_days": (exit_d - fill).days,
                      "entry_commission": qty * COMMISSION, "entry_spread": qty * spread(px),
                      "dividends": None, "dividend_status": "UNKNOWN_NOT_ZERO",
                      "borrow_status": "SCENARIO_ONLY_NO_LOAN_EVIDENCE"})
            # Daily marks over the holding window (fill..exit-1) for borrow base and stale audit.
            borrow_base = 0.0
            stale = 0
            last_mark = px
            last_mark_date = fill
            unit_date = fill
            for j in range(fi, fi + hold):
                d = FEATS[j]
                if d > LOCAL_TAPE_END:
                    break
                r = summaries.get((d.isoformat(), sym))
                last_mark *= adjustment_factor(sym, unit_date, d)
                unit_date = d
                if present(r):
                    last_mark, last_mark_date = r["close"], d
                else:
                    stale += 1
                q_now = qty / adjustment_factor(sym, fill, d)
                borrow_base += q_now * last_mark * (FEATS[j + 1] - d).days / 365
            t.update({"stale_mark_sessions_in_hold": stale, "borrow_base_dollar_years": borrow_base})
            exit_blocked = structural_block(sym, exit_d, xrec) if present(xrec) else None
            if exit_blocked:
                t.update({"status": "BLOCKED_STRUCTURAL_EXIT", "gross_pnl": None, "modeled_net": None,
                          "structural_issue": exit_blocked, "verification_status": "BLOCKED_STRUCTURAL",
                          "verification_reason": "exit partition carries an unreviewed structural defect"})
            elif present(xrec) and xrec.get("exec_px") is not None:
                xp = xrec["exec_px"]
                gross = q_exit * (entry_adj - xp)
                xc = q_exit * COMMISSION
                xs = q_exit * spread(xp)
                net = gross - t["entry_commission"] - t["entry_spread"] - xc - xs
                t.update({"status": VERIFIED, "exit_ts": xrec["exec_ts"], "exit_price_field": xrec["exec_field"],
                          "exit_price": xp, "exit_source": xrec["path"], "exit_reason": "scheduled_backstop",
                          "exit_eod_reference": xrec.get("eod_close"), "exit_commission": xc, "exit_spread": xs,
                          "gross_pnl": gross, "modeled_net": net,
                          "modeled_net_double_spread": net - t["entry_spread"] - xs,
                          "net_borrow_10": net - 0.10 * borrow_base, "net_borrow_30": net - 0.30 * borrow_base,
                          "actual_holding_sessions": hold, "verification_status": VERIFIED,
                          "verification_reason": "entry/exit final-minute closes present in one local vendor partition; no independent second vendor"})
            else:
                delayed = None
                carried = None
                for j in range(fi + hold + 1, len(FEATS)):
                    d = FEATS[j]
                    if d > LOCAL_TAPE_END:
                        break
                    r = summaries.get((d.isoformat(), sym))
                    if present(r):
                        delayed = {"diagnostic_delayed_exit_date": d.isoformat(), "diagnostic_delayed_open": r["open"],
                                   "diagnostic_delayed_ts": r["first_ts"], "diagnostic_delay_sessions": j - (fi + hold)}
                        if r.get("exec_px") is not None:
                            carried = (d, r, j)
                        break
                event = halted(sym, exit_d)
                if event and carried:
                    # Documented non-execution: the resting cover order executes at the first later
                    # session on which the security actually traded, same late-RTH close convention.
                    d, r, j = carried
                    fac2 = adjustment_factor(sym, fill, d)
                    q2 = qty / fac2
                    ent2 = px * fac2
                    xp = r["exec_px"]
                    gross = q2 * (ent2 - xp)
                    xc = q2 * COMMISSION
                    xs = q2 * spread(xp)
                    net = gross - t["entry_commission"] - t["entry_spread"] - xc - xs
                    t.update({"status": CARRIED_STATUS, "exit_ts": r["exec_ts"],
                              "exit_price_field": r["exec_field"], "exit_price": xp,
                              "exit_source": r["path"], "exit_reason": "documented_trading_event_order_carried",
                              "exit_eod_reference": r.get("eod_close"), "exit_commission": xc, "exit_spread": xs,
                              "action_factor_over_hold": fac2, "quantity_at_exit": q2,
                              "entry_price_exit_units": ent2,
                              "gross_pnl": gross, "modeled_net": net,
                              "modeled_net_double_spread": net - t["entry_spread"] - xs,
                              "net_borrow_10": net - 0.10 * borrow_base, "net_borrow_30": net - 0.30 * borrow_base,
                              "actual_holding_sessions": j - fi, "actual_exit_date": d.isoformat(),
                              "event_treatment": event["event"], "event_source": event["source"],
                              "verification_status": CARRIED_STATUS,
                              "verification_reason": "scheduled session had no executable trade under a documented "
                                                     "suspension/halt; the resting order is filled at the first later "
                                                     "session that actually traded"})
                elif event:
                    t.update({"status": "OPEN_AT_BOUNDARY_DOCUMENTED_HALT", "exit_price": None,
                              "exit_reason": "documented_trading_event_no_later_execution_in_window",
                              "gross_pnl": None, "modeled_net": None,
                              "verification_status": "OPEN_DOCUMENTED_EVENT",
                              "verification_reason": "security did not trade again inside the study window under a "
                                                     "documented suspension/halt; the short obligation remains open "
                                                     "and is excluded from completed-trade totals",
                              "event_treatment": event["event"], "event_source": event["source"],
                              "stale_liability_last_mark": last_mark,
                              "stale_liability_last_mark_date": last_mark_date.isoformat(),
                              **(delayed or {})})
                else:
                    t.update({"status": "UNRESOLVED_" + t["exit_status"], "exit_price": None,
                              "exit_reason": "scheduled_exit_not_observed_locally",
                              "gross_pnl": None, "modeled_net": None, "verification_status": "UNRESOLVED",
                              "verification_reason": "scheduled exit observation absent locally; not evidence of a halt; stale liability carried",
                              "stale_liability_last_mark": last_mark, "stale_liability_last_mark_date": last_mark_date.isoformat(),
                              "stale_liability_eod_reference": xrec.get("eod_close") if xrec else None,
                              **(delayed or {})})
            trades.append(t)
    return {"trades": trades, "daily": daily_account(trades, summaries)}


def daily_account(trades: list[dict], summaries: dict) -> list[dict]:
    """Cash-minus-liability account through the cutoff. Stale marks are flagged, never verified."""
    opens = {}
    for t in trades:
        if t.get("quantity") and t["status"] != "ZERO_SHARE_ORDER" and t.get("entry_price") is not None and "scheduled_exit_date" in t:
            opens.setdefault(t["scheduled_entry_date"], []).append(t)
    cash = 100000.0
    realized = costs = 0.0
    active = []
    rows = []
    for i, d in enumerate(SCORE):
        iso = d.isoformat()
        events = []
        for t in opens.get(iso, []):
            q = t["quantity"]
            px = t["entry_price"]
            cash += q * px - t["entry_commission"] - t["entry_spread"]
            costs += t["entry_commission"] + t["entry_spread"]
            active.append({"t": t, "q": q, "mark": px, "mark_date": d, "fresh": True})
            events.append(f"ENTRY {t['symbol']} {q}@{px:.4f}")
        still = []
        for p in active:
            t = p["t"]
            fac = adjustment_factor(t["symbol"], p["mark_date"], d)
            if fac != 1:
                p["q"] /= fac
                p["mark"] *= fac
                events.append(f"ACTION {t['symbol']} factor {fac}")
            close_on = t.get("actual_exit_date") or t.get("scheduled_exit_date")
            if t["status"] in COMPLETED and close_on == iso:
                xp = t["exit_price"]
                cash -= p["q"] * xp + t["exit_commission"] + t["exit_spread"]
                costs += t["exit_commission"] + t["exit_spread"]
                realized += t["modeled_net"]
                events.append(f"EXIT {t['symbol']} {p['q']:g}@{xp:.4f}")
                continue
            r = summaries.get((iso, t["symbol"]))
            if present(r):
                p["mark"], p["fresh"] = r["close"], True
            else:
                p["fresh"] = False
            p["mark_date"] = d
            still.append(p)
        active = still
        fresh = sum(p["q"] * p["mark"] for p in active if p["fresh"])
        stale = sum(p["q"] * p["mark"] for p in active if not p["fresh"])
        overdue = sum(p["q"] * p["mark"] for p in active if p["t"]["scheduled_exit_date"] < iso)
        unrealized = sum(p["q"] * (p["t"]["entry_price"] * adjustment_factor(p["t"]["symbol"], date.fromisoformat(p["t"]["scheduled_entry_date"]), d) - p["mark"]) for p in active)
        liability = fresh + stale
        id_review = sum(p["q"] * p["mark"] for p in active if p["t"].get("security_identity_status") == "TEST_SYMBOL_ID_REVIEW")
        id_review_unreal = sum(p["q"] * (p["t"]["entry_price"] * adjustment_factor(p["t"]["symbol"], date.fromisoformat(p["t"]["scheduled_entry_date"]), d) - p["mark"]) for p in active if p["t"].get("security_identity_status") == "TEST_SYMBOL_ID_REVIEW")
        stale_unreal = sum(p["q"] * (p["t"]["entry_price"] * adjustment_factor(p["t"]["symbol"], date.fromisoformat(p["t"]["scheduled_entry_date"]), d) - p["mark"]) for p in active if not p["fresh"])
        rows.append({"date": iso, "cash": cash, "short_liability": liability, "equity": cash - liability,
                     "equity_convention": "cash minus short liability at last available minute close; stale marks included and flagged",
                     "stale_unrealized_in_equity": stale_unreal, "equity_excluding_stale_unrealized": cash - liability - stale_unreal,
                     "identity_review_gross": id_review, "identity_review_unrealized": id_review_unreal,
                     "equity_excluding_stale_and_identity_review": cash - liability - stale_unreal - (id_review_unreal if id_review_unreal and id_review else 0.0),
                     "realized_modeled_net_cum": realized, "unrealized_price_pnl": unrealized, "model_costs_cum": costs,
                     "gross_exposure": liability, "fresh_gross": fresh, "stale_gross": stale, "overdue_gross": overdue,
                     "open_tickets": len(active), "stale_tickets": sum(not p["fresh"] for p in active),
                     "overdue_tickets": sum(p["t"]["scheduled_exit_date"] < iso for p in active),
                     "borrow_base_day": liability * ((SCORE[i + 1] - d).days if i + 1 < len(SCORE) else 1) / 365,
                     "events": "; ".join(events)})
    return rows
