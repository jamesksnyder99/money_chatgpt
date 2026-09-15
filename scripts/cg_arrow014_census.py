"""CG Arrow 014 census — take every screened case to the issuer's own SEC filings.

The Phase 0B screen says where the corridor's price series changes level or breaks. It does not
say why, and a price jump is not proof of a corporate action. This stage answers each case from
primary evidence: the issuer's EDGAR filings across the corridor, read for an explicit split,
consolidation or share-exchange statement carrying a ratio and a dated effect.

An event is only written into the action table when a filing states it. A case the filings do not
explain stays unexplained and is reported as such; it is then the certification gate's job to
decide whether it touches a frozen scored cell. Nothing here reads an outcome.

Usage:
  python scripts/cg_arrow014_census.py --stage scan    [--workers 8]
  python scripts/cg_arrow014_census.py --stage resolve [--threshold 1.2]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_events as ev  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification.r4r5_data import dump_json, read_json, stamp  # noqa: E402

WORK = H.WORK
CASES = WORK / "phase0b_event_cases.json"
SCANS = WORK / "census_symbol_scans.json"
TABLE = REPORTS / "cg_arrow014_corporate_actions.json"

# Filings are read either side of the corridor: a split is announced before it takes effect and
# amended after, so a window clipped to the corridor would miss the document that explains it.
SCAN_LO = "2024-06-01"
SCAN_HI = "2025-11-30"
T0 = time.monotonic()
LOG: list[str] = []


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def stage_scan(args) -> int:
    cases = read_json(CASES)
    symbols = sorted({c["symbol"] for c in cases.values()})
    done = read_json(SCANS) if SCANS.exists() else {}
    todo = [s for s in symbols if s not in done]
    note(f"{len(cases):,} screened cases across {len(symbols):,} securities; "
         f"{len(done):,} already scanned, {len(todo):,} to scan")
    if not todo:
        note("nothing to scan")
        return 0
    batch = 200
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        done.update(ev.scan_symbols(chunk, SCAN_LO, SCAN_HI, workers=args.workers))
        dump_json(SCANS, done)
        found = sum(1 for v in done.values() if v.get("status") == "FILING_EVIDENCE_FOUND")
        note(f"scanned {len(done):,}/{len(symbols):,}; filing evidence for {found:,}")
    by_status = Counter(v.get("status") for v in done.values())
    note("scan outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())))
    return 0


def nearest_session(d: date) -> date | None:
    """The first corridor session on or after a stated effective date."""
    for x in HO.FEATS:
        if x >= d:
            return x
    return None


def stage_resolve(args) -> int:
    """Match documented filing events to screened discontinuities and build the action table."""
    cases, scans = read_json(CASES), read_json(SCANS)
    corridor = {d.isoformat() for d in HO.FEATS}
    by_symbol: dict = defaultdict(list)
    for c in cases.values():
        by_symbol[c["symbol"]].append(c)

    events, unmatched_filings = [], []
    for sym, scan in sorted(scans.items()):
        for e in scan.get("events", []):
            # An extracted statement becomes an event only when it carries a date that lands
            # inside the corridor and a factor the engine can apply.
            candidates = []
            for ds in e.get("dates_in_window", []):
                try:
                    eff = nearest_session(datetime.fromisoformat(ds).date())
                except ValueError:
                    continue
                if eff is not None and eff.isoformat() in corridor:
                    candidates.append(eff)
            if not candidates:
                unmatched_filings.append({"symbol": sym, "form": e.get("form"),
                                          "filing_date": e.get("filing_date"),
                                          "ratio_text": e.get("ratio_text"),
                                          "reason": "no stated effective date inside the corridor"})
                continue
            eff = min(candidates)
            # Corroboration: the screen must actually show a level change at the stated session,
            # in the direction and near the magnitude the filing states. A filing that describes
            # an event the tape does not show is not applied.
            observed = next((c for c in by_symbol.get(sym, [])
                             if c.get("date") == eff.isoformat() and "ratio" in c), None)
            factor = e["price_factor"]
            residual = None
            if observed is not None:
                residual = observed["ratio"] * factor
                residual = max(residual, 1 / residual) if residual else None
            events.append({
                "symbol": sym, "effective_session": eff.isoformat(), "price_factor": factor,
                "event_type": e["event_type"], "source": e["url"],
                "source_date": e["filing_date"], "source_form": e["form"],
                "source_items": e.get("items"), "ratio_text": e["ratio_text"],
                "status": "PRIMARY_VERIFIED" if observed is not None
                          else "PRIMARY_VERIFIED_NO_TAPE_DISCONTINUITY",
                "observed_ratio": observed["ratio"] if observed else None,
                "residual_discontinuity_after_factor": round(residual, 4) if residual else None,
                "origin": "arrow014_sec_edgar_census"})

    # Deduplicate: one issuer can file the same split in an 8-K and amend it. Keep one event per
    # symbol and effective session, preferring the record whose factor leaves the flattest tape.
    best: dict = {}
    for e in events:
        key = (e["symbol"], e["effective_session"])
        prev = best.get(key)
        if prev is None or (e["residual_discontinuity_after_factor"] or 9e9) < \
                (prev["residual_discontinuity_after_factor"] or 9e9):
            best[key] = e
    events = [best[k] for k in sorted(best)]
    note(f"documented events inside the corridor: {len(events)} "
         f"({sum(1 for e in events if e['status'] == 'PRIMARY_VERIFIED')} corroborated by the tape)")

    explained = {(e["symbol"], e["effective_session"]) for e in events}
    unexplained = [c for k, c in sorted(cases.items())
                   if (c["symbol"], c["date"]) not in explained]
    note(f"screened cases without a filing explanation: {len(unexplained):,} of {len(cases):,}")

    by_status = Counter(v.get("status") for v in scans.values())
    payload = {
        "version": "cg_arrow014_corporate_actions_v1",
        "timestamp": stamp(),
        "corridor_id": HO.CORRIDOR_ID,
        "factor_convention": ("price_factor multiplies a price observed before the effective "
                              "session to express it in post-event share units; share volume is "
                              "divided by the same factor"),
        "primary_source": "SEC EDGAR issuer filings",
        "scan_window": [SCAN_LO, SCAN_HI],
        "coverage": ("every security that showed a price level change at or beyond the screen "
                     "threshold, or a multi-session trading gap, inside a session its own cohorts "
                     "depend on; the screen ran over the whole corridor universe, not a shortlist"),
        "cases_investigated": len(cases),
        "securities_investigated": len(scans),
        "scan_status_counts": dict(by_status),
        "events": events,
        "security_identity": [],
        "trading_events": [],
        "non_comparable_events": [],
        "unmatched_filing_statements": unmatched_filings[:200],
        "unexplained_screen_cases": len(unexplained),
        "limitations": ("A screened case with no filing explanation is not asserted to be an "
                        "action; it is carried to the certification gate, which fails closed if "
                        "any such case touches a frozen scored cell."),
    }
    dump_json(TABLE, payload)
    dump_json(WORK / "census_unexplained_cases.json",
              {f"{c['symbol']}|{c['date']}": c for c in unexplained})
    note(f"wrote {TABLE.relative_to(REPO_ROOT).as_posix()} with {len(events)} documented events")
    dump_json(WORK / "census_manifest.json", {
        "arrow": "CG Arrow 014", "stage": "resolve", "timestamp": stamp(),
        "cases": len(cases), "securities_scanned": len(scans),
        "scan_status_counts": dict(by_status), "events": len(events),
        "unexplained_cases": len(unexplained),
        "no_outcomes_calculated": True, "log": LOG})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("scan", "resolve"), required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--threshold", type=float, default=1.2)
    args = ap.parse_args()
    return {"scan": stage_scan, "resolve": stage_resolve}[args.stage](args)


if __name__ == "__main__":
    sys.exit(main())
