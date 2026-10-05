from fastapi import APIRouter, Depends
from app.dependencies import runtime
router=APIRouter(tags=["risk"])

@router.get("/risk")
async def risk(rt=Depends(runtime)):
    payload=rt.risk.model_dump(mode="json")
    payload["firewall"]=rt.risk_firewall_payload()
    return payload

@router.get("/references")
async def references(rt=Depends(runtime)):
    return await rt.references_summary()

@router.get("/risk/evidence")
async def evidence(rt=Depends(runtime)):
    return await rt.risk_evidence_summary()

@router.get("/risk/events")
async def events(rt=Depends(runtime)):
    return rt.risk_events_summary()

@router.get("/risk/authorization")
async def authorization(rt=Depends(runtime)):
    return rt.authorization_summary()

@router.post("/risk/kill")
async def kill(rt=Depends(runtime)):
    await rt.activate_kill()
    return rt.risk

@router.post("/risk/resume")
async def resume(rt=Depends(runtime)):
    return await rt.resume()
