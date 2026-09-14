"""CG Arrow 011 — D1: mechanical Volume-Sized (R4) to Momentum+Volume-Sized (R5) attribution.

Both books hold the same 416 intended positions with the same entry and exit observations;
they differ only in share count. For one ticket with fill-basis price p, volume multiplier
vm and momentum multiplier mm:

    q4 = floor(5150 * vm / p)            q5 = floor(8300 * vm * mm / p)
    net(q) = q * nps                     nps = modeled net per entry share, common to both

so   R5 - R4 = nps * (q5 - q4)  exactly, and, stated in a declared order,

    BASE_TICKET  = nps * (8300 - 5150) * vm / p          raising the base ticket at R4's multipliers
    MOMENTUM     = nps * 8300 * vm * (mm - 1) / p         applying the momentum halving at the R5 base
    ROUNDING     = (R5 - R4) - BASE_TICKET - MOMENTUM     integer-share residual of both floors

BASE_TICKET and MOMENTUM are the continuous components in that order; they are not independent
causal effects because MOMENTUM is evaluated at the raised base. The identity is exact.

The same per-ticket split applies to every calendar month, because a ticket's marked P&L is
its share count times a common per-share marked path. Monthly rows are built from that path
and must reconcile to the books' daily accounts to 1e-6.

Usage: python scripts/cg_arrow011_bridge.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_accounting as acct  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_metrics as met  # noqa: E402
from verification import r4r5_monthly as mon  # noqa: E402
from verification.r4r5_data import SCORE, VERIFY_ROOT, adjustment_factor, dump_json, present, stamp  # noqa: E402
from verification.r4r5_replay import COMMISSION, COMPLETED, spread  # noqa: E402
from cg_arrow010_run import build_substrate  # noqa: E402

A8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
A10 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow010"
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011"
CACHE = VERIFY_ROOT / "a11"
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
          "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
PANELS = {"LEGACY_FILL_QTY": ("R2_LEGACY_FILL_QTY", "entry_price"),
          "CAUSAL_PREORDER_QTY": ("R2_CAUSAL_PREORDER_QTY", "preorder_price")}
BASE = {"R4": 5150.0, "R5": 8300.0}
BOOK_LABELS = {("R5", "R2_LEGACY_FILL_QTY"): "Momentum+Volume, fixed dollars, legacy fill quantities",
               ("R5", "R2_CAUSAL_PREORDER_QTY"): "Momentum+Volume, fixed dollars, causal pre-order quantities",
               ("R4", "R2_LEGACY_FILL_QTY"): "Volume-Sized, fixed dollars, legacy fill quantities",
               ("R4", "R2_CAUSAL_PREORDER_QTY"): "Volume-Sized, fixed dollars, causal pre-order quantities",
               ("R5", "R5_EQUITY_SCALED"): "Momentum+Volume, equity-scaled, causal pre-order quantities"}
FOOTNOTE = ("Modeled P&L includes the lab's stated commission/spread assumptions; broker-specific locate/HTB charges, "
            "dividends, financing, forced-close effects, taxes and other execution items are excluded. Historical fills "
            "and availability are modeled, not broker execution guarantees.")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg):
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def num(x):
    return None if x in ("", None) else float(x)


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def typed_trade(r):
    t = dict(r)
    for k in ("quantity", "entry_price", "exit_price", "action_factor_over_hold", "gross_pnl", "modeled_net",
              "preorder_price", "volume_multiplier", "momentum_multiplier", "entry_commission", "entry_spread",
              "exit_commission", "exit_spread", "quantity_at_exit", "holding_calendar_days"):
        t[k] = num(r.get(k))
    t["rank"] = int(r["rank"])
    return t


def typed_daily(r):
    d = dict(r)
    for k in ("cash", "short_liability", "equity", "gross_exposure", "stale_gross", "fresh_gross", "overdue_gross"):
        d[k] = num(r.get(k))
    d["open_tickets"] = int(r["open_tickets"])
    return d


def per_share_path(t: dict, summaries: dict) -> dict:
    """Per-entry-share marked P&L at every scored session, under the daily_account conventions.

    Zero before entry; after a completed exit, fixed at the per-share modeled net. Stale marks
    are carried in current units, exactly as the account does.
    """
    entry = t["scheduled_entry_date"]
    p0 = t["entry_price"]
    if not p0 or not t.get("scheduled_exit_date"):
        return {d.isoformat(): 0.0 for d in SCORE}
    exit_iso = t.get("actual_exit_date") or t["scheduled_exit_date"]
    done = t["status"] in COMPLETED
    fee_in = COMMISSION + spread(p0)
    out = {}
    mark, mark_date, unit_date = p0, date.fromisoformat(entry), date.fromisoformat(entry)
    closed_value = None
    for d in SCORE:
        iso = d.isoformat()
        if iso < entry:
            out[iso] = 0.0
            continue
        if closed_value is not None:
            out[iso] = closed_value
            continue
        f = adjustment_factor(t["symbol"], date.fromisoformat(entry), d)
        if done and iso == exit_iso:
            xp = t["exit_price"]
            closed_value = ((p0 * f - xp) / f) - fee_in - (COMMISSION + spread(xp)) / f
            out[iso] = closed_value
            continue
        rec = summaries.get((iso, t["symbol"]))
        if present(rec):
            mark, mark_date = rec["close"], d
        else:
            mark = mark * adjustment_factor(t["symbol"], unit_date, d)
        unit_date = d
        out[iso] = ((p0 * f - mark) / f) - fee_in
    return out


def month_end_sessions():
    last = {}
    for d in SCORE:
        last[d.strftime("%Y-%m")] = d.isoformat()
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    corrected, summaries, _ = build_substrate(args.workers)
    a8 = [typed_trade(r) for r in read(A8 / "r4r5_verified_trades.csv")]
    a8d = [typed_daily(r) for r in read(A8 / "r4r5_daily_account.csv")]
    a10 = [typed_trade(r) for r in read(A10 / "r4r5_verified_trades.csv")]
    a10d = [typed_daily(r) for r in read(A10 / "r4r5_daily_account.csv")]
    books = defaultdict(list)
    for t in a8 + a10:
        books[(t["model"], t["replay_stage"])].append(t)
    daily = defaultdict(list)
    for d in a8d + a10d:
        daily[(d["model"], d["replay_stage"])].append(d)
    for k in daily:
        daily[k].sort(key=lambda r: r["date"])
    me = month_end_sessions()

    # ------------------------------------------------------------ per-share paths, verified against every book
    paths_cache = {}
    recon = {}
    for key in (("R5", "R2_LEGACY_FILL_QTY"), ("R4", "R2_LEGACY_FILL_QTY"), ("R5", "R2_CAUSAL_PREORDER_QTY"),
                ("R4", "R2_CAUSAL_PREORDER_QTY")):
        eq = defaultdict(float)
        for t in books[key]:
            pk = (t["ticket_id"], t["entry_price"], t.get("exit_price"), t["status"])
            if pk not in paths_cache:
                paths_cache[pk] = per_share_path(t, summaries)
            q = t["quantity"] or 0
            for iso, v in paths_cache[pk].items():
                eq[iso] += q * v
        worst = max(abs(100000.0 + eq[r["date"]] - r["equity"]) for r in daily[key])
        recon["/".join(key)] = {"max_abs_equity_error": worst, "ok": worst < 1e-6}
        note(f"per-share path x quantity reproduces {key[0]}/{key[1]} daily equity: max error {worst:.2e}")
    if not all(v["ok"] for v in recon.values()):
        dump_json(CACHE / "bridge_manifest.json", {"blockers": ["per-share path does not reproduce the daily accounts"], "recon": recon})
        return 1

    # ------------------------------------------------------------ the bridge, per ticket, per panel
    bridge_rows, public_rows = [], []
    identity_worst = 0.0
    for panel, (stage, price_field) in PANELS.items():
        r4 = {t["ticket_id"]: t for t in books[("R4", stage)]}
        r5 = {t["ticket_id"]: t for t in books[("R5", stage)]}
        per_ticket = []
        for tid, t5 in r5.items():
            t4 = r4[tid]
            q4, q5 = t4["quantity"] or 0, t5["quantity"] or 0
            p = t5[price_field]
            vm, mm = t5["volume_multiplier"], t5["momentum_multiplier"]
            assert t4["volume_multiplier"] == vm, tid
            done = t5["status"] in COMPLETED
            nps = (t5["modeled_net"] / q5) if done and q5 else (t4["modeled_net"] / q4 if done and q4 else 0.0)
            if done and q4 and q5:
                identity_worst = max(identity_worst, abs(t5["modeled_net"] / q5 - t4["modeled_net"] / q4))
            diff = ((t5["modeled_net"] or 0) - (t4["modeled_net"] or 0)) if done else 0.0
            base_c = nps * (BASE["R5"] - BASE["R4"]) * vm / p if p else 0.0
            mom_c = nps * BASE["R5"] * vm * (mm - 1) / p if p else 0.0
            rounding = diff - base_c - mom_c
            pk = (tid, t5["entry_price"], t5.get("exit_price"), t5["status"])
            path = paths_cache.get(pk) or per_share_path(t5, summaries)
            monthly = {}
            prev = 0.0
            for m in MONTHS:
                v = path.get(me[m], 0.0)
                monthly[m] = v - prev
                prev = v
            dq = q5 - q4
            dq_cont = (BASE["R5"] * vm * mm - BASE["R4"] * vm) / p if p else 0.0
            row = {"panel": panel, "ticket_id": tid, "cohort_id": t5["cohort_id"], "signal_month": t5["cohort_id"][:7],
                   "split": t5["split"], "symbol": t5["symbol"], "rank": t5["rank"], "status": t5["status"],
                   "size_tier_r5": t5["size_tier"], "volume_multiplier": vm, "momentum_multiplier": mm,
                   "basis_price": p, "q_r4": q4, "q_r5": q5, "delta_shares": dq, "delta_shares_continuous": dq_cont,
                   "net_per_entry_share": nps, "r4_net": t4["modeled_net"], "r5_net": t5["modeled_net"],
                   "difference": diff, "base_ticket_component": base_c, "momentum_component": mom_c,
                   "rounding_residual": rounding, "identity_residual": diff - nps * dq if done else 0.0,
                   "price_return_10": (1 - t5["exit_price"] / (t5["action_factor_over_hold"] * t5["entry_price"])) if done else None,
                   "winner_under_r4": (t4["modeled_net"] > 0) if done else None}
            for m in MONTHS:
                row[f"pps_change_{m}"] = monthly[m]
                row[f"diff_marked_{m}"] = dq * monthly[m]
            per_ticket.append(row)
            bridge_rows.append(row)

        # ---- aggregate: signal-cohort eventual basis and calendar-month marked basis
        def agg(rows_sel, label_kind, label):
            done_rows = [r for r in rows_sel if r["status"] in COMPLETED]
            d = sum(r["difference"] for r in done_rows)
            base = sum(r["base_ticket_component"] for r in done_rows)
            mom = sum(r["momentum_component"] for r in done_rows)
            rnd = sum(r["rounding_residual"] for r in done_rows)
            win = sum(r["difference"] for r in done_rows if r["winner_under_r4"])
            lose = sum(r["difference"] for r in done_rows if r["winner_under_r4"] is False)
            top3 = sorted((abs(r["difference"]) for r in done_rows), reverse=True)[:3]
            tiers = defaultdict(float)
            for r in done_rows:
                tiers[r["size_tier_r5"]] += r["difference"]
            prs = [r["price_return_10"] for r in done_rows if r["price_return_10"] is not None]
            return {"panel": panel, "basis": label_kind, "period": label, "tickets": len(rows_sel), "completed": len(done_rows),
                    "r4_total": sum(r["r4_net"] or 0 for r in done_rows), "r5_total": sum(r["r5_net"] or 0 for r in done_rows),
                    "difference": d, "base_ticket_component": base, "momentum_component": mom, "rounding_residual": rnd,
                    "identity_residual": d - base - mom - rnd,
                    "difference_from_r4_winners": win, "difference_from_r4_losers": lose,
                    "difference_from_open_obligations": 0.0,
                    "top3_tickets_share_of_abs_difference": (sum(top3) / sum(abs(r["difference"]) for r in done_rows)) if done_rows and sum(abs(r["difference"]) for r in done_rows) else None,
                    "tickets_with_positive_difference": sum(1 for r in done_rows if r["difference"] > 0),
                    "tickets_with_negative_difference": sum(1 for r in done_rows if r["difference"] < 0),
                    "difference_FULL": tiers["FULL"], "difference_HALF": tiers["HALF"], "difference_QUARTER": tiers["QUARTER"],
                    "sizing_neutral_mean_price_return": (sum(prs) / len(prs)) if prs else None,
                    "sizing_neutral_hit_rate": (sum(1 for x in prs if x > 0) / len(prs)) if prs else None,
                    "quantity_convention": panel, "footnote": FOOTNOTE}

        by_cohort = defaultdict(list)
        for r in per_ticket:
            by_cohort[r["cohort_id"]].append(r)
        for cid in sorted(by_cohort):
            public_rows.append(agg(by_cohort[cid], "SIGNAL_COHORT_EVENTUAL_COMPLETED", cid))
        by_sm = defaultdict(list)
        for r in per_ticket:
            by_sm[r["signal_month"]].append(r)
        for m in MONTHS:
            public_rows.append(agg(by_sm.get(m, []), "SIGNAL_MONTH_EVENTUAL_COMPLETED", m))
        public_rows.append(agg(per_ticket, "ALL_EVENTUAL_COMPLETED", "ALL"))

        # calendar month, marked-account basis: exact per-ticket split of the monthly marked difference
        book5, book4 = daily[("R5", stage)], daily[("R4", stage)]
        m5 = mon.monthly_account(book5)
        m4 = mon.monthly_account(book4)
        for i, m in enumerate(MONTHS):
            diffs = [(r, r[f"diff_marked_{m}"]) for r in per_ticket]
            d = sum(v for _, v in diffs)
            # components scale with the per-share change, so they are recomputed directly
            base = sum(((BASE["R5"] - BASE["R4"]) * r["volume_multiplier"] / r["basis_price"]) * r[f"pps_change_{m}"] for r in per_ticket if r["basis_price"])
            mom = sum((BASE["R5"] * r["volume_multiplier"] * (r["momentum_multiplier"] - 1) / r["basis_price"]) * r[f"pps_change_{m}"] for r in per_ticket if r["basis_price"])
            rnd = d - base - mom
            win = sum(v for r, v in diffs if r["winner_under_r4"])
            lose = sum(v for r, v in diffs if r["winner_under_r4"] is False)
            # the documented open obligation has no completed exit, so its marked change is
            # neither a winner nor a loser; it is carried in its own bucket
            open_obl = sum(v for r, v in diffs if r["winner_under_r4"] is None)
            top3 = sorted((abs(v) for _, v in diffs), reverse=True)[:3]
            tot_abs = sum(abs(v) for _, v in diffs)
            tiers = defaultdict(float)
            for r, v in diffs:
                tiers[r["size_tier_r5"]] += v
            public_rows.append({
                "panel": panel, "basis": "CALENDAR_MONTH_MARKED_ACCOUNT", "period": m,
                "tickets": sum(1 for _, v in diffs if v != 0), "completed": None,
                "r4_total": m4[i]["monthly_pnl"], "r5_total": m5[i]["monthly_pnl"], "difference": d,
                "book_difference_from_daily_accounts": m5[i]["monthly_pnl"] - m4[i]["monthly_pnl"],
                "reconciliation_residual": d - (m5[i]["monthly_pnl"] - m4[i]["monthly_pnl"]),
                "base_ticket_component": base, "momentum_component": mom, "rounding_residual": rnd,
                "identity_residual": d - base - mom - rnd,
                "difference_from_r4_winners": win, "difference_from_r4_losers": lose,
                "difference_from_open_obligations": open_obl,
                "top3_tickets_share_of_abs_difference": (sum(top3) / tot_abs) if tot_abs else None,
                "tickets_with_positive_difference": sum(1 for _, v in diffs if v > 0),
                "tickets_with_negative_difference": sum(1 for _, v in diffs if v < 0),
                "difference_FULL": tiers["FULL"], "difference_HALF": tiers["HALF"], "difference_QUARTER": tiers["QUARTER"],
                "sizing_neutral_mean_price_return": None, "sizing_neutral_hit_rate": None,
                "quantity_convention": panel, "footnote": FOOTNOTE})
    worst_month_resid = max(abs(r["reconciliation_residual"]) for r in public_rows if r["basis"] == "CALENDAR_MONTH_MARKED_ACCOUNT")
    worst_identity = max(abs(r["identity_residual"]) for r in public_rows)
    note(f"bridge: net-per-share identity worst {identity_worst:.2e}; monthly marked reconciliation worst {worst_month_resid:.2e}; identity worst {worst_identity:.2e}")
    for r in public_rows:
        for k, v in list(r.items()):
            if isinstance(v, float):
                r[k] = round(v, 6)
    exp.write_csv(REPORTS / "cg_arrow011_model_month_attribution.csv", public_rows)
    exp.write_csv(OUT / "model_month_trade_bridge.csv", bridge_rows)

    # ------------------------------------------------------------ monthly accounts and account statistics
    monthly_rows, account_rows, recon_m = [], [], {}
    for key, label in BOOK_LABELS.items():
        book = {"trades": books[key], "daily": daily[key]}
        av = acct.account_view(book, summaries, label)
        h = met.headline(book, av, 100000.0)
        table = mon.monthly_account(daily[key])
        rc = mon.reconcile(table, av["B_marked_account_pnl_at_cutoff"])
        recon_m["/".join(key)] = rc
        prior = 100000.0
        for r in table:
            end = round(r["month_end_equity"], 2)
            pnl = round(end - prior, 2)
            monthly_rows.append({"month": r["month"], "book": label, "legacy_id": key[0], "replay_stage": key[1],
                                 "strategy": "Winner-Fade Short", "replay": "Corrected-Universe Replay (R2)", "horizon": "10-Session Hold (H10)",
                                 "monthly_pnl": pnl, "monthly_return_pct": round(pnl / prior * 100, 4),
                                 "month_end_equity": end, "prior_month_end_equity": prior,
                                 "reporting_standard": mon.STANDARD_ID, "footnote": FOOTNOTE})
            prior = end
        done = [t for t in books[key] if t["status"] in COMPLETED]
        wins = [t["modeled_net"] for t in done if t["modeled_net"] > 0]
        losses = [t["modeled_net"] for t in done if t["modeled_net"] < 0]
        account_rows.append({
            "book": label, "legacy_id": key[0], "replay_stage": key[1],
            "intended": len(books[key]), "filled": sum(1 for t in books[key] if t["quantity"]),
            "completed": len(done), "open_documented": av["E_open_documented_obligations"],
            "wins": len(wins), "losses": len(losses), "flats": len(done) - len(wins) - len(losses),
            "hit_rate": round(len(wins) / len(done), 4) if done else None,
            "avg_winner": round(sum(wins) / len(wins), 2) if wins else None,
            "avg_loser": round(sum(losses) / len(losses), 2) if losses else None,
            "payoff_ratio": round((sum(wins) / len(wins)) / abs(sum(losses) / len(losses)), 4) if wins and losses else None,
            "profit_factor": round(sum(wins) / -sum(losses), 4) if losses else None,
            "eventual_completed_trade_pnl": round(av["A_completed_trade_pnl_all_cohorts"], 2),
            "marked_account_pnl_at_2026_08_31": round(av["B_marked_account_pnl_at_cutoff"], 2),
            "post_cutoff_incremental_runoff_pnl": round(av["C_post_cutoff_incremental_runoff_pnl"], 2),
            "eventual_pnl_of_runoff_trades": round(av["D_eventual_pnl_of_runoff_trades"], 2),
            "runoff_trade_count": av["runoff_trade_count"],
            "ending_marked_equity": round(h["ending_marked_equity_at_cutoff"], 2),
            "max_drawdown_dollars": round(h["max_drawdown_dollars"], 2), "max_drawdown_pct_of_peak": round(h["max_drawdown_pct_of_peak"], 2),
            "worst_day": round(h["worst_day"], 2), "time_underwater_pct": round(h["time_underwater_pct"], 2),
            "mean_gross_exposure": round(h["mean_gross_exposure"], 2), "peak_gross_exposure": round(h["peak_gross_exposure"], 2),
            "mean_gross_over_marked_equity": round(h["mean_gross_over_marked_equity"], 4),
            "turnover_entry_notional": round(h["turnover_entry_notional"], 2),
            "positive_months": h["positive_months"], "red_months": h["red_months"], "flat_months": 12 - h["positive_months"] - h["red_months"],
            "worst_month": round(h["worst_month"], 2), "best_month": round(h["best_month"], 2), "median_month": round(h["median_month"], 2),
            "monthly_reconciles": rc["reconciles"], "identities_hold": av["identities_hold"], "footnote": FOOTNOTE})
        note(f"{label}: B={av['B_marked_account_pnl_at_cutoff']:,.2f} monthly reconciles={rc['reconciles']} identities={av['identities_hold']}")
    exp.write_csv(REPORTS / "cg_arrow011_monthly_account.csv", monthly_rows)
    exp.write_csv(REPORTS / "cg_arrow011_account_summary.csv", account_rows)
    dump_json(CACHE / "bridge_manifest.json", {
        "stage": "bridge", "timestamp": stamp(), "per_share_path_reconciliation": recon,
        "net_per_share_identity_worst": identity_worst, "monthly_marked_reconciliation_worst": worst_month_resid,
        "identity_worst": worst_identity, "monthly_reconciliation": recon_m,
        "decomposition_order": "BASE_TICKET (5150 -> 8300 at R4 multipliers) then MOMENTUM (mm at the 8300 base), ROUNDING residual; exact identity",
        "blockers": [], "log": LOG})
    note("bridge complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
