"""One replacement per original slot, never an independent cross-month signal book."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ingest.calendar import NYSE_EARLY_CLOSE
from research.arrow44 import _by_sess
from research.arrow47 import _short_n
from research.arrow70 import _elig_year
from research.cg_arrow002_lab import (ROOT, SCORE, FEATS, INDEX, assert_signals, dump,
                                    load_summaries, stamp, tape_summary, history_features, all_minute_exit, authorize)
from research.clock import session_bar_path

ET = ZoneInfo("America/New_York")


def decision_session(exit_ts, scheduled_end):
    """First 15:55 checkpoint after released cash, with >=3 sessions remaining."""
    d = exit_ts.date()
    if exit_ts.time().replace(tzinfo=None) > time(15,55):
        if INDEX[d]+1 >= len(FEATS):
            return None
        d = FEATS[INDEX[d]+1]
    while d in NYSE_EARLY_CLOSE:  # no 15:55 checkpoint at a 13:00 close
        if INDEX[d]+1 >= len(FEATS):
            return None
        d = FEATS[INDEX[d]+1]
    return d if INDEX[scheduled_end]-INDEX[d] >= 3 else None


def validate_contexts(contexts, mode):
    for c in contexts:
        root_signal = c["source_signal"]
        assert_signals([root_signal],mode)
        if not (INDEX[root_signal]+1 <= INDEX[c["decision_date"]] <= INDEX[c["scheduled_end"]]-3):
            raise RuntimeError("Replacement rank requested outside original slot lifecycle")
        if INDEX[c["scheduled_end"]] != INDEX[root_signal]+11:
            raise RuntimeError("Replacement cannot extend original slot horizon")


def lifecycle_rankings(contexts,mode,summaries):
    validate_contexts(contexts,mode)  # firewall BEFORE reading any candidate universe
    authorize(mode)
    days = sorted({c["decision_date"] for c in contexts})
    if not days:
        return {}
    by = _by_sess(_elig_year(days))
    needs = {(x.isoformat(),h["symbol"]) for d in days
             for h in by.get(d.isoformat(),[]) for x in (d,FEATS[INDEX[d]-15])}
    print(f"{stamp()} {mode} lifecycle-only replacement ranking: {len(contexts)} original slots, "
          f"{len(days)} checkpoint dates, {len(needs)} observations; no new root signals",flush=True)
    summaries.update(load_summaries(needs,8))
    out = {}
    for d in days:
        rows = []
        for h in by.get(d.isoformat(),[]):
            now = summaries.get((d.isoformat(),h["symbol"]))
            old = summaries.get((FEATS[INDEX[d]-15].isoformat(),h["symbol"]))
            if now and old and now["checkpoint"] is not None and min(now["checkpoint"],old["close"]) > 0:
                rows.append({**h,"raw_return":now["checkpoint"]/old["close"]-1})
        rows.sort(key=lambda r:r["raw_return"],reverse=True)
        out[d.isoformat()] = rows[:8] if len(rows) >= 16 else []
    dump(ROOT/f"lifecycle_replacement_ranks_{mode}.json",
         {"source_signal_cohort":mode,"purpose":"original-slot lifecycle only", "rankings":out})
    return out


def base_capacity_positions(ranks,summaries,base_trades):
    """Simulate every causal fill/early exit BEFORE applying common economic missing-H10 exclusions."""
    completed = {t["ticket_id"]:t for t in base_trades}
    positions = []
    for iso,rec in ranks.items():
        d = date.fromisoformat(iso)
        if INDEX[d]+11 >= len(FEATS):
            continue
        fill_d,end_d = FEATS[INDEX[d]+1],FEATS[INDEX[d]+11]
        for h in rec["rows"][:8]:
            ent = summaries.get((fill_d.isoformat(),h["symbol"]))
            if not ent:
                continue
            entry = datetime.fromisoformat(ent["ts"])
            close = NYSE_EARLY_CLOSE.get(end_d,time(16))
            expiry = datetime.combine(end_d,close,tzinfo=ET)-timedelta(minutes=1)
            t = _short_n(h,(entry,ent["close"]),(expiry,ent["close"]),"reservation",4000)
            if t is None:
                continue
            ticket_id = f"{iso}/{h['symbol']}"
            hist = [summaries.get((x.isoformat(),h["symbol"])) for x in FEATS[INDEX[d]-20:INDEX[d]+1]]
            atr = history_features(hist)["atr20"]
            early = all_minute_exit(ent["close"],atr,summaries.get((iso,h["symbol"],"minute_path"),[]))
            if early:
                t["exit_ts"] = datetime.fromisoformat(early[0])
                t["exit_px"] = early[1]
            else:
                target = summaries.get((end_d.isoformat(),h["symbol"]))
                if target:
                    t["exit_ts"] = datetime.fromisoformat(target["ts"])
                    t["exit_px"] = target["close"]
            t.update(signal=d,fill_date=fill_d,exit_date=t["exit_ts"].date(),ticket_id=ticket_id,
                     scheduled_end=end_d,early=early is not None,
                     economic_cohort=ticket_id in completed)
            if ticket_id in completed:
                actual = completed[ticket_id]
                if t["exit_ts"] != actual["exit_ts"] or t["exit_px"] != actual["exit_px"]:
                    raise RuntimeError("Independent causal protection state disagrees with scored cash control")
            positions.append(t)
    return positions


def marked_at_checkpoint(position,d,summaries):
    for x in reversed(FEATS[INDEX[position["entry_ts"].date()]:INDEX[d]+1]):
        rec = summaries.get((x.isoformat(),position["symbol"]))
        if rec:
            px = rec["checkpoint"] if x == d else rec["close"]
            if px is not None:
                return px
    return position["entry_px"]


def recycle_slots(spec,mode,ranks,summaries,base_trades):
    if not (spec.protection == "full" and spec.protection_clock == "all_minutes"
            and spec.ticket == 4000 and spec.feature_rule == "none" and spec.cap is None
            and spec.secondary_rule == "none" and spec.sizing == "equal"
            and spec.selection_rule == "none" and spec.min_hold == 3
            and spec.arm_atr == 2 and spec.rebound_atr == 1
            and spec.portfolio_rule == "none" and not spec.entry_confirmation):
        raise ValueError("D6 supports only the completed frozen R8_MINUTE_FULL cash rule")
    positions = base_capacity_positions(ranks,summaries,base_trades)
    contexts = []
    for t in positions:
        end_d = t["scheduled_end"]
        if not t["early"]:
            continue
        d = decision_session(t["exit_ts"],end_d)
        if d:
            contexts.append({"source_signal":t["signal"],"decision_date":d,"scheduled_end":end_d,
                             "original":t})
    validate_contexts(contexts,mode)
    rec_ranks = lifecycle_rankings(contexts,mode,summaries)
    needs = set()
    for c in contexts:
        for h in rec_ranks[c["decision_date"].isoformat()]:
            for d in FEATS[INDEX[c["decision_date"]]:INDEX[c["scheduled_end"]]+1]:
                needs.add((d.isoformat(),h["symbol"]))
    summaries.update(load_summaries(needs,8))
    result = list(base_trades)
    counters = Counter()
    intended = 0.0
    for c in sorted(contexts,key=lambda x:(x["decision_date"],x["original"]["ticket_id"])):
        d,end_d,t = c["decision_date"],c["scheduled_end"],c["original"]
        decision = datetime.combine(d,time(15,55),tzinfo=ET)+timedelta(minutes=1)
        live = [p for p in positions if p["entry_ts"] < decision < p["exit_ts"]]
        used = sum(p["shares"]*marked_at_checkpoint(p,d,summaries) for p in live)
        # Upcoming original next-close entries were decided earlier. Reserve their
        # nominal budget so recycling cannot spend the same capital at 15:56/15:59.
        # Pending primary orders are reserved at the signal-known $4000, not at
        # their not-yet-known closing execution price/borrow acceptance.
        prior_signal = FEATS[INDEX[d]-1].isoformat()
        pending_symbols = [h["symbol"] for h in ranks.get(prior_signal,{}).get("rows",[])[:8]]
        pending_replacements = [p for p in positions if p.get("planned_amount") is not None
                                and p["entry_ts"].date() == d and p["entry_ts"] >= decision]
        used += 4000*len(pending_symbols)+sum(p["planned_amount"] for p in pending_replacements)
        counters["replacement_opportunities"] += 1
        freed = t["shares"]*t["exit_px"]
        for h in rec_ranks[d.isoformat()]:
            rec = summaries.get((d.isoformat(),h["symbol"]))
            if not rec or rec["next_ts"] is None:
                continue
            sym_used = sum(p["shares"]*p["entry_px"] for p in live if p["symbol"] == h["symbol"])
            sym_used += 4000*pending_symbols.count(h["symbol"])
            sym_used += sum(p["planned_amount"] for p in pending_replacements if p["symbol"] == h["symbol"])
            amount = min(freed,4000.0,max(0,8000-sym_used),max(0,100000-used))
            if amount < rec["next_open"]:
                continue
            ent = (datetime.fromisoformat(rec["next_ts"]),rec["next_open"])
            if ent[0] < decision:
                raise RuntimeError("Replacement cannot precede checkpoint availability")
            ex = summaries.get((end_d.isoformat(),h["symbol"]))
            close = NYSE_EARLY_CLOSE.get(end_d,time(16))
            expiry = datetime.combine(end_d,close,tzinfo=ET)-timedelta(minutes=1)
            exit_bar = (datetime.fromisoformat(ex["ts"]),ex["close"]) if ex else (expiry,ent[1])
            tr = _short_n(h,ent,exit_bar,"recycle",amount)
            if tr is None:
                continue
            intended += amount
            tr["planned_amount"] = amount
            positions.append(tr)  # reserves capacity even if its eventual exit is missing
            if ex is None:
                counters["replacement_missing_exit_drop"] += 1
                break
            tr.update(signal=c["source_signal"],fill_date=d,exit_date=end_d,
                      ticket_id=t["ticket_id"]+"/R",ticket=amount)
            if t["economic_cohort"]:
                result.append(tr)
                counters["replacement_completed"] += 1
            else:
                counters["shadow_replacement_common_missing_backstop_exclusion"] += 1
            counters["cross_calendar_month_lifecycle_decisions"] += d.month % 2 != c["source_signal"].month % 2
            break
    return result,intended,counters
