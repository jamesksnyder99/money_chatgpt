import inspect
from datetime import datetime
from zoneinfo import ZoneInfo

import polars as pl

from research.harness import confirmed_launch
from research.strategies29 import (
    cell_buy_gate,
    cell_buy_long,
    flush_vs_anchor,
    forward_ext,
    launch_compatible_long,
    path_from_0944,
)

ET = ZoneInfo("America/New_York")


def _bars(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("bar_start").dt.replace_time_zone("America/New_York")
    )


def _row(hh, mm, o, h, l, c, v=1000):
    return {
        "symbol": "TEST",
        "bar_start": datetime(2026, 6, 1, hh, mm, tzinfo=ET),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "session_part": "pre" if hh < 9 or (hh == 9 and mm < 30) else "rth",
    }


def _pack_from_rows(rows: list[dict]) -> dict:
    return {
        "ts": [r["bar_start"] for r in rows],
        "open": [r["open"] for r in rows],
        "high": [r["high"] for r in rows],
        "low": [r["low"] for r in rows],
        "close": [r["close"] for r in rows],
        "vol": [r["volume"] for r in rows],
    }


def test_part_a_uses_0944_close_not_prior_close() -> None:
    px44, pc, px1159 = 10.50, 10.00, 11.025
    vs44 = forward_ext(px1159, px44)
    vs_pc = forward_ext(px1159, pc)
    assert vs44 is not None and vs_pc is not None
    assert abs(vs44 - (11.025 / 10.50 - 1.0)) < 1e-12
    assert abs(vs44 - vs_pc) > 1e-3
    rows = [
        _row(9, 44, 10.40, 10.60, 10.30, 10.50),
        _row(9, 45, 10.50, 10.80, 10.45, 10.70),
        _row(11, 59, 11.00, 11.10, 10.90, 11.025),
    ]
    pack = _pack_from_rows(rows)
    rec = path_from_0944(pack, px44=10.50, or_low=10.20, atr=0.20, i44=0)
    assert rec["ext1159_44"] is not None
    assert abs(rec["ext1159_44"] - vs44) < 1e-12
    assert abs(rec["ext1159_44"] - vs_pc) > 1e-3


def test_id4_never_reads_0800_last_px() -> None:
    assert "0800" not in inspect.signature(flush_vs_anchor).parameters
    assert "last_px_0800" not in inspect.signature(flush_vs_anchor).parameters
    # 08:00 last=10, 09:44 close=11. Flush to 10.70 is 2.7% vs 11, not 2% vs 10.
    df = _bars(
        [
            _row(8, 0, 10.00, 10.20, 9.90, 10.00),
            _row(9, 44, 11.00, 11.10, 10.90, 11.00),
            _row(9, 50, 10.90, 10.95, 10.70, 10.80),
            _row(9, 55, 10.85, 11.05, 10.78, 11.05),
        ]
    )
    sigs = flush_vs_anchor(df, 11.00, tag="flush_0944")
    assert sigs
    assert all(s.side == 1 for s in sigs)
    assert flush_vs_anchor(df, 10.00, tag="if_0800") == []


def test_id6_rejects_12pct_wick_close_6pct() -> None:
    pc = 10.0
    rows = [
        _row(9, 30, 10.20, 11.20, 10.10, 10.60),  # +12% wick, close +6%
        _row(9, 31, 10.60, 10.70, 10.50, 10.65),
        _row(9, 45, 10.70, 10.80, 10.60, 10.75),
    ]
    df = _bars(rows)
    pack = _pack_from_rows(rows)
    rec = confirmed_launch(pack, pc)
    assert rec["confirmed"] is False
    sigs = launch_compatible_long(
        df,
        pack,
        pc,
        ext_0929=0.02,
        orw=0.06,
        dv0929=200_000.0,
        cumdv=[0.0] * 720,
        prior_cum=[[1.0] * 720] * 10,
    )
    assert sigs == []


def test_cell_buy_silent_if_gate_fails() -> None:
    assert cell_buy_gate(median_ext_1159=-0.01, frac_1atr_before_or=0.50) is False
    assert cell_buy_gate(median_ext_1159=0.02, frac_1atr_before_or=0.20) is False
    assert cell_buy_gate(median_ext_1159=0.02, frac_1atr_before_or=0.40) is True
    df = _bars([_row(9, 44, 10.0, 10.2, 9.9, 10.1), _row(9, 45, 10.1, 10.3, 10.0, 10.2)])
    ts = df["bar_start"][0]
    assert cell_buy_long(df, signal_ts=ts, or_low=9.80, rel0944=4.0, gate=False) == []
    sigs = cell_buy_long(df, signal_ts=ts, or_low=9.80, rel0944=4.0, gate=True)
    assert sigs
    assert all(s.side == 1 for s in sigs)
