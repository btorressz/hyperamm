from __future__ import annotations

import hashlib
from app.amm.models import QuoteLevel
from .models import OrderRequest
from .quote_reconciler import reconcile_quotes, ReconcileActionType


class OrderManager:
    def __init__(self, execution):
        self.execution=execution
        self._nonce=0

    def request_for(self, market: str, quote: QuoteLevel) -> OrderRequest:
        self._nonce += 1
        key=f"{market}:{quote.side}:{quote.level_index}:{quote.price}:{quote.size}:{self._nonce}"
        cid="hamm-"+hashlib.sha256(key.encode()).hexdigest()[:20]
        return OrderRequest(client_order_id=cid,market=market,side=quote.side,price=quote.price,size=quote.size,level_index=quote.level_index)

    async def reconcile(self, market: str, desired, price_tolerance_bps, size_tolerance):
        existing=await self.execution.get_open_orders()
        actions=reconcile_quotes(desired,existing,price_tolerance_bps,size_tolerance)
        creates=[]; replacements=[]; cancels=[]
        for a in actions:
            if a.action==ReconcileActionType.CREATE: creates.append(self.request_for(market,a.desired))
            elif a.action==ReconcileActionType.REPLACE: replacements.append((a.existing.client_order_id,self.request_for(market,a.desired)))
            elif a.action==ReconcileActionType.CANCEL: cancels.append(a.existing.client_order_id)
        if cancels: await self.execution.cancel_orders(cancels)
        if replacements: await self.execution.replace_orders(replacements)
        if creates: await self.execution.submit_orders(creates)
        return actions
