from __future__ import annotations

import subprocess

from ingest.paths import (
    CALENDAR,
    DATA,
    FULL_BARS,
    FULL_ELIGIBILITY,
    FULL_IWM,
    META_DIR,
    REPO_ROOT,
    SPLITS,
    VIRGIN_BARS,
    VIRGIN_ELIGIBILITY,
    VIRGIN_IWM,
)
from research.arrow43 import MAX_PX, MIN_PDV, MIN_PX
from research.arrow55 import HOLD, LB, MIN_RESIDUAL, N_SHORT
from research.arrow66 import CONTROL_ID, FILL_KIND
from research.arrow70 import BASE_TICKET, KEEP, arrow70_signal_dates


def test_lab_paths_are_repository_relative() -> None:
    root = REPO_ROOT.resolve()
    assert root.name.casefold() == "money_chatgpt"
    assert DATA.resolve().is_relative_to(root)

    for path in (
        CALENDAR,
        FULL_BARS,
        FULL_ELIGIBILITY,
        FULL_IWM,
        META_DIR,
        SPLITS,
        VIRGIN_BARS,
        VIRGIN_ELIGIBILITY,
        VIRGIN_IWM,
    ):
        assert path.resolve().is_relative_to(root)


def test_canonical_market_data_paths_are_git_ignored() -> None:
    probes = (
        "data/calendar/sessions.parquet",
        "data/full/bars/2099-01-01/PROBE.parquet",
        "data/full/eligibility.parquet",
        "data/meta/sector_sic.parquet",
        "data/ref/symbols_common.parquet",
        "data/virgin/bars/2099-01-01/PROBE.parquet",
        "data/virgin/eligibility.parquet",
    )
    for probe in probes:
        result = subprocess.run(
            ["git", "check-ignore", "--no-index", "--quiet", probe],
            cwd=REPO_ROOT,
            check=False,
        )
        assert result.returncode == 0, probe


def test_frozen_hold_short_for_fade_parent_parameters() -> None:
    assert CONTROL_ID == "h10_4k"
    assert FILL_KIND == "nextrth"
    assert (MIN_PX, MAX_PX, MIN_PDV) == (10.0, 80.0, 10_000_000.0)
    assert (N_SHORT, LB, HOLD, MIN_RESIDUAL) == (8, 15, 10, 16)
    assert BASE_TICKET == 4_000.0
    assert KEEP is False
    assert all(signal.weekday() == 2 for signal in arrow70_signal_dates())
