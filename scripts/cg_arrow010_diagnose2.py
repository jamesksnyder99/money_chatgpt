"""Arrow 010 diagnosis 2: per-ticket comparison against the certified R5 legacy-fill book."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))

from ingest.paths import REPO_ROOT  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    FEATS, INDEX, VERIFY_ROOT, action_events, load_summaries, non_comparable_events,
    present, read_json, set_vendor_status,
)
from verification.r4r5_replay import COMPLETED, replay  # noqa: E402
from cg_arrow007_run import candidate_meta, rank_with  # noqa: E402

WORK = VERIFY_ROOT / "work"
LOOKBACK = 15
HOLD = 10


def num(x):
    return None if x in ("", None) else float(x)


def main() -> int:
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
    summaries = load_summaries(endpoints, 8)
    action_events.cache_clear()
    non_comparable_events.cache_clear()
    corrected = rank_with(rule_field, meta, summaries, status_map)

    life = set()
    for c in corrected:
        i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
        for h in c["rows"]:
            for d in FEATS[i - LOOKBACK - 1: fi + HOLD + 1]:
                life.add((d.isoformat(), h["symbol"]))
    summaries.update(load_summaries(life - set(summaries), 8))

    book = replay("R5", corrected, summaries, hold=HOLD, quantity="fill", stage="X")
    mine = {t["ticket_id"]: t for t in book["trades"]}

    path = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008" / "r4r5_verified_trades.csv"
    cert = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r["model"] == "R5" and r["replay_stage"] == "R2_LEGACY_FILL_QTY":
            cert[r["ticket_id"]] = r

    print(f"tickets mine={len(mine)} certified={len(cert)} same_keys={set(mine)==set(cert)}")
    status_pairs = Counter()
    worst = []
    for tid, c in cert.items():
        m = mine[tid]
        status_pairs[(c["status"], m["status"])] += 1
        cn, mn = num(c["modeled_net"]), m.get("modeled_net")
        if (cn is None) != (mn is None):
            worst.append((abs(mn or cn or 0.0), tid, c, m))
        elif cn is not None and abs(cn - mn) > 0.005:
            worst.append((abs(cn - mn), tid, c, m))
    print("\nstatus (certified -> rebuilt) pairs:")
    for (a, b), n in status_pairs.most_common():
        flag = "" if a == b else "   <-- CHANGED"
        print(f"  {n:4d}  {a}  ->  {b}{flag}")
    worst.sort(reverse=True)
    print(f"\ntickets whose modeled net differs: {len(worst)}")
    for gap, tid, c, m in worst[:12]:
        print(f"\n  {tid}  gap {gap:,.2f}")
        for k in ("status", "quantity", "entry_price", "exit_price", "scheduled_exit_date",
                  "actual_exit_date", "action_factor_over_hold", "modeled_net"):
            print(f"    {k:26s} certified={c.get(k)!r:>28}  rebuilt={m.get(k)!r}")
        sym = c["symbol"]
        for d in (c.get("scheduled_entry_date"), c.get("scheduled_exit_date")):
            if d:
                print(f"    summary present {sym} {d}: {present(summaries.get((d, sym)))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
