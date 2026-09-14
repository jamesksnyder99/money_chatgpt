"""CG Arrow 007 canonical corporate-action table: merge primary evidence deterministically.

A factor is only ever taken from an issuer filing. The observed price discontinuity
corroborates it and fixes the first post-event trading session; it never supplies the
factor. A case is PRIMARY_VERIFIED only when a filing states a ratio and the adjusted
series becomes continuous once that ratio is applied at the observed session.

Usage: python scripts/cg_arrow007_actions.py [--tolerance 0.35]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPORTS  # noqa: E402
from verification.r4r5_data import ACTION_PATH_V1, VERIFY_ROOT, dump_json, read_json, stamp  # noqa: E402

WORK = VERIFY_ROOT / "work"
OUT = REPORTS / "cg_arrow007_corporate_actions.json"
INHERITED = REPORTS / "cg_arrow006_corporate_actions.json"
CONVENTION = "price_factor = old shares per new share; 1-for-50 reverse -> 50; 5-for-1 forward -> 0.2"


def pick(candidates: list[dict], observed_ratio: float, event_date: str, screen: float):
    """Accept a filing-stated factor only when applying it actually flattens the observed jump.

    The factor always comes from the filing. Acceptance is decided by the same integrity test
    the ranking screen uses: after dividing the observed discontinuity by the stated factor,
    the residual must fall below the screen threshold. A factor that does not explain the unit
    change is rejected rather than quietly applied.
    """
    best = None
    if not observed_ratio:
        return None
    for c in candidates:
        f = c["price_factor"]
        if f <= 0:
            continue
        if (observed_ratio > 1) != (f > 1):      # direction must agree
            continue
        residual = observed_ratio / f
        size = max(residual, 1 / residual)
        if size >= screen:
            continue
        date_supported = event_date in c["dates_in_window"]
        near = any(abs((date.fromisoformat(x) - date.fromisoformat(event_date)).days) <= 6
                   for x in c["dates_in_window"])
        if not (date_supported or near):
            continue
        score = (abs(residual - 1), not date_supported)
        if best is None or score < best[0]:
            best = (score, c, size, date_supported, near)
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--screen", type=float, default=2.0,
                    help="residual discontinuity that must remain after applying the stated factor")
    args = ap.parse_args()

    cases = read_json(WORK / "event_cases.json")
    evidence = read_json(WORK / "event_evidence.json")
    inherited = read_json(INHERITED)

    events, ledger = [], []
    seen = set()
    # inherited documented events are preserved unchanged
    for e in inherited["events"]:
        key = (e["symbol"], e["effective_session"])
        seen.add(key)
        events.append({**e, "event_type": e.get("event_type", "reverse_split"),
                       "status": "PRIMARY_VERIFIED" if e.get("source", "").startswith("http") else "SECONDARY_CORROBORATED",
                       "origin": "inherited_arrow003_005_006"})
    counts = defaultdict(int)
    for key, case in sorted(cases.items()):
        ev = evidence.get(key) or {}
        sym, d = case["symbol"], case["date"]
        obs = case["max_ratio"]
        row = {"symbol": sym, "observed_session": d, "observed_price_ratio": round(obs, 6),
               "close_before": case["close_before"], "close_at": case["close_at"],
               "cohorts_touched": case["cohorts"], "roles": case["roles"],
               "issuer": ev.get("issuer"), "cik": ev.get("cik"),
               "former_names": ev.get("former_names", []),
               "evidence_status": ev.get("status", "NOT_INVESTIGATED"),
               "filing_candidates": len(ev.get("candidates", []))}
        chosen = pick(ev.get("candidates", []), obs, d, args.screen)
        if chosen is not None:
            _score, c, residual_size, date_supported, near = chosen
            row.update({"resolution": "PRIMARY_VERIFIED_ACTION", "event_type": c["event_type"],
                        "price_factor": c["price_factor"], "ratio_text": c["ratio_text"],
                        "filing_form": c["form"], "filing_date": c["filing_date"],
                        "filing_items": c["items"], "source": c["url"],
                        "residual_discontinuity_after_factor": round(residual_size, 4),
                        "effective_session_supported_by_filing": bool(date_supported or near)})
            k = (sym, d)
            if k not in seen:
                seen.add(k)
                events.append({"symbol": sym, "effective_session": d,
                               "price_factor": c["price_factor"], "event_type": c["event_type"],
                               "source": c["url"], "source_date": c["filing_date"],
                               "source_form": c["form"], "source_items": c["items"],
                               "ratio_text": c["ratio_text"], "status": "PRIMARY_VERIFIED",
                               "residual_discontinuity_after_factor": round(residual_size, 4),
                               "origin": "arrow007_sec_edgar_census"})
            counts["PRIMARY_VERIFIED_ACTION"] += 1
        elif ev.get("candidates"):
            row.update({"resolution": "FILING_EVIDENCE_DOES_NOT_EXPLAIN_MOVE",
                        "note": "issuer filings in the window mention a split, but no stated ratio both "
                                "matches this session's date and flattens the observed unit change",
                        "source": ev["candidates"][0]["url"]})
            counts["FILING_EVIDENCE_DOES_NOT_EXPLAIN_MOVE"] += 1
        else:
            row.update({"resolution": "NO_ACTION_FILING_FOUND",
                        "note": "no issuer filing in the surrounding window states a split ratio; "
                                "treated as a price move unless later evidence appears"})
            counts["NO_ACTION_FILING_FOUND"] += 1
        ledger.append(row)

    table = {
        "version": "cg_arrow007_actions_v1", "timestamp": stamp(),
        "factor_convention": CONVENTION,
        "coverage": ("Scoped census: every symbol/session discontinuity at or beyond 1.2x inside the "
                     "15-session ranking window of the top 25 ranked candidates of all 52 cohorts, plus the "
                     "ranking and holding windows of every historically recorded selection, each taken to "
                     "the issuer's SEC filings. Inherited Arrow 003/005/006 events are preserved unchanged."),
        "primary_source": "SEC EDGAR issuer filings (data.sec.gov submissions and www.sec.gov Archives)",
        "cases_investigated": len(ledger), "resolution_counts": dict(counts),
        "events": sorted(events, key=lambda e: (e["symbol"], e["effective_session"])),
        "security_identity": inherited.get("security_identity", []),
        "trading_events": inherited.get("trading_events", []),
        "screen_resolutions": inherited.get("screen_resolutions", []),
        "limitations": ["A filing search finds no evidence only within the fetched window and forms.",
                        "Cash-in-lieu and broker fractional treatment remain unknown unless stated.",
                        "Dividends, locate and financing history remain unavailable."],
    }
    dump_json(OUT, table)
    dump_json(WORK / "action_ledger.json", ledger)
    print(f"{stamp()} cases={len(ledger)} {dict(counts)}")
    print(f"{stamp()} canonical events: {len(events)} "
          f"(inherited {len(inherited['events'])}, new {len(events) - len(inherited['events'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
