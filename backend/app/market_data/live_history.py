"""Bounded per-market component observations, separate from operational history."""
from collections import deque
from app.market_data.live_stream_models import LiveHistoryPoint, LiveMarketHistory
from app.simulation.market_profiles import MARKETS


class LiveObservationHistory:
    def __init__(self, instance_id, max_points=1000):
        if type(max_points) is not int or not 1 <= max_points <= 3600:
            raise ValueError('invalid history capacity')
        self.instance_id, self.max_points = instance_id, max_points
        self._points = {m: deque(maxlen=max_points) for m in MARKETS}
        self._evicted = dict.fromkeys(MARKETS, 0)
        self._gaps = dict.fromkeys(MARKETS, 0)
        self._last_l2 = dict.fromkeys(MARKETS, None)
        self._last_context = dict.fromkeys(MARKETS, None)
        self._generation = dict.fromkeys(MARKETS, 0)

    def gap(self, market):
        self._gaps[market] += 1

    def append(self, point: LiveHistoryPoint):
        if point.observer_instance_id != self.instance_id:
            raise ValueError('history process mismatch')
        market = point.market
        if point.connection_generation < self._generation[market]:
            return False
        self._generation[market] = point.connection_generation
        values = self._points[market]
        if point.kind == 'L2':
            previous = self._last_l2[market]
            if point.source_timestamp is None or (previous and point.source_timestamp <= previous):
                return False
            self._last_l2[market] = point.source_timestamp
        else:
            identity = (point.mark, point.oracle,
                        point.funding, point.open_interest)
            if identity == self._last_context[market]:
                return False
            self._last_context[market] = identity
        if len(values) == self.max_points:
            self._evicted[market] += 1
        values.append(point)
        return True

    def query(self, market, limit=100):
        if market not in MARKETS or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('invalid bounded history query')
        values = self._points[market]
        return LiveMarketHistory(market=market, observer_instance_id=self.instance_id,
            points=tuple(values)[-limit:], coverage_start=min(p.observed_at for p in values) if values else None,
            coverage_end=max(p.observed_at for p in values) if values else None,
            retained_point_count=len(values), evicted_point_count=self._evicted[market],
            gap_count=self._gaps[market], max_points=self.max_points)
