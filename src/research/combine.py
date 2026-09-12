from __future__ import annotations

import math
import statistics

from research.arrow3 import _summarize


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2 or n != len(ys):
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx <= 1e-15 or dy <= 1e-15:
        return 0.0
    return num / (dx * dy)


def combine_books(*series: dict[str, float]) -> dict:
    """Union of session keys; a missing engine is $0 that day, not a dropped day."""
    if not series:
        empty = _summarize([], [], 0)
        empty.update({"sessions": [], "daily": [], "corr": {}, "n": 0, "aligned": []})
        return empty
    keys = sorted(set().union(*(s.keys() for s in series)))
    aligned = [[float(s.get(k, 0.0)) for k in keys] for s in series]
    daily = [sum(col) for col in zip(*aligned)]
    sm = _summarize(daily, [], len(keys))
    corr: dict[tuple[int, int], float] = {}
    for i in range(len(aligned)):
        for j in range(i + 1, len(aligned)):
            corr[(i, j)] = _pearson(aligned[i], aligned[j])
    sm.update(
        {
            "sessions": keys,
            "daily": daily,
            "aligned": aligned,
            "corr": corr,
            "n": len(keys),
        }
    )
    return sm
