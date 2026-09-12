from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS
from research.arrow47 import shares_for
from research.arrow75 import (
    BUCKET_OPEN,
    CONTROL_ID,
    EXPERIMENTS,
    HOME_LOOK,
    LONG_ID,
    morn_last_ok,
    prior_n,
)
from research.clock import (
    arrow74_sessions,
    arrow75_feature_sessions,
    feature_sessions,
    tape_root,
)
from research.costs import signed_pnl

ET = ZoneInfo("America/New_York")


def test_home_hour_uses_only_prior_10_not_t() -> None:
    feats = arrow75_feature_sessions()
    t = date(2026, 1, 16)
    prior = prior_n(t, HOME_LOOK, feats)
    assert prior is not None
    assert len(prior) == 10
    assert t not in prior
    assert all(p < t for p in prior)
    assert prior[-1] < t
    jan2 = date(2026, 1, 2)
    p2 = prior_n(jan2, HOME_LOOK, feats)
    assert p2 is not None
    assert jan2 not in p2
    assert p2[0] == date(2025, 12, 17)


def test_id0_short_only_id1_long_only() -> None:
    assert EXPERIMENTS[0][0] == CONTROL_ID == "short_left"
    assert EXPERIMENTS[0][2] == "short"
    assert EXPERIMENTS[1][0] == LONG_ID == "long_left"
    assert EXPERIMENTS[1][2] == "long"
    assert len(EXPERIMENTS) == 6
    assert all(e[2] == "short" for e in EXPERIMENTS if e[0].startswith("short_"))
    assert all(e[2] == "long" for e in EXPERIMENTS if e[0].startswith("long_"))
    assert signed_pnl(-1, 10, 20.0, 19.0) > 0
    assert signed_pnl(1, 10, 20.0, 21.0) > 0
    assert shares_for(20.0, 3000.0) == 150


def test_morn_1030_does_not_use_prints_at_or_after_1030() -> None:
    open_1030 = BUCKET_OPEN["1030"]
    assert open_1030 == time(10, 30)
    before = datetime(2026, 1, 16, 10, 29, tzinfo=ET)
    at = datetime(2026, 1, 16, 10, 30, tzinfo=ET)
    after = datetime(2026, 1, 16, 10, 31, tzinfo=ET)
    assert morn_last_ok(before, open_1030) is True
    assert morn_last_ok(at, open_1030) is False
    assert morn_last_ok(after, open_1030) is False


def test_march_is_not_scored() -> None:
    sess = arrow74_sessions()
    assert date(2026, 3, 2) not in sess
    assert all(d.month in {1, 2} for d in sess)
    leftover = feature_sessions()
    assert leftover[0] == date(2025, 12, 17)


def test_do_not_read_lab_a_or_full() -> None:
    assert tape_root(date(2026, 1, 2)) == VIRGIN_BARS
    assert tape_root(date(2026, 2, 3)) == VIRGIN_BARS
    assert tape_root(date(2025, 12, 17)) == VIRGIN_BARS
    for d in (date(2026, 1, 2), date(2026, 1, 16), date(2026, 2, 27)):
        assert tape_root(d) != BARS_DIR
        assert tape_root(d) != FULL_BARS
        assert tape_root(d) == VIRGIN_BARS
