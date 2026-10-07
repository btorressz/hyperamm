"""Bounded, current-session chart observations; never trading evidence."""

import builtins
from collections import deque
from datetime import timedelta
from .models import TerminalHistoryPoint

HISTORY_MAX_POINTS = 3600
HISTORY_QUERY_MAX = 1000
RANGES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "session": None}


class TerminalHistory:
    def __init__(self, max_points=HISTORY_MAX_POINTS):
        if not 1 <= max_points <= HISTORY_MAX_POINTS:
            raise ValueError("max_points must be 1..3600")
        self.max_points = max_points
        self._points = deque(maxlen=max_points)

    def clear(self):
        self._points.clear()

    def append(self, point: TerminalHistoryPoint):
        if self._points:
            previous = self._points[-1]
            if (
                point.sequence <= previous.sequence
                or point.timestamp < previous.timestamp
            ):
                raise ValueError("history observations must be ordered")
        self._points.append(point)

    def query(self, limit=HISTORY_QUERY_MAX, range="session"):
        if not 1 <= limit <= HISTORY_QUERY_MAX or range not in RANGES:
            raise ValueError("invalid bounded history query")
        points = list(self._points)
        seconds = RANGES[range]
        if seconds is not None and points:
            cutoff = points[-1].timestamp - timedelta(seconds=seconds)
            points = [p for p in points if p.timestamp >= cutoff]
        # Preserve the retained time span via deterministic sampling when bounded.
        if len(points) > limit:
            points = (
                [points[-1]]
                if limit == 1
                else [
                    points[i * (len(points) - 1) // (limit - 1)]
                    for i in builtins.range(limit)
                ]
            )
        return points

    def metadata(self):
        points = self._points
        span = (
            (points[-1].timestamp - points[0].timestamp).total_seconds()
            if len(points) > 1
            else 0
        )
        return {
            "max_points": self.max_points,
            "query_max": HISTORY_QUERY_MAX,
            "retained_points": len(points),
            "retained_seconds": span,
            "available_ranges": [
                name
                for name, seconds in RANGES.items()
                if seconds is None or span >= seconds - 1
            ],
            "oldest_at": points[0].timestamp.isoformat() if points else None,
            "latest_at": points[-1].timestamp.isoformat() if points else None,
        }
