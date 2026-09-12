from __future__ import annotations

from collections import defaultdict
from datetime import date

import polars as pl

from research.fills import tradeable_mask
from research.signals import MINUTE_0944, MINUTE_0945, MINUTE_1159, RTH_OPEN, bar_time

Q_EDGES = (0.0, 0.2, 0.4, 0.6, 0.8, 1.01)
Q_LABELS = ("Q1", "Q2", "Q3", "Q4", "Q5")


def dv_ranks(dv_by_sym: dict[str, float]) -> dict[str, float]:
    """Percentile rank in [0, 1]: fraction of session names with strictly lower DV.
    dv_rank >= 0.80 is the top fifth when values are unique.
    """
    n = len(dv_by_sym)
    if n == 0:
        return {}
    if n == 1:
        return {s: 1.0 for s in dv_by_sym}
    vals = list(dv_by_sym.values())
    out: dict[str, float] = {}
    for s, v in dv_by_sym.items():
        less = sum(1 for x in vals if x < v)
        out[s] = less / (n - 1)
    return out


def sessions_for_character(
    sessions: list[date], develop: list[date] | None = None
) -> list[date]:
    """If a develop list is passed, holdout (and any other) dates are ignored."""
    if develop is None:
        return list(sessions)
    allow = set(develop)
    return [d for d in sessions if d in allow]


def quintile(rank: float) -> str:
    if rank >= 0.80:
        return "Q5"
    if rank >= 0.60:
        return "Q4"
    if rank >= 0.40:
        return "Q3"
    if rank >= 0.20:
        return "Q2"
    return "Q1"


def gap_bucket(abs_gap: float) -> str:
    if abs_gap >= 0.02 - 1e-12:
        return ">=2%"
    if abs_gap >= 0.005 - 1e-12:
        return "0.5-2%"
    return "<0.5%"


def orw_bucket(w: float) -> str:
    if w > 0.04 + 1e-12:
        return ">4%"
    if w >= 0.01 - 1e-12:
        return "1-4%"
    return "<1%"


def name_day_character(bars: pl.DataFrame, prior_close: float | None) -> dict | None:
    """Point-in-time features for one name-day. None if OR / post-OR / 09:30 missing."""
    if bars.height == 0:
        return None
    df = bars.filter(tradeable_mask(bars)).sort("bar_start")
    if df.height == 0:
        return None
    times = [bar_time(t) for t in df["bar_start"].to_list()]
    highs = df["high"].to_list()
    lows = df["low"].to_list()
    closes = df["close"].to_list()
    opens = df["open"].to_list()
    vols = df["volume"].to_list()
    stamps = df["bar_start"].to_list()

    or_hi = or_lo = None
    or_dollar = 0.0
    close_0944 = None
    open930 = None
    post_hi = post_lo = None
    close_1159 = None
    last_rth_close = None
    ext_hi = ext_lo = None
    ext_hi_ts = ext_lo_ts = None

    for i, t in enumerate(times):
        if t < RTH_OPEN:
            continue
        h, l, c, o, v = float(highs[i]), float(lows[i]), float(closes[i]), float(opens[i]), float(vols[i])
        last_rth_close = c
        if t == RTH_OPEN:
            open930 = o
        if RTH_OPEN <= t <= MINUTE_0944:
            or_hi = h if or_hi is None else max(or_hi, h)
            or_lo = l if or_lo is None else min(or_lo, l)
            or_dollar += ((h + l + c) / 3.0) * v
            close_0944 = c
        if t >= MINUTE_0945:
            post_hi = h if post_hi is None else max(post_hi, h)
            post_lo = l if post_lo is None else min(post_lo, l)
        if t == MINUTE_1159:
            close_1159 = c
        if ext_hi is None or h > ext_hi:
            ext_hi, ext_hi_ts = h, stamps[i]
        if ext_lo is None or l < ext_lo:
            ext_lo, ext_lo_ts = l, stamps[i]

    if or_hi is None or or_lo is None or open930 is None or open930 <= 0:
        return None
    mid = (or_hi + or_lo) / 2.0
    if mid <= 0:
        return None
    or_w = (or_hi - or_lo) / mid
    post_or_range = None
    if post_hi is not None and post_lo is not None:
        post_or_range = (post_hi - post_lo) / mid
    post_or_exc = None
    end_c = close_1159 if close_1159 is not None else last_rth_close
    if close_0944 is not None and close_0944 > 0 and end_c is not None:
        post_or_exc = end_c / close_0944 - 1.0
    gap = None
    if prior_close is not None and prior_close > 0:
        gap = open930 / float(prior_close) - 1.0

    rth_close = close_1159 if close_1159 is not None else last_rth_close
    max_ext_hour = None
    if rth_close is not None and open930 is not None and ext_hi_ts is not None and ext_lo_ts is not None:
        ts = ext_hi_ts if rth_close > open930 else ext_lo_ts
        hr = bar_time(ts).hour
        if hr in (9, 10, 11):
            max_ext_hour = hr

    return {
        "or_w": or_w,
        "or_dollar": or_dollar,
        "post_or_range": post_or_range,
        "post_or_exc": post_or_exc,
        "gap": gap,
        "max_ext_hour": max_ext_hour,
    }


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def summarize_character(rows: list[dict]) -> dict:
    by_q: dict[str, list[float]] = {k: [] for k in Q_LABELS}
    by_gap: dict[str, list[float]] = {"<0.5%": [], "0.5-2%": [], ">=2%": []}
    by_orw: dict[str, list[float]] = {"<1%": [], "1-4%": [], ">4%": []}
    by_tr: dict[str, list[float]] = {"up": [], "down": [], "flat": []}
    by_hr: dict[int, int] = {9: 0, 10: 0, 11: 0}
    cross: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    n_used = 0
    for r in rows:
        por = r.get("post_or_range")
        if por is None:
            continue
        n_used += 1
        q = r.get("quintile") or quintile(float(r.get("dv_rank") or 0.0))
        by_q[q].append(por)
        g = r.get("gap")
        gb = gap_bucket(abs(g)) if g is not None else None
        if gb:
            by_gap[gb].append(por)
        w = r.get("or_w")
        ob = orw_bucket(w) if w is not None else None
        if ob:
            by_orw[ob].append(por)
        tr = r.get("trend") or "flat"
        if tr not in by_tr:
            tr = "flat"
        by_tr[tr].append(por)
        hr = r.get("max_ext_hour")
        if hr in by_hr:
            by_hr[hr] += 1
        if q == "Q5" and gb and ob:
            cross[(q, gb, ob)].append(por)
    return {
        "n_rows": len(rows),
        "n_used": n_used,
        "by_q": {k: (_mean(v), len(v)) for k, v in by_q.items()},
        "by_gap": {k: (_mean(v), len(v)) for k, v in by_gap.items()},
        "by_orw": {k: (_mean(v), len(v)) for k, v in by_orw.items()},
        "by_tr": {k: (_mean(v), len(v)) for k, v in by_tr.items()},
        "by_hr": dict(by_hr),
        "cross_q5": {k: (_mean(v), len(v)) for k, v in cross.items()},
    }


def movement_paragraph(tables: dict[str, dict]) -> str:
    """Prose from develop tables only. Does not inspect holdout."""
    bits = []
    for trk, sm in tables.items():
        q = sm["by_q"]
        q1, n1 = q["Q1"]
        q5, n5 = q["Q5"]
        gap = sm["by_gap"]
        orw = sm["by_orw"]
        best_gap = max(gap.items(), key=lambda kv: kv[1][0] if kv[1][1] else -1)
        best_orw = max(orw.items(), key=lambda kv: kv[1][0] if kv[1][1] else -1)
        cross = sm["cross_q5"]
        best_x = None
        if cross:
            best_x = max(cross.items(), key=lambda kv: kv[1][0] if kv[1][1] else -1)
        hr = sm["by_hr"]
        hr_tot = sum(hr.values()) or 1
        hr_line = ", ".join(f"{h}h {hr[h]} ({100.0 * hr[h] / hr_tot:.0f}%)" for h in (9, 10, 11))
        x_txt = "n/a"
        if best_x:
            (_q, gb, ob), (mu, n) = best_x
            x_txt = f"Q5 × |gap| {gb} × OR {ob} (mean {100 * mu:.2f}% n={n})"
        bits.append(
            f"Track {trk}: post-09:44 range is "
            f"{'larger' if q5 > q1 else 'not larger'} in Q5 ({100 * q5:.2f}% n={n5}) than Q1 "
            f"({100 * q1:.2f}% n={n1}). Highest |gap| bucket is {best_gap[0]} "
            f"({100 * best_gap[1][0]:.2f}% n={best_gap[1][1]}); highest OR-width bucket is "
            f"{best_orw[0]} ({100 * best_orw[1][0]:.2f}% n={best_orw[1][1]}). "
            f"Q5 intersection with the most leftover range: {x_txt}. "
            f"Session extremes by clock: {hr_line}."
        )
    lead = (
        "On develop, leftover range after 09:44 concentrates where the tables are tallest: "
        "liquid names (Q5) that already printed a real opening range and/or a real gap. "
    )
    return lead + " ".join(bits)


def format_character_report(
    by_track: dict[str, dict],
    develop: list[date],
) -> str:
    lines = [
        "Arrow 9 Phase 1 — characterize movers (develop sessions only)",
        f"develop n={len(develop)} {develop[0]}..{develop[-1]}",
        "Holdout bars were not used to choose buckets, thresholds, or this paragraph.",
        "post_or_range = (09:45-11:59 high-low) / 09:44 OR mid.",
        "",
    ]
    for trk, sm in by_track.items():
        lines.append(f"Track {trk} name-days={sm['n_rows']} with post-OR range={sm['n_used']}")
        lines.append("  mean post_or_range by DV quintile (Q1=smallest DV … Q5=largest):")
        for lab in Q_LABELS:
            mu, n = sm["by_q"][lab]
            lines.append(f"    {lab}: {100 * mu:7.3f}%  n={n}")
        lines.append("  mean post_or_range by |gap|:")
        for lab in ("<0.5%", "0.5-2%", ">=2%"):
            mu, n = sm["by_gap"][lab]
            lines.append(f"    {lab}: {100 * mu:7.3f}%  n={n}")
        lines.append("  mean post_or_range by OR width:")
        for lab in ("<1%", "1-4%", ">4%"):
            mu, n = sm["by_orw"][lab]
            lines.append(f"    {lab}: {100 * mu:7.3f}%  n={n}")
        lines.append("  mean post_or_range by 10d trend:")
        for lab in ("up", "down", "flat"):
            mu, n = sm["by_tr"][lab]
            lines.append(f"    {lab}: {100 * mu:7.3f}%  n={n}")
        lines.append("  session-extreme clock hour counts:")
        for h in (9, 10, 11):
            lines.append(f"    {h:02d}: {sm['by_hr'][h]}")
        lines.append("  Q5 × |gap| × OR-width mean post_or_range:")
        keys = sorted(sm["cross_q5"].items(), key=lambda kv: -kv[1][0])
        if not keys:
            lines.append("    (none)")
        for (_q, gb, ob), (mu, n) in keys:
            lines.append(f"    |gap| {gb:>6}  OR {ob:>4}: {100 * mu:7.3f}%  n={n}")
        lines.append("")
    lines.append("Where movement lives (develop only):")
    lines.append(movement_paragraph(by_track))
    lines.append("")
    return "\n".join(lines)
