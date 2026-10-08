from app.diagnostics import sanitize_public_payload
from fastapi import APIRouter, Depends
from app.dependencies import runtime

router = APIRouter(tags=["positions"])


@router.get("/positions")
async def positions(rt=Depends(runtime)):
    return sanitize_public_payload(await rt.inventory_summary())
