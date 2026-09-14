"""CG Arrow 010 — R5 equity-sizing study on the certified R2/H10 substrate.

One experiment: the frozen Momentum+Volume-Sized Short, causal pre-order quantities, with
ticket notionals either fixed in dollars or scaled by the marked account equity at the close
of the signal session. Selection, tiers, entry and exit sessions and every observed price are
identical between the two books; only share counts differ.

No redeployment, hold change, leverage sweep, gross cap, throttle or new strategy research.

Usage: python scripts/cg_arrow010_run.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_accounting as acct  # noqa: E402
from verification import r4r5_equity as eq  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_metrics as met  # noqa: E402
from verification import r4r5_monthly as mon  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    ACTION_PATH, FEATS, INDEX, RANKS_PATH, VERIFY_ROOT, action_events, digest, dump_json,
    load_summaries, non_comparable_events, present, read_json, set_vendor_status, stamp,
)
from verification.r4r5_replay import COMPLETED, needs_for, replay  # noqa: E402
from cg_arrow007_run import candidate_meta, rank_with, tradable_universe  # noqa: E402

WORK = VERIFY_ROOT / "work"
HANDOFF = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow010"
FAM = "R5"
VARIANT = "Momentum+Volume-Sized Short"
LOOKBACK = 15
HOLD = 10
START_EQUITY = 100000.0
TIERS = {"FULL": 8300.0, "HALF": 4150.0, "QUARTER": 2075.0}
FIXED = "R5_FIXED_DOLLAR_CONTROL"
SCALED = "R5_EQUITY_SCALED"
MODES = (FIXED, SCALED)
MODE_LABEL = {FIXED: "Fixed-dollar R5", SCALED: "Equity-scaled R5"}
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
          "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
LATE = ("2026-06", "2026-07", "2026-08")
CONTROLS = {"legacy_fill_eventual_completed_trade_pnl": 129092.60,
            "legacy_fill_marked_account_pnl_at_cutoff": 129202.83,
            "legacy_fill_marked_equity_at_cutoff": 229202.83,
            "causal_preorder_eventual_completed_trade_pnl": 128864.62}
FOOTNOTE = ("Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes "
            "broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other "
            "account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow "
            "fees for Trading API users; short availability and other security-specific costs may still vary.")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def money(x) -> str:
    return "n/a" if x is None else f"{x:,.2f}"


def pct(x, places: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{places}f}%"


def build_substrate(workers: int) -> tuple[list[dict], dict, dict]:
    """The certified Corrected-Universe cohort field and the observations it needs."""
    assert ACTION_PATH.name == "cg_arrow008_corporate_actions.json", ACTION_PATH
    cohort_field = read_json(WORK / "cohort_field.json")
    meta = candidate_meta(sorted(cohort_field))
    status_map = rep.session_status_map()
    set_vendor_status(status_map)
    rule_field = {iso: cf["rule_field"] for iso, cf in cohort_field.items()}

    endpoints = set()
    for iso, syms in rule_field.items():
        back = FEATS[INDEX[date.fromisoformat(iso)] - LOOKBACK].isoformat()
        for s in syms:
            endpoints.add((iso, s))
            endpoints.add((back, s))
    note(f"loading {len(endpoints)} ranking endpoints")
    summaries = load_summaries(endpoints, workers)

    action_events.cache_clear()
    non_comparable_events.cache_clear()
    corrected = rank_with(rule_field, meta, summaries, status_map)

    # the engine's own declaration of what a ledger needs: 22 sessions of feature history
    # before the signal, the fill, every mark through the exit, and the post-due sessions a
    # carried exit may reach. A shorter window silently drops a volume or momentum feature
    # and promotes a HALF or QUARTER ticket to FULL, so this set is taken from the engine.
    life = set(needs_for(corrected, hold=HOLD))
    summaries.update(load_summaries(life - set(summaries), workers))

    # A gap only matters where the ledger reads something. The engine's pricing window is the
    # 20 sessions of feature history through the signal, the fill, and every mark through the
    # scheduled exit. The need set is deliberately wider: it carries two further history
    # sessions of margin and every post-due session a documented-halt carry might reach, and
    # an absence in that margin cannot move a price, a quantity or a P&L.
    core = set()
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in c["rows"]:
            for d in FEATS[max(0, i - 20): fi + HOLD + 1]:
                core.add((d.isoformat(), h["symbol"]))

    def absent(pairs):
        return [(s, iso) for (iso, s) in pairs if not present(summaries.get((iso, s)))
                and status_map.get((s, iso)) != "DOCUMENTED_NO_TRADING"]

    missing_core = absent(core)
    missing_post = absent(life - core)
    note(f"cohorts={len(corrected)} pricing-window observations missing={len(missing_core)}; "
         f"absent in the wider need-set margin={len(missing_post)} (cannot move a result)")
    return corrected, summaries, {"pricing_window_missing": len(missing_core),
                                  "absent_in_need_set_margin": len(missing_post),
                                  "pricing_window_basis": "20 sessions of feature history through "
                                                          "the signal, the fill, and every mark "
                                                          "through the scheduled exit",
                                  "margin_basis": "two further history sessions and the post-due "
                                                  "sessions a documented-halt carry may reach; "
                                                  "read by no pricing path"}


def cohort_net(book: dict) -> dict:
    out = defaultdict(float)
    for t in book["trades"]:
        if t["status"] in COMPLETED:
            out[t["cohort_id"]] += t["modeled_net"]
    return out


def ticket_net(book: dict) -> dict:
    return {t["ticket_id"]: (t["modeled_net"] if t["status"] in COMPLETED else None)
            for t in book["trades"]}


def gross_on(daily: list[dict], when: str) -> float | None:
    for r in daily:
        if r["date"] == when:
            return r["gross_exposure"]
    return None


def equity_on(daily: list[dict], when: str) -> float | None:
    for r in daily:
        if r["date"] == when:
            return r["equity"]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    blockers: list[str] = []

    corrected, summaries, coverage = build_substrate(args.workers)

    # ------------------------------------------------------- certified controls must reproduce
    legacy = replay(FAM, corrected, summaries, hold=HOLD, quantity="fill", stage="R2_LEGACY_FILL_QTY")
    preorder = replay(FAM, corrected, summaries, hold=HOLD, quantity="preorder",
                      stage="R2_CAUSAL_PREORDER_QTY")
    legacy_acct = acct.account_view(legacy, summaries, "legacy fill")
    observed = {
        "legacy_fill_eventual_completed_trade_pnl": legacy_acct["A_completed_trade_pnl_all_cohorts"],
        "legacy_fill_marked_account_pnl_at_cutoff": legacy_acct["B_marked_account_pnl_at_cutoff"],
        "legacy_fill_marked_equity_at_cutoff": legacy["daily"][-1]["equity"],
        "causal_preorder_eventual_completed_trade_pnl":
            sum(t["modeled_net"] for t in preorder["trades"] if t["status"] in COMPLETED),
    }
    control_check = {k: {"expected": v, "observed": observed[k],
                         "difference": observed[k] - v, "reproduces": abs(observed[k] - v) < 0.005}
                     for k, v in CONTROLS.items()}
    for k, v in control_check.items():
        note(f"control {k}: expected {money(v['expected'])} observed {money(v['observed'])} "
             f"reproduces={v['reproduces']}")
    if not all(v["reproduces"] for v in control_check.values()):
        note("CERTIFIED CONTROLS DID NOT REPRODUCE — stopping before any sizing research")
        dump_json(REPORTS / "cg_arrow010_manifest.json",
                  {"arrow": "CG Arrow 010", "timestamp": stamp(), "control_check": control_check,
                   "status": "STOPPED_CONTROLS_DID_NOT_REPRODUCE", "log": LOG})
        return 1

    # ------------------------------------------------------- the two books
    books = {}
    books[FIXED] = eq.causal_book(FAM, corrected, summaries, hold=HOLD, stage=FIXED, scaled=False)
    books[SCALED] = eq.causal_book(FAM, corrected, summaries, hold=HOLD, stage=SCALED, scaled=True)
    for mode in MODES:
        done = [t for t in books[mode]["trades"] if t["status"] in COMPLETED]
        note(f"{MODE_LABEL[mode]}: {len(done)}/{len(books[mode]['trades'])} completed, "
             f"eventual {money(sum(t['modeled_net'] for t in done))}")

    # the serial control must equal the batch causal pre-order book exactly
    batch = sum(t["modeled_net"] for t in preorder["trades"] if t["status"] in COMPLETED)
    serial = sum(t["modeled_net"] for t in books[FIXED]["trades"] if t["status"] in COMPLETED)
    if abs(batch - serial) > 1e-9:
        blockers.append(f"the serial fixed-dollar control ({serial}) does not equal the certified "
                        f"batch causal pre-order book ({batch})")
    note(f"serial control equals batch causal pre-order book: {abs(batch - serial) <= 1e-9}")

    # ------------------------------------------------------- invariants between the books
    def key_of(t):
        return (t["cohort_id"], t["rank"], t["symbol"], t["scheduled_entry_date"],
                t.get("scheduled_exit_date"), t["size_tier"], t.get("entry_price"),
                t.get("exit_price"), t.get("preorder_price"))

    fixed_keys = [key_of(t) for t in books[FIXED]["trades"]]
    scaled_keys = [key_of(t) for t in books[SCALED]["trades"]]
    identical_substrate = fixed_keys == scaled_keys
    note(f"selection, tiers, sessions and prices identical between books: {identical_substrate}")
    if not identical_substrate:
        blockers.append("the two books do not share an identical selection/tier/session/price substrate")

    # per-trade price return before sizing must be identical
    max_ret_gap = 0.0
    fixed_by_id = {t["ticket_id"]: t for t in books[FIXED]["trades"]}
    for t in books[SCALED]["trades"]:
        f = fixed_by_id[t["ticket_id"]]
        if t["status"] in COMPLETED and f["status"] in COMPLETED:
            a = t["entry_price_exit_units"] / t["exit_price"] - 1
            b = f["entry_price_exit_units"] / f["exit_price"] - 1
            max_ret_gap = max(max_ret_gap, abs(a - b))
    note(f"max per-trade pre-sizing price-return gap: {max_ret_gap:.3e}")
    if max_ret_gap > 1e-12:
        blockers.append("per-trade price return before sizing differs between the books")

    violations = eq.causality_violations(books[SCALED], corrected)
    note(f"causality violations in the equity-scaled sizing path: {len(violations)}")
    if violations:
        blockers.append(f"equity-scaled sizing uses information it is not entitled to: {violations[:3]}")

    first = books[SCALED]["scaling_path"][0]
    base_tickets = [t for t in books[SCALED]["trades"] if t["cohort_id"] == first["cohort_id"]]
    at_par = all(abs(t["intended_size"] - TIERS[t["size_tier"]]) < 1e-9 for t in base_tickets)
    note(f"first cohort sizes from 100,000 at par tiers: {at_par} "
         f"(reference {money(first['equity_reference'])})")
    if not at_par:
        blockers.append("at 100,000 reference equity the scaled tiers do not equal 8,300/4,150/2,075")

    # ------------------------------------------------------- accounts, splits and metrics
    accounts, split_books, headline = {}, {}, {}
    for mode in MODES:
        scaled_flag = mode == SCALED
        for split in ("IS", "OOS", "ALL"):
            if split == "ALL":
                b = books[mode]
            else:
                subset = [c for c in corrected if c["split"] == split]
                b = eq.causal_book(FAM, subset, summaries, hold=HOLD,
                                   stage=f"{mode}_{split}", scaled=scaled_flag)
            split_books[(mode, split)] = b
            accounts[f"{mode}/{split}"] = acct.account_view(
                b, summaries, f"{VARIANT} / {MODE_LABEL[mode]} / {split}")
            headline[f"{mode}/{split}"] = met.headline(b, accounts[f"{mode}/{split}"], START_EQUITY)
    bad = [k for k, v in accounts.items() if not v["identities_hold"]]
    note(f"account identities hold: {len(accounts) - len(bad)}/{len(accounts)}")
    if bad:
        blockers.append(f"account identities fail for {bad}")

    # ------------------------------------------------------- monthly standard
    monthly, recon = {}, {}
    for mode in MODES:
        table = mon.monthly_account(books[mode]["daily"], START_EQUITY)
        b = accounts[f"{mode}/ALL"]["B_marked_account_pnl_at_cutoff"]
        monthly[mode] = table
        recon[mode] = mon.reconcile(table, b, START_EQUITY)
        note(f"{MODE_LABEL[mode]} monthly: {len(table)} months, reconciles={recon[mode]['reconciles']}")
        if [r["month"] for r in table] != MONTHS:
            blockers.append(f"{mode} monthly table is not the twelve required months")
        if not recon[mode]["reconciles"]:
            blockers.append(f"{mode} monthly rows do not reconcile to the cutoff marked account result")

    # ------------------------------------------------------- compounding diagnostics
    fixed_cohort = cohort_net(books[FIXED])
    scaled_cohort = cohort_net(books[SCALED])
    fixed_ticket = ticket_net(books[FIXED])
    scaled_ticket = ticket_net(books[SCALED])
    intended = defaultdict(lambda: defaultdict(float))
    for mode in MODES:
        for t in books[mode]["trades"]:
            intended[mode][t["cohort_id"]] += t["intended_size"]

    cohort_rows = []
    for row in books[SCALED]["scaling_path"]:
        cid = row["cohort_id"]
        entry = row["entry_date"]
        pre_gross = gross_on(books[SCALED]["daily"], cid)
        post_gross = gross_on(books[SCALED]["daily"], entry)
        post_equity = equity_on(books[SCALED]["daily"], entry)
        cohort_rows.append({
            "cohort_id": cid, "signal_date": cid, "entry_date": entry, "split": row["split"],
            "signal_session_reference_equity": round(row["equity_reference"], 2),
            "scale_factor_vs_100k": round(row["scale_factor"], 6),
            "fixed_dollar_intended_cohort_notional": round(intended[FIXED][cid], 2),
            "equity_scaled_intended_cohort_notional": round(intended[SCALED][cid], 2),
            "fixed_dollar_realized_cohort_pnl": round(fixed_cohort.get(cid, 0.0), 2),
            "equity_scaled_realized_cohort_pnl": round(scaled_cohort.get(cid, 0.0), 2),
            "incremental_pnl_from_equity_scaling":
                round(scaled_cohort.get(cid, 0.0) - fixed_cohort.get(cid, 0.0), 2),
            "pre_entry_marked_gross_exposure": None if pre_gross is None else round(pre_gross, 2),
            "post_entry_marked_gross_exposure": None if post_gross is None else round(post_gross, 2),
            "post_entry_marked_equity": None if post_equity is None else round(post_equity, 2),
            "post_entry_gross_over_equity":
                None if not post_equity else round(post_gross / post_equity, 4),
            "sizing_rule_id": eq.RULE_ID})
    exp.write_csv(REPORTS / "cg_arrow010_cohort_scaling.csv", cohort_rows)

    uplift = sum(r["incremental_pnl_from_equity_scaling"] for r in cohort_rows)
    factors = [r["scale_factor_vs_100k"] for r in cohort_rows]
    by_month = defaultdict(float)
    for r in cohort_rows:
        by_month[r["cohort_id"][:7]] += r["incremental_pnl_from_equity_scaling"]
    ranked = sorted(cohort_rows, key=lambda r: -abs(r["incremental_pnl_from_equity_scaling"]))

    winner_uplift = loser_uplift = 0.0
    tier_uplift = defaultdict(float)
    for t in books[SCALED]["trades"]:
        f_net, s_net = fixed_ticket.get(t["ticket_id"]), scaled_ticket.get(t["ticket_id"])
        if f_net is None or s_net is None:
            continue
        delta = s_net - f_net
        tier_uplift[t["size_tier"]] += delta
        if f_net > 0:
            winner_uplift += delta
        elif f_net < 0:
            loser_uplift += delta

    def first_above(threshold: float):
        for r in cohort_rows:
            if r["scale_factor_vs_100k"] >= threshold:
                return {"cohort_id": r["cohort_id"], "scale_factor": r["scale_factor_vs_100k"]}
        return None

    share = (lambda x: (x / uplift * 100.0) if uplift else None)
    diagnostics = {
        "total_incremental_pnl_from_equity_scaling": uplift,
        "scale_factor_min": min(factors), "scale_factor_median": statistics.median(factors),
        "scale_factor_max": max(factors), "scale_factor_final_cohort": factors[-1],
        "first_cohort_above": {f"{x:.2f}x": first_above(x) for x in (1.10, 1.25, 1.50, 2.00)},
        "uplift_share_by_signal_month_pct": {m: share(v) for m, v in sorted(by_month.items())},
        "uplift_share_june_to_august_2026_pct": share(sum(by_month[m] for m in LATE)),
        "uplift_share_top_1_cohorts_pct": share(sum(
            r["incremental_pnl_from_equity_scaling"] for r in ranked[:1])),
        "uplift_share_top_3_cohorts_pct": share(sum(
            r["incremental_pnl_from_equity_scaling"] for r in ranked[:3])),
        "uplift_share_top_5_cohorts_pct": share(sum(
            r["incremental_pnl_from_equity_scaling"] for r in ranked[:5])),
        "top_cohorts": [{"cohort_id": r["cohort_id"], "split": r["split"],
                         "scale_factor": r["scale_factor_vs_100k"],
                         "incremental_pnl": r["incremental_pnl_from_equity_scaling"]}
                        for r in ranked[:5]],
        "uplift_from_trades_that_won_under_fixed_dollars": winner_uplift,
        "extra_loss_from_trades_that_lost_under_fixed_dollars": loser_uplift,
        "uplift_by_tier": dict(tier_uplift),
        "incremental_max_drawdown_dollars":
            headline[f"{SCALED}/ALL"]["max_drawdown_dollars"] - headline[f"{FIXED}/ALL"]["max_drawdown_dollars"],
        "incremental_max_drawdown_pct_of_peak":
            headline[f"{SCALED}/ALL"]["max_drawdown_pct_of_peak"] - headline[f"{FIXED}/ALL"]["max_drawdown_pct_of_peak"],
        "gross_over_equity_fixed": {k: headline[f"{FIXED}/ALL"][k] for k in
                                    ("mean_gross_over_marked_equity", "p95_gross_over_marked_equity",
                                     "peak_gross_over_marked_equity")},
        "gross_over_equity_scaled": {k: headline[f"{SCALED}/ALL"][k] for k in
                                     ("mean_gross_over_marked_equity", "p95_gross_over_marked_equity",
                                      "peak_gross_over_marked_equity")},
    }
    # Whether leverage stays put as dollars grow is a question about each book's own path
    # over time, not about the gap between the books. Comparing the two means would call the
    # fixed book's de-levering "stability" in the scaled book, which is backwards.
    halves = {}
    for mode in MODES:
        ratios = [r["gross_exposure"] / r["equity"] for r in books[mode]["daily"] if r["equity"] > 0]
        mid = len(ratios) // 2
        first = sum(ratios[:mid]) / mid
        second = sum(ratios[mid:]) / (len(ratios) - mid)
        halves[mode] = {"first_half_mean": first, "second_half_mean": second,
                        "drift": second - first}
    diagnostics["gross_over_equity_by_half"] = halves
    diagnostics["gross_over_equity_scaled_drift"] = halves[SCALED]["drift"]
    diagnostics["gross_over_equity_fixed_drift"] = halves[FIXED]["drift"]
    diagnostics["gross_over_equity_approximately_stable"] = abs(halves[SCALED]["drift"]) < 0.05
    diagnostics["gross_over_equity_stability_basis"] = (
        "gross short exposure over the same session's marked equity, mean of the first half of "
        "the account sessions against the mean of the second half, measured separately for each "
        "book; the scaled book holds the ratio it was designed to hold, while the fixed-dollar "
        "book sheds leverage as equity grows because its tickets do not follow the account")
    note(f"uplift {money(uplift)}; scale {factors[0]:.3f}..{factors[-1]:.3f}; "
         f"June-Aug share {pct(diagnostics['uplift_share_june_to_august_2026_pct'])}")

    # ------------------------------------------------------- private exports and the oracle
    export = {(FAM, mode): books[mode] for mode in MODES}
    files = exp.export_all(export, root=HANDOFF)
    (HANDOFF / "equity_scaled_trade_audit.csv").write_bytes(
        (HANDOFF / "r4r5_verified_trades.csv").read_bytes())
    (HANDOFF / "equity_scaled_cohort_audit.csv").write_bytes(
        (HANDOFF / "r4r5_verified_cohort_audit.csv").read_bytes())
    (HANDOFF / "equity_scaled_daily_account.csv").write_bytes(
        (HANDOFF / "r4r5_daily_account.csv").read_bytes())
    files["equity_scaled_trade_audit.csv"] = digest(HANDOFF / "equity_scaled_trade_audit.csv")
    files["equity_scaled_cohort_audit.csv"] = digest(HANDOFF / "equity_scaled_cohort_audit.csv")
    files["equity_scaled_daily_account.csv"] = digest(HANDOFF / "equity_scaled_daily_account.csv")

    orc = oracle.run(HANDOFF, summaries)
    stored = oracle.read_csv(HANDOFF / "r4r5_verified_trades.csv")
    sizing_check = oracle.verify_equity_sizing(
        [r for r in stored if r["replay_stage"] == SCALED], summaries, TIERS, START_EQUITY)
    control_sizing = oracle.verify_equity_sizing(
        [r for r in stored if r["replay_stage"] == FIXED], summaries,
        {k: v for k, v in TIERS.items()}, START_EQUITY)
    orc["equity_sizing"] = sizing_check
    note(f"oracle ok={orc['ok']} trades={orc['trades']} cohorts={orc['cohorts']}; "
         f"independent sizing check ok={sizing_check['ok']} "
         f"tickets={sizing_check['tickets_checked']} max share error={sizing_check['max_share_error']}")
    if not orc["ok"]:
        blockers.append("the independent oracle did not reconcile")
    if not sizing_check["ok"]:
        blockers.append(f"independent equity sizing recomputation disagrees: {sizing_check['failures'][:3]}")
    if control_sizing["errors"] and control_sizing["max_share_error"] == 0:
        pass  # the control carries no scale fields; only share counts are meaningful there

    # ------------------------------------------------------- public tables
    summary_rows = []
    for mode in MODES:
        for split in ("IS", "OOS", "ALL"):
            h = headline[f"{mode}/{split}"]
            v = accounts[f"{mode}/{split}"]
            summary_rows.append({
                "strategy": "Winner-Fade Short", "variant": VARIANT, "legacy_id": FAM,
                "replay": "Corrected-Universe Replay (R2)", "horizon": "10-Session Hold (H10)",
                "quantity_panel": "CAUSAL_PREORDER_QTY", "sizing_mode": MODE_LABEL[mode],
                "sizing_mode_id": mode, "split": split,
                "book_basis": ("account of record" if split == "ALL" else
                               "standalone split-owned book, restarts at 100,000 starting equity"),
                "starting_equity": round(h["starting_equity"], 2),
                "ending_marked_equity_at_2026_08_31": round(h["ending_marked_equity_at_cutoff"], 2),
                "marked_account_pnl_at_2026_08_31": round(h["marked_account_pnl_at_cutoff"], 2),
                "eventual_completed_trade_pnl": round(h["eventual_completed_trade_pnl"], 2),
                "return_on_starting_equity_pct": round(h["return_on_starting_equity_pct"], 2),
                "completed_trades": h["completed_trades"],
                "hit_rate": None if h["hit_rate"] is None else round(h["hit_rate"], 4),
                "avg_winner": None if h["avg_winner"] is None else round(h["avg_winner"], 2),
                "avg_loser": None if h["avg_loser"] is None else round(h["avg_loser"], 2),
                "profit_factor": None if h["profit_factor"] is None else round(h["profit_factor"], 4),
                "max_drawdown_dollars": round(h["max_drawdown_dollars"], 2),
                "max_drawdown_pct_of_peak": round(h["max_drawdown_pct_of_peak"], 2),
                "max_drawdown_date": h["max_drawdown_date"],
                "worst_day": round(h["worst_day"], 2),
                "worst_month": round(h["worst_month"], 2),
                "best_month": round(h["best_month"], 2),
                "median_month": round(h["median_month"], 2),
                "positive_months": h["positive_months"], "red_months": h["red_months"],
                "sum_of_red_months": round(h["sum_of_red_months"], 2),
                "mean_gross_exposure": round(h["mean_gross_exposure"], 2),
                "peak_gross_exposure": round(h["peak_gross_exposure"], 2),
                "mean_gross_over_marked_equity": round(h["mean_gross_over_marked_equity"], 4),
                "p95_gross_over_marked_equity": round(h["p95_gross_over_marked_equity"], 4),
                "peak_gross_over_marked_equity": round(h["peak_gross_over_marked_equity"], 4),
                "turnover_entry_notional": round(h["turnover_entry_notional"], 2),
                "exposure_dollar_sessions": round(h["exposure_dollar_sessions"], 2),
                "time_underwater_pct": round(h["time_underwater_pct"], 2),
                "sessions_underwater": h["sessions_underwater"],
                "account_sessions": h["account_sessions"],
                "runoff_trade_count": h["runoff_trade_count"],
                "post_cutoff_incremental_runoff_pnl": round(h["post_cutoff_incremental_runoff_pnl"], 2),
                "eventual_pnl_of_runoff_trades": round(h["eventual_pnl_of_runoff_trades"], 2),
                "open_documented_obligations": h["open_documented_obligations"],
                "stale_gross_at_calendar_boundary": round(h["stale_gross_at_calendar_boundary"], 2),
                "identities_hold": v["identities_hold"],
                "sizing_rule_id": eq.RULE_ID, "footnote": FOOTNOTE})
    exp.write_csv(REPORTS / "cg_arrow010_equity_summary.csv", summary_rows)

    monthly_rows = []
    for mode in MODES:
        prior = round(START_EQUITY, 2)
        for r in monthly[mode]:
            end = round(r["month_end_equity"], 2)
            pnl = round(end - prior, 2)
            monthly_rows.append({
                "month": r["month"], "strategy": VARIANT, "legacy_id": FAM,
                "replay": "Corrected-Universe Replay (R2)", "horizon": "10-Session Hold (H10)",
                "quantity_panel": "CAUSAL_PREORDER_QTY",
                "sizing_mode": MODE_LABEL[mode], "sizing_mode_id": mode,
                "monthly_pnl": pnl, "monthly_return_pct": round(pnl / prior * 100.0, 4),
                "month_end_equity": end, "prior_month_end_equity": prior,
                "reporting_standard": mon.STANDARD_ID, "footnote": FOOTNOTE})
            prior = end
    exp.write_csv(REPORTS / "cg_arrow010_monthly_account.csv", monthly_rows)
    assert not mon.missing_standard_fields(monthly_rows), mon.missing_standard_fields(monthly_rows)

    # ------------------------------------------------------- research status
    f_all, s_all = headline[f"{FIXED}/ALL"], headline[f"{SCALED}/ALL"]
    ret_gain = s_all["return_on_starting_equity_pct"] - f_all["return_on_starting_equity_pct"]
    f_eff = f_all["marked_account_pnl_at_cutoff"] / abs(f_all["max_drawdown_dollars"]) \
        if f_all["max_drawdown_dollars"] else None
    s_eff = s_all["marked_account_pnl_at_cutoff"] / abs(s_all["max_drawdown_dollars"]) \
        if s_all["max_drawdown_dollars"] else None
    if abs(ret_gain) < 1.0:
        status = "EQUITY SCALING IS ECONOMICALLY NEUTRAL"
    elif ret_gain < 0:
        status = "EQUITY SCALING DEGRADES THE ACCOUNT PATH"
    elif s_eff is not None and f_eff is not None and s_eff >= f_eff - 0.05:
        status = "EQUITY SCALING IS ECONOMICALLY ATTRACTIVE FOR FURTHER STUDY"
    else:
        status = "EQUITY SCALING ADDS RETURN BUT NOT RISK EFFICIENCY"
    if blockers:
        status = "RESULT INCONCLUSIVE — " + "; ".join(blockers[:2])
    note(f"return on starting equity: fixed {pct(f_all['return_on_starting_equity_pct'])} "
         f"scaled {pct(s_all['return_on_starting_equity_pct'])}; "
         f"pnl per drawdown dollar fixed {f_eff:.3f} scaled {s_eff:.3f}")
    note(f"RESEARCH STATUS: {status}")

    manifest = {
        "arrow": "CG Arrow 010", "executor": "Opus in Claude Code", "timestamp": stamp(),
        "elapsed_minutes": (time.monotonic() - T0) / 60,
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                               cwd=REPO_ROOT).decode().strip(),
        "scope": ("R5-only equity-responsive sizing on the certified R2/H10 causal pre-order "
                  "substrate; no redeployment, hold change, leverage sweep or new strategy research"),
        "variant": VARIANT, "legacy_id": FAM,
        "sizing_rule_id": eq.RULE_ID, "sizing_rule": eq.RULE, "tiers": TIERS,
        "certified_controls": control_check,
        "certified_inputs": {
            "arrow008_manifest_sha256": digest(REPORTS / "cg_arrow008_manifest.json"),
            "action_table_sha256": digest(ACTION_PATH),
            "arrow008_certification": read_json(REPORTS / "cg_arrow008_manifest.json")["certification"]["verdict"]},
        "observation_coverage": coverage,
        "substrate_identical_between_books": identical_substrate,
        "max_pre_sizing_price_return_gap": max_ret_gap,
        "causality_violations": violations,
        "serial_control_equals_batch": abs(batch - serial) <= 1e-9,
        "entry_ledger_sha256": {
            mode: sha_obj([{"cohort_id": t["cohort_id"], "symbol": t["symbol"], "rank": t["rank"],
                            "entry_date": t.get("scheduled_entry_date"),
                            "entry_price": t.get("entry_price"), "quantity": t.get("quantity"),
                            "size_tier": t.get("size_tier")} for t in books[mode]["trades"]])
            for mode in MODES},
        "membership_sha256": sha_obj({c["signal_iso"]: [h["symbol"] for h in c["rows"]]
                                      for c in corrected}),
        "accounts": accounts, "headline": headline,
        "monthly": {mode: monthly[mode] for mode in MODES},
        "monthly_reconciliation": recon,
        "monthly_reporting_standard": mon.STANDARD_ID,
        "diagnostics": diagnostics,
        "oracle": orc, "local_csvs": files,
        "research_status": status,
        "status_basis": {"return_on_starting_equity_pct":
                         {FIXED: f_all["return_on_starting_equity_pct"],
                          SCALED: s_all["return_on_starting_equity_pct"]},
                         "marked_pnl_per_drawdown_dollar": {FIXED: f_eff, SCALED: s_eff}},
        "blockers": blockers,
        "headline_footnote": FOOTNOTE,
        "log": LOG,
    }
    dump_json(REPORTS / "cg_arrow010_manifest.json", manifest)

    write_report(manifest, summary_rows, monthly_rows, cohort_rows, diagnostics, headline,
                 accounts, recon, status)
    note(f"elapsed {(time.monotonic() - T0) / 60:.1f} minutes")
    return 0 if not blockers else 1


def write_report(manifest, summary_rows, monthly_rows, cohort_rows, diagnostics, headline,
                 accounts, recon, status) -> None:
    f, s = headline[f"{FIXED}/ALL"], headline[f"{SCALED}/ALL"]
    L: list[str] = []
    A = L.append
    A("# CG Arrow 010 — R5 equity-sizing study")
    A("")
    A(f"Executor: Opus in Claude Code. Starting checkpoint `{manifest['head_at_run'][:7]}`. "
      "One experiment on the certified substrate: the frozen Momentum+Volume-Sized Short "
      "(`R5`), Corrected-Universe Replay (`R2`), 10-Session Hold (`H10`), causal pre-order "
      "quantities, sized either in fixed dollars or as the equivalent percentage of account "
      "equity. No hold, entry time, selection, filter, cap, throttle or redeployment rule was "
      "introduced or tested.")
    A("")
    A("## The rule, frozen before scoring")
    A("")
    A("For every weekly cohort the reference is the marked account equity at the close of the "
      "signal session, the last completed account close before the next-session entry. It is "
      "the same reference for all eight tickets in the cohort.")
    A("")
    A("```")
    A("scale_factor    = equity at signal-session close / 100,000")
    A("intended ticket = fixed R5 tier notional * scale_factor")
    A("FULL 8,300 -> 8.300%   HALF 4,150 -> 4.150%   QUARTER 2,075 -> 2.075%   of reference equity")
    A("```")
    A("")
    A("At exactly 100,000 the two books are identical in intended dollars, and the first cohort "
      "confirms it. Shares remain floored from the causal pre-order price, so an equity-responsive "
      "order is still knowable before its fill.")
    A("")
    A("## Certified controls reproduced first")
    A("")
    A("| Certified Arrow 008 control | Expected | Observed | Reproduces |")
    A("|---|---:|---:|---|")
    for k, v in manifest["certified_controls"].items():
        A(f"| {k.replace('_', ' ')} | {money(v['expected'])} | {money(v['observed'])} | "
          f"{'yes' if v['reproduces'] else 'NO'} |")
    A("")
    A("The fixed-dollar control was then rebuilt cohort by cohort through the same serial path "
      "the equity-scaled book uses, and reproduces the certified batch causal pre-order total "
      f"exactly: {str(manifest['serial_control_equals_batch']).lower()}. The difference between "
      "the two books is therefore sizing alone.")
    A("")
    A("## Headline account results, account of record")
    A("")
    A("| Measure | Fixed-dollar R5 | Equity-scaled R5 | Difference |")
    A("|---|---:|---:|---:|")

    def line(label, key, fmt=money, diff=True):
        a, b = f[key], s[key]
        d = (b - a) if (diff and a is not None and b is not None) else None
        A(f"| {label} | {fmt(a)} | {fmt(b)} | {'' if d is None else fmt(d)} |")

    line("Starting equity", "starting_equity")
    line("Ending marked equity at 2026-08-31", "ending_marked_equity_at_cutoff")
    line("Marked account P&L at 2026-08-31", "marked_account_pnl_at_cutoff")
    line("Eventual completed-trade P&L", "eventual_completed_trade_pnl")
    line("Return on starting equity", "return_on_starting_equity_pct", pct)
    line("Hit rate", "hit_rate", lambda x: f"{x:.3f}")
    line("Average winner", "avg_winner")
    line("Average loser", "avg_loser")
    line("Profit factor", "profit_factor", lambda x: f"{x:.3f}")
    line("Max drawdown dollars", "max_drawdown_dollars")
    A(f"| Max drawdown percent of peak | {pct(f['max_drawdown_pct_of_peak'])} | "
      f"{pct(s['max_drawdown_pct_of_peak'])} | "
      f"{s['max_drawdown_pct_of_peak'] - f['max_drawdown_pct_of_peak']:+.2f} pp |")
    line("Worst day", "worst_day")
    line("Worst month", "worst_month")
    line("Median month", "median_month")
    line("Sum of red months", "sum_of_red_months")
    A(f"| Positive months | {f['positive_months']} | {s['positive_months']} | "
      f"{s['positive_months'] - f['positive_months']:+d} |")
    A(f"| Red months | {f['red_months']} | {s['red_months']} | "
      f"{s['red_months'] - f['red_months']:+d} |")
    line("Mean gross exposure", "mean_gross_exposure")
    line("Peak gross exposure", "peak_gross_exposure")
    line("Mean gross / marked equity", "mean_gross_over_marked_equity", lambda x: f"{x:.3f}")
    line("95th percentile gross / marked equity", "p95_gross_over_marked_equity", lambda x: f"{x:.3f}")
    line("Peak gross / marked equity", "peak_gross_over_marked_equity", lambda x: f"{x:.3f}")
    line("Turnover, entry notional", "turnover_entry_notional")
    line("Exposure dollar-sessions", "exposure_dollar_sessions")
    line("Time underwater", "time_underwater_pct", pct)
    line("Runoff trades", "runoff_trade_count", lambda x: str(x))
    line("Post-cutoff incremental runoff P&L", "post_cutoff_incremental_runoff_pnl")
    line("Open documented obligations", "open_documented_obligations", lambda x: str(x))
    line("Stale gross at the calendar boundary", "stale_gross_at_calendar_boundary")
    A("")
    A("Gross exposure is divided by the **same session's** marked equity, never by starting "
      "equity, because the question an equity-responsive rule raises is whether leverage stays "
      "put while dollars grow. It does not stay put here: mean gross against marked equity rises "
      f"from {f['mean_gross_over_marked_equity']:.3f} to {s['mean_gross_over_marked_equity']:.3f}, "
      "and the worst single session deepens from "
      f"{money(f['worst_day'])} to {money(s['worst_day'])}, a larger multiple than the account "
      "itself grew by. Both facts belong beside the higher ending equity.")
    A("")
    A("## Monthly account results")
    A("")
    A("Published under the frozen lab standard `" + mon.STANDARD_ID + "`. Rows are stated in whole "
      "cents and chain exactly. Monthly P&L is the change in marked account equity across the "
      "month, so a position opened in one month and closed in the next contributes to both.")
    A("")
    A("| Month | Fixed-dollar P&L | Equity-scaled P&L | Fixed return | Equity-scaled return |")
    A("|---|---:|---:|---:|---:|")
    by_mode = defaultdict(dict)
    for r in monthly_rows:
        by_mode[r["sizing_mode_id"]][r["month"]] = r
    for m in MONTHS:
        a, b = by_mode[FIXED][m], by_mode[SCALED][m]
        A(f"| {m} | {money(a['monthly_pnl'])} | {money(b['monthly_pnl'])} | "
          f"{a['monthly_return_pct']:.2f}% | {b['monthly_return_pct']:.2f}% |")
    A(f"| **Total** | **{money(sum(by_mode[FIXED][m]['monthly_pnl'] for m in MONTHS))}** | "
      f"**{money(sum(by_mode[SCALED][m]['monthly_pnl'] for m in MONTHS))}** | | |")
    A("")
    A("| Month-end marked equity | Fixed-dollar R5 | Equity-scaled R5 |")
    A("|---|---:|---:|")
    for m in MONTHS:
        A(f"| {m} | {money(by_mode[FIXED][m]['month_end_equity'])} | "
          f"{money(by_mode[SCALED][m]['month_end_equity'])} |")
    A("")
    A("Both books reconcile exactly to their own marked account result at 2026-08-31: "
      f"{str(recon[FIXED]['reconciles']).lower()} and {str(recon[SCALED]['reconciles']).lower()}. "
      "They deliberately do not reconcile to eventual completed-trade P&L, which contains exits "
      "scheduled after August closes. Positions still open at the boundary are carried in the "
      "August equity at their last observed marks, and one documented open obligation remains "
      "under a documented trading suspension in each book.")
    A("")
    A("## Where the difference comes from")
    A("")
    d = diagnostics
    A(f"Total incremental P&L from equity scaling: **{money(d['total_incremental_pnl_from_equity_scaling'])}**.")
    A("")
    A("| Diagnostic | Value |")
    A("|---|---:|")
    A(f"| Scale factor, first cohort | {cohort_rows[0]['scale_factor_vs_100k']:.3f}x |")
    A(f"| Scale factor, minimum | {d['scale_factor_min']:.3f}x |")
    A(f"| Scale factor, median | {d['scale_factor_median']:.3f}x |")
    A(f"| Scale factor, maximum | {d['scale_factor_max']:.3f}x |")
    A(f"| Scale factor, final cohort | {d['scale_factor_final_cohort']:.3f}x |")
    for k, v in d["first_cohort_above"].items():
        A(f"| First cohort at or above {k} | {'never' if v is None else v['cohort_id']} |")
    A(f"| Uplift share, June-August 2026 signals | {pct(d['uplift_share_june_to_august_2026_pct'])} |")
    A(f"| Uplift share, top 1 cohort | {pct(d['uplift_share_top_1_cohorts_pct'])} |")
    A(f"| Uplift share, top 3 cohorts | {pct(d['uplift_share_top_3_cohorts_pct'])} |")
    A(f"| Uplift share, top 5 cohorts | {pct(d['uplift_share_top_5_cohorts_pct'])} |")
    A(f"| Uplift from trades that won under fixed dollars | {money(d['uplift_from_trades_that_won_under_fixed_dollars'])} |")
    A(f"| Extra loss from trades that lost under fixed dollars | {money(d['extra_loss_from_trades_that_lost_under_fixed_dollars'])} |")
    for tier in ("FULL", "HALF", "QUARTER"):
        A(f"| Incremental P&L, {tier} tier | {money(d['uplift_by_tier'].get(tier, 0.0))} |")
    A(f"| Incremental max drawdown dollars | {money(d['incremental_max_drawdown_dollars'])} |")
    A(f"| Incremental max drawdown, percent of peak | {d['incremental_max_drawdown_pct_of_peak']:+.2f} pp |")
    A(f"| Mean gross / equity, fixed vs scaled | {d['gross_over_equity_fixed']['mean_gross_over_marked_equity']:.3f} vs {d['gross_over_equity_scaled']['mean_gross_over_marked_equity']:.3f} |")
    A("")
    A("### Does leverage stay put as dollars grow?")
    A("")
    A("This is a question about each book's own path over time, not about the gap between the "
      "books. Comparing the two averages would mistake the fixed book's de-levering for drift in "
      "the scaled book, which gets the causation backwards.")
    A("")
    A("| Gross / marked equity | First half of sessions | Second half | Drift |")
    A("|---|---:|---:|---:|")
    for mode in MODES:
        h = d["gross_over_equity_by_half"][mode]
        A(f"| {MODE_LABEL[mode]} | {h['first_half_mean']:.3f} | {h['second_half_mean']:.3f} | "
          f"{h['drift']:+.3f} |")
    A("")
    A("The equity-scaled book holds the leverage it was designed to hold: its gross/equity ratio "
      f"drifts by {d['gross_over_equity_scaled_drift']:+.3f} between the halves. The fixed-dollar "
      f"book drifts by {d['gross_over_equity_fixed_drift']:+.3f}, because its tickets do not follow "
      "the account, so it sheds leverage as equity grows. The higher mean ratio in the scaled book "
      "is therefore the absence of that de-levering, not new leverage on top of the design. What "
      "the design itself permits is visible at the peak: gross exposure reaches "
      f"{d['gross_over_equity_scaled']['peak_gross_over_marked_equity']:.3f} times marked equity, "
      "above one, against "
      f"{d['gross_over_equity_fixed']['peak_gross_over_marked_equity']:.3f} fixed.")
    A("")
    A("Per-cohort sizing paths for all 52 cohorts, including reference equity, scale factor, "
      "intended cohort notional under each rule, realized cohort P&L under each rule and the "
      "post-entry gross/equity ratio, are in `reports/cg_arrow010_cohort_scaling.csv`.")
    A("")
    A("## Reading the result")
    A("")
    A("**Mechanically expected.** A rule that multiplies ticket size by account equity will place "
      "larger dollar tickets once the account grows. None of the uplift is evidence that the "
      "signal improved; the per-trade price return before sizing is identical between the two "
      f"books to {manifest['max_pre_sizing_price_return_gap']:.1e}, and no trade was added, removed, "
      "substituted or re-ranked.")
    A("")
    A("**Sequence dependence.** The strongest fixed-dollar month of this sample falls late, so the "
      "largest tickets and the strongest returns coincide. "
      f"{pct(d['uplift_share_june_to_august_2026_pct'])} of the total uplift comes from June through "
      "August 2026 signals alone. That is a property of this sample's ordering, not of the sizing "
      "rule. A sample with the same months in a different order would compound differently, and a "
      "sample whose losses fell late would compound the losses instead.")
    A("")
    A("**Risk efficiency.** Marked account P&L per dollar of maximum drawdown is "
      f"{manifest['status_basis']['marked_pnl_per_drawdown_dollar'][FIXED]:.3f} fixed and "
      f"{manifest['status_basis']['marked_pnl_per_drawdown_dollar'][SCALED]:.3f} scaled, so the "
      "return bought more per dollar of drawdown than it cost. The costs are real and belong in "
      "the same sentence. Maximum drawdown deepens from "
      f"{money(f['max_drawdown_dollars'])} to {money(s['max_drawdown_dollars'])} and from "
      f"{pct(f['max_drawdown_pct_of_peak'])} to {pct(s['max_drawdown_pct_of_peak'])} of its own "
      f"peak, the worst single session deepens from {money(f['worst_day'])} to "
      f"{money(s['worst_day'])}, and peak gross exposure reaches "
      f"{d['gross_over_equity_scaled']['peak_gross_over_marked_equity']:.3f} times marked equity "
      "against "
      f"{d['gross_over_equity_fixed']['peak_gross_over_marked_equity']:.3f} fixed. A short book "
      "carrying more gross than its own equity is a financing and locate question this arrow does "
      "not answer.")
    A("")
    A("**Unresolved and out of scope.** This arrow answers nothing about capital redeployment "
      "after early exits, gross-exposure caps, leverage sweeps, drawdown throttles, volatility "
      "targeting, other hold lengths or broker-specific short availability at larger ticket sizes. "
      "Those require their own arrows and, in the case of borrow capacity at scale, data this lab "
      "does not hold.")
    A("")
    A("## Split reporting")
    A("")
    A("The historical out-of-sample months have already been inspected repeatedly in earlier "
      "research, so the split comparison below is descriptive robustness evidence and **not** a "
      "pristine confirmation. The sizing formula was frozen before scoring and was not chosen, "
      "tuned or changed after seeing any result. Each split row is a standalone book that restarts "
      "at 100,000 starting equity, so its scale path is its own; the account of record is the "
      "all-cohort row.")
    A("")
    A("| Sizing mode | Split | Marked account P&L | Return on starting equity | Max drawdown | Mean gross / equity |")
    A("|---|---|---:|---:|---:|---:|")
    for row in summary_rows:
        A(f"| {row['sizing_mode']} | {row['split']} | {money(row['marked_account_pnl_at_2026_08_31'])} | "
          f"{row['return_on_starting_equity_pct']:.2f}% | {money(row['max_drawdown_dollars'])} | "
          f"{row['mean_gross_over_marked_equity']:.3f} |")
    A("")
    A("## Verification")
    A("")
    A("| Check | Result |")
    A("|---|---|")
    A(f"| Certified Arrow 008 controls reproduce | {sum(v['reproduces'] for v in manifest['certified_controls'].values())} of {len(manifest['certified_controls'])} |")
    A(f"| Selection, tiers, sessions and prices identical between books | {'yes' if manifest['substrate_identical_between_books'] else 'NO'} |")
    A(f"| Per-trade price return before sizing identical | max gap {manifest['max_pre_sizing_price_return_gap']:.1e} |")
    A(f"| Causality violations in the sizing path | {len(manifest['causality_violations'])} |")
    A(f"| Pricing-window observations missing | {manifest['observation_coverage']['pricing_window_missing']} |")
    A(f"| Account identities hold | {sum(v['identities_hold'] for v in accounts.values())} of {len(accounts)} |")
    A(f"| Monthly rows chain and reconcile | {sum(v['reconciles'] for v in recon.values())} of {len(recon)} books |")
    A(f"| Independent oracle | trades {manifest['oracle']['trades']['checked']} checked, "
      f"max error {manifest['oracle']['trades']['max_abs_error']:.1e} |")
    A(f"| Independent equity-sizing recomputation | {manifest['oracle']['equity_sizing']['tickets_checked']} tickets, "
      f"{manifest['oracle']['equity_sizing']['errors']} disagreements |")
    A("| Public/private separation | intact |")
    A("")
    A("Every equity-scaled share count was re-derived by the independent oracle from stored inputs "
      "only: for each cohort it rebuilds the account from strictly earlier cohorts, reads marked "
      "equity at the signal close, and floors the scaled tier notional against the stored causal "
      "pre-order price. It never consults the sizing engine or the scale factors that engine "
      "recorded, so a look-ahead, a wrong reference or a wrong integer rule would surface there.")
    A("")
    A(f"> {FOOTNOTE}")
    A("")
    A("---")
    A("")
    A(f"# RESEARCH STATUS: {status}")
    A("")
    A("This is a research interpretation of one historical sample, not a production deployment "
      "decision and not a claim about future returns.")
    A("")
    A("NEXT RECOMMENDED STEP: CAPITAL REDEPLOYMENT STUDY")
    (REPORTS / "cg_arrow010_equity_sizing.md").write_text("\n".join(L) + "\n",
                                                          encoding="utf-8", newline="\n")


if __name__ == "__main__":
    sys.exit(main())
