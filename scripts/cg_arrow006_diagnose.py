"""CG Arrow 006 diagnostic: characterise the uncertified ranking-window discontinuities.

For every selected trade whose 15-session ranking window contains an undocumented
single-session discontinuity of 2x or more, this records the joint price and share-volume
behaviour at that session, and whether the security's price immediately before the jump sat
below the strategy's $10 eligibility floor.

This never infers a corporate action and never adjusts a price. It is a bounded diagnostic
that describes the flagged population so the next pass knows exactly what evidence to seek.
A share consolidation multiplies price and divides share volume by the same factor, leaving
dollar volume roughly continuous; a genuine repricing does not.

Usage: python scripts/cg_arrow006_diagnose.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPORTS  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    FEATS, HANDOFF, INDEX, VERIFY_ROOT, dump_json, load_summaries, present, read_json, stamp,
)

WORK = VERIFY_ROOT / "work"
HANDOFF6 = HANDOFF.parent / "cg_arrow006"
PRICE_FLOOR = 10.0


def classify(price_ratio: float, volume_ratio: float | None, before_close: float) -> str:
    """Label the joint signature. A label is a description of evidence, never a factor."""
    if price_ratio >= 2.0 and volume_ratio is not None and volume_ratio <= 0.5:
        if before_close < PRICE_FLOOR:
            return "CONSOLIDATION_SIGNATURE_FROM_BELOW_ELIGIBILITY_FLOOR"
        return "CONSOLIDATION_SIGNATURE"
    if price_ratio >= 2.0:
        return "PRICE_RISE_WITHOUT_VOLUME_CONTRACTION"
    if price_ratio <= 0.5 and volume_ratio is not None and volume_ratio >= 2.0:
        return "PRICE_FALL_WITH_VOLUME_EXPANSION"
    return "OTHER_DISCONTINUITY"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    man = read_json(REPORTS / "cg_arrow006_manifest.json")
    state = read_json(WORK / "baseline_state.json")
    flags = [f for f in man["ranking_window_flags"]
             if f[4] == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY"]
    print(f"{stamp()} characterising {len(flags)} uncertified ranking-window flags", flush=True)

    needs = set()
    for sym, cohort_id, ratio, flag_date, _res in flags:
        i = INDEX[date.fromisoformat(flag_date)]
        for d in FEATS[i - 1: i + 2]:
            needs.add((d.isoformat(), sym))
    s = load_summaries(needs, args.workers)

    rows = []
    for sym, cohort_id, ratio, flag_date, _res in flags:
        d = date.fromisoformat(flag_date)
        i = INDEX[d]
        before = s.get((FEATS[i - 1].isoformat(), sym))
        at = s.get((d.isoformat(), sym))
        if not (present(before) and present(at)):
            rows.append({"symbol": sym, "cohort_id": cohort_id, "flag_date": flag_date,
                         "price_ratio": ratio, "classification": "ENDPOINTS_UNAVAILABLE"})
            continue
        pr = at["close"] / before["close"]
        vr = at["volume"] / before["volume"] if before["volume"] else None
        rows.append({
            "symbol": sym, "cohort_id": cohort_id, "flag_date": flag_date,
            "price_ratio": round(pr, 4),
            "volume_ratio": round(vr, 6) if vr is not None else None,
            "dollar_volume_ratio": round(pr * vr, 4) if vr is not None else None,
            "close_before": round(before["close"], 6), "close_at": round(at["close"], 6),
            "below_eligibility_floor_before": before["close"] < PRICE_FLOOR,
            "classification": classify(pr, vr, before["close"])})

    counts = Counter(r["classification"] for r in rows)
    out = HANDOFF6 / "r4r5_ranking_window_diagnostics.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["symbol", "cohort_id", "flag_date", "price_ratio", "volume_ratio", "dollar_volume_ratio",
              "close_before", "close_at", "below_eligibility_floor_before", "classification"]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(rows, key=lambda x: -(x.get("price_ratio") or 0)):
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    summary = {"timestamp": stamp(), "flags_characterised": len(rows), "classification_counts": dict(counts),
               "consolidation_signature_total": counts["CONSOLIDATION_SIGNATURE"]
               + counts["CONSOLIDATION_SIGNATURE_FROM_BELOW_ELIGIBILITY_FLOOR"],
               "from_below_eligibility_floor": counts["CONSOLIDATION_SIGNATURE_FROM_BELOW_ELIGIBILITY_FLOOR"],
               "method": ("joint price and share-volume behaviour at the flagged session; a consolidation "
                          "multiplies price and divides share volume by the same factor. Diagnostic only: "
                          "no corporate action is inferred and no price is adjusted."),
               "local_detail": out.as_posix()}
    dump_json(REPORTS / "cg_arrow006_ranking_window_diagnostics.json", summary)
    print(f"{stamp()} {dict(counts)}", flush=True)
    print(f"{stamp()} wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
