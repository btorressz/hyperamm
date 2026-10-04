from fastapi import APIRouter, Depends
from app.dependencies import runtime
router=APIRouter(tags=["risk"])

@router.get("/risk")
async def risk(rt=Depends(runtime)): return rt.risk

@router.post("/risk/kill")
async def kill(rt=Depends(runtime)):
    rt.strategy.running=False
    await rt.kill.activate(rt.execution)
    return rt.risk

@router.post("/risk/resume")
async def resume(rt=Depends(runtime)):
    rt.kill.resume(); return rt.risk
