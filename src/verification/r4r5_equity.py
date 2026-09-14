"""Arrow 010 — causal equity-responsive sizing on the frozen Winner-Fade Short substrate.

One question only: what happens to account economics when already-defined ticket sizes
scale with account equity instead of staying fixed in dollars?

The rule is deliberately the smallest possible change to the certified engine:

    equity_reference = marked account equity at the close of the signal session
    scale_factor     = equity_reference / starting_equity
    intended_ticket  = fixed_tier_notional * scale_factor

The signal session is the last fully completed account close before the next-session entry,
so the reference is knowable before any order in the cohort is placed and is the same for
all eight tickets. Nothing else moves: selection, tier, entry and exit sessions and every
observed price are those of the fixed-dollar control, and shares are still floored from the
causal pre-order price.

Causality is enforced structurally rather than by assertion. Cohorts are built strictly in
signal order, and each cohort's reference equity is read from an account containing only
trades whose entry session precedes this cohort's signal session. A cohort can therefore
never see its own fill, its own marks or any later cohort.
"""
from __future__ import annotations

from datetime import date

from verification.r4r5_data import SCORE
from verification.r4r5_replay import daily_account, replay

STARTING_EQUITY = 100000.0
RULE_ID = "cg_arrow010_causal_signal_close_equity_scaling_v1"
RULE = ("intended ticket notional = fixed R5 tier notional * (marked account equity at the "
        "close of the signal session / 100,000); no leverage multiplier, drawdown throttle, "
        "gross cap, volatility target, Kelly rule, cohort filter or redeployment")


def equity_at(daily: list[dict], when: date) -> float:
    """Marked account equity at the close of `when`, or the last close on or before it.

    Before the first scored session the account is untouched, so the reference is the
    starting equity. This is a lookup into an already-built path; it never looks forward.
    """
    value = STARTING_EQUITY
    for row in daily:
        if row["date"] > when.isoformat():
            break
        value = row["equity"]
    return value


def causal_book(family: str, cohort_list: list[dict], summaries: dict, *, hold: int = 10,
                stage: str = "R5_EQUITY_SCALED", starting_equity: float = STARTING_EQUITY,
                scaled: bool = True, allocation: dict | None = None) -> dict:
    """Build a causal pre-order book, cohort by cohort, in signal order.

    With `scaled=False` every scale factor is 1.0 and the result is the fixed-dollar control,
    which must reproduce the certified causal pre-order totals exactly.
    """
    ordered = sorted(cohort_list, key=lambda c: c["signal"])
    trades: list[dict] = []
    daily: list[dict] = []
    path: list[dict] = []
    for cohort in ordered:
        reference = equity_at(daily, cohort["signal"]) if scaled else starting_equity
        factor = reference / starting_equity if scaled else 1.0
        book = replay(family, [cohort], summaries, hold=hold, quantity="preorder", stage=stage,
                      scale={cohort["signal_iso"]: factor}, allocation=allocation)
        for t in book["trades"]:
            t["equity_reference"] = reference
            t["equity_reference_date"] = cohort["signal_iso"]
            t["sizing_rule_id"] = RULE_ID
        trades.extend(book["trades"])
        # rebuild the account through the cutoff so the next cohort reads a complete path
        daily = daily_account(trades, summaries)
        path.append({"cohort_id": cohort["signal_iso"], "signal_date": cohort["signal_iso"],
                     "split": cohort["split"], "entry_date": cohort["fill"].isoformat(),
                     "equity_reference": reference, "scale_factor": factor})
    return {"trades": trades, "daily": daily, "scaling_path": path,
            "sizing_rule_id": RULE_ID, "sizing_rule": RULE, "scaled": scaled}


def scale_map(book: dict) -> dict:
    return {r["cohort_id"]: r["scale_factor"] for r in book["scaling_path"]}


def causality_violations(book: dict, cohort_list: list[dict]) -> list[str]:
    """Every way a scale factor could have used information it was not entitled to.

    A cohort's reference equity is the close of its signal session, so only trades entered
    on or before that session may contribute. This checks that no ticket of the cohort
    itself or of any later cohort was entered by then, that each entry genuinely follows its
    own signal, and that the first cohort sizes from the untouched starting equity.
    """
    by_signal = {c["signal_iso"]: c for c in cohort_list}
    rows = sorted(book["scaling_path"], key=lambda r: r["signal_date"])
    out = []
    if rows and abs(rows[0]["equity_reference"] - STARTING_EQUITY) > 1e-9:
        out.append(f"first cohort {rows[0]['cohort_id']} did not size from the starting equity")
    for row in rows:
        cohort = by_signal[row["cohort_id"]]
        if cohort["fill"].isoformat() <= row["signal_date"]:
            out.append(f"{row['cohort_id']} entry does not follow its signal session")
        leaked = [t["ticket_id"] for t in book["trades"]
                  if t["cohort_id"] >= row["cohort_id"]
                  and t["scheduled_entry_date"] <= row["signal_date"]]
        if leaked:
            out.append(f"{row['cohort_id']} reference equity could see {len(leaked)} ticket(s) "
                       f"of its own or a later cohort, first {leaked[0]}")
    return out


def rebuild_reference(book: dict, summaries: dict, cohort_id: str) -> float:
    """Independent re-derivation of one cohort's reference equity.

    Rebuilds the account from only those trades of strictly earlier cohorts and reads the
    close of the signal session, without consulting the stored scaling path.
    """
    earlier = [t for t in book["trades"] if t["cohort_id"] < cohort_id]
    return equity_at(daily_account(earlier, summaries), date.fromisoformat(cohort_id))


def session_count() -> int:
    return len(SCORE)
