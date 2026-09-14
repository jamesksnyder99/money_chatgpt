"""Calendar-month account reporting — the frozen lab standard.

Any research arrow that publishes strategy economics and has a daily marked-account path
must also publish calendar-month account reporting built with this helper. The standard set
is fixed:

  * every calendar month of the reported period, individually, with none collapsed or skipped;
  * principal strategies or variants side by side;
  * monthly marked-account P&L in dollars;
  * monthly return percent, on the prior month-end marked equity;
  * month-end marked equity;
  * positive and red month counts;
  * worst month and median month;
  * exact reconciliation to the marked account result for the same calendar period;
  * explicit treatment of positions still open at the period end.

Two rules make the numbers mean what they say:

1. Monthly P&L comes from the **daily marked-account path**, never from grouping completed
   trades by exit month. A trade that opens in one month and closes in another contributes
   to both, which is what an account statement shows.
2. The twelve calendar months reconcile to the **marked account result at the period end**,
   not to eventual completed-trade P&L, because eventual P&L includes exits scheduled after
   the period closes. Those are reported separately as runoff.

This is a reporting standard, not an optimization dimension. Monthly outcomes must never be
used to select or alter a strategy.
"""
from __future__ import annotations

from collections import OrderedDict
import statistics

STANDARD_ID = "cg_lab_monthly_account_reporting_v1"
STARTING_EQUITY = 100000.0
TOL = 1e-6
REQUIRED_FIELDS = ("month", "strategy", "legacy_id", "replay", "horizon", "monthly_pnl",
                   "monthly_return_pct", "month_end_equity", "prior_month_end_equity")


def monthly_account(daily_rows, starting_equity: float = STARTING_EQUITY) -> list[dict]:
    """Calendar-month account rows from a daily marked-account path.

    daily_rows: an iterable of mappings with a 'date' (ISO) and an 'equity' value, in
    session order. Months are taken from the dates present, so an empty month inside the
    period still appears with zero P&L as long as the path covers its sessions.
    """
    by_month: "OrderedDict[str, float]" = OrderedDict()
    for r in daily_rows:
        by_month[str(r["date"])[:7]] = float(r["equity"])
    out, prior = [], float(starting_equity)
    for month, end_equity in by_month.items():
        pnl = end_equity - prior
        out.append({"month": month, "monthly_pnl": pnl,
                    "monthly_return_pct": (pnl / prior * 100.0) if prior else None,
                    "month_end_equity": end_equity, "prior_month_end_equity": prior})
        prior = end_equity
    return out


def summarize(rows: list[dict]) -> dict:
    pnl = [r["monthly_pnl"] for r in rows]
    reds = [x for x in pnl if x < 0]
    return {"months": len(rows),
            "positive_months": sum(1 for x in pnl if x > 0),
            "red_months": len(reds), "flat_months": sum(1 for x in pnl if x == 0),
            "red_month_loss_sum": sum(reds),
            "worst_month": min(pnl) if pnl else None,
            "best_month": max(pnl) if pnl else None,
            "median_month": statistics.median(pnl) if pnl else None,
            "total_monthly_pnl": sum(pnl)}


def reconcile(rows: list[dict], expected_period_marked_pnl: float,
              starting_equity: float = STARTING_EQUITY) -> dict:
    """Assert the month table against the marked account result for the same period."""
    total = sum(r["monthly_pnl"] for r in rows)
    chain_ok = True
    prior = float(starting_equity)
    for r in rows:
        chain_ok = chain_ok and abs(r["prior_month_end_equity"] - prior) < TOL
        chain_ok = chain_ok and abs(r["month_end_equity"] - (prior + r["monthly_pnl"])) < TOL
        prior = r["month_end_equity"]
    checks = {
        "monthly_pnl_sums_to_period_marked_pnl": abs(total - expected_period_marked_pnl) < TOL,
        "month_end_equity_chains": chain_ok,
        "first_month_starts_from_starting_equity":
            bool(rows) and abs(rows[0]["prior_month_end_equity"] - starting_equity) < TOL,
        "last_month_end_equity_matches":
            bool(rows) and abs(rows[-1]["month_end_equity"]
                               - (starting_equity + expected_period_marked_pnl)) < TOL,
        "return_denominator_is_prior_month_end_equity": all(
            r["monthly_return_pct"] is None
            or abs(r["monthly_return_pct"] - r["monthly_pnl"] / r["prior_month_end_equity"] * 100.0) < TOL
            for r in rows),
    }
    return {"standard": STANDARD_ID, "total_monthly_pnl": total,
            "expected_period_marked_pnl": expected_period_marked_pnl,
            "difference": total - expected_period_marked_pnl,
            "checks": checks, "reconciles": all(checks.values())}


def side_by_side(books: dict) -> list[dict]:
    """books: label -> month rows. Returns one row per month with a column per label."""
    months = []
    for rows in books.values():
        for r in rows:
            if r["month"] not in months:
                months.append(r["month"])
    out = []
    for m in months:
        row = {"month": m}
        for label, rows in books.items():
            hit = next((r for r in rows if r["month"] == m), None)
            row[label] = hit["monthly_pnl"] if hit else None
            row[label + " %"] = hit["monthly_return_pct"] if hit else None
        out.append(row)
    return out


def missing_standard_fields(rows: list[dict]) -> list[str]:
    """Which required fields a published monthly table is missing."""
    if not rows:
        return list(REQUIRED_FIELDS)
    return [f for f in REQUIRED_FIELDS if f not in rows[0]]
