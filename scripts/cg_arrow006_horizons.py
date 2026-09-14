"""CG Arrow 006 H1-H10 census. Runs only when the baseline gate is OPEN.

Stages:
  is     score the 30 in-sample cells and write the pre-reveal freeze
  oos    reveal all 30 out-of-sample cells in one batch, plus the all-signal replay

Every cell clones the same verified R2 entries, initial shares, entry observations and
entry costs. Only the scheduled exit age changes. No reinvestment, replacement entry,
compounding or exposure normalisation when a shorter hold frees cash.

Usage: python scripts/cg_arrow006_horizons.py <stage> [--workers 8]
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
from verification.r4r5_data import (  # noqa: E402
    FEATS, INDEX, RANKS_PATH, SCORE, VERIFY_ROOT, digest, dump_json, load_summaries, present,
    read_json, split_of, stamp,
)
from verification.r4r5_replay import COMPLETED, VERIFIED, needs_for, replay  # noqa: E402

WORK = VERIFY_ROOT / "work"
HANDOFF6 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow006"
FREEZE = REPORTS / "cg_arrow006_horizon_freeze.json"
FAMS = ("PARENT", "R4", "R5")
HORIZONS = tuple(range(1, 11))
IS_SESSIONS = sum(1 for d in SCORE if split_of(d) == "IS")
OOS_SESSIONS = sum(1 for d in SCORE if split_of(d) == "OOS")
ALL_SESSIONS = len(SCORE)
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def load_corrected() -> list[dict]:
    st = read_json(WORK / "baseline_state.json")
    out = []
    for c in st["corrected_cohorts"]:
        signal = date.fromisoformat(c["signal_iso"])
        out.append({"signal": signal, "signal_iso": c["signal_iso"], "split": c["split"],
                    "fill": date.fromisoformat(c["fill"]), "rows": c["rows"], "n_field": c["n_field"],
                    "field_ceiling": c["field_ceiling"], "ranking_scope": c["ranking_scope"]})
    return out, st


def denominator(split: str) -> tuple[int, str]:
    if split == "IS":
        return IS_SESSIONS, f"{IS_SESSIONS} IS signal-month account sessions"
    if split == "OOS":
        return OOS_SESSIONS, f"{OOS_SESSIONS} OOS signal-month account sessions"
    return ALL_SESSIONS, f"{ALL_SESSIONS} account sessions (2025-09-02..2026-08-31)"


def cell_metrics(fam: str, hold: int, book: dict, split: str) -> dict:
    trades = [t for t in book["trades"] if split == "ALL" or t["split"] == split]
    ver = [t for t in trades if t["status"] in COMPLETED]
    filled = [t for t in trades if t.get("quantity")]
    wins = [t["modeled_net"] for t in ver if t["modeled_net"] > 0]
    losses = [t["modeled_net"] for t in ver if t["modeled_net"] < 0]
    daily = [r for r in book["daily"] if split == "ALL" or split_of(date.fromisoformat(r["date"])) == split]
    # continuous account walk over every session, including flat ones
    eq, peak, dd, dd_pct, underwater = [], 100000.0, 0.0, 0.0, 0
    prev = 100000.0
    day_changes = []
    for r in book["daily"]:
        e = r["equity"]
        day_changes.append((r["date"], e - prev))
        prev = e
        peak = max(peak, e)
        dd = min(dd, e - peak)
        dd_pct = min(dd_pct, e / peak - 1)
        underwater += e < peak - 1e-8
        eq.append(e)
    scoped = [(d, c) for d, c in day_changes if split == "ALL" or split_of(date.fromisoformat(d)) == split]
    monthly = defaultdict(float)
    for d, c in day_changes:
        monthly[d[:7]] += c
    reds = [v for v in monthly.values() if v < 0]
    n, basis = denominator(split)
    gross = [r["gross_exposure"] for r in book["daily"]]
    closed = sum(t["modeled_net"] for t in ver)
    open_rows = [t for t in trades if t["status"].startswith("UNRESOLVED")]
    return {
        "family": fam, "horizon": hold, "split": split,
        "intended": len(trades), "filled": len(filled), "completed": len(ver),
        "wins": len(wins), "losses": len(losses), "flats": len(ver) - len(wins) - len(losses),
        "hit_rate": len(wins) / len(ver) if ver else None,
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "payoff_ratio": (sum(wins) / len(wins)) / abs(sum(losses) / len(losses)) if wins and losses else None,
        "profit_factor": (sum(wins) / -sum(losses)) if losses else None,
        "gross_pnl": sum(t["gross_pnl"] for t in ver),
        "modeled_net": closed,
        "net_double_spread": sum(t["modeled_net_double_spread"] for t in ver),
        "net_borrow_10": sum(t["net_borrow_10"] for t in ver),
        "net_borrow_30": sum(t["net_borrow_30"] for t in ver),
        "per_session": closed / n, "per_session_basis": basis,
        "closed_trade_pnl": closed, "open_or_runoff_trades": len(open_rows),
        "max_dd_dollars": dd, "max_dd_percent": dd_pct,
        "worst_day": min((c for _, c in scoped), default=0.0),
        "time_underwater_sessions": underwater,
        "red_calendar_months": len(reds), "red_month_loss_sum": sum(reds),
        "worst_month": min(monthly.values()) if monthly else None,
        "median_month": statistics.median(monthly.values()) if monthly else None,
        "mean_gross": sum(gross) / len(gross), "peak_gross": max(gross),
        "exposure_dollar_days": sum(gross),
        "turnover_entry_notional": sum(t["quantity"] * t["entry_price"] for t in filled),
        "utilization_mean_gross_over_equity": (sum(gross) / len(gross)) / 100000.0,
        "tier_contribution": {k: sum(t["modeled_net"] for t in ver if t["size_tier"] == k)
                              for k in ("FULL", "HALF", "QUARTER")},
        "avg_holding_calendar_days": (sum(t["holding_calendar_days"] for t in ver) / len(ver)) if ver else None,
    }


def same_trade_increments(books: dict, fam: str, split: str) -> list[dict]:
    """Paired H(n)->H(n+1) economics on identical trades, price versus cost separated."""
    out = []
    for h in range(1, 10):
        a = {t["ticket_id"]: t for t in books[(fam, h)]["trades"] if t["status"] in COMPLETED}
        b = {t["ticket_id"]: t for t in books[(fam, h + 1)]["trades"] if t["status"] in COMPLETED}
        keys = [k for k in a if k in b and (split == "ALL" or a[k]["split"] == split)]
        price = sum(b[k]["gross_pnl"] - a[k]["gross_pnl"] for k in keys)
        cost = sum((a[k]["exit_commission"] + a[k]["exit_spread"]) - (b[k]["exit_commission"] + b[k]["exit_spread"])
                   for k in keys)
        borrow10 = sum((b[k]["modeled_net"] - b[k]["net_borrow_10"]) - (a[k]["modeled_net"] - a[k]["net_borrow_10"])
                       for k in keys)
        out.append({"family": fam, "split": split, "step": f"H{h}->H{h+1}", "paired_trades": len(keys),
                    "price_movement": price, "exit_cost_difference": cost,
                    "additional_borrow_at_10pct": -borrow10,
                    "net_change": sum(b[k]["modeled_net"] - a[k]["modeled_net"] for k in keys)})
    return out


def holding_age_curve(books: dict, fam: str, split: str) -> list[dict]:
    """Cross-trade average cumulative economics by holding age. Not an account equity curve."""
    rows = []
    base = [t for t in books[(fam, 10)]["trades"] if t["status"] in COMPLETED
            and (split == "ALL" or t["split"] == split)]
    ids = {t["ticket_id"] for t in base}
    rows.append({"family": fam, "split": split, "holding_age": 0, "trades": len(ids),
                 "cumulative_net": sum(-(t["entry_commission"] + t["entry_spread"]) for t in base),
                 "note": "H0 is the entry and entry-cost state, not a round trip"})
    for h in HORIZONS:
        ts = [t for t in books[(fam, h)]["trades"] if t["ticket_id"] in ids and t["status"] in COMPLETED]
        rows.append({"family": fam, "split": split, "holding_age": h, "trades": len(ts),
                     "cumulative_net": sum(t["modeled_net"] for t in ts), "note": ""})
    return rows


def build_books(corrected, summaries) -> dict:
    books = {}
    for fam in FAMS:
        for h in HORIZONS:
            books[(fam, h)] = replay(fam, corrected, summaries, hold=h, quantity="fill", stage=f"R2_H{h:02d}")
    return books


def load_all(args):
    corrected, st = load_corrected()
    if st["gate"] != "OPEN":
        note(f"baseline gate is {st['gate']}; horizon census must not run")
        sys.exit(3)
    needs = set()
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in c["rows"]:
            for d in FEATS[i - 20: fi + 11]:
                needs.add((d.isoformat(), h["symbol"]))
    summaries = load_summaries(needs, args.workers)
    missing = [k for k, v in summaries.items() if not present(v)]
    note(f"horizon inputs: {len(needs)} observations, absent={len(missing)}")
    return corrected, st, summaries


def stage_is(args) -> int:
    corrected, st, summaries = load_all(args)
    books = build_books(corrected, summaries)
    # every endpoint of every horizon must be priced before comparing horizons
    gaps = {f"{fam}/H{h}": sum(1 for t in books[(fam, h)]["trades"] if t["status"].startswith(("UNRESOLVED", "MISSED")))
            for fam in FAMS for h in HORIZONS}
    bad = {k: v for k, v in gaps.items() if v}
    note(f"endpoint completeness across all 30 cells: {'COMPLETE' if not bad else bad}")
    if bad:
        note("refusing to score horizons on an incomplete endpoint set")
        return 3
    cells = [cell_metrics(fam, h, books[(fam, h)], "IS") for fam in FAMS for h in HORIZONS]
    for c in cells:
        note(f"IS {c['family']} H{c['horizon']:02d} net={c['modeled_net']:10.2f} "
             f"hit={c['hit_rate']:.3f} dd={c['max_dd_dollars']:10.2f} $/sess={c['per_session']:.2f}")
    inc = [r for fam in FAMS for r in same_trade_increments(books, fam, "IS")]
    curve = [r for fam in FAMS for r in holding_age_curve(books, fam, "IS")]
    best = {fam: max((c for c in cells if c["family"] == fam), key=lambda x: x["modeled_net"])["horizon"]
            for fam in FAMS}
    ride = {fam: max((c for c in cells if c["family"] == fam), key=lambda x: x["max_dd_dollars"])["horizon"]
            for fam in FAMS}
    h10 = {fam: next(c for c in cells if c["family"] == fam and c["horizon"] == 10)["modeled_net"] for fam in FAMS}
    interpretation = {
        "profit_first_is_horizon": best, "ride_first_is_horizon": ride,
        "is_h10_reference_net": h10,
        "preferred_horizon": {fam: (best[fam] if best[fam] != 10 else 10) for fam in FAMS},
        "primary_claimed_benefit": "higher in-sample modeled net at the preferred horizon versus that family's H10",
        "tolerable_downside": "a preferred horizon is treated as not confirmed if its OOS modeled net is below "
                              "that family's OOS H10, or if its OOS maximum drawdown is more than 20% worse",
        "note": "ten horizons on the same entry ledger are one correlated family, not ten independent discoveries",
    }
    freeze = {
        "status": "FROZEN_PRE_OOS", "timestamp": stamp(),
        "baseline_gate": st["gate"], "r2_entry_ledger_sha256": st["r2_entry_ledger_sha256"],
        "grid": {"families": list(FAMS), "horizons": list(HORIZONS), "cells": len(FAMS) * len(HORIZONS)},
        "rules": {"hn": "n exchange sessions after the fill session; fill = H0",
                  "exit_convention": "final regular-hours minute bar close, the same convention as the verified H10",
                  "entries": "identical verified R2 entries, initial shares, entry observations and entry costs at every horizon",
                  "capital": "no reinvestment, replacement entry, compounding or exposure normalisation when a shorter hold frees cash",
                  "schedule": "weekly Wednesday signal schedule unchanged even if short horizons leave flat periods",
                  "costs": "$0.005/share/side commission, max($0.01, 0.001*price)/side spread proxy; "
                           "0/10/30% annualised borrow scenarios on marked gross by actual calendar days; "
                           "dividends/locate/financing unknown and null"},
        "is_months": ["2025-09", "2025-11", "2026-01", "2026-03", "2026-05", "2026-07"],
        "oos_months": ["2025-10", "2025-12", "2026-02", "2026-04", "2026-06", "2026-08"],
        "oos_procedure": "one batch revealing all 30 OOS cells; no post-reveal parameter or horizon change",
        "is_cells": cells, "is_same_trade_increments": inc, "is_holding_age_curve": curve,
        "is_interpretation": interpretation,
        "code_sha256": {p: digest(REPO_ROOT / p) for p in
                        ("src/verification/r4r5_replay.py", "src/verification/r4r5_rank.py",
                         "src/verification/r4r5_data.py", "scripts/cg_arrow006_horizons.py")},
        "log": LOG}
    dump_json(FREEZE, freeze)
    note(f"freeze written: preferred={interpretation['preferred_horizon']} profit_first={best} ride_first={ride}")
    return 0


def stage_oos(args) -> int:
    if not FREEZE.exists():
        note("no committed freeze; OOS reveal refused")
        return 3
    freeze = read_json(FREEZE)
    if freeze["status"] not in {"FROZEN_PRE_OOS"}:
        note(f"freeze status {freeze['status']}; single-batch OOS reveal already consumed")
        return 3
    rel = FREEZE.relative_to(REPO_ROOT).as_posix()
    try:
        committed = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=REPO_ROOT)
    except subprocess.CalledProcessError:
        note("freeze must be committed before the OOS reveal")
        return 3
    if committed.replace(b"\r\n", b"\n") != FREEZE.read_bytes().replace(b"\r\n", b"\n"):
        note("freeze must be committed unchanged before the OOS reveal")
        return 3
    corrected, st, summaries = load_all(args)
    if st["r2_entry_ledger_sha256"] != freeze["r2_entry_ledger_sha256"]:
        note("entry ledger changed since the freeze; reveal refused")
        return 3
    books = build_books(corrected, summaries)
    cells = []
    for split in ("IS", "OOS", "ALL"):
        for fam in FAMS:
            for h in HORIZONS:
                cells.append(cell_metrics(fam, h, books[(fam, h)], split))
    # H10 must reproduce the locked baseline exactly
    base = {fam: read_json(REPORTS / "cg_arrow006_manifest.json")["summary"][f"{fam}/R2"]["verified_modeled_net"]
            for fam in FAMS}
    ident = {}
    for fam in FAMS:
        c = next(x for x in cells if x["family"] == fam and x["horizon"] == 10 and x["split"] == "ALL")
        ident[fam] = {"h10_all_net": c["modeled_net"], "locked_baseline_net": base[fam],
                      "difference": c["modeled_net"] - base[fam]}
    note(f"H10 identity vs locked baseline: {json.dumps(ident)}")
    inc = [r for fam in FAMS for split in ("IS", "OOS", "ALL") for r in same_trade_increments(books, fam, split)]
    curve = [r for fam in FAMS for split in ("IS", "OOS", "ALL") for r in holding_age_curve(books, fam, split)]
    for c in [x for x in cells if x["split"] == "OOS"]:
        note(f"OOS {c['family']} H{c['horizon']:02d} net={c['modeled_net']:10.2f} "
             f"hit={c['hit_rate']:.3f} dd={c['max_dd_dollars']:10.2f} $/sess={c['per_session']:.2f}")
    pref = freeze["is_interpretation"]["preferred_horizon"]
    confirm = {}
    for fam in FAMS:
        p = pref[fam]
        po = next(x for x in cells if x["family"] == fam and x["horizon"] == p and x["split"] == "OOS")
        h10 = next(x for x in cells if x["family"] == fam and x["horizon"] == 10 and x["split"] == "OOS")
        better = po["modeled_net"] > h10["modeled_net"]
        dd_ok = po["max_dd_dollars"] >= 1.2 * h10["max_dd_dollars"]
        confirm[fam] = {"preferred_horizon": p, "oos_net": po["modeled_net"], "oos_h10_net": h10["modeled_net"],
                        "oos_increment": po["modeled_net"] - h10["modeled_net"],
                        "oos_dd": po["max_dd_dollars"], "oos_h10_dd": h10["max_dd_dollars"],
                        "repeated": bool(better and dd_ok),
                        "verdict": "REPEATED" if (better and dd_ok) else
                                   ("NOT REPEATED" if not better else "REPEATED ON PROFIT, DRAWDOWN TOLERANCE BREACHED")}
    note(f"confirmation: {json.dumps(confirm)}")
    # local detailed CSVs
    wide, tidy = {}, []
    for fam in FAMS:
        w, t = exp.horizon_paths(fam, corrected, summaries)
        wide[fam] = w
        tidy.extend(t)
    exp.write_csv(HANDOFF6 / "r4r5_horizon_trade_paths.csv", [r for v in wide.values() for r in v])
    exp.write_csv(HANDOFF6 / "r4r5_horizon_trade_paths_tidy.csv", tidy)
    exp.write_csv(HANDOFF6 / "r4r5_horizon_summary.csv", cells)
    exp.write_csv(REPORTS / "cg_arrow006_horizons.csv", cells)
    exp.write_csv(REPORTS / "cg_arrow006_horizon_increments.csv", inc)
    exp.write_csv(REPORTS / "cg_arrow006_holding_age_curve.csv", curve)
    freeze.update({"status": "OOS_REVEALED", "oos_revealed_at": stamp(), "cells": cells,
                   "h10_baseline_identity": ident, "confirmation": confirm,
                   "same_trade_increments": inc, "holding_age_curve": curve,
                   "local_csvs": {n: {"path": (HANDOFF6 / n).as_posix(), "sha256": digest(HANDOFF6 / n)}
                                  for n in ("r4r5_horizon_trade_paths.csv", "r4r5_horizon_trade_paths_tidy.csv",
                                            "r4r5_horizon_summary.csv")},
                   "log": freeze.get("log", []) + LOG})
    dump_json(FREEZE, freeze)
    note("OOS reveal complete; freeze updated to OOS_REVEALED")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["is", "oos"])
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    return stage_is(args) if args.stage == "is" else stage_oos(args)


if __name__ == "__main__":
    sys.exit(main())
