"""CG Arrow 002R: isolated signal-cohort research and immutable confirmation gate.

Raw prices and inherited missing-exit/borrow-proxy conventions are deliberate.
Only local copied tape is used. Derived market-data caches stay under data/tmp.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import time as timer

import polars as pl

from ingest.calendar import NYSE_EARLY_CLOSE
from ingest.paths import REPO_ROOT, DATA, REPORTS, VIRGIN_IWM, FULL_IWM
from research.arrow44 import _by_sess
from research.arrow47 import _short_n
from research.arrow65 import _make_trade, _mtm_and_peak
from research.arrow70 import _elig_year
from research.clock import arrow70_feature_sessions, arrow70_score_sessions, session_bar_path
from research.costs import cost_per_share, signed_pnl

ROOT = DATA / "tmp" / "cg_arrow002r"
FREEZE = REPORTS / "cg_arrow002_freeze.txt"
START = "2026-09-13T01:42:30+00:00"
CEILING = 102922.0
FEATS = arrow70_feature_sessions()
SCORE = arrow70_score_sessions()
INDEX = {d: i for i, d in enumerate(FEATS)}
CAVEAT = ("Research results under the inherited raw-price convention; "
          "corporate-action integrity remains unresolved for deployment.")


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_identity():
    # Include ALL research/ingest dependencies, not merely the new runner.
    return {p.relative_to(REPO_ROOT).as_posix(): digest(p)
            for folder in ("src/research", "src/ingest")
            for p in sorted((REPO_ROOT / folder).glob("*.py"))}


def authorize(mode, freeze=FREEZE):
    if mode == "IS":
        if (ROOT / "oos_started.json").exists():
            raise RuntimeError("Research closed: OOS has already started")
        if freeze.exists():
            try:
                status = read(freeze).get("status")
            except (ValueError,AttributeError):
                status = None  # historical NOT FROZEN text artifact
            if status == "FROZEN":
                raise RuntimeError("Research closed: finalists are frozen")
        return None
    if mode not in {"OOS", "ALL"}:
        raise ValueError("Unknown cohort")
    if not freeze.is_file():
        raise RuntimeError("A valid freeze is required before OOS")
    try:
        manifest = read(freeze)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("A valid freeze is required before OOS") from exc
    if manifest.get("status") != "FROZEN" or not manifest.get("finalists"):
        raise RuntimeError("A valid freeze is required before OOS")
    if manifest.get("code_sha256") != code_identity():
        raise RuntimeError("Frozen strategy code has changed")
    if mode == "ALL" and not (ROOT / "oos_complete.json").exists():
        raise RuntimeError("Investor view is available only after OOS completion")
    return manifest


def signal_dates(mode, schedule="wed", *, check=True):
    if check:
        authorize(mode)
    if mode not in {"IS", "OOS", "ALL"}:
        raise ValueError(mode)
    return [d for d in SCORE if (mode == "ALL" or (d.month % 2 == (mode == "IS")))
            and (schedule == "daily" or (schedule == "wed" and d.weekday() == 2))
            and INDEX[d] >= 15 and INDEX[d] + 1 < len(FEATS)]


def assert_signals(days, mode):
    if mode == "IS" and any(d.month % 2 == 0 for d in days):
        raise RuntimeError("OOS signal generation forbidden during IS research")
    if mode == "OOS" and any(d.month % 2 for d in days):
        raise RuntimeError("IS signals supplied to confirmation cohort")


def tape_summary(path, session):
    """Vectorized inherited last-RTH filter; minute checkpoint retained, not resampled execution."""
    if not path.is_file():
        return None
    try:
        df = pl.read_parquet(path, columns=["bar_start", "open", "high", "low", "close", "volume"])
    except (OSError, pl.exceptions.PolarsError):
        return None
    clock = pl.col("bar_start").dt.time()
    df = df.filter((clock >= time(9, 30)) & (clock < time(16))
                   & (pl.col("volume") > 0) & pl.col("open").is_finite()
                   & pl.col("close").is_finite()).sort("bar_start")
    if df.is_empty():
        return None
    early = NYSE_EARLY_CLOSE.get(session)
    if early is not None:
        clipped = df.filter(clock < early)
        if not clipped.is_empty():
            df = clipped
    last = df.row(-1, named=True)
    # A 15:55 bar closes at 15:56. Fill on the open of a strictly later bar.
    cp = df.filter(clock == time(15, 55))
    later = df.filter(clock >= time(15, 56))
    if early is not None:
        cp = cp.head(0)
        later = later.head(0)
    signed_volume = df.select(((pl.col("close")-pl.col("open")).sign()*pl.col("volume")).sum()).item()
    return {"schema":2,"signed_volume_ratio":float(signed_volume/df["volume"].sum()),
            "ts": last["bar_start"].isoformat(), "close": float(last["close"]),
            "open": float(df["open"][0]), "high": float(df["high"].max()),
            "low": float(df["low"].min()), "volume": float(df["volume"].sum()),
            "checkpoint": float(cp["close"][0]) if cp.height else None,
            "next_ts": later["bar_start"][0].isoformat() if later.height else None,
            "next_open": float(later["open"][0]) if later.height else None}


def summary_job(job):
    iso, symbols = job
    d = date.fromisoformat(iso)
    path = ROOT / "summaries" / (iso + ".json")
    cache = read(path) if path.exists() else {}
    for sym in symbols:
        if sym not in cache or (cache[sym] is not None and (cache[sym].get("schema") != 2
                or (d in NYSE_EARLY_CLOSE and cache[sym].get("checkpoint") is not None))):
            cache[sym] = tape_summary(session_bar_path(d, sym), d)
    dump(path, cache)
    return iso, cache


def load_summaries(needs, workers=8):
    """One writer per date; processes partition independent parquet reads."""
    by = defaultdict(set)
    for iso, sym in needs:
        by[iso].add(sym)
    result = {}
    start = timer.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        fs = [pool.submit(summary_job, (iso, sorted(syms))) for iso, syms in sorted(by.items())]
        for n, f in enumerate(as_completed(fs), 1):
            iso, rows = f.result()
            result.update({(iso, sym): x for sym, x in rows.items()})
            if n % 16 == 0 or n == len(fs):
                elapsed = timer.monotonic() - start
                print(f"{stamp()} summaries {n}/{len(fs)} elapsed={elapsed:.1f}s "
                      f"ETA~{elapsed / n * (len(fs)-n):.1f}s", flush=True)
    return result


def prepare(mode, schedule="wed", workers=8):
    days = signal_dates(mode, schedule)
    assert_signals(days, mode)  # immediately before any universe/rank generation
    by = _by_sess(_elig_year(days))
    needs = {(x.isoformat(), h["symbol"]) for d in days
             for h in by.get(d.isoformat(), []) for x in (d, FEATS[INDEX[d]-15])}
    print(f"{stamp()} prepare {mode}/{schedule}: {len(days)} signals; "
          f"{len(needs)} eligible endpoint observations; workers={workers}; no live pulls", flush=True)
    summaries = load_summaries(needs, workers)
    out = {}
    for d in days:
        root = VIRGIN_IWM if d <= date(2026, 5, 29) else FULL_IWM
        back = FEATS[INDEX[d]-15]
        backroot = VIRGIN_IWM if back <= date(2026, 5, 29) else FULL_IWM
        iwm1 = tape_summary(root / (d.isoformat()+".parquet"), d)
        iwm0 = tape_summary(backroot / (back.isoformat()+".parquet"), back)
        rows = []
        if iwm1 and iwm0 and min(iwm1["close"], iwm0["close"]) > 0:
            ir = iwm1["close"] / iwm0["close"] - 1
            for h in by.get(d.isoformat(), []):
                now = summaries.get((d.isoformat(), h["symbol"]))
                old = summaries.get((back.isoformat(), h["symbol"]))
                if now and old and min(now["close"], old["close"]) > 0:
                    raw = now["close"] / old["close"] - 1
                    rows.append({**h, "raw_return": raw, "residual": raw-ir,
                                 "now": [now["ts"], now["close"]]})
        rows.sort(key=lambda h: h["residual"], reverse=True)  # inherited stable tie order
        out[d.isoformat()] = {"rows": rows if len(rows) >= 16 else [],
                              "n_res": len(rows), "iwm15": ir if iwm1 and iwm0 else None}
    dump(ROOT / f"ranks_{mode}_{schedule}.json", out)
    print(f"{stamp()} prepared {mode}/{schedule}; rank data remain ignored local cache", flush=True)
    return out


def bounded_inverse_vol(vols, budget=32000.0, low=2000.0, high=6000.0):
    """Initial inverse-vol clip, then bounded renormalization; neutral missing-vol fallback."""
    valid = [v for v in vols if v is not None and math.isfinite(v) and v > 0]
    fallback = statistics.median(valid) if valid else 1.0
    weights = [1 / (v if v is not None and math.isfinite(v) and v > 0 else fallback) for v in vols]
    if not weights:
        return []
    budget = min(budget, high * len(weights))
    vals = [max(low, min(high, budget*w/sum(weights))) for w in weights]
    for _ in range(30):
        residual = budget - sum(vals)
        if abs(residual) < 1e-8:
            break
        ids = [i for i, x in enumerate(vals) if x < high-1e-9] if residual > 0 else [i for i, x in enumerate(vals) if x > low+1e-9]
        if not ids:
            break
        denom = sum(vals[i] for i in ids)
        for i in ids:
            vals[i] = min(high, max(low, vals[i] + residual*vals[i]/denom))
    return vals


def history_features(days):
    """Exactly 21 consecutive session closes -> 20 returns/TR observations, signal-inclusive."""
    extra = {"efficiency":None,"jump_share":None,"ret3":None,
             "volume_ratio":None,"close_location":None,"signed_volume_ratio":None}
    if days and days[-1]:
        last = days[-1]
        extra["close_location"] = ((last["close"]-last["low"])/(last["high"]-last["low"])
                                   if last["high"] > last["low"] else .5)
        extra["signed_volume_ratio"] = last.get("signed_volume_ratio")
    if len(days) >= 4 and all(x and x["close"] > 0 for x in days[-4:]):
        extra["ret3"] = days[-1]["close"]/days[-4]["close"]-1
    if len(days) >= 16 and all(x and x["close"] > 0 for x in days[-16:]):
        path = [x["close"] for x in days[-16:]]
        inc = [b-a for a,b in zip(path,path[1:])]
        gain = path[-1]-path[0]
        extra["efficiency"] = gain/sum(abs(x) for x in inc) if any(inc) else 0
        extra["jump_share"] = max(inc)/gain if gain > 0 else 0
    if len(days) == 21 and all(days):
        vb = statistics.mean(x["volume"] for x in days[:-1])
        extra["volume_ratio"] = days[-1]["volume"]/vb if vb > 0 else None
    if len(days) != 21 or any(x is None or x["close"] <= 0 for x in days):
        return {"vol20":None,"atr20":None,**extra}
    rets = [b["close"]/a["close"]-1 for a,b in zip(days, days[1:])]
    trs = [max(b["high"]-b["low"], abs(b["high"]-a["close"]), abs(b["low"]-a["close"]))
           for a,b in zip(days, days[1:])]
    return {"vol20":statistics.stdev(rets),"atr20":statistics.mean(trs),**extra}


@dataclass(frozen=True)
class Spec:
    id: str
    origin: str = "CONTROL"
    mechanism: str = "Frozen Wednesday eight-name hold-short-for-fade parent"
    schedule: str = "wed"
    ticket: float = 4000.0
    sizing: str = "equal"
    width_cut: float | None = None
    cap: float | None = None
    substitute: bool = False
    protection: str = "none"
    arm_atr: float = 2.0
    rebound_atr: float = 1.0
    min_hold: int = 3
    feature_rule: str = "none"
    feature_cut: float | None = None
    feature_low_size: float = .5
    feature_direction: str = "high"
    rank_pool: int = 8
    account_cap: float | None = None
    portfolio_rule: str = "none"
    entry_confirmation: bool = False
    secondary_rule: str = "none"
    secondary_cut: float | None = None
    secondary_direction: str = "high"
    cluster_cap: float | None = None
    cluster_correlation: float = .75
    selection_rule: str = "none"
    protection_clock: str = "daily_1555"
    recycle: bool = False

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}",self.id):
            raise ValueError("Invalid strategy identifier")
        if self.origin not in {"CONTROL","DIRECTED","ASTRA","DERIVED"}:
            raise ValueError("Unknown origin")
        if self.schedule not in {"wed","daily"} or self.sizing not in {"equal","width","inverse_vol"}:
            raise ValueError("Unknown schedule or sizing")
        if self.protection not in {"none","full","half"} or self.protection_clock not in {"daily_1555","all_minutes"}:
            raise ValueError("Unknown protection rule")
        if self.selection_rule not in {"none","exhaustion_top16","return_over_vol"}:
            raise ValueError("Unknown selection rule")
        if self.rank_pool == 0 and self.selection_rule != "return_over_vol":
            raise ValueError("Whole-field feature ranking requires an explicit selection rule")
        fields = {"none","ret3","close_location","jump_share","volume_ratio","efficiency","signed_volume_ratio"}
        if self.feature_rule not in fields or self.secondary_rule not in fields:
            raise ValueError("Unknown feature")
        if self.feature_direction not in {"low","high"} or self.secondary_direction not in {"low","high"}:
            raise ValueError("Unknown feature direction")
        for rule,cut in ((self.feature_rule,self.feature_cut),(self.secondary_rule,self.secondary_cut),
                         ("width" if self.sizing == "width" else "none",self.width_cut)):
            if rule != "none" and (cut is None or not math.isfinite(cut)):
                raise ValueError("Active rule needs a finite cutoff")
        if not math.isfinite(self.ticket) or self.ticket <= 0:
            raise ValueError("Ticket must be positive and finite")
        if self.portfolio_rule not in {"none","underwater_inventory"}:
            raise ValueError("Unknown portfolio rule")
        if self.portfolio_rule != "none" and self.protection != "none":
            raise ValueError("Inventory sizing currently supports fixed-backstop positions only")


PARENT = Spec("PARENT")


def correlation_caps(histories, amounts, cap=8000.0, threshold=.75):
    """Connected components of highly correlated 20-return paths; cap each new batch cluster."""
    n = len(histories)
    parent = list(range(n))
    def find(i):
        while parent[i] != i:
            i = parent[i]
        return i
    for i in range(n):
        a = histories[i]
        if len(a) != 20 or any(x is None for x in a) or statistics.pstdev(a) == 0:
            continue
        for j in range(i):
            b = histories[j]
            if len(b) != 20 or any(x is None for x in b) or statistics.pstdev(b) == 0:
                continue
            if statistics.correlation(a,b) >= threshold:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    out = list(amounts)
    for ids in groups.values():
        total = sum(amounts[i] for i in ids)
        scale = min(1.0,cap/total) if total else 1.0
        for i in ids:
            out[i] *= scale
    return out


def risk_adjusted_selection(rows,features):
    eligible = [h for h in rows if features[h["symbol"]]["vol20"] is not None
                and features[h["symbol"]]["vol20"] > 0]
    if len(eligible) < 16:
        return []
    return sorted(eligible,key=lambda h:h["raw_return"]/features[h["symbol"]]["vol20"],reverse=True)[:8]


def protection_exit(entry, atr, checkpoints, arm=2.0, rebound=1.0, min_hold=3):
    """Only a later checkpoint can trigger; decision bar never supplies execution price."""
    if atr is None or not math.isfinite(atr) or atr <= 0:
        return None
    armed = False
    low = math.inf
    for hold_day, rec in checkpoints:
        if hold_day < min_hold or rec is None or rec["checkpoint"] is None:
            continue
        px = rec["checkpoint"]
        if armed and px >= low + rebound*atr and rec["next_ts"] is not None:
            decision = datetime.combine(date.fromisoformat(rec["next_ts"][:10]), time(15,55))
            execution = datetime.fromisoformat(rec["next_ts"]).replace(tzinfo=None)
            if execution < decision+timedelta(minutes=1):
                raise RuntimeError("Protection execution must follow decision bar")
            return rec["next_ts"], rec["next_open"], hold_day
        if px <= entry - arm*atr:
            armed = True
        if armed:
            low = min(low, px)
    return None


def minute_protection_path(job):
    """Causal all-minute comparator to daily 15:55 protection; one path per slot."""
    iso,symbol = job
    signal = date.fromisoformat(iso)
    fill_index = INDEX[signal]+1
    observations = []
    tape = []
    for hold_day in range(3,11):
        if fill_index+hold_day >= len(FEATS):
            break
        d = FEATS[fill_index+hold_day]
        path = session_bar_path(d,symbol)
        if not path.is_file():
            continue
        df = pl.read_parquet(path,columns=["bar_start","open","close","volume"])
        clock = pl.col("bar_start").dt.time()
        close = NYSE_EARLY_CLOSE.get(d,time(16))
        df = df.filter((clock >= time(9,30)) & (clock < close) & (pl.col("volume") > 0)
                       & pl.col("open").is_finite() & pl.col("close").is_finite()).sort("bar_start")
        tape.extend((hold_day,rec) for rec in df.to_dicts())
    for (hold_day,rec),(_,nxt) in zip(tape,tape[1:]):
        if hold_day >= 10:
            break
        if nxt["bar_start"] <= rec["bar_start"]:
            raise RuntimeError("Non-increasing minute tape")
        observations.append({"hold_day":hold_day,"decision":rec["bar_start"].isoformat(),
                             "price":float(rec["close"]),"execution":nxt["bar_start"].isoformat(),
                             "fill":float(nxt["open"])})
    path = ROOT/"minute_paths"/(iso+"_"+hashlib.sha256(symbol.encode()).hexdigest()[:16]+".json")
    dump(path,observations)
    return iso,symbol,observations


def all_minute_exit(entry,atr,observations,arm=2.0,rebound=1.0,min_hold=3):
    if atr is None or not math.isfinite(atr) or atr <= 0:
        return None
    armed = False
    low = math.inf
    for rec in observations:
        if rec["hold_day"] < min_hold:
            continue
        px = rec["price"]
        if armed and px >= low+rebound*atr:
            if datetime.fromisoformat(rec["execution"]) < datetime.fromisoformat(rec["decision"])+timedelta(minutes=1):
                raise RuntimeError("Minute decision must precede execution")
            return rec["execution"],rec["fill"],rec["hold_day"]
        if px <= entry-arm*atr:
            armed = True
        if armed:
            low = min(low,px)
    return None


def leg(trade, shares, exit_ts, exit_px):
    return {**trade, "shares": shares, "exit_ts": exit_ts, "exit_px": exit_px,
            "exit_date": exit_ts.date(),
            "pnl": signed_pnl(-1, shares, trade["entry_px"], exit_px)}


def metrics(trades, summaries, mode, intended, counters):
    """Ticket legs conserve entry costs. Exposure is EOD marked gross, including flat days."""
    sessions = SCORE  # full lifecycle chronology, NEVER slice alternate calendar days
    daily = [0.0]*len(sessions)
    gross = [0.0]*len(sessions)
    tickets = [set() for _ in sessions]
    symbols = [set() for _ in sessions]
    months = {d.strftime("%Y-%m"): 0.0 for d in sessions
              if mode == "ALL" or d.month % 2 == (mode == "IS")}
    month_days = Counter(d.strftime("%Y-%m") for d in sessions
                         if mode == "ALL" or d.month % 2 == (mode == "IS"))
    ticket_pnl = defaultdict(float)
    borrow_base = 0.0
    for t in trades:
        months[t["signal"].strftime("%Y-%m")] += t["pnl"]
        ticket_pnl[t["ticket_id"]] += t["pnl"]
        prev = t["entry_px"]
        for i,d in enumerate(sessions):
            if d < t["fill_date"] or d > t["exit_date"]:
                continue
            sh = t["shares"]
            rec = summaries.get((d.isoformat(), t["symbol"]))
            mark = rec["close"] if rec else prev
            if d == t["fill_date"]:
                daily[i] -= sh*cost_per_share(t["entry_px"])
            if d == t["exit_date"]:
                daily[i] += sh*(prev-t["exit_px"])-sh*cost_per_share(t["exit_px"])
            else:
                daily[i] += sh*(prev-mark)
                gross[i] += abs(sh*mark)
                tickets[i].add(t["ticket_id"])
                symbols[i].add(t["symbol"])
                nxt = sessions[i+1] if i+1 < len(sessions) else d
                borrow_base += abs(sh*mark)*(nxt-d).days/365.0
            prev = mark
    pnl = sum(ticket_pnl.values())
    if abs(sum(daily)-pnl) > 1e-6:
        raise AssertionError("Completed PnL and lifecycle MTM must reconcile")
    equity = peak = 0.0
    dd = 0.0
    for x in daily:
        equity += x
        peak = max(peak, equity)
        dd = min(dd, equity-peak)
    wins = [p for p in ticket_pnl.values() if p > 0]
    losses = [p for p in ticket_pnl.values() if p < 0]
    reds = [p for p in months.values() if p < 0]
    avg = statistics.mean(gross)
    mtm_months = defaultdict(float)
    for d,p in zip(sessions,daily):
        mtm_months[d.strftime("%Y-%m")] += p
    return {"total_pnl": pnl, "per_day": pnl/sum(month_days.values()),
            "sessions": sum(month_days.values()), "trades": len(ticket_pnl), "exit_legs": len(trades),
            "hit_rate": len(wins)/len(ticket_pnl) if ticket_pnl else 0,
            "profit_factor": sum(wins)/-sum(losses) if losses else None,
            "max_dd": dd, "worst_day": min(daily), "red_months": len(reds),
            "red_loss_sum": sum(reds), "worst_month": min(months.values()),
            "best_month_concentration": max(months.values())/pnl if pnl > 0 else None,
            "months": months, "month_per_day": {m:p/month_days[m] for m,p in months.items()},
            "avg_exposure": avg, "peak_exposure": max(gross),
            "mean_live_tickets": statistics.mean(len(x) for x in tickets),
            "peak_live_tickets": max(len(x) for x in tickets),
            "mean_live_symbols": statistics.mean(len(x) for x in symbols),
            "peak_live_symbols": max(len(x) for x in symbols),
            "intended_notional": intended, "profit_per_avg_exposure": pnl/avg if avg else None,
            "borrow_sensitivity": {str(r):pnl-r*borrow_base for r in (0,.1,.3)},
            "monthly_mtm": dict(mtm_months), "daily": daily, "gross": gross,
            "counters": dict(counters)}


def score(spec, mode, ranks, summaries):
    if mode != "IS":
        manifest = authorize(mode)
        allowed = [x["spec"] for x in manifest["finalists"]] + manifest["controls"]
        if asdict(spec) not in allowed:
            raise RuntimeError("Candidate is not in frozen manifest")
        if mode == "OOS":
            if not (ROOT/"oos_started.json").exists() or (ROOT/"oos_complete.json").exists():
                raise RuntimeError("OOS scorer must run inside the single active confirmation pass")
            if (ROOT/"results"/(spec.id+"_OOS.json")).exists():
                raise RuntimeError("Frozen OOS book already scored")
    days = signal_dates(mode, spec.schedule)
    assert_signals(days, mode)
    trades = []
    reservations = []
    counts = Counter()
    intended = 0.0
    weekly_counts = Counter(d.isocalendar()[:2] for d in FEATS)
    for d in days:
        rows = ranks[d.isoformat()]["rows"]
        if len(rows) < 8:
            continue
        scheduled_base = spec.ticket
        if spec.schedule == "daily":
            scheduled_base = 32000.0/weekly_counts[d.isocalendar()[:2]]/8
        if spec.sizing == "width" and rows[0]["raw_return"]-rows[7]["raw_return"] < spec.width_cut:
            scheduled_base *= .5
        counts["scheduled_batch_notional"] += scheduled_base*8
        fill_d = FEATS[INDEX[d]+1]
        end_i = INDEX[d]+11
        if end_i >= len(FEATS):
            counts["off_end_slots"] += 8
            continue
        end_d = FEATS[end_i]
        picks = rows if spec.rank_pool == 0 else rows[:spec.rank_pool]
        features = {}
        if spec.sizing == "inverse_vol" or spec.protection != "none" or spec.feature_rule != "none" or spec.secondary_rule != "none" or spec.selection_rule != "none":
            for h in picks:
                hist = [summaries.get((x.isoformat(),h["symbol"]))
                        for x in FEATS[INDEX[d]-20:INDEX[d]+1]]
                features[h["symbol"]] = history_features(hist)
        selection_rows = rows
        if spec.selection_rule == "exhaustion_top16":
            def quality(h):
                f = features[h["symbol"]]
                return sum(.5 if f[k] is None else float(f[k] <= cut)
                           for k,cut in (("ret3",0.0),("volume_ratio",1.0)))
            selection_rows = sorted(picks,key=quality,reverse=True)[:8]
            picks = selection_rows
        elif spec.selection_rule == "return_over_vol":
            counts["missing_ranking_vol"] += sum(features[h["symbol"]]["vol20"] is None
                                                 or features[h["symbol"]]["vol20"] <= 0 for h in picks)
            selection_rows = risk_adjusted_selection(picks,features)
            picks = selection_rows
            if not picks:
                counts["thin_risk_rank"] += 1
                continue
        base = scheduled_base
        if spec.portfolio_rule == "underwater_inventory":
            unrealized = 0.0
            for t in reservations:
                if t["fill_date"] <= d < t["end"]:
                    rec = summaries.get((d.isoformat(),t["symbol"]))
                    # Prior marks carried if today's observation is unavailable.
                    if rec is None:
                        for x in reversed(FEATS[INDEX[t["fill_date"]]:INDEX[d]]):
                            rec = summaries.get((x.isoformat(),t["symbol"]))
                            if rec:
                                break
                    mark = rec["close"] if rec else t["entry"]
                    unrealized += t["shares"]*(t["entry"]-mark)
            if unrealized < 0:
                base *= .5
                counts["underwater_batches_halved"] += 1
        weights = [base]*8
        if spec.sizing == "inverse_vol":
            vols = [features[h["symbol"]]["vol20"] for h in picks[:8]]
            counts["missing_vol_fallback"] += sum(v is None for v in vols)
            weights = bounded_inverse_vol(vols, base*8)
        if spec.cluster_cap is not None:
            histories = []
            for h in picks[:8]:
                hist = [summaries.get((x.isoformat(),h["symbol"]))
                        for x in FEATS[INDEX[d]-20:INDEX[d]+1]]
                histories.append([b["close"]/a["close"]-1 if a and b and a["close"] > 0 else None
                                  for a,b in zip(hist,hist[1:])])
            weights = correlation_caps(histories,weights,spec.cluster_cap,spec.cluster_correlation)
        reservations = [r for r in reservations if r["end"] > fill_d]
        slots = 0
        budget_left = base*8
        # Fixed signal ranking; only no-capacity slots may walk beyond first eight.
        for rank,h in enumerate(selection_rows):
            if slots >= 8 or budget_left < 1:
                break
            if rank >= 8 and not spec.substitute:
                break
            sym = h["symbol"]
            if (fill_d.isoformat(),sym) not in summaries:
                # Rare deep substitution: sequential dependency on live cap state is
                # the reason for this bounded lazy read, not a universe/rank cap.
                for x in FEATS[INDEX[fill_d]:end_i+1]:
                    key = (x.isoformat(),sym)
                    if key not in summaries:
                        summaries[key] = tape_summary(session_bar_path(x,sym),x)
            amount = weights[min(rank,7)] if not spec.substitute else min(base,budget_left)
            if spec.feature_rule != "none":
                f = features[sym]
                value = f.get(spec.feature_rule)
                if value is None:
                    counts["missing_feature_neutral"] += 1
                elif ((value < spec.feature_cut) if spec.feature_direction == "high" else (value > spec.feature_cut)):
                    amount *= spec.feature_low_size
            if spec.secondary_rule != "none":
                value = features[sym].get(spec.secondary_rule)
                if value is None:
                    counts["missing_secondary_neutral"] += 1
                elif ((value < spec.secondary_cut) if spec.secondary_direction == "high" else (value > spec.secondary_cut)):
                    amount *= .5
            ent = summaries.get((fill_d.isoformat(),sym))
            if spec.entry_confirmation and ent:
                # Do not apply a fill-day state if inherited fallback fill predates checkpoint.
                if ent["checkpoint"] is None or datetime.fromisoformat(ent["ts"]).time() < time(15,56):
                    counts["entry_confirmation_missing_neutral"] += 1
                elif ent["checkpoint"] >= h["now"][1]:
                    amount *= .5
                    counts["entry_unconfirmed_halved"] += 1
            if spec.cap is not None:
                used = sum(r["value"] for r in reservations if r["symbol"] == sym)
                amount = min(amount,max(0.0,spec.cap-used))
                if amount < (ent["close"] if ent else 1.0):
                    counts["cap_zero"] += 1
                    if not spec.substitute:
                        slots += 1
                    continue
            slots += 1
            intended += amount
            budget_left -= amount
            if not ent:
                counts["missing_fill"] += 1
                continue
            # Execution-value cap includes existing marks; never uses exit-day future outcomes.
            if spec.account_cap is not None:
                used = 0.0
                for r in reservations:
                    mark = summaries.get((fill_d.isoformat(),r["symbol"]))
                    used += r["shares"]*(mark["close"] if mark else r["entry"])
                amount = min(amount,max(0.0,spec.account_cap-used))
            ex = summaries.get((end_d.isoformat(),sym))
            # Reserve filled tickets even when their eventual missing exit excludes economic scoring.
            target = ex if ex else ent
            tr = _short_n(h, (datetime.fromisoformat(ent["ts"]),ent["close"]),
                          (datetime.fromisoformat(target["ts"]),target["close"]), "nextrth",amount)
            if tr is None:
                counts["borrow_or_size_skip"] += 1
                continue
            reservations.append({"symbol":sym,"value":tr["shares"]*tr["entry_px"],
                                 "shares":tr["shares"],"entry":tr["entry_px"],"end":end_d,"fill_date":fill_d})
            if ex is None:
                counts["missing_exit_drop"] += 1
                continue
            tr.update(signal=d,fill_date=fill_d,exit_date=end_d,ticket_id=f"{d}/{sym}",ticket=amount)
            if spec.protection != "none":
                atr = features[sym]["atr20"]
                counts["missing_atr_inert"] += atr is None
                checkpoints = [(j,summaries.get((FEATS[INDEX[fill_d]+j].isoformat(),sym)))
                               for j in range(1,10)]
                early = protection_exit(tr["entry_px"],atr,checkpoints,spec.arm_atr,spec.rebound_atr,spec.min_hold)
                if spec.protection_clock == "all_minutes":
                    early = all_minute_exit(tr["entry_px"],atr,summaries[(d.isoformat(),sym,"minute_path")],
                                            spec.arm_atr,spec.rebound_atr,spec.min_hold)
                if early:
                    ts,px,hd = early
                    qty = tr["shares"] if spec.protection == "full" else tr["shares"]//2
                    if qty:
                        trades.append(leg(tr,qty,datetime.fromisoformat(ts),px))
                        counts["early_tickets"] += 1
                        execution_day = date.fromisoformat(ts[:10])
                        counts["released_entry_dollar_sessions"] += qty*tr["entry_px"]*(INDEX[end_d]-INDEX[execution_day])
                        if qty < tr["shares"]:
                            trades.append(leg(tr,tr["shares"]-qty,tr["exit_ts"],tr["exit_px"]))
                        continue
            trades.append(tr)
    if spec.recycle:
        from research.cg_arrow002_recycle import recycle_slots
        trades,extra,rcounts = recycle_slots(spec,mode,ranks,summaries,trades)
        intended += extra
        counts.update(rcounts)
    result = metrics(trades,summaries,mode,intended,counts)
    if mode == "IS":
        result.pop("borrow_sensitivity")  # not an IS optimization input
    return result,trades


def data_for_specs(specs, mode, workers=8):
    authorize(mode)
    ranks_by = {}
    needs = set()
    for schedule in sorted({s.schedule for s in specs}):
        path = ROOT / f"ranks_{mode}_{schedule}.json"
        ranks = read(path) if path.exists() else prepare(mode,schedule,workers)
        assert_signals([date.fromisoformat(d) for d in ranks],mode)
        ranks_by[schedule] = ranks
        # All substitute rankings are retained; only top 32 history/lifecycle prefetched.
        # Additional substitute candidates are requested lazily before scoring if necessary.
        for iso, rec in ranks.items():
            d = date.fromisoformat(iso)
            schedule_specs = [s for s in specs if s.schedule == schedule]
            whole_field = any(s.rank_pool == 0 for s in schedule_specs)
            n = len(rec["rows"]) if whole_field else max(32 if any(s.substitute for s in schedule_specs) else 8,
                                                        max(s.rank_pool for s in schedule_specs))
            for h in rec["rows"][:n]:
                last = INDEX[d]+1 if whole_field else INDEX[d]+12
                for x in FEATS[max(0,INDEX[d]-20):min(len(FEATS),last)]:
                    needs.add((x.isoformat(),h["symbol"]))
            if whole_field:
                regular = [s for s in schedule_specs if s.rank_pool != 0]
                if regular:
                    regular_n = max(32 if any(s.substitute for s in regular) else 8,
                                    max(s.rank_pool for s in regular))
                    for h in rec["rows"][:regular_n]:
                        for x in FEATS[INDEX[d]+1:min(len(FEATS),INDEX[d]+12)]:
                            needs.add((x.isoformat(),h["symbol"]))
    summaries = load_summaries(needs,workers)
    risk_lifecycle_needs = set()
    for spec in specs:
        if spec.selection_rule == "return_over_vol":
            for iso,rec in ranks_by[spec.schedule].items():
                d = date.fromisoformat(iso)
                fs = {h["symbol"]:history_features([summaries.get((x.isoformat(),h["symbol"]))
                        for x in FEATS[INDEX[d]-20:INDEX[d]+1]]) for h in rec["rows"]}
                for h in risk_adjusted_selection(rec["rows"],fs):
                    for x in FEATS[INDEX[d]+1:min(len(FEATS),INDEX[d]+12)]:
                        risk_lifecycle_needs.add((x.isoformat(),h["symbol"]))
    if risk_lifecycle_needs:
        summaries.update(load_summaries(risk_lifecycle_needs,workers))
    minute_jobs = set()
    for spec in specs:
        if spec.protection_clock == "all_minutes":
            for iso,rec in ranks_by[spec.schedule].items():
                for h in rec["rows"][:spec.rank_pool]:
                    minute_jobs.add((iso,h["symbol"]))
    if minute_jobs:
        start = timer.monotonic()
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for n,(iso,sym,path) in enumerate(pool.map(minute_protection_path,sorted(minute_jobs)),1):
                summaries[(iso,sym,"minute_path")] = path
                if n % 32 == 0 or n == len(minute_jobs):
                    elapsed = timer.monotonic()-start
                    print(f"{stamp()} minute lifecycles {n}/{len(minute_jobs)} elapsed={elapsed:.1f}s "
                          f"ETA~{elapsed/n*(len(minute_jobs)-n):.1f}s",flush=True)
    return ranks_by,summaries


def is_run(specs, workers=8, verify_existing=False):
    authorize("IS")
    start = timer.monotonic()
    ranks, summaries = data_for_specs(specs,"IS",workers)
    results = {}
    identity = hashlib.sha256(json.dumps(code_identity(),sort_keys=True).encode()).hexdigest()
    for spec in specs:
        s = timer.monotonic()
        m,trades = score(spec,"IS",ranks[spec.schedule],summaries)
        path = ROOT / "results" / (spec.id+"_IS.json")
        old = read(path) if path.exists() else None
        if verify_existing and old is not None:
            fields = ["total_pnl","max_dd","worst_day","avg_exposure","peak_exposure","trades"]
            mismatch = {k:(old["metrics"][k],m[k]) for k in fields if abs(old["metrics"][k]-m[k]) > 1e-7}
            if mismatch:
                raise RuntimeError(f"Unexplained IS replay drift in {spec.id}: {mismatch}")
        results[spec.id] = {"spec":asdict(spec),"metrics":m,"timestamp":stamp(),
                            "first_timestamp":old.get("first_timestamp",old["timestamp"]) if old else stamp(),
                            "score_seconds":timer.monotonic()-s,"engine_state_sha256":identity,
                            "replay_count":old.get("replay_count",1)+1 if old else 1}
        dump(path,results[spec.id])
        print(f"{spec.id}: IS total={m['total_pnl']:.2f} day={m['per_day']:.2f} "
              f"red={m['red_months']} DD={m['max_dd']:.2f} peak={m['peak_exposure']:.2f} "
              f"n={m['trades']} {dict(m['counters'])}",flush=True)
    print(f"{stamp()} IS block completed {len(specs)} books in {timer.monotonic()-start:.1f}s",flush=True)
    return results


def inherited_trade_job(job):
    iso, h = job
    return _make_trade(h,"nextrth",4000.0,False,date.fromisoformat(iso),FEATS,hold=10)[0]


def validate_parent(workers=8):
    authorize("IS")
    ranks,summaries = data_for_specs([PARENT],"IS",workers)
    m,trades = score(PARENT,"IS",ranks["wed"],summaries)
    jobs = [(iso,h) for iso,rec in ranks["wed"].items() for h in rec["rows"][:8]]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        legacy = [t for t in pool.map(inherited_trade_job,jobs) if t is not None]
    key = lambda t:(t["signal"],t["symbol"])
    actual = {key(t):t for t in trades}
    expected = {key(t):t for t in legacy}
    if actual.keys() != expected.keys():
        raise AssertionError("Parent selected/completed ticket identities differ")
    for k,t in actual.items():
        for field in ("entry_ts","exit_ts","entry_px","exit_px","shares","pnl"):
            if t[field] != expected[k][field]:
                raise AssertionError(f"Parent differs in {field}")
    last_map = {k:v["close"] for k,v in summaries.items() if v is not None}
    daily,peak = _mtm_and_peak(legacy,SCORE,last_map)
    if max(abs(a-b) for a,b in zip(daily,m["daily"])) > 1e-7 or abs(peak-m["peak_exposure"]) > 1e-7:
        raise AssertionError("Parent lifecycle MTM differs from inherited accounting")
    out = {"status":"PASS","timestamp":stamp(),"signal_cohort":"IS only",
           "inherited_trades":len(legacy),"max_daily_difference":max(abs(a-b) for a,b in zip(daily,m["daily"])),
           "peak_difference":peak-m["peak_exposure"],"metrics":public_metrics(m)}
    dump(REPORTS/"cg_arrow002_parent_validation.json",out)
    dump(ROOT/"results"/"PARENT_IS.json",{"spec":asdict(PARENT),"metrics":m,"timestamp":stamp(),"score_seconds":0})
    print(json.dumps(out,indent=2),flush=True)


def public_metrics(m):
    return {k:v for k,v in m.items() if k not in {"daily","gross"}}


def compare(m, parent):
    """Transparent guard, not an optimization score. Five-percent materiality predeclared."""
    changes = {
        "red_months": m["red_months"] < parent["red_months"],
        **{k:m[k] > parent[k]+1e-6 for k in ("red_loss_sum","worst_month","max_dd","worst_day")},
        "best_month_concentration": m["best_month_concentration"] is not None
            and parent["best_month_concentration"] is not None
            and m["best_month_concentration"] < parent["best_month_concentration"]-1e-6}
    acceptable = (m["red_months"] <= parent["red_months"]
                  and all(m[k] >= parent[k]-abs(parent[k])*.05-1e-6
                          for k in ("red_loss_sum","worst_month","max_dd","worst_day"))
                  and m["best_month_concentration"] is not None
                  and parent["best_month_concentration"] is not None
                  and m["best_month_concentration"] <= parent["best_month_concentration"]+.05)
    strict = (m["total_pnl"] > parent["total_pnl"] and sum(changes.values()) >= 2
              and acceptable and m["peak_exposure"] <= CEILING)
    confirmation = (m["total_pnl"] > parent["total_pnl"] and sum(changes.values()) >= 2
                    and m["peak_exposure"] <= CEILING
                    and m["profit_per_avg_exposure"] > parent["profit_per_avg_exposure"])
    return {"strict_dual":strict,"improved":changes,"no_material_worsening":acceptable,
            "confirmation_numeric_gate":confirmation}


def freeze_finalists(ids, controls=None, reasons=None):
    authorize("IS")
    if len(ids) > 5 or not ids or len(set(ids)) != len(ids):
        raise ValueError("Freeze needs one to five distinct justified finalists")
    records = [read(ROOT/"results"/(i+"_IS.json")) for i in ids]
    parent = read(ROOT/"results"/"PARENT_IS.json")
    state = code_identity()
    state_digest = hashlib.sha256(json.dumps(state,sort_keys=True).encode()).hexdigest()
    for r in records+[parent]:
        if r.get("engine_state_sha256") != state_digest:
            raise RuntimeError("Finalists and parent need exact IS replay under the final code state")
    manifest = {"status":"FROZEN","timestamp":stamp(),"session_start":START,
                "git_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO_ROOT,text=True).strip(),
                "code_sha256":state,"engine_state_sha256":state_digest,"corporate_action_caveat":CAVEAT,
                "firewall":"No new OOS signal-cohort performance has been scored or inspected in this arrow.",
                "common_rules":{
                    "universe":"Inherited point-in-time common-stock field, prior close $10-$80, prior dollar volume >=$10M, inherited ETP exclusions; no name cap",
                    "rank":"15-session raw close return, descending stable inherited eligibility tie order; minimum 16 rankable names, top eight",
                    "entry":"Next session last tradable regular-hours minute close; integer floor(intended/price); inherited borrow_blocks_short proxy",
                    "backstop":"ten NYSE sessions after fill, last regular-hours minute close; missing exits dropped as inherited; no terminal forced liquidation",
                    "features":"Minute-derived RTH daily observations known by signal close. Vol20/ATR20/volume ratio require 21 consecutive sessions (20 sample returns, 20 arithmetic true ranges, prior20 mean volume excluding signal). ret3 needs four closes, jump share needs sixteen, close-location and signed-volume need only signal session. Missing volatility median-selected fallback, missing ATR inert, other missing features neutral",
                    "protection":"daily_1555: 15:55 minute close known 15:56, next traded minute open >=15:56. all_minutes: every tradable minute CLOSE on hold days3..9, subsequent traded minute OPEN including next session if necessary. Both: no arm before min_hold, arm >=arm_atr favorable, subsequent checkpoint rebound >=rebound_atr, one-time full or floor(shares/2) cover. RTH clipped to actual early closes; fixed H10 backstop unchanged",
                    "capital":"No parent global leverage limiter. Candidate cap values in spec, symbol cap uses actual aggregate entry value; missing-exit positions reserve until scheduled expiry; same-day scheduled exits before new close entries. EOD peak ceiling 102922; $100k fit measured, not presumed",
                    "daily_weekly_budget":"$32000 / actual NYSE sessions of full ISO week / eight; no reallocation from out-of-cohort days",
                    "costs":"Each share/side: $0.005 commission + max($0.01,0.001*execution_price); stock-loan/dividends absent; raw fixed shares",
                    "feature_sizing":"feature_direction=high favors values >=cut; low favors <=cut; disfavored feature receives feature_low_size times normal ticket, missing neutral. underwater_inventory halves base if existing live shares show negative aggregate unrealized price PnL at signal close. entry_confirmation halves if next-session 15:55 checkpoint >= signal close, only when inherited fill >=15:56; missing checkpoint neutral. Numerical spec fields are complete.",
                    "secondary_sizing":"Independent secondary feature applies a multiplicative half-size penalty when disfavored; missing neutral. Integer shares floored only after all penalties and capital clips.",
                    "recycling":"D6 only: completed R8 full-minute protection; first 15:55 checkpoint after cover with >=3 sessions to original H10 expiry; strongest current checkpoint top8 within $8k symbol entry-value and $100k marked account capacity; next traded minute open >=15:56, max min($4k,freed exit-market-value); reserve scheduled primary orders at known $4k and same-checkpoint replacement orders at intended dollars; one replacement, no new protection, original expiry. All filled slots are simulated causally including missing-H10 shadows; only common parent-complete-backstop roots and children enter economic metrics. Original SIGNAL month remains cohort owner, including cross-calendar lifecycle decisions.",
                    "metrics":"Completed PnL by signal month; continuous daily MTM throughout lifecycle on 251-day calendar; EOD gross and live counts include flat days; half-exit legs count one ticket",
                    "materiality":"Strict dual: higher PnL, >=2 of six smoothness improve; no extra red month, monetary downside no worse >5%, best-month concentration no worse >0.05 absolute; peak <=102922"},
                "controls":[asdict(PARENT)]+[asdict(s) for s in (controls or [])],
                "parent_is":public_metrics(parent["metrics"]),
                "finalists":[{"id":r["spec"]["id"],"spec":asdict(Spec(**r["spec"])),
                               "is_metrics":public_metrics(r["metrics"]),
                               "comparison":compare(r["metrics"],parent["metrics"]),
                               "reason":(reasons or {}).get(r["spec"]["id"],"See pre-OOS Pareto board and selection rationale in ledger")}
                              for r in records]}
    dump(FREEZE,manifest)
    print(f"{stamp()} FROZEN {ids}; manifest SHA256={digest(FREEZE)}",flush=True)


def confirmation(workers=8):
    manifest = authorize("OOS")
    identity = digest(FREEZE)
    started = ROOT/"oos_started.json"
    if started.exists():
        if read(started)["freeze_sha256"] != identity:
            raise RuntimeError("Cannot resume a different freeze")
        if (ROOT/"oos_complete.json").exists():
            raise RuntimeError("The single OOS pass is complete; rerun forbidden")
        print("Resuming identical frozen pass; completed books will not be rescored",flush=True)
    else:
        dump(started,{"timestamp":stamp(),"freeze_sha256":identity})
    specs = [Spec(**s) for s in manifest["controls"]] + [Spec(**r["spec"]) for r in manifest["finalists"]]
    ranks,summaries = data_for_specs(specs,"OOS",workers)
    for spec in specs:
        path = ROOT/"results"/(spec.id+"_OOS.json")
        if path.exists():
            old = read(path)
            if old.get("freeze_sha256") != identity:
                raise RuntimeError("Mismatched OOS checkpoint")
            continue
        start = timer.monotonic()
        m,_ = score(spec,"OOS",ranks[spec.schedule],summaries)
        dump(path,{"spec":asdict(spec),"metrics":m,"timestamp":stamp(),
                   "score_seconds":timer.monotonic()-start,"freeze_sha256":identity})
        print(f"{stamp()} OOS {spec.id}: total={m['total_pnl']:.2f}, day={m['per_day']:.2f}, "
              f"DD={m['max_dd']:.2f}, peak={m['peak_exposure']:.2f}",flush=True)
    dump(ROOT/"oos_complete.json",{"timestamp":stamp(),"freeze_sha256":identity,
                                  "books":[s.id for s in specs]})


def investor(workers=8):
    manifest = authorize("ALL")
    specs = [Spec(**s) for s in manifest["controls"]] + [Spec(**r["spec"]) for r in manifest["finalists"]]
    # No fresh signal calculation: union the already cached, frozen cohort rankings.
    for schedule in {s.schedule for s in specs}:
        a = read(ROOT/f"ranks_IS_{schedule}.json")
        b = read(ROOT/f"ranks_OOS_{schedule}.json")
        if set(a)&set(b):
            raise RuntimeError("Cohort overlap")
        dump(ROOT/f"ranks_ALL_{schedule}.json",{**a,**b})
    ranks,summaries = data_for_specs(specs,"ALL",workers)
    for spec in specs:
        m,_ = score(spec,"ALL",ranks[spec.schedule],summaries)
        dump(ROOT/"results"/(spec.id+"_ALL.json"),
             {"spec":asdict(spec),"metrics":m,"timestamp":stamp(),"freeze_sha256":digest(FREEZE)})
        print(f"{stamp()} investor {spec.id}: total={m['total_pnl']:.2f}, day={m['per_day']:.2f}, "
              f"DD={m['max_dd']:.2f}, peak={m['peak_exposure']:.2f}",flush=True)
        if spec == PARENT:
            expected = {"total_pnl":51855.71,"max_dd":-20033.68,"worst_day":-6607.31,
                        "peak_exposure":102922,"trades":376}
            for k,v in expected.items():
                tolerance = .51 if k == "peak_exposure" else .011
                if abs(m[k]-v) > tolerance:
                    raise AssertionError(f"Parent reproduction mismatch in {k}: {m[k]} vs {v}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action",choices=["prepare","score","recheck","validate","confirm","investor"])
    p.add_argument("--schedule",choices=["wed","daily"],default="wed")
    p.add_argument("--specs",type=Path)
    p.add_argument("--workers",type=int,default=8)
    args = p.parse_args()
    if args.action == "prepare":
        prepare("IS",args.schedule,args.workers)
    elif args.action == "score":
        specs = [Spec(**s) for s in read(args.specs)] if args.specs else [PARENT]
        is_run(specs,args.workers)
    elif args.action == "recheck":
        specs = [Spec(**read(p)["spec"]) for p in sorted((ROOT/"results").glob("*_IS.json"))]
        is_run(specs,args.workers,verify_existing=True)
    elif args.action == "confirm":
        confirmation(args.workers)
    elif args.action == "validate":
        validate_parent(args.workers)
    else:
        investor(args.workers)


if __name__ == "__main__":
    main()
