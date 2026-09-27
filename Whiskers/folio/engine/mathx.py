"""Arithmetic on dated series. Pure functions, no database, easy to test.

A series is a list of (iso_date, value) sorted by date.
"""

from __future__ import annotations

import bisect
import datetime as dt


def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = []
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        out.append(total / n if i >= n - 1 else None)
    return out


def rolling_max(values: list[float], n: int) -> list[float]:
    """Highest value in the trailing window, O(n) with a monotonic queue."""
    from collections import deque
    q: deque[int] = deque()
    out = []
    for i, v in enumerate(values):
        while q and values[q[-1]] <= v:
            q.pop()
        q.append(i)
        if q[0] <= i - n:
            q.popleft()
        out.append(values[q[0]])
    return out


def drawdowns(values: list[float], window: int = 252) -> list[float]:
    """How far below its trailing high each value sits, as a positive fraction."""
    highs = rolling_max(values, window)
    return [0.0 if h <= 0 else max(0.0, 1 - v / h) for v, h in zip(values, highs)]


def max_drawdown(points: list[tuple[str, float]]) -> dict | None:
    """The deepest peak-to-trough fall anywhere in the series."""
    if len(points) < 2:
        return None
    peak_v, peak_d = points[0][1], points[0][0]
    best = {"depth": 0.0, "peak": peak_d, "trough": peak_d}
    for d, v in points:
        if v > peak_v:
            peak_v, peak_d = v, d
        elif peak_v > 0:
            depth = 1 - v / peak_v
            if depth > best["depth"]:
                best = {"depth": depth, "peak": peak_d, "trough": d}
    return best


def value_on(points: list[tuple[str, float]], day: str) -> float | None:
    """The value on `day`, or the last one before it."""
    ds = [d for d, _ in points]
    i = bisect.bisect_right(ds, day) - 1
    return points[i][1] if i >= 0 else None


def change_over(points: list[tuple[str, float]], days: int) -> float | None:
    """Fractional change from `days` calendar days before the last point."""
    if len(points) < 2:
        return None
    last_d, last_v = points[-1]
    start = (dt.date.fromisoformat(last_d) - dt.timedelta(days=days)).isoformat()
    if points[0][0] > start:
        return None                     # not enough history: say so rather than guess
    base = value_on(points, start)
    return None if not base else last_v / base - 1


def points_change(points: list[tuple[str, float]], days: int) -> float | None:
    """Change in the value's own units — for a rate or a spread, where "down 48%" would
    describe a move from 5.7% to 3.0% far more alarmingly than "down 2.7 points"."""
    if len(points) < 2:
        return None
    last_d, last_v = points[-1]
    start = (dt.date.fromisoformat(last_d) - dt.timedelta(days=days)).isoformat()
    if points[0][0] > start:
        return None
    base = value_on(points, start)
    return None if base is None else last_v - base


def ratio(a: list[tuple[str, float]], b: list[tuple[str, float]]) -> list[tuple[str, float]]:
    bd = dict(b)
    return [(d, v / bd[d]) for d, v in a if d in bd and bd[d]]


def rebase(points: list[tuple[str, float]], base: float = 100.0) -> list[tuple[str, float]]:
    if not points or not points[0][1]:
        return []
    first = points[0][1]
    return [(d, v / first * base) for d, v in points]


def since(points: list[tuple[str, float]], days: int) -> list[tuple[str, float]]:
    if not points:
        return []
    start = (dt.date.fromisoformat(points[-1][0]) - dt.timedelta(days=days)).isoformat()
    return [p for p in points if p[0] >= start]


def thin(points: list[tuple[str, float]], limit: int = 400) -> list[tuple[str, float]]:
    """Fewer points for drawing, always keeping the first and the last."""
    if len(points) <= limit:
        return points
    step = len(points) / (limit - 1)
    out = [points[int(i * step)] for i in range(limit - 1)]
    out.append(points[-1])
    return out
