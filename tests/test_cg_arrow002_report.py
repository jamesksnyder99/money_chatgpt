import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("cg_report",Path(__file__).resolve().parents[1]/"scripts/cg_arrow002_report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def fixture_metrics():
    m = {k:0 for k in ("max_dd","worst_day","avg_exposure","peak_exposure","mean_live_tickets",
         "peak_live_tickets","mean_live_symbols","peak_live_symbols","intended_notional",
         "profit_per_avg_exposure","trades","hit_rate","profit_factor")}
    m.update(monthly_mtm={"2026-01":-10,"2026-02":30},total_pnl=20,sessions=2,
             red_months=0,red_loss_sum=0,borrow_sensitivity={"0":20,"0.1":18,"0.3":14})
    return m


def test_calendar_red_months_are_not_signal_month_counts():
    m = report.calendar_metrics(fixture_metrics())
    assert m["calendar_red_months"] == 1
    assert m["calendar_red_loss_sum"] == -10
    assert m["worst_calendar_month"] == -10
    assert m["best_calendar_month_concentration"] == 1.5
    assert m["per_session"] == 10


def test_investor_report_requires_pnl_reconciliation():
    m = fixture_metrics()
    m["total_pnl"] = 999
    with pytest.raises(ValueError,match="reconcile"):
        report.calendar_metrics(m)
