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


def eod_ratios() -> dict:
    """(symbol, session) -> close / previous close, from the independent end-of-day layer.

    Corroboration has to be able to look at any symbol and session a filing names, not only the
    ones that made the screen's case set. The case set is restricted to sessions a cohort depends
    on; a filing can state an effective date anywhere in the corridor.
    """
    import polars as pl
    df = (pl.read_parquet(WORK / "eod_corridor.parquet")
            .filter(pl.col("close").is_finite() & (pl.col("close") > 0))
            .sort(["symbol", "eod_date"]))
    df = (df.with_columns(prev=pl.col("close").shift(1).over("symbol"))
            .filter(pl.col("prev").is_not_null())
            .with_columns(ratio=pl.col("close") / pl.col("prev")))
    return {(s, d.isoformat()): r
            for s, d, r in df.select(["symbol", "eod_date", "ratio"]).iter_rows()}


def stage_resolve(args) -> int:
    """Match documented filing statements to what the tape shows, and build the action table.

    Two independent things must agree before a factor is applied to a price. The issuer must have
    filed a statement carrying a ratio and a dated effect, and the tape must show a level change
    at that session which the factor flattens. A filing alone is not enough: the extraction reads
    any date near split language, so an uncorroborated statement is as likely to be a mention of a
    past or contemplated action as a record of one that happened here. Applying such a factor
    would rewrite a price where no unit change occurred, which is worse than leaving it alone.
    """
    cases, scans = read_json(CASES), read_json(SCANS)
    corridor = {d.isoformat() for d in HO.FEATS}
    ratios = eod_ratios()

    # Two evidence sources, merged deterministically and held to the same standard. The first is
    # the census over issuers SEC's current ticker file can reach. The second is the point-in-time
    # identity investigation, which reaches the issuers it cannot — the delisted and consolidated
    # microcaps whose actions are exactly the ones that distort a winner ranking.
    merged: dict = {sym: list(scan.get("events", [])) for sym, scan in scans.items()}
    identity_path = WORK / "identity_investigation.json"
    identity_added = 0
    if identity_path.exists():
        for sym, rec in read_json(identity_path).items():
            evs = (rec.get("actions") or {}).get("events") or []
            if evs:
                merged.setdefault(sym, []).extend(evs)
                identity_added += len(evs)
        note(f"point-in-time identity investigation contributed {identity_added} filing "
             f"statements the ticker file could not reach")

    events, unmatched_filings, uncorroborated = [], [], []
    for sym, scan_events in sorted(merged.items()):
        for e in scan_events:
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
            factor = e["price_factor"]
            observed = ratios.get((sym, eff.isoformat()))
            # price_factor converts a price observed BEFORE the effective session into post-event
            # units, so a real event makes the observed session ratio and the factor equal: a
            # 1-for-25 consolidation carries factor 25 and prints a ratio near 25, and a 2-for-1
            # split carries factor 0.5 and prints a ratio near 0.5. The residual is therefore
            # ratio / factor, and it sits near 1 exactly when the tape shows what the filing says.
            residual = (observed / factor) if observed and factor else None
            flat = residual is not None and 0.8 <= residual <= 1.25
            rec = {
                "symbol": sym, "effective_session": eff.isoformat(), "price_factor": factor,
                "event_type": e["event_type"], "source": e["url"],
                "source_date": e["filing_date"], "source_form": e["form"],
                "source_items": e.get("items"), "ratio_text": e["ratio_text"],
                "observed_ratio": round(observed, 6) if observed else None,
                "residual_discontinuity_after_factor": round(residual, 4) if residual else None,
                "origin": "arrow014_sec_edgar_census"}
            if flat:
                rec["status"] = "PRIMARY_VERIFIED_AND_CORROBORATED_BY_TAPE"
                events.append(rec)
            else:
                rec["status"] = ("FILING_STATEMENT_NOT_CORROBORATED_BY_TAPE" if observed
                                 else "FILING_STATEMENT_NO_TAPE_OBSERVATION")
                rec["why_not_applied"] = (
                    "the stated factor does not flatten the observed session ratio, so the tape "
                    "does not show the unit change the filing describes" if observed else
                    "the end-of-day layer holds no ratio for this security at this session")
                uncorroborated.append(rec)

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
    note(f"filing statements with an effective date inside the corridor: "
         f"{len(events) + len(uncorroborated)}; applied because the tape corroborates them: "
         f"{len(events)}; recorded but NOT applied: {len(uncorroborated)}")

    explained = {(e["symbol"], e["effective_session"]) for e in events}
    unexplained = [c for k, c in sorted(cases.items())
                   if (c["symbol"], c["date"]) not in explained]
    note(f"screened cases without a filing explanation: {len(unexplained):,} of {len(cases):,}")

    by_status = Counter(v.get("status") for v in scans.values())
    ident_status = Counter()
    if identity_path.exists():
        for rec in read_json(identity_path).values():
            ident_status[(rec.get("identity") or {}).get("status")] += 1
    payload = {
        "version": "cg_arrow014_corporate_actions_v1",
        "timestamp": stamp(),
        "corridor_id": HO.CORRIDOR_ID,
        "factor_convention": ("price_factor multiplies a price observed before the effective "
                              "session to express it in post-event share units; share volume is "
                              "divided by the same factor"),
        "primary_source": "SEC EDGAR issuer filings",
        "identity_resolution": ("securities whose ticker SEC's current file no longer maps to an "
                                "issuer were resolved point-in-time through EDGAR full-text "
                                "search, counting a hit only where the ticker is the filer's own "
                                "registered symbol inside the corridor"),
        "identity_outcomes": dict(ident_status),
        "identity_filing_statements_contributed": identity_added,
        "scan_window": [SCAN_LO, SCAN_HI],
        "coverage": ("every security that showed a price level change at or beyond the screen "
                     "threshold, or a multi-session trading gap, inside a session its own cohorts "
                     "depend on; the screen ran over the whole corridor universe, not a shortlist"),
        "cases_investigated": len(cases),
        "securities_investigated": len(scans),
        "scan_status_counts": dict(by_status),
        "corroboration_rule": ("a factor is applied only when an issuer filing states the ratio "
                               "and a dated effect AND the independent end-of-day tape shows a "
                               "level change at that session which the factor flattens; a filing "
                               "the tape does not corroborate is recorded and never applied"),
        "events": events,
        "uncorroborated_filing_statements": uncorroborated,
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
        "uncorroborated_filing_statements": len(uncorroborated),
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
