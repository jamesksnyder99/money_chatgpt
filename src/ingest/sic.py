"""Arrow 63 — official SEC EDGAR SIC map into data/meta/. Ingest only."""

from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import polars as pl

from ingest.paths import (
    BARS_DIR,
    FULL_BARS,
    FULL_ELIGIBILITY,
    META_DIR,
    REPORTS,
    SECTOR_SIC,
    SECTOR_SIC_CACHE,
    SECTOR_SIC_CSV,
    SECTOR_SIC_META,
    VIRGIN_BARS,
    VIRGIN_ELIGIBILITY,
    ensure_meta_dirs,
)
from ingest.progress import Progress

ET = ZoneInfo("America/New_York")
SCORES_ENGINES = False
USER_AGENT = "ProjectMoney research jks.michigan@gmail.com"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
TICKERS_FALLBACK = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_TMPL = "https://data.sec.gov/submissions/CIK{cik10}.json"
SLEEP_S = 0.2
TIMEOUT_S = 60.0


def request_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "identity",
    }


def pad_cik(cik) -> str | None:
    if cik is None or cik == "":
        return None
    digits = "".join(ch for ch in str(cik).strip() if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def pad_sic4(sic) -> str | None:
    if sic is None or sic == "":
        return None
    digits = "".join(ch for ch in str(sic).strip() if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(4)


def sic2_of(sic4) -> str | None:
    """First two digits of zero-padded sic4."""
    padded = pad_sic4(sic4)
    if padded is None:
        return None
    return padded[:2]


def arrow63_output_roots() -> list:
    return [META_DIR, SECTOR_SIC, SECTOR_SIC_CSV, SECTOR_SIC_CACHE, SECTOR_SIC_META]


def symbols_on_disk() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for path in (VIRGIN_ELIGIBILITY, FULL_ELIGIBILITY):
        if not path.exists():
            continue
        df = pl.read_parquet(path, columns=["symbol"])
        for s in df["symbol"].to_list():
            t = str(s).upper().strip()
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    out.sort()
    return out


def lookup_cik(symbol: str, mapping: dict[str, str]) -> str | None:
    s = symbol.upper().strip()
    for cand in (s, s.replace(".", "-"), s.replace("-", "."), s.replace("/", "-")):
        got = mapping.get(cand)
        if got:
            return got
    return None


def parse_company_tickers(payload) -> dict[str, str]:
    out: dict[str, str] = {}
    if isinstance(payload, dict) and "fields" in payload and "data" in payload:
        fields = [str(x).lower() for x in payload["fields"]]
        ti = fields.index("ticker")
        ci = fields.index("cik")
        for row in payload["data"]:
            t = str(row[ti]).upper().strip()
            c = pad_cik(row[ci])
            if t and c:
                out[t] = c
        return out
    rows = payload.values() if isinstance(payload, dict) else payload
    for entry in rows:
        if not isinstance(entry, dict):
            continue
        t = str(entry.get("ticker") or "").upper().strip()
        c = pad_cik(entry.get("cik_str") if entry.get("cik_str") is not None else entry.get("cik"))
        if t and c:
            out[t] = c
    return out


def _http_json(url: str, retries: int = 6) -> tuple[dict | list | None, int | None, str]:
    """Return (payload, http_status, error). 404 is (None, 404, '')."""
    delay = 1.0
    last_err = ""
    last_status = None
    headers = request_headers()
    for _ in range(max(1, retries)):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                status = int(getattr(resp, "status", 200) or 200)
                raw = resp.read()
                if status == 200:
                    return json.loads(raw.decode("utf-8")), 200, ""
                last_status = status
                last_err = f"http {status}"
        except urllib.error.HTTPError as exc:
            last_status = int(exc.code)
            last_err = f"http {exc.code}"
            if exc.code == 404:
                return None, 404, ""
            if exc.code in (429, 503):
                time.sleep(delay)
                delay = min(delay * 2.0, 60.0)
                continue
            return None, last_status, last_err
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            time.sleep(delay)
            delay = min(delay * 2.0, 60.0)
            continue
        time.sleep(delay)
        delay = min(delay * 2.0, 60.0)
    return None, last_status, last_err


def fetch_ticker_map() -> dict[str, str]:
    payload, status, err = _http_json(TICKERS_URL)
    if payload is None:
        print(f"company_tickers.json failed status={status} err={err}; trying fallback", flush=True)
        time.sleep(SLEEP_S)
        payload, status, err = _http_json(TICKERS_FALLBACK)
    if payload is None:
        raise RuntimeError(f"SEC ticker map failed status={status} err={err}")
    mapping = parse_company_tickers(payload)
    if not mapping:
        raise RuntimeError("SEC ticker map parsed empty")
    return mapping


def load_cache() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not SECTOR_SIC_CACHE.exists():
        return out
    with SECTOR_SIC_CACHE.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            cik = pad_cik(rec.get("cik"))
            if cik:
                out[cik] = rec
    return out


def append_cache(rec: dict) -> None:
    ensure_meta_dirs()
    with SECTOR_SIC_CACHE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=True) + "\n")
        fh.flush()


def load_asof() -> date:
    if SECTOR_SIC_META.exists():
        rec = json.loads(SECTOR_SIC_META.read_text(encoding="utf-8"))
        raw = rec.get("asof")
        if raw:
            return date.fromisoformat(str(raw)[:10])
    return datetime.now(timezone.utc).date()


def save_asof(asof: date) -> None:
    ensure_meta_dirs()
    SECTOR_SIC_META.write_text(
        json.dumps(
            {
                "asof": asof.isoformat(),
                "source": "sec.gov / data.sec.gov",
                "user_agent": USER_AGENT,
                "wrapper": "none",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def fetch_sic_for_cik(cik10: str) -> dict:
    url = SUBMISSIONS_TMPL.format(cik10=cik10)
    payload, status, err = _http_json(url)
    sic4 = pad_sic4((payload or {}).get("sic")) if isinstance(payload, dict) else None
    name = None
    if isinstance(payload, dict):
        raw_name = payload.get("sicDescription")
        name = str(raw_name).strip() if raw_name else None
        if name == "":
            name = None
    return {
        "cik": cik10,
        "sic": sic4,
        "sic_name": name,
        "http": status,
        "error": err,
    }


def _median_per_sic2(mapped: list[dict]) -> float | None:
    counts: dict[str, int] = {}
    for rec in mapped:
        s2 = rec.get("sic2")
        if not s2:
            continue
        counts[s2] = counts.get(s2, 0) + 1
    if not counts:
        return None
    return float(statistics.median(counts.values()))


def run_arrow63(*, workers: int | None = None) -> int:
    del workers  # serial: SEC fair-access. Do not parallel-hammer EDGAR.
    if META_DIR.resolve() in (BARS_DIR.resolve(), FULL_BARS.resolve(), VIRGIN_BARS.resolve()):
        raise RuntimeError("Arrow 63 must not write Lab A data/bars or tape bars")
    ensure_meta_dirs()
    t0 = time.monotonic()
    asof = load_asof()
    save_asof(asof)
    print(
        f"ingest start mode=arrow63 source=official SEC EDGAR "
        f"user_agent_set=yes sleep={SLEEP_S}s serial=1 "
        f"asof={asof.isoformat()} output={SECTOR_SIC} "
        f"do_not_touch=data/full,data/virgin/bars,data/bars "
        f"do_not_score=yes no_arrow_64 no_paid_edgar_wrapper",
        flush=True,
    )
    symbols = symbols_on_disk()
    print(f"symbols_on_disk={len(symbols)} (unique eligibility tickers)", flush=True)
    ticker_map = fetch_ticker_map()
    print(f"sec ticker map n={len(ticker_map)} from {TICKERS_URL} (fallback if needed)", flush=True)
    time.sleep(SLEEP_S)

    cik_by_sym: dict[str, str | None] = {}
    need_ciks: list[str] = []
    seen_cik: set[str] = set()
    no_cik = 0
    for sym in symbols:
        cik = lookup_cik(sym, ticker_map)
        cik_by_sym[sym] = cik
        if cik is None:
            no_cik += 1
            continue
        if cik not in seen_cik:
            seen_cik.add(cik)
            need_ciks.append(cik)
    print(
        f"unique CIKs={len(need_ciks)} symbols_no_cik={no_cik} "
        f"(ticker aliases: . <-> -)",
        flush=True,
    )

    cache = load_cache()
    todo = [c for c in need_ciks if c not in cache]
    print(f"submissions cached={len(cache)} to_fetch={len(todo)} resume-safe", flush=True)
    if todo[:5]:
        print(f"pilot first 5 CIKs: {todo[:5]}", flush=True)
    prog = Progress(len(todo), "arrow63")
    prog.start_heartbeat()
    http_fail = 0
    for i, cik in enumerate(todo, 1):
        rec = fetch_sic_for_cik(cik)
        append_cache(rec)
        cache[cik] = rec
        ok = rec.get("http") == 200
        if not ok:
            http_fail += 1
        prog.mark(cik, rows=1, elapsed_s=SLEEP_S, ok=ok)
        if i == 5:
            print("pilot 5 CIKs done; continuing full unique-CIK pull", flush=True)
            prog.heartbeat()
        if i % 100 == 0:
            prog.heartbeat()
        time.sleep(SLEEP_S)
    prog.stop_heartbeat()
    prog.heartbeat()

    rows = []
    mapped = []
    cik_no_sic = 0
    for sym in symbols:
        cik = cik_by_sym.get(sym)
        sic4 = None
        sic_name = None
        if cik and cik in cache:
            sic4 = pad_sic4(cache[cik].get("sic"))
            sic_name = cache[cik].get("sic_name")
            if not sic4:
                cik_no_sic += 1
        sic2 = sic2_of(sic4) if sic4 else None
        rec = {
            "symbol": sym,
            "cik": cik,
            "sic4": sic4,
            "sic2": sic2,
            "sic_name": sic_name,
            "asof": asof,
        }
        rows.append(rec)
        if sic4:
            mapped.append(rec)

    df = pl.DataFrame(rows)
    df.write_parquet(SECTOR_SIC)
    df.write_csv(SECTOR_SIC_CSV)

    sic2s = sorted({r["sic2"] for r in mapped if r.get("sic2")})
    med = _median_per_sic2(mapped)
    wall_min = (time.monotonic() - t0) / 60.0
    cached_http_fail = sum(1 for c in need_ciks if cache.get(c, {}).get("http") not in (200, None) and cache.get(c, {}).get("http") != 200)
    # count fetch failures across this run + cached non-200 that we did not retry
    fail_total = sum(1 for c in need_ciks if (cache.get(c) or {}).get("http") not in (200,))
    med_s = f"{med:.1f}" if med is not None else "n/a"
    lines = [
        "Arrow 63 — SEC SIC map into data/meta/ (ingest only)",
        "B pulled SEC directly (urllib to www.sec.gov / data.sec.gov) and did not use a paid EDGAR wrapper.",
        "Did not score engines. Did not touch data/full, data/virgin bars, or Lab A data/bars. No Arrow 64.",
        f"asof={asof.isoformat()} (UTC date of the pull; frozen).",
        f"user_agent={USER_AGENT}",
        f"symbols_on_disk={len(symbols)}",
        f"symbols_mapped={len(mapped)}",
        f"symbols_no_cik={no_cik}",
        f"symbols_cik_no_sic={cik_no_sic}",
        f"unique_ciks={len(need_ciks)}",
        f"unique_sic2_buckets={len(sic2s)}",
        f"median_names_per_sic2={med_s} (among mapped symbols)",
        f"http_failures={fail_total} (this_run_new_fails={http_fail} cached_non_200={cached_http_fail})",
        f"sleep_s={SLEEP_S} serial=1 retries_on=429,503",
        f"wrote={SECTOR_SIC} csv={SECTOR_SIC_CSV}",
        f"wall_min={wall_min:.1f}",
        "Acronyms: SIC = Standard Industrial Classification; CIK = Central Index Key; "
        "SEC = U.S. Securities and Exchange Commission; EDGAR = Electronic Data Gathering, "
        "Analysis, and Retrieval; IS = in-sample; OOS = out-of-sample.",
        "",
    ]
    text = "\n".join(lines)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "tape63_sic.txt").write_text(text, encoding="utf-8")
    print(text, flush=True)
    print(f"wrote {REPORTS / 'tape63_sic.txt'}", flush=True)

    log_path = REPORTS / "RESEARCH_LOG.md"
    stamp = datetime.now(timezone.utc).astimezone(ET).isoformat(timespec="seconds")
    bits = [
        f"## {stamp} — Arrow 63",
        "",
        "Ingest only. Official SEC EDGAR SIC map into data/meta/. Did not use a paid EDGAR wrapper.",
        f"symbols_on_disk={len(symbols)} mapped={len(mapped)} no_cik={no_cik} cik_no_sic={cik_no_sic} "
        f"sic2_buckets={len(sic2s)} median_per_sic2={med_s} http_failures={fail_total} wall_min={wall_min:.1f}.",
        "Did not score engines. Did not touch data/full, data/virgin bars, or Lab A data/bars. No Arrow 64.",
        "",
    ]
    prev = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(prev.rstrip() + "\n\n" + "\n".join(bits), encoding="utf-8")
    return 0
