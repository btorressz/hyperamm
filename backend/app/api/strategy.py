from app.diagnostics import sanitize_public_payload, sanitize_public_text
from fastapi import APIRouter,Depends,HTTPException
from fastapi.encoders import jsonable_encoder
from decimal import Decimal
from app.dependencies import runtime
from app.strategy.models import StrategyConfig
from app.amm.diagnostics import effective_liquidity
from app.strategy.quote_engine import StrategyFeasibilityError
router=APIRouter(tags=['strategy'])
@router.get('/strategy')
async def get_strategy(rt=Depends(runtime)):return sanitize_public_payload(rt.strategy.model_dump(mode="json"))
@router.put('/strategy')
async def put_strategy(config:StrategyConfig,rt=Depends(runtime)):
    try:return sanitize_public_payload((await rt.update_config(config)).model_dump(mode="json"))
    except StrategyFeasibilityError as exc:raise HTTPException(status_code=422,detail=sanitize_public_text(exc)) from exc
@router.post('/strategy/start')
async def start(rt=Depends(runtime)):
    try:return sanitize_public_payload((await rt.start_strategy()).model_dump(mode="json"))
    except PermissionError as exc:raise HTTPException(status_code=403,detail=sanitize_public_text(exc)) from exc
@router.post('/strategy/stop')
async def stop(rt=Depends(runtime)):return sanitize_public_payload((await rt.stop_strategy()).model_dump(mode="json"))
@router.get('/amm/state')
async def amm_state(rt=Depends(runtime)):return {'fair_value':rt.fair_value,'pool':rt.pool.model_copy(deep=True) if rt.pool else None,'model':rt.config.amm_model,'inventory':sanitize_public_payload(rt._inventory_payload(rt.inventory,rt.inventory_decision)) if rt.inventory else None}
@router.get('/amm/curve')
async def curve(rt=Depends(runtime)):
    async with rt.execution_lock:
        return {'fair_value':rt.fair_value,'quotes':[q.model_copy(deep=True) for q in rt.quotes],
            'inventory':sanitize_public_payload(rt._inventory_payload(rt.inventory,rt.inventory_decision)) if rt.inventory else None,
            'effective_liquidity': jsonable_encoder({
                'strategy': effective_liquidity(rt.strategy_quotes),
                'agent': effective_liquidity(rt.agent_quotes),
                'authorized': effective_liquidity(rt.quotes),
            }, custom_encoder={Decimal: str})}
@router.get('/amm/quotes')
async def quotes(rt=Depends(runtime)):return [q.model_copy(deep=True) for q in rt.quotes]

@router.get('/market-adaptation')
async def market_adaptation(rt=Depends(runtime)):
    return await rt.market_adaptation_summary()

@router.get('/perp-context')
async def perp_context(rt=Depends(runtime)):
    return await rt.perp_context_summary()
