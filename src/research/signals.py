from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

RTH_OPEN = time(9, 30)
MINUTE_0934 = time(9, 34)
MINUTE_0935 = time(9, 35)
MINUTE_1000 = time(10, 0)
MINUTE_1015 = time(10, 15)
MINUTE_1100 = time(11, 0)
MINUTE_1200 = time(12, 0)
MINUTE_1300 = time(13, 0)
MINUTE_1330 = time(13, 30)
MINUTE_1430 = time(14, 30)
MINUTE_0944 = time(9, 44)
MINUTE_0945 = time(9, 45)
MINUTE_0950 = time(9, 50)
MINUTE_1045 = time(10, 45)
MINUTE_1130 = time(11, 30)
MINUTE_1150 = time(11, 50)
MINUTE_1158 = time(11, 58)
MINUTE_1159 = time(11, 59)
MINUTE_1559 = time(15, 59)
MINUTE_0929 = time(9, 29)


@dataclass(frozen=True, slots=True)
class Signal:
    """Decision at signal_ts close; fill at the next tradeable open (unless overnight)."""

    signal_ts: datetime
    symbol: str
    side: int  # +1 long, -1 short
    stop: float
    target: float | None
    score: float  # rank competing signals at the same timestamp
    tag: str
    stop_from_entry: bool = False
    overnight: bool = False
    atr: float = 0.0


def bar_time(ts: datetime) -> time:
    return ts.timetz().replace(tzinfo=None) if ts.tzinfo else ts.time()
