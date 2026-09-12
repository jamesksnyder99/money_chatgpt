from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ingest.calendar import all_2026_sessions, prior_n_sessions

_ALL = all_2026_sessions()
_IDX = {d: i for i, d in enumerate(_ALL)}


def classify_trend(closes: list[float]) -> str:
    """closes oldest→newest, length 10. Up/down/flat per Arrow 5."""
    if len(closes) < 10:
        return "flat"
    if any(c is None or c <= 0 for c in closes):
        return "flat"
    c1, c10 = closes[0], closes[-1]
    mu = sum(closes) / 10.0
    if c10 > c1 and c10 > mu:
        return "up"
    if c10 < c1 and c10 < mu:
        return "down"
    return "flat"


def prior10(session: date) -> list[date] | None:
    i = _IDX.get(session)
    if i is None or i < 10:
        return prior_n_sessions(session, 10)
    return _ALL[i - 10 : i]


@dataclass(frozen=True, slots=True)
class Trend:
    side: str  # up | down | flat
    c1: float
    c10: float
    mean: float
    score: float  # |C10/C1 - 1|


def trend_for(
    symbol: str,
    session: date,
    prior_close: dict[tuple[str, str], float],
) -> Trend | None:
    """C10 = prior_close[session]; Ck = prior_close[S_{k+1}] for k<10."""
    s = prior10(session)
    if not s or len(s) < 10:
        return None
    closes: list[float] = []
    for k in range(9):
        # C_{k+1} = EOD of S_{k+1} = prior_close of S_{k+2}
        key = (symbol, s[k + 1].isoformat())
        v = prior_close.get(key)
        if v is None or v <= 0:
            return None
        closes.append(float(v))
    v10 = prior_close.get((symbol, session.isoformat()))
    if v10 is None or v10 <= 0:
        return None
    closes.append(float(v10))
    side = classify_trend(closes)
    c1, c10 = closes[0], closes[-1]
    mu = sum(closes) / 10.0
    score = abs(c10 / c1 - 1.0) if c1 else 0.0
    return Trend(side=side, c1=c1, c10=c10, mean=mu, score=score)
