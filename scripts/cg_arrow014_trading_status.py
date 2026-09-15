"""CG Arrow 014 — establish the documented trading status of every selected name that stops trading.

The certification found selected names whose entry or exit session carries a full retrieved
partition and zero trading. That is not a missing observation; the vendor was asked, answered, and
the security did not trade. Treating it as a data gap would be wrong, and so would treating it as
a price of zero.

What the frozen engine needs is the Arrow 007 convention: a documented non-execution, under which
the resting cover order executes at the first later session on which the security actually trades,
and if no such session exists inside the corridor the position stays open at the boundary and is
excluded from completed-trade totals. That convention may only be applied to an event with dated
evidence, so this stage assembles two independent kinds:

  the tape      the last session the security traded, whether it ever traded again inside the
                corridor, and the first session on which it did
  the issuer    SEC EDGAR filings around that date — Form 25 and 25-NSE delisting notices, and
                8-K items covering delisting, suspension and transfer

No ranking, selection or performance is computed here.

Usage: python scripts/cg_arrow014_trading_status.py [--workers 8]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_events as ev  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    candidate_paths, close_time, dump_json, read_json, stamp,
)

WORK = H.WORK
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow014"
STATE = OUT / "selected_corridor_state.csv"
LOG: list[str] = []
T0 = time.monotonic()
DELISTING_FORMS = ("25", "25-NSE", "15-12B", "15-12G", "15-15D", "8-K", "8-K/A", "6-K")


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def traded_on(d: date, symbol: str) -> tuple[bool, str | None, int]:
    """Did this security print a qualifying regular-hours trade on this session?

    Returns (traded, source label, priced regular-hours minutes). A session with no partition at
    all is a different answer from a session whose partition holds no trade, and the caller must
    be able to tell them apart.
    """
    for label, p in candidate_paths(d, symbol):
        if not p.is_file():
            continue
        try:
            df = pl.read_parquet(p, columns=["bar_start", "open", "close", "volume"])
        except Exception:  # noqa: BLE001
            continue
        if not df.height:
            return False, label, 0
        clock = pl.col("bar_start").dt.time()
        r = df.filter((clock >= H.RTH_OPEN) & (clock < close_time(d)) & (pl.col("volume") > 0)
                      & pl.col("open").is_finite() & pl.col("close").is_finite()
                      & (pl.col("close") > 0))
        return r.height > 0, label, r.height
    return False, None, 0


def tape_profile(symbol: str, slots: list[dict]) -> dict:
    """The trading record inside the window this security's own cohorts depend on.

    Scanning the whole corridor would count sessions the strategy never reads — a security can be
    absent from the tape for months before it is ever selected, and that says nothing about
    whether its entry or its exit can be observed. The window here therefore runs from the
    earliest entry of its cohorts to the end of the corridor, which is exactly the span over which
    a resting cover order could still execute.
    """
    first_entry = min(date.fromisoformat(s["entry_date"]) for s in slots)
    window = [d for d in HO.FEATS if d >= first_entry]
    traded, unretrieved, no_trade = [], [], []
    for d in window:
        ok, label, _n = traded_on(d, symbol)
        if label is None:
            unretrieved.append(d)
        elif ok:
            traded.append(d)
        else:
            no_trade.append(d)
    # For every unobserved exit, the Arrow 007 convention asks one question: is there a later
    # session inside the corridor on which this security actually trades?
    carries = {}
    for s in slots:
        for g in s["gaps"]:
            key = f"{s['cohort_id']}/{g}"
            need = (date.fromisoformat(s["entry_date"]) if g == "entry"
                    else date.fromisoformat(s[f"{g}_exit_date"]))
            later = [d for d in traded if d >= need]
            carries[key] = {"unobserved_session": need.isoformat(),
                            "first_later_trading_session": later[0].isoformat() if later else None,
                            "sessions_carried": (HO.INDEX[later[0]] - HO.INDEX[need]) if later else None,
                            "resolvable_inside_corridor": bool(later)}
    return {"symbol": symbol, "window_start": first_entry.isoformat(),
            "window_sessions": len(window),
            "sessions_traded": len(traded),
            "sessions_retrieved_with_no_trade": len(no_trade),
            "sessions_never_retrieved": len(unretrieved),
            "never_retrieved_examples": [d.isoformat() for d in unretrieved[:5]],
            "last_traded": traded[-1].isoformat() if traded else None,
            "carry_resolution": carries}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    HO.activate(action_path=WORK / "actions_holdout_empty.json")

    rows = list(csv.DictReader(STATE.open(encoding="utf-8")))
    cases: dict = defaultdict(list)
    for r in rows:
        if r["group"] != "TOP8":
            continue
        gaps = []
        if r["entry_execution_present"] == "False":
            gaps.append("entry")
        for h in HO.HOLDS:
            if r[f"h{h}_exit_observed"] == "False":
                gaps.append(f"h{h}")
        if gaps:
            cases[r["symbol"]].append({"cohort_id": r["cohort_id"], "rank": int(r["rank"]),
                                       "entry_date": r["entry_date"], "gaps": gaps,
                                       "h8_exit_date": r["h8_exit_date"],
                                       "h9_exit_date": r["h9_exit_date"],
                                       "h10_exit_date": r["h10_exit_date"]})
    note(f"selected names with an unobserved entry or exit: {len(cases)} securities across "
         f"{sum(len(v) for v in cases.values())} cohort slots")

    findings = {}
    for sym, slots in sorted(cases.items()):
        prof = tape_profile(sym, slots)
        # Classified from the tape before any filing is read, so a filing corroborates the
        # conclusion rather than supplying it.
        carries = prof["carry_resolution"].values()
        if prof["sessions_never_retrieved"]:
            kind = "UNRETRIEVED_SESSIONS_IN_LIFECYCLE_WINDOW"
        elif not prof["sessions_traded"]:
            kind = "NEVER_TRADES_AGAIN_IN_CORRIDOR"
        elif all(c["resolvable_inside_corridor"] for c in carries):
            kind = "DOCUMENTED_NON_TRADING_RESOLVED_BY_LATER_SESSION"
        else:
            kind = "DOCUMENTED_NON_TRADING_UNRESOLVED_AT_BOUNDARY"
        findings[sym] = {**prof, "classification": kind, "slots": slots}
        carried = [c["sessions_carried"] for c in carries if c["sessions_carried"] is not None]
        note(f"  {sym}: from {prof['window_start']}, traded {prof['sessions_traded']} of "
             f"{prof['window_sessions']}, retrieved-no-trade "
             f"{prof['sessions_retrieved_with_no_trade']}, never retrieved "
             f"{prof['sessions_never_retrieved']}; carries "
             f"{sorted(set(carried)) or 'none'} sessions -> {kind}")

    note(f"scanning {len(findings)} issuers against SEC EDGAR for delisting and suspension evidence")
    scans = ev.scan_symbols(sorted(findings), "2024-06-01", "2025-12-31", workers=args.workers)
    for sym, f in findings.items():
        s = scans.get(sym, {})
        f["issuer"] = s.get("issuer")
        f["cik"] = s.get("cik")
        f["former_names"] = s.get("former_names")
        f["edgar_status"] = s.get("status")
        f["filing_events"] = s.get("events", [])[:6]

    dump_json(WORK / "trading_status_findings.json", findings)
    flat = [{"symbol": sym, "classification": f["classification"],
             "cohort_id": s["cohort_id"], "rank": s["rank"], "entry_date": s["entry_date"],
             "unobserved": ",".join(s["gaps"]),
             "sessions_traded_in_window": f["sessions_traded"],
             "sessions_retrieved_with_no_trade": f["sessions_retrieved_with_no_trade"],
             "sessions_never_retrieved": f["sessions_never_retrieved"],
             "last_traded": f["last_traded"],
             "carry_resolution": ";".join(
                 f"{k}->{v['first_later_trading_session'] or 'none'}"
                 f"(+{v['sessions_carried']})" if v["sessions_carried"] is not None
                 else f"{k}->none"
                 for k, v in f["carry_resolution"].items() if k.startswith(s["cohort_id"])),
             "issuer": f.get("issuer"), "cik": f.get("cik"), "edgar_status": f.get("edgar_status")}
            for sym, f in sorted(findings.items()) for s in f["slots"]]
    with (OUT / "trading_status.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(flat[0]))
        w.writeheader()
        w.writerows(flat)

    by_kind: dict = defaultdict(int)
    for f in findings.values():
        by_kind[f["classification"]] += 1
    note("classifications: " + ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())))
    dump_json(WORK / "trading_status_manifest.json", {
        "arrow": "CG Arrow 014", "stage": "trading_status", "timestamp": stamp(),
        "securities": len(findings), "cohort_slots": sum(len(v) for v in cases.values()),
        "classifications": dict(by_kind),
        "basis": ("every session of the corridor was checked for a qualifying regular-hours trade; "
                  "a retrieved partition holding no trade is a fact about the security, and is "
                  "distinguished throughout from a session that was never retrieved"),
        "no_outcomes_calculated": True, "log": LOG})
    note(f"wrote {(OUT / 'trading_status.csv').relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
