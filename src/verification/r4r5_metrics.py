"""Account path metrics for sizing comparison.

Everything here reads the daily marked-account path and the completed trades of one book.
Ratios that divide exposure by equity use the **same session's** marked equity, because the
point of an equity-responsive rule is whether leverage stays put while dollars grow; a ratio
against fixed starting equity would hide exactly that.

Drawdown is measured on marked equity against its own running peak, so a percentage
drawdown is stated against the peak that preceded it rather than against starting equity.
"""
from __future__ import annotations

import statistics

from verification.r4r5_replay import COMPLETED

STARTING_EQUITY = 100000.0


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def drawdown(daily: list[dict], starting_equity: float = STARTING_EQUITY) -> dict:
    """Worst peak-to-trough decline in marked equity, in dollars and against its own peak."""
    peak = starting_equity
    worst_dollars, worst_pct, worst_date, peak_at_worst = 0.0, 0.0, None, peak
    underwater = 0
    for row in daily:
        equity = row["equity"]
        peak = max(peak, equity)
        gap = equity - peak
        if gap < worst_dollars:
            worst_dollars, worst_date, peak_at_worst = gap, row["date"], peak
            worst_pct = gap / peak if peak else 0.0
        if equity < peak:
            underwater += 1
    return {"max_drawdown_dollars": worst_dollars,
            "max_drawdown_pct_of_peak": worst_pct * 100.0,
            "max_drawdown_date": worst_date,
            "peak_equity_before_max_drawdown": peak_at_worst,
            "sessions_underwater": underwater,
            "time_underwater_pct": (underwater / len(daily) * 100.0) if daily else None}


def daily_changes(daily: list[dict], starting_equity: float = STARTING_EQUITY) -> list[float]:
    out, prior = [], starting_equity
    for row in daily:
        out.append(row["equity"] - prior)
        prior = row["equity"]
    return out


def exposure(daily: list[dict]) -> dict:
    """Gross short exposure in dollars and against the same session's marked equity."""
    gross = [row["gross_exposure"] for row in daily]
    ratios = [row["gross_exposure"] / row["equity"] for row in daily if row["equity"] > 0]
    dollar_days = sum(gross)  # one session of gross exposure per row
    return {"mean_gross_exposure": (sum(gross) / len(gross)) if gross else None,
            "peak_gross_exposure": max(gross) if gross else None,
            "mean_gross_over_marked_equity": (sum(ratios) / len(ratios)) if ratios else None,
            "p95_gross_over_marked_equity": _percentile(ratios, 0.95),
            "peak_gross_over_marked_equity": max(ratios) if ratios else None,
            "exposure_dollar_sessions": dollar_days,
            "gross_ratio_basis": "gross short exposure divided by the same session's marked "
                                 "account equity, not by starting equity"}


def trade_stats(trades: list[dict]) -> dict:
    done = [t for t in trades if t["status"] in COMPLETED]
    wins = [t["modeled_net"] for t in done if t["modeled_net"] > 0]
    losses = [t["modeled_net"] for t in done if t["modeled_net"] < 0]
    entry_notional = sum(t["quantity"] * t["entry_price"] for t in trades
                         if t.get("quantity") and t.get("entry_price"))
    return {"completed_trades": len(done),
            "intended_tickets": len(trades),
            "hit_rate": (len(wins) / len(done)) if done else None,
            "avg_winner": (sum(wins) / len(wins)) if wins else None,
            "avg_loser": (sum(losses) / len(losses)) if losses else None,
            "profit_factor": (sum(wins) / -sum(losses)) if losses else None,
            "turnover_entry_notional": entry_notional,
            "avg_entry_notional_per_ticket": (entry_notional / len(done)) if done else None}


def month_stats(daily: list[dict], starting_equity: float = STARTING_EQUITY) -> dict:
    by, prior = {}, starting_equity
    for row in daily:
        by[row["date"][:7]] = by.get(row["date"][:7], 0.0) + (row["equity"] - prior)
        prior = row["equity"]
    values = list(by.values())
    reds = [v for v in values if v < 0]
    return {"months": len(values),
            "positive_months": sum(1 for v in values if v > 0),
            "red_months": len(reds),
            "sum_of_red_months": sum(reds),
            "worst_month": min(values) if values else None,
            "best_month": max(values) if values else None,
            "median_month": statistics.median(values) if values else None}


def headline(book: dict, account: dict, starting_equity: float = STARTING_EQUITY) -> dict:
    """The full headline metric set for one book, combining path, trade and account views."""
    daily = book["daily"]
    changes = daily_changes(daily, starting_equity)
    ending = daily[-1]["equity"] if daily else starting_equity
    out = {"starting_equity": starting_equity,
           "ending_marked_equity_at_cutoff": ending,
           "marked_account_pnl_at_cutoff": account["B_marked_account_pnl_at_cutoff"],
           "eventual_completed_trade_pnl": account["A_completed_trade_pnl_all_cohorts"],
           "return_on_starting_equity_pct":
               account["B_marked_account_pnl_at_cutoff"] / starting_equity * 100.0,
           "worst_day": min(changes) if changes else None,
           "best_day": max(changes) if changes else None,
           "account_sessions": len(daily),
           "post_cutoff_incremental_runoff_pnl": account["C_post_cutoff_incremental_runoff_pnl"],
           "eventual_pnl_of_runoff_trades": account["D_eventual_pnl_of_runoff_trades"],
           "runoff_trade_count": account["runoff_trade_count"],
           "open_documented_obligations": account["E_open_documented_obligations"],
           "stale_gross_at_calendar_boundary": account["F_stale_gross_in_calendar_equity"]}
    out.update(trade_stats(book["trades"]))
    out.update(drawdown(daily, starting_equity))
    out.update(exposure(daily))
    out.update(month_stats(daily, starting_equity))
    return out
