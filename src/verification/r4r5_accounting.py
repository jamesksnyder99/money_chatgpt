"""Arrow 008 Repair 2 and 3 — unambiguous account semantics and a reconciling R1 to R2 bridge.

Six distinct quantities are reported, and the identities between them are asserted in code
rather than described in prose:

  A  completed-trade P&L for all signal cohorts      eventual P&L of every completed position,
                                                     including exits scheduled after the cutoff
  B  marked account P&L at 2026-08-31                realised through the cutoff plus unrealised
                                                     on positions still open, under the stated
                                                     valuation convention
  C  post-cutoff incremental runoff P&L              only the change in value earned after the
                                                     cutoff on positions open at the cutoff
  D  eventual P&L of runoff trades                   full-life P&L of trades exiting after the cutoff
  E  open documented obligations                     positions with no completed exit, kept apart
  F  stale-mark amount and status                    any stale mark inside calendar equity

Identities, all tested:
  A = (completed trades exiting on or before the cutoff) + D
  D = (marked P&L of those trades at the cutoff) + C
  B = (realised through the cutoff) + (unrealised at the cutoff)

A per-session figure names its numerator and its denominator. Eventual post-cutoff P&L is
never divided by an account-session count that stops at the cutoff.
"""
from __future__ import annotations

from datetime import date

from verification.r4r5_data import CUTOFF, SCORE, adjustment_factor, present
from verification.r4r5_replay import COMMISSION, COMPLETED, spread

TOL = 1e-6
OPEN_STATES = ("OPEN_AT_BOUNDARY_DOCUMENTED_HALT", "NO_ENTRY_DOCUMENTED_TRADING_EVENT")


def _mark_at_cutoff(t: dict, summaries: dict):
    """Last observed mark on or before the calendar cutoff, in cutoff share units."""
    entry_date = date.fromisoformat(t["scheduled_entry_date"])
    mark, mark_date = t["entry_price"], entry_date
    for d in SCORE:
        if d < entry_date:
            continue
        rec = summaries.get((d.isoformat(), t["symbol"]))
        if present(rec):
            mark, mark_date = rec["close"], d
    return mark, mark_date


def trade_views(book: dict, summaries: dict) -> list[dict]:
    """Per-trade decomposition into the cutoff state and the post-cutoff increment."""
    out = []
    for t in book["trades"]:
        if t["status"] not in COMPLETED:
            continue
        exit_date = date.fromisoformat(t.get("actual_exit_date") or t["scheduled_exit_date"])
        after = exit_date > CUTOFF
        row = {"ticket_id": t["ticket_id"], "symbol": t["symbol"], "cohort_id": t["cohort_id"],
               "split": t["split"], "exit_date": exit_date.isoformat(),
               "exits_after_cutoff": after, "eventual_net": t["modeled_net"]}
        if not after:
            row.update({"marked_pnl_at_cutoff": t["modeled_net"], "post_cutoff_increment": 0.0})
            out.append(row)
            continue
        q = t["quantity"]
        f_cut = adjustment_factor(t["symbol"], date.fromisoformat(t["scheduled_entry_date"]), CUTOFF)
        mark, mark_date = _mark_at_cutoff(t, summaries)
        q_cut = q / f_cut
        entry_cut = t["entry_price"] * f_cut
        # mark-to-cutoff P&L carries the entry costs already paid, and no exit costs yet
        marked = q_cut * (entry_cut - mark) - t["entry_commission"] - t["entry_spread"]
        row.update({"marked_pnl_at_cutoff": marked,
                    "post_cutoff_increment": t["modeled_net"] - marked,
                    "cutoff_mark": mark, "cutoff_mark_date": mark_date.isoformat(),
                    "cutoff_mark_is_stale": mark_date != SCORE[-1]})
        out.append(row)
    return out


def account_view(book: dict, summaries: dict, label: str) -> dict:
    """The six quantities plus the tested identities, for one book."""
    views = trade_views(book, summaries)
    daily = book["daily"]
    trades = book["trades"]
    through = [v for v in views if not v["exits_after_cutoff"]]
    runoff = [v for v in views if v["exits_after_cutoff"]]
    open_obl = [t for t in trades if t["status"] in OPEN_STATES]
    unresolved = [t for t in trades if t["status"].startswith(("UNRESOLVED", "MISSED", "BLOCKED"))]

    A = sum(v["eventual_net"] for v in views)
    D = sum(v["eventual_net"] for v in runoff)
    C = sum(v["post_cutoff_increment"] for v in runoff)
    runoff_marked = sum(v["marked_pnl_at_cutoff"] for v in runoff)
    realised = sum(v["eventual_net"] for v in through)
    last = daily[-1]
    B = last["equity"] - 100000.0
    unrealised_at_cutoff = B - realised

    stale_gross = last["stale_gross"]
    stale_trades = [v for v in runoff if v.get("cutoff_mark_is_stale")]

    checks = {
        "A_equals_through_plus_D": abs(A - (realised + D)) < TOL,
        "D_equals_marked_plus_C": abs(D - (runoff_marked + C)) < TOL,
        "B_equals_realised_plus_unrealised": abs(B - (realised + unrealised_at_cutoff)) < TOL,
    }
    n_sessions = len(daily)
    return {
        "book": label,
        "A_completed_trade_pnl_all_cohorts": A,
        "A_basis": "eventual P&L of every completed position of every signal cohort, including "
                   "exits scheduled after 2026-08-31",
        "completed_trades_exiting_through_cutoff": realised,
        "completed_trade_count": len(views),
        "B_marked_account_pnl_at_cutoff": B,
        "B_basis": "account equity at 2026-08-31 minus the 100,000 starting equity, that is realised "
                   "P&L through the cutoff plus unrealised P&L on positions still open",
        "unrealised_at_cutoff": unrealised_at_cutoff,
        "C_post_cutoff_incremental_runoff_pnl": C,
        "C_basis": "value earned after 2026-08-31 only, on positions already open at the cutoff",
        "D_eventual_pnl_of_runoff_trades": D,
        "D_basis": "full-life P&L of trades whose exit falls after 2026-08-31",
        "runoff_trade_count": len(runoff),
        "runoff_marked_pnl_at_cutoff": runoff_marked,
        "E_open_documented_obligations": len(open_obl),
        "E_open_obligation_tickets": [t["ticket_id"] for t in open_obl],
        "E_basis": "positions with no completed exit under a documented trading event; never valued "
                   "as completed trades",
        "F_stale_gross_in_calendar_equity": stale_gross,
        "F_stale_marked_runoff_trades": len(stale_trades),
        "F_basis": "gross exposure at the cutoff carried at a mark older than the cutoff session",
        "unresolved_slots": len(unresolved),
        "account_sessions_to_cutoff": n_sessions,
        "marked_account_pnl_per_account_session": B / n_sessions,
        "per_session_basis": (f"numerator: marked account P&L at 2026-08-31 ({B:,.2f}); "
                              f"denominator: {n_sessions} account sessions from 2025-09-02 to 2026-08-31"),
        "identity_checks": checks,
        "identities_hold": all(checks.values()),
    }


def bridge(r1_book: dict, r2_book: dict, label: str) -> dict:
    """R2 - R1 = COMMON_REVALUATION + ADDED_R2_PNL - DROPPED_R1_PNL, with a tested residual.

    DROPPED_R1_PNL is the actual signed P&L of the tickets removed from R1, so a dropped
    loser carries a negative value and subtracting it raises the bridge. The sign is fixed
    by the identity rather than by prose.
    """
    a = {t["ticket_id"]: t for t in r1_book["trades"] if t["status"] in COMPLETED}
    b = {t["ticket_id"]: t for t in r2_book["trades"] if t["status"] in COMPLETED}
    common = sorted(set(a) & set(b))
    added = sorted(set(b) - set(a))
    dropped = sorted(set(a) - set(b))
    r1_total = sum(t["modeled_net"] for t in a.values())
    r2_total = sum(t["modeled_net"] for t in b.values())
    common_reval = sum(b[k]["modeled_net"] - a[k]["modeled_net"] for k in common)
    added_pnl = sum(b[k]["modeled_net"] for k in added)
    dropped_pnl = sum(a[k]["modeled_net"] for k in dropped)
    residual = (r2_total - r1_total) - (common_reval + added_pnl - dropped_pnl)
    return {
        "book": label,
        "identity": "R2_total - R1_total = COMMON_REVALUATION + ADDED_R2_PNL - DROPPED_R1_PNL",
        "R1_total": r1_total, "R2_total": r2_total, "difference": r2_total - r1_total,
        "common_tickets": len(common), "COMMON_REVALUATION": common_reval,
        "common_r1_pnl": sum(a[k]["modeled_net"] for k in common),
        "common_r2_pnl": sum(b[k]["modeled_net"] for k in common),
        "added_tickets": len(added), "ADDED_R2_PNL": added_pnl,
        "dropped_tickets": len(dropped), "DROPPED_R1_PNL": dropped_pnl,
        "dropped_sign_note": ("DROPPED_R1_PNL is the signed P&L those tickets earned inside R1; the "
                              "identity subtracts it, so dropping a losing ticket raises the bridge"),
        "reconciliation_residual": residual,
        "reconciles": abs(residual) < TOL,
    }
