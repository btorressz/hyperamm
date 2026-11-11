"""Compare the measured pruning fast path against the original algorithm.

Actual execution rows exercise transitions, retained pins and eviction order.
"""
from copy import deepcopy
from datetime import datetime, timezone
from random import Random

import pytest

from app.execution.fills import ACTIVE_STATUSES, OrderHistory
from app.execution.models import StrategyOrder


class OriginalOrderHistory(OrderHistory):
    def prune(self):
        eligible = [cid for cid, order in self._closed.items()
                    if order.status not in ACTIVE_STATUSES and not self.pinned(cid)]
        for cid in eligible[:-self.limit]:
            self._closed.pop(cid, None)
            dict.pop(self, cid, None)


@pytest.mark.parametrize('limit', [1, 3, 1000])
def test_closed_retention_matches_original_for_every_transition(limit):
    pins = set()
    observed = [[], []]
    current = OrderHistory(limit=limit, pinned=pins.__contains__, observer=lambda rows: observed[0].extend(deepcopy(rows)))
    original = OriginalOrderHistory(limit=limit, pinned=pins.__contains__, observer=lambda rows: observed[1].extend(deepcopy(rows)))
    clock = datetime(2026, 11, 11, tzinfo=timezone.utc)
    def check():
        assert list(current.items()) == list(original.items())
        assert list(current._closed.items()) == list(original._closed.items())
        assert current.active() == original.active()
        assert current.recent() == original.recent()
        assert observed[0] == observed[1]
    def record(index, status):
        cid = f'order-{index}'
        row = StrategyOrder(client_order_id=cid, market='BTC', side='BID', price='60000', size='1',
            status=status, created_at=clock, updated_at=clock)
        current[cid] = row.model_copy(deep=True)
        original[cid] = row.model_copy(deep=True)
        check()
    for index in range(limit + 5):
        if index % 3 == 0:
            pins.add(f'order-{index}')
        record(index, 'OPEN')
        record(index, 'PARTIALLY_FILLED' if index % 2 else 'UNKNOWN')
        record(index, 'FILLED' if index % 2 else 'CANCELLED')
    rng = Random(166)
    for _ in range(80):
        index = rng.randrange(limit + 5)
        if rng.randrange(2):
            pins.add(f'order-{index}')
        else:
            pins.discard(f'order-{index}')
        record(index, rng.choice(['OPEN', 'UNKNOWN', 'PARTIALLY_FILLED', 'FILLED', 'REPLACED', 'REJECTED']))
        current.prune();original.prune();check()
    pins.clear()
    current.prune();original.prune();check()
    assert len(current._closed) <= limit
