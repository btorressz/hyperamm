"""Read-only proposals and isolated worker comparisons. No configuration writes."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies import runtime
from app.infrastructure.research import ResearchUnavailableError
from app.simulation.config import SimulationConfig
from app.simulation.executor import ResearchBusyError
from app.simulation.presets import PRESETS
from app.simulation.research_vault import RESEARCH_CONFIG_VERSION, ResearchProposal, preview
from app.simulation.scenarios import ScenarioName
from app.simulation.market_profiles import ResearchPerpMarketId
from app.api.research_markets import selected_profile

router = APIRouter(prefix="/research-vault", tags=["research-vault"])
logger = logging.getLogger(__name__)


class ResearchComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline: ResearchProposal
    custom: ResearchProposal
    scenario: ScenarioName = ScenarioName.QUIET
    frames: int = Field(default=120, ge=2, le=1000)
    record_trace: bool = True
    trace_max_points: int = Field(default=250, ge=0, le=500)
    research_market: ResearchPerpMarketId | None = None


@router.get("/presets")
async def presets():
    return {"research_config_version": RESEARCH_CONFIG_VERSION, "simulated": True,
            "presets": [preset.response() for preset in PRESETS]}


@router.post("/preview")
async def preview_config(proposal: ResearchProposal):
    return preview(proposal)


@router.post("/compare")
async def compare_configs(proposal: ResearchComparisonRequest, request: Request, rt=Depends(runtime)):
    try:
        market_profile = await selected_profile(request, proposal.research_market)
        result = await request.app.state.simulation_executor.execute("compare_research_configs",
            scenario=proposal.scenario.value, frames=proposal.frames,
            strategy=rt.config.model_copy(deep=True), agents=rt.agent_config.model_copy(deep=True),
            risk=rt.risk_config.model_copy(deep=True), baseline=proposal.baseline.model_copy(deep=True),
            custom=proposal.custom.model_copy(deep=True), simulation=SimulationConfig(max_frames=proposal.frames,
                record_trace=proposal.record_trace, trace_max_points=proposal.trace_max_points),
            **({"market_profile": market_profile} if market_profile is not None else {}))
        return result.model_dump(mode="json")
    except (ResearchBusyError, ResearchUnavailableError) as exc:
        raise HTTPException(status_code=429 if isinstance(exc, ResearchBusyError) else 503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Research configuration comparison failed")
        raise HTTPException(status_code=500, detail="Research configuration comparison failed") from exc


class ResearchBodyLimit:
    """Bound proposal parsing before Pydantic, including chunked requests."""
    def __init__(self, app, max_bytes=65536):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        if scope["type"] != "http" or scope.get("method") != "POST" or not any(
                segment in path for segment in ("/research-vault/", "/simulation/")):
            return await self.app(scope, receive, send)
        messages, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                await send({"type": "http.response.start", "status": 413,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": b'{"detail":"Research payload exceeds 65536 bytes"}'})
                return
            messages.append(message)
            if not message.get("more_body", False):
                break
        async def replay():
            return messages.pop(0) if messages else await receive()
        await self.app(scope, replay, send)
