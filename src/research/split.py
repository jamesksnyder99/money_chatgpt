from __future__ import annotations

from datetime import date

from ingest.calendar import study_sessions

N_DEVELOP = 42
N_HOLDOUT = 22


def develop_holdout() -> tuple[list[date], list[date]]:
    study = study_sessions()
    if len(study) != N_DEVELOP + N_HOLDOUT:
        raise ValueError(f"expected {N_DEVELOP + N_HOLDOUT} study sessions, got {len(study)}")
    return study[:N_DEVELOP], study[N_DEVELOP:]
