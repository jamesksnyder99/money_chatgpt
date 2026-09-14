"""Arrow 005 exports: private local CSVs under handoff/outgoing/cg_arrow005 plus safe hashes."""
from __future__ import annotations

from collections import defaultdict
import csv
from pathlib import Path

from verification.r4r5_data import HANDOFF, digest, split_of
from verification.r4r5_replay import COMPLETED, VERIFIED, replay

TRADE_FIELDS = ["model", "replay_stage", "data_version", "quantity_convention", "horizon", "cohort_id", "signal_date",
                "signal_month", "split", "rank", "ticket_id", "symbol", "security_id", "ranking_scope", "field_size",
                "prior_close", "prior_dollar_volume", "ret15", "ret3", "volume_ratio", "feature_history_sessions",
                "volume_feature_available", "momentum_feature_available", "intended_size_fixed_dollar", "sizing_scale_factor",
                "equity_reference", "equity_reference_date", "intended_size", "size_tier",
                "volume_multiplier", "momentum_multiplier", "scheduled_entry_date", "entry_status", "entry_ts",
                "entry_price_field", "entry_price", "entry_source", "entry_eod_reference", "preorder_price", "preorder_ts",
                "quantity_fill_convention", "quantity_preorder_convention", "quantity", "scheduled_exit_date",
                "exit_status", "exit_ts", "exit_price_field", "exit_price", "exit_source", "exit_eod_reference",
                "exit_reason", "actual_exit_date", "event_treatment", "event_source", "action_factor_over_hold", "quantity_at_exit", "entry_price_exit_units",
                "exit_after_cutoff", "holding_sessions_intended", "actual_holding_sessions", "holding_calendar_days",
                "gross_pnl", "entry_commission", "entry_spread", "exit_commission", "exit_spread", "dividends",
                "dividend_status", "borrow_status", "borrow_base_dollar_years", "modeled_net", "modeled_net_double_spread",
                "net_borrow_10", "net_borrow_30", "stale_mark_sessions_in_hold", "stale_liability_last_mark",
                "stale_liability_last_mark_date", "stale_liability_eod_reference", "diagnostic_delayed_exit_date",
                "diagnostic_delayed_open", "diagnostic_delayed_ts", "diagnostic_delay_sessions", "security_identity_status",
                "max_session_ratio_in_hold", "max_session_ratio_date", "discontinuity_flag", "action_review_resolution",
                "lookback_flag", "lookback_max_ratio", "lookback_ratio_date", "lookback_resolution",
                "lookback_evidence_classification", "lookback_issuer_filings_searched",
                "lookback_filings_scanned", "lookback_volume_ratio_at_flag",
                "holding_flag", "holding_max_ratio", "holding_ratio_date", "holding_resolution",
                "holding_evidence_classification", "status",
                "verification_status", "verification_reason"]


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({k for r in rows for k in r})
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})
    tmp.replace(path)
    return digest(path)


def exceptions_rows(books: dict, initial: dict | None = None) -> list[dict]:
    """Initial and final status of every intended slot across families/stages."""
    out = []
    for key, book in books.items():
        for t in book["trades"]:
            out.append({"model": t["model"], "replay_stage": t["replay_stage"], "cohort_id": t["cohort_id"], "rank": t["rank"],
                        "symbol": t["symbol"], "scheduled_entry_date": t["scheduled_entry_date"], "entry_status": t.get("entry_status"),
                        "scheduled_exit_date": t.get("scheduled_exit_date"), "exit_status": t.get("exit_status"),
                        "initial_status": (initial or {}).get((key, t["ticket_id"]), t["status"]), "final_status": t["status"],
                        "ranking_scope": t["ranking_scope"], "diagnostic_delay_sessions": t.get("diagnostic_delay_sessions"),
                        "security_identity_status": t.get("security_identity_status"), "discontinuity_flag": t.get("discontinuity_flag"), "action_review_resolution": t.get("action_review_resolution"),
                        "reason": t.get("verification_reason")})
    return out


def cohort_audit_rows(books: dict) -> list[dict]:
    out = []
    for key, book in books.items():
        by = defaultdict(list)
        for t in book["trades"]:
            by[t["cohort_id"]].append(t)
        totals = defaultdict(lambda: defaultdict(float))
        for cid, ts in sorted(by.items()):
            for t in ts:
                out.append({"row_type": "TRADE", "model": t["model"], "replay_stage": t["replay_stage"], "cohort_id": cid,
                            "split": t["split"], "rank": t["rank"], "symbol": t["symbol"], "status": t["status"],
                            "quantity": t.get("quantity"), "entry_price": t.get("entry_price"), "exit_price": t.get("exit_price"),
                            "gross_pnl": t.get("gross_pnl"), "modeled_net": t.get("modeled_net")})
            ver = [t for t in ts if t["status"] in COMPLETED]
            row = {"row_type": "COHORT_SUBTOTAL", "model": ts[0]["model"], "replay_stage": ts[0]["replay_stage"], "cohort_id": cid,
                   "split": ts[0]["split"], "expected_slots": len(ts), "filled": sum(bool(t.get("quantity")) for t in ts),
                   "closed_verified": len(ver), "unresolved": sum(t["status"].startswith("UNRESOLVED") for t in ts),
                   "missed_entry": sum(t["status"].startswith("MISSED_ENTRY") for t in ts),
                   "blocked_or_zero": sum(t["status"] in {"BLOCKED_INHERITED_BORROW_PROXY", "ZERO_SHARE_ORDER"} for t in ts),
                   "gross_pnl": sum(t["gross_pnl"] for t in ver), "modeled_net": sum(t["modeled_net"] for t in ver),
                   "verified_total_is_complete": all(t["status"] in COMPLETED or t["status"].startswith(("MISSED", "BLOCKED", "ZERO", "NO_ENTRY")) for t in ts)}
            out.append(row)
            for scope in (("SIGNAL_MONTH", cid[:7]), ("SPLIT", ts[0]["split"]), ("PERIOD", "ALL")):
                tot = totals[scope]
                for k in ("expected_slots", "filled", "closed_verified", "unresolved", "missed_entry", "blocked_or_zero", "gross_pnl", "modeled_net"):
                    tot[k] += row[k]
                tot["complete"] = tot.get("complete", 1.0) * row["verified_total_is_complete"]
        for (kind, label), tot in sorted(totals.items()):
            out.append({"row_type": kind + "_TOTAL", "model": key[0], "replay_stage": key[1], "cohort_id": label,
                        **{k: (int(v) if k not in {"gross_pnl", "modeled_net"} else v) for k, v in tot.items() if k != "complete"},
                        "verified_total_is_complete": bool(tot["complete"])})
    return out


def cohort_matrix_rows(books: dict) -> list[dict]:
    out = []
    for key, book in books.items():
        by = defaultdict(list)
        for t in book["trades"]:
            by[t["cohort_id"]].append(t)
        for cid, ts in sorted(by.items()):
            row = {"model": key[0], "replay_stage": key[1], "cohort_id": cid, "split": ts[0]["split"]}
            for t in sorted(ts, key=lambda x: x["rank"]):
                s = f"slot{t['rank']:02d}_"
                row.update({s + "symbol": t["symbol"], s + "entry": t.get("entry_price"), s + "exit": t.get("exit_price"),
                            s + "qty": t.get("quantity"), s + "pnl": t.get("modeled_net"), s + "status": t["status"]})
            ver = [t for t in ts if t["status"] == VERIFIED]
            row.update({"cohort_verified_net": sum(t["modeled_net"] for t in ver), "cohort_unresolved": len(ts) - len(ver)})
            out.append(row)
    return out


def daily_rows(books: dict) -> list[dict]:
    out = []
    for key, book in books.items():
        for r in book["daily"]:
            out.append({"model": key[0], "replay_stage": key[1], **r})
    return out


def horizon_paths(family: str, cohort_list, summaries, *, quantity="fill", stage="R2") -> tuple[list[dict], list[dict]]:
    """Same entries and shares at every horizon; H0 is the entry-cost state."""
    wide = {}
    tidy = []
    for h in range(1, 11):
        book = replay(family, cohort_list, summaries, hold=h, quantity=quantity, stage=stage)
        for t in book["trades"]:
            key = t["ticket_id"]
            w = wide.setdefault(key, {"model": family, "cohort_id": t["cohort_id"], "split": t["split"], "rank": t["rank"], "symbol": t["symbol"],
                                      "entry_date": t.get("scheduled_entry_date"), "entry_price": t.get("entry_price"), "quantity": t.get("quantity"),
                                      "H00_pnl": -(t.get("entry_commission", 0) or 0) - (t.get("entry_spread", 0) or 0) if t.get("quantity") else None})
            w.update({f"H{h:02d}_exit_date": t.get("scheduled_exit_date"), f"H{h:02d}_exit_price": t.get("exit_price"),
                      f"H{h:02d}_pnl": t.get("modeled_net"), f"H{h:02d}_status": t["status"]})
            tidy.append({"model": family, "ticket_id": key, "horizon": h, "exit_date": t.get("scheduled_exit_date"),
                         "exit_price": t.get("exit_price"), "gross_pnl": t.get("gross_pnl"), "modeled_net": t.get("modeled_net"), "status": t["status"]})
    return list(wide.values()), tidy


def export_all(books: dict, initial: dict | None = None, root: Path = HANDOFF) -> dict:
    files = {}
    files["r4r5_trade_exceptions.csv"] = write_csv(root / "r4r5_trade_exceptions.csv", exceptions_rows(books, initial))
    trades = [t for b in books.values() for t in b["trades"]]
    files["r4r5_verified_trades.csv"] = write_csv(root / "r4r5_verified_trades.csv", trades, TRADE_FIELDS)
    files["r4r5_verified_cohort_audit.csv"] = write_csv(root / "r4r5_verified_cohort_audit.csv", cohort_audit_rows(books))
    files["r4r5_cohort_matrix.csv"] = write_csv(root / "r4r5_cohort_matrix.csv", cohort_matrix_rows(books))
    files["r4r5_daily_account.csv"] = write_csv(root / "r4r5_daily_account.csv", daily_rows(books))
    return {name: {"path": (root / name).as_posix(), "sha256": sha, "bytes": (root / name).stat().st_size} for name, sha in files.items()}
