"""CG Arrow 009 — certified monthly account reporting export.

Reporting only. Nothing in the certified Arrow 008 substrate is recomputed or changed: the
daily marked-account paths of the certified Corrected-Universe Replay 10-Session Hold
legacy-fill books are read as-is and aggregated to calendar months.

Usage: python scripts/cg_arrow009_report.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingest.paths import REPO_ROOT, REPORTS  # noqa: E402
from verification import r4r5_monthly as mon  # noqa: E402
from verification.r4r5_data import digest, dump_json, read_json, stamp  # noqa: E402

HANDOFF8 = REPO_ROOT / "handoff" / "outgoing" / "cg_arrow008"
BOOK = "R2_LEGACY_FILL_QTY"
NAMES = {"PARENT": "Equal-Dollar Short", "R4": "Volume-Sized Short",
         "R5": "Momentum+Volume-Sized Short"}
SHORT = {"PARENT": "Equal-Dollar H10", "R4": "R4 H10", "R5": "R5 H10"}
MONTHS = ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02",
          "2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
LABEL = {"2025-09": "Sep 2025", "2025-10": "Oct 2025", "2025-11": "Nov 2025", "2025-12": "Dec 2025",
         "2026-01": "Jan 2026", "2026-02": "Feb 2026", "2026-03": "Mar 2026", "2026-04": "Apr 2026",
         "2026-05": "May 2026", "2026-06": "Jun 2026", "2026-07": "Jul 2026", "2026-08": "Aug 2026"}
FOOTNOTE = ("Headline modeled P&L includes the lab's stated commission/spread assumptions and excludes "
            "broker-specific locate/HTB charges, dividends, recalls/buy-ins, financing, taxes, and other "
            "account-specific execution items. Alpaca ETB securities currently carry $0 locate and borrow "
            "fees for Trading API users; short availability and other security-specific costs may still vary.")


def money(x: float) -> str:
    return f"{x:,.2f}"


def main() -> int:
    a8 = read_json(REPORTS / "cg_arrow008_manifest.json")
    daily = list(csv.DictReader((HANDOFF8 / "r4r5_daily_account.csv").open(encoding="utf-8")))

    tables, recon, summaries = {}, {}, {}
    for fam in NAMES:
        rows = [r for r in daily if r["model"] == fam and r["replay_stage"] == BOOK]
        rows.sort(key=lambda r: r["date"])
        table = mon.monthly_account(rows)
        b = a8["accounts"][f"{fam}/LEGACY_FILL_QTY/ALL"]["B_marked_account_pnl_at_cutoff"]
        tables[fam] = table
        recon[fam] = mon.reconcile(table, b)
        summaries[fam] = mon.summarize(table)
        print(f"{stamp()} {NAMES[fam]}: {len(table)} months, total {money(recon[fam]['total_monthly_pnl'])}, "
              f"certified B {money(b)}, reconciles={recon[fam]['reconciles']}", flush=True)
        assert [r["month"] for r in table] == MONTHS, f"{fam} months {[r['month'] for r in table]}"

    # ---- tidy CSV
    # Published rows are stated in whole cents and must chain exactly, the way an account
    # statement does, so the cent-rounded equity path is the authority for the published
    # P&L and return columns. Full precision is retained in the manifest, which is what
    # carries the exact reconciliation to the certified Arrow 008 account result.
    out = []
    for fam, table in tables.items():
        prior = round(mon.STARTING_EQUITY, 2)
        for r in table:
            end = round(r["month_end_equity"], 2)
            pnl = round(end - prior, 2)
            out.append({"month": r["month"], "strategy": NAMES[fam], "legacy_id": fam,
                        "replay": "Corrected-Universe Replay (R2)", "horizon": "10-Session Hold (H10)",
                        "quantity_panel": "LEGACY_FILL_QTY",
                        "monthly_pnl": pnl,
                        "monthly_return_pct": round(pnl / prior * 100.0, 4),
                        "month_end_equity": end,
                        "prior_month_end_equity": prior,
                        "reporting_standard": mon.STANDARD_ID, "footnote": FOOTNOTE})
            prior = end
    path = REPORTS / "cg_arrow009_monthly_account.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    assert not mon.missing_standard_fields(out), mon.missing_standard_fields(out)

    # ---- human-readable report
    L = []
    L.append("# CG Arrow 009 — certified 12-month account results, Winner-Fade Short")
    L.append("")
    L.append("Reporting only. Nothing in the certified Arrow 008 substrate was recomputed, reselected or "
             "changed. These are the calendar-month account results of the certified Corrected-Universe "
             "Replay (`R2`) at the 10-Session Hold (`H10`), legacy fill-quantity panel, read from the "
             "daily marked-account path.")
    L.append("")
    L.append("Monthly P&L is the change in marked account equity across the month, so a position opened "
             "in one month and closed in the next contributes to both, exactly as an account statement "
             "would show. Monthly return divides that month's P&L by the prior month-end marked equity; "
             "September 2025 starts from the $100,000 study equity.")
    L.append("")
    L.append("Published rows are stated in whole cents and chain exactly, as an account statement does. "
             "Full precision is retained in `reports/cg_arrow009_manifest.json`, which carries the exact "
             "reconciliation to the certified Arrow 008 account result.")
    L.append("")
    L.append("## Monthly account P&L, dollars")
    L.append("")
    L.append("| Month | " + " | ".join(SHORT[f] for f in NAMES) + " |")
    L.append("|---|" + "---:|" * len(NAMES))
    for i, m in enumerate(MONTHS):
        L.append(f"| {LABEL[m]} | " + " | ".join(money(tables[f][i]["monthly_pnl"]) for f in NAMES) + " |")
    L.append("| **Total** | " + " | ".join(
        f"**{money(recon[f]['total_monthly_pnl'])}**" for f in NAMES) + " |")
    L.append("")
    L.append("## Monthly return, percent of prior month-end equity")
    L.append("")
    L.append("| Month | " + " | ".join(SHORT[f] for f in NAMES) + " |")
    L.append("|---|" + "---:|" * len(NAMES))
    for i, m in enumerate(MONTHS):
        L.append(f"| {LABEL[m]} | " + " | ".join(
            f"{tables[f][i]['monthly_return_pct']:.2f}%" for f in NAMES) + " |")
    L.append("")
    L.append("## Month-end marked equity")
    L.append("")
    L.append("| Month | " + " | ".join(SHORT[f] for f in NAMES) + " |")
    L.append("|---|" + "---:|" * len(NAMES))
    for i, m in enumerate(MONTHS):
        L.append(f"| {LABEL[m]} | " + " | ".join(money(tables[f][i]["month_end_equity"]) for f in NAMES) + " |")
    L.append("")
    L.append("## Monthly shape")
    L.append("")
    L.append("| Measure | " + " | ".join(SHORT[f] for f in NAMES) + " |")
    L.append("|---|" + "---:|" * len(NAMES))
    for key, name in (("positive_months", "Positive months"), ("red_months", "Red months"),
                      ("red_month_loss_sum", "Sum of red months"), ("worst_month", "Worst month"),
                      ("best_month", "Best month"), ("median_month", "Median month")):
        vals = []
        for f in NAMES:
            v = summaries[f][key]
            vals.append(str(v) if isinstance(v, int) else money(v))
        L.append(f"| {name} | " + " | ".join(vals) + " |")
    L.append("")
    L.append("## Reconciliation to the certified Arrow 008 account result")
    L.append("")
    L.append("The twelve calendar months reconcile to Arrow 008 quantity **B**, the marked account P&L at "
             "2026-08-31. They deliberately do **not** reconcile to quantity **A**, eventual completed-trade "
             "P&L, because A includes exits scheduled after August closes; that runoff is reported separately.")
    L.append("")
    L.append("| Book | Sum of 12 monthly P&L | Certified Arrow 008 B | Difference | Aug-2026 month-end equity |")
    L.append("|---|---:|---:|---:|---:|")
    for f in NAMES:
        L.append(f"| {SHORT[f]} | {money(recon[f]['total_monthly_pnl'])} | "
                 f"{money(recon[f]['expected_period_marked_pnl'])} | "
                 f"{recon[f]['difference']:.2e} | {money(tables[f][-1]['month_end_equity'])} |")
    L.append("")
    L.append("Positions still open at the boundary are carried in the August marked equity above at their "
             "last observed marks, and their eventual outcomes appear in the Arrow 008 runoff quantities C "
             "and D rather than in any month here. One documented open obligation per book remains, under a "
             "documented trading suspension.")
    L.append("")
    L.append("## Reporting standard")
    L.append("")
    L.append(f"These tables are produced by the frozen lab standard `{mon.STANDARD_ID}` in "
             "`src/verification/r4r5_monthly.py`. Every future research arrow that publishes strategy "
             "economics and has a daily marked-account path must publish the same set: every calendar "
             "month individually, principal variants side by side, monthly P&L dollars, monthly return "
             "percent on prior month-end equity, month-end equity, positive and red month counts, worst "
             "and median month, exact reconciliation to the period's marked account result, and explicit "
             "boundary treatment. It is a reporting requirement, never an optimization dimension: monthly "
             "outcomes must not be used to select or alter a strategy.")
    L.append("")
    L.append(f"> {FOOTNOTE}")
    L.append("")
    (REPORTS / "cg_arrow009_monthly_report.md").write_text("\n".join(L) + "\n",
                                                           encoding="utf-8", newline="\n")

    manifest = {
        "arrow": "CG Arrow 009", "executor": "Opus in Claude Code", "timestamp": stamp(),
        "scope": "reporting only; no strategy, ranking, sizing, event or accounting change",
        "head_at_run": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                               cwd=REPO_ROOT).decode().strip(),
        "source_book": f"certified Arrow 008 {BOOK} daily marked-account path",
        "reporting_standard": mon.STANDARD_ID,
        "months": MONTHS,
        "monthly": {fam: tables[fam] for fam in NAMES},
        "summary": summaries, "reconciliation": recon,
        "certified_inputs": {
            "arrow008_manifest_sha256": digest(REPORTS / "cg_arrow008_manifest.json"),
            "arrow008_membership_sha256": a8["membership_sha256"],
            "arrow008_entry_ledger_sha256": a8["r2_entry_ledger_sha256"],
            "arrow008_action_table_sha256": a8["action_table_sha256"],
            "arrow008_certification": a8["certification"]["verdict"]},
        "all_reconcile": all(recon[f]["reconciles"] for f in NAMES),
        "headline_footnote": FOOTNOTE,
    }
    dump_json(REPORTS / "cg_arrow009_manifest.json", manifest)
    print(f"{stamp()} all books reconcile: {manifest['all_reconcile']}", flush=True)
    return 0 if manifest["all_reconcile"] else 1


if __name__ == "__main__":
    sys.exit(main())
