from app.diagnostics import sanitize_public_payload
from typing import Literal

from fastapi import APIRouter,Depends,Query

from app.dependencies import runtime

router=APIRouter(tags=["agents"])


@router.get("/agents")
async def agents(rt=Depends(runtime)):
    return sanitize_public_payload(await rt.agents_summary())


@router.get("/agents/events")
async def agent_events(rt=Depends(runtime), limit:int=Query(default=250,ge=1,le=250),
    agent:Literal["REGIME","TOXIC_FLOW","EXECUTION_QUALITY","LIQUIDITY_QUALITY","PERP_CROWDING","PREDICTIVE_ADVERSE_SELECTION","SUPERVISOR"]|None=None):
    return sanitize_public_payload(rt.agent_events_summary(limit=limit,agent=agent))


@router.get("/agents/evidence")
async def agent_evidence(rt=Depends(runtime)):
    return sanitize_public_payload(rt.agents_payload()["evidence"])


@router.get("/agents/models")
async def agent_models(rt=Depends(runtime)):
    payload=rt.agents_payload()
    output=payload["predictive_adverse_selection"]
    config=payload["config"]
    mode=config["predictive_agent_mode"] if config["agents_enabled"] and config["predictive_agent_enabled"] else "DISABLED"
    return sanitize_public_payload({"mode":output["mode"] if output else mode,
        "affects_quotes":False,"model_provenance":output["model_provenance"] if output else None})
