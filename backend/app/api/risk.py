from app.diagnostics import sanitize_public_payload
from fastapi import APIRouter, Depends
from app.dependencies import runtime
router=APIRouter(tags=["risk"])

@router.get("/risk")
async def risk(rt=Depends(runtime)):
    payload=rt.risk.model_dump(mode="json")
    payload["firewall"]=rt.risk_firewall_payload()
    return sanitize_public_payload(payload)

@router.get("/references")
async def references(rt=Depends(runtime)):
    return sanitize_public_payload(await rt.references_summary())

@router.get("/references/observations")
async def references_observations(rt=Depends(runtime)):
    return sanitize_public_payload(await rt.references_observations_summary())

@router.get("/risk/evidence")
async def evidence(rt=Depends(runtime)):
    return sanitize_public_payload(await rt.risk_evidence_summary())

@router.get("/risk/events")
async def events(rt=Depends(runtime)):
    return sanitize_public_payload(rt.risk_events_summary())

@router.get("/risk/authorization")
async def authorization(rt=Depends(runtime)):
    return sanitize_public_payload(rt.authorization_summary())

@router.post("/risk/kill")
async def kill(rt=Depends(runtime)):
    await rt.activate_kill()
    return sanitize_public_payload(rt.risk.model_dump(mode="json"))

@router.post("/risk/resume")
async def resume(rt=Depends(runtime)):
    return sanitize_public_payload((await rt.resume()).model_dump(mode="json"))
