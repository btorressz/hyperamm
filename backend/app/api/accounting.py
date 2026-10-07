from fastapi import APIRouter, Depends, Query

from app.dependencies import runtime


router = APIRouter(tags=["accounting"])


@router.get("/vault")
async def vault(rt=Depends(runtime)):
    return await rt.vault_summary()


@router.get("/accounting/pnl")
async def pnl(rt=Depends(runtime)):
    await rt.vault_summary()
    return rt.accounting_service.pnl().model_dump(mode="json")


@router.get("/accounting/position")
async def position(rt=Depends(runtime)):
    await rt.vault_summary()
    if rt.config.execution_mode.value == "TESTNET":
        return rt.perp_position.model_dump(mode="json") if rt.perp_position is not None else None
    return rt.accounting_service.position.model_dump(mode="json")


@router.get("/accounting/ledger")
async def ledger(limit: int = Query(default=100, ge=1, le=500), rt=Depends(runtime)):
    return {"mode": rt.config.execution_mode.value, "market": rt.config.market,
            "retention_policy": rt.accounting_service.ledger.retention_policy,
            "ledger_version": rt.accounting_service.ledger.version,
            "ledger_fingerprint": rt.accounting_service.ledger.fingerprint,
            "order": "newest-first",
            "entries": [entry.model_dump(mode="json") for entry in rt.accounting_service.ledger.entries(limit)]}


@router.get("/accounting/events")
async def events(limit: int = Query(default=100, ge=1, le=500), rt=Depends(runtime)):
    return [event.model_dump(mode="json") for event in rt.accounting_service.events(limit)]
