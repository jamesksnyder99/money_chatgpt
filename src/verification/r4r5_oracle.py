"""Independent calculator for Arrow 005 ledgers.

Reads the finalized trade CSV and the source summaries directly; it never calls the
replay engine's PnL or selection helpers. It re-derives per-trade PnL from the
recorded price/quantity fields, cohort subtotals, and a daily cash-minus-liability
account, then compares against the exported daily account at full precision.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from datetime import date
import math
from pathlib import Path

from verification.r4r5_data import SCORE, adjustment_factor, present

TOL = 1e-6


def fee(px: float) -> float:
    return 0.005 + max(0.01, 0.001 * px)


def _num(x):
    return None if x in ("", None) else float(x)


def read_csv(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def verify_trades(rows: list[dict]) -> dict:
    """Per-trade arithmetic from price/quantity fields; returns counts and max error."""
    errors = 0
    max_err = 0.0
    checked = 0
    for r in rows:
        if r["status"] not in ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT"):
            if _num(r.get("modeled_net")) is not None or _num(r.get("gross_pnl")) is not None:
                raise AssertionError(f"Unverified row carries a net total: {r['ticket_id']}")
            continue
        q = _num(r["quantity"])
        f = _num(r["action_factor_over_hold"]) or 1.0
        qe = q / f
        ent = _num(r["entry_price"]) * f
        ext = _num(r["exit_price"])
        gross = qe * (ent - ext)
        net = gross - q * fee(_num(r["entry_price"])) - qe * fee(ext)
        err = max(abs(gross - _num(r["gross_pnl"])), abs(net - _num(r["modeled_net"])))
        max_err = max(max_err, err)
        errors += err > TOL
        checked += 1
        if abs(qe - _num(r["quantity_at_exit"])) > TOL:
            errors += 1
    return {"checked": checked, "errors": errors, "max_abs_error": max_err}


def verify_cohorts(trades: list[dict], audit: list[dict]) -> dict:
    by = defaultdict(float)
    counts = defaultdict(int)
    for r in trades:
        key = (r["model"], r["replay_stage"], r["cohort_id"])
        counts[key] += 1
        if r["status"] in ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT"):
            by[key] += _num(r["modeled_net"])
    errors = 0
    seen = 0
    period = defaultdict(float)
    for a in audit:
        key = (a["model"], a["replay_stage"], a["cohort_id"])
        if a["row_type"] == "COHORT_SUBTOTAL":
            seen += 1
            if abs(by[key] - _num(a["modeled_net"])) > TOL or int(a["expected_slots"]) != counts[key]:
                errors += 1
            period[(a["model"], a["replay_stage"])] += _num(a["modeled_net"])
        elif a["row_type"] == "PERIOD_TOTAL":
            if abs(period[(a["model"], a["replay_stage"])] - _num(a["modeled_net"])) > TOL:
                errors += 1
    return {"cohorts": seen, "errors": errors}


def rebuild_account(rows: list[dict], summaries: dict) -> dict:
    """Independent cash-minus-liability path from trade rows plus source marks.

    Returns one entry per scored session with cash, short liability, equity and the open
    ticket count. It never calls the replay engine.
    """
    cash = 100000.0
    active = []
    out = {}
    entries = defaultdict(list)
    for r in rows:
        if _num(r.get("quantity")) and r.get("entry_price") not in ("", None) and r.get("scheduled_exit_date"):
            entries[r["scheduled_entry_date"]].append(r)
    for d in SCORE:
        iso = d.isoformat()
        for r in entries.get(iso, []):
            q, px = _num(r["quantity"]), _num(r["entry_price"])
            cash += q * (px - fee(px))
            active.append([r, q, px, d])
        keep = []
        for p in active:
            r, q, mark, md = p
            f = adjustment_factor(r["symbol"], md, d)
            q, mark = q / f, mark * f
            if r["status"] in ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT") \
                    and (r.get("actual_exit_date") or r["scheduled_exit_date"]) == iso:
                xp = _num(r["exit_price"])
                cash -= q * (xp + fee(xp))
                continue
            s = summaries.get((iso, r["symbol"]))
            if present(s):
                mark, md = s["close"], d
            else:
                md = d
            keep.append([r, q, mark, md])
        active = keep
        liability = sum(q * mark for _, q, mark, _ in active)
        out[iso] = {"cash": cash, "short_liability": liability, "equity": cash - liability,
                    "open_tickets": len(active)}
    return out


def verify_daily(trades: list[dict], daily: list[dict], summaries: dict) -> dict:
    """Rebuild cash minus short liability from trade rows plus source marks."""
    out = {}
    by_book = defaultdict(list)
    for r in trades:
        by_book[(r["model"], r["replay_stage"])].append(r)
    daily_by = defaultdict(dict)
    for r in daily:
        daily_by[(r["model"], r["replay_stage"])][r["date"]] = r
    for key, rows in by_book.items():
        own = rebuild_account(rows, summaries)
        max_err = 0.0
        for iso, mine in own.items():
            ref = daily_by[key].get(iso)
            if ref is None:
                raise AssertionError(f"Missing daily row {key} {iso}")
            err = max(abs(mine["cash"] - _num(ref["cash"])),
                      abs(mine["short_liability"] - _num(ref["short_liability"])),
                      abs(mine["equity"] - _num(ref["equity"])))
            if int(ref["open_tickets"]) != mine["open_tickets"]:
                err = max(err, 1.0)
            max_err = max(max_err, err)
        out["/".join(key)] = {"max_abs_error": max_err, "ok": max_err <= TOL}
    return out


def verify_equity_sizing(trades: list[dict], summaries: dict, tiers: dict,
                         starting_equity: float = 100000.0) -> dict:
    """Independently re-derive every equity-scaled share count from stored inputs.

    For each cohort in signal order this rebuilds the account from the trades of strictly
    earlier cohorts only, reads marked equity at the close of the signal session, and floors
    the scaled tier notional against the stored causal pre-order price. It consults neither
    the sizing engine nor the scale factors that engine recorded, so a wrong reference
    equity, a look-ahead, a wrong tier notional or a wrong integer rule all surface here.
    """
    by_cohort = defaultdict(list)
    for r in trades:
        by_cohort[r["cohort_id"]].append(r)
    checked = errors = 0
    max_qty_err = 0.0
    max_scale_err = 0.0
    failures = []
    for cohort_id in sorted(by_cohort):
        earlier = [r for r in trades if r["cohort_id"] < cohort_id]
        path = rebuild_account(earlier, summaries)
        equity = starting_equity
        for iso in sorted(path):
            if iso > cohort_id:
                break
            equity = path[iso]["equity"]
        scale = equity / starting_equity
        for r in by_cohort[cohort_id]:
            stored_scale = _num(r.get("sizing_scale_factor"))
            if stored_scale is not None:
                max_scale_err = max(max_scale_err, abs(stored_scale - scale))
                if abs(stored_scale - scale) > 1e-9:
                    errors += 1
                    failures.append(f"{r['ticket_id']} scale {stored_scale} vs {scale}")
            stored_ref = _num(r.get("equity_reference"))
            if stored_ref is not None and abs(stored_ref - equity) > 1e-6:
                errors += 1
                failures.append(f"{r['ticket_id']} reference equity {stored_ref} vs {equity}")
            pre = _num(r.get("preorder_price"))
            q = _num(r.get("quantity"))
            if not pre or q is None:
                continue
            tier = tiers.get(r["size_tier"])
            if tier is None:
                continue
            expect = math.floor(tier * scale / pre)
            checked += 1
            max_qty_err = max(max_qty_err, abs(expect - q))
            if abs(expect - q) > 0:
                errors += 1
                failures.append(f"{r['ticket_id']} shares {q} vs {expect}")
    return {"cohorts": len(by_cohort), "tickets_checked": checked, "errors": errors,
            "max_share_error": max_qty_err, "max_scale_error": max_scale_err,
            "failures": failures[:10], "ok": errors == 0}


def run(root: Path, summaries: dict) -> dict:
    trades = read_csv(root / "r4r5_verified_trades.csv")
    audit = read_csv(root / "r4r5_verified_cohort_audit.csv")
    daily = read_csv(root / "r4r5_daily_account.csv")
    result = {"trades": verify_trades(trades), "cohorts": verify_cohorts(trades, audit), "daily": verify_daily(trades, daily, summaries)}
    result["ok"] = result["trades"]["errors"] == 0 and result["cohorts"]["errors"] == 0 and all(v["ok"] for v in result["daily"].values())
    return result
