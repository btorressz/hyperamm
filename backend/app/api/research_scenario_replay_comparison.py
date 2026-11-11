"""Local computational PAPER comparison. No trading or operational mutation."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.historical_replay import execute, NO_STORE
from app.api.research_markets import selected_profile
from app.dependencies import runtime
from app.research_replay.transport import ScenarioHistoricalRequest, ScenarioHistoricalResponse

router = APIRouter(prefix="/research-comparison", tags=["research-comparison"])


@router.post("/scenario-historical", response_model=ScenarioHistoricalResponse)
async def compare(body: ScenarioHistoricalRequest, request: Request, response: Response, rt=Depends(runtime)):
    response.headers.update(NO_STORE)
    try:
        selected = await selected_profile(request, body.research_market)
        return await execute(request, "compare_scenario_historical", request=body,
            strategy=rt.config.model_copy(deep=True), agents=rt.agent_config.model_copy(deep=True),
            risk=rt.risk_config.model_copy(deep=True), market_profile=selected)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(422, "Research market profile unavailable", headers=NO_STORE) from None
    except Exception:
        raise HTTPException(500, "Comparison unavailable", headers=NO_STORE) from None
