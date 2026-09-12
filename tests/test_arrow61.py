from datetime import date

from ingest.calendar import (
    ARROW61_END,
    ARROW61_EXPECTED,
    ARROW61_START,
    arrow61_sessions,
)
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS, VIRGIN_EOD, VIRGIN_IWM
from ingest.virgin import (
    arrow61_output_roots,
    ohlc_dates_to_pull,
)


def test_do_not_write_lab_a_bars() -> None:
    for p in arrow61_output_roots():
        assert p != BARS_DIR
        assert BARS_DIR not in p.parents
        assert "virgin" in p.parts or p.suffix == ".parquet"


def test_do_not_write_data_full() -> None:
    for p in arrow61_output_roots():
        assert p != FULL_BARS
        assert FULL_BARS not in p.parents
        assert "full" not in p.parts
    assert VIRGIN_BARS != FULL_BARS
    assert VIRGIN_EOD != FULL_BARS
    assert VIRGIN_IWM != FULL_BARS


def test_dates_before_2025_12_01_are_not_pulled() -> None:
    sess = arrow61_sessions()
    assert sess[0] == date(2025, 12, 1)
    assert sess[-1] == date(2025, 12, 16)
    assert date(2025, 11, 28) not in sess
    assert all(d >= ARROW61_START for d in sess)
    got = ohlc_dates_to_pull(
        [date(2025, 11, 28), date(2025, 12, 1), date(2025, 12, 16)],
        set(),
    )
    assert date(2025, 11, 28) not in got
    assert date(2025, 12, 1) in got
    assert list(sess) == list(ARROW61_EXPECTED)


def test_2025_12_17_not_refetched_if_in_manifest() -> None:
    already = {date(2025, 12, 17), date(2025, 12, 18), date(2025, 12, 1)}
    got = ohlc_dates_to_pull(list(ARROW61_EXPECTED) + [date(2025, 12, 17)], already)
    assert date(2025, 12, 17) not in got
    assert date(2025, 12, 17) > ARROW61_END
    assert date(2025, 12, 1) not in got
    assert date(2025, 12, 16) in got
    forced = ohlc_dates_to_pull([date(2025, 12, 17)], already, force=True)
    assert date(2025, 12, 17) not in forced
