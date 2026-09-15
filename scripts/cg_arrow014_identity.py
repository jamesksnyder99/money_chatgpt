"""CG Arrow 014 — resolve the identities Arrow 013 could not, and gather their corporate actions.

The census reached every issuer SEC's current ticker file knows. It could not reach the ones that
matter most: a microcap that was delisted, renamed or consolidated out of existence during the
corridor no longer holds its ticker, so `company_tickers.json` has nothing to say about it. Those
are precisely the securities whose ranking windows contain a level change the strategy read as an
enormous gain.

This runs the point-in-time identity resolution over every selected name whose ranking or holding
window carries an unexplained discontinuity, and then gathers that issuer's own split and
consolidation statements, exhibits included.

No ranking, selection or performance is computed here.

Usage: python scripts/cg_arrow014_identity.py [--workers 8] [--scope flagged|all]
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT  # noqa: E402
from verification import r4r5_identity as idy  # noqa: E402
from verification.r4r5_data import dump_json, read_json, stamp  # noqa: E402

WORK = H.WORK
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow014"
STATE = OUT / "selected_corridor_state.csv"
FOUND = WORK / "identity_investigation.json"
LO, HI = "2024-06-01", "2025-12-31"
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def flagged_symbols() -> list[str]:
    """Selected names whose ranking or holding window carries an unexplained discontinuity."""
    out = set()
    for r in csv.DictReader(STATE.open(encoding="utf-8")):
        if r["group"] != "TOP8":
            continue
        bad = r["lookback_resolution"] == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"
        for h in H.__dict__.get("HOLDS", (8, 9, 10)):
            if r.get(f"h{h}_holding_resolution") == "UNEXPLAINED_HOLDING_WINDOW_DISCONTINUITY":
                bad = True
        if bad:
            out.add(r["symbol"])
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--scope", choices=("flagged", "all"), default="flagged")
    args = ap.parse_args()

    if args.scope == "flagged":
        symbols = flagged_symbols()
    else:
        symbols = sorted({c["symbol"] for c in read_json(WORK / "phase0b_event_cases.json").values()})
    done = read_json(FOUND) if FOUND.exists() else {}
    todo = [s for s in symbols if s not in done]
    note(f"{len(symbols)} securities in scope; {len(done)} already investigated, {len(todo)} to do")

    # The screen already recorded exactly where each security's tape changed level. Those dates
    # are what the filings have to explain, and confining the search to their neighbourhood is
    # the difference between a thirty-minute census and a five-hour one.
    import datetime
    anchors: dict = {}
    for c in read_json(WORK / "phase0b_event_cases.json").values():
        anchors.setdefault(c["symbol"], []).append(datetime.date.fromisoformat(c["date"]))
    note(f"discontinuity anchors available for {len(anchors)} securities; in scope, "
         f"{sum(1 for s in symbols if s in anchors)} of {len(symbols)} have at least one")

    batch = 40
    for i in range(0, len(todo), batch):
        done.update(idy.investigate(todo[i:i + batch], LO, HI, workers=args.workers,
                                    anchors=anchors))
        dump_json(FOUND, done)
        res = sum(1 for v in done.values() if v["identity"].get("cik"))
        act = sum(1 for v in done.values() if v["actions"].get("events"))
        note(f"  investigated {len(done)}/{len(symbols)}; identity resolved {res}; "
             f"action evidence found {act}")

    ident = Counter(v["identity"].get("status") for v in done.values())
    acts = Counter(v["actions"].get("status") for v in done.values())
    note("identity outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(ident.items())))
    note("action outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(acts.items())))
    dump_json(WORK / "identity_manifest.json", {
        "arrow": "CG Arrow 014", "stage": "identity", "timestamp": stamp(),
        "scope": args.scope, "securities": len(symbols),
        "window": [LO, HI],
        "method": ("EDGAR full-text search restricted to the corridor, counting a hit only when "
                   "the ticker is the filer's own registered symbol in its display name"),
        "identity_outcomes": dict(ident), "action_outcomes": dict(acts),
        "identity_resolved": sum(1 for v in done.values() if v["identity"].get("cik")),
        "action_evidence_found": sum(1 for v in done.values() if v["actions"].get("events")),
        "no_outcomes_calculated": True, "log": LOG})
    return 0


if __name__ == "__main__":
    sys.exit(main())
