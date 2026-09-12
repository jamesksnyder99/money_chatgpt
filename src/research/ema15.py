from __future__ import annotations

from datetime import datetime, time, timedelta

import polars as pl

from research.fills import tradeable_mask
from research.signals import bar_time

SPAN_FAST = 9
SPAN_SLOW = 21


def bar_end(ts: datetime, minutes: int) -> datetime:
    """Availability cut: a bucket starting at `ts` is complete at ts+minutes."""
    return ts + timedelta(minutes=minutes)


def resample_15m(
    df: pl.DataFrame, *, not_before: time | None = None
) -> list[tuple[datetime, float]]:
    """OHLC session 1m → 15m closes. Tradeable bars only.

    `not_before` drops prints before that clock (C-R3: 04:00 vs 07:30 stitch).
    A sparse bucket is not complete at its last traded minute; callers must
    cut incomplete bars with completed_15m_closes (bar_end = ts+15m).
    """
    if df.height == 0:
        return []
    ok = df.filter(tradeable_mask(df)).sort("bar_start")
    if ok.height == 0:
        return []
    if not_before is not None:
        times = ok["bar_start"].to_list()
        keep = [bar_time(t) >= not_before for t in times]
        ok = ok.filter(pl.Series("keep", keep))
        if ok.height == 0:
            return []
    ok = ok.with_columns(pl.col("bar_start").dt.truncate("15m").alias("b15"))
    g = (
        ok.group_by("b15")
        .agg(pl.col("close").sort_by("bar_start").last().alias("close"))
        .sort("b15")
    )
    out: list[tuple[datetime, float]] = []
    for rec in g.iter_rows(named=True):
        c = rec["close"]
        if c is None:
            continue
        out.append((rec["b15"], float(c)))
    return out


def resample_15m_by_symbol(df: pl.DataFrame) -> dict[str, list[tuple[datetime, float]]]:
    if df.height == 0:
        return {}
    ok = df.filter(tradeable_mask(df)).sort(["symbol", "bar_start"])
    if ok.height == 0:
        return {}
    ok = ok.with_columns(pl.col("bar_start").dt.truncate("15m").alias("b15"))
    g = (
        ok.group_by(["symbol", "b15"])
        .agg(pl.col("close").sort_by("bar_start").last().alias("close"))
        .sort(["symbol", "b15"])
    )
    out: dict[str, list[tuple[datetime, float]]] = {}
    for rec in g.iter_rows(named=True):
        c = rec["close"]
        if c is None:
            continue
        out.setdefault(str(rec["symbol"]), []).append((rec["b15"], float(c)))
    return out


def completed_15m_closes(
    stitched: list[tuple[datetime, float]], decision_ts: datetime
) -> list[float]:
    """Closes of 15m bars that have fully ended at or before decision_ts."""
    out: list[float] = []
    delta = timedelta(minutes=15)
    for ts, c in stitched:
        if ts + delta <= decision_ts:
            out.append(c)
        else:
            break
    return out


def ema_last(closes: list[float], span: int) -> float | None:
    """Standard EMA (span); seed with SMA of the first `span` closes. None if too short."""
    n = len(closes)
    if n < span or span < 1:
        return None
    alpha = 2.0 / (span + 1.0)
    prev = sum(closes[:span]) / span
    for i in range(span, n):
        prev = alpha * closes[i] + (1.0 - alpha) * prev
    return prev


def ema9_at(
    stitched: list[tuple[datetime, float]], decision_ts: datetime
) -> float | None:
    """Last completed-bar ema9 before decision_ts, or None if the stack is not ready."""
    closes = completed_15m_closes(stitched, decision_ts)
    return ema_last(closes, SPAN_FAST)


def ema_stack(
    stitched: list[tuple[datetime, float]], decision_ts: datetime
) -> str | None:
    """'long' if ema9 > ema21, 'short' if ema9 < ema21, else None. Completed bars only."""
    closes = completed_15m_closes(stitched, decision_ts)
    e9 = ema_last(closes, SPAN_FAST)
    e21 = ema_last(closes, SPAN_SLOW)
    if e9 is None or e21 is None:
        return None
    if e9 > e21:
        return "long"
    if e9 < e21:
        return "short"
    return None


def stitch_15m(
    symbol: str,
    session_iso: str,
    session_order: list[str],
    bars15: dict[tuple[str, str], list[tuple[datetime, float]]],
) -> list[tuple[datetime, float]]:
    """Prior sessions in order, then this session. Caller cuts incomplete bars by time."""
    out: list[tuple[datetime, float]] = []
    for iso in session_order:
        if iso > session_iso:
            break
        part = bars15.get((symbol, iso))
        if part:
            out.extend(part)
    return out
