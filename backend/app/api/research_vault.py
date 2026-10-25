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
    """64 KiB pre-parsing bound for API writes, including chunked bodies.

    Retain the original middleware name for existing imports. Coalesce chunks so
    one-byte fragments cannot create an unbounded list of ASGI message objects.
    """
    def __init__(self, app, max_bytes=65536):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await self.app(scope, receive, send)

        async def reject(status, detail):
            from starlette.responses import JSONResponse
            await JSONResponse({"detail": detail}, status_code=status,
                               headers={"Cache-Control": "no-store"})(scope, receive, send)

        lengths = [v for k, v in scope.get("headers", []) if k.lower() == b"content-length"]
        transfer = [v for k, v in scope.get("headers", []) if k.lower() == b"transfer-encoding"]
        if len(lengths) > 1 or lengths and transfer:
            return await reject(400, "Ambiguous request framing")
        expected = None
        if lengths:
            raw = lengths[0]
            if not raw or len(raw) > 20 or not raw.isdigit():
                return await reject(400, "Invalid content length")
            expected = int(raw)
            if expected > self.max_bytes:
                return await reject(413, f"Research payload exceeds {self.max_bytes} bytes")
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.max_bytes:
                return await reject(413, f"Research payload exceeds {self.max_bytes} bytes")
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        if expected is not None and expected != len(body):
            return await reject(400, "Content length does not match request body")
        pending = True
        async def replay():
            nonlocal pending
            if pending:
                pending = False
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)
