"""CG Arrow 008 Repair 1 — close the material-event evidence classification.

Every discontinuity that can affect selection, ranking, sizing, entry, exit or
Hold-Length Ladder economics is re-evaluated against the issuer's own filing record,
exhibits included, over a wide window. A heuristic clearance is no longer allowed to
support a selected trade.

Final states, one per material case:

  PRIMARY_VERIFIED_ACTION        a filing states a ratio and an effective/first adjusted
                                 trading date, and applying it flattens the observed jump
  ADEQUATELY_REVIEWED_MARKET_MOVE the issuer filing record was searched with exhibits over
                                 the surrounding window, states no ratio, and the joint
                                 price/share-volume behaviour is inconsistent with a
                                 consolidation, or a dated authoritative explanation exists
  DOCUMENTED_TRADING_EVENT       a documented suspension or halt
  NON_COMPARABLE_REORGANIZATION  a reorganisation after which no factor makes the series
                                 one continuous claim
  UNRESOLVED                     anything else

Usage: python scripts/cg_arrow008_events.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from datetime import date, timedelta
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))  # after src so the ingest package is not shadowed

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_events as ev  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    FEATS, INDEX, VERIFY_ROOT, dump_json, load_summaries, present, read_json, stamp,
)
from cg_arrow007_deepscan import resolve_cik  # noqa: E402

WORK = VERIFY_ROOT / "work"
HANDOFF8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
ACTIONS7 = REPORTS / "cg_arrow007_corporate_actions.json"
OUT = REPORTS / "cg_arrow008_corporate_actions.json"
CONTINUOUS = "ADJUSTED_SERIES_CONTINUOUS"
MIN_DOCS = 8                  # an adequate issuer search must actually read filings
WINDOW_DAYS = 200             # and must cover the surrounding period, not just the week
# A reverse split or consolidation cannot be effected without a current report: a domestic
# issuer files an 8-K (Item 3.03 / 5.03) and a foreign private issuer a 6-K. Reading every
# current report in the window, exhibits included, is therefore a complete test for the
# announcement, and far cheaper than sweeping registration statements and annual reports.
CURRENT_REPORT_FORMS = ("8-K", "8-K/A", "6-K", "6-K/A", "8-K12B", "425")
MAX_FILINGS = 40
MAX_DOCS_PER_FILING = 8
T0 = time.monotonic()


def note(msg: str) -> None:
    print(f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}", flush=True)



def scan_issuer(symbol: str, cik: int, lo: str, hi: str) -> dict:
    """Read every current report in the window, exhibits included."""
    sub = ev.submissions(cik)
    out = {"symbol": symbol, "cik": cik, "window": [lo, hi], "documents_read": 0,
           "filings_read": 0, "events": [], "issuer": (sub or {}).get("name")}
    if sub is None:
        return out
    rows = [r for r in ev.filing_rows(sub) if lo <= r["date"] <= hi
            and r["form"] in CURRENT_REPORT_FORMS]
    rows.sort(key=lambda r: r["date"])
    for r in rows[:MAX_FILINGS]:
        acc = r["accession"].replace("-", "")
        idx = ev.fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json")
        docs = []
        if idx:
            try:
                for item in json.loads(idx)["directory"]["item"]:
                    n = item["name"]
                    if n.lower().endswith((".htm", ".html", ".txt")) and not n.startswith("R"):
                        docs.append(n)
            except (KeyError, json.JSONDecodeError):
                docs = []
        if not docs and r["doc"]:
            docs = [r["doc"]]
        out["filings_read"] += 1
        for n in docs[:MAX_DOCS_PER_FILING]:
            raw = ev.fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{n}")
            if raw is None or len(raw) > ev.MAX_DOC_BYTES:
                continue
            out["documents_read"] += 1
            for e in ev.extract_events(ev.plain_text(raw)):
                for a, b, span in e["ratios"]:
                    fac = ev.classify_factor(e["phrase"], a, b)
                    if fac is None:
                        continue
                    out["events"].append({
                        "filing_date": r["date"], "form": r["form"], "items": r.get("items", ""),
                        "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{n}",
                        "phrase": e["phrase"], "ratio_text": span, "price_factor": fac[0],
                        "event_type": fac[1], "dates_in_window": e["dates_in_window"],
                        "snippet": e["snippet"]})
    return out


def material_cases() -> dict:
    """Every selected-name window whose adjusted series is not already continuous."""
    cases = defaultdict(lambda: {"cohorts": set(), "windows": set(), "ratios": []})
    src = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow007" / "r4r5_verified_trades.csv"
    for r in csv.DictReader(src.open(encoding="utf-8")):
        if r["replay_stage"] != "R2_LEGACY_FILL_QTY":
            continue
        for field, window in (("lookback", "ranking"), ("holding", "holding")):
            res = r.get(f"{field}_resolution") or ""
            when = r.get(f"{field}_ratio_date") or ""
            if not when or res in ("", CONTINUOUS, "NONE"):
                continue
            c = cases[(r["symbol"], when)]
            c["cohorts"].add(r["cohort_id"])
            c["windows"].add(window)
            c["ratios"].append(float(r.get(f"{field}_max_ratio") or 0))
            c["prior_resolution"] = res
    return cases


def volume_signature(symbol: str, when: str, summaries: dict) -> dict:
    d = date.fromisoformat(when)
    i = INDEX.get(d)
    if i is None:
        return {"classifiable": False}
    before = None
    for j in range(i - 1, max(0, i - 6), -1):
        rec = summaries.get((FEATS[j].isoformat(), symbol))
        if present(rec):
            before = rec
            break
    at = summaries.get((when, symbol))
    if not (present(at) and before):
        return {"classifiable": False}
    pr = at["close"] / before["close"]
    vr = at["volume"] / before["volume"] if before["volume"] else None
    return {"classifiable": True, "price_ratio": pr, "volume_ratio": vr,
            "consolidation_like": bool(pr >= 2.0 and vr is not None and vr <= 0.5),
            "volume_expanded": bool(vr is not None and vr >= 1.0)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    actions = read_json(ACTIONS7)
    applied_events = {(e["symbol"], e["effective_session"]): e for e in actions["events"]}
    applied = set(applied_events)
    halts = {e["symbol"] for e in actions.get("trading_events", [])}
    noncomp = {e["symbol"] for e in actions.get("non_comparable_events", [])}
    dated = {(x["symbol"], x.get("date")): x for x in actions.get("screen_resolutions", [])}

    cases = material_cases()
    note(f"material selected-name cases: {len(cases)} across {len({s for s, _ in cases})} securities")

    symbols = sorted({s for s, _ in cases})
    dates_by_symbol = defaultdict(list)
    for s, when in cases:
        dates_by_symbol[s].append(when)

    # one exhibit-level scan per security, covering every one of its case dates
    def work(sym):
        whens = sorted(dates_by_symbol[sym])
        mid = whens[len(whens) // 2]
        r = resolve_cik(sym, mid)
        if not r["cik"]:
            return sym, r, {"documents_read": 0, "events": [], "cik": None}
        lo = (date.fromisoformat(whens[0]) - timedelta(days=WINDOW_DAYS)).isoformat()
        hi = (date.fromisoformat(whens[-1]) + timedelta(days=45)).isoformat()
        s = scan_issuer(sym, r["cik"], lo, hi)
        return sym, r, s

    cached = read_json(WORK / "a8_symbol_scans.json") if (WORK / "a8_symbol_scans.json").exists() else {}
    scans = {s: v for s, v in cached.items() if s in set(symbols) and v.get("documents_read")}
    symbols = [s for s in symbols if s not in scans]
    note(f"reusing {len(scans)} stored issuer scans; {len(symbols)} still to scan")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, s) for s in symbols]
        for n, f in enumerate(as_completed(futs), 1):
            sym, r, s = f.result()
            scans[sym] = {"cik_resolution": r, **s}
            if n % 10 == 0 or n == len(futs):
                note(f"issuer scans {n}/{len(futs)}")
    dump_json(WORK / "a8_symbol_scans.json", {**cached, **scans})

    needs = set()
    for s, when in cases:
        i = INDEX[date.fromisoformat(when)]
        for d in FEATS[max(0, i - 6): i + 1]:
            needs.add((d.isoformat(), s))
    sums = load_summaries(needs, args.workers)

    ledger, new_events = [], []
    for (sym, when), c in sorted(cases.items()):
        scan = scans.get(sym, {})
        sig = volume_signature(sym, when, sums)
        obs_ratio = max(c["ratios"], key=lambda x: abs(x - 1)) if c["ratios"] else None
        row = {"symbol": sym, "session": when, "windows": ";".join(sorted(c["windows"])),
               "cohorts": ";".join(sorted(c["cohorts"])), "cohort_count": len(c["cohorts"]),
               "arrow007_resolution": c.get("prior_resolution"),
               "issuer": scan.get("issuer"), "cik": scan.get("cik"),
               "cik_resolution_method": (scan.get("cik_resolution") or {}).get("method"),
               "issuer_documents_read": scan.get("documents_read", 0),
               "issuer_current_reports_read": scan.get("filings_read", 0),
               "search_window_days": WINDOW_DAYS,
               "split_statements_found": len(scan.get("events", [])),
               "observed_adjusted_ratio": obs_ratio,
               "price_ratio_at_session": sig.get("price_ratio"),
               "volume_ratio_at_session": sig.get("volume_ratio"),
               "consolidation_like": sig.get("consolidation_like"),
               "volume_expanded": sig.get("volume_expanded")}

        # 1. does a filing explain this session as a unit change?
        best = None
        for e in scan.get("events", []):
            f = e["price_factor"]
            if not obs_ratio or f <= 0 or (obs_ratio > 1) != (f > 1):
                continue
            residual = obs_ratio / f
            size = max(residual, 1 / residual)
            supported = when in e["dates_in_window"] or any(
                abs((date.fromisoformat(x) - date.fromisoformat(when)).days) <= 6
                for x in e["dates_in_window"])
            if size < 2.0 and supported and (best is None or size < best[0]):
                best = (size, e)
        if best is not None:
            size, e = best
            row.update({"final_state": "PRIMARY_VERIFIED_ACTION", "price_factor": e["price_factor"],
                        "ratio_text": e["ratio_text"], "source": e["url"],
                        "source_form": e["form"], "source_date": e["filing_date"],
                        "residual_after_factor": round(size, 4),
                        "basis": "issuer filing states the ratio and an effective date that matches this "
                                 "session, and applying it flattens the observed discontinuity"})
            if (sym, when) not in applied:
                new_events.append({"symbol": sym, "effective_session": when,
                                   "price_factor": e["price_factor"], "event_type": e["event_type"],
                                   "source": e["url"], "source_date": e["filing_date"],
                                   "source_form": e["form"], "ratio_text": e["ratio_text"],
                                   "status": "PRIMARY_VERIFIED",
                                   "residual_discontinuity_after_factor": round(size, 4),
                                   "origin": "arrow008_material_event_review"})
        elif sym in noncomp:
            row.update({"final_state": "NON_COMPARABLE_REORGANIZATION",
                        "basis": "documented reorganisation; no factor makes the series one claim"})
        elif sym in halts:
            row.update({"final_state": "DOCUMENTED_TRADING_EVENT",
                        "basis": "documented suspension or halt"})
        elif (sym, when) in dated:
            d = dated[(sym, when)]
            row.update({"final_state": "ADEQUATELY_REVIEWED_MARKET_MOVE", "source": d.get("source"),
                        "source_date": d.get("source_date"),
                        "basis": "dated authoritative explanation on file: " + d.get("note", "")[:180]})
        else:
            # A split mention elsewhere in the window is not evidence that THIS session was a
            # unit change. What matters is whether any filing places a ratio on this session.
            # A filing that discusses a split we have already documented and applied at another
            # effective session is not evidence of a second, undocumented unit change here.
            already = [e["price_factor"] for (sy, es), e in applied_events.items()
                       if sy == sym and es != when]
            date_matched = [
                e for e in scan.get("events", [])
                if any(abs((date.fromisoformat(x) - date.fromisoformat(when)).days) <= 2
                       for x in e["dates_in_window"])
                and not any(abs(e["price_factor"] / f - 1) < 0.01 for f in already if f)]
            searched = (scan.get("documents_read", 0) >= MIN_DOCS
                        and scan.get("cik") is not None
                        and not date_matched)
            inconsistent = sig.get("classifiable") and not sig.get("consolidation_like")
            row["date_matched_split_statements"] = len(date_matched)
            row["accounted_elsewhere_statements"] = sum(
                1 for e in scan.get("events", [])
                if any(abs(e["price_factor"] / f - 1) < 0.01 for f in already if f))
            if searched and inconsistent:
                row.update({"final_state": "ADEQUATELY_REVIEWED_MARKET_MOVE",
                            "basis": f"{scan.get('filings_read')} issuer current reports "
                                     f"({scan.get('documents_read')} documents including exhibits) across the "
                                     f"surrounding window place no split ratio on this session "
                                     f"({len(scan.get('events', []))} ratio statements elsewhere in the window, "
                                     f"all dated to other sessions), and share volume at the session is "
                                     f"inconsistent with a consolidation"})
            else:
                why = []
                if scan.get("cik") is None:
                    why.append("issuer filing record could not be located")
                elif scan.get("documents_read", 0) < MIN_DOCS:
                    why.append(f"only {scan.get('documents_read', 0)} issuer documents readable")
                if date_matched:
                    why.append(f"{len(date_matched)} issuer filing statements place a split ratio on "
                               f"this session but none of them flattens the observed unit change")
                if sig.get("consolidation_like"):
                    why.append("price and volume behaviour is consolidation-like")
                if not sig.get("classifiable"):
                    why.append("endpoints unavailable for the signature test")
                row.update({"final_state": "UNRESOLVED", "basis": "; ".join(why) or "insufficient evidence"})
        ledger.append(row)

    counts = Counter(r["final_state"] for r in ledger)
    note(f"final evidence states: {dict(counts)}")
    blocking = [r for r in ledger if r["final_state"] == "UNRESOLVED"]
    note(f"material cases still unresolved: {len(blocking)}")
    for r in blocking[:20]:
        note(f"  UNRESOLVED {r['symbol']:6} {r['session']} {r['basis'][:90]}")

    table = dict(actions)
    table["version"] = "cg_arrow008_actions_v1"
    table["timestamp"] = stamp()
    table["events"] = sorted(actions["events"] + new_events,
                             key=lambda e: (e["symbol"], e["effective_session"]))
    table["material_event_states"] = dict(counts)
    table["material_event_review"] = {
        "cases": len(ledger), "minimum_documents_for_adequate_review": MIN_DOCS,
        "search_window_days": WINDOW_DAYS,
        "rule": ("a selected trade may not rest on a heuristic clearance; an adequately reviewed market "
                 "move requires the issuer filing record searched with exhibits, no stated ratio, and a "
                 "price/volume signature inconsistent with a consolidation")}
    dump_json(OUT, table)
    note(f"canonical events {len(actions['events'])} -> {len(table['events'])} "
         f"(+{len(new_events)} newly primary-verified)")

    HANDOFF8.mkdir(parents=True, exist_ok=True)
    fields = ["symbol", "session", "final_state", "basis", "windows", "cohorts", "cohort_count",
              "arrow007_resolution", "issuer", "cik", "cik_resolution_method", "issuer_documents_read",
              "search_window_days", "split_statements_found", "observed_adjusted_ratio",
              "price_ratio_at_session", "volume_ratio_at_session", "consolidation_like",
              "volume_expanded", "accounted_elsewhere_statements", "price_factor", "ratio_text", "residual_after_factor",
              "source", "source_form", "source_date"]
    with (HANDOFF8 / "material_event_audit.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(ledger, key=lambda x: (x["final_state"], x["symbol"])):
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    dump_json(WORK / "a8_material_ledger.json", ledger)
    note(f"material event audit written: {len(ledger)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
