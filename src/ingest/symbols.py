from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ingest.paths import ETP_TICKERS

# Primary-listed common: 1–5 letters, optional single-letter share class (BRK.B).
# Drops preferreds (.PR), warrants (.WS/.WT/.W), units (.U/.UN), rights (.RT),
# when-issued (/WI, .WI), leading-dot junk, and NASDAQ 5th-letter U/W/R/V.
_COMMON = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")
_NASDAQ_FIFTH = set("UWRV")  # unit, warrant, right, when-issued


@lru_cache(maxsize=1)
def load_etp_tickers(path: Path | None = None) -> frozenset[str]:
    src = path or ETP_TICKERS
    out: set[str] = set()
    if not src.exists():
        return frozenset()
    for line in src.read_text(encoding="utf-8").splitlines():
        text = line.strip().upper()
        if not text or text.startswith("#"):
            continue
        out.add(text)
    return frozenset(out)


def is_etp_ticker(symbol: str) -> bool:
    return symbol.strip().upper() in load_etp_tickers()


def is_common_stock_ticker(symbol: str) -> bool:
    if not symbol:
        return False
    text = symbol.strip().upper()
    if "/" in text:
        return False
    if any(token in text for token in (".PR", ".WS", ".WT", ".UN", ".RT", ".WI")):
        return False
    if re.search(r"\.[UW]$", text):
        return False
    if len(text) == 5 and "." not in text and text[-1] in _NASDAQ_FIFTH:
        return False
    return bool(_COMMON.match(text))


def type_col_name(columns: list[str]) -> str | None:
    lowered = {c.lower(): c for c in columns}
    for key in (
        "security_type",
        "securitytype",
        "listing_type",
        "instrument_type",
        "type",
        "name",
        "security_name",
        "issue_type",
    ):
        if key in lowered:
            return lowered[key]
    return None


def keep_by_theta_type(value: str) -> bool | None:
    """True keep, False drop, None unknown."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    drop = (
        "ETF",
        "ETN",
        "ETV",
        "ETMF",
        "UNIT",
        "WARRANT",
        "PREFERRED",
        "RIGHT",
        "WHEN-ISSUED",
        "WHEN ISSUED",
        "WHENISSUED",
    )
    if any(tok in text for tok in drop):
        return False
    keep = ("COMMON", "CS", "EQUITY", "STOCK")
    if any(tok in text for tok in keep):
        return True
    return None


def filter_common(symbols: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in symbols:
        sym = str(raw).strip().upper()
        if sym in seen:
            continue
        if is_common_stock_ticker(sym):
            seen.add(sym)
            out.append(sym)
    return out


def filter_candidates(
    symbols: list[str],
    *,
    types: list[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    """raw → regex → type/ETP drop. Returns (candidates, funnel counts)."""
    raw_n = len(symbols)
    type_map: dict[str, str] = {}
    if types is not None:
        for raw, typ in zip(symbols, types, strict=False):
            type_map[str(raw).strip().upper()] = str(typ)
    regex_kept = filter_common(symbols)
    etp = load_etp_tickers()
    dropped_type = 0
    dropped_etp = 0
    out: list[str] = []
    for sym in regex_kept:
        if type_map:
            decision = keep_by_theta_type(type_map.get(sym, ""))
            if decision is False:
                dropped_type += 1
                continue
            if decision is True:
                out.append(sym)
                continue
        if sym in etp:
            dropped_etp += 1
            continue
        out.append(sym)
    funnel = {
        "raw": raw_n,
        "regex_kept": len(regex_kept),
        "type_dropped": dropped_type,
        "etp_dropped": dropped_etp,
        "candidates": len(out),
    }
    return out, funnel
