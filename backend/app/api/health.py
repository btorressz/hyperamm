from fastapi import APIRouter, Depends, Request
from app.dependencies import runtime
router=APIRouter(tags=["health"])

@router.get("/health")
async def health(request: Request, rt=Depends(runtime)):
    snap=await rt.market.snapshot()
    infrastructure = getattr(request.app.state, "redis_infrastructure", None)
    redis = infrastructure.health() if infrastructure is not None else {
        "enabled": rt.settings.redis_enabled,
        "required": rt.settings.redis_required,
        "status": "DEGRADED" if rt.settings.redis_enabled else "DISABLED",
        "research_enabled": rt.settings.redis_research_enabled,
        "last_error": None,
        "last_success_at": None,
    }
    return {"status":"ok","app":"HyperAMM","market_connection":snap.connection_state,"stale":snap.stale,"mode":snap.mode,"simulated":snap.simulated,"redis":redis}
