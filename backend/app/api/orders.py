from fastapi import APIRouter, Depends, Query
from app.dependencies import runtime
router=APIRouter(tags=["orders"])

@router.get("/orders")
async def orders(rt=Depends(runtime), limit: int = Query(100, ge=1, le=1000)):
    return rt.paper.recent_orders(limit) if rt.config.execution_mode.value=="PAPER" else rt.testnet.recent_orders(limit)

@router.get("/fills")
async def fills(rt=Depends(runtime), limit: int = Query(100, ge=1, le=1000)):
    return rt.paper.fills.recent(limit) if rt.config.execution_mode.value=="PAPER" else []
