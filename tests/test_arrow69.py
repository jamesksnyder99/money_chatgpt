from datetime import date

from ingest.calendar import (
    ARROW69_END,
    ARROW69_START,
    arrow69_sessions,
)
from ingest.paths import BARS_DIR, FULL_BARS, VIRGIN_BARS, VIRGIN_EOD, VIRGIN_IWM
from ingest.virgin import (
    ARROW69_EOD_CHUNKS,
    arrow69_output_roots,
    ohlc_dates_to_pull,
)


def test_do_not_write_lab_a_bars_or_full() -> None:
    for p in arrow69_output_roots():
        assert p != BARS_DIR
        assert p != FULL_BARS
        assert BARS_DIR not in p.parents
        assert FULL_BARS not in p.parents
        assert "virgin" in p.parts or p.suffix == ".parquet"
        assert "full" not in p.parts
    assert VIRGIN_BARS != FULL_BARS
    assert VIRGIN_EOD != FULL_BARS
    assert VIRGIN_IWM != FULL_BARS


def test_2025_09_02_is_not_pulled() -> None:
    sess = arrow69_sessions()
    assert sess[0] == date(2025, 8, 1)
    assert sess[-1] == date(2025, 8, 29)
    assert date(2025, 9, 2) not in sess
    assert date(2025, 7, 31) not in sess
    got = ohlc_dates_to_pull(
        [date(2025, 7, 31), date(2025, 8, 1), date(2025, 8, 29), date(2025, 9, 2)],
        set(),
        start=ARROW69_START,
        end=ARROW69_END,
    )
    assert date(2025, 9, 2) not in got
    assert date(2025, 7, 31) not in got
    assert date(2025, 8, 1) in got
    assert date(2025, 8, 29) in got
    assert all(ARROW69_START <= d <= ARROW69_END for d in got)


def test_september_2025_in_manifest_is_not_refetched() -> None:
    already = {date(2025, 9, 2), date(2025, 9, 3), date(2025, 8, 1)}
    got = ohlc_dates_to_pull(
        [date(2025, 9, 2), date(2025, 8, 1), date(2025, 8, 29)],
        already,
        start=ARROW69_START,
        end=ARROW69_END,
    )
    assert date(2025, 9, 2) not in got
    assert date(2025, 8, 1) not in got
    assert date(2025, 8, 29) in got
    chunks = [c[2] for c in ARROW69_EOD_CHUNKS]
    assert "2025-08" not in chunks
    assert "2025-08-early" in chunks
    assert "2025-07" in chunks
