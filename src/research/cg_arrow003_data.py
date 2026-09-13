"""Arrow 003 local, independently copied tape and causal feature views.

Raw inputs are immutable. Cache partitions have one writer and explicit schemas.
An official/end-of-day mark is valuation only, never an execution observation.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics
import time as timer
from functools import lru_cache

import polars as pl

from ingest.calendar import NYSE_EARLY_CLOSE
from ingest.paths import DATA, REPO_ROOT, safe_symbol_filename
from research.clock import arrow70_feature_sessions, arrow70_score_sessions, session_bar_path
from research.cg_arrow002_lab import history_features

ROOT = DATA / "tmp" / "cg_arrow003"
OLD = DATA / "tmp" / "cg_arrow002r"
FEATS = arrow70_feature_sessions()
SCORE = arrow70_score_sessions()
INDEX = {d: i for i, d in enumerate(FEATS)}
SCHEMA = "cg003_raw_local_v1"
CONVENTION = "cg003_common_partial_actions_v1"
ACTION_PATH = REPO_ROOT / "reports" / "cg_arrow003_corporate_actions.json"


@lru_cache(maxsize=1)
def action_events():
    return read(ACTION_PATH)["events"] if ACTION_PATH.exists() else []


def adjustment_factor(symbol, observed, asof):
    factor = 1.0
    for e in action_events():
        if e["symbol"]==symbol and observed.isoformat()<e["effective_session"]<=asof.isoformat():
            factor *= e["price_factor"]
    return factor


def adjusted_record(rec, factor):
    if rec is None or factor==1:
        return rec
    out = dict(rec)
    for k in ("open","close","high","low","checkpoint","next_open","entry_px","preorder"):
        if out.get(k) is not None:
            out[k] *= factor
    for k in ("volume","cp_volume"):
        if out.get(k) is not None:
            out[k] /= factor
    return out


def history_asof(symbol, days, asof, summaries):
    return [adjusted_record(summaries.get((x.isoformat(),symbol)),adjustment_factor(symbol,x,asof)) for x in days]


def repair_rankings(ranks):
    result = {}
    for iso,rec in ranks.items():
        d = date.fromisoformat(iso)
        back = FEATS[INDEX[d]-15]
        rows = []
        for h in rec["rows"]:
            f = adjustment_factor(h["symbol"],back,d)
            ret = (1+h["raw_return"])/f-1
            rows.append({**h,"raw_return":ret,"residual":ret-(rec.get("iwm15") or 0),"documented_rank_factor":f})
        # Inherited field and stable tie order preserved; every cached eligible row
        # competes after the common documented-event repair, not only old winners.
        rows.sort(key=lambda h:h["raw_return"],reverse=True)
        result[iso] = {**rec,"rows":rows}
    return result


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    # Canonical LF bytes must match the committed freeze on Windows as well.
    temp.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    temp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_path(path):
    """Check lexical containment before resolving or reading any target."""
    root = REPO_ROOT.absolute()
    p = Path(path).absolute()
    if not p.is_relative_to(root) or ".." in p.parts:
        raise ValueError("Path outside the independent lab")
    cursor = root
    for part in p.relative_to(root).parts:
        cursor = cursor / part
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError("Linked lab inputs are forbidden")
    return p


def close_time(d):
    return NYSE_EARLY_CLOSE.get(d, time(16))


def read_bars(d, symbol):
    canonical = session_bar_path(d, symbol)
    paths = [canonical] + [DATA / tree / "bars" / d.isoformat() /
                           (safe_symbol_filename(symbol) + ".parquet")
                           for tree in ("virgin", "full")]
    seen = set()
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        safe_path(p)
        if not p.is_file():
            continue
        try:
            df = pl.read_parquet(p, columns=["bar_start", "open", "high", "low", "close", "volume"])
        except (OSError, pl.exceptions.PolarsError):
            continue
        clock = pl.col("bar_start").dt.time()
        df = df.filter((clock >= time(9, 30)) & (clock < close_time(d)) &
                       (pl.col("volume") > 0) & pl.col("open").is_finite() &
                       pl.col("close").is_finite() & (pl.col("open") > 0) &
                       (pl.col("close") > 0)).sort("bar_start")
        if df.height:
            return df, p.relative_to(REPO_ROOT).as_posix()
    return None, None


def summarize(df, d, source=None):
    if df is None or df.is_empty():
        return None
    last = df.row(-1, named=True)
    first = df.row(0, named=True)
    clock = pl.col("bar_start").dt.time()
    early = d in NYSE_EARLY_CLOSE
    cp = df.filter(clock == time(15, 55)) if not early else df.head(0)
    before = df.filter(clock <= time(15, 55)) if not early else df.head(0)
    later = df.filter(clock >= time(15, 56)) if not early else df.head(0)
    # Fixed final-minute execution avoids retrospectively selecting an earlier print.
    final_minute = (datetime.combine(d, close_time(d)) - timedelta(minutes=1)).time()
    closing = df.filter(clock == final_minute)
    pre = df.filter(clock < final_minute)
    total = float(df["volume"].sum())
    signed = df.select(((pl.col("close")-pl.col("open")).sign()*pl.col("volume")).sum()).item()
    late = df.filter(clock >= time(15)) if not early else df.head(0)
    return {"schema": SCHEMA, "source": source, "mark_kind": "minute_close",
            "ts": last["bar_start"].isoformat(), "close": float(last["close"]),
            "open": float(first["open"]), "first_ts": first["bar_start"].isoformat(),
            "high": float(df["high"].max()), "low": float(df["low"].min()), "volume": total,
            "signed_volume_ratio": float(signed/total),
            "checkpoint": float(cp["close"][0]) if cp.height else None,
            "cp_volume": float(before["volume"].sum()) if cp.height else None,
            "next_ts": later["bar_start"][0].isoformat() if later.height else None,
            "next_open": float(later["open"][0]) if later.height else None,
            "entry_ts": closing["bar_start"][0].isoformat() if closing.height else None,
            "entry_px": float(closing["close"][0]) if closing.height else None,
            "preorder": float(pre["close"][-1]) if pre.height else None,
            "preorder_ts": pre["bar_start"][-1].isoformat() if pre.height else None,
            "late_volume_share": float(late["volume"].sum()/total) if late.height else None,
            "early_close": early}


def eod_mark(d, symbol):
    """Compatible local EOD close, explicitly valuation-only and unadjusted if declared.

    Unknown adjustment schemas are not silently mixed with the raw minute convention.
    """
    base = DATA / "virgin" / "eod"
    for chunk in (d.strftime("%Y-%m"), d.strftime("%Y-%m") + "-early"):
        p = safe_path(base / chunk / (safe_symbol_filename(symbol) + ".parquet"))
        if not p.is_file():
            continue
        df = pl.read_parquet(p)
        # Copied Theta EOD schema is examined in the repair audit before adoption.
        if "session_date" not in df.columns or "close" not in df.columns:
            continue
        rows = df.filter(pl.col("session_date").cast(pl.String) == d.isoformat())
        if rows.height and "adjusted" in rows.columns and rows["adjusted"][0] is False:
            px = float(rows["close"][0])
            if math.isfinite(px) and px > 0:
                return {"schema":SCHEMA,"close":px,"mark_kind":"declared_unadjusted_eod",
                        "source":p.relative_to(REPO_ROOT).as_posix(),"ts":None}
    return None


def summary_job(job):
    iso, symbols = job
    d = date.fromisoformat(iso)
    p = ROOT / "summaries" / (iso + ".json")
    cache = read(p) if p.exists() else {}
    for sym in symbols:
        if sym not in cache or (cache[sym] is not None and cache[sym].get("schema")!=SCHEMA):
            df, source = read_bars(d, sym)
            cache[sym] = summarize(df, d, source) or eod_mark(d, sym)
    dump(p, cache)
    return iso, {sym:cache[sym] for sym in symbols}


def load_summaries(needs, workers=8):
    by = defaultdict(set)
    for iso, sym in needs:
        by[iso].add(sym)
    out = {}
    start = timer.monotonic()
    with ProcessPoolExecutor(max_workers=min(workers, 8)) as pool:
        futures = [pool.submit(summary_job, (iso, sorted(syms))) for iso,syms in sorted(by.items())]
        for n,f in enumerate(as_completed(futures), 1):
            iso, rows = f.result()
            out.update({(iso,sym):v for sym,v in rows.items()})
            if n % 32 == 0 or n == len(futures):
                elapsed = timer.monotonic()-start
                print(f"{stamp()} summaries {n}/{len(futures)} elapsed={elapsed:.1f}s "
                      f"ETA~{elapsed/n*(len(futures)-n):.1f}s", flush=True)
    return out


def features(hist):
    # Feature history never substitutes stale or EOD marks for volume/ranges.
    hist = [x if x and x.get("mark_kind") == "minute_close" else None for x in hist]
    out = history_features(hist[-21:])
    out["positive_days3"] = (sum(b["close"]>a["close"] for a,b in zip(hist[-4:-1],hist[-3:]))
                             if len(hist)>=4 and all(hist[-4:]) else None)
    ratios = []
    for stop in range(max(0,len(hist)-3),len(hist)):
        window = hist[max(0,stop-20):stop+1]
        if len(window)==21 and all(window):
            mean = statistics.mean(x["volume"] for x in window[:-1])
            ratios.append(window[-1]["volume"]/mean if mean > 0 else None)
        else:
            ratios.append(None)
    out["volume_persistence3"] = statistics.median(ratios) if len(ratios)==3 and all(x is not None for x in ratios) else None
    out["volume_median_ratio"] = None
    out["late_share_ratio"] = None
    if len(hist)>=21 and all(hist[-21:]):
        med = statistics.median(x["volume"] for x in hist[-21:-1])
        out["volume_median_ratio"] = hist[-1]["volume"]/med if med > 0 else None
        late = [x.get("late_volume_share") for x in hist[-21:]]
        if all(x is not None for x in late) and statistics.mean(late[:-1]) > 0:
            out["late_share_ratio"] = late[-1]/statistics.mean(late[:-1])
    out["volume_previous_ratio"] = ratios[-2] if len(ratios)>=2 else None
    return out


def checkpoint_ratio(d, sym, summaries):
    now = summaries.get((d.isoformat(),sym))
    if not now or now.get("cp_volume") is None:
        return None
    # Early closes do not have a same-slot observation: strict consecutive history,
    # neutral fallback rather than replacing a missing slot with a full-day value.
    hist = history_asof(sym,FEATS[max(0,INDEX[d]-20):INDEX[d]],d,summaries)
    if len(hist)!=20 or any(not x or x.get("cp_volume") is None for x in hist):
        return None
    mean = statistics.mean(x["cp_volume"] for x in hist)
    return now["cp_volume"]/mean if mean > 0 else None


def minute_cache_path(d,sym):
    return ROOT/"minute_paths"/d.isoformat()/(safe_symbol_filename(sym)+".json")


def minute_job(job):
    iso,sym=job
    d=date.fromisoformat(iso)
    p=minute_cache_path(d,sym)
    if p.exists() and read(p).get("schema")=="cg003_minute_decisions_v1":
        return p.relative_to(REPO_ROOT).as_posix(),digest(p)
    df,source=read_bars(d,sym)
    observations=[]
    if df is not None:
        rows=list(df.select("bar_start","open","close").iter_rows(named=True))
        for now,nxt in zip(rows,rows[1:]):
            observations.append({"decision":now["bar_start"].isoformat(),"price":float(now["close"]),
                                 "execution":nxt["bar_start"].isoformat(),"fill":float(nxt["open"])})
    dump(p,{"schema":"cg003_minute_decisions_v1","source":source,"observations":observations})
    return p.relative_to(REPO_ROOT).as_posix(),digest(p)


def prepare_minutes(ranks,workers=8):
    jobs=set()
    for iso,rec in ranks.items():
        d=date.fromisoformat(iso)
        for h in rec["rows"][:8]:
            for day in FEATS[INDEX[d]+2:min(len(FEATS),INDEX[d]+11)]:
                jobs.add((day.isoformat(),h["symbol"]))
    identity={}
    start=timer.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for n,(path,sha) in enumerate(pool.map(minute_job,sorted(jobs)),1):
            identity[path]=sha
            if n%128==0 or n==len(jobs):
                spent=timer.monotonic()-start
                print(f"{stamp()} causal minute paths {n}/{len(jobs)} ETA~{spent/n*(len(jobs)-n):.1f}s",flush=True)
    return identity


@lru_cache(maxsize=4096)
def minute_observations(iso,sym):
    p=minute_cache_path(date.fromisoformat(iso),sym)
    if not p.exists():raise RuntimeError("Required minute decision cache was not prepared")
    return read(p)["observations"]


def data_for(mode, workers=8, *, need_minutes=False):
    from research.cg_arrow003_lab import authorize
    authorize(mode)
    modes = ("IS","OOS") if mode=="ALL" else (mode,)
    ranks = {}
    for split in modes:
        p = OLD / f"ranks_{split}_wed.json"
        raw = read(safe_path(p))
        if any(date.fromisoformat(d).month % 2 != (split=="IS") for d in raw):
            raise RuntimeError("Signal-cohort cache mismatch")
        ranks.update(raw)
    ranks = repair_rankings(ranks)
    needs = set()
    for iso,rec in ranks.items():
        d = date.fromisoformat(iso)
        for h in rec["rows"][:8]:
            # Include complete remaining lifecycle for delayed exits/terminal marks.
            for x in FEATS[max(0,INDEX[d]-22):]:
                needs.add((x.isoformat(),h["symbol"]))
    summaries = load_summaries(needs, workers)
    if need_minutes:
        prepare_minutes(ranks,workers)
    return dict(sorted(ranks.items())), summaries
