"""Read-only research catalog; independent of operational /markets."""
from fastapi import APIRouter, Request

router = APIRouter(tags=["research-markets"])


@router.get("/research-markets")
async def research_markets(request: Request):
    return (await request.app.state.research_market_catalog.catalog()).model_dump(mode="json")


async def selected_profile(request: Request, market):
    return await request.app.state.research_market_catalog.resolve(market) if market is not None else None
