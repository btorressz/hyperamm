from fastapi import APIRouter, Depends
from app.dependencies import runtime

router = APIRouter(tags=["positions"])


@router.get("/positions")
async def positions(rt=Depends(runtime)):
    return await rt.inventory_summary(refresh=rt.config.execution_mode.value == "TESTNET")
