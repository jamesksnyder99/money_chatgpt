"""CG Arrow 007 certified baseline: fixed-point reranking, engine repairs, freeze and gate.

Usage: python scripts/cg_arrow007_run.py [--workers 8] [--max-iterations 6]
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import polars as pl  # noqa: E402

from ingest.paths import ETP_TICKERS, REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_events as ev  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification import r4r5_schedule as sched  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    ACTION_PATH, CUTOFF, FEATS, INDEX, RANKS_PATH, VERIFY_ROOT, action_events, digest, dump_json,
    load_summaries, present, read_json, set_vendor_status, split_of, stamp,
)
from verification.r4r5_replay import COMPLETED, VERIFIED, cohorts, load_field, needs_for, replay  # noqa: E402

WORK = VERIFY_ROOT / "work"
HANDOFF7 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow007"
FROZEN = REPO_ROOT / "data" / "tmp" / "cg_arrow003"
FAMS = ("PARENT", "R4", "R5")
PANELS = {"LEGACY_FILL_QTY": "fill", "CAUSAL_PREORDER_QTY": "preorder"}
LOOKBACK = 15
CODE_FILES = ("src/verification/r4r5_data.py", "src/verification/r4r5_replay.py",
              "src/verification/r4r5_export.py", "src/verification/r4r5_oracle.py",
              "src/verification/r4r5_repair.py", "src/verification/r4r5_rank.py",
              "src/verification/r4r5_events.py", "src/verification/r4r5_schedule.py",
              "scripts/cg_arrow007_run.py", "scripts/cg_arrow007_events.py",
              "scripts/cg_arrow007_actions.py")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------------ universe
def tradable_universe():
    import re
    roster = set(pl.read_parquet(REPO_ROOT / "data/ref/symbols_common.parquet")["symbol"].to_list())
    etp = {x.strip().upper() for x in ETP_TICKERS.read_text(encoding="utf-8").splitlines()
           if x.strip() and not x.startswith("#")} if ETP_TICKERS.exists() else set()
    tests = sorted(s for s in roster if re.match(r"^Z[A-Z]ZZT$", s))
    return roster, etp, tests


def candidate_meta(signals):
    out = {}
    frames = {t: pl.read_parquet(REPO_ROOT / f"data/{t}/eligibility.parquet") for t in ("virgin", "full")}
    for iso in signals:
        d = date.fromisoformat(iso)
        f = frames["virgin" if d <= date(2026, 5, 29) else "full"]
        day = f.filter(pl.col("session_date") == d).unique(subset=["symbol"])
        out[iso] = {s: {"prior_close": pc, "prior_dollar_volume": dv}
                    for s, pc, dv in day.select("symbol", "prior_close", "prior_dollar_volume").iter_rows()}
    return out


def rank_with(field_per_cohort: dict, meta: dict, summaries: dict, status_map: dict,
              events=None) -> list[dict]:
    """Rank a given per-cohort candidate set under a given event set."""
    out = []
    for iso in sorted(field_per_cohort):
        signal = date.fromisoformat(iso)
        cands = {s: meta[iso][s] for s in field_per_cohort[iso] if s in meta[iso]}
        ranked = rank.rank_cohort(signal, cands, summaries, status_map, events=events)
        out.append({"signal": signal, "signal_iso": iso, "split": split_of(signal),
                    "fill": sched.entry_for(signal), "rows": ranked["rows"][:8],
                    "n_field": ranked["n_field"], "field_ceiling": ranked["field_ceiling"],
                    "ranking_scope": ranked["ranking_scope"],
                    "unrankable": ranked["unrankable"],
                    "unrankable_unresolved": ranked["unrankable_unresolved"]})
    return out


# ------------------------------------------------------------------ fixed point
def volume_signature(symbol: str, when: str, summaries: dict) -> dict:
    """Joint price and share-volume behaviour at a session.

    A share consolidation multiplies price and divides share volume by the same factor.
    A repricing does not contract volume. This describes evidence; it never sets a factor.
    """
    d = date.fromisoformat(when)
    i = INDEX.get(d)
    if i is None:
        return {"classifiable": False}
    before = None
    for j in range(i - 1, max(0, i - 6), -1):
        rec = summaries.get((FEATS[j].isoformat(), symbol))
        if present(rec):
            before = rec
            break
    at = summaries.get((when, symbol))
    if not (present(at) and before):
        return {"classifiable": False}
    pr = at["close"] / before["close"]
    vr = at["volume"] / before["volume"] if before["volume"] else None
    consolidation_like = bool(pr >= 2.0 and vr is not None and vr <= 0.5)
    return {"classifiable": True, "price_ratio": pr, "volume_ratio": vr,
            "consolidation_like": consolidation_like}


def classify_unresolved(item: dict, summaries: dict, scans: dict) -> dict:
    """Decide whether a remaining discontinuity blocks certification.

    Blocking requires that the observation still looks like a unit change after every
    documented event is applied, or that the issuer's filing record could not be searched
    at all. A discontinuity whose issuer filings were searched, which states no split, and
    whose share volume expanded rather than contracted, is classified as a market move.
    """
    sig = volume_signature(item["symbol"], item["date"], summaries) if item.get("date") else {"classifiable": False}
    scan = scans.get(item["symbol"], {})
    searched = scan.get("status") in ("FILING_EVIDENCE_FOUND", "UNRESOLVED_NO_FILING_EVIDENCE") \
        and scan.get("filings_scanned", 0) > 0
    out = {**item, **{k: v for k, v in sig.items() if k != "classifiable"},
           "issuer_filings_searched": bool(searched),
           "filings_scanned": scan.get("filings_scanned", 0),
           "issuer": scan.get("issuer")}
    if sig.get("consolidation_like"):
        out["classification"] = "SUSPECTED_UNFILED_UNIT_CHANGE"
        out["blocking"] = True
    elif not searched:
        out["classification"] = "ISSUER_FILING_RECORD_UNAVAILABLE"
        out["blocking"] = True
    elif sig.get("classifiable"):
        out["classification"] = "MARKET_MOVE_NO_SPLIT_IN_ISSUER_FILINGS"
        out["blocking"] = False
    else:
        out["classification"] = "ENDPOINTS_UNAVAILABLE_FOR_CLASSIFICATION"
        out["blocking"] = True
    return out


def unresolved_selected(cohort_list, summaries, resolutions) -> list[dict]:
    """Selected names whose action-adjusted ranking or holding window is still discontinuous."""
    bad = []
    for c in cohort_list:
        for h in c["rows"]:
            lb = rank.lookback_integrity(c["signal"], h["symbol"], summaries, resolutions)
            h.update(lb)
            exit_d = FEATS[INDEX[c["fill"]] + 10]
            hd = rank.holding_integrity(c["fill"], exit_d, h["symbol"], summaries, resolutions)
            h.update(hd)
            if lb["lookback_resolution"] == "UNEXPLAINED_RANKING_WINDOW_DISCONTINUITY":
                bad.append({"symbol": h["symbol"], "cohort_id": c["signal_iso"], "window": "ranking",
                            "date": lb["lookback_ratio_date"], "ratio": lb["lookback_max_ratio"]})
            if hd["holding_resolution"] == "UNEXPLAINED_HOLDING_WINDOW_DISCONTINUITY":
                bad.append({"symbol": h["symbol"], "cohort_id": c["signal_iso"], "window": "holding",
                            "date": hd["holding_ratio_date"], "ratio": hd["holding_max_ratio"]})
    return bad


def merge_new_evidence(cases: list[dict], workers: int) -> int:
    """Investigate cases not yet in the evidence store and fold verified actions into the table."""
    store = read_json(WORK / "event_evidence.json") if (WORK / "event_evidence.json").exists() else {}
    todo = [(c["symbol"], c["date"]) for c in cases
            if c["date"] and f"{c['symbol']}|{c['date']}" not in store]
    if not todo:
        return 0
    note(f"investigating {len(todo)} newly selected-name cases against SEC EDGAR")
    store.update(ev.investigate_many(todo, workers=workers, progress_every=20))
    dump_json(WORK / "event_evidence.json", store)
    cases_store = read_json(WORK / "event_cases.json")
    for c in cases:
        key = f"{c['symbol']}|{c['date']}"
        if key not in cases_store and c["date"]:
            cases_store[key] = {"symbol": c["symbol"], "date": c["date"], "cohorts": [c["cohort_id"]],
                                "roles": [f"fixed_point_{c['window']}_window"],
                                "max_ratio": c["ratio"], "close_before": None, "close_at": None}
    dump_json(WORK / "event_cases.json", cases_store)
    subprocess.run([sys.executable, "scripts/cg_arrow007_actions.py"], cwd=REPO_ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    action_events.cache_clear()
    return len(todo)


# ------------------------------------------------------------------ books
def build_books(cohort_list, summaries, recorded_map, cl_recorded) -> dict:
    books = {}
    for fam in FAMS:
        for panel, qty in PANELS.items():
            books[(fam, "R1", panel)] = replay(fam, cl_recorded, summaries, hold=10, quantity=qty,
                                               stage=f"R1_{panel}", recorded=recorded_map[fam])
            books[(fam, "R2", panel)] = replay(fam, cohort_list, summaries, hold=10, quantity=qty,
                                               stage=f"R2_{panel}")
    return books


def split_books(fam, stage, panel, cohort_list, summaries, recorded=None) -> dict:
    """Independent books by original signal ownership, so risk metrics never mix splits."""
    qty = PANELS[panel]
    out = {}
    for split in ("IS", "OOS", "ALL"):
        subset = [c for c in cohort_list if split == "ALL" or c["split"] == split]
        out[split] = replay(fam, subset, summaries, hold=10, quantity=qty,
                            stage=f"{stage}_{panel}_{split}", recorded=recorded)
    return out


def account_metrics(book, label) -> dict:
    ts = book["trades"]
    ver = [t for t in ts if t["status"] in COMPLETED]
    daily = book["daily"]
    eq = [r["equity"] for r in daily]
    peak, dd, ddp, under = 100000.0, 0.0, 0.0, 0
    prev = 100000.0
    changes, monthly = [], defaultdict(float)
    for r in daily:
        e = r["equity"]
        changes.append(e - prev)
        monthly[r["date"][:7]] += e - prev
        prev = e
        peak = max(peak, e)
        dd = min(dd, e - peak)
        ddp = min(ddp, e / peak - 1)
        under += e < peak - 1e-8
    wins = [t["modeled_net"] for t in ver if t["modeled_net"] > 0]
    losses = [t["modeled_net"] for t in ver if t["modeled_net"] < 0]
    reds = [v for v in monthly.values() if v < 0]
    gross = [r["gross_exposure"] for r in daily]
    runoff_ids = {t["ticket_id"] for t in ver if t.get("exit_after_cutoff") in (True, "True")}
    return {
        "book": label, "sessions_in_account": len(daily), "intended": len(ts), "completed": len(ver),
        "documented_event_open": sum(1 for t in ts if t["status"] in
                                     ("OPEN_AT_BOUNDARY_DOCUMENTED_HALT", "NO_ENTRY_DOCUMENTED_TRADING_EVENT")),
        "unresolved": sum(1 for t in ts if t["status"].startswith(("UNRESOLVED", "MISSED", "BLOCKED_STRUCTURAL"))),
        "wins": len(wins), "losses": len(losses), "flats": len(ver) - len(wins) - len(losses),
        "hit_rate": len(wins) / len(ver) if ver else None,
        "avg_win": sum(wins) / len(wins) if wins else None,
        "avg_loss": sum(losses) / len(losses) if losses else None,
        "payoff_ratio": ((sum(wins) / len(wins)) / abs(sum(losses) / len(losses))) if wins and losses else None,
        "profit_factor": (sum(wins) / -sum(losses)) if losses else None,
        "gross_pnl": sum(t["gross_pnl"] for t in ver), "modeled_net": sum(t["modeled_net"] for t in ver),
        "net_double_spread": sum(t["modeled_net_double_spread"] for t in ver),
        "net_borrow_10": sum(t["net_borrow_10"] for t in ver),
        "net_borrow_30": sum(t["net_borrow_30"] for t in ver),
        "completed_net_through_cutoff": sum(t["modeled_net"] for t in ver
                                            if t["ticket_id"] not in runoff_ids),
        "september_runoff_net": sum(t["modeled_net"] for t in ver if t["ticket_id"] in runoff_ids),
        "september_runoff_trades": len(runoff_ids),
        "per_session_basis": f"{len(daily)} account sessions in this split-owned book",
        "net_per_session": (sum(t["modeled_net"] for t in ver) / len(daily)) if daily else None,
        "max_dd_dollars": dd, "max_dd_percent": ddp, "worst_day": min(changes, default=0.0),
        "time_underwater_sessions": under,
        "red_calendar_months": len(reds), "red_month_loss_sum": sum(reds),
        "worst_month": min(monthly.values()) if monthly else None,
        "median_month": sorted(monthly.values())[len(monthly) // 2] if monthly else None,
        "mean_gross": sum(gross) / len(gross), "peak_gross": max(gross),
        "exposure_dollar_days": sum(gross),
        "turnover_entry_notional": sum(t["quantity"] * t["entry_price"] for t in ts if t.get("quantity")),
        "tier_contribution": {k: sum(t["modeled_net"] for t in ver if t["size_tier"] == k)
                              for k in ("FULL", "HALF", "QUARTER")},
        "aug31_equity": daily[-1]["equity"], "aug31_open_tickets": daily[-1]["open_tickets"],
        "aug31_stale_gross": daily[-1]["stale_gross"],
    }


def upside_bridge(r1_book, r2_book) -> dict:
    a = {t["ticket_id"]: t for t in r1_book["trades"] if t["status"] in COMPLETED}
    b = {t["ticket_id"]: t for t in r2_book["trades"] if t["status"] in COMPLETED}
    common = set(a) & set(b)
    added, dropped = set(b) - set(a), set(a) - set(b)
    per_cohort = defaultdict(lambda: [0.0, 0.0])
    for k, t in a.items():
        per_cohort[t["cohort_id"]][0] += t["modeled_net"]
    for k, t in b.items():
        per_cohort[t["cohort_id"]][1] += t["modeled_net"]
    by_symbol = defaultdict(float)
    for k in added:
        by_symbol[b[k]["symbol"]] += b[k]["modeled_net"]
    for k in dropped:
        by_symbol[a[k]["symbol"]] -= a[k]["modeled_net"]
    top = sorted(by_symbol.items(), key=lambda x: -abs(x[1]))[:15]
    return {
        "r1_total": sum(t["modeled_net"] for t in a.values()),
        "r2_total": sum(t["modeled_net"] for t in b.values()),
        "common_tickets": len(common),
        "common_r1_net": sum(a[k]["modeled_net"] for k in common),
        "common_r2_net": sum(b[k]["modeled_net"] for k in common),
        "common_difference": sum(b[k]["modeled_net"] - a[k]["modeled_net"] for k in common),
        "added_tickets": len(added), "added_net": sum(b[k]["modeled_net"] for k in added),
        "dropped_tickets": len(dropped), "dropped_net": sum(a[k]["modeled_net"] for k in dropped),
        "per_cohort": {c: {"r1": round(v[0], 2), "r2": round(v[1], 2), "delta": round(v[1] - v[0], 2)}
                       for c, v in sorted(per_cohort.items())},
        "top_symbol_contributions": [{"symbol": s, "net_effect": round(v, 2)} for s, v in top],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-iterations", type=int, default=6)
    args = ap.parse_args()

    # Phase 0 — frozen calendar, proved before anything is scored
    existing = [date.fromisoformat(k) for k in read_json(RANKS_PATH)]
    diff = sched.schedule_diff(existing, date(2025, 9, 1), date(2026, 8, 31))
    note(f"calendar rule {diff['rule_id']}: identical={diff['identical']} "
         f"weeks={diff['weeks']} rollbacks={len(diff['weeks_requiring_rollback'])}")
    if not diff["identical"]:
        note("frozen calendar rule changes the study sample; stopping before economic comparison")
        dump_json(REPORTS / "cg_arrow007_schedule_diff.json", diff)
        return 3
    dump_json(REPORTS / "cg_arrow007_schedule_diff.json", diff)

    roster, etp, tests = tradable_universe()
    note(f"universe: roster={len(roster)} etp={len(etp)} test_issues={tests}")
    cohort_field = read_json(WORK / "cohort_field.json")
    ranks_cache = read_json(RANKS_PATH)
    meta = candidate_meta(sorted(cohort_field))
    status_map = rep.session_status_map()
    set_vendor_status(status_map)

    rule_field = {iso: cf["rule_field"] for iso, cf in cohort_field.items()}
    cached_field = {iso: [h["symbol"] for h in ranks_cache[iso]["rows"]] for iso in ranks_cache}

    endpoints = set()
    for iso, syms in rule_field.items():
        i = INDEX[date.fromisoformat(iso)]
        back = FEATS[i - LOOKBACK].isoformat()
        for s in set(syms) | set(cached_field.get(iso, [])):
            endpoints.add((iso, s))
            endpoints.add((back, s))
    note(f"loading {len(endpoints)} ranking endpoints")
    summaries = load_summaries(endpoints, args.workers)

    # ---- Phase 2: iterative rerank to a fixed point
    resolutions = {(x["symbol"], x.get("date")): x["resolution"]
                   for x in read_json(ACTION_PATH).get("screen_resolutions", [])}
    iterations = []
    corrected = None
    for it in range(1, args.max_iterations + 1):
        action_events.cache_clear()
        corrected = rank_with(rule_field, meta, summaries, status_map)
        # windows of the current selection must be loaded before screening
        win = set()
        for c in corrected:
            i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
            for h in c["rows"]:
                for d in FEATS[i - LOOKBACK - 1: fi + 11]:
                    win.add((d.isoformat(), h["symbol"]))
        summaries.update(load_summaries(win - set(summaries), args.workers))
        raw_bad = unresolved_selected(corrected, summaries, resolutions)
        scans = read_json(WORK / "event_symbol_scans.json") if (WORK / "event_symbol_scans.json").exists() else {}
        classified = [classify_unresolved(b, summaries, scans) for b in raw_bad]
        bad = [b for b in classified if b["blocking"]]
        by_class = Counter(b["classification"] for b in classified)
        note(f"  discontinuity classification: {dict(by_class)}")
        members = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in corrected}
        iterations.append({"iteration": it, "unresolved_selected": len(bad),
                           "discontinuities_examined": len(classified),
                           "classification_counts": dict(by_class),
                           "membership_sha256": sha_obj(members),
                           "blocking_cases": bad[:60],
                           "non_blocking_market_moves": [b for b in classified
                                                         if not b["blocking"]][:60]})
        note(f"iteration {it}: unresolved selected-name events={len(bad)} "
             f"membership={sha_obj(members)[:12]}")
        if not bad:
            # confirmation pass: another complete rerank must reproduce the same membership
            action_events.cache_clear()
            again = rank_with(rule_field, meta, summaries, status_map)
            again_members = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in again}
            stable = sha_obj(again_members) == sha_obj(members)
            iterations.append({"iteration": it + 1, "unresolved_selected": 0,
                               "confirmation_pass": True, "membership_stable": stable,
                               "membership_sha256": sha_obj(again_members)})
            note(f"confirmation rerank: membership stable={stable}")
            break
        added = merge_new_evidence(bad, args.workers)
        resolutions = {(x["symbol"], x.get("date")): x["resolution"]
                       for x in read_json(ACTION_PATH).get("screen_resolutions", [])}
        if added == 0:
            note("no new evidence available for the remaining cases; fixed point reached with "
                 "unresolved events")
            break
    converged = (iterations[-1]["unresolved_selected"] == 0
                 and iterations[-1].get("membership_stable", False))
    note(f"fixed point after {len(iterations)} iterations, converged={converged}")

    # ---- three ranking baselines
    raw_top8 = {iso: [h["symbol"] for h in sorted(ranks_cache[iso]["rows"],
                                                  key=lambda x: -x["raw_return"])[:8]] for iso in ranks_cache}
    recorded_map = {fam: {p["id"]: p for p in read_json(FROZEN / "details" / f"{fam}_ALL.json")["positions"]}
                    for fam in FAMS}
    cl_recorded = cohorts(load_field(events=tuple(read_json(REPO_ROOT / "reports/cg_arrow003_corporate_actions.json")["events"])))
    for c in cl_recorded:
        c["fill"] = sched.entry_for(c["signal"])
    recorded_top8 = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in cl_recorded}
    certified_top8 = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in corrected}

    recon = []
    for iso in sorted(certified_top8):
        raw, rec, cert = raw_top8.get(iso, []), recorded_top8.get(iso, []), certified_top8[iso]
        recon.append({
            "cohort_id": iso, "split": split_of(date.fromisoformat(iso)),
            "R0_RAW_CACHE_TOP8": raw, "R1_RECORDED_TOP8": rec, "R2_CERTIFIED_TOP8": cert,
            "raw_field_size": len(cached_field.get(iso, [])),
            "certified_field_size": next(c["n_field"] for c in corrected if c["signal_iso"] == iso),
            "membership_change_vs_recorded": sorted(set(cert) ^ set(rec)) != [],
            "added_vs_recorded": [s for s in cert if s not in rec],
            "dropped_vs_recorded": [s for s in rec if s not in cert],
            "order_only_change_vs_recorded": set(cert) == set(rec) and cert != rec,
            "unrankable_unresolved": next(c["unrankable_unresolved"] for c in corrected if c["signal_iso"] == iso),
        })
    note(f"ranking reconciliation: membership changed vs recorded in "
         f"{sum(r['membership_change_vs_recorded'] for r in recon)} cohorts, order-only in "
         f"{sum(r['order_only_change_vs_recorded'] for r in recon)}")

    # ---- lifecycle observations for every certified and recorded selection
    life = set(needs_for(cl_recorded))
    for group in (corrected, cl_recorded):
        for c in group:
            i, fi = INDEX[c["signal"]], INDEX[c["fill"]]
            for h in c["rows"]:
                for d in FEATS[i - 20: fi + 11]:
                    life.add((d.isoformat(), h["symbol"]))
    summaries.update(load_summaries(life - set(summaries), args.workers))
    missing = [(s, iso) for (iso, s) in life if not present(summaries.get((iso, s)))
               and status_map.get((s, iso)) != "DOCUMENTED_NO_TRADING"]
    note(f"selection lifecycle observations missing: {len(missing)}")
    if missing:
        dump_json(WORK / "a7_missing_lifecycle.json", sorted(f"{s}/{d}" for s, d in missing))
        needed = {}
        for s, iso in missing:
            needed.setdefault(s, set()).add(date.fromisoformat(iso))
        reqs = rep.plan_requests(needed)
        note(f"acquiring {len(reqs)} request windows for the certified selection")
        rep.acquire(reqs, concurrency=8)
        rep.invalidate_summaries({d for ds in needed.values() for d in ds})
        set_vendor_status(rep.session_status_map())
        summaries.update(load_summaries({(d.isoformat(), s) for s, ds in needed.items() for d in ds},
                                        args.workers))

    # ---- replays and books
    books = build_books(corrected, summaries, recorded_map, cl_recorded)
    for fam in FAMS:
        note(f"{fam}: " + "  ".join(
            f"{st}/{pn}={sum(t['status'] in COMPLETED for t in books[(fam, st, pn)]['trades'])}/"
            f"{len(books[(fam, st, pn)]['trades'])}"
            for st in ("R1", "R2") for pn in PANELS))

    split_views = {}
    for fam in FAMS:
        for panel in PANELS:
            for stage, cl, rec in (("R1", cl_recorded, recorded_map[fam]), ("R2", corrected, None)):
                sb = split_books(fam, stage, panel, cl, summaries, rec)
                for split, book in sb.items():
                    split_views[f"{fam}/{stage}/{panel}/{split}"] = account_metrics(
                        book, f"{fam}/{stage}/{panel}/{split}")
    note(f"split-owned books built: {len(split_views)}")

    # ---- exports
    export_books = {(fam, f"{stage}_{panel}"): books[(fam, stage, panel)]
                    for fam in FAMS for stage in ("R1", "R2") for panel in PANELS}
    initial = HANDOFF7 / "r4r5_trade_exceptions_initial.csv"
    if not initial.exists():
        exp.write_csv(initial, exp.exceptions_rows(export_books))
    files = exp.export_all(export_books, root=HANDOFF7)
    files["r4r5_trade_exceptions_initial.csv"] = {"path": initial.as_posix(),
                                                  "sha256": digest(initial),
                                                  "bytes": initial.stat().st_size}
    orc = oracle.run(HANDOFF7, summaries)
    note(f"oracle ok={orc['ok']} trades={orc['trades']} cohorts={orc['cohorts']}")

    bridge = {fam: upside_bridge(books[(fam, "R1", "LEGACY_FILL_QTY")],
                                 books[(fam, "R2", "LEGACY_FILL_QTY")]) for fam in FAMS}
    for fam, b in bridge.items():
        note(f"{fam} R1->R2: {b['r1_total']:,.2f} -> {b['r2_total']:,.2f} "
             f"(common {b['common_difference']:+,.2f}, added {b['added_net']:+,.2f}, "
             f"dropped {-b['dropped_net']:+,.2f})")

    # ---- gate
    blockers = []
    if not converged:
        blockers.append(f"{iterations[-1]['unresolved_selected']} selected-name ranking or holding "
                        f"windows still carry an unexplained action-adjusted discontinuity")
    unresolved_rank = sum(c["unrankable_unresolved"] for c in corrected)
    if unresolved_rank:
        blockers.append(f"{unresolved_rank} rule-eligible candidates have an unresolved ranking endpoint")
    for fam in FAMS:
        ts = books[(fam, "R2", "LEGACY_FILL_QTY")]["trades"]
        u = [t for t in ts if t["status"].startswith(("UNRESOLVED", "MISSED", "BLOCKED_STRUCTURAL"))]
        if u:
            blockers.append(f"{fam}: {len(u)} slots unresolved or structurally blocked")
    if not orc["ok"]:
        blockers.append("independent oracle did not reconcile")
    gate = {"status": "OPEN" if not blockers else "NOT_RUN_DATA_GATE", "blockers": blockers,
            "disclosed": ["borrow, locate and dividend history unavailable: modeled net is conditional",
                          "single market-data vendor; SEC filings are the independent event source",
                          "observed bar prices are a simulation reference, not guaranteed broker fills"]}
    note(f"GATE {gate['status']} blockers={blockers}")

    ledger = [{"cohort_id": t["cohort_id"], "symbol": t["symbol"], "rank": t["rank"],
               "entry_date": t.get("scheduled_entry_date"), "entry_price": t.get("entry_price"),
               "quantity": t.get("quantity"), "size_tier": t.get("size_tier")}
              for t in books[("R5", "R2", "LEGACY_FILL_QTY")]["trades"]]
    ledger_hash = sha_obj(ledger)

    actions = read_json(ACTION_PATH)
    manifest = {
        "arrow": "CG Arrow 007", "executor": "Opus in Claude Code", "timestamp": stamp(),
        "elapsed_minutes": (time.monotonic() - T0) / 60,
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "calendar_rule": diff,
        "code_sha256": {p: digest(REPO_ROOT / p) for p in CODE_FILES},
        "action_table_sha256": digest(ACTION_PATH),
        "action_summary": {"events": len(actions["events"]), "cases": actions.get("cases_investigated"),
                           "resolution_counts": actions.get("resolution_counts"),
                           "identity_changes": len(actions.get("security_identity", [])),
                           "trading_events": len(actions.get("trading_events", []))},
        "fixed_point": {"iterations": iterations, "converged": converged},
        "ranking_reconciliation": recon,
        "split_owned_books": split_views,
        "upside_bridge": bridge,
        "oracle": orc, "gate": gate,
        "r2_entry_ledger_sha256": ledger_hash,
        "local_csvs": files, "log": LOG,
    }
    dump_json(REPORTS / "cg_arrow007_manifest.json", manifest)
    dump_json(WORK / "a7_baseline_state.json", {
        "gate": gate["status"], "r2_entry_ledger_sha256": ledger_hash, "converged": converged,
        "certified_cohorts": [{"signal_iso": c["signal_iso"], "split": c["split"],
                               "fill": c["fill"].isoformat(),
                               "rows": [{k: h[k] for k in ("symbol", "prior_close", "prior_dv",
                                                           "raw_return", "rank")} for h in c["rows"]],
                               "n_field": c["n_field"], "ranking_scope": c["ranking_scope"],
                               "unrankable_unresolved": c["unrankable_unresolved"]} for c in corrected]})
    note("manifest written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
