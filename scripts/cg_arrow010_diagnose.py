"""Arrow 010 diagnosis: why does the rebuilt substrate not reproduce the certified controls?

Compares the membership this script's substrate build produces against the certified Arrow 008
membership hash, then narrows the difference to specific cohorts and names.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))

from ingest.paths import REPORTS  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    FEATS, INDEX, VERIFY_ROOT, action_events, load_summaries, non_comparable_events,
    read_json, set_vendor_status,
)
from cg_arrow007_run import candidate_meta, rank_with  # noqa: E402

WORK = VERIFY_ROOT / "work"
LOOKBACK = 15


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def main() -> int:
    a8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    certified = a8["membership_sha256"]
    print(f"certified membership sha256 : {certified}")

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
    members = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in corrected}
    mine = sha_obj(members)
    print(f"rebuilt   membership sha256 : {mine}")
    print(f"membership identical        : {mine == certified}")
    print(f"cohorts                     : {len(members)}")

    ledger = read_json(WORK / "a8_material_ledger.json") if (WORK / "a8_material_ledger.json").exists() else None
    print(f"material ledger present     : {ledger is not None}")

    # what does the certified private ledger say the members were?
    from ingest.paths import REPO_ROOT
    path = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008" / "r4r5_verified_trades.csv"
    print(f"certified trade csv present : {path.exists()}")
    if path.exists():
        import csv
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        cert_members = {}
        for r in rows:
            if r["model"] == "R5" and r["replay_stage"] == "R2_LEGACY_FILL_QTY":
                cert_members.setdefault(r["cohort_id"], []).append((int(r["rank"]), r["symbol"]))
        cert_members = {k: [s for _, s in sorted(v)] for k, v in cert_members.items()}
        print(f"certified cohorts in csv    : {len(cert_members)}")
        print(f"membership matches csv      : {cert_members == members}")
        diff = [k for k in sorted(set(cert_members) | set(members))
                if cert_members.get(k) != members.get(k)]
        print(f"cohorts that differ         : {len(diff)}")
        for k in diff[:6]:
            c = cert_members.get(k, [])
            m = members.get(k, [])
            print(f"  {k}")
            print(f"    certified : {c}")
            print(f"    rebuilt   : {m}")
            print(f"    added     : {sorted(set(m) - set(c))}")
            print(f"    dropped   : {sorted(set(c) - set(m))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
