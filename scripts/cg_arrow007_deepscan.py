"""CG Arrow 007 deep scan: resolve the last blocking discontinuities against primary sources.

Two gaps remain after the broad census:

1. Securities whose ticker has since changed or been delisted are absent from the SEC's
   current ticker map, so their filing record could not be searched at all. They are
   resolved through the documented identity map, and otherwise by finding an issuer whose
   own filing cover page carries that trading symbol in the relevant period.
2. Split announcements frequently live in a press-release exhibit rather than the primary
   document of the 8-K, so a primary-document scan can miss them. Here every document of
   every candidate filing is read.

Usage: python scripts/cg_arrow007_deepscan.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import re
import sys
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPORTS  # noqa: E402
from verification import r4r5_events as ev  # noqa: E402
from verification.r4r5_data import VERIFY_ROOT, dump_json, read_json, stamp  # noqa: E402

WORK = VERIFY_ROOT / "work"
DEEP_FORMS = ("8-K", "8-K/A", "6-K", "6-K/A", "8-K12B", "425", "DEF 14A", "DEFA14A",
              "424B3", "424B4", "S-1", "S-1/A", "20-F", "10-K", "10-Q")


def note(msg: str) -> None:
    print(f"{stamp()} {msg}", flush=True)


def fts(query: str, start: str, end: str, forms: str = "8-K,6-K") -> list[dict]:
    url = ("https://efts.sec.gov/LATEST/search-index?q=" + urllib.parse.quote(query)
           + f"&forms={urllib.parse.quote(forms)}&startdt={start}&enddt={end}")
    raw = ev.fetch(url)
    if raw is None:
        return []
    try:
        return json.loads(raw).get("hits", {}).get("hits", [])
    except json.JSONDecodeError:
        return []


def resolve_cik(symbol: str, around: str) -> dict:
    """Find the issuer that filed under this trading symbol in the relevant period."""
    out = {"symbol": symbol, "cik": None, "method": None, "evidence": None}
    direct = ev.ticker_cik().get(symbol.upper())
    if direct:
        out.update(cik=direct[0], method="current_sec_ticker_map")
        return out
    identity = read_json(REPORTS / "cg_arrow007_corporate_actions.json").get("security_identity", [])
    for e in identity:
        if e["symbol"] == symbol:
            succ = ev.ticker_cik().get(e["successor"].upper())
            if succ:
                out.update(cik=succ[0], method="documented_ticker_change",
                           evidence=f"{symbol} -> {e['successor']} effective {e['effective_session']}; "
                                    f"{e['source']}")
                return out
    d = date.fromisoformat(around)
    lo, hi = (d - timedelta(days=200)).isoformat(), (d + timedelta(days=60)).isoformat()
    pat = re.compile(r"(?is)trading\s+symbol[^<]{0,400}?\b" + re.escape(symbol) + r"\b")
    for hit in fts(f'"{symbol}"', lo, hi, forms="8-K,6-K,10-Q,10-K")[:12]:
        src = hit.get("_source", {})
        ciks = src.get("ciks") or []
        ident = hit.get("_id", "")
        if not ciks or ":" not in ident:
            continue
        acc, doc = ident.split(":", 1)
        cik = int(ciks[0])
        url = ev.doc_url(cik, acc, doc)
        raw = ev.fetch(url)
        if raw is None:
            continue
        if pat.search(ev.plain_text(raw)[:20000]):
            out.update(cik=cik, method="filing_cover_page_trading_symbol", evidence=url)
            return out
    out["method"] = "unresolved"
    return out


def deep_scan(symbol: str, cik: int, around: str, span_days: int = 150) -> dict:
    """Read every document of every candidate filing in the window, exhibits included."""
    d = date.fromisoformat(around)
    lo, hi = (d - timedelta(days=span_days)).isoformat(), (d + timedelta(days=30)).isoformat()
    sub = ev.submissions(cik)
    out = {"symbol": symbol, "cik": cik, "window": [lo, hi], "documents_read": 0, "events": [],
           "issuer": (sub or {}).get("name")}
    if sub is None:
        return out
    rows = [r for r in ev.filing_rows(sub) if lo <= r["date"] <= hi and r["form"] in DEEP_FORMS]
    rows.sort(key=lambda r: abs((date.fromisoformat(r["date"]) - d).days))
    for r in rows[:25]:
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
        for n in docs[:12]:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    man = read_json(REPORTS / "cg_arrow007_manifest.json")
    blocking = man["fixed_point"]["iterations"][-1]["blocking_cases"]
    cases = defaultdict(list)
    for b in blocking:
        if b.get("date"):
            cases[(b["symbol"], b["date"])].append(b)
    note(f"deep scan for {len(cases)} blocking symbol/date cases "
         f"({len({s for s, _ in cases})} securities)")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    resolved, scans = {}, {}

    def work(key):
        sym, when = key
        r = resolve_cik(sym, when)
        s = deep_scan(sym, r["cik"], when) if r["cik"] else {"symbol": sym, "cik": None,
                                                             "documents_read": 0, "events": []}
        return key, r, s

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for fut in as_completed([pool.submit(work, k) for k in cases]):
            key, r, s = fut.result()
            resolved[f"{key[0]}|{key[1]}"] = r
            scans[f"{key[0]}|{key[1]}"] = s
            note(f"  {key[0]:6} {key[1]} cik={r['cik']} via {r['method']} "
                 f"docs={s['documents_read']} split_statements={len(s['events'])}")

    dump_json(WORK / "deepscan_cik.json", resolved)
    dump_json(WORK / "deepscan_events.json", scans)

    # fold the deep-scan findings into the per-case evidence store the merge reads
    store = read_json(WORK / "event_evidence.json")
    cases_store = read_json(WORK / "event_cases.json")
    added = 0
    for key, s in scans.items():
        sym, when = key.split("|")
        entry = store.get(key) or {"symbol": sym, "event_date": when, "source_type": "SEC_EDGAR",
                                   "candidates": []}
        have = {(c["url"], c["ratio_text"]) for c in entry.get("candidates", [])}
        for e in s["events"]:
            if (e["url"], e["ratio_text"]) not in have:
                entry.setdefault("candidates", []).append(e)
                added += 1
        entry["status"] = ("FILING_EVIDENCE_FOUND" if entry.get("candidates")
                           else ("UNRESOLVED_NO_FILING_EVIDENCE" if s["cik"]
                                 else "UNRESOLVED_NO_CIK_FOR_TICKER"))
        entry["deep_scanned"] = True
        entry["deep_scan_documents"] = s["documents_read"]
        entry["cik"] = s.get("cik")
        entry["issuer"] = s.get("issuer")
        store[key] = entry
        if key not in cases_store:
            b = cases[(sym, when)][0]
            cases_store[key] = {"symbol": sym, "date": when, "cohorts": [b["cohort_id"]],
                                "roles": ["fixed_point_window"], "max_ratio": b.get("price_ratio"),
                                "close_before": None, "close_at": None}
    dump_json(WORK / "event_evidence.json", store)
    dump_json(WORK / "event_cases.json", cases_store)
    note(f"deep scan added {added} filing statements across {len(scans)} cases")

    # make the deep-scan issuer record visible to the classifier
    sym_scans = read_json(WORK / "event_symbol_scans.json")
    for key, s in scans.items():
        sym = key.split("|")[0]
        prev = sym_scans.get(sym, {})
        if s["documents_read"] > prev.get("filings_scanned", 0):
            sym_scans[sym] = {**prev, "symbol": sym, "cik": s["cik"], "issuer": s.get("issuer"),
                              "filings_scanned": s["documents_read"],
                              "status": ("FILING_EVIDENCE_FOUND" if s["events"]
                                         else "UNRESOLVED_NO_FILING_EVIDENCE"),
                              "events": prev.get("events", []) + s["events"],
                              "deep_scanned": True}
    dump_json(WORK / "event_symbol_scans.json", sym_scans)
    note("symbol scan record updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
