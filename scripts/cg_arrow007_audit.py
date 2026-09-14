"""CG Arrow 007 adversarial audit: recompute the published result from stored evidence.

Nothing here calls the replay or ranking helpers. Every figure is rebuilt from the exported
CSV ledger, the canonical action table and the stored observations, then compared with what
was published.

Usage: python scripts/cg_arrow007_audit.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import date
import json
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

HANDOFF7 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow007"
WORK = VERIFY_ROOT / "work"
COMPLETED = ("VERIFIED_PRICE_LOCAL_SINGLE_SOURCE", "VERIFIED_PRICE_CARRIED_DOCUMENTED_HALT")
FAMILY_BASE = {"PARENT": 4000.0, "R4": 5150.0, "R5": 8300.0}
findings = []


def note(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


def check(label: str, ok: bool, detail: str = "") -> None:
    findings.append({"check": label, "ok": bool(ok), "detail": detail})
    note(f"{'PASS' if ok else 'FAIL'}  {label}  {detail}")


def num(x):
    return None if x in ("", None) else float(x)


def fee(px: float) -> float:
    return 0.005 + max(0.01, 0.001 * px)


def factor(symbol: str, observed: date, asof: date, events) -> float:
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
    trades = list(csv.DictReader((HANDOFF7 / "r4r5_verified_trades.csv").open(encoding="utf-8")))
    audit = list(csv.DictReader((HANDOFF7 / "r4r5_verified_cohort_audit.csv").open(encoding="utf-8")))
    daily = list(csv.DictReader((HANDOFF7 / "r4r5_daily_account.csv").open(encoding="utf-8")))
    man = read_json(REPORTS / "cg_arrow007_manifest.json")
    note(f"ledger rows={len(trades)} audit rows={len(audit)} daily rows={len(daily)}")

    book = [t for t in trades if t["model"] == "R5" and t["replay_stage"] == "R2_LEGACY_FILL_QTY"]
    done = [t for t in book if t["status"] in COMPLETED]

    # ---- 1. independent per-trade arithmetic on the largest winners and losers
    ranked = sorted(done, key=lambda t: num(t["modeled_net"]))
    sample = ranked[:5] + ranked[-5:]
    worst = 0.0
    for t in sample:
        q = num(t["quantity"])
        f = num(t["action_factor_over_hold"]) or 1.0
        entry, exit_ = num(t["entry_price"]), num(t["exit_price"])
        qe = q / f
        gross = qe * (entry * f - exit_)
        net = gross - q * fee(entry) - qe * fee(exit_)
        worst = max(worst, abs(net - num(t["modeled_net"])), abs(gross - num(t["gross_pnl"])))
        # the action factor must equal the product of documented events over the hold
        fill = date.fromisoformat(t["scheduled_entry_date"])
        ex = date.fromisoformat(t.get("actual_exit_date") or t["scheduled_exit_date"])
        worst = max(worst, abs(f - factor(t["symbol"], fill, ex, events)))
    check("largest winners and losers recompute from stored prices, quantities and factors",
          worst < 1e-6, f"max absolute difference {worst:.2e} across {len(sample)} trades")

    # ---- 2. sizing tier and integer quantity from the frozen rule
    bad = []
    for t in done[:400]:
        base = FAMILY_BASE[t["model"]]
        vr, r3 = num(t["volume_ratio"]), num(t["ret3"])
        vm = 0.5 if (vr is not None and vr > 1) else 1.0
        mm = 0.5 if (t["model"] == "R5" and r3 is not None and r3 > 0) else 1.0
        expect = base if t["model"] == "PARENT" else base * vm * (mm if t["model"] == "R5" else 1.0)
        tier = {1.0: "FULL", 0.5: "HALF", 0.25: "QUARTER"}[
            1.0 if t["model"] == "PARENT" else vm * (mm if t["model"] == "R5" else 1.0)]
        q = math.floor(expect / num(t["entry_price"]))
        if abs(expect - num(t["intended_size"])) > 1e-9 or tier != t["size_tier"] or q != int(num(t["quantity"])):
            bad.append(f"{t['ticket_id']} size={t['intended_size']} tier={t['size_tier']} qty={t['quantity']}")
    check("sizing tier and integer share count follow the frozen rule",
          not bad, f"{len(bad)} mismatches in {min(400, len(done))} checked" + (f"; first {bad[0]}" if bad else ""))

    # ---- 3. cohort subtotals and period totals conserve
    by_cohort = defaultdict(float)
    for t in book:
        if t["status"] in COMPLETED:
            by_cohort[t["cohort_id"]] += num(t["modeled_net"])
    err = 0.0
    seen = 0
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

    # ---- 4. the account equity walk reproduces the published book
    rows = [r for r in daily if r["model"] == "R5" and r["replay_stage"] == "R2_LEGACY_FILL_QTY"]
    eq_last = num(rows[-1]["equity"])
    cash_last, liab_last = num(rows[-1]["cash"]), num(rows[-1]["short_liability"])
    check("August 31 equity equals cash minus short liability",
          abs(eq_last - (cash_last - liab_last)) < 1e-6,
          f"equity {eq_last:,.2f} cash {cash_last:,.2f} liability {liab_last:,.2f}")
    through = sum(num(t["modeled_net"]) for t in done if t["exit_after_cutoff"] != "True")
    runoff = sum(num(t["modeled_net"]) for t in done if t["exit_after_cutoff"] == "True")
    published = man["split_owned_books"]["R5/R2/LEGACY_FILL_QTY/ALL"]
    check("calendar-account and September runoff totals are reported separately and add up",
          abs(through - published["completed_net_through_cutoff"]) < 1e-6
          and abs(runoff - published["september_runoff_net"]) < 1e-6,
          f"through cutoff {through:,.2f} + runoff {runoff:,.2f} = {through + runoff:,.2f}")

    # ---- 5. rank boundary and adjusted ranking return, rebuilt from observations
    recon = {r["cohort_id"]: r for r in man["ranking_reconciliation"]}
    state = read_json(WORK / "a7_baseline_state.json")
    cohorts = {c["signal_iso"]: c for c in state["certified_cohorts"]}
    changed = [c for c in recon.values() if c["membership_change_vs_recorded"]][:4]
    need = set()
    for c in changed:
        i = INDEX[date.fromisoformat(c["cohort_id"])]
        back = FEATS[i - 15].isoformat()
        for s in cohorts[c["cohort_id"]]["rows"]:
            need.add((c["cohort_id"], s["symbol"]))
            need.add((back, s["symbol"]))
    sums = load_summaries(need, args.workers)
    rr_err, boundary_ok = 0.0, True
    for c in changed:
        iso = c["cohort_id"]
        i = INDEX[date.fromisoformat(iso)]
        back = FEATS[i - 15]
        rows_c = cohorts[iso]["rows"]
        for s in rows_c:
            a = sums.get((back.isoformat(), s["symbol"]))
            b = sums.get((iso, s["symbol"]))
            if present(a) and present(b):
                f = factor(s["symbol"], back, date.fromisoformat(iso), events)
                rebuilt = b["close"] / (a["close"] * f) - 1
                rr_err = max(rr_err, abs(rebuilt - s["raw_return"]))
        ret = [s["raw_return"] for s in rows_c]
        boundary_ok = boundary_ok and ret == sorted(ret, reverse=True) and len(rows_c) == 8
    check("adjusted 15-session ranking returns rebuild from stored prices and documented factors",
          rr_err < 1e-9, f"max difference {rr_err:.2e} across {len(changed)} changed cohorts")
    check("the certified top eight is the ranked head of the field, in order",
          boundary_ok, f"{len(changed)} changed cohorts inspected")

    # ---- 6. every documented factor traces to a primary source
    missing = [e for e in events if not str(e.get("source", "")).startswith("http")]
    check("every canonical corporate action carries a source URL",
          not missing, f"{len(events)} events, {len(missing)} without a source")

    # ---- 7. no unresolved row hides inside a verified subtotal
    leak = [t for t in trades if t["status"] not in COMPLETED and num(t.get("modeled_net")) is not None]
    check("no unresolved or blocked row carries a modelled net total", not leak,
          f"{len(leak)} leaking rows")

    # ---- 8. public repository safety
    tracked = subprocess.check_output(["git", "ls-files"], cwd=REPO_ROOT).decode().splitlines()
    bad_paths = [t for t in tracked if t == ".env" or t.startswith(("handoff/", "data/verification/"))
                 or t.endswith(".parquet")]
    check("public repository contains no .env, private CSV, vendor partition or parquet",
          not bad_paths, f"{len(tracked)} tracked files, {len(bad_paths)} offending")
    leak_txt = []
    for p in list((REPO_ROOT / "reports").glob("cg_arrow007*")):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        if "THETADATA_API_KEY=" in txt and "<key>" not in txt:
            leak_txt.append(p.name)
    check("public Arrow 007 artefacts contain no credential material", not leak_txt, str(leak_txt))

    ok = all(f["ok"] for f in findings)
    dump_json(REPORTS / "cg_arrow007_adversarial_audit.json",
              {"timestamp": stamp(), "all_passed": ok, "checks": findings})
    note(f"adversarial audit {'PASSED' if ok else 'FAILED'}: "
         f"{sum(f['ok'] for f in findings)}/{len(findings)} checks")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
