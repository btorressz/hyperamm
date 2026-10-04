from fastapi import APIRouter, Depends
from app.dependencies import runtime
router=APIRouter(tags=["orders"])

@router.get("/orders")
async def orders(rt=Depends(runtime)):
    return rt.paper.all_orders() if rt.config.execution_mode.value=="PAPER" else await rt.execution.get_open_orders()

@router.get("/fills")
async def fills(rt=Depends(runtime)):
    return rt.paper.fills.all() if rt.config.execution_mode.value=="PAPER" else []
