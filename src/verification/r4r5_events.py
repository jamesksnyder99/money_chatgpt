"""Arrow 007 corporate-action / security-identity evidence layer.

Primary evidence comes from SEC EDGAR: the issuer's own filings, fetched from
`data.sec.gov` and `www.sec.gov/Archives`, which is free public primary source material.
Every HTTP response is cached under the ignored verification tree so the evidence is
preserved and reruns are deterministic.

A factor is only ever taken from a filing. The observed price discontinuity is used to
corroborate a documented factor, never to infer one. When no filing evidence is found the
case stays UNRESOLVED rather than being assumed away in either direction.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import gzip
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request

from verification.r4r5_data import VERIFY_ROOT, dump_json, read_json, stamp

EVENTS_ROOT = VERIFY_ROOT / "events"
HTTP_CACHE = EVENTS_ROOT / "http_cache"
USER_AGENT = "money_chatgpt research (jks.michigan@gmail.com)"
SEC_RATE_PER_SEC = 8.0          # SEC asks for no more than 10/s; stay under it
FORMS = ("8-K", "8-K/A", "6-K", "6-K/A", "425", "8-K12B", "10-K", "20-F", "S-1", "S-1/A",
         "DEF 14A", "DEFA14A", "PRE 14A", "424B3", "424B4", "25-NSE", "15-12B")
SPLIT_FORMS = ("8-K", "8-K/A", "6-K", "6-K/A", "8-K12B")
SPLIT_ITEMS = ("3.03", "5.03", "8.01", "1.01")   # articles amendment / other events
MAX_DOC_BYTES = 3_000_000

_lock = threading.Lock()
_next_slot = [0.0]

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
         "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
         "twenty-five": 25, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
         "eighty": 80, "ninety": 90, "one hundred": 100, "hundred": 100, "one hundred fifty": 150,
         "two hundred": 200, "two hundred twenty": 220, "two hundred fifty": 250, "five hundred": 500,
         "one thousand": 1000, "thousand": 1000}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}


# ------------------------------------------------------------------ transport
def _throttle() -> None:
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot[0])
        _next_slot[0] = slot + 1.0 / SEC_RATE_PER_SEC
    delay = slot - time.monotonic()
    if delay > 0:
        time.sleep(delay)


def fetch(url: str, *, retries: int = 3) -> bytes | None:
    """Cached, rate-limited GET. Returns None when the resource is unavailable."""
    key = hashlib.sha256(url.encode()).hexdigest()[:40]
    path = HTTP_CACHE / key[:2] / (key + ".bin")
    if path.is_file():
        return path.read_bytes()
    last = None
    for attempt in range(retries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       "Accept-Encoding": "gzip, deflate"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(raw)
            tmp.replace(path)
            return raw
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (403, 429, 500, 502, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0 * (attempt + 1))
    return None


# ------------------------------------------------------------------ EDGAR indexes
def ticker_cik() -> dict:
    p = EVENTS_ROOT / "ticker_cik.json"
    if p.is_file():
        return read_json(p)
    raw = fetch("https://www.sec.gov/files/company_tickers.json")
    if raw is None:
        return {}
    data = json.loads(raw)
    out = {}
    for v in data.values():
        out.setdefault(v["ticker"].upper(), []).append(int(v["cik_str"]))
    dump_json(p, out)
    return out


def submissions(cik: int) -> dict | None:
    raw = fetch(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def filing_rows(sub: dict) -> list[dict]:
    out = []
    blocks = [sub["filings"]["recent"]]
    for extra in sub["filings"].get("files", [])[:3]:
        raw = fetch("https://data.sec.gov/submissions/" + extra["name"])
        if raw:
            try:
                blocks.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    for b in blocks:
        n = len(b.get("filingDate", []))
        for i in range(n):
            out.append({"date": b["filingDate"][i], "form": b["form"][i],
                        "accession": b["accessionNumber"][i], "doc": b["primaryDocument"][i],
                        "items": b.get("items", [""] * n)[i]})
    return out


def doc_url(cik: int, accession: str, doc: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{doc}"


def plain_text(raw: bytes) -> str:
    txt = raw.decode("utf-8", "ignore")
    txt = re.sub(r"(?is)<(script|style).*?</\1>", " ", txt)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = txt.replace("&#160;", " ").replace("&nbsp;", " ").replace("&#8217;", "'")
    txt = txt.replace("&#8220;", '"').replace("&#8221;", '"').replace("&amp;", "&")
    return re.sub(r"\s+", " ", txt)


# ------------------------------------------------------------------ extraction
def _num(token: str) -> int | None:
    token = token.strip().lower().replace(",", "")
    if token.isdigit():
        return int(token)
    return WORDS.get(token)


RATIO_PATTERNS = (
    re.compile(r"(?i)\b(?:ratio of\s+)?(\d{1,4}|[a-z\- ]{3,22})[\s-]*(?:for|to|:)[\s-]*(\d{1,4}|[a-z\- ]{3,22})\b"
               r"(?=[^.]{0,120}?(?:reverse|forward)?[^.]{0,40}?(?:stock split|share split|split|consolidation))"),
    re.compile(r"(?i)(?:reverse|forward)?\s*(?:stock|share)?\s*split[^.]{0,80}?\bratio of\s+"
               r"(\d{1,4}|[a-z\- ]{3,22})[\s-]*(?:for|to|:)[\s-]*(\d{1,4}|[a-z\- ]{3,22})\b"),
)
DATE_PATTERNS = (
    re.compile(r"(?i)\b(january|february|march|april|may|june|july|august|september|october|"
               r"november|december)\s+(\d{1,2}),?\s+(20\d{2})\b"),
)


def extract_events(text: str) -> list[dict]:
    """Find split/consolidation statements with a ratio, plus nearby candidate dates."""
    out = []
    for m in re.finditer(r"(?i)(reverse stock split|reverse share split|reverse split|"
                         r"share consolidation|forward stock split|forward split|stock split|"
                         r"stock dividend|share subdivision)", text):
        lo, hi = max(0, m.start() - 700), min(len(text), m.end() + 900)
        window = text[lo:hi]
        kind = m.group(1).lower()
        ratios = []
        for pat in RATIO_PATTERNS:
            for rm in pat.finditer(window):
                a, b = _num(rm.group(1)), _num(rm.group(2))
                if a and b and (a == 1 or b == 1) and max(a, b) > 1 and max(a, b) <= 2000:
                    ratios.append((a, b, rm.group(0).strip()[:70]))
        dates = []
        for dm in DATE_PATTERNS[0].finditer(window):
            try:
                dates.append(date(int(dm.group(3)), MONTHS[dm.group(1).lower()], int(dm.group(2))).isoformat())
            except ValueError:
                pass
        if ratios:
            out.append({"phrase": kind, "ratios": ratios[:4], "dates_in_window": sorted(set(dates))[:8],
                        "snippet": window[max(0, 700 - 220): 700 + 320].strip()[:520]})
    return out


def classify_factor(kind: str, a: int, b: int) -> tuple[float, str] | None:
    """price_factor = old shares per new share. 1-for-50 reverse -> 50. 5-for-1 forward -> 0.2."""
    reverse = "reverse" in kind or "consolidation" in kind
    forward = "forward" in kind or "subdivision" in kind or kind == "stock split"
    big, small = (max(a, b), min(a, b))
    if small != 1:
        return None
    if reverse:
        return float(big), "reverse_split"
    if forward:
        return 1.0 / float(big), "forward_split"
    return None


# ------------------------------------------------------------------ investigation
def scan_symbol(symbol: str, lo: str, hi: str, *, max_docs: int = 40) -> dict:
    """Every split/consolidation statement an issuer filed across the whole window.

    One pass per security. Filings are ordered so that the forms that actually carry a
    split announcement, and the items that signal one, are read first.
    """
    out = {"symbol": symbol, "window": [lo, hi], "source_type": "SEC_EDGAR",
           "status": "UNRESOLVED_NO_FILING_EVIDENCE", "events": [], "cik": None,
           "issuer": None, "former_names": [], "filings_scanned": 0}
    ciks = ticker_cik().get(symbol.upper()) or []
    if not ciks:
        out["status"] = "UNRESOLVED_NO_CIK_FOR_TICKER"
        return out
    for cik in ciks[:2]:
        sub = submissions(cik)
        if sub is None:
            continue
        out["cik"] = cik
        out["issuer"] = sub.get("name")
        out["former_names"] = [f["name"] for f in sub.get("formerNames", [])][:4]
        rows = [r for r in filing_rows(sub) if lo <= r["date"] <= hi and r["form"] in SPLIT_FORMS]
        rows.sort(key=lambda r: (not any(i in (r.get("items") or "") for i in SPLIT_ITEMS), r["date"]))
        for r in rows[:max_docs]:
            if not r["doc"] or r["doc"].endswith(".xml"):
                continue
            url = doc_url(cik, r["accession"], r["doc"])
            raw = fetch(url)
            if raw is None or len(raw) > MAX_DOC_BYTES:
                continue
            out["filings_scanned"] += 1
            for e in extract_events(plain_text(raw)):
                for a, b, span in e["ratios"]:
                    fac = classify_factor(e["phrase"], a, b)
                    if fac is None:
                        continue
                    out["events"].append({
                        "filing_date": r["date"], "form": r["form"], "items": r["items"],
                        "url": url, "phrase": e["phrase"], "ratio_text": span,
                        "price_factor": fac[0], "event_type": fac[1],
                        "dates_in_window": e["dates_in_window"], "snippet": e["snippet"]})
        if out["events"]:
            break
    if out["events"]:
        out["status"] = "FILING_EVIDENCE_FOUND"
    return out


def scan_symbols(symbols: list[str], lo: str, hi: str, workers: int = 8,
                 progress_every: int = 20) -> dict:
    """Independent per-security scans in parallel, merged deterministically by symbol."""
    results = {}
    t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(scan_symbol, s, lo, hi): s for s in sorted(set(symbols))}
        for n, f in enumerate(as_completed(futs), 1):
            sym = futs[f]
            try:
                results[sym] = f.result()
            except Exception as exc:  # noqa: BLE001
                results[sym] = {"symbol": sym, "status": "INVESTIGATION_ERROR",
                                "error": str(exc)[:200], "events": []}
            if n % progress_every == 0 or n == len(futs):
                el = time.monotonic() - t0
                print(f"{stamp()} symbols {n}/{len(futs)} {el:.0f}s "
                      f"ETA~{el / n * (len(futs) - n):.0f}s", flush=True)
    return results
