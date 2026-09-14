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
        if r["status"] != "VERIFIED_PRICE_LOCAL_SINGLE_SOURCE":
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
        if r["status"] == "VERIFIED_PRICE_LOCAL_SINGLE_SOURCE":
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
        cash = 100000.0
        active = []
        max_err = 0.0
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
                if r["status"] == "VERIFIED_PRICE_LOCAL_SINGLE_SOURCE" and r["scheduled_exit_date"] == iso:
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
            ref = daily_by[key].get(iso)
            if ref is None:
                raise AssertionError(f"Missing daily row {key} {iso}")
            err = max(abs(cash - _num(ref["cash"])), abs(liability - _num(ref["short_liability"])), abs(cash - liability - _num(ref["equity"])))
            if int(ref["open_tickets"]) != len(active):
                err = max(err, 1.0)
            max_err = max(max_err, err)
        out["/".join(key)] = {"max_abs_error": max_err, "ok": max_err <= TOL}
    return out


def run(root: Path, summaries: dict) -> dict:
    trades = read_csv(root / "r4r5_verified_trades.csv")
    audit = read_csv(root / "r4r5_verified_cohort_audit.csv")
    daily = read_csv(root / "r4r5_daily_account.csv")
    result = {"trades": verify_trades(trades), "cohorts": verify_cohorts(trades, audit), "daily": verify_daily(trades, daily, summaries)}
    result["ok"] = result["trades"]["errors"] == 0 and result["cohorts"]["errors"] == 0 and all(v["ok"] for v in result["daily"].values())
    return result
