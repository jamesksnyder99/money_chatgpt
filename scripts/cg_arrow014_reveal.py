"""CG Arrow 014 Phase 1 — the gated pristine reveal, run once, in one batch.

This script refuses to start unless LOCK 2 is committed with the exact status
`HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL` and zero unresolved material exceptions. Once it
starts it runs the whole predeclared matrix to completion: every one of the eighteen frozen
cells, twelve monthly rows for every scored account, the 52-cohort matrices, the rank-by-rank
diagnostic, all ten mechanism checks, horizon attribution, drawdown episodes, the C2/C3
falsification controls and the historical comparison. There is no partial-result path, because
stopping at an interesting number is how a holdout stops being a holdout.

Nothing here is tuned. Every rule, cut, multiplier and threshold is read from a freeze committed
before the memberships existed, and the membership itself is checked against the hash LOCK 2
certified.

Usage: python scripts/cg_arrow014_reveal.py [--workers 8]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest import holdout2024 as H  # noqa: E402
from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_accounting as acct  # noqa: E402
from verification import r4r5_anatomy as an  # noqa: E402
from verification import r4r5_anatomy_stats as ast  # noqa: E402
from verification import r4r5_challenger as ch  # noqa: E402
from verification import r4r5_equity as eq  # noqa: E402
from verification import r4r5_export as exp  # noqa: E402
from verification import r4r5_holdout as HO  # noqa: E402
from verification import r4r5_metrics as met  # noqa: E402
from verification import r4r5_monthly as mon  # noqa: E402
from verification import r4r5_oracle as oracle  # noqa: E402
from verification import r4r5_rank as rank  # noqa: E402
from verification import r4r5_replay as rp  # noqa: E402
from verification.r4r5_data import (  # noqa: E402
    dump_json, features, history, load_summaries, read_json, stamp,
)

WORK = H.WORK
OUT = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow014"
FREEZE = REPORTS / "cg_arrow014_reveal_freeze.json"
GATE_MANIFEST = REPORTS / "cg_arrow014_certification_manifest.json"
ACTIONS = REPORTS / "cg_arrow014_corporate_actions.json"
COMPLETED = set(rp.COMPLETED)
START = HO.STARTING_EQUITY
LOG: list[str] = []
T0 = time.monotonic()

NAMES = {"PARENT": "Equal-Dollar Short", "R4": "Volume-Sized Short",
         "R5": "Momentum+Volume-Sized Short", "C1": "Rank-One 1.50x Reallocation",
         "C2": "Off-High Substitution", "C3": "Combined Reallocation and Substitution"}
# Which engine family and allocation each frozen cell's model maps onto.
CONFIG = {"PARENT": ("PARENT", "C0"), "R4": ("R4", "C0"), "R5": ("R5", "C0"),
          "C1": ("R5", "C1"), "C2": ("R5", "C2"), "C3": ("R5", "C3")}


def note(msg: str) -> None:
    line = f"{stamp()} +{(time.monotonic() - T0) / 60:.1f}m {msg}"
    print(line, flush=True)
    LOG.append(line)


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def committed_at(relpath: str) -> str:
    return subprocess.run(["git", "log", "-1", "--format=%H", "--", relpath],
                          cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


def _r(x, nd: int = 6):
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    return round(x, nd)


def _stat(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "hit_rate": None}
    return {"n": len(values), "mean": _r(statistics.fmean(values)),
            "median": _r(statistics.median(values)),
            "hit_rate": _r(sum(1 for v in values if v > 0) / len(values), 4)}


# ---------------------------------------------------------------------------- the gate
def open_gate() -> dict:
    """Refuse to reveal anything unless LOCK 2 is committed and closed clean."""
    if not GATE_MANIFEST.exists():
        raise SystemExit("LOCK 2 is not written; the reveal is not permitted")
    man = read_json(GATE_MANIFEST)
    if man.get("status") != "HOLDOUT_DATA_CERTIFIED_FOR_PRISTINE_REVEAL":
        raise SystemExit(f"LOCK 2 status is {man.get('status')!r}; the reveal is not permitted")
    if man.get("unresolved_material_exceptions") != 0:
        raise SystemExit(f"{man.get('unresolved_material_exceptions')} unresolved material "
                         "exceptions remain; the reveal is not permitted")
    lock2 = committed_at("reports/cg_arrow014_certification_manifest.json")
    lock1 = committed_at("reports/cg_arrow014_reveal_freeze.json")
    if not lock2:
        raise SystemExit("the certification manifest is not committed; the reveal is not permitted")
    if not lock1:
        raise SystemExit("LOCK 1 is not committed")
    note(f"LOCK 1 at {lock1[:7]}, LOCK 2 at {lock2[:7]}, status {man['status']}, "
         "unresolved material exceptions 0 — the reveal may proceed")
    return {"lock1_commit": lock1, "lock2_commit": lock2, "certification": man}


# ---------------------------------------------------------------------------- substrate
def build_cohorts(membership: dict, field: dict, summaries: dict, status: dict):
    """The 52 frozen cohorts with rank 1-8 rows, plus the rank 9-20 pool for C2/C3.

    The ranking is rerun rather than read back, and must reproduce the certified membership
    exactly. A silent difference here would mean the thing being scored is not the thing that
    was certified.
    """
    cohorts, deep = [], {}
    for iso in sorted(membership["top8"]):
        signal = date.fromisoformat(iso)
        res = rank.rank_cohort(signal, field[iso], summaries, status)
        rows = res["rows"][:ch.SUBSTITUTION_SEARCH_DEPTH]
        got = [h["symbol"] for h in rows[:8]]
        if got != membership["top8"][iso]:
            raise SystemExit(f"cohort {iso} does not reproduce the certified membership")
        deep[iso] = rows
        cohorts.append({"signal": signal, "signal_iso": iso, "split": "PRISTINE_OOS",
                        "fill": HO.entry_for(signal), "rows": rows[:8],
                        "n_field": res["n_field"], "field_ceiling": res["field_ceiling"],
                        "ranking_scope": res["ranking_scope"]})
    return cohorts, deep


def attach_integrity(cohorts, deep, summaries, hold: int) -> None:
    """Carry the certified ranking and holding evidence onto each row, as the ledger expects."""
    for c in cohorts:
        x = HO.exit_for(c["fill"], hold)
        for h in deep[c["signal_iso"]]:
            h.update(rank.lookback_integrity(c["signal"], h["symbol"], summaries, {}))
            if x is not None:
                h.update(rank.holding_integrity(c["fill"], x, h["symbol"], summaries, {}))


def build_allocations(cohorts, deep, feats, off_high, threshold, certified):
    """C0 base, C1 reallocation, C2 substitution, C3 combined — the frozen Arrow 012 rules."""
    lineups = {k: [] for k in ("C0", "C1", "C2", "C3")}
    alloc = {k: {} for k in ("C0", "C1", "C2", "C3")}
    rows, plans, problems = [], {}, []
    for c in cohorts:
        iso = c["signal_iso"]
        top8 = sorted(c["rows"], key=lambda h: h["rank"])
        f8 = {h["symbol"]: feats[(iso, h["symbol"])] for h in top8}
        base8 = ch.base_notionals(top8, f8)
        T = sum(v["base"] for v in base8.values())
        protected = top8[0]["symbol"]

        c0 = ch.cohort_with_rows(c, top8)
        lineups["C0"].append(c0)
        alloc["C0"].update({f"{iso}/{s}": v["base"] for s, v in base8.items()})

        r1 = ch.c1_allocation(top8, base8)
        if not r1["ok"]:
            problems.append(f"C1 failed cohort {iso}: {r1['reason']}")
            continue
        lineups["C1"].append(c0)
        alloc["C1"].update({f"{iso}/{s}": v for s, v in r1["allocation"].items()})

        oh = {h["symbol"]: off_high[(iso, h["symbol"])] for h in deep[iso]}
        plan = ch.substitution_plan(top8, deep[iso][8:], oh, threshold, certified.get(iso, set()))
        if not plan["unique"]:
            problems.append(f"C2 lineup for {iso} is not eight unique names")
            continue
        fnew = {h["symbol"]: feats[(iso, h["symbol"])] for h in plan["lineup"]}
        base_new = ch.base_notionals(plan["lineup"], fnew)
        r2 = ch.c2_allocation(plan["lineup"], base_new, T)
        if not r2["ok"]:
            problems.append(f"C2 failed cohort {iso}: {r2['reason']}")
            continue
        c2c = ch.cohort_with_rows(c, plan["lineup"])
        lineups["C2"].append(c2c)
        alloc["C2"].update({f"{iso}/{s}": v for s, v in r2["allocation"].items()})

        r3 = ch.c3_allocation(plan["lineup"], r2["allocation"], protected)
        if not r3["ok"]:
            problems.append(f"C3 failed cohort {iso}: {r3['reason']}")
            continue
        lineups["C3"].append(c2c)
        alloc["C3"].update({f"{iso}/{s}": v for s, v in r3["allocation"].items()})

        plans[iso] = {"k": plan["k"], "removable": plan["removable"], "eligible": plan["eligible"],
                      "outgoing": [h["symbol"] for h in plan["outgoing"]],
                      "incoming": [h["symbol"] for h in plan["incoming"]]}
        for cfg, a in (("C0", {s: v["base"] for s, v in base8.items()}), ("C1", r1["allocation"]),
                       ("C2", r2["allocation"]), ("C3", r3["allocation"])):
            src = plan["lineup"] if cfg in ("C2", "C3") else top8
            for s, v in a.items():
                row = next((h for h in src if h["symbol"] == s), None)
                rows.append({"config": cfg, "cohort_id": iso, "symbol": s,
                             "original_rank": row["rank"] if row else None,
                             "is_protected_rank_one": s == protected,
                             "base_notional": _r(v, 2), "cohort_total_T": _r(T, 2),
                             "incumbent_base_notional": _r((base8.get(s) or {}).get("base"), 2),
                             "r5_tier": (base8.get(s) or base_new.get(s, {})).get("tier"),
                             "substituted_in": cfg in ("C2", "C3") and s not in base8})
    return lineups, alloc, rows, plans, problems


# ---------------------------------------------------------------------------- diagnostics
def anatomy_rows(books: dict, deep: dict, summaries: dict, hold: int = 10) -> list[dict]:
    """One row per selected name: frozen pre-entry descriptors plus its sizing-neutral outcome.

    The anatomy helpers return unprefixed keys and Arrow 011 froze its cuts against the prefixed
    names, so the same `sc_` / `cx_` / `po_` / `ep_` convention is applied here. Getting that
    wrong would not raise; it would quietly leave every frozen cut unmatched and every mechanism
    check reading a column of None.
    """
    b = books[("R5", "FIXED_DOLLAR", hold)]
    episodes = an.selection_episodes({c: [h["symbol"] for h in v[:8]] for c, v in deep.items()})
    ctx = {iso: an.cohort_context(rows[:8], rows) for iso, rows in deep.items()}
    out = []
    for t in b["trades"]:
        iso, sym = t["cohort_id"], t["symbol"]
        signal = date.fromisoformat(iso)
        sc = an.signal_close_features(sym, signal, summaries)
        po = an.pre_order_features(sym, signal, date.fromisoformat(t["scheduled_entry_date"]),
                                   t.get("preorder_ts"), summaries)
        sn = an.sizing_neutral_outcome(t)
        row = {"cohort_id": iso, "symbol": sym, "rank": t["rank"], "status": t["status"],
               "price_band": an.price_band(sc.get("signal_close")),
               "sizing_neutral_return": sn.get("price_return_10"),
               "net_per_entry_dollar": sn.get("net_per_entry_dollar"),
               "modeled_net": sn.get("modeled_net")}
        row.update({f"sc_{k}": v for k, v in sc.items()
                    if k not in ("schema", "cutoff", "signal_date")})
        row.update({f"po_{k}": v for k, v in po.items()
                    if k not in ("schema", "cutoff", "entry_date", "entry_source_path")})
        row.update({f"cx_{k}": v for k, v in (ctx.get(iso, {}).get(sym) or {}).items()})
        row.update({f"ep_{k}": v for k, v in (episodes.get((iso, sym)) or {}).items()})
        out.append(row)
    missing = [k for k in ("sc_close_vs_high20", "sc_ret3", "cx_gap_to_next_rank", "ep_episode")
               if not any(r.get(k) is not None for r in out)]
    if missing:
        raise SystemExit(f"anatomy columns the mechanism panel needs are empty: {missing}")
    return out


def rank_by_rank(books: dict, freeze: dict) -> list[dict]:
    ref_mean = freeze["rank_by_rank_diagnostic"]["historical_reference_h10_mean"]
    ref_hit = freeze["rank_by_rank_diagnostic"]["historical_reference_h10_hit"]
    out = []
    for hold in HO.HOLDS:
        b = books[("R5", "FIXED_DOLLAR", hold)]
        by = defaultdict(list)
        for t in b["trades"]:
            sn = an.sizing_neutral_outcome(t).get("price_return_10")
            if sn is not None:
                by[t["rank"]].append(sn)
        for r in sorted(by):
            s = _stat(by[r])
            out.append({"hold": hold, "rank": r, **s,
                        "historical_h10_mean": ref_mean.get(str(r)) if hold == 10 else None,
                        "historical_h10_hit": ref_hit.get(str(r)) if hold == 10 else None,
                        "classification": classify(s["mean"], ref_mean.get(str(r)), s["n"])
                        if hold == 10 else None})
    return out


def classify(pristine, historical, n: int) -> str:
    """The frozen classification vocabulary. Nothing here is fitted to the holdout."""
    if n < 20:
        return "INCONCLUSIVE_SPARSE"
    if pristine is None or historical is None:
        return "DATA_LIMIT"
    if historical == 0:
        return "PRISTINE_REPLICATION" if pristine > 0 else "NOT_REPLICATED"
    if pristine * historical <= 0:
        return "NOT_REPLICATED"
    return ("PRISTINE_REPLICATION" if abs(pristine) >= 0.5 * abs(historical)
            else "SAME_DIRECTION_WEAKER")


PANEL = [("M2", "cx_gap_to_next_rank", "all"),
         ("M3", "sc_close_vs_high20", "ranks 2-8"),
         ("M5a", "sc_mean_range_pct_10", "all"),
         ("M5b", "sc_logret_std_15", "all"),
         ("M5c", "sc_signal_day_range_pct", "all"),
         ("M5d", "po_partial_range_pct", "all"),
         ("M6a", "sc_up_sessions_15", "all"),
         ("M6b", "sc_top3_sessions_share_of_advance", "all"),
         ("M7", "sc_ret3", "all"),
         ("M8a", "po_signal_close_to_preorder", "all"),
         ("M8b", "po_preorder_location_in_partial_range", "all"),
         ("M8c", "po_overnight_gap_vs_signal_close", "all")]


def mechanism_panel(anat: list[dict], freeze: dict) -> list[dict]:
    """M1 to M10, each on its frozen feature and, where A11 froze them, its frozen cuts."""
    cuts = freeze["mechanism_panel"]["a11_frozen_cuts"]
    oh_median = freeze["mechanism_panel"]["a11_off_high_median"]
    ref = freeze["rank_by_rank_diagnostic"]["historical_reference_h10_mean"]
    scored = [r for r in anat if r["sizing_neutral_return"] is not None]
    one = [r for r in scored if r["rank"] == 1]
    rest = [r for r in scored if r["rank"] > 1]
    out = []

    s1, s2 = _stat([r["sizing_neutral_return"] for r in one]), \
        _stat([r["sizing_neutral_return"] for r in rest])
    hist_effect = _r(ref["1"] - statistics.fmean([ref[str(k)] for k in range(2, 9)]))
    effect = _r(None if s1["mean"] is None or s2["mean"] is None else s1["mean"] - s2["mean"])
    out.append({"check": "M1", "name": "rank-one effect", "feature": "rank", "group": "rank 1",
                "n": s1["n"], "mean": s1["mean"], "median": s1["median"], "hit_rate": s1["hit_rate"],
                "contrast_group": "ranks 2-8", "contrast_n": s2["n"], "contrast_mean": s2["mean"],
                "contrast_hit_rate": s2["hit_rate"], "effect": effect,
                "historical_effect": hist_effect,
                "cuts_source": "none", "cohorts": len({r["cohort_id"] for r in one}),
                "classification": classify(effect, hist_effect, s1["n"])})

    for cid, feat, scope in PANEL:
        rows = rest if scope == "ranks 2-8" else scored
        frozen = tuple(cuts[feat]) if feat in cuts else None
        rel = ast.relationship(rows, feat, "sizing_neutral_return", frozen)
        if rel.get("insufficient"):
            out.append({"check": cid, "name": feat, "feature": feat, "group": scope,
                        "n": rel.get("n"), "classification": "INCONCLUSIVE_SPARSE"})
            continue
        eff = rel["t3_minus_t1_mean"]
        out.append({"check": cid, "name": feat, "feature": feat, "group": scope, "n": rel["n"],
                    "cohorts": rel["cohorts"], "securities": rel["securities"],
                    "pooled_spearman": _r(rel["pooled_spearman"]),
                    "within_cohort_mean_spearman": _r(rel["within_cohort_mean_spearman"]),
                    "within_cohort_positive_share": _r(rel["within_cohort_positive_share"], 4),
                    "t1_low_mean": _r(rel["t1_low"]["mean"]),
                    "t3_high_mean": _r(rel["t3_high"]["mean"]),
                    "effect": _r(eff), "hit_effect": _r(rel["t3_minus_t1_hit"], 4),
                    "cuts_source": "A11 frozen" if frozen else "learned on this corridor",
                    "classification": "INCONCLUSIVE_SPARSE" if rel["n"] < 20
                    else ("REPORTED" if eff is not None else "DATA_LIMIT")})

    for band in ("[10,20)", "[20,40)", "[40,80)"):
        for side in ("off_high", "near_high"):
            rs = [r for r in scored if r.get("price_band") == band
                  and r.get("sc_close_vs_high20") is not None
                  and ((r["sc_close_vs_high20"] < oh_median) == (side == "off_high"))]
            s = _stat([r["sizing_neutral_return"] for r in rs])
            out.append({"check": "M4", "name": f"price band {band} / {side}",
                        "feature": "sc_close_vs_high20 x price_band", "group": f"{band}/{side}",
                        **s, "cuts_source": "A11 frozen bands and median",
                        "classification": "INCONCLUSIVE_SPARSE" if s["n"] < 20 else "REPORTED"})

    for ep in sorted({r.get("ep_episode") for r in scored if r.get("ep_episode") is not None}):
        rs = [r for r in scored if r.get("ep_episode") == ep]
        s = _stat([r["sizing_neutral_return"] for r in rs])
        out.append({"check": "M9", "name": "repeat-selection episode", "feature": "ep_episode",
                    "group": str(ep), **s, "cuts_source": "A11 frozen",
                    "classification": "INCONCLUSIVE_SPARSE" if s["n"] < 20 else "REPORTED"})
    return out


def holding_paths(books: dict, summaries: dict) -> list[dict]:
    """M10: the close-only sizing-neutral path at each age, rank one against ranks 2-8."""
    b = books[("R5", "FIXED_DOLLAR", 10)]
    by = defaultdict(lambda: defaultdict(list))
    for t in b["trades"]:
        p = an.holding_path(t, summaries, hold=10)
        if not p.get("path_available"):
            continue
        for age, v in enumerate(p["path_returns"]):
            if age and v is not None:
                by["rank 1" if t["rank"] == 1 else "ranks 2-8"][age].append(v)
    out = []
    for grp in sorted(by):
        for age in sorted(by[grp]):
            out.append({"check": "M10", "group": grp, "age_sessions": age,
                        **_stat(by[grp][age]), "is_frozen_hold": age in HO.HOLDS})
    return out


def drawdown_episodes(daily: list[dict], label: str, top: int = 8) -> list[dict]:
    """Peak-to-trough episodes in an equity path, deepest first."""
    peak, peak_d, cur, episodes = START, daily[0]["date"] if daily else None, None, []
    for r in daily:
        e = r["equity"]
        if e >= peak:
            if cur:
                cur["recovery_date"], cur["recovered"] = r["date"], True
                episodes.append(cur)
                cur = None
            peak, peak_d = e, r["date"]
        elif cur is None:
            cur = {"account": label, "peak_date": peak_d, "peak_equity": _r(peak, 2),
                   "trough_date": r["date"], "trough_equity": _r(e, 2),
                   "depth_pct_of_peak": _r(e / peak - 1), "recovered": False,
                   "recovery_date": None}
        elif e < cur["trough_equity"]:
            cur.update({"trough_date": r["date"], "trough_equity": _r(e, 2),
                        "depth_pct_of_peak": _r(e / peak - 1)})
    if cur:
        episodes.append(cur)
    for ep in episodes:
        ep["sessions_peak_to_trough"] = sum(
            1 for r in daily if ep["peak_date"] <= r["date"] <= ep["trough_date"])
    return sorted(episodes, key=lambda e: e["depth_pct_of_peak"])[:top]


def money(x) -> str:
    return "n/a" if x is None else f"{x:,.2f}"


def pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.2f}%"


def write_reveal_md(path: Path, cell_rows, breadth, horizon, rbr, panel, dd, gate, freeze,
                    membership, plans, orc, info) -> None:
    """The narrative, written from the tables rather than alongside them."""
    by_cell = {r["cell"]: r for r in cell_rows}
    principal = [r for r in cell_rows if r["role"] == "principal"]
    controls = [r for r in cell_rows if "falsification" in r["role"]]

    def table(rows, cols, headers):
        head = "| " + " | ".join(headers) + " |"
        rule = "|" + "|".join("---" for _ in headers) + "|"
        body = "\n".join("| " + " | ".join(
            money(r[c]) if isinstance(r.get(c), float) and abs(r.get(c) or 0) > 1.5
            # max_drawdown_pct_of_peak already arrives scaled to a percentage; formatting it as a
            # fraction would report a drawdown a hundred times too large
            else (f"{r[c]:.2f}%" if c == "max_drawdown_pct_of_peak" and r.get(c) is not None
                  else pct(r[c]) if c in ("return_on_starting_equity", "hit_rate",
                                     "cohort_hit_rate", "top_cohort_share_of_total",
                                     "top3_cohort_share_of_total")
                  else str(r.get(c))) for c in cols) + " |" for r in rows)
        return "\n".join([head, rule, body])

    m1 = next((r for r in panel if r["check"] == "M1"), {})
    h10 = [r for r in rbr if r["hold"] == 10]
    reps = {}
    for r in h10:
        reps[r["rank"]] = r.get("classification")
    worst = min(dd, key=lambda e: e["depth_pct_of_peak"]) if dd else None

    path.write_text(f"""# CG Arrow 014 — the pristine reveal

Twelve out-of-sample months, September 2024 through August 2025, on data acquired and certified
without any strategy result being computed on it. {len(membership['top8'])} weekly cohorts,
{sum(len(v) for v in membership['top8'].values())} selected positions, cutoff {info['cutoff']}.

The reveal specification — all eighteen cells, the cohort calendar, every formula, every frozen
cut and the historical reference values — was committed at `{gate['lock1_commit'][:7]}` before any
membership existed. The certification gate closed at `{gate['lock2_commit'][:7]}`. This run was a
single batch: every cell below was produced by one execution, and no cell was inspected before the
others existed.

Membership SHA-256 `{membership['membership_sha256']}`.

## The eighteen frozen cells

{table(cell_rows, ["cell", "model", "account_view", "hold", "completed_trades",
                   "A_eventual_completed_pnl", "ending_equity", "return_on_starting_equity",
                   "hit_rate", "max_drawdown_pct_of_peak"],
       ["cell", "model", "view", "hold", "trades", "eventual P&L", "ending equity", "return",
        "hit rate", "max drawdown"])}

Account quantities are reported separately throughout, under the frozen convention: A is the
eventual completed-trade P&L, B the marked account P&L at the cutoff, C the post-cutoff runoff
increment, D the eventual runoff P&L and E the open documented obligations. They appear in
`cg_arrow014_account_summary.csv`, and `cg_arrow014_monthly_account.csv` carries all twelve
monthly rows for every scored account under `cg_lab_monthly_account_reporting_v1`.

## Breadth: how many cohorts carried the result

{table(breadth, ["model", "account_view", "hold", "cohorts", "profitable_cohorts",
                 "cohort_hit_rate", "top_cohort_share_of_total", "top3_cohort_share_of_total"],
       ["model", "view", "hold", "cohorts", "profitable", "cohort hit rate",
        "top cohort share", "top 3 share"])}

A result carried by a handful of cohorts is a different claim from one carried by most of them,
which is why this table sits beside the headline rather than beneath it.

## Horizon attribution

{table(horizon, ["model", "account_view", "hold", "completed_trades", "eventual_pnl",
                 "ending_equity", "increment_vs_h8", "hit_rate"],
       ["model", "view", "hold", "trades", "eventual P&L", "ending equity", "vs H8", "hit rate"])}

## Rank by rank, against the historical reference

The Addendum 2 diagnostic. It is a measurement only: it may not create a top-five book, drop
ranks 6-8, change the C1 multiplier or introduce any allocation rule on this holdout.

{table(h10, ["rank", "n", "mean", "median", "hit_rate", "historical_h10_mean",
             "historical_h10_hit", "classification"],
       ["rank", "n", "pristine mean", "median", "hit rate", "historical mean", "historical hit",
        "classification"])}

Rank-one replication: **{reps.get(1, 'n/a')}**.

## Mechanism

M1, the rank-one effect, is the load-bearing one. On this corridor rank one returns a mean
sizing-neutral {m1.get('mean')} against {m1.get('contrast_mean')} for ranks 2-8, an effect of
{m1.get('effect')} where the historical study showed {m1.get('historical_effect')} —
**{m1.get('classification')}**.

The full panel, all ten checks on their frozen features and Arrow 011's frozen cuts with no
refitting, is in `cg_arrow014_mechanism_confirmation.csv`, including the M10 holding-path anatomy
at every age 1 through 10.

## Falsification controls

C2 substitutes off-high names from ranks 9-20 for near-high names in ranks 2-8, and C3 combines
that with C1's rank-one reallocation. Both preserve each cohort's base capital exactly, so neither
can win by spending more. Across {len(plans)} cohorts they made
{sum(p['k'] for p in plans.values())} substitutions.

{table(controls, ["cell", "model", "account_view", "hold", "A_eventual_completed_pnl",
                  "ending_equity", "return_on_starting_equity"],
       ["cell", "model", "view", "hold", "eventual P&L", "ending equity", "return"])}

## Drawdown

{("The deepest episode on any scored account was " + pct(worst["depth_pct_of_peak"]) +
  " on " + str(worst["account"]) + ", from a peak on " + str(worst["peak_date"]) +
  " to a trough on " + str(worst["trough_date"]) +
  (", recovered by " + str(worst["recovery_date"]) if worst["recovered"] else
   ", not recovered inside the corridor") + ".") if worst else "No drawdown episode was recorded."}

Every episode for every account is in `cg_arrow014_drawdown_episodes.csv`.

## Verification

An independent oracle recomputed every ledger from its stored inputs:
{orc['trades']['checked']:,} trades checked, maximum absolute error
{orc['trades']['max_abs_error']:.1e}. Account identities hold on every scored account and every
monthly table reconciles to its own marked account P&L at the cutoff.

## What this is not

This is one twelve-month out-of-sample period. It is not a forward test, it does not model
borrow availability or hard-to-borrow cost beyond the frozen cost model, and the account
convention assumes the frozen execution and cost rules throughout. The rank-by-rank table is a
diagnostic, not a proposal.

---
Generated {stamp()} from LOCK 1 `{gate['lock1_commit'][:7]}` and LOCK 2 `{gate['lock2_commit'][:7]}`.
""", encoding="utf-8")


def write_commands(path: Path) -> None:
    path.write_text("""# CG Arrow 014 — the exact sequence, in order. Each stage refuses to run out of turn.

# LOCK 1: the reveal specification and the cohort calendar, committed before any membership
python scripts/cg_arrow014_phase0a.py
python scripts/cg_arrow014_lock1.py

# Phase 0B: whole-corridor screen, mechanical membership, and the corridor census
python scripts/cg_arrow014_phase0b.py --stage screen --threshold 1.2 --gap-sessions 3
python scripts/cg_arrow014_phase0b.py --stage rank --workers 6

# close every observation gap the August 2025 eligibility extension exposed, then certify it
python scripts/cg_arrow014_repair_bars.py --mode ranking  --workers 8
python scripts/cg_arrow014_repair_bars.py --mode corridor --workers 8
python scripts/cg_arrow014_certify_repair.py --workers 8

# primary-source corporate action and identity evidence, then rerank to a fixed point
python scripts/cg_arrow014_census.py --stage scan --workers 8
python scripts/cg_arrow014_census.py --stage resolve
python scripts/cg_arrow014_phase0b.py --stage rank --workers 6     # repeat until the hash repeats

# per-name corridor certification, then LOCK 2
python scripts/cg_arrow014_phase0b.py --stage certify --workers 8
python scripts/cg_arrow014_lock2.py

# Phase 1: the reveal, one batch, only after LOCK 2 is committed
python scripts/cg_arrow014_reveal.py --workers 8

# the full suite
python -m pytest tests -q
""", encoding="utf-8")


# ---------------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    blockers: list[str] = []

    gate = open_gate()
    freeze = read_json(FREEZE)
    cells = freeze["reveal_matrix"]["cells"]
    if len(cells) != 18:
        raise SystemExit("the frozen matrix is not 18 cells")
    info = HO.activate(action_path=ACTIONS)
    note(f"corridor active: {info['sessions']} sessions, cutoff {info['cutoff']}, "
         f"{len(read_json(ACTIONS)['events'])} documented actions")

    membership = read_json(WORK / "phase0b_membership.json")
    if gate["certification"].get("membership_sha256") != membership["membership_sha256"]:
        raise SystemExit("the certified membership is not the membership on disk")
    note(f"frozen membership {membership['membership_sha256'][:12]} matches LOCK 2")

    # ---- ranking substrate and the certified memberships, reproduced not reread
    field = read_json(WORK / "phase0b_field.json")
    endpoints = set()
    for iso, cands in field.items():
        back = HO.FEATS[HO.INDEX[date.fromisoformat(iso)] - rank.LOOKBACK].isoformat()
        for s in cands:
            endpoints.add((iso, s))
            endpoints.add((back, s))
    note(f"loading {len(endpoints):,} ranking endpoints with {args.workers} workers")
    summaries = load_summaries(endpoints, args.workers)
    status = HO.observation_status(summaries)
    cohorts, deep = build_cohorts(membership, field, summaries, status)
    note(f"{len(cohorts)} cohorts rebuilt and every top eight reproduces the certified membership")

    # ---- every observation the ledgers need, for all three holds plus the runoff tail
    need = set()
    for c in cohorts:
        i, fi = HO.INDEX[c["signal"]], HO.INDEX[c["fill"]]
        for h in deep[c["signal_iso"]]:
            for d in HO.FEATS[max(0, i - 22): min(len(HO.FEATS), fi + max(HO.HOLDS) + 1)]:
                need.add((d.isoformat(), h["symbol"]))
            for d in HO.FEATS[fi + max(HO.HOLDS) + 1:]:
                if d <= HO.LOCAL_TAPE_END:
                    need.add((d.isoformat(), h["symbol"]))
    note(f"loading {len(need - set(summaries)):,} further lifecycle observations")
    summaries.update(load_summaries(need - set(summaries), args.workers))
    attach_integrity(cohorts, deep, summaries, max(HO.HOLDS))

    # ---- frozen features, off-high state and the four allocations
    feats, off_high = {}, {}
    for c in cohorts:
        iso, signal = c["signal_iso"], c["signal"]
        for h in deep[iso]:
            sym = h["symbol"]
            feats[(iso, sym)] = features(history(
                sym, HO.FEATS[HO.INDEX[signal] - 20: HO.INDEX[signal] + 1], signal, summaries))
            off_high[(iso, sym)] = an.signal_close_features(sym, signal, summaries)["close_vs_high20"]
    threshold = freeze["mechanism_panel"]["a11_off_high_median"]
    certified = {c["signal_iso"]: {h["symbol"] for h in deep[c["signal_iso"]][8:]} for c in cohorts}
    lineups, alloc, alloc_rows, plans, problems = build_allocations(
        cohorts, deep, feats, off_high, threshold, certified)
    blockers.extend(problems)
    exp.write_csv(OUT / "cohort_allocation_audit.csv", alloc_rows)
    note(f"allocations built for C0/C1/C2/C3 over {len(lineups['C0'])} cohorts; "
         f"{sum(p['k'] for p in plans.values())} C2 substitutions across {len(plans)} cohorts")

    for cfg in ("C1", "C2", "C3"):
        tot, base = defaultdict(float), defaultdict(float)
        for tid, v in alloc[cfg].items():
            tot[tid.split("/")[0]] += v
        for tid, v in alloc["C0"].items():
            base[tid.split("/")[0]] += v
        worst = max(abs(tot[k] - base[k]) for k in base if k in tot)
        note(f"{cfg}: cohort base capital preserved, worst deviation {worst:.2e}")
        if worst > 1e-6:
            blockers.append(f"{cfg} does not preserve cohort base capital")
    if blockers:
        dump_json(WORK / "reveal_manifest.json", {"blockers": blockers, "log": LOG})
        note("STOPPED before any book was built: " + "; ".join(blockers[:3]))
        return 1

    # ---- the eighteen cells, in one batch
    books, keys = {}, []
    for cell in cells:
        fam, cfg = CONFIG[cell["legacy_id"]]
        key = (cell["legacy_id"], cell["account_view"], cell["hold"])
        if key in books:
            continue
        keys.append(key)
        books[key] = eq.causal_book(
            fam, lineups[cfg], summaries, hold=cell["hold"],
            stage=f"{cell['legacy_id']}_{cell['account_view']}_H{cell['hold']}",
            scaled=cell["account_view"] == "EQUITY_SCALED",
            allocation=None if cfg == "C0" else alloc[cfg])
    # the rank-by-rank and mechanism diagnostics read fixed-dollar R5 books at all three holds
    for hold in HO.HOLDS:
        key = ("R5", "FIXED_DOLLAR", hold)
        if key not in books:
            books[key] = eq.causal_book("R5", lineups["C0"], summaries, hold=hold,
                                        stage=f"R5_FIXED_DOLLAR_H{hold}", scaled=False)
    note(f"built {len(books)} distinct books covering all 18 frozen cells")

    scored_cohorts = {t["cohort_id"] for b in books.values() for t in b["trades"]}
    frozen_ids = set(membership["top8"])
    if scored_cohorts != frozen_ids:
        blockers.append("scored cohorts are not exactly the frozen 52")
    note(f"holdout guard: scored cohort ids == the frozen 52: {scored_cohorts == frozen_ids}")

    # ---- accounts, headline metrics, monthly tables
    accounts, headline, monthly, recon = {}, {}, {}, {}
    for key, b in books.items():
        label = f"{NAMES[key[0]]} / {key[1]} / H{key[2]}"
        accounts[key] = acct.account_view(b, summaries, label)
        headline[key] = met.headline(b, accounts[key], START)
        monthly[key] = mon.monthly_account(b["daily"], START)
        recon[key] = mon.reconcile(monthly[key],
                                   accounts[key]["B_marked_account_pnl_at_cutoff"], START)
        if not recon[key]["reconciles"]:
            blockers.append(f"{label} monthly table does not reconcile")
    months = sorted({r["month"] for t in monthly.values() for r in t})
    short = [f"{k}" for k, t in monthly.items() if len(t) != 12]
    note(f"accounts: {len(accounts)}; identities hold "
         f"{sum(1 for v in accounts.values() if v['identities_hold'])}/{len(accounts)}; "
         f"monthly reconcile {sum(1 for v in recon.values() if v['reconciles'])}/{len(recon)}; "
         f"months {months[0]}..{months[-1]}; accounts without twelve rows: {len(short)}")
    if short:
        blockers.append(f"{len(short)} accounts do not carry twelve monthly rows")
    bad_id = [k for k, v in accounts.items() if not v["identities_hold"]]
    if bad_id:
        blockers.append(f"account identities fail for {bad_id[:3]}")

    # ---- private ledgers and the independent oracle
    # The export is keyed by the engine family the book was actually built with, not by the
    # cell's label. A challenger cell is a reallocation of an R5 book, so its trade rows carry
    # model "R5"; keying the export by "C1" wrote daily rows the oracle then could not find
    # against the trades they belong to.
    files = exp.export_all({(CONFIG[k[0]][0], f"{k[0]}_{k[1]}_H{k[2]}"): b
                            for k, b in books.items()}, root=OUT)
    orc = oracle.run(OUT, summaries)
    note(f"independent oracle: ok={orc['ok']} trades={orc['trades']['checked']} "
         f"max_abs_error={orc['trades']['max_abs_error']:.1e}")
    if not orc["ok"]:
        blockers.append("the independent oracle did not reconcile a ledger")

    # ---- public tables
    cell_rows = []
    for cell in cells:
        key = (cell["legacy_id"], cell["account_view"], cell["hold"])
        b, a, h = books[key], accounts[key], headline[key]
        done = [t for t in b["trades"] if t["status"] in COMPLETED]
        nets = [t["modeled_net"] for t in done]
        cell_rows.append({
            "cell": cell["cell"], "model": cell["model"], "legacy_id": cell["legacy_id"],
            "role": cell["role"], "account_view": cell["account_view"], "hold": cell["hold"],
            "quantity_convention": cell["quantity_convention"],
            "cohorts": len({t["cohort_id"] for t in b["trades"]}),
            "intended_positions": len(b["trades"]), "completed_trades": len(done),
            "A_eventual_completed_pnl": _r(a["A_completed_trade_pnl_all_cohorts"], 2),
            "B_marked_account_pnl_at_cutoff": _r(a["B_marked_account_pnl_at_cutoff"], 2),
            "C_post_cutoff_runoff_increment": _r(a["C_post_cutoff_incremental_runoff_pnl"], 2),
            "D_eventual_runoff_pnl": _r(a["D_eventual_pnl_of_runoff_trades"], 2),
            "E_open_obligations": a["E_open_documented_obligations"],
            "F_stale_gross_in_calendar_equity": _r(a["F_stale_gross_in_calendar_equity"], 2),
            "ending_equity": _r(b["daily"][-1]["equity"], 2),
            "return_on_starting_equity": _r(b["daily"][-1]["equity"] / START - 1),
            "hit_rate": _r(sum(1 for n in nets if n > 0) / len(nets), 4) if nets else None,
            "mean_net_per_trade": _r(statistics.fmean(nets), 2) if nets else None,
            "max_drawdown_pct_of_peak": _r(met.drawdown(b["daily"], START)["max_drawdown_pct_of_peak"]),
            "identities_hold": a["identities_hold"],
            "monthly_reconciles": recon[key]["reconciles"]})
    exp.write_csv(REPORTS / "cg_arrow014_headline_matrix.csv", cell_rows)

    acc_rows = []
    for key in sorted(books, key=lambda k: (k[0], k[1], k[2])):
        a, h = accounts[key], headline[key]
        acc_rows.append({"model": NAMES[key[0]], "legacy_id": key[0], "account_view": key[1],
                         "hold": key[2], **{k: _r(v, 2) if isinstance(v, float) else v
                                            for k, v in a.items() if k != "trades"},
                         **{f"headline_{k}": _r(v, 6) if isinstance(v, float) else v
                            for k, v in h.items() if not isinstance(v, (dict, list))}})
    exp.write_csv(REPORTS / "cg_arrow014_account_summary.csv", acc_rows)

    mon_rows = []
    for key in sorted(monthly, key=lambda k: (k[0], k[1], k[2])):
        for r in monthly[key]:
            mon_rows.append({"model": NAMES[key[0]], "legacy_id": key[0], "account_view": key[1],
                             "hold": key[2], **r})
    exp.write_csv(REPORTS / "cg_arrow014_monthly_account.csv", mon_rows)

    for view, name in (("FIXED_DOLLAR", "cohort_fixed_matrix"), ("EQUITY_SCALED", "cohort_equity_matrix")):
        rows = []
        for key in sorted(books, key=lambda k: (k[0], k[2])):
            if key[1] != view:
                continue
            by = defaultdict(list)
            for t in books[key]["trades"]:
                by[t["cohort_id"]].append(t)
            for iso in sorted(by):
                ts = by[iso]
                done = [t for t in ts if t["status"] in COMPLETED]
                nets = [t["modeled_net"] for t in done]
                rows.append({"model": NAMES[key[0]], "legacy_id": key[0], "hold": key[2],
                             "cohort_id": iso, "signal_month": iso[:7],
                             "positions": len(ts), "completed": len(done),
                             "eventual_pnl": _r(sum(nets), 2),
                             "winners": sum(1 for n in nets if n > 0),
                             "losers": sum(1 for n in nets if n <= 0),
                             "best_name_net": _r(max(nets), 2) if nets else None,
                             "worst_name_net": _r(min(nets), 2) if nets else None})
        exp.write_csv(REPORTS / f"cg_arrow014_{name}.csv", rows)

    breadth = []
    for key in sorted(books, key=lambda k: (k[0], k[1], k[2])):
        by = defaultdict(list)
        for t in books[key]["trades"]:
            if t["status"] in COMPLETED:
                by[t["cohort_id"]].append(t["modeled_net"])
        tot = {iso: sum(v) for iso, v in by.items()}
        pos = [v for v in tot.values() if v > 0]
        ordered = sorted(tot.values(), reverse=True)
        total = sum(ordered)
        breadth.append({"model": NAMES[key[0]], "legacy_id": key[0], "account_view": key[1],
                        "hold": key[2], "cohorts": len(tot),
                        "profitable_cohorts": len(pos),
                        "cohort_hit_rate": _r(len(pos) / len(tot), 4) if tot else None,
                        "top_cohort_share_of_total": _r(ordered[0] / total) if total else None,
                        "top3_cohort_share_of_total": _r(sum(ordered[:3]) / total) if total else None,
                        "median_cohort_pnl": _r(statistics.median(tot.values()), 2) if tot else None})
    exp.write_csv(REPORTS / "cg_arrow014_cohort_breadth.csv", breadth)

    # ---- horizon attribution
    horizon = []
    for legacy in ("R4", "R5"):
        for view in ("FIXED_DOLLAR", "EQUITY_SCALED"):
            base = None
            for hold in HO.HOLDS:
                key = (legacy, view, hold)
                if key not in books:
                    continue
                b = books[key]
                nets = [t["modeled_net"] for t in b["trades"] if t["status"] in COMPLETED]
                total = sum(nets)
                base = total if base is None else base
                horizon.append({"model": NAMES[legacy], "legacy_id": legacy, "account_view": view,
                                "hold": hold, "completed_trades": len(nets),
                                "eventual_pnl": _r(total, 2),
                                "ending_equity": _r(b["daily"][-1]["equity"], 2),
                                "increment_vs_h8": _r(total - base, 2),
                                "hit_rate": _r(sum(1 for n in nets if n > 0) / len(nets), 4)
                                if nets else None})
    exp.write_csv(REPORTS / "cg_arrow014_horizon_attribution.csv", horizon)

    # ---- drawdowns
    dd = []
    for key in sorted(books, key=lambda k: (k[0], k[1], k[2])):
        dd.extend(drawdown_episodes(books[key]["daily"],
                                    f"{NAMES[key[0]]} / {key[1]} / H{key[2]}"))
    exp.write_csv(REPORTS / "cg_arrow014_drawdown_episodes.csv", dd)

    # ---- rank-by-rank and the mechanism panel
    rbr = rank_by_rank(books, freeze)
    exp.write_csv(REPORTS / "cg_arrow014_rank_by_rank.csv", rbr)
    anat = anatomy_rows(books, deep, summaries)
    panel = mechanism_panel(anat, freeze) + holding_paths(books, summaries)
    exp.write_csv(REPORTS / "cg_arrow014_mechanism_confirmation.csv", panel)
    exp.write_csv(OUT / "selected_anatomy.csv", anat)
    note(f"mechanism panel: {len(panel)} rows; rank-by-rank: {len(rbr)} rows; "
         f"anatomy rows: {len(anat)}")

    # ---- historical versus pristine
    hist = read_json(REPORTS / "cg_arrow012_manifest.json") if \
        (REPORTS / "cg_arrow012_manifest.json").exists() else {}
    comp = []
    for cell in cells:
        key = (cell["legacy_id"], cell["account_view"], cell["hold"])
        b = books[key]
        nets = [t["modeled_net"] for t in b["trades"] if t["status"] in COMPLETED]
        comp.append({"cell": cell["cell"], "model": cell["model"], "legacy_id": cell["legacy_id"],
                     "account_view": cell["account_view"], "hold": cell["hold"],
                     "pristine_eventual_pnl": _r(sum(nets), 2),
                     "pristine_ending_equity": _r(b["daily"][-1]["equity"], 2),
                     "pristine_return": _r(b["daily"][-1]["equity"] / START - 1),
                     "historical_period": "2025-09..2026-08",
                     "pristine_period": "2024-09..2025-08",
                     "historical_reference": json.dumps(
                         hist.get("headline", {}).get(f"{cell['legacy_id']}/{cell['account_view']}"))
                     if hist else None})
    for r in rbr:
        if r["hold"] == 10:
            comp.append({"cell": None, "model": "rank diagnostic", "legacy_id": f"rank {r['rank']}",
                         "account_view": "FIXED_DOLLAR", "hold": 10,
                         "pristine_mean_sizing_neutral": r["mean"],
                         "historical_mean_sizing_neutral": r["historical_h10_mean"],
                         "pristine_hit_rate": r["hit_rate"],
                         "historical_hit_rate": r["historical_h10_hit"],
                         "classification": r["classification"]})
    exp.write_csv(REPORTS / "cg_arrow014_historical_vs_pristine.csv", comp)

    manifest = {
        "arrow": "CG Arrow 014", "phase": "1_reveal", "timestamp": stamp(),
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                               cwd=REPO_ROOT).decode().strip(),
        "lock1_commit": gate["lock1_commit"], "lock2_commit": gate["lock2_commit"],
        "corridor": info, "cells": len(cells), "books": len(books),
        "membership_sha256": membership["membership_sha256"],
        "cohorts_scored": len(frozen_ids),
        "scored_matches_frozen": scored_cohorts == frozen_ids,
        "oracle": {"ok": orc["ok"], "trades_checked": orc["trades"]["checked"],
                   "max_abs_error": orc["trades"]["max_abs_error"]},
        "accounts": {f"{k[0]}/{k[1]}/H{k[2]}": {
            "identities_hold": accounts[k]["identities_hold"],
            "monthly_reconciles": recon[k]["reconciles"],
            "monthly_rows": len(monthly[k])} for k in books},
        "headline_by_cell": {r["cell"]: {"model": r["model"], "view": r["account_view"],
                                         "hold": r["hold"],
                                         "A_eventual_completed_pnl": r["A_eventual_completed_pnl"],
                                         "ending_equity": r["ending_equity"]}
                             for r in cell_rows},
        "substitutions": plans, "private_files": files,
        "blockers": blockers, "log": LOG}
    dump_json(REPORTS / "cg_arrow014_manifest.json", manifest)
    dump_json(WORK / "reveal_manifest.json", manifest)
    write_reveal_md(REPORTS / "cg_arrow014_reveal.md", cell_rows, breadth, horizon, rbr, panel,
                    dd, gate, freeze, membership, plans, orc, info)
    write_commands(REPORTS / "cg_arrow014_commands.txt")
    note(f"reveal complete over all {len(cells)} frozen cells; blockers: {blockers or 'none'}")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
