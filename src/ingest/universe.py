from __future__ import annotations

import polars as pl

from ingest.paths import ARROW02_UNIVERSE, SYMBOLS, SYMBOLS_RAW, ensure_dirs
from ingest.symbols import filter_candidates, type_col_name


def persist_raw_symbols(df: pl.DataFrame) -> None:
    ensure_dirs()
    SYMBOLS_RAW.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(SYMBOLS_RAW)
    print(f"LIST raw columns={df.columns} rows={df.height}", flush=True)
    for col in df.columns:
        nuniq = df[col].n_unique()
        print(f"  col {col}: n_unique={nuniq}", flush=True)
        if nuniq <= 40 and col.lower() != "symbol":
            vc = df[col].value_counts().sort("count", descending=True)
            print(f"  value_counts {col}: {vc.to_dicts()[:20]}", flush=True)


def candidates_from_raw(df: pl.DataFrame) -> tuple[list[str], dict[str, int], str | None]:
    col = "symbol" if "symbol" in df.columns else df.columns[0]
    raw = [str(x).strip().upper() for x in df[col].to_list()]
    tcol = type_col_name(list(df.columns))
    types = [str(x) for x in df[tcol].to_list()] if tcol else None
    cands, funnel = filter_candidates(raw, types=types)
    pl.DataFrame({"symbol": cands}).write_parquet(SYMBOLS)
    return cands, funnel, tcol


def write_universe_report(
    *,
    funnel: dict[str, int],
    type_col: str | None,
    elig: pl.DataFrame,
    notes: list[str],
) -> None:
    warmup = elig.filter(pl.col("is_warmup") & pl.col("eligible"))
    per = warmup.group_by("session_date").len().sort("session_date")
    counts = per["len"].to_list() if per.height else [0]
    mean_n = sum(counts) / len(counts)
    lines = [
        "Arrow 2 — universe filter funnel",
        f"theta_type_column: {type_col or '(none — Theta stock_list_symbols returned no type field)'}",
        f"raw_list_count: {funnel.get('raw', 0)}",
        f"regex_kept: {funnel.get('regex_kept', 0)}",
        f"type_dropped: {funnel.get('type_dropped', 0)}",
        f"etp_dropped: {funnel.get('etp_dropped', 0)}",
        f"final_candidates: {funnel.get('candidates', 0)}",
        f"warmup_eligible_mean: {mean_n:.1f}",
        f"warmup_eligible_min: {min(counts)}",
        f"warmup_eligible_max: {max(counts)}",
        "warmup_eligible_per_session:",
    ]
    for row in per.iter_rows(named=True):
        lines.append(f"  {row['session_date']}: {row['len']}")
    lines += [
        "",
        "arrow1_eligible_mean: 2756.8",
        f"delta_vs_arrow1: {mean_n - 2756.8:.1f}",
        "",
        "notes:",
        "  - ETP denylist: src/ingest/etp_tickers.txt from NASDAQ Trader symbol directories.",
        "  - Warmup eligibility recomputed from existing EOD parquet (plus CON/PRN retry).",
        "  - Zero-volume 1m bars (full 270-minute grid) are stored as Theta returned them;",
        "    later research must not treat zero-volume minutes as trades.",
        "  - 2026-07-03 and 2026-06-19 are NYSE full closes; not study sessions.",
    ]
    lines.extend(f"  - {n}" for n in notes)
    if mean_n > 2500:
        lines.append(
            "  - WARNING: eligible/day still near Arrow 1 ~2757; denylist may be too weak."
        )
    text = "\n".join(lines) + "\n"
    ARROW02_UNIVERSE.parent.mkdir(parents=True, exist_ok=True)
    ARROW02_UNIVERSE.write_text(text, encoding="utf-8")
    print(text, flush=True)
