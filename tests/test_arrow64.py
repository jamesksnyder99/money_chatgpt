from datetime import date
from pathlib import Path

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow64 import (
    CONTROL_ID,
    EXPERIMENTS,
    LONG_ID,
    MIN_PEER,
    attach_group_residuals,
    group_residual,
    select_longs,
    select_shorts,
)
from research.clock import entry_split, is_is_session, tape_root
from research.costs import signed_pnl


def test_id1_residual_subtracts_same_sic2_median_not_iwm() -> None:
    peers = [0.00, 0.00, 0.00, 0.00, 0.02, 0.02, 0.02, 0.04]
    name_ret = 0.20
    iwm_ret = 0.50
    g = group_residual(name_ret, peers)
    assert g is not None
    assert abs(g - (0.20 - 0.01)) < 1e-12
    iwm_res = name_ret - iwm_ret
    assert abs(iwm_res - (-0.30)) < 1e-12
    assert g != iwm_res
    assert EXPERIMENTS[1][0] == "short_sic_fri"
    assert EXPERIMENTS[1][2] == "sic"
    assert EXPERIMENTS[0][0] == CONTROL_ID == "short_iwm_fri"
    assert EXPERIMENTS[0][2] == "iwm"


def test_id2_long_only_others_short_only() -> None:
    assert EXPERIMENTS[2][0] == LONG_ID == "long_sic_fri"
    assert EXPERIMENTS[2][1] == "long"
    for e in EXPERIMENTS:
        if e[0] == LONG_ID:
            assert e[1] == "long"
        else:
            assert e[1] == "short"
    assert EXPERIMENTS[0][1] == EXPERIMENTS[1][1] == EXPERIMENTS[3][1] == "short"
    assert EXPERIMENTS[4][1] == EXPERIMENTS[5][1] == "short"
    assert len(EXPERIMENTS) == 6
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 21.0) > 0
    assert shares_for(20.0, 3000.0) == 150
    rows = [
        {"residual": 0.20, "symbol": "A"},
        {"residual": -0.10, "symbol": "B"},
        {"residual": 0.05, "symbol": "C"},
    ]
    assert select_shorts(rows, 1)[0]["symbol"] == "A"
    assert select_longs(rows, 1)[0]["symbol"] == "B"


def test_name_with_fewer_than_8_sic2_peers_is_dropped() -> None:
    assert MIN_PEER == 8
    thin = [
        {"symbol": f"S{i}", "sic2": "10", "name_ret": 0.01 * i} for i in range(8)
    ]
    assert attach_group_residuals(thin) == []
    assert group_residual(0.10, [0.0] * 7) is None
    fat = [
        {"symbol": f"S{i}", "sic2": "10", "name_ret": 0.01 * i} for i in range(9)
    ]
    kept = attach_group_residuals(fat)
    assert len(kept) == 9
    assert all(r["peer_n"] == 8 for r in kept)
    other = {"symbol": "Z", "sic2": "20", "name_ret": 0.50}
    mixed = fat + [other]
    kept2 = attach_group_residuals(mixed)
    assert all(r["symbol"] != "Z" for r in kept2)
    assert len(kept2) == 9


def test_even_month_entry_is_not_is() -> None:
    assert entry_split(date(2026, 2, 6)) == "OOS"
    assert not is_is_session(date(2026, 2, 6))
    assert is_is_session(date(2026, 1, 2))
    assert date(2026, 1, 2).weekday() == 4
    assert EXPERIMENTS[3][0] == "short_sic_wed"
    assert EXPERIMENTS[3][3] == 2
    assert date(2026, 1, 7).weekday() == 2


def test_do_not_call_sec() -> None:
    src = Path(__file__).resolve().parents[1] / "src" / "research" / "arrow64.py"
    text = src.read_text(encoding="utf-8")
    assert "sec.gov" not in text
    assert "data.sec.gov" not in text
    assert "urllib" not in text
    assert "fetch_ticker_map" not in text
    assert "fetch_sic_for_cik" not in text
    assert "USER_AGENT" not in text
    assert "load_sic2" in text
    assert "SECTOR_SIC" in text


def test_do_not_read_lab_a_bars() -> None:
    for d in (date(2026, 1, 2), date(2026, 6, 5), date(2026, 8, 28)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
