from datetime import date

import polars as pl
import pytest

from ingest.paths import REPO_ROOT
from research.cg_arrow002_preflight import assess_splits, inspect_splits


def test_empty_placeholder_cannot_certify_split_safety():
    frame = pl.DataFrame(
        schema={"symbol": pl.String, "ex_date": pl.Date, "factor": pl.Float64}
    )
    assert assess_splits(frame)["status"] == "BLOCKED"


def test_missing_schema_blocks():
    assert assess_splits(pl.DataFrame({"symbol": ["TEST"]}))["status"] == "BLOCKED"


@pytest.mark.parametrize("factor", [0.0, -1.0, float("nan"), float("inf"), None])
def test_invalid_split_factor_blocks(factor):
    frame = pl.DataFrame(
        {"symbol": ["TEST"], "ex_date": [date(2026, 1, 2)], "factor": [factor]},
        schema_overrides={"factor": pl.Float64},
    )
    assert assess_splits(frame)["status"] == "BLOCKED"


def test_nonempty_events_still_need_coverage_and_adjustment_review():
    frame = pl.DataFrame(
        {"symbol": ["TEST"], "ex_date": [date(2026, 1, 2)], "factor": [2.0]}
    )
    assert assess_splits(frame)["status"] == "REVIEW_REQUIRED"


def test_outside_path_rejected_before_read(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("An out-of-lab path reached the parquet reader")

    monkeypatch.setattr(pl, "read_parquet", forbidden)
    with pytest.raises(ValueError, match="inside the lab"):
        inspect_splits(REPO_ROOT.parent / "outside_test_fixture.parquet")


def test_lexical_parent_escape_rejected_before_read(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("A parent escape reached the parquet reader")

    monkeypatch.setattr(pl, "read_parquet", forbidden)
    with pytest.raises(ValueError, match="inside the lab"):
        inspect_splits(REPO_ROOT / ".." / "outside_test_fixture.parquet")
