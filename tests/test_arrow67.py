from datetime import date

from ingest.calendar import (
    ARROW67_END,
    ARROW67_LABOR_DAY,
    ARROW67_START,
    ARROW67_THANKSGIVING,
    arrow67_non_sessions,
    arrow67_sessions,
)
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS, VIRGIN_EOD, VIRGIN_IWM
from ingest.virgin import (
    ARROW67_EOD_CHUNKS,
    arrow67_output_roots,
    ohlc_dates_to_pull,
)


def test_do_not_write_lab_a_bars() -> None:
    for p in arrow67_output_roots():
        assert p != BARS_DIR
        assert BARS_DIR not in p.parents
        assert "virgin" in p.parts or p.suffix == ".parquet"


def test_do_not_write_data_full() -> None:
    for p in arrow67_output_roots():
        assert p != FULL_BARS
        assert FULL_BARS not in p.parents
        assert "full" not in p.parts
    assert VIRGIN_BARS != FULL_BARS
    assert VIRGIN_EOD != FULL_BARS
    assert VIRGIN_IWM != FULL_BARS


def test_labor_day_and_thanksgiving_are_not_pulled() -> None:
    sess = arrow67_sessions()
    assert sess[0] == date(2025, 9, 2)
    assert sess[-1] == date(2025, 11, 28)
    assert ARROW67_LABOR_DAY not in sess
    assert ARROW67_THANKSGIVING not in sess
    assert date(2025, 11, 27) in arrow67_non_sessions()
    got = ohlc_dates_to_pull(
        [ARROW67_LABOR_DAY, date(2025, 9, 2), ARROW67_THANKSGIVING, date(2025, 11, 28)],
        set(),
        start=ARROW67_START,
        end=ARROW67_END,
    )
    assert ARROW67_LABOR_DAY not in got
    assert ARROW67_THANKSGIVING not in got
    assert date(2025, 9, 2) in got
    assert date(2025, 11, 28) in got


def test_2025_12_01_is_not_pulled() -> None:
    got = ohlc_dates_to_pull(
        [date(2025, 12, 1), date(2025, 11, 28), date(2025, 8, 29)],
        set(),
        start=ARROW67_START,
        end=ARROW67_END,
    )
    assert date(2025, 12, 1) not in got
    assert date(2025, 8, 29) not in got
    assert date(2025, 11, 28) in got
    assert all(ARROW67_START <= d <= ARROW67_END for d in got)


def test_december_2025_in_manifest_is_not_refetched() -> None:
    already = {date(2025, 12, 1), date(2025, 12, 17), date(2025, 9, 2)}
    got = ohlc_dates_to_pull(
        [date(2025, 12, 1), date(2025, 12, 17), date(2025, 9, 2), date(2025, 11, 28)],
        already,
        start=ARROW67_START,
        end=ARROW67_END,
    )
    assert date(2025, 12, 1) not in got
    assert date(2025, 12, 17) not in got
    assert date(2025, 9, 2) not in got
    assert date(2025, 11, 28) in got
    chunks = [c[2] for c in ARROW67_EOD_CHUNKS]
    assert "2025-11" not in chunks
    assert "2025-11-early" in chunks
