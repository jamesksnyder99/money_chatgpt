"""CG Arrow 007 audit exports: action ledger, three-way ranking reconciliation, upside bridge.

Private detail goes to handoff/outgoing/cg_arrow007; the public copies carry the same rows
without proprietary raw bar values.

Usage: python scripts/cg_arrow007_exports.py
"""
from __future__ import annotations

from collections import defaultdict
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification.r4r5_data import ACTION_PATH, VERIFY_ROOT, digest, read_json, stamp  # noqa: E402

WORK = VERIFY_ROOT / "work"
HANDOFF7 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow007"
PUBLIC_DROP = {"close_before", "close_at", "observed_close_before", "observed_close_at"}


def write(path: Path, rows: list[dict], fields=None) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or list({k: None for r in rows for k in r})
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    tmp.replace(path)
    return digest(path)


def flat(v):
    if isinstance(v, (list, tuple)):
        return ";".join(str(x) for x in v)
    if isinstance(v, dict):
        return ";".join(f"{a}={b}" for a, b in v.items())
    return v


def main() -> int:
    man = read_json(REPORTS / "cg_arrow007_manifest.json")
    actions = read_json(ACTION_PATH)
    ledger_src = read_json(WORK / "action_ledger.json")

    # ---- corporate action ledger: every investigation with its evidence and status
    rows = [{k: flat(v) for k, v in r.items() if k != "snippet"} for r in ledger_src]
    applied = {(e["symbol"], e["effective_session"]): e for e in actions["events"]}
    for r in rows:
        key = (r["symbol"], r["observed_session"])
        r["applied_as_canonical_event"] = key in applied
        r["canonical_price_factor"] = applied.get(key, {}).get("price_factor")
        r["canonical_status"] = applied.get(key, {}).get("status")
    for e in actions["events"]:
        if (e["symbol"], e["effective_session"]) not in {(r["symbol"], r["observed_session"]) for r in rows}:
            rows.append({"symbol": e["symbol"], "observed_session": e["effective_session"],
                         "resolution": "INHERITED_OR_REVIEWED_EVENT", "applied_as_canonical_event": True,
                         "canonical_price_factor": e["price_factor"], "canonical_status": e.get("status"),
                         "event_type": e.get("event_type"), "source": e.get("source"),
                         "filing_date": e.get("source_date"), "ratio_text": e.get("ratio_text")})
    for e in actions.get("non_comparable_events", []):
        rows.append({"symbol": e["symbol"], "observed_session": e["effective_session"],
                     "resolution": "NON_COMPARABLE_REORGANIZATION", "applied_as_canonical_event": True,
                     "canonical_status": e.get("status"), "event_type": e["event_type"],
                     "source": e["source"], "filing_date": e.get("source_date"),
                     "ratio_text": e.get("note")})
    fields = ["symbol", "observed_session", "resolution", "event_type", "canonical_price_factor",
              "canonical_status", "applied_as_canonical_event", "observed_price_ratio",
              "residual_discontinuity_after_factor", "filing_form", "filing_date", "filing_items",
              "source", "ratio_text", "issuer", "cik", "evidence_status", "filing_candidates",
              "cohorts_touched", "roles", "note"]
    h_led = write(HANDOFF7 / "r4r5_corporate_action_ledger.csv", rows, fields)
    write(REPORTS / "cg_arrow007_corporate_action_ledger.csv",
          [{k: v for k, v in r.items() if k not in PUBLIC_DROP} for r in rows], fields)

    # ---- three-way ranking reconciliation
    rec = []
    for r in man["ranking_reconciliation"]:
        rec.append({"cohort_id": r["cohort_id"], "split": r["split"],
                    "R0_RAW_CACHE_TOP8": ";".join(r["R0_RAW_CACHE_TOP8"]),
                    "R1_RECORDED_TOP8": ";".join(r["R1_RECORDED_TOP8"]),
                    "R2_CERTIFIED_TOP8": ";".join(r["R2_CERTIFIED_TOP8"]),
                    "raw_field_size": r["raw_field_size"],
                    "certified_field_size": r["certified_field_size"],
                    "membership_change_vs_recorded": r["membership_change_vs_recorded"],
                    "order_only_change_vs_recorded": r["order_only_change_vs_recorded"],
                    "added_vs_recorded": ";".join(r["added_vs_recorded"]),
                    "dropped_vs_recorded": ";".join(r["dropped_vs_recorded"]),
                    "unrankable_unresolved": r["unrankable_unresolved"]})
    h_rec = write(HANDOFF7 / "r4r5_ranking_reconciliation.csv", rec)
    write(REPORTS / "cg_arrow007_ranking_reconciliation.csv", rec)

    # ---- R1 -> R2 upside bridge, per cohort and per symbol
    bridge_rows = []
    for fam, b in man["upside_bridge"].items():
        bridge_rows.append({"model": fam, "level": "TOTAL", "key": "ALL",
                            "r1_net": round(b["r1_total"], 2), "r2_net": round(b["r2_total"], 2),
                            "delta": round(b["r2_total"] - b["r1_total"], 2),
                            "common_tickets": b["common_tickets"],
                            "common_difference": round(b["common_difference"], 2),
                            "added_tickets": b["added_tickets"], "added_net": round(b["added_net"], 2),
                            "dropped_tickets": b["dropped_tickets"],
                            "dropped_net_removed": round(-b["dropped_net"], 2)})
        for cohort, v in b["per_cohort"].items():
            bridge_rows.append({"model": fam, "level": "COHORT", "key": cohort,
                                "r1_net": v["r1"], "r2_net": v["r2"], "delta": v["delta"]})
        for s in b["top_symbol_contributions"]:
            bridge_rows.append({"model": fam, "level": "SYMBOL_EFFECT", "key": s["symbol"],
                                "delta": s["net_effect"]})
    h_bridge = write(HANDOFF7 / "r4r5_r2_upside_bridge.csv", bridge_rows)
    write(REPORTS / "cg_arrow007_upside_bridge.csv", bridge_rows)

    # ---- safe split-owned account aggregates
    books = [{"book": k, **{kk: (round(vv, 4) if isinstance(vv, float) else flat(vv))
                            for kk, vv in v.items() if kk != "book"}}
             for k, v in man["split_owned_books"].items()]
    write(REPORTS / "cg_arrow007_baseline_results.csv", books)

    print(f"{stamp()} action ledger rows={len(rows)} reconciliation={len(rec)} "
          f"bridge={len(bridge_rows)} books={len(books)}")
    print(f"{stamp()} hashes ledger={h_led[:16]} reconciliation={h_rec[:16]} bridge={h_bridge[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
