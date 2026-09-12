from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "data"
REPORTS = REPO_ROOT / "reports"
CALENDAR = DATA / "calendar" / "sessions.parquet"
ELIGIBILITY = DATA / "universe" / "eligibility.parquet"
SPLITS = DATA / "ref" / "splits.parquet"
SYMBOLS = DATA / "ref" / "symbols_common.parquet"
SYMBOLS_RAW = DATA / "ref" / "stock_list_symbols.parquet"
EOD_ROOT = DATA / "eod"
EOD_DIR = EOD_ROOT / "warmup"
BARS_DIR = DATA / "bars" / "ohlc_1m"
FULL_ROOT = DATA / "full"
FULL_BARS = FULL_ROOT / "bars"
FULL_ELIGIBILITY = FULL_ROOT / "eligibility.parquet"
FULL_MANIFEST = FULL_ROOT / "manifest.parquet"
FULL_BENCH = FULL_ROOT / "bench"
FULL_IWM = FULL_BENCH / "IWM"
VIRGIN_ROOT = DATA / "virgin"
VIRGIN_BARS = VIRGIN_ROOT / "bars"
VIRGIN_ELIGIBILITY = VIRGIN_ROOT / "eligibility.parquet"
VIRGIN_MANIFEST = VIRGIN_ROOT / "manifest.parquet"
VIRGIN_EOD = VIRGIN_ROOT / "eod"
VIRGIN_BENCH = VIRGIN_ROOT / "bench"
VIRGIN_IWM = VIRGIN_BENCH / "IWM"
META_DIR = DATA / "meta"
SECTOR_SIC = META_DIR / "sector_sic.parquet"
SECTOR_SIC_CSV = META_DIR / "sector_sic.csv"
SECTOR_SIC_CACHE = META_DIR / "submissions_cache.jsonl"
SECTOR_SIC_META = META_DIR / "pull_meta.json"
MANIFEST = DATA / "manifests" / "pulls.jsonl"
INGEST_REPORT = REPORTS / "ingest_latest.txt"
ARROW01_REPORT = REPORTS / "arrow01_timing.txt"
ARROW02_UNIVERSE = REPORTS / "arrow02_universe.txt"
ARROW02_REPORT = REPORTS / "arrow02_timing.txt"
ETP_TICKERS = Path(__file__).with_name("etp_tickers.txt")


def ensure_dirs() -> None:
    for path in (
        CALENDAR.parent,
        ELIGIBILITY.parent,
        SPLITS.parent,
        EOD_DIR,
        EOD_ROOT,
        BARS_DIR,
        FULL_BARS,
        FULL_ELIGIBILITY.parent,
        FULL_IWM,
        MANIFEST.parent,
        REPORTS,
        DATA / "tmp",
    ):
        path.mkdir(parents=True, exist_ok=True)


# Windows reserved device names (CON, PRN, AUX, ...) cannot be filenames.
_WIN_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_symbol_filename(symbol: str) -> str:
    stem = symbol.split(".")[0].upper()
    if stem in _WIN_RESERVED:
        return f"_{symbol}"
    return symbol


def bar_path(session_date, symbol: str) -> Path:
    return BARS_DIR / f"session_date={session_date.isoformat()}" / f"{safe_symbol_filename(symbol)}.parquet"


def full_bar_path(session_date, symbol: str) -> Path:
    iso = session_date.isoformat() if hasattr(session_date, "isoformat") else str(session_date)
    return FULL_BARS / iso / f"{safe_symbol_filename(symbol)}.parquet"


def virgin_bar_path(session_date, symbol: str) -> Path:
    iso = session_date.isoformat() if hasattr(session_date, "isoformat") else str(session_date)
    return VIRGIN_BARS / iso / f"{safe_symbol_filename(symbol)}.parquet"


def virgin_eod_path(symbol: str, chunk: str) -> Path:
    return VIRGIN_EOD / chunk / f"{safe_symbol_filename(symbol)}.parquet"


def virgin_iwm_path(session_date) -> Path:
    iso = session_date.isoformat() if hasattr(session_date, "isoformat") else str(session_date)
    return VIRGIN_IWM / f"{iso}.parquet"


def ensure_virgin_dirs() -> None:
    """Create only data/virgin trees. Does not mkdir data/full or Lab A data/bars."""
    for path in (VIRGIN_BARS, VIRGIN_EOD, VIRGIN_IWM, REPORTS):
        path.mkdir(parents=True, exist_ok=True)


def ensure_meta_dirs() -> None:
    """Create data/meta only. Does not mkdir data/full, data/virgin, or Lab A data/bars."""
    META_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)


def eod_path(symbol: str, chunk: str = "warmup") -> Path:
    return EOD_ROOT / chunk / f"{safe_symbol_filename(symbol)}.parquet"
