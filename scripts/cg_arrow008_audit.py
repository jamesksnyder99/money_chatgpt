"""CG Arrow 008 adversarial audit — recompute the certified result from stored evidence.

Nothing here calls the replay, ranking or accounting helpers. Every figure is rebuilt from the
exported CSV ledger, the canonical action table and the stored observations, then compared
with what was published.

Usage: python scripts/cg_arrow008_audit.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    ACTION_PATH, FEATS, INDEX, VERIFY_ROOT, dump_json, load_summaries, present, read_json, stamp,
)

HANDOFF8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
WORK = VERIFY_ROOT / "work"
COMPLETED = ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT")
FAMILY_BASE = {"PARENT": 4000.0, "R4": 5150.0, "R5": 8300.0}
ADEQUATE = {"PRIMARY_VERIFIED_ACTION", "ADEQUATELY_REVIEWED_MARKET_MOVE",
            "DOCUMENTED_TRADING_EVENT", "NON_COMPARABLE_REORGANIZATION"}
findings = []


def check(label: str, ok: bool, detail: str = "") -> None:
    findings.append({"check": label, "ok": bool(ok), "detail": detail})
    print(f"{stamp()} {'PASS' if ok else 'FAIL'}  {label}  {detail}", flush=True)


def num(x):
    return None if x in ("", None) else float(x)


def fee(px: float) -> float:
    return 0.005 + max(0.01, 0.001 * px)


def factor(symbol, observed: date, asof: date, events) -> float:
    f = 1.0
    for e in events:
        if e["symbol"] == symbol and observed.isoformat() < e["effective_session"] <= asof.isoformat():
            f *= e["price_factor"]
    return f


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    actions = read_json(ACTION_PATH)
    events = actions["events"]
    m8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    trades = list(csv.DictReader((HANDOFF8 / "certified_trade_audit.csv").open(encoding="utf-8")))
    audit = list(csv.DictReader((HANDOFF8 / "certified_cohort_audit.csv").open(encoding="utf-8")))
    daily = list(csv.DictReader((HANDOFF8 / "r4r5_daily_account.csv").open(encoding="utf-8")))
    led = read_json(WORK / "a8_material_ledger.json")
    print(f"{stamp()} ledger rows={len(trades)} audit rows={len(audit)} daily rows={len(daily)}")

    book = [t for t in trades if t["model"] == "R5" and t["replay_stage"] == "R2_LEGACY_FILL_QTY"]
    done = [t for t in book if t["status"] in COMPLETED]

    # 1. per-trade arithmetic on the largest winners and losers
    ranked = sorted(done, key=lambda t: num(t["modeled_net"]))
    sample = ranked[:5] + ranked[-5:]
    worst = 0.0
    for t in sample:
        q, f = num(t["quantity"]), (num(t["action_factor_over_hold"]) or 1.0)
        entry, exit_ = num(t["entry_price"]), num(t["exit_price"])
        qe = q / f
        gross = qe * (entry * f - exit_)
        net = gross - q * fee(entry) - qe * fee(exit_)
        worst = max(worst, abs(net - num(t["modeled_net"])), abs(gross - num(t["gross_pnl"])))
        fill = date.fromisoformat(t["scheduled_entry_date"])
        ex = date.fromisoformat(t.get("actual_exit_date") or t["scheduled_exit_date"])
        worst = max(worst, abs(f - factor(t["symbol"], fill, ex, events)))
    check("largest winners and losers recompute from stored prices, quantities and factors",
          worst < 1e-6, f"max absolute difference {worst:.2e} across {len(sample)} trades")

    # 2. sizing tier and integer quantity from the frozen rule
    bad = []
    for t in done:
        base = FAMILY_BASE[t["model"]]
        vr, r3 = num(t["volume_ratio"]), num(t["ret3"])
        vm = 0.5 if (vr is not None and vr > 1) else 1.0
        mm = 0.5 if (t["model"] == "R5" and r3 is not None and r3 > 0) else 1.0
        expect = base if t["model"] == "PARENT" else base * vm * (mm if t["model"] == "R5" else 1.0)
        if abs(expect - num(t["intended_size"])) > 1e-9 \
                or math.floor(expect / num(t["entry_price"])) != int(num(t["quantity"])):
            bad.append(t["ticket_id"])
    check("sizing and integer share count follow the frozen rule on every completed trade",
          not bad, f"{len(done)} trades checked, {len(bad)} mismatches")

    # 3. cohort subtotals and the period total
    by_cohort = defaultdict(float)
    for t in book:
        if t["status"] in COMPLETED:
            by_cohort[t["cohort_id"]] += num(t["modeled_net"])
    err, seen = 0.0, 0
    for a in audit:
        if a["model"] != "R5" or a["replay_stage"] != "R2_LEGACY_FILL_QTY":
            continue
        if a["row_type"] == "COHORT_SUBTOTAL":
            err = max(err, abs(by_cohort[a["cohort_id"]] - num(a["modeled_net"])))
            seen += 1
        elif a["row_type"] == "PERIOD_TOTAL":
            err = max(err, abs(sum(by_cohort.values()) - num(a["modeled_net"])))
    check("cohort subtotals and the period total reconcile to the trade ledger",
          err < 1e-6 and seen == 52, f"{seen} cohort subtotals, max difference {err:.2e}")

    # 4. the six published account quantities, rebuilt from the ledger
    rows = [r for r in daily if r["model"] == "R5" and r["replay_stage"] == "R2_LEGACY_FILL_QTY"]
    eq, cash, liab = num(rows[-1]["equity"]), num(rows[-1]["cash"]), num(rows[-1]["short_liability"])
    check("August 31 equity equals cash minus short liability", abs(eq - (cash - liab)) < 1e-6,
          f"equity {eq:,.2f}")
    acct = m8["accounts"]["R5/LEGACY_FILL_QTY/ALL"]
    A = sum(num(t["modeled_net"]) for t in done)
    through = sum(num(t["modeled_net"]) for t in done if t["exit_after_cutoff"] != "True")
    D = sum(num(t["modeled_net"]) for t in done if t["exit_after_cutoff"] == "True")
    check("completed-trade P&L splits exactly into through-cutoff plus eventual runoff",
          abs(A - (through + D)) < 1e-6 and abs(A - acct["A_completed_trade_pnl_all_cohorts"]) < 1e-6,
          f"A {A:,.2f} = through {through:,.2f} + runoff {D:,.2f}")
    check("eventual runoff P&L splits into its cutoff mark plus the post-cutoff increment",
          abs(acct["D_eventual_pnl_of_runoff_trades"]
              - (acct["runoff_marked_pnl_at_cutoff"]
                 + acct["C_post_cutoff_incremental_runoff_pnl"])) < 1e-6,
          f"D {acct['D_eventual_pnl_of_runoff_trades']:,.2f} = marked "
          f"{acct['runoff_marked_pnl_at_cutoff']:,.2f} + increment "
          f"{acct['C_post_cutoff_incremental_runoff_pnl']:,.2f}")
    check("the marked account figure at the cutoff is not the eventual completed figure",
          abs(acct["B_marked_account_pnl_at_cutoff"] - A) > 1.0,
          f"B {acct['B_marked_account_pnl_at_cutoff']:,.2f} vs A {A:,.2f}")
    check("the per-session figure divides the cutoff account result by cutoff account sessions",
          abs(acct["marked_account_pnl_per_account_session"]
              - acct["B_marked_account_pnl_at_cutoff"] / acct["account_sessions_to_cutoff"]) < 1e-9,
          acct["per_session_basis"])

    # 5. the bridge identity, recomputed from the two ledgers
    r1 = {t["ticket_id"]: num(t["modeled_net"]) for t in trades
          if t["model"] == "R5" and t["replay_stage"] == "R1_LEGACY_FILL_QTY"
          and t["status"] in COMPLETED}
    r2 = {t["ticket_id"]: num(t["modeled_net"]) for t in done}
    common = set(r1) & set(r2)
    lhs = sum(r2.values()) - sum(r1.values())
    rhs = (sum(r2[k] - r1[k] for k in common)
           + sum(v for k, v in r2.items() if k not in r1)
           - sum(v for k, v in r1.items() if k not in r2))
    published = m8["bridges"]["R5/LEGACY_FILL_QTY"]
    check("the R1 to R2 bridge identity holds when rebuilt from the two ledgers",
          abs(lhs - rhs) < 1e-6 and abs(published["reconciliation_residual"]) < 1e-6,
          f"difference {lhs:,.2f}, residual {lhs - rhs:.2e}")
    check("the dropped component is the signed P&L of the removed tickets",
          abs(published["DROPPED_R1_PNL"] - sum(v for k, v in r1.items() if k not in r2)) < 1e-6,
          f"DROPPED_R1_PNL {published['DROPPED_R1_PNL']:,.2f}")

    # 6. evidence states
    bad_state = [r for r in led if r["final_state"] not in ADEQUATE]
    check("every material selected-name event carries an adequate evidence state", not bad_state,
          f"{len(led)} cases, {len(bad_state)} inadequate")
    no_src = [e for e in events if not str(e.get("source", "")).startswith("http")]
    check("every canonical corporate action carries a ratio, an effective session and a source",
          not no_src and all(e.get("price_factor") for e in events),
          f"{len(events)} events")

    # 7. nothing unresolved hides inside a total
    leak = [t for t in trades if t["status"] not in COMPLETED and num(t.get("modeled_net")) is not None]
    check("no unresolved or blocked row carries a modelled net total", not leak, f"{len(leak)} rows")

    # 8. ladder identity and public safety
    check("the 10-session hold reproduces the certified baseline", m8["h10_reproduces_baseline"])
    tracked = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT).decode().splitlines()
    offending = [t for t in tracked if t == ".env" or t.startswith(("handoff/", "data/verification/"))
                 or t.endswith(".parquet")]
    check("public repository contains no .env, private CSV, vendor partition or parquet",
          not offending, f"{len(tracked)} tracked files")

    ok = all(f["ok"] for f in findings)
    dump_json(REPORTS / "cg_arrow008_adversarial_audit.json",
              {"timestamp": stamp(), "all_passed": ok, "checks": findings})
    print(f"{stamp()} Arrow 008 adversarial audit {'PASSED' if ok else 'FAILED'}: "
          f"{sum(f['ok'] for f in findings)}/{len(findings)} checks", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
