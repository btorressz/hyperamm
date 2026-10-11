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


# Additive stream contracts do not replace the REST snapshot or its cache.
from fastapi import Query
from app.market_data.live_stream_models import LiveMarketStreamStatus, LiveMarketHistory, LiveStreamSnapshot
from app.references.live_provider_integrity import LiveProviderHealth, provider_health


@router.get('/live-markets/{market}/stream-status', response_model=LiveMarketStreamStatus)
async def stream_status(market: LiveMarketId, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.live_market_streams.snapshot(market).status


@router.get('/live-markets/{market}/stream-snapshot', response_model=LiveStreamSnapshot)
async def stream_snapshot(market: LiveMarketId, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.live_market_streams.snapshot(market)


@router.get('/live-markets/{market}/history', response_model=LiveMarketHistory)
async def live_history(market: LiveMarketId, request: Request, response: Response,
                       limit: int = Query(default=100, ge=1, le=1000)):
    response.headers['Cache-Control'] = 'no-store'
    return request.app.state.live_market_streams.history.query(market, limit)


@router.get('/live-markets/{market}/references', response_model=LiveProviderHealth)
async def live_references(market: LiveMarketId, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    return provider_health(request.app.state.live_market_streams.snapshot(market))
