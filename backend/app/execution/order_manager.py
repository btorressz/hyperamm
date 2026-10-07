from __future__ import annotations

import asyncio
import hashlib
import inspect
from app.amm.models import QuoteLevel
from .models import OrderRequest
from .quote_reconciler import reconcile_quotes, ReconcileActionType


class OrderManager:
    def __init__(self, execution, lock=None, authority=None):
        self.execution = execution
        self.lock = lock if lock is not None else asyncio.Lock()
        self.authority = authority or (lambda: None)
        self._nonce = 0

    def request_for(self, market: str, quote: QuoteLevel) -> OrderRequest:
        self._nonce += 1
        key = f"{market}:{quote.side}:{quote.level_index}:{quote.price}:{quote.size}:{self._nonce}"
        cid = "hamm-" + hashlib.sha256(key.encode()).hexdigest()[:20]
        return OrderRequest(client_order_id=cid, market=market, side=quote.side, price=quote.price, size=quote.size, level_index=quote.level_index)

    async def reconcile(self, market: str, desired, price_tolerance_bps, size_tolerance):
        async with self.lock:
            return await self.reconcile_locked(market, desired, price_tolerance_bps, size_tolerance)

    async def reconcile_locked(self, market, desired, price_tolerance_bps, size_tolerance, *, venue_reconciled=False):
        """Runtime may hold the shared execution lock across generation and reconciliation."""
        if hasattr(self.execution, "reconcile_venue") and not venue_reconciled:
            await self.execution.reconcile_venue()
        existing = await self.execution.get_open_orders()
        actions = reconcile_quotes(desired, existing, price_tolerance_bps, size_tolerance)
        uncertain = any(o.status == "UNKNOWN" for o in existing)
        cancelled_ids = set()
        for action in actions:
            if action.action in {ReconcileActionType.CANCEL, ReconcileActionType.REPLACE}:
                await self.execution.cancel_orders([action.existing.client_order_id])
                cancelled_ids.add(action.existing.client_order_id)
            if action.action in {ReconcileActionType.CREATE, ReconcileActionType.REPLACE}:
                if getattr(self.execution, "_needs_verification", set()):
                    await self.execution.reconcile_venue()
                remaining = await self.execution.get_open_orders()
                if uncertain or any(o.status == "UNKNOWN" for o in remaining) or getattr(self.execution, "_needs_verification", set()):
                    raise RuntimeError("unresolved execution exposure prevents CREATE/REPLACE")
                if any(o.client_order_id in cancelled_ids for o in remaining):
                    raise RuntimeError("replacement cancellation unconfirmed")
                request = self.request_for(market, action.desired)
                # Preserve legacy zero-argument PAPER/research callbacks.
                try:
                    inspect.signature(self.authority).bind(request)
                except TypeError:
                    check = self.authority()
                else:
                    check = self.authority(request.model_copy(deep=True))
                if inspect.isawaitable(check):
                    await check
                await self.execution.submit_orders([request])
        return actions

    async def cancel_all(self):
        async with self.lock:
            return await self.execution.cancel_all()
