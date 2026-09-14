"""CG Arrow 007 H1-H10 census on the certified frozen ledger.

Stages:
  is    score every horizon on IS-owned books only and write the pre-reveal freeze
  oos   reveal all OOS cells in one batch, then replay ALL as an operational account

Repairs carried in from the Arrow 006 audit:
  * risk metrics come from split-owned books, so an IS drawdown never contains an
    OOS-owned position and vice versa;
  * same-trade horizon increments carry an explicit state for every ticket, so a trade
    that becomes trapped at a longer horizon is reported as a transition rather than
    silently dropped from the sample;
  * September runoff, the calendar account to 2026-08-31 and still-open documented-event
    obligations are reported separately, and every per-session figure names its denominator;
  * both predeclared quantity panels are scored; neither is chosen after seeing OOS.

Usage: python scripts/cg_arrow007_horizons.py <is|oos> [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    FEATS, INDEX, SCORE, VERIFY_ROOT, digest, dump_json, load_summaries, present, read_json,
    set_vendor_status, split_of, stamp,
)
from verification.r4r5_replay import COMPLETED, needs_for, replay  # noqa: E402

WORK = VERIFY_ROOT / "work"
HANDOFF7 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow007"
FREEZE = REPORTS / "cg_arrow007_horizon_freeze.json"
FAMS = ("PARENT", "R4", "R5")
PANELS = {"LEGACY_FILL_QTY": "fill", "CAUSAL_PREORDER_QTY": "preorder"}
HORIZONS = tuple(range(1, 11))
OPEN_STATES = ("OPEN_AT_BOUNDARY_DOCUMENTED_HALT", "NO_ENTRY_DOCUMENTED_TRADING_EVENT")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def load_certified():
    st = read_json(WORK / "a7_baseline_state.json")
    out = []
    for c in st["certified_cohorts"]:
        out.append({"signal": date.fromisoformat(c["signal_iso"]), "signal_iso": c["signal_iso"],
                    "split": c["split"], "fill": date.fromisoformat(c["fill"]), "rows": c["rows"],
                    "n_field": c["n_field"], "field_ceiling": None,
                    "ranking_scope": c["ranking_scope"]})
    return out, st


def state_of(t: dict) -> str:
    if t["status"] in COMPLETED:
        return "COMPLETED"
    if t["status"] in OPEN_STATES:
        return "DOCUMENTED_EVENT_OPEN"
    if t["status"].startswith("BLOCKED_STRUCTURAL"):
        return "STRUCTURAL_BLOCK"
    if t["status"].startswith("MISSED"):
        return "NO_ENTRY"
    return "UNRESOLVED"


def cell_metrics(fam, hold, panel, book, split) -> dict:
    ts = book["trades"]
    ver = [t for t in ts if t["status"] in COMPLETED]
    daily = book["daily"]
    eq, peak, dd, ddp, under = [], 100000.0, 0.0, 0.0, 0
    prev = 100000.0
    changes, monthly = [], defaultdict(float)
    for r in daily:
        e = r["equity"]
        changes.append(e - prev)
        monthly[r["date"][:7]] += e - prev
        prev = e
        peak = max(peak, e)
        dd = min(dd, e - peak)
        ddp = min(ddp, e / peak - 1)
        under += e < peak - 1e-8
        eq.append(e)
    wins = [t["modeled_net"] for t in ver if t["modeled_net"] > 0]
    losses = [t["modeled_net"] for t in ver if t["modeled_net"] < 0]
    reds = [v for v in monthly.values() if v < 0]
    gross = [r["gross_exposure"] for r in daily]
    runoff = {t["ticket_id"] for t in ver if t.get("exit_after_cutoff") in (True, "True")}
    states = Counter(state_of(t) for t in ts)
    return {
        "family": fam, "horizon": hold, "panel": panel, "split": split,
        "intended": len(ts), "filled": sum(1 for t in ts if t.get("quantity")), "completed": len(ver),
        "documented_event_open": states["DOCUMENTED_EVENT_OPEN"], "no_entry": states["NO_ENTRY"],
        "unresolved": states["UNRESOLVED"], "structural_block": states["STRUCTURAL_BLOCK"],
        "wins": len(wins), "losses": len(losses), "flats": len(ver) - len(wins) - len(losses),
        "hit_rate": len(wins) / len(ver) if ver else None,
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "payoff_ratio": ((sum(wins) / len(wins)) / abs(sum(losses) / len(losses))) if wins and losses else None,
        "profit_factor": (sum(wins) / -sum(losses)) if losses else None,
        "gross_pnl": sum(t["gross_pnl"] for t in ver), "modeled_net": sum(t["modeled_net"] for t in ver),
        "net_double_spread": sum(t["modeled_net_double_spread"] for t in ver),
        "net_borrow_10": sum(t["net_borrow_10"] for t in ver),
        "net_borrow_30": sum(t["net_borrow_30"] for t in ver),
        "net_through_cutoff": sum(t["modeled_net"] for t in ver if t["ticket_id"] not in runoff),
        "september_runoff_net": sum(t["modeled_net"] for t in ver if t["ticket_id"] in runoff),
        "september_runoff_trades": len(runoff),
        "per_session_denominator": len(daily),
        "per_session_basis": f"{len(daily)} account sessions of the {split}-owned book",
        "net_per_session": sum(t["modeled_net"] for t in ver) / len(daily) if daily else None,
        "max_dd_dollars": dd, "max_dd_percent": ddp, "worst_day": min(changes, default=0.0),
        "time_underwater_sessions": under,
        "red_calendar_months": len(reds), "red_month_loss_sum": sum(reds),
        "worst_month": min(monthly.values()) if monthly else None,
        "median_month": statistics.median(monthly.values()) if monthly else None,
        "mean_gross": sum(gross) / len(gross), "peak_gross": max(gross),
        "exposure_dollar_days": sum(gross),
        "turnover_entry_notional": sum(t["quantity"] * t["entry_price"] for t in ts if t.get("quantity")),
        "tier_full": sum(t["modeled_net"] for t in ver if t["size_tier"] == "FULL"),
        "tier_half": sum(t["modeled_net"] for t in ver if t["size_tier"] == "HALF"),
        "tier_quarter": sum(t["modeled_net"] for t in ver if t["size_tier"] == "QUARTER"),
        "aug31_equity": daily[-1]["equity"] if daily else None,
        "aug31_open_tickets": daily[-1]["open_tickets"] if daily else None,
    }


def increments(books, fam, panel, split) -> list[dict]:
    """Same-trade H(n)->H(n+1) economics with explicit state transitions, never a silent drop."""
    out = []
    for h in range(1, 10):
        a = {t["ticket_id"]: t for t in books[(fam, panel, split, h)]["trades"]}
        b = {t["ticket_id"]: t for t in books[(fam, panel, split, h + 1)]["trades"]}
        keys = sorted(set(a) & set(b))
        paired = [k for k in keys if state_of(a[k]) == "COMPLETED" and state_of(b[k]) == "COMPLETED"]
        to_open = [k for k in keys if state_of(a[k]) == "COMPLETED" and state_of(b[k]) != "COMPLETED"]
        to_closed = [k for k in keys if state_of(a[k]) != "COMPLETED" and state_of(b[k]) == "COMPLETED"]
        price = sum(b[k]["gross_pnl"] - a[k]["gross_pnl"] for k in paired)
        cost = sum((a[k]["exit_commission"] + a[k]["exit_spread"])
                   - (b[k]["exit_commission"] + b[k]["exit_spread"]) for k in paired)
        borrow = sum((b[k]["modeled_net"] - b[k]["net_borrow_10"])
                     - (a[k]["modeled_net"] - a[k]["net_borrow_10"]) for k in paired)
        out.append({
            "family": fam, "panel": panel, "split": split, "step": f"H{h}->H{h + 1}",
            "tickets_in_ledger": len(keys), "paired_completed": len(paired),
            "completed_to_open_transitions": len(to_open),
            "completed_to_open_pnl_withdrawn": -sum(a[k]["modeled_net"] for k in to_open),
            "open_to_completed_transitions": len(to_closed),
            "open_to_completed_pnl_added": sum(b[k]["modeled_net"] for k in to_closed),
            "paired_price_movement": price, "paired_exit_cost_difference": cost,
            "paired_additional_borrow_at_10pct": -borrow,
            "paired_net_change": sum(b[k]["modeled_net"] - a[k]["modeled_net"] for k in paired),
            "total_book_net_change": (sum(t["modeled_net"] for t in b.values() if state_of(t) == "COMPLETED")
                                      - sum(t["modeled_net"] for t in a.values() if state_of(t) == "COMPLETED")),
        })
    return out


def age_curve(books, fam, panel, split) -> list[dict]:
    base = books[(fam, panel, split, 10)]["trades"]
    ids = {t["ticket_id"] for t in base if t.get("quantity")}
    rows = [{"family": fam, "panel": panel, "split": split, "holding_age": 0, "tickets": len(ids),
             "cumulative_net_completed": sum(-(t.get("entry_commission") or 0) - (t.get("entry_spread") or 0)
                                             for t in base if t["ticket_id"] in ids),
             "completed": 0,
             "note": "cross-trade holding-age curve, not an account equity curve; H0 is entry cost state"}]
    for h in HORIZONS:
        ts = [t for t in books[(fam, panel, split, h)]["trades"] if t["ticket_id"] in ids]
        done = [t for t in ts if state_of(t) == "COMPLETED"]
        rows.append({"family": fam, "panel": panel, "split": split, "holding_age": h,
                     "tickets": len(ts), "completed": len(done),
                     "cumulative_net_completed": sum(t["modeled_net"] for t in done), "note": ""})
    return rows


def build(cohort_list, summaries, splits) -> dict:
    books = {}
    for fam in FAMS:
        for panel, qty in PANELS.items():
            for split in splits:
                subset = [c for c in cohort_list if split == "ALL" or c["split"] == split]
                for h in HORIZONS:
                    books[(fam, panel, split, h)] = replay(
                        fam, subset, summaries, hold=h, quantity=qty,
                        stage=f"R2_{panel}_{split}_H{h:02d}")
    return books


def load_inputs(args):
    cl, st = load_certified()
    if st["gate"] != "OPEN":
        note(f"baseline gate is {st['gate']}; the horizon census must not run")
        sys.exit(3)
    set_vendor_status(rep.session_status_map())
    needs = set()
    for c in cl:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in c["rows"]:
            for d in FEATS[i - 20: fi + 11]:
                needs.add((d.isoformat(), h["symbol"]))
    summaries = load_summaries(needs, args.workers)
    status = rep.session_status_map()
    absent = [(s, iso) for (iso, s) in needs if not present(summaries.get((iso, s)))
              and status.get((s, iso)) != "DOCUMENTED_NO_TRADING"]
    note(f"horizon inputs: {len(needs)} observations, absent={len(absent)}")
    if absent:
        needed = {}
        for s, iso in absent:
            needed.setdefault(s, set()).add(date.fromisoformat(iso))
        reqs = rep.plan_requests(needed)
        note(f"acquiring {len(reqs)} windows so no horizon is scored on a smaller sample")
        rep.acquire(reqs, concurrency=8)
        rep.invalidate_summaries({d for ds in needed.values() for d in ds})
        set_vendor_status(rep.session_status_map())
        summaries.update(load_summaries({(d.isoformat(), s) for s, ds in needed.items() for d in ds},
                                        args.workers))
    return cl, st, summaries


def stage_is(args) -> int:
    cl, st, summaries = load_inputs(args)
    books = build(cl, summaries, ("IS",))
    gaps = {f"{fam}/{panel}/H{h}": sum(1 for t in books[(fam, panel, 'IS', h)]["trades"]
                                       if state_of(t) in ("UNRESOLVED", "STRUCTURAL_BLOCK"))
            for fam in FAMS for panel in PANELS for h in HORIZONS}
    bad = {k: v for k, v in gaps.items() if v}
    note(f"IS endpoint completeness: {'COMPLETE' if not bad else bad}")
    if bad:
        note("refusing to score horizons on an incomplete endpoint set")
        return 3
    cells = [cell_metrics(fam, h, panel, books[(fam, panel, "IS", h)], "IS")
             for fam in FAMS for panel in PANELS for h in HORIZONS]
    for c in [x for x in cells if x["panel"] == "LEGACY_FILL_QTY"]:
        note(f"IS {c['family']:6} H{c['horizon']:02d} net={c['modeled_net']:12,.2f} "
             f"hit={c['hit_rate']:.3f} dd={c['max_dd_dollars']:11,.2f} "
             f"$/sess={c['net_per_session']:8.2f}")
    inc = [r for fam in FAMS for panel in PANELS for r in increments(books, fam, panel, "IS")]
    curve = [r for fam in FAMS for panel in PANELS for r in age_curve(books, fam, panel, "IS")]

    legacy = [c for c in cells if c["panel"] == "LEGACY_FILL_QTY"]
    best = {fam: max((c for c in legacy if c["family"] == fam), key=lambda x: x["modeled_net"])["horizon"]
            for fam in FAMS}
    ride = {fam: max((c for c in legacy if c["family"] == fam), key=lambda x: x["max_dd_dollars"])["horizon"]
            for fam in FAMS}
    h10 = {fam: next(c for c in legacy if c["family"] == fam and c["horizon"] == 10)["modeled_net"]
           for fam in FAMS}
    interpretation = {
        "profit_first_is_horizon": best, "ride_first_is_horizon": ride, "is_h10_reference_net": h10,
        "preferred_horizon": best,
        "primary_claimed_benefit": "higher in-sample modeled net at the preferred horizon than that family's H10",
        "tolerable_downside": ("a preferred horizon is not confirmed if its OOS modeled net is below that "
                               "family's OOS H10, or if its OOS maximum drawdown is more than 20% worse"),
        "selection_basis": "LEGACY_FILL_QTY in-sample only; the causal panel is a robustness view, not a search",
        "note": "ten horizons on one entry ledger are one correlated family, not ten independent discoveries",
    }
    freeze = {
        "status": "FROZEN_PRE_OOS", "timestamp": stamp(),
        "baseline_gate": st["gate"], "r2_entry_ledger_sha256": st["r2_entry_ledger_sha256"],
        "grid": {"families": list(FAMS), "horizons": list(HORIZONS), "panels": list(PANELS),
                 "cells_per_panel": len(FAMS) * len(HORIZONS)},
        "rules": {
            "hn": "n exchange sessions after the fill session; fill = H0",
            "schedule": "nominal Wednesday signal, rolled back to the prior session if closed; "
                        "entry is the first session after the signal",
            "exit_convention": "final regular-hours minute close, or that session's last regular-hours "
                               "print when the security did not trade in the final minute",
            "entries": "identical certified R2 entries, shares, entry observations and entry costs at "
                       "every horizon inside a panel",
            "capital": "no reinvestment, replacement entry, compounding or exposure normalisation",
            "costs": "$0.005/share/side commission and a max($0.01, 0.001*price)/side spread proxy; "
                     "0/10/30% annualised borrow scenarios on marked gross by actual calendar days; "
                     "dividends, locate and financing unknown and null",
            "risk_accounting": "IS and OOS metrics come from split-owned books; ALL is a separate view",
        },
        "is_months": ["2025-09", "2025-11", "2026-01", "2026-03", "2026-05", "2026-07"],
        "oos_months": ["2025-10", "2025-12", "2026-02", "2026-04", "2026-06", "2026-08"],
        "oos_procedure": "one batch revealing every OOS cell of both panels; no post-reveal change",
        "is_cells": cells, "is_increments": inc, "is_age_curve": curve,
        "is_interpretation": interpretation,
        "action_table_sha256": digest(REPORTS / "cg_arrow007_corporate_actions.json"),
        "code_sha256": {p: digest(REPO_ROOT / p) for p in
                        ("src/verification/r4r5_replay.py", "src/verification/r4r5_rank.py",
                         "src/verification/r4r5_data.py", "src/verification/r4r5_schedule.py",
                         "scripts/cg_arrow007_horizons.py")},
        "log": LOG}
    dump_json(FREEZE, freeze)
    exp.write_csv(REPORTS / "cg_arrow007_horizons_is.csv", cells)
    note(f"freeze written: preferred={best} ride_first={ride}")
    return 0


def stage_oos(args) -> int:
    if not FREEZE.exists():
        note("no freeze; OOS reveal refused")
        return 3
    freeze = read_json(FREEZE)
    if freeze["status"] != "FROZEN_PRE_OOS":
        note(f"freeze status {freeze['status']}; the single-batch reveal is already consumed")
        return 3
    rel = FREEZE.relative_to(REPO_ROOT).as_posix()
    try:
        committed = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=REPO_ROOT)
    except subprocess.CalledProcessError:
        note("the freeze must be committed before the OOS reveal")
        return 3
    if committed.replace(b"\r\n", b"\n") != FREEZE.read_bytes().replace(b"\r\n", b"\n"):
        note("the freeze must be committed unchanged before the OOS reveal")
        return 3
    cl, st, summaries = load_inputs(args)
    if st["r2_entry_ledger_sha256"] != freeze["r2_entry_ledger_sha256"]:
        note("the entry ledger changed since the freeze; reveal refused")
        return 3
    books = build(cl, summaries, ("IS", "OOS", "ALL"))
    cells = [cell_metrics(fam, h, panel, books[(fam, panel, split, h)], split)
             for fam in FAMS for panel in PANELS for split in ("IS", "OOS", "ALL") for h in HORIZONS]
    base = read_json(REPORTS / "cg_arrow007_manifest.json")["split_owned_books"]
    ident = {}
    for fam in FAMS:
        for panel in PANELS:
            c = next(x for x in cells if x["family"] == fam and x["panel"] == panel
                     and x["horizon"] == 10 and x["split"] == "ALL")
            locked = base[f"{fam}/R2/{panel}/ALL"]["modeled_net"]
            ident[f"{fam}/{panel}"] = {"h10_all_net": c["modeled_net"], "locked_baseline_net": locked,
                                       "difference": c["modeled_net"] - locked}
    note("H10 identity vs frozen baseline: " + json.dumps(
        {k: round(v["difference"], 6) for k, v in ident.items()}))
    for c in [x for x in cells if x["split"] == "OOS" and x["panel"] == "LEGACY_FILL_QTY"]:
        note(f"OOS {c['family']:6} H{c['horizon']:02d} net={c['modeled_net']:12,.2f} "
             f"hit={c['hit_rate']:.3f} dd={c['max_dd_dollars']:11,.2f} "
             f"$/sess={c['net_per_session']:8.2f}")
    inc = [r for fam in FAMS for panel in PANELS for split in ("IS", "OOS", "ALL")
           for r in increments(books, fam, panel, split)]
    curve = [r for fam in FAMS for panel in PANELS for split in ("IS", "OOS", "ALL")
             for r in age_curve(books, fam, panel, split)]
    pref = freeze["is_interpretation"]["preferred_horizon"]
    confirm = {}
    for fam in FAMS:
        p = pref[fam]
        po = next(x for x in cells if x["family"] == fam and x["horizon"] == p
                  and x["split"] == "OOS" and x["panel"] == "LEGACY_FILL_QTY")
        h10 = next(x for x in cells if x["family"] == fam and x["horizon"] == 10
                   and x["split"] == "OOS" and x["panel"] == "LEGACY_FILL_QTY")
        better = po["modeled_net"] > h10["modeled_net"]
        dd_ok = po["max_dd_dollars"] >= 1.2 * h10["max_dd_dollars"]
        confirm[fam] = {"preferred_horizon": p, "oos_net": po["modeled_net"],
                        "oos_h10_net": h10["modeled_net"],
                        "oos_increment": po["modeled_net"] - h10["modeled_net"],
                        "oos_dd": po["max_dd_dollars"], "oos_h10_dd": h10["max_dd_dollars"],
                        "verdict": ("REPEATED" if (better and dd_ok) else
                                    "NOT REPEATED" if not better else
                                    "REPEATED ON PROFIT, DRAWDOWN TOLERANCE BREACHED")}
    note("confirmation: " + json.dumps(confirm, default=str))
    wide, tidy = [], []
    for fam in FAMS:
        w, t = exp.horizon_paths(fam, cl, summaries)
        wide.extend(w)
        tidy.extend(t)
    exp.write_csv(HANDOFF7 / "r4r5_horizon_trade_paths.csv", wide)
    exp.write_csv(HANDOFF7 / "r4r5_horizon_trade_paths_tidy.csv", tidy)
    exp.write_csv(HANDOFF7 / "r4r5_horizon_summary.csv", cells)
    exp.write_csv(REPORTS / "cg_arrow007_horizons.csv", cells)
    exp.write_csv(REPORTS / "cg_arrow007_horizon_increments.csv", inc)
    exp.write_csv(REPORTS / "cg_arrow007_holding_age_curve.csv", curve)
    freeze.update({"status": "OOS_REVEALED", "oos_revealed_at": stamp(), "cells": cells,
                   "h10_baseline_identity": ident, "confirmation": confirm,
                   "increments": inc, "age_curve": curve,
                   "local_csvs": {n: {"path": (HANDOFF7 / n).as_posix(), "sha256": digest(HANDOFF7 / n)}
                                  for n in ("r4r5_horizon_trade_paths.csv",
                                            "r4r5_horizon_trade_paths_tidy.csv",
                                            "r4r5_horizon_summary.csv")},
                   "log": freeze.get("log", []) + LOG})
    dump_json(FREEZE, freeze)
    note("OOS reveal complete")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["is", "oos"])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    return stage_is(args) if args.stage == "is" else stage_oos(args)


if __name__ == "__main__":
    sys.exit(main())
