from fastapi import APIRouter, Depends, HTTPException
from app.dependencies import runtime
router=APIRouter(tags=["markets"])

@router.get("/markets/{market}")
async def market(market:str, rt=Depends(runtime)):
    if market != rt.config.market: raise HTTPException(404,"market not configured")
    return await rt.market.snapshot()

@router.get("/markets/{market}/book")
async def book(market:str, rt=Depends(runtime)):
    snap=await market_snapshot(market,rt)
    return snap.book

async def market_snapshot(market,rt):
    if market != rt.config.market: raise HTTPException(404,"market not configured")
    return await rt.market.snapshot()
