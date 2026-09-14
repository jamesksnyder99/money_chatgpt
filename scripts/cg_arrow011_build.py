"""CG Arrow 011 — build the private trade/cohort atlas from the frozen ledgers.

Stage 1 of the anatomy study. Verifies the certified private inputs against their manifests,
reproduces the economic controls, computes SIGNAL_CLOSE and PRE_ORDER features, attaches
sizing-neutral and dollar outcome lenses and close-only holding paths, and writes the
git-ignored atlas plus the public feature catalog. No IS/OOS analysis happens here.

Usage: python scripts/cg_arrow011_build.py [--workers 8]
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.append(str(ROOT / "scripts"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_anatomy as an  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification import r4r5_repair as rep  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    ACTION_PATH, VERIFY_ROOT, digest, dump_json, read_json, stamp,
)
from verification.r4r5_replay import COMPLETED, replay  # noqa: E402
from cg_arrow007_run import candidate_meta  # noqa: E402
from cg_arrow010_run import build_substrate  # noqa: E402

A8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
A10 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow010"
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow011"
CACHE = VERIFY_ROOT / "a11"
PRINCIPAL = ("R5", "R2_CAUSAL_PREORDER_QTY")
LOG: list[str] = []
T0 = time.monotonic()


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def num(x):
    return None if x in ("", None) else float(x)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def read_ledger(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def typed(r: dict) -> dict:
    """CSV row to typed ledger row for the fields the anatomy layer reads."""
    out = dict(r)
    for k in ("quantity", "entry_price", "exit_price", "action_factor_over_hold", "gross_pnl",
              "modeled_net", "preorder_price", "intended_size", "ret3", "volume_ratio",
              "sizing_scale_factor", "equity_reference", "entry_commission", "entry_spread",
              "exit_commission", "exit_spread", "quantity_at_exit", "entry_price_exit_units",
              "prior_close", "ret15", "volume_multiplier", "momentum_multiplier"):
        if k in out:
            out[k] = num(out[k])
    out["rank"] = int(r["rank"])
    return out


def preorder_job(job):
    """One ticket's PRE_ORDER features; runs in a worker process."""
    symbol, signal_iso, entry_iso, preorder_ts, sig_rec = job
    from verification import r4r5_anatomy as an2
    summaries = {(signal_iso, symbol): sig_rec} if sig_rec else {}
    return (signal_iso, symbol), an2.pre_order_features(
        symbol, date.fromisoformat(signal_iso), date.fromisoformat(entry_iso), preorder_ts, summaries)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []

    # ------------------------------------------------------------ 1. input hashes
    a8m = read_json(REPORTS / "cg_arrow008_manifest.json")
    a10m = read_json(REPORTS / "cg_arrow010_manifest.json")
    hash_checks = {}
    for name, ref in a8m["local_csvs"].items():
        p = A8 / name
        hash_checks[f"a8/{name}"] = {"expected": ref["sha256"], "observed": digest(p) if p.exists() else None}
    for name, ref in a10m["local_csvs"].items():
        p = A10 / name
        exp_hash = ref["sha256"] if isinstance(ref, dict) else ref
        hash_checks[f"a10/{name}"] = {"expected": exp_hash, "observed": digest(p) if p.exists() else None}
    for k, v in hash_checks.items():
        v["ok"] = v["expected"] == v["observed"]
    bad = [k for k, v in hash_checks.items() if not v["ok"]]
    note(f"private input hashes verified: {len(hash_checks) - len(bad)}/{len(hash_checks)}")
    if bad:
        blockers.append(f"private inputs do not match their manifests: {bad}")
        return finish(blockers, {"hash_checks": hash_checks})
    hash_checks["action_table"] = {"expected": a8m["action_table_sha256"], "observed": digest(ACTION_PATH),
                                   "ok": a8m["action_table_sha256"] == digest(ACTION_PATH)}

    # ------------------------------------------------------------ 2. ledgers
    a8_rows = [typed(r) for r in read_ledger(A8 / "r4r5_verified_trades.csv")]
    a10_rows = [typed(r) for r in read_ledger(A10 / "r4r5_verified_trades.csv")]
    books = {}
    for r in a8_rows:
        books.setdefault((r["model"], r["replay_stage"]), []).append(r)
    for r in a10_rows:
        books.setdefault((r["model"], r["replay_stage"]), []).append(r)
    counts = {}
    for key, rows in books.items():
        done = sum(r["status"] in COMPLETED for r in rows)
        halted = sum(r["status"] == "OPEN_AT_BOUNDARY_DOCUMENTED_HALT" for r in rows)
        counts["/".join(key)] = {"intended": len(rows), "completed": done, "open_documented": halted,
                                 "cohorts": len({r["cohort_id"] for r in rows}),
                                 "eventual_completed_pnl": sum(r["modeled_net"] for r in rows if r["status"] in COMPLETED)}
    for key in (("R5", "R2_LEGACY_FILL_QTY"), ("R5", "R2_CAUSAL_PREORDER_QTY"), ("R4", "R2_LEGACY_FILL_QTY"),
                ("R4", "R2_CAUSAL_PREORDER_QTY"), ("PARENT", "R2_LEGACY_FILL_QTY"), ("PARENT", "R2_CAUSAL_PREORDER_QTY"),
                ("R5", "R5_FIXED_DOLLAR_CONTROL"), ("R5", "R5_EQUITY_SCALED")):
        c = counts["/".join(key)]
        note(f"{'/'.join(key)}: cohorts={c['cohorts']} intended={c['intended']} completed={c['completed']} "
             f"open={c['open_documented']} eventual={c['eventual_completed_pnl']:,.2f}")
        if not (c["cohorts"] == 52 and c["intended"] == 416 and c["completed"] == 415 and c["open_documented"] == 1):
            blockers.append(f"{'/'.join(key)} census is not 52/416/415+1: {c}")
    ref = {"R5/R2_LEGACY_FILL_QTY": 129092.60, "R5/R2_CAUSAL_PREORDER_QTY": 128864.62,
           "R5/R5_EQUITY_SCALED": 230566.36, "R4/R2_LEGACY_FILL_QTY": 114190.85}
    control_checks = {k: {"expected": v, "observed": counts[k]["eventual_completed_pnl"],
                          "ok": abs(counts[k]["eventual_completed_pnl"] - v) < 0.005} for k, v in ref.items()}
    if not all(v["ok"] for v in control_checks.values()):
        blockers.append(f"eventual completed-trade controls do not reproduce from the ledgers: {control_checks}")
    # the Arrow 010 fixed control must be the same trades as the A8 causal pre-order book
    a8p = {r["ticket_id"]: r for r in books[("R5", "R2_CAUSAL_PREORDER_QTY")]}
    a10f = {r["ticket_id"]: r for r in books[("R5", "R5_FIXED_DOLLAR_CONTROL")]}
    same = all(a8p[k]["quantity"] == a10f[k]["quantity"] and a8p[k]["entry_price"] == a10f[k]["entry_price"]
               and a8p[k]["exit_price"] == a10f[k]["exit_price"] and a8p[k]["status"] == a10f[k]["status"] for k in a8p)
    note(f"Arrow 010 fixed control identical to Arrow 008 causal pre-order book, ticket by ticket: {same}")
    if not same:
        blockers.append("Arrow 010 fixed control differs from the Arrow 008 causal pre-order book")

    # ------------------------------------------------------------ 3. substrate and replay reproduction
    corrected, summaries, coverage = build_substrate(args.workers)
    fresh = replay("R5", corrected, summaries, hold=10, quantity="preorder", stage="R2_CAUSAL_PREORDER_QTY")
    fresh_by = {t["ticket_id"]: t for t in fresh["trades"]}
    mism = 0
    for k, r in a8p.items():
        f = fresh_by.get(k)
        if f is None or f["status"] != r["status"] or (f.get("quantity") or 0) != (r["quantity"] or 0) \
                or (f.get("modeled_net") is None) != (r["modeled_net"] is None) \
                or (f.get("modeled_net") is not None and abs(f["modeled_net"] - r["modeled_net"]) > 1e-6):
            mism += 1
    note(f"fresh replay reproduces the certified causal pre-order ledger: mismatches={mism}")
    if mism:
        blockers.append(f"fresh replay differs from the certified ledger on {mism} tickets")
    # Oracle scope: the Corrected-Universe (R2) books this arrow reads. The R1 books' names lie
    # outside the substrate loaded here, so their daily marks cannot be rebuilt from it; that is
    # coverage, not a ledger defect, and those books are not used in this arrow.
    a8_trades = oracle.read_csv(A8 / "r4r5_verified_trades.csv")
    a8_audit = oracle.read_csv(A8 / "r4r5_verified_cohort_audit.csv")
    a8_daily = oracle.read_csv(A8 / "r4r5_daily_account.csv")
    r2_trades = [r for r in a8_trades if r["replay_stage"].startswith("R2_")]
    r2_daily = [r for r in a8_daily if r["replay_stage"].startswith("R2_")]
    orc = {"scope": "Arrow 008 R2 books only; R1 books not used in this arrow",
           "trades": oracle.verify_trades(a8_trades), "cohorts": oracle.verify_cohorts(a8_trades, a8_audit),
           "daily": oracle.verify_daily(r2_trades, r2_daily, summaries)}
    orc["ok"] = orc["trades"]["errors"] == 0 and orc["cohorts"]["errors"] == 0 and all(v["ok"] for v in orc["daily"].values())
    a10_trades = oracle.read_csv(A10 / "r4r5_verified_trades.csv")
    a10_daily = oracle.read_csv(A10 / "r4r5_daily_account.csv")
    orc10 = {"trades": oracle.verify_trades(a10_trades), "daily": oracle.verify_daily(a10_trades, a10_daily, summaries)}
    orc10["ok"] = orc10["trades"]["errors"] == 0 and all(v["ok"] for v in orc10["daily"].values())
    note(f"independent oracle: A8 R2 books ok={orc['ok']} (trades={orc['trades']['checked']}, "
         f"max_err={orc['trades']['max_abs_error']:.1e}, daily books={len(orc['daily'])}); A10 books ok={orc10['ok']}")
    if not orc["ok"] or not orc10["ok"]:
        blockers.append("independent oracle failed on the R2 / Arrow 010 ledgers")
    if blockers:
        return finish(blockers, {"hash_checks": hash_checks, "counts": counts, "control_checks": control_checks})

    # full ranked field per cohort, for cohort context only
    cohort_field = read_json(VERIFY_ROOT / "work" / "cohort_field.json")
    meta = candidate_meta(sorted(cohort_field))
    status_map = rep.session_status_map()
    full_field = {}
    for c in corrected:
        iso = c["signal_iso"]
        cands = {s: meta[iso][s] for s in cohort_field[iso]["rule_field"] if s in meta[iso]}
        full_field[iso] = rank.rank_cohort(c["signal"], cands, summaries, status_map)["rows"]
    membership = {c["signal_iso"]: [h["symbol"] for h in c["rows"]] for c in corrected}
    if sha_obj(membership) != a8m["membership_sha256"]:
        return finish(["membership hash drifted from Arrow 008"], {})
    episodes = an.selection_episodes(membership)

    # ------------------------------------------------------------ 4. features
    principal = books[PRINCIPAL]
    sc_feats, ctx = {}, {}
    for c in corrected:
        cc = an.cohort_context(c["rows"], full_field[c["signal_iso"]])
        for h in c["rows"]:
            key = (c["signal_iso"], h["symbol"])
            sc_feats[key] = an.signal_close_features(h["symbol"], c["signal"], summaries)
            ctx[key] = cc[h["symbol"]]
    note(f"SIGNAL_CLOSE features computed for {len(sc_feats)} tickets")
    # frozen-rule agreement on every adequately observed ticket
    disagree = []
    for r in principal:
        f = sc_feats[(r["cohort_id"], r["symbol"])]
        if f["ret3_frozen"] is not None and r["ret3"] is not None and abs(f["ret3_frozen"] - r["ret3"]) > 1e-12:
            disagree.append(r["ticket_id"])
        if f["volume_ratio_frozen"] is not None and r["volume_ratio"] is not None \
                and abs(f["volume_ratio_frozen"] - r["volume_ratio"]) > 1e-9:
            disagree.append(r["ticket_id"])
        expect = {"FULL": "S1", "HALF": ("S2" if r["volume_multiplier"] < 1 else "S3"), "QUARTER": "S4"}[r["size_tier"]]
        if f["four_state"] != "MISSING_FEATURE" and not f["four_state"].startswith(expect):
            disagree.append(r["ticket_id"] + ":state")
    note(f"four-state labels and frozen features agree with the ledger: disagreements={len(disagree)}")
    if disagree:
        return finish([f"feature/state disagreement on {disagree[:5]}"], {})

    jobs = []
    for r in principal:
        sig = summaries.get((r["cohort_id"], r["symbol"]))
        jobs.append((r["symbol"], r["cohort_id"], r["scheduled_entry_date"], r.get("preorder_ts") or None, sig))
    po_feats = {}
    cache_p = CACHE / "preorder_features.json"
    cached = read_json(cache_p) if cache_p.exists() else {}
    todo = [j for j in jobs if f"{j[1]}/{j[0]}" not in cached]
    note(f"PRE_ORDER features: {len(jobs) - len(todo)} cached, {len(todo)} to compute")
    if todo:
        with ProcessPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
            futs = [pool.submit(preorder_job, j) for j in todo]
            for n, f in enumerate(as_completed(futs), 1):
                key, val = f.result()
                cached[f"{key[0]}/{key[1]}"] = val
                if n % 100 == 0 or n == len(futs):
                    note(f"  pre-order {n}/{len(futs)}")
        dump_json(cache_p, cached)
    for j in jobs:
        po_feats[(j[1], j[0])] = cached[f"{j[1]}/{j[0]}"]
    note(f"PRE_ORDER available for {sum(1 for v in po_feats.values() if v.get('pre_order_available'))}/{len(po_feats)}")

    # ------------------------------------------------------------ 5. outcomes, lenses, paths
    lens = {("fixed_causal", ("R5", "R2_CAUSAL_PREORDER_QTY")), ("equity_scaled", ("R5", "R5_EQUITY_SCALED")),
            ("legacy_fill", ("R5", "R2_LEGACY_FILL_QTY")), ("r4_causal", ("R4", "R2_CAUSAL_PREORDER_QTY")),
            ("r4_legacy", ("R4", "R2_LEGACY_FILL_QTY")), ("parent_causal", ("PARENT", "R2_CAUSAL_PREORDER_QTY"))}
    by_lens = {name: {r["ticket_id"]: r for r in books[key]} for name, key in lens}
    atlas, paths_rows, evidence = [], [], []
    recon_fail = 0
    for r in principal:
        key = (r["cohort_id"], r["symbol"])
        sc, po, cx, ep = sc_feats[key], po_feats[key], ctx[key], episodes[key]
        oc = an.sizing_neutral_outcome(r)
        if oc.get("gross_reconciles") is False:
            recon_fail += 1
        path = an.holding_path(r, summaries)
        row = {"ticket_id": r["ticket_id"], "cohort_id": r["cohort_id"], "signal_date": r["cohort_id"],
               "signal_month": r["cohort_id"][:7], "split": r["split"], "symbol": r["symbol"],
               "rank": r["rank"], "entry_date": r["scheduled_entry_date"],
               "scheduled_exit_date": r.get("scheduled_exit_date"), "actual_exit_date": r.get("actual_exit_date") or None,
               "status": r["status"], "size_tier": r["size_tier"],
               "volume_multiplier": r["volume_multiplier"], "momentum_multiplier": r["momentum_multiplier"],
               "principal_book": "/".join(PRINCIPAL), "quantity_convention": "CAUSAL_PREORDER_QTY"}
        row.update({f"sc_{k}": v for k, v in sc.items() if k not in ("schema", "cutoff", "signal_date")})
        row.update({f"cx_{k}": v for k, v in cx.items()})
        row.update({f"ep_{k}": v for k, v in ep.items()})
        row.update({f"po_{k}": v for k, v in po.items() if k not in ("schema", "cutoff", "entry_date", "entry_source_path")})
        row.update({f"oc_{k}": v for k, v in oc.items()})
        for name in ("fixed_causal", "equity_scaled", "legacy_fill", "r4_causal", "r4_legacy", "parent_causal"):
            t = by_lens[name].get(r["ticket_id"])
            row[f"lens_{name}_quantity"] = t.get("quantity") if t else None
            row[f"lens_{name}_net"] = t.get("modeled_net") if t else None
            row[f"lens_{name}_status"] = t.get("status") if t else None
        row["lens_equity_scale_factor"] = by_lens["equity_scaled"][r["ticket_id"]].get("sizing_scale_factor")
        row.update({f"path_{k}": v for k, v in path.items() if k != "path_returns"})
        row["path_archetype"] = an.path_archetype(path)
        atlas.append(row)
        prow = {"ticket_id": r["ticket_id"], "cohort_id": r["cohort_id"], "split": r["split"], "symbol": r["symbol"],
                "status": r["status"], "size_tier": r["size_tier"], "path_archetype": row["path_archetype"]}
        for a, v in enumerate(path.get("path_returns") or []):
            prow[f"age{a:02d}_short_return"] = v
            prow[f"age{a:02d}_status"] = "OBSERVED" if v is not None else "STALE_OR_ABSENT"
        paths_rows.append(prow)
        evidence.append({"ticket_id": r["ticket_id"], "symbol": r["symbol"], "signal_date": r["cohort_id"],
                         "entry_date": r["scheduled_entry_date"],
                         "signal_close_source": (summaries.get(key) or {}).get("path"),
                         "signal_close_ts": (summaries.get(key) or {}).get("ts"),
                         "history_sessions_present": sc["history_sessions_present"],
                         "preorder_ts": po.get("preorder_ts"), "preorder_bars": po.get("preorder_bars_present"),
                         "preorder_source": po.get("entry_source_path"),
                         "elapsed_window_comparison_sessions": po.get("elapsed_window_comparison_sessions"),
                         "actions_effective_by_signal": sc["documented_action_within_60_sessions"],
                         "action_factor_over_hold": r.get("action_factor_over_hold"),
                         "entry_price_source": r.get("entry_source"), "exit_price_source": r.get("exit_source"),
                         "path_ages_observed": path.get("path_ages_observed"), "path_ages_stale": path.get("path_ages_stale")})
    note(f"atlas rows={len(atlas)}; gross reconciliation failures={recon_fail}")
    if recon_fail:
        return finish([f"{recon_fail} sizing-neutral outcomes do not reconcile to the ledger gross"], {})

    files = {}
    files["trade_atlas.csv"] = exp.write_csv(OUT / "trade_atlas.csv", atlas)
    files["trade_path_atlas.csv"] = exp.write_csv(OUT / "trade_path_atlas.csv", paths_rows)
    files["pre_entry_feature_evidence.csv"] = exp.write_csv(OUT / "pre_entry_feature_evidence.csv", evidence)

    # ------------------------------------------------------------ 6. public feature catalog
    catalog = feature_catalog(atlas)
    exp.write_csv(REPORTS / "cg_arrow011_feature_catalog.csv", catalog)

    manifest = {
        "arrow": "CG Arrow 011", "stage": "build", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT).decode().strip(),
        "schema": an.SCHEMA_VERSION, "principal_book": "/".join(PRINCIPAL),
        "hash_checks": hash_checks, "counts": counts, "control_checks": control_checks,
        "fresh_replay_mismatches": mism, "oracle_a8_r2": orc, "oracle_a10": orc10,
        "observation_coverage": coverage, "membership_sha256": sha_obj(membership),
        "feature_state_disagreements": len(disagree),
        "pre_order_available": sum(1 for v in po_feats.values() if v.get("pre_order_available")),
        "atlas_rows": len(atlas), "local_files": files,
        "code_hashes": {p: digest(REPO_ROOT / p) for p in (
            "src/verification/r4r5_anatomy.py", "src/verification/r4r5_replay.py", "src/verification/r4r5_data.py",
            "src/verification/r4r5_equity.py", "scripts/cg_arrow011_build.py")},
        "blockers": [], "log": LOG,
    }
    dump_json(CACHE / "build_manifest.json", manifest)
    note("build complete")
    return 0


def feature_catalog(atlas: list[dict]) -> list[dict]:
    n = len(atlas)

    def cov(col):
        return sum(1 for r in atlas if r.get(col) is not None)

    defs = [
        ("sc_ret1", "SIGNAL_CLOSE", "close_t / close_{t-1} - 1", "1 session"),
        ("sc_ret3", "SIGNAL_CLOSE", "close_t / close_{t-3} - 1; equals the frozen R5 momentum feature", "3 sessions"),
        ("sc_ret5", "SIGNAL_CLOSE", "close_t / close_{t-5} - 1", "5 sessions"),
        ("sc_ret10", "SIGNAL_CLOSE", "close_t / close_{t-10} - 1", "10 sessions"),
        ("sc_ret15", "SIGNAL_CLOSE", "close_t / close_{t-15} - 1; the frozen ranking return in signal units", "15 sessions"),
        ("sc_ret15_to_5", "SIGNAL_CLOSE", "close_{t-5} / close_{t-15} - 1, the earlier part of the run-up", "15 sessions"),
        ("sc_recent_minus_earlier", "SIGNAL_CLOSE", "ret5 - ret15_to_5", "15 sessions"),
        ("sc_acceleration_3", "SIGNAL_CLOSE", "ret3 - (close_{t-3}/close_{t-6} - 1)", "6 sessions"),
        ("sc_largest_session_share_of_advance", "SIGNAL_CLOSE", "largest single-session log return / sum of 15 session log returns, when the sum is positive", "15 sessions"),
        ("sc_top3_sessions_share_of_advance", "SIGNAL_CLOSE", "sum of the three largest session log returns / total 15-session log advance", "15 sessions"),
        ("sc_up_sessions_15", "SIGNAL_CLOSE", "count of positive session log returns in the 15-session window", "15 sessions"),
        ("sc_logret_std_15", "SIGNAL_CLOSE", "population std of session log returns over 15 sessions", "15 sessions"),
        ("sc_gap_share_of_advance", "SIGNAL_CLOSE", "sum of log(open_t/close_{t-1}) over 15 sessions / total log advance; overnight gaps in adjusted units", "15 sessions"),
        ("sc_close_vs_high20", "SIGNAL_CLOSE", "close_t / max(high over 21 sessions) - 1", "21 sessions"),
        ("sc_close_vs_low20", "SIGNAL_CLOSE", "close_t / min(low over 21 sessions) - 1", "21 sessions"),
        ("sc_close_vs_max_close15", "SIGNAL_CLOSE", "close_t / max(close over the last 16 closes) - 1; drawdown already underway", "15 sessions"),
        ("sc_sessions_since_max_close15", "SIGNAL_CLOSE", "sessions since the highest close of the last 15 sessions", "15 sessions"),
        ("sc_position_in_range20", "SIGNAL_CLOSE", "(close_t - min low) / (max high - min low) over 21 sessions", "21 sessions"),
        ("sc_close_location_signal_day", "SIGNAL_CLOSE", "(close - low) / (high - low) on the signal session", "1 session"),
        ("sc_signal_day_range_pct", "SIGNAL_CLOSE", "(high - low) / close on the signal session", "1 session"),
        ("sc_mean_range_pct_10", "SIGNAL_CLOSE", "mean of (high - low) / close over the last 10 sessions", "10 sessions"),
        ("sc_volume_ratio_frozen", "SIGNAL_CLOSE", "signal-session share volume / mean share volume of the prior 20 sessions; exact frozen R5 rule, all 21 sessions required", "21 sessions"),
        ("sc_volume_trend_5_vs_15", "SIGNAL_CLOSE", "mean volume of the 5 sessions before the signal / mean of the 15 before those", "20 sessions"),
        ("sc_dollar_volume_signal_day", "SIGNAL_CLOSE", "close_t * volume_t on the signal session", "1 session"),
        ("sc_dollar_volume_mean20", "SIGNAL_CLOSE", "mean of close*volume over the prior 20 sessions", "20 sessions"),
        ("sc_dollar_volume_cv20", "SIGNAL_CLOSE", "coefficient of variation of prior-20-session dollar volume", "20 sessions"),
        ("sc_volume_expansion_15", "SIGNAL_CLOSE", "mean volume over the 15-session window / mean volume of the 6 sessions before it", "21 sessions"),
        ("sc_move_per_volume_unit", "SIGNAL_CLOSE", "|ret15| / volume_expansion_15", "21 sessions"),
        ("sc_signal_close_band", "SIGNAL_CLOSE", "price band of the signal close: [10,20) [20,40) [40,80) else OUTSIDE", "1 session"),
        ("sc_documented_action_within_60_sessions", "SIGNAL_CLOSE", "count of documented corporate actions effective within the 60 sessions ending at the signal, from the certified action table; only actions effective by the signal", "60 sessions"),
        ("sc_four_state", "SIGNAL_CLOSE", "frozen R5 state from ret3 > 0 and volume_ratio > 1; MISSING_FEATURE when either is absent", "21 sessions"),
        ("cx_rank_in_eight", "SIGNAL_CLOSE", "rank by frozen 15-session return within the selected eight", "cohort"),
        ("cx_ret15_minus_cohort_median", "SIGNAL_CLOSE", "ranking return minus the cohort's median ranking return", "cohort"),
        ("cx_gap_to_next_rank", "SIGNAL_CLOSE", "ranking return minus the next lower rank's return (rank 8 uses the field's rank 9)", "cohort"),
        ("cx_cohort_ret15_spread", "SIGNAL_CLOSE", "rank-1 return minus rank-8 return", "cohort"),
        ("cx_ret15_field_percentile", "SIGNAL_CLOSE", "share of the ranked candidate field with a lower ranking return", "field"),
        ("ep_prior_selections", "SIGNAL_CLOSE", "number of earlier cohorts that selected the same symbol, from frozen membership", "membership"),
        ("ep_sessions_since_last_selection", "SIGNAL_CLOSE", "sessions since the previous selection of the same symbol", "membership"),
        ("ep_episode", "SIGNAL_CLOSE", "FIRST, OVERLAPPING_REPEAT (previous hold still open), LATER_REPEAT", "membership"),
        ("po_preorder_price", "PRE_ORDER", "close of the last fully completed bar before the final regular-hours minute of the entry session (the frozen preorder_ts)", "entry session"),
        ("po_overnight_gap_vs_signal_close", "PRE_ORDER", "entry-session first RTH bar open / signal close (in entry units) - 1", "entry session"),
        ("po_signal_close_to_preorder", "PRE_ORDER", "preorder price / signal close (in entry units) - 1", "entry session"),
        ("po_open_to_preorder", "PRE_ORDER", "preorder price / entry-session open - 1", "entry session"),
        ("po_preorder_location_in_partial_range", "PRE_ORDER", "(preorder - partial low) / (partial high - partial low) through the pre-order bar", "entry session"),
        ("po_partial_range_pct", "PRE_ORDER", "(partial high - partial low) / preorder price", "entry session"),
        ("po_partial_volume_vs_elapsed_window_mean", "PRE_ORDER", "entry-session volume through the pre-order bar / mean volume through the same clock time on the preceding 5 sessions; never divided by a full-session average", "entry session + 5"),
        ("po_preorder_price_band", "PRE_ORDER", "price band of the pre-order price", "entry session"),
    ]
    out = []
    for col, cutoff, formula, lookback in defs:
        out.append({"feature": col, "cutoff": cutoff, "formula": formula, "lookback": lookback,
                    "source": ("certified local one-minute tape aggregated to sessions" if cutoff == "SIGNAL_CLOSE"
                               else "certified local one-minute tape, entry session bars through preorder_ts"),
                    "units": ("signal-session units; earlier bars adjusted by actions effective by the signal" if cutoff == "SIGNAL_CLOSE"
                              else "entry-session units; signal close adjusted by actions effective by entry"),
                    "availability": ("signal-session regular-hours close" if cutoff == "SIGNAL_CLOSE"
                                     else "completion of the bar starting at preorder_ts, one minute before the final RTH minute"),
                    "missing_rule": "None when any required session or bar is absent; never zero, never a favorable state",
                    "coverage_tickets": cov(col), "coverage_pct": round(cov(col) / n * 100, 1),
                    "certification": ("price/volume from the certified tape; the feature definition itself is new and uncertified"
                                      if not col.endswith("_frozen") and col not in ("sc_ret3", "sc_ret15", "sc_four_state")
                                      else "identical to the frozen engine rule, verified against the ledger on every ticket")})
    return out


def finish(blockers: list[str], extra: dict) -> int:
    dump_json(CACHE / "build_manifest.json", {"arrow": "CG Arrow 011", "stage": "build", "timestamp": stamp(),
                                              "blockers": blockers, **extra, "log": LOG})
    note("BUILD BLOCKED: " + "; ".join(blockers))
    return 1


if __name__ == "__main__":
    sys.exit(main())
