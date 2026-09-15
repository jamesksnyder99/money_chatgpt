"""Arrow 005 data layer: checked observations with explicit source and status.

Precedence: validated repair partitions (data/verification/r4r5/v1/validated) first,
then the original canonical minute tree (virgin through 2026-05-29, full afterwards),
then the alternate copied tree. National EOD reports are same-vendor references
only: they never supply an execution. Every observation carries its source path.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import math
import os
from pathlib import Path
import statistics

import polars as pl

from ingest.calendar import NYSE_EARLY_CLOSE, nyse_sessions
from ingest.paths import DATA, REPO_ROOT, safe_symbol_filename

VERSION = "r4r5_v1"
VERIFY_ROOT = DATA / "verification" / "r4r5" / "v1"
VALIDATED = VERIFY_ROOT / "validated"
CACHE = VERIFY_ROOT / "cache" / f"summaries_{VERSION}"
HANDOFF = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow005"
ACTION_PATH_V1 = REPO_ROOT / "reports" / "cg_arrow003_corporate_actions.json"
ACTION_PATH_V2 = REPO_ROOT / "reports" / "cg_arrow005_corporate_actions.json"  # v2: inherited plus Arrow 005 additions
ACTION_PATH_V3 = REPO_ROOT / "reports" / "cg_arrow006_corporate_actions.json"  # v3: Arrow 006 reference
ACTION_PATH_V4 = REPO_ROOT / "reports" / "cg_arrow007_corporate_actions.json"  # v4: Arrow 007 reference
# v5 is the active reference for the 2025-26 study. A different study corridor must be able to
# point this at its own documented table, and the override has to survive process boundaries: the
# summary loader runs in worker processes that import this module fresh, and those workers resolve
# point-in-time ticker identity through identity_events(). An in-process patch would silently fail
# to reach them and a 2025-26 identity or split event could then be applied to a 2024-25
# observation wherever the effective sessions overlap. The environment carries the override.
ACTION_PATH = Path(os.environ.get("CG_ACTION_PATH")
                   or REPO_ROOT / "reports" / "cg_arrow008_corporate_actions.json")
RANKS_PATH = DATA / "tmp" / "cg_arrow002r" / "ranks_ALL_wed.json"
VIRGIN_END = date(2026, 5, 29)
LOCAL_TAPE_END = date(2026, 9, 11)  # Arrow 006: last required H10 exit of the 2026-08-26 cohort, now retrievable
CUTOFF = date(2026, 8, 31)
FEATS = nyse_sessions(date(2025, 8, 1), date(2026, 9, 30))
INDEX = {d: i for i, d in enumerate(FEATS)}
SCORE = [d for d in FEATS if date(2025, 9, 2) <= d <= CUTOFF]
IS_MONTHS = {9, 11, 1, 3, 5, 7}

STATUS = ("PRESENT_CHECKED", "NOT_PREVIOUSLY_REQUESTED", "EMPTY_RESPONSE_UNRESOLVED",
          "PARTIAL_OR_SPARSE_REVIEW", "RETRIEVED_CHECKED", "DOCUMENTED_NO_TRADING",
          "CORPORATE_ACTION_OR_ID_REVIEW", "UNRESOLVED", "FUTURE_NOT_OBSERVABLE")


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def split_of(signal: date) -> str:
    return "IS" if signal.month in IS_MONTHS else "OOS"


def close_time(d: date) -> time:
    return NYSE_EARLY_CLOSE.get(d, time(16))


def final_minute(d: date) -> time:
    return (datetime.combine(d, close_time(d)) - timedelta(minutes=1)).time()


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dump_json(path: Path, obj) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@lru_cache(maxsize=100_000)
def _safe_dir(directory: Path) -> None:
    """Containment and link check for a directory prefix, memoised per directory.

    Walking every component for every file made the loader syscall-bound; the
    check is identical for every file in the same directory, so it is cached.
    """
    root = REPO_ROOT.absolute()
    if not directory.is_relative_to(root) or ".." in directory.parts:
        raise ValueError("Path outside the independent lab")
    cursor = root
    for part in directory.relative_to(root).parts:
        cursor = cursor / part
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError("Linked lab inputs are forbidden")


def safe_path(path: Path) -> Path:
    p = Path(path).absolute()
    _safe_dir(p.parent)
    if p.is_symlink() or p.is_junction():
        raise ValueError("Linked lab inputs are forbidden")
    return p


# ---------------------------------------------------------------- corporate actions
@lru_cache(maxsize=1)
def action_events() -> tuple:
    if not ACTION_PATH.exists():
        return ()
    return tuple(read_json(ACTION_PATH)["events"])


def adjustment_factor(symbol: str, observed: date, asof: date, events=None) -> float:
    """Price factor converting a price observed on `observed` into `asof` units."""
    factor = 1.0
    for e in (action_events() if events is None else events):
        if e["symbol"] == symbol and observed.isoformat() < e["effective_session"] <= asof.isoformat():
            factor *= e["price_factor"]
    return factor


def adjusted(rec: dict | None, factor: float) -> dict | None:
    if rec is None or factor == 1:
        return rec
    out = dict(rec)
    for k in ("open", "close", "high", "low", "entry_px", "preorder", "eod_close"):
        if out.get(k) is not None:
            out[k] *= factor
    if out.get("volume") is not None:
        out["volume"] /= factor
    return out


@lru_cache(maxsize=1)
def identity_events() -> tuple:
    """Documented symbol changes: the same security trading under a successor ticker."""
    if not ACTION_PATH.exists():
        return ()
    return tuple(read_json(ACTION_PATH).get("security_identity", []))


def resolved_symbol(symbol: str, d: date) -> str:
    """Ticker under which this security actually traded on session d."""
    out = symbol
    for e in identity_events():
        if e["symbol"] == out and d.isoformat() >= e["effective_session"]:
            out = e["successor"]
    return out


@lru_cache(maxsize=1)
def trading_events() -> tuple:
    """Documented halts/suspensions: real non-execution, never a missing observation."""
    if not ACTION_PATH.exists():
        return ()
    return tuple(read_json(ACTION_PATH).get("trading_events", []))


def halted(symbol: str, d: date) -> dict | None:
    for e in trading_events():
        if e["symbol"] == symbol and d.isoformat() >= e["first_non_trading_session"]:
            return e
    return None


@lru_cache(maxsize=1)
def non_comparable_events() -> tuple:
    """Documented events after which a price series is not one continuous claim.

    A plan-of-reorganisation share exchange changes both the share count and the economic
    claim, so no single factor converts a pre-event price into post-event units. A ranking
    return spanning such an event is not a return; the candidate simply cannot be ranked
    across it under the unchanged rule.
    """
    if not ACTION_PATH.exists():
        return ()
    return tuple(read_json(ACTION_PATH).get("non_comparable_events", []))


def spans_non_comparable(symbol: str, first: date, last: date) -> dict | None:
    for e in non_comparable_events():
        if e["symbol"] == symbol and first.isoformat() < e["effective_session"] <= last.isoformat():
            return e
    return None


# ---------------------------------------------------------------- source resolution
# Arrow 013 landed the September 2024 to August 2025 holdout into its own immutable tree. Its
# sessions (2024-08-01 to 2025-07-31) do not overlap the 2025-26 study trees, so listing it as a
# candidate source is additive: for any pre-existing study date the holdout path simply does not
# exist. Resolution must live here rather than in a caller-side patch, because the summary loader
# runs in worker processes that import this module fresh.
HOLDOUT_BARS = DATA / "holdout2024" / "raw" / "bars"
# Arrow 014 gap-fill. Extending eligibility across August 2025 admitted candidates the Arrow 013
# minute universe never contained, so their ranking and feature corridors had no bars at all.
# Those are acquired into their own tree, and that tree is resolved LAST on purpose: a gap-fill
# source that sorts after every existing one can supply an observation nothing else has, and can
# never quietly replace one that already exists.
HOLDOUT_REPAIR_BARS = DATA / "holdout2024" / "repair" / "bars"


def candidate_paths(d: date, symbol: str) -> list[tuple[str, Path]]:
    fn = safe_symbol_filename(resolved_symbol(symbol, d)) + ".parquet"
    primary = "virgin" if d <= VIRGIN_END else "full"
    alternate = "full" if primary == "virgin" else "virgin"
    return [("validated", VALIDATED / d.isoformat() / fn),
            ("holdout_raw", HOLDOUT_BARS / d.isoformat() / fn),
            (primary, DATA / primary / "bars" / d.isoformat() / fn),
            (alternate, DATA / alternate / "bars" / d.isoformat() / fn),
            ("holdout_repair", HOLDOUT_REPAIR_BARS / d.isoformat() / fn)]


def read_bars(d: date, symbol: str):
    """Return (rth_frame, source_label, relative_path, checks) or (None, None, None, checks)."""
    checks = {"tried": [], "duplicates": 0, "unordered": False, "ohlc_inconsistent": 0, "negative_volume": 0}
    for label, p in candidate_paths(d, symbol):
        safe_path(p)
        if not p.is_file():
            continue
        checks["tried"].append(p.relative_to(REPO_ROOT).as_posix())
        try:
            df = pl.read_parquet(p, columns=["bar_start", "open", "high", "low", "close", "volume"])
        except (OSError, pl.exceptions.PolarsError):
            continue
        if df.height == 0:
            checks.setdefault("empty_files", []).append(label)
            continue
        checks["negative_volume"] += int(df.filter(pl.col("volume") < 0).height)
        checks["unordered"] = bool(not df["bar_start"].is_sorted())
        checks["duplicates"] += int(df.height - df["bar_start"].n_unique())
        clock = pl.col("bar_start").dt.time()
        rth = df.filter((clock >= time(9, 30)) & (clock < close_time(d)) & (pl.col("volume") > 0)
                        & pl.col("open").is_finite() & pl.col("close").is_finite()
                        & (pl.col("open") > 0) & (pl.col("close") > 0)).sort("bar_start")
        checks["ohlc_inconsistent"] += int(rth.filter((pl.col("high") < pl.col("low")) | (pl.col("close") > pl.col("high") + 1e-9)
                                                        | (pl.col("close") < pl.col("low") - 1e-9)).height)
        if rth.height:
            return rth, label, p.relative_to(REPO_ROOT).as_posix(), checks
    return None, None, None, checks


ACCEPTED_STRUCTURAL_ISSUES: dict = {}


def set_accepted_structural_issues(mapping: dict) -> None:
    """(symbol, session) -> reason. An explicitly reviewed and accepted structural defect."""
    ACCEPTED_STRUCTURAL_ISSUES.clear()
    ACCEPTED_STRUCTURAL_ISSUES.update(mapping)


def structural_issues(checks: dict) -> list[str]:
    """Structural defects that must block a VERIFIED status until reviewed."""
    out = []
    if checks.get("duplicates"):
        out.append(f"duplicate_timestamps={checks['duplicates']}")
    if checks.get("unordered"):
        out.append("unordered_timestamps")
    if checks.get("ohlc_inconsistent"):
        out.append(f"ohlc_inconsistent={checks['ohlc_inconsistent']}")
    if checks.get("negative_volume"):
        out.append(f"negative_volume={checks['negative_volume']}")
    return out


def structural_block(symbol: str, d: date, rec: dict | None) -> str | None:
    """None when the observation may support a verified execution, else the blocking reason."""
    if not rec or not rec.get("structural_issues"):
        return None
    accepted = ACCEPTED_STRUCTURAL_ISSUES.get((symbol, d.isoformat()))
    if accepted:
        return None
    return "; ".join(rec["structural_issues"])


def summarize(df: pl.DataFrame, d: date, source: str, path: str, checks: dict) -> dict:
    last = df.row(-1, named=True)
    first = df.row(0, named=True)
    clock = pl.col("bar_start").dt.time()
    fm = final_minute(d)
    closing = df.filter(clock == fm)
    pre = df.filter(clock < fm)
    return {"version": VERSION, "source": source, "path": path, "mark_kind": "minute_close",
            "ts": last["bar_start"].isoformat(), "close": float(last["close"]),
            "first_ts": first["bar_start"].isoformat(), "open": float(first["open"]),
            "high": float(df["high"].max()), "low": float(df["low"].min()),
            "volume": float(df["volume"].sum()), "n_bars": int(df.height),
            "entry_ts": closing["bar_start"][0].isoformat() if closing.height else None,
            "entry_px": float(closing["close"][0]) if closing.height else None,
            # Execution reference. The original engine took the final-minute print when it
            # existed and otherwise the session's last regular-hours print; a thinly traded
            # security has no 15:59 trade, and that is trading behaviour, not a data gap.
            "exec_ts": (closing["bar_start"][0].isoformat() if closing.height
                        else last["bar_start"].isoformat()),
            "exec_px": float(closing["close"][0]) if closing.height else float(last["close"]),
            "exec_field": ("final_minute_bar_close" if closing.height
                           else "last_regular_hours_print_fallback"),
            "preorder": float(pre["close"][-1]) if pre.height else None,
            "preorder_ts": pre["bar_start"][-1].isoformat() if pre.height else None,
            "early_close": d in NYSE_EARLY_CLOSE,
            "checks": {k: v for k, v in checks.items() if k != "tried"}}


HOLDOUT_EOD = DATA / "holdout2024" / "raw" / "eod"


def eod_reference(d: date, symbol: str) -> dict | None:
    """Same-vendor national 17:15 EOD close. Reference only; not an RTH execution.

    Both end-of-day trees are searched. The pristine 2024-25 corridor was landed under
    `data/holdout2024/raw/eod`, so a virgin-only lookup would silently drop the independent
    EOD cross-reference for every session before August 2025 — exactly the corridor whose
    executions most need a second source to check against.
    """
    for base in (DATA / "virgin" / "eod", HOLDOUT_EOD):
        for chunk in (d.strftime("%Y-%m"), d.strftime("%Y-%m") + "-early"):
            p = base / chunk / (safe_symbol_filename(symbol) + ".parquet")
            safe_path(p)
            if not p.is_file():
                continue
            try:
                df = pl.read_parquet(p, columns=["eod_date", "close", "last_trade", "volume"])
            except (OSError, pl.exceptions.PolarsError):
                continue
            rows = df.filter(pl.col("eod_date") == d)
            if rows.height:
                px = float(rows["close"][0])
                if math.isfinite(px) and px > 0:
                    return {"eod_close": px, "eod_last_trade": str(rows["last_trade"][0]),
                            "eod_volume": float(rows["volume"][0]),
                            "eod_path": p.relative_to(REPO_ROOT).as_posix(),
                            "scope": "national_1715_report; adjustment undeclared"}
    return None


def _file_key(p: Path) -> str:
    st = p.stat()
    return f"{st.st_size}:{int(st.st_mtime)}"


def resolve_source(d: date, symbol: str):
    """First existing candidate partition for a symbol-session, by loader precedence."""
    for label, p in candidate_paths(d, symbol):
        safe_path(p)
        if p.is_file():
            return label, p
    return None, None


def summary_job(job):
    """Build one date partition of the summary cache.

    Sources are resolved first, then read in batches with a single polars call per
    source tree, because one call per symbol made the loader I/O-bound.
    """
    iso, symbols = job
    d = date.fromisoformat(iso)
    p = CACHE / (iso + ".json")
    cache = read_json(p) if p.exists() else {}
    todo, resolved = [], {}
    for sym in symbols:
        label, path = resolve_source(d, sym)
        key = _file_key(path) if path else None
        entry = cache.get(sym)
        if entry is not None and entry.get("_key") == key and entry.get("version") == VERSION:
            continue
        resolved[sym] = (label, path, key)
        todo.append(sym)
    if todo:
        by_path = {}
        for sym in todo:
            label, path, _ = resolved[sym]
            if path is not None:
                by_path.setdefault(path, sym)
        frames = {}
        paths = sorted(by_path)
        for chunk in (paths[i:i + 400] for i in range(0, len(paths), 400)):
            try:
                df = pl.read_parquet(chunk, columns=["symbol", "bar_start", "open", "high", "low",
                                                     "close", "volume"])
            except (OSError, pl.exceptions.PolarsError):
                df = None
            if df is None or df.is_empty():
                continue
            for (sym,), part in df.group_by("symbol"):
                frames[sym] = part
        for sym in todo:
            label, path, key = resolved[sym]
            raw = frames.get(resolved_symbol(sym, d))
            checks = {"tried": [path.relative_to(REPO_ROOT).as_posix()] if path else [],
                      "duplicates": 0, "unordered": False, "ohlc_inconsistent": 0, "negative_volume": 0}
            rth = None
            if raw is not None and raw.height:
                checks["negative_volume"] = int(raw.filter(pl.col("volume") < 0).height)
                checks["unordered"] = bool(not raw["bar_start"].is_sorted())
                checks["duplicates"] = int(raw.height - raw["bar_start"].n_unique())
                clock = pl.col("bar_start").dt.time()
                rth = raw.filter((clock >= time(9, 30)) & (clock < close_time(d)) & (pl.col("volume") > 0)
                                 & pl.col("open").is_finite() & pl.col("close").is_finite()
                                 & (pl.col("open") > 0) & (pl.col("close") > 0)).sort("bar_start")
                checks["ohlc_inconsistent"] = int(rth.filter(
                    (pl.col("high") < pl.col("low")) | (pl.col("close") > pl.col("high") + 1e-9)
                    | (pl.col("close") < pl.col("low") - 1e-9)).height)
                if rth.is_empty():
                    rth = None
            rec = (summarize(rth, d, label, path.relative_to(REPO_ROOT).as_posix(), checks)
                   if rth is not None else
                   # A record without a minute close has two very different causes, and the
                   # certification layer must be able to tell them apart from the record alone:
                   # the partition was retrieved and simply holds no qualifying regular-hours
                   # trade (trading behaviour), or no partition resolved / none could be read
                   # (an unresolved observation). `raw_rows` carries that evidence.
                   {"version": VERSION, "source": None, "path": None, "mark_kind": None, "missing": True,
                    "tried": checks["tried"], "empty_files": [],
                    "partition_resolved": path is not None,
                    "raw_rows": int(raw.height) if raw is not None else 0})
            issues = structural_issues(checks)
            if issues:
                rec["structural_issues"] = issues
                rec["structural_status"] = "RETRIEVED_WITH_ISSUES"
            eod = eod_reference(d, sym)
            if eod:
                rec.update(eod)
            rec["_key"] = key
            traded_as = resolved_symbol(sym, d)
            if traded_as != sym:
                rec["resolved_symbol"] = traded_as
                rec["identity_note"] = "documented ticker change; same security"
            cache[sym] = rec
        dump_json(p, cache)
    return iso, {sym: cache[sym] for sym in symbols}


def load_summaries(needs, workers: int = 8) -> dict:
    by: dict[str, set] = {}
    for iso, sym in needs:
        by.setdefault(iso, set()).add(sym)
    out = {}
    jobs = sorted((iso, sorted(s)) for iso, s in by.items())
    with ProcessPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        futures = [pool.submit(summary_job, j) for j in jobs]
        for n, f in enumerate(as_completed(futures), 1):
            iso, rows = f.result()
            out.update({(iso, s): v for s, v in rows.items()})
            if n % 40 == 0 or n == len(futures):
                print(f"{stamp()} summaries {n}/{len(futures)}", flush=True)
    return out


def present(rec: dict | None) -> bool:
    return bool(rec) and not rec.get("missing") and rec.get("mark_kind") == "minute_close"


# ---------------------------------------------------------------- manifests / statuses
@lru_cache(maxsize=1)
def manifest_rows() -> dict:
    out = {}
    for tree in ("virgin", "full"):
        p = DATA / tree / "manifest.parquet"
        if not p.exists():
            continue
        m = pl.read_parquet(p, columns=["symbol", "session_date", "status", "rows"])
        for sym, d, status, rows in m.iter_rows():
            out[(sym, d.isoformat())] = (tree, status, int(rows or 0))
    return out


VENDOR_STATUS: dict = {}


def set_vendor_status(mapping: dict) -> None:
    """Terminal vendor status per (symbol, session) from the Arrow 006 request log."""
    VENDOR_STATUS.clear()
    VENDOR_STATUS.update(mapping)


def observation_status(d: date, symbol: str, rec: dict | None, *, need_final_minute: bool) -> str:
    """Evidence label for one symbol-session; describes data, not outcomes."""
    if d > LOCAL_TAPE_END:
        return "FUTURE_NOT_OBSERVABLE" if d > date.today() else "NOT_PREVIOUSLY_REQUESTED"
    if present(rec):
        if need_final_minute and rec.get("entry_ts") is None:
            return "THIN_SESSION_LAST_PRINT_USED" if rec.get("exec_px") is not None else "PARTIAL_OR_SPARSE_REVIEW"
        return "PRESENT_CHECKED"
    vendor = VENDOR_STATUS.get((symbol, d.isoformat()))
    if vendor:
        return vendor
    man = manifest_rows().get((symbol, d.isoformat()))
    if man is None:
        return "NOT_PREVIOUSLY_REQUESTED"
    if man[2] == 0:
        return "EMPTY_RESPONSE_UNRESOLVED"
    return "PARTIAL_OR_SPARSE_REVIEW"


# ---------------------------------------------------------------- features
def history(symbol: str, days: list[date], asof: date, summaries: dict) -> list[dict | None]:
    out = []
    for x in days:
        rec = summaries.get((x.isoformat(), symbol))
        out.append(adjusted(rec, adjustment_factor(symbol, x, asof)) if present(rec) else None)
    return out


def features(hist: list[dict | None]) -> dict:
    """ret3 and the 20-session mean volume ratio exactly as the frozen R4/R5 rules define them."""
    days = hist[-21:]
    out = {"ret3": None, "volume_ratio": None, "history_sessions": sum(1 for x in days if x)}
    if len(days) >= 4 and all(x and x["close"] > 0 for x in days[-4:]):
        out["ret3"] = days[-1]["close"] / days[-4]["close"] - 1
    if len(days) == 21 and all(days):
        vb = statistics.mean(x["volume"] for x in days[:-1])
        out["volume_ratio"] = days[-1]["volume"] / vb if vb > 0 else None
    return out
