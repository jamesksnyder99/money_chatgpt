"""Arrow 003: bounded R4/R5 continuation, common live-inventory accounting.

Signal ownership is odd/even month. Every cohort is valued on the uninterrupted
calendar; the all-signal capital replay is distinct from isolated cohort books.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
import json
import math
import random
import statistics
import subprocess
import time as timer

from ingest.paths import REPO_ROOT, REPORTS
from research.book import borrow_blocks_short
from research.costs import cost_per_share, spread_proxy
from research.cg_arrow003_data import (
    ROOT, OLD, SCORE, FEATS, INDEX, SCHEMA, stamp, dump, read, digest,
    data_for, features, checkpoint_ratio,
    CONVENTION, ACTION_PATH, adjustment_factor, history_asof, adjusted_record,
    minute_observations,
)

FREEZE = REPORTS / "cg_arrow003_freeze.json"
LEDGER = REPORTS / "cg_arrow003_ledger.jsonl"
MATERIALITY = {"profit_relative":0.05,"downside_relative":0.05,
               "ride_improvement":0.10,"ride_profit_retention":0.85,
               "return_risk_tolerance":0.20,"gross_planning":130000.0}
SCENARIOS = {"baseline":"$0.005/share commission plus max($0.01, 0.001*price) each side",
             "borrow_annual_rates":[0.0,0.1,0.3],"spread_multipliers":[1.0,2.0],
             "borrow_clock":"calendar days, preceding end-of-day marked gross / 365",
             "dividends_locate_financing":"unknown; not fabricated"}


def elapsed():
    s = read(ROOT / "state.json")
    wall = (datetime.now(timezone.utc)-datetime.fromisoformat(s["start_utc"])).total_seconds()
    mono = timer.monotonic()-s["start_monotonic"]
    return max(wall, mono) if mono >= 0 else wall


def code_identity():
    paths = read(REPORTS / "cg_arrow003_dependencies.json")["paths"]
    return {p:digest(REPO_ROOT/p) for p in paths}


def input_identity():
    paths = [OLD/f"ranks_{s}_wed.json" for s in ("IS","OOS")]
    paths += [REPO_ROOT/"data/ref/splits.parquet"]
    paths += [ACTION_PATH]
    paths += [REPO_ROOT/p for p in ("data/virgin/manifest.parquet","data/full/manifest.parquet",
              "data/virgin/eligibility.parquet","data/full/eligibility.parquet","data/ref/symbols_common.parquet")]
    return {p.relative_to(REPO_ROOT).as_posix():digest(p) for p in paths}


def authorize(mode):
    if mode not in {"IS","OOS","ALL"}:
        raise ValueError("Unknown cohort")
    if mode=="IS":
        if FREEZE.exists() or (ROOT/"oos_started.json").exists():
            raise RuntimeError("IS research is closed")
        return None
    if not FREEZE.exists():
        raise RuntimeError("Committed freeze required before confirmation")
    f = read(FREEZE)
    if f.get("status")!="FROZEN" or f.get("code_sha256")!=code_identity():
        raise RuntimeError("Frozen strategy identity changed")
    if f.get("input_sha256")!=input_identity():
        raise RuntimeError("Frozen input identity changed")
    if elapsed()<135*60:
        raise RuntimeError("No new OOS before minute 135")
    rel = FREEZE.relative_to(REPO_ROOT).as_posix()
    try:
        committed = subprocess.check_output(["git","show",f"HEAD:{rel}"],cwd=REPO_ROOT)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("Freeze must be committed") from exc
    if committed != FREEZE.read_bytes():
        raise RuntimeError("Freeze must be committed unchanged")
    paths=list(f["code_sha256"])
    # Git's content comparison respects checkout newline conventions; raw runtime
    # bytes are independently fixed by the SHA-256 identity above.
    tracked=subprocess.run(["git","ls-files","--error-unmatch","--",*paths],cwd=REPO_ROOT,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    clean=subprocess.run(["git","diff","--quiet","HEAD","--",*paths],cwd=REPO_ROOT)
    if tracked.returncode or clean.returncode:
        raise RuntimeError("Every frozen code dependency must be committed")
    if mode=="ALL" and not (ROOT/"oos_complete.json").exists():
        raise RuntimeError("Investor replay follows completed confirmation")
    if mode=="ALL" and read(ROOT/"oos_complete.json").get("freeze_sha256")!=digest(FREEZE):
        raise RuntimeError("Confirmation completion belongs to a different freeze")
    return f


@dataclass(frozen=True)
class Spec:
    id: str
    family: str = "R4"
    base: float = 5150.0
    origin: str = "DIRECTED"
    mechanism: str = "Volume-conditioned R4 sizing"
    control: str = "R4"
    volume: str = "mean"
    momentum: str = "switch"
    pacing: bool = False
    cover: str = "none"
    volume_power: float = .5
    penalty: float = .5
    min_hold: int = 3
    fade_atr: float = 1.0
    state: str = "none"
    state_cut: float = .05
    shuffle_seed: int | None = None
    scale: float = 1.0
    share_sizing: str = "fill"
    momentum_missing: str = "neutral"
    cover_clock: str = "checkpoint"
    cover_on_backstop: bool = False

    def __post_init__(self):
        import re
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", self.id):
            raise ValueError("Invalid policy id")
        if self.family not in {"PARENT","R4","R5","BLEND"}:
            raise ValueError("Unrelated family")
        if self.origin not in {"CONTROL","DIRECTED","ASTRA","DERIVED","DIAGNOSTIC"}:
            raise ValueError("Unknown origin")
        if self.volume not in {"mean","median","persistence","taper","entry_update","late_share","ordinal","two_day"}:
            raise ValueError("Unknown volume rule")
        if self.momentum not in {"switch","taper","none","votes"}:
            raise ValueError("Unknown momentum rule")
        if self.cover not in {"none","earned_fade","earned_rebound","low_participation"}:
            raise ValueError("Unknown cover rule")
        if self.state not in {"none","drawdown","symbol_budget","adverse_inventory"}:
            raise ValueError("Unknown account state rule")
        if self.share_sizing not in {"fill","preorder"}:
            raise ValueError("Unknown share-sizing convention")
        if self.momentum_missing not in {"neutral","original_switch"}:
            raise ValueError("Unknown momentum missing-history rule")
        if self.cover_clock not in {"checkpoint","all_minutes"}:
            raise ValueError("Unknown management clock")
        if self.cover_clock=="all_minutes" and self.cover not in {"low_participation","earned_rebound"}:
            raise ValueError("Minute clock requires a price/entry-state management rule")
        if not all(math.isfinite(x) and x>0 for x in (self.base,self.scale,self.volume_power,self.fade_atr)):
            raise ValueError("Nonpositive finite size/shape required")
        if not 0 < self.penalty <= 1 or self.min_hold < 1:
            raise ValueError("Invalid penalty/holding age")


CONTROLS = [
    Spec("PARENT",family="PARENT",base=4000,origin="CONTROL",control="PARENT",mechanism="Original constant $4000 tickets"),
    Spec("R4",origin="CONTROL",mechanism="$5150, half for above prior20 mean volume"),
    Spec("R5",family="R5",base=8300,origin="CONTROL",control="R5",mechanism="$8300, independently half for positive ret3 and above-mean volume"),
    Spec("A4",base=4000,origin="CONTROL",mechanism="Conservative R4 $4000/$2000"),
    Spec("R1",family="R5",base=4000,origin="CONTROL",control="R5",mechanism="Conservative R5 $4000/$2000/$1000"),
]


def valid(x):
    return x is not None and math.isfinite(x)


def volume_multiplier(spec, f, updated=None):
    key = {"median":"volume_median_ratio","persistence":"volume_persistence3",
           "late_share":"late_share_ratio"}.get(spec.volume,"volume_ratio")
    value = updated if spec.volume=="entry_update" and valid(updated) else f.get(key)
    if not valid(value) or value<=0:
        return 1.0
    if spec.volume=="taper":
        return max(.5,min(1.0,value**(-spec.volume_power)))
    if spec.volume=="two_day":
        prev = f.get("volume_previous_ratio")
        return spec.penalty if value>1 and valid(prev) and prev>1 else 1.0
    return spec.penalty if value>1 else 1.0


def momentum_multiplier(spec, f):
    r = f.get("ret3")
    if spec.momentum=="none" or not valid(r):
        return 1.0
    if spec.momentum=="votes":
        if spec.momentum_missing=="original_switch" and not valid(f.get("vol20")):
            return spec.penalty if r>0 else 1.0
        votes=f.get("positive_days3")
        return spec.penalty if valid(votes) and votes>=2 else 1.0
    if spec.momentum=="taper":
        vol = f.get("vol20")
        if valid(vol) and vol>0:
            return max(.5,min(1.0,1/(1+max(r,0)/(vol*math.sqrt(3)))))
        return (spec.penalty if r>0 else 1.0) if spec.momentum_missing=="original_switch" else 1.0
    return spec.penalty if r>0 else 1.0


def intended_amount(spec, f, updated=None):
    if spec.family=="PARENT":
        return spec.base*spec.scale
    v = volume_multiplier(spec,f,updated)
    m = momentum_multiplier(spec,f)
    if spec.family=="BLEND":
        return .5*(5150*v+8300*v*m)*spec.scale
    return spec.base*v*(m if spec.family=="R5" else 1)*spec.scale


def pro_rata(amounts, used, target=130000.0):
    if any(not math.isfinite(x) or x<0 for x in amounts) or not math.isfinite(used):
        raise ValueError("Invalid pacing inputs")
    total = sum(amounts)
    scale = min(1.0,max(0.0,target-used)/total) if total else 0.0
    return [x*scale for x in amounts], scale


def cover_trigger(spec, p, d, rec, summaries):
    if spec.cover=="none" or p["covered"] or INDEX[d]-p["fill_index"]<spec.min_hold:
        return False
    if not rec or not valid(rec.get("checkpoint")) or not valid(p["atr"]):
        return False
    cp = rec["checkpoint"]
    prev = history_asof(p["symbol"],[FEATS[INDEX[d]-1]],d,summaries)[0]
    ratio = checkpoint_ratio(d,p["symbol"],summaries)
    earned = p["entry"]-cp >= spec.fade_atr*p["atr"]
    bounce = bool(prev and cp>prev["close"])
    if spec.cover=="earned_rebound":
        return earned and bounce
    if spec.cover=="low_participation":
        return earned and bounce and valid(p["feature"].get("volume_ratio")) and p["feature"]["volume_ratio"]<=1
    return earned and bounce and valid(ratio) and ratio>1


def longest_run(values):
    best = cur = 0
    for value in values:
        cur = cur+1 if value else 0
        best = max(best,cur)
    return best


def cover_observation(spec,p,d,rec,summaries):
    if spec.cover_clock=="checkpoint":
        return rec if cover_trigger(spec,p,d,rec,summaries) else None
    if p["covered"] or INDEX[d]-p["fill_index"]<spec.min_hold or not valid(p["atr"]):
        return None
    if spec.cover=="low_participation":
        v=p["feature"].get("volume_ratio")
        if not valid(v) or v>1:return None
    prev=history_asof(p["symbol"],[FEATS[INDEX[d]-1]],d,summaries)[0]
    if not prev:return None
    for row in minute_observations(d.isoformat(),p["symbol"]):
        if p["entry"]-row["price"]>=spec.fade_atr*p["atr"] and row["price"]>prev["close"]:
            decision=datetime.fromisoformat(row["decision"])
            execution=datetime.fromisoformat(row["execution"])
            if execution<decision+timedelta(minutes=1):
                raise RuntimeError("Minute execution must follow completed decision bar")
            return {"next_ts":row["execution"],"next_open":row["fill"],"decision":row["decision"]}
    return None


def classify(m,c,*,calendar=False):
    if calendar:
        def account_view(x):
            out=dict(x)
            for key in ("red_months","red_loss_sum","worst_month","median_month"):
                out[key]=x["calendar_"+key]
            return out
        m,c=account_view(m),account_view(c)
    """One descriptive classifier for IS and confirmation; no gross-exposure veto."""
    fields = ("red_loss_sum","worst_month","max_dd","worst_day")
    improvement = {k:m[k]-c[k] for k in fields}
    rel = {k:(m[k]-c[k])/abs(c[k]) if c[k] else None for k in fields}
    retained = m["total_pnl"]/c["total_pnl"] if c["total_pnl"]>0 else None
    better = sum(x is not None and x>=MATERIALITY["downside_relative"] for x in rel.values())
    tolerable = all(x is None or x>=-MATERIALITY["downside_relative"] for x in rel.values())
    profit_gain = m["total_pnl"]-c["total_pnl"]
    meaningful = profit_gain>=max(100,abs(c["total_pnl"])*MATERIALITY["profit_relative"])
    if meaningful and better>=2 and tolerable and m["red_months"]<=c["red_months"]:
        label = "BALANCED"
    elif retained is not None and retained>=MATERIALITY["ride_profit_retention"] and better>=2 and tolerable:
        label = "RIDE-FIRST"
    elif meaningful and all(x is None or x>=-MATERIALITY["return_risk_tolerance"] for x in rel.values()):
        label = "RETURN-FIRST"
    else:
        label = "MIXED / NO MATERIAL PROGRESS"
    fields=("total_pnl","per_day","red_months","red_loss_sum","worst_month","median_month",
            "max_dd","max_dd_percent","worst_day","avg_exposure","p95_exposure","peak_exposure",
            "time_underwater_sessions","longest_underwater_sessions","above_130k_sessions",
            "exposure_dollar_days_above_130k","largest_symbol_gross","terminal_stale_gross")
    changes={k:{"candidate":m[k],"control":c[k],"difference":m[k]-c[k],
                "relative_change_abs_control":(m[k]-c[k])/abs(c[k]) if c[k] else None}
             for k in fields if k in m and k in c and m[k] is not None and c[k] is not None}
    return {"classification":label,"profit_difference":profit_gain,"profit_retention":retained,
            "downside_differences":improvement,"downside_relative":rel,
            "metric_changes":changes,"monthly_comparison_scope":"calendar account months" if calendar else "signal-cohort ownership; calendar account months reported separately",
            "return_risk_within_planning_tolerance":all(x is None or x>=-MATERIALITY["return_risk_tolerance"] for x in rel.values()),
            "exposure_difference":m["peak_exposure"]-c["peak_exposure"],
            "soft_exposure_auto_failure":False}


def score(spec, mode, ranks, summaries, *, check=True, stale_shock=None):
    if stale_shock is not None and (mode!="IS" or stale_shock not in {0.,.1,.5,1.}):
        raise ValueError("Stale-mark counterfactual is a fixed IS-only diagnostic")
    if check:
        manifest = authorize(mode)
        if mode!="IS" and asdict(spec) not in manifest["specs"]:
            raise RuntimeError("Unfrozen policy")
        if mode=="OOS":
            if not (ROOT/"oos_started.json").exists() or (ROOT/"oos_complete.json").exists():
                raise RuntimeError("OOS scorer requires the single active confirmation job")
            if (ROOT/"results"/f"{spec.id}_OOS.json").exists():
                raise RuntimeError("Frozen OOS policy has already completed")
    if any(mode!="ALL" and date.fromisoformat(d).month%2!=(mode=="IS") for d in ranks):
        raise RuntimeError("Signal-cohort firewall")
    entries = {}
    for iso, rec in ranks.items():
        d = date.fromisoformat(iso)
        if INDEX[d]+1<len(FEATS) and len(rec["rows"])>=8:
            entries[FEATS[INDEX[d]+1]]=(d,rec["rows"][:8])
    active = []
    positions = []
    legs = []
    daily = []
    counts = Counter()
    intended = 0.0
    equity = peak_equity = 100000.0
    cohort = {d.strftime("%Y-%m"):0.0 for d in SCORE if mode=="ALL" or d.month%2==(mode=="IS")}
    symbol_pnl = defaultdict(float)
    ticket_pnl = defaultdict(float)
    for day_i,d in enumerate(SCORE):
        # Share/price units change at the effective trading session, never before.
        for p in active:
            previous = FEATS[INDEX[d]-1]
            factor = adjustment_factor(p["symbol"],previous,d)
            if factor!=1:
                for key in ("shares","initial_shares"):
                    p[key] /= factor
                for key in ("entry","mark","last_observed_mark","entry_cost"):
                    p[key] *= factor
                if p["atr"] is not None:
                    p["atr"] *= factor
                counts["held_split_adjustments"] += 1
                counts["fractional_split_liabilities"] += p["shares"]%1!=0
        day = {"date":d.isoformat(),"pnl":0.0,"gross":0.0,"borrow_base":0.0,"extra_spread":0.0,
               "stale_gross":0.0,"tickets":0,"symbols":0,"largest_symbol_gross":0.0,
               "new_gross":0.0,"pacing_scale":1.0,"preorder_gross":0.0}
        def book(p, pnl):
            day["pnl"] += pnl
            cohort[p["signal"][:7]] += pnl
            symbol_pnl[p["symbol"]] += pnl
            ticket_pnl[p["id"]] += pnl
        def cover(p,q,px,ts,reason):
            if q<=0:
                return
            book(p,q*(p["mark"]-px)-q*cost_per_share(px))
            day["extra_spread"] += q*spread_proxy(px)
            pnl = q*(p["entry"]-px)-q*(p["entry_cost"]+cost_per_share(px))
            legs.append({"ticket_id":p["id"],"symbol":p["symbol"],"signal":p["signal"],
                         "entry_date":p["fill_date"],"entry_ts":p["entry_ts"],"entry":p["entry"],
                         "exit_ts":ts,"exit":px,"shares":q,"pnl":pnl,"reason":reason})
            p["shares"] -= q
        # Prior unfilled backstops execute only at a genuinely later available print.
        for p in active:
            rec = summaries.get((d.isoformat(),p["symbol"]))
            if p["due_index"]<INDEX[d] and rec and rec.get("first_ts"):
                cover(p,p["shares"],rec["open"],rec["first_ts"],"delayed_backstop")
                counts["delayed_exit_fills"] += 1
                counts["delayed_exit_sessions"] += INDEX[d]-p["due_index"]
        active = [p for p in active if p["shares"]]
        for p in active:
            rec = summaries.get((d.isoformat(),p["symbol"]))
            eligible_age=INDEX[d]<p["due_index"] or (spec.cover_on_backstop and INDEX[d]==p["due_index"])
            trigger=cover_observation(spec,p,d,rec,summaries) if eligible_age else None
            if trigger:
                if trigger.get("next_ts") and trigger.get("next_open"):
                    ts = datetime.fromisoformat(trigger["next_ts"])
                    if spec.cover_clock=="checkpoint" and ts.hour*60+ts.minute<15*60+56:
                        raise RuntimeError("Checkpoint fill must follow completed decision bar")
                    qty = min(p["initial_shares"]//2,p["shares"])
                    if qty>0:
                        cover(p,qty,trigger["next_open"],trigger["next_ts"],"half_cover")
                        p["covered"] = True
                        counts["half_covers"] += 1
                    else:
                        counts["zero_share_half_cover_attempts"] += 1
        active = [p for p in active if p["shares"]]
        # Pre-order state includes due-but-unfilled closing orders; no future exits
        # or future missing observations can manufacture current headroom.
        used = 0.0
        by_symbol = defaultdict(float)
        unrealized = 0.0
        for p in active:
            rec = summaries.get((d.isoformat(),p["symbol"]))
            mark = rec.get("preorder") if rec else None
            mark = mark if valid(mark) else (p["last_observed_mark"]*(1+stale_shock) if stale_shock is not None else p["mark"])
            used += p["shares"]*mark
            by_symbol[p["symbol"]] += p["shares"]*mark
            unrealized += p["shares"]*(p["entry"]-mark)
        day["preorder_gross"] = used
        proposals = []
        if d in entries:
            signal, picks = entries[d]
            fs = {h["symbol"]:features(history_asof(h["symbol"],
                  FEATS[max(0,INDEX[signal]-22):INDEX[signal]+1],signal,summaries)) for h in picks}
            amounts = []
            for h in picks:
                sym = h["symbol"]
                f = fs[sym]
                updated = checkpoint_ratio(d,sym,summaries) if spec.volume=="entry_update" else None
                counts["missing_volume_neutral"] += not valid(f.get("volume_ratio"))
                counts["missing_momentum_neutral"] += spec.family in {"R5","BLEND"} and not valid(f.get("ret3"))
                counts["entry_update_fallback"] += spec.volume=="entry_update" and not valid(updated)
                amount = intended_amount(spec,f,updated)
                amounts.append(amount)
            if spec.volume=="ordinal":
                available = [(i,fs[h["symbol"]].get("volume_ratio")) for i,h in enumerate(picks)]
                ranked = sorted((x for x in available if valid(x[1]) and x[1]>0),key=lambda x:x[1])
                # Bottom half of valid batch participation gets full volume size;
                # upper half gets half. Missing stays neutral, fixed ranking ties.
                high = {i for i,_ in ranked[(len(ranked)+1)//2:]}
                amounts = [spec.base*spec.scale*(spec.penalty if i in high else 1)*
                           (momentum_multiplier(spec,fs[h["symbol"]]) if spec.family=="R5" else 1)
                           for i,h in enumerate(picks)]
            if spec.shuffle_seed is not None:
                random.Random(f"{spec.shuffle_seed}/{signal}").shuffle(amounts)
            if spec.state=="drawdown" and equity/peak_equity-1 < -spec.state_cut:
                amounts = [x*.5 for x in amounts]
                counts["drawdown_scaled_batches"] += 1
            if spec.state=="adverse_inventory" and unrealized<0:
                amounts = [x*.5 for x in amounts]
                counts["adverse_inventory_batches"] += 1
            if spec.state=="symbol_budget":
                amounts = [min(x,max(0,130000*spec.state_cut-by_symbol[h["symbol"]])) for x,h in zip(amounts,picks)]
            if spec.pacing:
                amounts,scale = pro_rata(amounts,used)
                day["pacing_scale"] = scale
                counts["paced_batches"] += scale<1
            intended += sum(amounts)
            for h,amount in zip(picks,amounts):
                rec = summaries.get((d.isoformat(),h["symbol"]))
                # Store orders before examining their eventual late-minute fill.
                prior = rec.get("preorder") if rec else None
                if not valid(prior):
                    old = summaries.get((signal.isoformat(),h["symbol"]))
                    observed=signal if old else FEATS[INDEX[signal]-1]
                    prior = (old["close"] if old else h["prior_close"])*adjustment_factor(h["symbol"],observed,d)
                proposals.append((h,amount,prior,fs[h["symbol"]],signal))
        # Scheduled final-minute covers are after pre-order decisions.
        for p in active:
            if p["due_index"]==INDEX[d]:
                rec = summaries.get((d.isoformat(),p["symbol"]))
                if rec and rec.get("entry_ts"):
                    cover(p,p["shares"],rec["entry_px"],rec["entry_ts"],"backstop")
                else:
                    counts["missing_scheduled_exit"] += 1
        active = [p for p in active if p["shares"]]
        for h,amount,prior,f,signal in proposals:
            sym = h["symbol"]
            rec = summaries.get((d.isoformat(),sym))
            if not rec or not rec.get("entry_ts"):
                counts["missed_late_entry"] += 1
                continue
            px = rec["entry_px"]
            if borrow_blocks_short(px/h["prior_close"]-1 if h["prior_close"]>0 else None,h["prior_dv"]):
                counts["inherited_borrow_proxy_block"] += 1
                continue
            qty = math.floor(amount/(prior if spec.pacing or spec.share_sizing=="preorder" else px))
            if qty<=0:
                counts["zero_share_order"] += 1
                continue
            p = {"id":f"{signal}/{sym}","symbol":sym,"signal":signal.isoformat(),
                 "fill_date":d.isoformat(),"fill_index":INDEX[d],"due_index":INDEX[d]+10,
                 "entry_ts":rec["entry_ts"],"entry":px,"shares":qty,"initial_shares":qty,
                 "original_entry":px,"original_shares":qty,
                 "entry_cost":cost_per_share(px),
                 "mark":px,"last_observed_mark":px,"last_mark_date":d.isoformat(),
                 "atr":f["atr20"]*adjustment_factor(sym,signal,d) if f.get("atr20") is not None else None,"feature":f,
                 "covered":False,"ticket":amount,"preorder_price":prior}
            active.append(p)
            positions.append(p)
            book(p,-qty*cost_per_share(px))
            day["extra_spread"] += qty*spread_proxy(px)
            day["new_gross"] += qty*px
        by_symbol = defaultdict(float)
        for p in active:
            rec = summaries.get((d.isoformat(),p["symbol"]))
            mark = rec["close"] if rec else (p["last_observed_mark"]*(1+stale_shock) if stale_shock is not None else p["mark"])
            book(p,p["shares"]*(p["mark"]-mark))
            p["mark"] = mark
            if rec:
                p["last_mark_date"] = d.isoformat()
                p["last_observed_mark"] = mark
            else:
                day["stale_gross"] += p["shares"]*mark
                counts["stale_position_sessions"] += 1
            by_symbol[p["symbol"]] += p["shares"]*mark
        day["gross"] = sum(by_symbol.values())
        day["tickets"] = len(active)
        day["symbols"] = len(by_symbol)
        day["largest_symbol_gross"] = max(by_symbol.values(),default=0.0)
        next_d = SCORE[day_i+1] if day_i+1<len(SCORE) else d
        day["borrow_base"] = day["gross"]*(next_d-d).days/365
        equity += day["pnl"]
        peak_equity = max(peak_equity,equity)
        day["equity"] = equity
        day["gross_to_equity"] = day["gross"]/equity if equity>0 else None
        day["largest_symbol_equity_fraction"] = day["largest_symbol_gross"]/equity if equity>0 else None
        day["above_130k"] = day["gross"]>130000
        day["excess_130k"] = max(0,day["gross"]-130000)
        day["excursion_cause"] = ("new_allocation_and_marks" if day["new_gross"] else "existing_inventory_price_drift") if day["above_130k"] else "none"
        daily.append(day)
    m = metrics(daily,cohort,legs,active,positions,mode,counts,intended,symbol_pnl,ticket_pnl)
    return m,{"positions":positions,"legs":legs,"terminal":active,"daily":daily,
              "symbol_pnl":dict(symbol_pnl),"ticket_pnl":dict(ticket_pnl)}


def metrics(daily,cohort,legs,active,positions,mode,counts,intended,symbol_pnl,ticket_pnl):
    pnl = sum(x["pnl"] for x in daily)
    completed = sum(x["pnl"] for x in legs)
    terminal = sum(p["shares"]*(p["entry"]-p["mark"]-p["entry_cost"]) for p in active)
    closed_ticket_pnl=sum(ticket_pnl[p["id"]] for p in positions if p["shares"]==0)
    open_ticket_pnl=sum(ticket_pnl[p["id"]] for p in active)
    open_signals={p["signal"] for p in active}
    completed_cohort_pnl=sum(ticket_pnl[p["id"]] for p in positions if p["signal"] not in open_signals)
    if abs(pnl-completed-terminal)>1e-6 or abs(pnl-sum(cohort.values()))>1e-6:
        raise AssertionError("Completed legs + terminal MTM + daily/cohort reconciliation")
    if abs(pnl-closed_ticket_pnl-open_ticket_pnl)>1e-6:
        raise AssertionError("Fully closed versus still-open ticket lifecycle reconciliation")
    monthly = defaultdict(float)
    for row in daily:
        monthly[row["date"][:7]] += row["pnl"]
    month_rows = []
    equity = peak = 100000.0
    dd = dd_pct = 0.0
    underwater = []
    for row in daily:
        equity += row["pnl"]
        peak = max(peak,equity)
        dd = min(dd,equity-peak)
        dd_pct = min(dd_pct,equity/peak-1)
        underwater.append(equity<peak-1e-8)
    equity = 100000.0
    for month,value in monthly.items():
        month_rows.append({"month":month,"starting_equity":equity,"pnl":value,"return":value/equity if equity>0 else None,"ending_equity":equity+value})
        equity += value
    gross = [x["gross"] for x in daily]
    reds = [v for v in cohort.values() if v<0]
    cal_reds = [v for v in monthly.values() if v<0]
    ndays = sum(mode=="ALL" or d.month%2==(mode=="IS") for d in SCORE)
    borrow = sum(x["borrow_base"] for x in daily)
    spread = sum(x["extra_spread"] for x in daily)
    terminal_gross = sum(p["shares"]*p["mark"] for p in active)
    sorted_symbols = sorted(symbol_pnl.items(),key=lambda x:x[1],reverse=True)
    opposite=[row for row in daily if mode!="ALL" and date.fromisoformat(row["date"]).month%2!=(mode=="IS")]
    end_dates=defaultdict(list)
    for leg in legs:end_dates[leg["ticket_id"]].append(date.fromisoformat(leg["exit_ts"][:10]))
    still_open={p["id"] for p in active}
    crossing=0
    for p in positions:
        last=SCORE[-1] if p["id"] in still_open else max(end_dates[p["id"]])
        crossing+=last.strftime("%Y-%m")!=p["signal"][:7]
    return {"total_pnl":pnl,"per_day":pnl/ndays,"sessions":ndays,"trades":len(positions),
            "completed_leg_pnl":completed,"terminal_net_mtm":terminal,"exit_legs":len(legs),
            "fully_closed_ticket_pnl":closed_ticket_pnl,"open_ticket_lifecycle_pnl":open_ticket_pnl,
            "fully_completed_signal_cohort_pnl":completed_cohort_pnl,
            "partly_open_signal_cohort_pnl":pnl-completed_cohort_pnl,
            "fully_closed_tickets":sum(p["shares"]==0 for p in positions),
            "terminal_tickets":len(active),"terminal_gross":terminal_gross,
            "terminal_stale_gross":sum(p["shares"]*p["mark"] for p in active if p["last_mark_date"]!=SCORE[-1].isoformat()),
            "terminal_max_stale_sessions":max((INDEX[SCORE[-1]]-INDEX[date.fromisoformat(p["last_mark_date"])] for p in active),default=0),
            "cross_signal_month_lifecycle_tickets":crossing,
            "opposite_split_calendar_mtm":sum(x["pnl"] for x in opposite),
            "opposite_split_calendar_absolute_mtm":sum(abs(x["pnl"]) for x in opposite),
            "opposite_split_sessions_with_inventory":sum(x["tickets"]>0 for x in opposite),
            "max_dd":dd,"max_dd_percent":dd_pct,"worst_day":min(x["pnl"] for x in daily),
            "time_underwater_sessions":sum(underwater),"longest_underwater_sessions":longest_run(underwater),
            "red_months":len(reds),"red_loss_sum":sum(reds),"worst_month":min(cohort.values()),
            "median_month":statistics.median(cohort.values()),"months":cohort,
            "best_month_concentration":max(cohort.values())/pnl if pnl>0 else None,
            "calendar_months":month_rows,"calendar_red_months":len(cal_reds),"calendar_red_loss_sum":sum(cal_reds),
            "calendar_worst_month":min(monthly.values()),"calendar_median_month":statistics.median(monthly.values()),
            "calendar_best_month_concentration":max(monthly.values())/pnl if pnl>0 else None,
            "avg_exposure":statistics.mean(gross),"p95_exposure":sorted(gross)[math.ceil(.95*len(gross))-1],
            "peak_exposure":max(gross),"above_130k_sessions":sum(x>130000 for x in gross),
            "longest_above_130k":longest_run(x>130000 for x in gross),
            "exposure_dollar_sessions_above_130k":sum(max(0,x-130000) for x in gross),
            "exposure_dollar_days_above_130k":sum(max(0,row["gross"]-130000)*
                 ((SCORE[i+1]-SCORE[i]).days if i+1<len(SCORE) else 0) for i,row in enumerate(daily)),
            "excursion_causes":dict(Counter(x["excursion_cause"] for x in daily if x["above_130k"])),
            "peak_gross_to_equity":max((x["gross_to_equity"] for x in daily if x["gross_to_equity"] is not None),default=None),
            "largest_symbol_gross":max(x["largest_symbol_gross"] for x in daily),
            "largest_symbol_equity_fraction":max((x["largest_symbol_equity_fraction"] for x in daily if x["largest_symbol_equity_fraction"] is not None),default=None),
            "peak_live_tickets":max(x["tickets"] for x in daily),"mean_live_tickets":statistics.mean(x["tickets"] for x in daily),
            "peak_live_symbols":max(x["symbols"] for x in daily),"mean_live_symbols":statistics.mean(x["symbols"] for x in daily),
            "profit_per_avg_exposure":pnl/statistics.mean(gross) if sum(gross)>0 else None,
            "intended_notional":intended,"borrow_base":borrow,"extra_spread_cost":spread,
            "scenarios":{f"borrow_{int(r*100)}_spread_{int(s)}":pnl-r*borrow-(s-1)*spread
                         for r in SCENARIOS["borrow_annual_rates"] for s in SCENARIOS["spread_multipliers"]},
            "stress_short_10pct":-.1*max(gross),
            "stress_largest_name_50pct":-.5*max(x["largest_symbol_gross"] for x in daily),
            "stress_joint_others10_largest50":min(-.1*x["gross"]-.4*x["largest_symbol_gross"] for x in daily),
            "top_symbol_profit":sorted_symbols[:5],"bottom_symbol_profit":sorted_symbols[-5:],
            "top_symbol_concentration":sorted_symbols[0][1]/pnl if sorted_symbols and pnl>0 else None,
            "stale_exposure_dollar_sessions":sum(x["stale_gross"] for x in daily),
            "counters":dict(counts),"valuation":CONVENTION+"; raw fills; partial split/dividend/loan coverage",
            "exposure_sampling":"synchronized EOD; minute peak audit separate"}


def ledger(record):
    record = {"timestamp":stamp(),"elapsed_seconds":elapsed(),**record}
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    with LEDGER.open("a",encoding="utf-8") as f:
        f.write(json.dumps(record,allow_nan=False)+"\n")


def score_job(job):
    spec_dict,mode,ranks,summaries = job
    spec = Spec(**spec_dict)
    start = timer.monotonic()
    m,details = score(spec,mode,ranks,summaries)
    path = ROOT/"details"/f"{spec.id}_{mode}.json"
    dump(path,details)
    out = {"spec":asdict(spec),"mode":mode,"metrics":m,"timestamp":stamp(),
           "score_seconds":timer.monotonic()-start,"code_sha256":code_identity(),
           "detail_path":path.relative_to(REPO_ROOT).as_posix(),"detail_sha256":digest(path)}
    dump(ROOT/"results"/f"{spec.id}_{mode}.json",out)
    return out


def run_is(specs,workers=8,replay_reason=None):
    authorize("IS")
    for spec in specs:
        p = ROOT/"results"/f"{spec.id}_IS.json"
        if p.exists():
            if not replay_reason:
                raise RuntimeError("Use a new hypothesis id or explicit audited replay")
            old = read(p)
            archive = ROOT/"superseded"/(spec.id+"_"+digest(p)[:16]+"_IS.json")
            dump(archive,old)
            ledger({"event":"COMMON_REPAIR_REPLAY","id":spec.id,"reason":replay_reason,
                    "previous_result_sha256":digest(p),"archive":archive.relative_to(REPO_ROOT).as_posix()})
        ledger({"event":"PREDECLARE","spec":asdict(spec),"materiality":MATERIALITY})
    start = timer.monotonic()
    ranks,summaries = data_for("IS",workers,need_minutes=any(s.cover_clock=="all_minutes" for s in specs))
    results = []
    # Each worker owns a policy output. Shared market input is read-only.
    with ProcessPoolExecutor(max_workers=min(workers,len(specs),8)) as pool:
        jobs = [pool.submit(score_job,(asdict(s),"IS",ranks,summaries)) for s in specs]
        for job in as_completed(jobs):
            out = job.result()
            results.append(out)
            m = out["metrics"]
            cpath = ROOT/"results"/f"{out['spec']['control']}_IS.json"
            comparison = classify(m,read(cpath)["metrics"]) if cpath.exists() else None
            ledger({"event":"COMPLETE","id":out["spec"]["id"],"origin":out["spec"]["origin"],
                    "mode":"IS","metrics":m,"comparison":comparison,"score_seconds":out["score_seconds"],
                    "detail_sha256":out["detail_sha256"]})
            print(f"{out['spec']['id']} IS PnL={m['total_pnl']:.2f} day={m['per_day']:.2f} "
                  f"DD={m['max_dd']:.2f} redloss={m['red_loss_sum']:.2f} "
                  f"gross avg/peak={m['avg_exposure']:.2f}/{m['peak_exposure']:.2f} "
                  f"terminal={m['terminal_tickets']} {comparison['classification'] if comparison else ''}",flush=True)
    ledger({"event":"BATCH_CHECKPOINT","ids":[s.id for s in specs],"wall_seconds":timer.monotonic()-start,
            "code_sha256":code_identity(),"input_sha256":input_identity(),"oos_exposed":False})
    state=read(ROOT/"state.json")
    state.update(last_checkpoint=stamp(),elapsed_checkpoint_seconds=elapsed(),code_sha256=code_identity(),
                 input_sha256=input_identity(),completed_is=sorted(p.stem[:-3] for p in (ROOT/"results").glob("*_IS.json")))
    dump(ROOT/"state.json",state)
    return results


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["controls","is","clock"])
    p.add_argument("--specs")
    p.add_argument("--workers",type=int,default=8)
    p.add_argument("--replay-reason")
    args=p.parse_args()
    if args.command=="clock":
        print(json.dumps({"timestamp":stamp(),"elapsed_minutes":elapsed()/60,"remaining_minutes":180-elapsed()/60}))
    else:
        specs=CONTROLS if args.command=="controls" else [Spec(**s) for s in read(REPO_ROOT/args.specs)]
        run_is(specs,args.workers,args.replay_reason)


if __name__=="__main__":
    main()
