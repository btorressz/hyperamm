from fastapi import APIRouter, Depends
from app.dependencies import runtime
router=APIRouter(tags=["health"])

@router.get("/health")
async def health(rt=Depends(runtime)):
    snap=await rt.market.snapshot()
    return {"status":"ok","app":"HyperAMM","market_connection":snap.connection_state,"stale":snap.stale,"mode":snap.mode,"simulated":snap.simulated}
