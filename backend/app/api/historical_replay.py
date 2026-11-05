"""Limited computational read-only APIs: no import, save, orders or deployment."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.dependencies import runtime
from app.infrastructure.research import ResearchUnavailableError
from app.research_replay.contracts import HistoricalReplayRequest, HistoricalReplayResult, ReplayRejected
from app.research_replay.models import Identifier
from app.research_replay.provenance import HistoricalDatasetProvenance
from app.simulation.executor import ResearchBusyError

router = APIRouter(prefix="/historical-replay", tags=["historical-replay"])
NO_STORE = {"Cache-Control": "no-store"}


async def execute(http_request, operation, **inputs):
    root = getattr(http_request.app.state, "historical_replay_root", None)
    if root is None:
        raise HTTPException(503, "Historical replay storage is not configured", headers=NO_STORE)
    try:
        return await http_request.app.state.simulation_executor.execute(operation, storage_root=root, **inputs)
    except ReplayRejected as exc:
        raise HTTPException(422, exc.rejection.model_dump(mode="json"), headers=NO_STORE) from exc
    except ResearchBusyError as exc:
        raise HTTPException(429, str(exc), headers=NO_STORE) from exc
    except ResearchUnavailableError:
        raise HTTPException(503, "Research admission unavailable", headers=NO_STORE) from None
    except ValueError:
        # Never return private filesystem paths, provider wire data or secrets.
        raise HTTPException(422, "Historical evidence or research configuration unavailable", headers=NO_STORE) from None
    except Exception:
        raise HTTPException(500, "Historical replay unavailable", headers=NO_STORE) from None


@router.get("/datasets", response_model=tuple[str, ...])
async def datasets(request: Request, response: Response):
    response.headers.update(NO_STORE)
    return await execute(request, "historical_catalog")


@router.get("/provenance", response_model=HistoricalDatasetProvenance)
async def provenance(request: Request, response: Response, dataset_id: Identifier = Query()):
    response.headers.update(NO_STORE)
    return await execute(request, "historical_provenance", dataset_id=dataset_id)


@router.post("/run", response_model=HistoricalReplayResult)
async def run(body: HistoricalReplayRequest, request: Request, response: Response, rt=Depends(runtime)):
    response.headers.update(NO_STORE)
    # Capture only existing immutable/copyable configuration before admission.
    return await execute(request, "replay_history", request=body,
        strategy=rt.config.model_copy(deep=True), agents=rt.agent_config.model_copy(deep=True),
        risk=rt.risk_config.model_copy(deep=True))
