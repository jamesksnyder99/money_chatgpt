"""CG Arrow 007 event census: build the candidate case set and gather primary evidence.

The Arrow 006 2x screen was triage. Here the screen runs at a lower threshold over the
candidates that could actually change a top eight, so smaller quantity-changing events
(3-for-2, 4-for-3 and similar) are not missed, and every case is taken to the issuer's own
SEC filings rather than to a price heuristic.

Usage: python scripts/cg_arrow007_events.py [--workers 8] [--top 25] [--threshold 1.2]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_events as ev  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    FEATS, INDEX, VERIFY_ROOT, dump_json, load_summaries, present, read_json, stamp,
)

WORK = VERIFY_ROOT / "work"
LOOKBACK = 15
T0 = time.monotonic()


def note(msg: str) -> None:
    print(f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}", flush=True)


def discontinuities(symbol: str, first_idx: int, last_idx: int, summaries: dict,
                    threshold: float) -> list[dict]:
    """Session-to-session price ratios beyond the threshold, in observation order."""
    out, prev = [], None
    for j in range(first_idx, last_idx + 1):
        d = FEATS[j]
        rec = summaries.get((d.isoformat(), symbol))
        if not present(rec):
            continue
        if prev is not None:
            for field in ("open", "close"):
                ratio = rec[field] / prev
                if max(ratio, 1 / ratio) >= threshold:
                    out.append({"date": d.isoformat(), "ratio": ratio, "field": field,
                                "close_before": prev, "close_at": rec["close"],
                                "volume_at": rec["volume"]})
                    break
        prev = rec["close"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--threshold", type=float, default=1.2)
    args = ap.parse_args()

    field = read_json(WORK / "cohort_field.json")
    ranks = read_json(REPO_ROOT / "data/tmp/cg_arrow002r/ranks_ALL_wed.json")
    note(f"cohorts={len(field)} threshold={args.threshold} top_k={args.top}")

    # 1. rank the whole field on unadjusted endpoints to find who could reach the top eight
    endpoints = set()
    for iso, cf in field.items():
        i = INDEX[date.fromisoformat(iso)]
        back = FEATS[i - LOOKBACK].isoformat()
        for s in cf["rule_field"]:
            endpoints.add((iso, s))
            endpoints.add((back, s))
    note(f"loading {len(endpoints)} ranking endpoints")
    sums = load_summaries(endpoints, args.workers)

    shortlist = {}
    for iso, cf in field.items():
        i = INDEX[date.fromisoformat(iso)]
        back = FEATS[i - LOOKBACK]
        rows = []
        for s in cf["rule_field"]:
            a = sums.get((back.isoformat(), s))
            b = sums.get((iso, s))
            if present(a) and present(b) and a["close"] > 0:
                rows.append((b["close"] / a["close"] - 1, s))
        rows.sort(reverse=True)
        shortlist[iso] = [s for _, s in rows[: args.top]]
    note(f"shortlist: {sum(len(v) for v in shortlist.values())} cohort-candidates, "
         f"{len({s for v in shortlist.values() for s in v})} unique symbols")

    # 2. screen the ranking window of every shortlisted candidate, plus the holding window
    #    of every historically recorded and Arrow 006 certified selection
    windows = set()
    for iso, syms in shortlist.items():
        i = INDEX[date.fromisoformat(iso)]
        for s in syms:
            for d in FEATS[i - LOOKBACK - 1: i + 1]:
                windows.add((d.isoformat(), s))
    recorded = {iso: [h["symbol"] for h in sorted(r["rows"], key=lambda x: -x["raw_return"])[:8]]
                for iso, r in ranks.items()}
    for iso, syms in recorded.items():
        i = INDEX[date.fromisoformat(iso)]
        for s in syms:
            for d in FEATS[i - LOOKBACK - 1: i + 12]:
                windows.add((d.isoformat(), s))
    note(f"loading {len(windows) - len(endpoints & windows)} additional window observations")
    sums.update(load_summaries(windows - set(sums), args.workers))

    cases = defaultdict(lambda: {"cohorts": set(), "roles": set(), "observations": []})
    for iso, syms in shortlist.items():
        i = INDEX[date.fromisoformat(iso)]
        for s in syms:
            for hit in discontinuities(s, i - LOOKBACK - 1, i, sums, args.threshold):
                c = cases[(s, hit["date"])]
                c["cohorts"].add(iso)
                c["roles"].add("ranking_window_shortlist")
                c["observations"].append(hit)
    for iso, syms in recorded.items():
        i = INDEX[date.fromisoformat(iso)]
        for s in syms:
            for hit in discontinuities(s, i - LOOKBACK - 1, min(i + 11, len(FEATS) - 1), sums, args.threshold):
                c = cases[(s, hit["date"])]
                c["cohorts"].add(iso)
                c["roles"].add("recorded_selection_window")
                c["observations"].append(hit)
    note(f"deduplicated cases: {len(cases)} unique symbol/date investigations, "
         f"{len({s for s, _ in cases})} unique symbols")

    payload = {f"{s}|{d}": {"symbol": s, "date": d, "cohorts": sorted(v["cohorts"]),
                            "roles": sorted(v["roles"]),
                            "max_ratio": max(v["observations"], key=lambda o: abs(o["ratio"] - 1))["ratio"],
                            "close_before": v["observations"][0]["close_before"],
                            "close_at": v["observations"][0]["close_at"]}
               for (s, d), v in cases.items()}
    dump_json(WORK / "event_cases.json", payload)

    # 3. primary-source investigation: one filing scan per security across the study window
    symbols = sorted({s for s, _ in cases})
    lo, hi = "2025-06-01", "2026-09-14"
    note(f"scanning {len(symbols)} securities against SEC EDGAR with {args.workers} workers")
    scans = ev.scan_symbols(symbols, lo, hi, workers=args.workers)
    dump_json(WORK / "event_symbol_scans.json", scans)
    found = sum(1 for v in scans.values() if v["status"] == "FILING_EVIDENCE_FOUND")
    note(f"filing evidence found for {found} of {len(scans)} securities")

    # 4. attach each security's filing evidence to its individual case dates
    evidence = {}
    for key, case in payload.items():
        sc = scans.get(case["symbol"], {})
        evidence[key] = {"symbol": case["symbol"], "event_date": case["date"],
                         "source_type": "SEC_EDGAR", "status": sc.get("status", "NOT_INVESTIGATED"),
                         "issuer": sc.get("issuer"), "cik": sc.get("cik"),
                         "former_names": sc.get("former_names", []),
                         "filings_scanned": sc.get("filings_scanned", 0),
                         "candidates": [e for e in sc.get("events", [])
                                        if abs((date.fromisoformat(e["filing_date"])
                                                - date.fromisoformat(case["date"])).days) <= 150]}
    dump_json(WORK / "event_evidence.json", evidence)
    by_status = defaultdict(int)
    for v in evidence.values():
        by_status[v["status"]] += 1
    note(f"case evidence status: {dict(by_status)}")
    note(f"cases with at least one filing candidate: "
         f"{sum(1 for v in evidence.values() if v['candidates'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
