"""Real lifespan/catalog/HTTP with explicit fault controls from the prior harness.

The official configured metadata loader is restored before lifespan startup.
Only delay/failure/WS transport controls are test instrumentation.
"""
from app.market_data.hyperliquid_metadata import HyperliquidMetadataCatalog
import phase175_browser_backend as harness

harness.main.HyperliquidMetadataCatalog = HyperliquidMetadataCatalog
app = harness.app
previous_status = harness.status


def status():
    result = previous_status()
    rt = app.state.runtime
    # Demo feeds continue marking a flat operational position independently of
    # research. Compare exact economics, canonicalizing Decimal zero spelling;
    # the current observed price itself is not trading authority.
    def number(value):
        return '0' if value == 0 else str(value) if value is not None else None
    position = rt.accounting_service.position
    result['authority'].update(
        fills=[f.model_dump(mode='json') for f in rt.paper.fills.all()],
        accounting_config=rt.accounting_config.model_dump(mode='json'),
        accounting_state=dict(position={key:number(value) for key,value in
            position.model_dump(exclude={'market','mark_price'}).items()},
            market=position.market, cash=number(rt.accounting_service._cash),
            reserved=number(rt.accounting_service._reserved), fees=number(rt.accounting_service._fees),
            funding=number(rt.accounting_service._funding)),
        testnet_settings=rt.settings.enable_hyperliquid_testnet_orders,
        signing_references=[id(rt.testnet), id(rt.testnet.authority), id(rt.execution)],
        market_listeners=[id(listener) for listener in rt.market._listeners],
    )
    return result

harness.status = status
