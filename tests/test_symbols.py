from ingest.paths import eod_path, safe_symbol_filename
from ingest.symbols import filter_candidates, filter_common, is_common_stock_ticker, is_etp_ticker


def test_keeps_common_and_class_shares() -> None:
    assert is_common_stock_ticker("AAPL")
    assert is_common_stock_ticker("BRK.B")
    assert is_common_stock_ticker("BF.A")
    assert is_common_stock_ticker("AA")


def test_drops_preferred_warrant_unit_wi() -> None:
    assert not is_common_stock_ticker(".PR.I.PR.A")
    assert not is_common_stock_ticker("BAC.PR")
    assert not is_common_stock_ticker("F.WS")
    assert not is_common_stock_ticker("XYZ.U")
    assert not is_common_stock_ticker("ABC/WI")
    assert not is_common_stock_ticker("ABC.WI")
    assert not is_common_stock_ticker(".PR.S/WI")


def test_filter_common_dedupes() -> None:
    out = filter_common(["aapl", "AAPL", "BAC.PR", "BRK.B", ".PR.I.PR.A"])
    assert out == ["AAPL", "BRK.B"]


def test_windows_reserved_filenames() -> None:
    assert safe_symbol_filename("AAPL") == "AAPL"
    assert safe_symbol_filename("CON") == "_CON"
    assert safe_symbol_filename("PRN") == "_PRN"
    assert eod_path("CON").name != "CON.parquet"
    assert eod_path("CON").name == "_CON.parquet"
    assert eod_path("PRN").name != "PRN.parquet"
    for stem in ("CON", "PRN", "AUX", "NUL", "COM1", "LPT1"):
        assert eod_path(stem).name != f"{stem}.parquet"


def test_etp_denylist_drops_levered_and_index_etfs() -> None:
    assert is_etp_ticker("SPY")
    assert is_etp_ticker("SOXL")
    assert is_etp_ticker("TQQQ")
    assert not is_etp_ticker("AAPL")
    cands, funnel = filter_candidates(["AAPL", "SPY", "SOXL", "TQQQ", "BAC.PR"])
    assert "AAPL" in cands
    assert "SPY" not in cands
    assert funnel["etp_dropped"] >= 3
    assert funnel["regex_kept"] == 4  # BAC.PR dropped by regex
