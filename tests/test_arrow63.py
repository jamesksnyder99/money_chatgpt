from pathlib import Path

from ingest.paths import (
    BARS_DIR,
    FULL_BARS,
    META_DIR,
    SECTOR_SIC,
    SECTOR_SIC_CSV,
    VIRGIN_BARS,
)
from ingest.sic import (
    SCORES_ENGINES,
    USER_AGENT,
    arrow63_output_roots,
    pad_sic4,
    request_headers,
    sic2_of,
)


def test_user_agent_header_is_set() -> None:
    headers = request_headers()
    assert headers["User-Agent"] == USER_AGENT
    assert "jks.michigan@gmail.com" in USER_AGENT
    assert USER_AGENT.strip()
    assert "python-requests" not in USER_AGENT.lower()
    assert "python-urllib" not in USER_AGENT.lower()
    assert headers["User-Agent"] != ""
    assert headers["User-Agent"] != "Python-urllib/3.12"


def test_sic2_is_first_two_digits_of_sic4() -> None:
    assert pad_sic4("7372") == "7372"
    assert sic2_of("7372") == "73"
    assert sic2_of(7372) == "73"
    assert pad_sic4("100") == "0100"
    assert sic2_of("100") == "01"
    assert sic2_of(100) == "01"
    assert sic2_of("0100") == "01"
    assert sic2_of(None) is None


def test_do_not_write_lab_a_bars_or_rebuild_tape() -> None:
    for p in arrow63_output_roots():
        assert p != BARS_DIR
        assert p != FULL_BARS
        assert p != VIRGIN_BARS
        assert BARS_DIR not in Path(p).parents
        assert FULL_BARS not in Path(p).parents
        assert VIRGIN_BARS not in Path(p).parents
    assert META_DIR != BARS_DIR
    assert SECTOR_SIC.parent == META_DIR
    assert SECTOR_SIC_CSV.parent == META_DIR
    assert "meta" in META_DIR.parts
    assert "bars" not in META_DIR.parts


def test_do_not_score_a_book() -> None:
    assert SCORES_ENGINES is False
    src = Path(__file__).resolve().parents[1] / "src" / "ingest" / "sic.py"
    text = src.read_text(encoding="utf-8")
    assert "from research" not in text
    assert "import research" not in text
    assert "run_arrow62" not in text
    assert "run_arrow64" not in text
    assert "SCORES_ENGINES = False" in text
