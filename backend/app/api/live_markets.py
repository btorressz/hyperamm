"""GET-only native public observations, independent of the runtime dependency."""
from fastapi import APIRouter, Request, Response

from app.market_data.live_models import LiveMarketId, LiveMarketOverview, LiveMarketSnapshot

router = APIRouter(tags=["live-markets"])


def snapshot_http_status(snapshot):
    codes = {item.code for item in snapshot.errors}
    if "CAPACITY" in codes or "RATE_LIMITED" in codes:
        return 429
    if snapshot.observation_status in {"AVAILABLE", "PARTIAL", "DEGRADED"}:
        return 200
    if "TIMEOUT" in codes:
        return 504
    return 503


@router.get("/live-markets/overview", response_model=LiveMarketOverview,
            responses={503: {"model": LiveMarketOverview}, 429: {"model": LiveMarketOverview},
                       504: {"model": LiveMarketOverview}})
async def overview(request: Request, response: Response):
    result = await request.app.state.live_market_observer.overview()
    statuses = [snapshot_http_status(item) for item in result.markets]
    response.status_code = 200 if 200 in statuses else 429 if 429 in statuses else 504 if 504 in statuses else 503
    if response.status_code == 429:
        response.headers["Retry-After"] = "30" if any(
            item.code == "RATE_LIMITED" for market in result.markets for item in market.errors) else "1"
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/live-markets/{market}/snapshot", response_model=LiveMarketSnapshot,
            responses={503: {"model": LiveMarketSnapshot}, 429: {"model": LiveMarketSnapshot},
                       504: {"model": LiveMarketSnapshot}})
async def snapshot(market: LiveMarketId, request: Request, response: Response):
    result = await request.app.state.live_market_observer.snapshot(market)
    response.status_code = snapshot_http_status(result)
    if response.status_code == 429:
        response.headers["Retry-After"] = "30" if any(item.code == "RATE_LIMITED" for item in result.errors) else "1"
    response.headers["Cache-Control"] = "no-store"
    return result
