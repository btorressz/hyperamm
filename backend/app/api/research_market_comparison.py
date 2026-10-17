"""Computational read-only POST: snapshot only, never REST refresh or research execution."""
import logging
from fastapi import APIRouter, HTTPException, Request, Response
from app.research_comparison.models import ResearchMarketComparisonRequest, MarketResearchComparisonResult
from app.research_comparison.comparison import compare

router = APIRouter(prefix='/research-market-comparison', tags=['research-market-comparison'])
logger = logging.getLogger(__name__)


@router.post('/compare', response_model=MarketResearchComparisonResult)
async def compare_market(body: ResearchMarketComparisonRequest, request: Request, response: Response):
    response.headers['Cache-Control'] = 'no-store'
    try:
        snapshot = request.app.state.live_market_streams.snapshot(body.market)
        return compare(body, snapshot)
    except Exception as exc:
        # Do not emit exception text/tracebacks that can contain provider secrets.
        logger.error('Market research comparison failed (%s)', type(exc).__name__)
        raise HTTPException(status_code=500, detail='Market research comparison unavailable',
                            headers={'Cache-Control': 'no-store'}) from exc
