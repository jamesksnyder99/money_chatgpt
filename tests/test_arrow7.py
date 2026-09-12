from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.book import replay_session
from research.signals import Signal
from research.strategies5 import failed_yday_break_signals

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(sym, hh, mm, o, h, l, c, v, day=1):
    return {
        "symbol": sym,
        "bar_start": datetime(2026, 6, day, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session": "pre" if hh < 9 else "rth",
    }


def test_failed_yday_break_fires_on_failed_break() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.0, 10.5, 9.9, 10.2, 1000),  # break above 10.0
            _row("TEST", 9, 45, 10.2, 10.4, 9.8, 9.9, 1000),  # close back inside
            _row("TEST", 11, 59, 10.0, 10.1, 9.9, 10.0, 1000),
        ]
    )
    sigs = failed_yday_break_signals(df, prior_high=10.0, prior_low=8.0)
    assert len(sigs) == 1
    assert sigs[0].side == -1
    assert sigs[0].stop == 10.5  # failed extreme = session high after the break


def test_failed_yday_break_no_signal_on_clean_unfailed_break() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.0, 10.4, 9.9, 10.2, 1000),  # close > prior high
            _row("TEST", 9, 45, 10.2, 10.5, 10.1, 10.3, 1000),
            _row("TEST", 10, 30, 10.3, 10.6, 10.2, 10.4, 1000),
            _row("TEST", 10, 59, 10.4, 10.7, 10.3, 10.5, 1000),  # still outside
            _row("TEST", 11, 0, 10.5, 10.6, 9.8, 9.9, 1000),  # back inside after 11:00
            _row("TEST", 11, 59, 10.0, 10.1, 9.9, 10.0, 1000),
        ]
    )
    sigs = failed_yday_break_signals(df, prior_high=10.0, prior_low=8.0)
    assert sigs == []


def test_2r_target_is_twice_stop_distance() -> None:
    df = _bars(
        [
            _row("TEST", 9, 30, 10.0, 10.2, 9.9, 10.1, 5000),
            _row("TEST", 9, 31, 10.0, 10.1, 9.95, 10.05, 5000),  # fill
            _row("TEST", 9, 32, 10.05, 11.10, 10.0, 10.80, 5000),  # high hits 2R=11.0
            _row("TEST", 9, 33, 11.00, 11.10, 10.90, 11.00, 5000),  # target fill
            _row("TEST", 11, 59, 10.50, 10.60, 10.40, 10.50, 5000),
        ]
    )
    sig = Signal(df["bar_start"][0], "TEST", 1, 9.50, None, 1.0, "test")
    trades = replay_session({"TEST": df}, [sig], {"TEST": 50_000_000.0}, take_2r=True)
    assert trades
    tr = trades[0]
    stop_dist = tr.entry_px - 9.50
    assert stop_dist > 0
    assert abs((tr.exit_px - tr.entry_px) - 2.0 * stop_dist) < 1e-9
    assert tr.tag == "target"


def test_tight_book_never_exceeds_two_positions() -> None:
    bars = {}
    sigs = []
    for i, sym in enumerate(["A", "B", "C", "D"]):
        bars[sym] = _bars(
            [
                _row(sym, 9, 30, 10.0, 10.2, 9.9, 10.1, 5000),
                _row(sym, 9, 31, 10.1, 10.2, 10.0, 10.15, 5000),
                _row(sym, 11, 59, 10.0, 10.1, 9.9, 10.0, 5000),
            ]
        )
        sigs.append(
            Signal(bars[sym]["bar_start"][0], sym, 1, 9.50, None, float(4 - i), "test")
        )
    dv = {s: 50_000_000.0 for s in bars}
    trades = replay_session(
        bars, sigs, dv, max_positions=2, max_entries=4
    )

    def _peak(trs) -> int:
        ev = [(t.entry_ts, 1) for t in trs] + [(t.exit_ts, -1) for t in trs]
        ev.sort(key=lambda x: (x[0], x[1]))
        n = peak = 0
        for _, d in ev:
            n += d
            peak = max(peak, n)
        return peak

    assert _peak(trades) <= 2
    assert len({t.symbol for t in trades}) <= 2
    assert len(trades) <= 4
