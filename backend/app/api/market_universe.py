"""GET-only public perpetual metadata evidence."""
from fastapi import APIRouter, Request, Response

from app.market_data.market_universe_discovery import MarketUniverseResponse, RATE_LIMIT_BACKOFF

router = APIRouter(tags=["market-universe"])


@router.get("/market-universe", response_model=MarketUniverseResponse,
            responses={code: {"model": MarketUniverseResponse} for code in (429, 503, 504)})
async def market_universe(request: Request, response: Response):
    result = await request.app.state.market_universe_discovery.catalog()
    response.headers["Cache-Control"] = "no-store"
    if result.availability in {"AVAILABLE", "PARTIAL", "STALE"}:
        return result
    codes = {
        result.error, result.inventory.error if result.inventory else None,
        *(item.error for item in result.namespaces),
    }
    if "RATE_LIMITED" in codes:
        response.status_code = 429
        response.headers["Retry-After"] = str(RATE_LIMIT_BACKOFF)
    elif "TIMEOUT" in codes:
        response.status_code = 504
    else:
        response.status_code = 503
    return result
