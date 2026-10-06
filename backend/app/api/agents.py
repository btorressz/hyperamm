from fastapi import APIRouter,Depends

from app.dependencies import runtime

router=APIRouter(tags=["agents"])


@router.get("/agents")
async def agents(rt=Depends(runtime)):
    return await rt.agents_summary()


@router.get("/agents/events")
async def agent_events(rt=Depends(runtime)):
    return rt.agent_events_summary()
