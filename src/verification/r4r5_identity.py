"""Point-in-time ticker to issuer resolution, and corporate actions for issuers the ticker file lost.

This closes the second of Arrow 013's two declared blockers. `r4r5_events.ticker_cik` reads SEC's
`company_tickers.json`, which is a snapshot of who holds a ticker *now*. A microcap that was
delisted, renamed or reverse-split out of existence during the corridor is simply absent from it,
so the census could not reach the very issuers whose actions matter most — the ones whose ranking
windows contain a level change the strategy read as a 300% gain.

EDGAR full-text search answers the question the ticker file cannot: which filer was filing under
this ticker at this date. A hit carries both the CIK and the filer's display name, and the display
name contains the ticker in parentheses exactly when the ticker is that filer's own registered
symbol. That is the discriminator — it separates `Femto Technologies Inc. (FMTO)` from the
thousands of documents that merely contain the letters ACON.

The resolution is point-in-time because the search is restricted to filings inside the corridor,
so a ticker later reassigned to a different issuer cannot resolve to the later one.

Nothing here computes a ranking, a selection or a return.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as _dt
import json
import re
import time
from urllib.parse import quote

from verification import r4r5_events as ev

FTS = ("https://efts.sec.gov/LATEST/search-index?q=%22{q}%22"
       "&dateRange=custom&startdt={lo}&enddt={hi}{forms}")
# A ticker that is also an ordinary word or a common firm name returns a wall of unrelated
# documents, and the filer we want can sit past the first page. Narrowing to the forms an issuer
# uses to report its own affairs removes almost all of that noise, so the search is retried that
# way before a security is called unresolvable.
FORM_FILTERS = ("", "&forms=8-K%2C6-K", "&forms=10-K%2C20-F%2CS-1%2C424B3", "&forms=25%2C25-NSE")
# Forms that carry a consolidation, split, delisting or transfer statement. Foreign private
# issuers report on 6-K rather than 8-K, and microcap consolidations are very often announced
# only in an exhibit, so the exhibit list is read as well as the primary document.
ACTION_FORMS = ("8-K", "8-K/A", "6-K", "6-K/A", "8-K12B", "25", "25-NSE",
                "S-1", "S-1/A", "424B3", "424B4", "424B5", "10-K", "20-F", "DEF 14A", "PRE 14A")


def _display_ticker(name: str) -> set:
    return set(re.findall(r"\(([A-Z][A-Z0-9.\-]{0,6})\)", name or ""))


def resolve(ticker: str, lo: str, hi: str, *, limit: int = 100) -> dict:
    """Which filer was filing under this ticker inside the window, from EDGAR full-text search.

    A hit counts only when the ticker appears as the filer's own registered symbol in its display
    name. Without that test, a common word like ACON returns thousands of unrelated documents.
    """
    out = {"symbol": ticker, "window": [lo, hi], "method": "SEC_EDGAR_FULL_TEXT_SEARCH",
           "candidates": [], "cik": None, "issuer": None, "queries": [],
           "status": "IDENTITY_UNRESOLVED"}
    by_cik: dict = {}
    searched = 0
    for forms in FORM_FILTERS:
        raw = ev.fetch(FTS.format(q=quote(ticker), lo=lo, hi=hi, forms=forms))
        out["queries"].append(forms or "all forms")
        if raw is None:
            continue
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        hits = (doc.get("hits") or {}).get("hits") or []
        searched += len(hits)
        for h in hits[:limit]:
            s = h.get("_source") or {}
            names = s.get("display_names") or []
            ciks = s.get("ciks") or []
            for name, cik in zip(names, ciks):
                if ticker.upper() not in _display_ticker(name):
                    continue
                rec = by_cik.setdefault(int(cik), {"cik": int(cik), "issuer": name, "filings": 0,
                                                   "first_seen": s.get("file_date"),
                                                   "last_seen": s.get("file_date"),
                                                   "forms": set()})
                rec["filings"] += 1
                rec["forms"].add((s.get("root_forms") or [s.get("file_type")])[0])
                d = s.get("file_date")
                if d:
                    rec["first_seen"] = min(rec["first_seen"] or d, d)
                    rec["last_seen"] = max(rec["last_seen"] or d, d)
        if by_cik:
            break
    out["hits_searched"] = searched
    cands = sorted(by_cik.values(), key=lambda r: -r["filings"])
    for c in cands:
        c["forms"] = sorted(x for x in c["forms"] if x)
    out["candidates"] = cands
    if cands:
        out["cik"] = cands[0]["cik"]
        out["issuer"] = cands[0]["issuer"]
        out["status"] = ("IDENTITY_RESOLVED_SINGLE_FILER" if len(cands) == 1
                         else "IDENTITY_RESOLVED_MULTIPLE_FILERS")
        out["evidence"] = (f"EDGAR full-text search over {lo}..{hi} returned "
                           f"{cands[0]['filings']} filings whose filer display name carries the "
                           f"ticker ({ticker}) as its own registered symbol")
    return out


def _near(filing_date: str, anchors: tuple, days: int) -> bool:
    """Is this filing close enough in time to a discontinuity to be about it?"""
    if not anchors:
        return True
    try:
        f = _dt.date.fromisoformat(filing_date)
    except ValueError:
        return False
    return any(abs((f - a).days) <= days for a in anchors)


def actions_for_cik(cik: int, symbol: str, lo: str, hi: str, *, max_docs: int = 12,
                    anchors: tuple = (), window_days: int = 45) -> dict:
    """The filer's split and consolidation statements around the dates in question.

    `r4r5_events.scan_symbol` reads only a filing's primary document. A microcap consolidation is
    usually announced in an attached press release, so the primary document says nothing and the
    ratio sits in EX-99.1. This reads the filing index and follows the exhibits too.

    `anchors` are the sessions on which the tape actually changed level. Reading every filing an
    issuer made across eighteen months costs hundreds of requests per security and answers a
    question nobody asked; a consolidation is announced within weeks of taking effect, so the
    search is confined to that neighbourhood. With no anchors the whole window is read.
    """
    out = {"symbol": symbol, "cik": cik, "events": [], "filings_scanned": 0,
           "anchors": [a.isoformat() for a in anchors], "window_days": window_days,
           "status": "UNRESOLVED_NO_FILING_EVIDENCE"}
    sub = ev.submissions(cik)
    if sub is None:
        out["status"] = "UNRESOLVED_SUBMISSIONS_UNAVAILABLE"
        return out
    out["issuer"] = sub.get("name")
    rows = [r for r in ev.filing_rows(sub)
            if lo <= r["date"] <= hi and r["form"] in ACTION_FORMS
            and _near(r["date"], anchors, window_days)]
    # the forms that actually carry a consolidation statement are read first
    rows.sort(key=lambda r: (r["form"] not in ("8-K", "6-K", "8-K/A", "6-K/A"), r["date"]))
    out["filings_in_neighbourhood"] = len(rows)
    for r in rows[:max_docs]:
        for url in _documents(cik, r):
            raw = ev.fetch(url)
            if raw is None or len(raw) > ev.MAX_DOC_BYTES:
                continue
            out["filings_scanned"] += 1
            for e in ev.extract_events(ev.plain_text(raw)):
                for a, b, span in e["ratios"]:
                    fac = ev.classify_factor(e["phrase"], a, b)
                    if fac is None:
                        continue
                    out["events"].append({
                        "filing_date": r["date"], "form": r["form"], "items": r.get("items"),
                        "url": url, "phrase": e["phrase"], "ratio_text": span,
                        "price_factor": fac[0], "event_type": fac[1],
                        "dates_in_window": e["dates_in_window"], "snippet": e["snippet"]})
    if out["events"]:
        out["status"] = "FILING_EVIDENCE_FOUND"
    return out


def _documents(cik: int, row: dict) -> list:
    """The filing's primary document and its readable exhibits, in that order."""
    urls = []
    if row.get("doc") and not row["doc"].endswith(".xml"):
        urls.append(ev.doc_url(cik, row["accession"], row["doc"]))
    acc = row["accession"].replace("-", "")
    idx = ev.fetch(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/index.json")
    if idx is None:
        return urls
    try:
        items = json.loads(idx).get("directory", {}).get("item", [])
    except ValueError:
        return urls
    for it in items:
        name = it.get("name") or ""
        if not name.lower().endswith((".htm", ".html", ".txt")):
            continue
        # exhibits carry the announcement; the primary document is already queued above
        if re.match(r"(?i).*ex-?\d", name) or "ex99" in name.lower():
            u = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
            if u not in urls:
                urls.append(u)
    return urls[:3]


def investigate(symbols: list[str], lo: str, hi: str, workers: int = 8,
                progress_every: int = 20, anchors: dict | None = None) -> dict:
    """Resolve identity then gather actions, for securities the ticker file cannot reach."""
    anchors = anchors or {}

    def one(sym: str) -> dict:
        ident = resolve(sym, lo, hi)
        if ident["cik"] is None:
            return {"identity": ident, "actions": {"symbol": sym, "events": [],
                                                   "status": "UNRESOLVED_NO_IDENTITY"}}
        return {"identity": ident,
                "actions": actions_for_cik(ident["cik"], sym, lo, hi,
                                           anchors=tuple(anchors.get(sym, ())))}

    results, t0 = {}, time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(one, s): s for s in sorted(set(symbols))}
        for n, f in enumerate(as_completed(futs), 1):
            sym = futs[f]
            try:
                results[sym] = f.result()
            except Exception as exc:  # noqa: BLE001
                results[sym] = {"identity": {"symbol": sym, "status": "INVESTIGATION_ERROR",
                                             "error": str(exc)[:200], "cik": None},
                                "actions": {"symbol": sym, "events": [],
                                            "status": "INVESTIGATION_ERROR"}}
            if n % progress_every == 0 or n == len(futs):
                el = time.monotonic() - t0
                print(f"{ev.stamp()} identity {n}/{len(futs)} {el:.0f}s "
                      f"ETA~{el / n * (len(futs) - n):.0f}s", flush=True)
    return results
