from fastapi import APIRouter
router=APIRouter(tags=["positions"])
@router.get("/positions")
async def positions(): return {"positions":[],"note":"Account positions are not required for Phase 1-4 paper mode."}
