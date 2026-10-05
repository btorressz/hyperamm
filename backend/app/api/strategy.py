from fastapi import APIRouter,Depends,HTTPException
from app.dependencies import runtime
from app.strategy.models import StrategyConfig
router=APIRouter(tags=['strategy'])
@router.get('/strategy')
async def get_strategy(rt=Depends(runtime)):return rt.strategy
@router.put('/strategy')
async def put_strategy(config:StrategyConfig,rt=Depends(runtime)):return await rt.update_config(config)
@router.post('/strategy/start')
async def start(rt=Depends(runtime)):
    try:return await rt.start_strategy()
    except PermissionError as exc:raise HTTPException(status_code=403,detail=str(exc)) from exc
@router.post('/strategy/stop')
async def stop(rt=Depends(runtime)):return await rt.stop_strategy()
@router.get('/amm/state')
async def amm_state(rt=Depends(runtime)):return {'fair_value':rt.fair_value,'pool':rt.pool,'model':rt.config.amm_model,'inventory':rt._inventory_payload(rt.inventory,rt.inventory_decision) if rt.inventory else None}
@router.get('/amm/curve')
async def curve(rt=Depends(runtime)):
    if rt.fair_value is None:await rt.refresh_once()
    return {'fair_value':rt.fair_value,'quotes':rt.quotes,'inventory':rt._inventory_payload(rt.inventory,rt.inventory_decision) if rt.inventory else None}
@router.get('/amm/quotes')
async def quotes(rt=Depends(runtime)):return rt.quotes
