"""Local read-only PAPER computation; configuration is the only client input."""
from fastapi import APIRouter, HTTPException, Request
from starlette.responses import Response

from app.api.historical_replay import NO_STORE
from app.infrastructure.research import ResearchUnavailableError
from app.portfolio_research.aggregation import bounded_json
from app.portfolio_research.config import PortfolioResponseTooLarge
from app.portfolio_research.models import (PortfolioResearchRunRequest, PortfolioExecutedResult,
    PortfolioAnalysisRequest, PortfolioAnalysisResult)
from app.simulation.executor import ResearchBusyError

router = APIRouter(prefix="/portfolio-research", tags=["portfolio-research"])


@router.post("/run", response_model=PortfolioExecutedResult)
async def run(body: PortfolioResearchRunRequest, request: Request):
    return await _compute(body, request, "run_portfolio_research", PortfolioExecutedResult)


@router.post("/analyze", response_model=PortfolioAnalysisResult)
async def analyze(body: PortfolioAnalysisRequest, request: Request):
    return await _compute(body, request, "analyze_portfolio_research", PortfolioAnalysisResult)


async def _compute(body, request, operation, result_type):
    try:
        result = await request.app.state.simulation_executor.execute(operation, request=body)
        result = result_type.model_validate(result)
        # Returning these exact bounded bytes avoids a second unguarded FastAPI
        # serialization. The OpenAPI response contract remains the typed model.
        return Response(bounded_json(result), media_type="application/json", headers=NO_STORE)
    except PortfolioResponseTooLarge:
        raise HTTPException(413, "Portfolio response exceeds transport budget", headers=NO_STORE) from None
    except ResearchBusyError:
        raise HTTPException(429, "Research worker is already running or shutting down", headers=NO_STORE) from None
    except ResearchUnavailableError:
        raise HTTPException(503, "Research admission unavailable", headers=NO_STORE) from None
    except ValueError:
        raise HTTPException(422, "Portfolio configuration or evidence rejected", headers=NO_STORE) from None
    except Exception:
        raise HTTPException(500, "Portfolio research unavailable", headers=NO_STORE) from None
