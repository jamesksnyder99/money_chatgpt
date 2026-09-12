from datetime import date

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow62 import (
    CONTROL_ID,
    EXPERIMENTS,
    LONG_H1,
    hold_month_exit,
    hold_n,
    prior_month_return,
    prior_month_stamps,
    select_max,
    select_min,
)
from research.clock import (
    arrow62_feature_sessions,
    entry_split,
    feature_sessions,
    is_is_session,
    month_first_last,
    tape_root,
)
from research.costs import signed_pnl


def test_id0_short_only_id1_long_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "short_max_m"
    assert EXPERIMENTS[0][1] == "short"
    assert EXPERIMENTS[1][0] == LONG_H1 == "long_min_m"
    assert EXPERIMENTS[1][1] == "long"
    assert len(EXPERIMENTS) == 6
    assert all(e[1] == "short" for e in EXPERIMENTS if e[0].startswith("short_"))
    assert all(e[1] == "long" for e in EXPERIMENTS if e[0].startswith("long_"))
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 21.0) > 0
    assert shares_for(20.0, 3000.0) == 150
    assert shares_for(20.0, 4000.0) == 200


def test_january_2026_entry_uses_december_2025_virgin() -> None:
    feats = arrow62_feature_sessions()
    stamps = month_first_last(2025, 12, feats)
    assert stamps == (date(2025, 12, 1), date(2025, 12, 31))
    assert tape_root(stamps[0]) == VIRGIN_BARS
    assert tape_root(stamps[1]) == VIRGIN_BARS
    entry = month_first_last(2026, 1, feats)[0]
    assert entry == date(2026, 1, 2)
    assert prior_month_stamps(entry, feats) == stamps
    assert tape_root(entry) == VIRGIN_BARS
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)
    assert feats[0] == date(2025, 12, 1)
    nr = prior_month_return(100.0, 110.0)
    assert nr is not None and abs(nr - 0.10) < 1e-12
    assert prior_month_return(None, 110.0) is None
    rows = [
        {"ret": 0.02, "symbol": "A"},
        {"ret": 0.10, "symbol": "B"},
        {"ret": -0.05, "symbol": "C"},
        {"ret": 0.10, "symbol": "D"},
    ]
    assert [r["symbol"] for r in select_max(rows, 2)] == ["B", "D"]
    assert [r["symbol"] for r in select_min(rows, 1)] == ["C"]


def test_hold_month_exits_last_session_of_m_hold_10_ten_later() -> None:
    sess = [
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
        date(2026, 1, 13),
        date(2026, 1, 14),
        date(2026, 1, 15),
        date(2026, 1, 16),
        date(2026, 1, 30),
        date(2026, 2, 2),
    ]
    entry = date(2026, 1, 2)
    assert EXPERIMENTS[0][4] == "month"
    assert EXPERIMENTS[2][4] == "h10"
    assert hold_month_exit(entry, sess) == date(2026, 1, 30)
    assert hold_n(entry, 10, sess) == date(2026, 1, 16)
    assert hold_month_exit(entry, sess) != hold_n(entry, 10, sess)
    feats = arrow62_feature_sessions()
    assert hold_month_exit(date(2026, 1, 2), feats) == date(2026, 1, 30)
    assert hold_n(date(2026, 1, 2), 10, feats) == date(2026, 1, 16)


def test_even_month_entry_is_not_is() -> None:
    assert entry_split(date(2026, 2, 2)) == "OOS"
    assert not is_is_session(date(2026, 2, 2))
    assert is_is_session(date(2026, 1, 2))
    assert entry_split(date(2026, 7, 1)) == "IS"


def test_do_not_read_lab_a_bars() -> None:
    for d in (
        date(2025, 12, 1),
        date(2025, 12, 31),
        date(2026, 1, 2),
        date(2026, 6, 1),
        date(2026, 7, 1),
        date(2026, 8, 31),
    ):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) in {VIRGIN_BARS, FULL_BARS}
    assert tape_root(date(2025, 12, 1)) == VIRGIN_BARS
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 6, 1)) == FULL_BARS
    assert tape_root(date(2026, 7, 1)) == FULL_BARS
