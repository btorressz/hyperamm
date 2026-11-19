"""Public perpetual metadata evidence and local PAPER research admission."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.infrastructure.research import ResearchUnavailableError
from app.market_data.market_universe_contracts import CONTRACT_VERSION, MarketInstrumentIdentity
from app.simulation.executor import ResearchBusyError
from app.simulation.generalized_market_profiles import (
    GeneralizedPaperResult, MAX_RESPONSE_BYTES, PROFILE_VERSION, PaperAdmission, PaperProposal,
    PaperRejected, PaperRunRequest, assess, decision,
)
from app.market_data.market_universe_discovery import MarketUniverseResponse, RATE_LIMIT_BACKOFF, RESPONSE_VERSION

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


# PAPER routes share discovery's server-owned catalog and the application's
# local research worker. No operational runtime dependency is needed.
def _paper_response(evidence, *, status=200):
    return Response(content=evidence.model_dump_json(), status_code=status,
                    media_type="application/json", headers={"Cache-Control": "no-store"})


def _decision_response(admission):
    status = 200
    if admission.status == "UNAVAILABLE":
        status = 503
    elif admission.reason.endswith("_FINGERPRINT_MISMATCH"):
        status = 409
    elif admission.status == "REJECTED":
        status = 422
    return _paper_response(admission, status=status)


class PaperAdmissionRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                body = exc.body if isinstance(exc.body, dict) else {}
                try:
                    identity = MarketInstrumentIdentity.model_validate(body.get("identity"))
                except ValueError:
                    identity = None
                version = body.get("profile_version")
                reason = "PROFILE_UNSUPPORTED" if identity is not None and version != PROFILE_VERSION else "CONFIGURATION_INVALID"
                return _decision_response(decision(identity, datetime.now(timezone.utc), reason))

        return handle


paper_router = APIRouter(prefix="/generalized-paper", tags=["generalized-paper"], route_class=PaperAdmissionRoute)
PAPER_DECISIONS = {status: {"model": PaperAdmission} for status in (409, 422, 503)}


async def _admit(request: Request, proposal: PaperProposal, expected=None):
    source = request.app.state.market_universe_discovery
    catalog = await source.catalog()
    if (catalog.schema_version != RESPONSE_VERSION or catalog.contract_version != CONTRACT_VERSION
            or (catalog.catalog is not None and catalog.catalog.contract_version != CONTRACT_VERSION)):
        return decision(proposal.identity, datetime.now(timezone.utc), "METADATA_UNAVAILABLE"), {}
    generation = (source.paper_generation(catalog.catalog_fingerprint)
                  if catalog.availability == "AVAILABLE" and catalog.catalog_fingerprint is not None else None)
    worker_inputs = (dict(catalog_valid_until=generation[0], catalog_guard=generation[1]) if generation else {})
    metadata = next((record for record in catalog.catalog.records
                     if record.identity == proposal.identity), None) if catalog.catalog is not None else None
    admission, _ = assess(proposal, metadata, network=catalog.network, evaluated_at=catalog.evaluated_at,
                          max_age_seconds=catalog.max_age_seconds,
                          metadata_current=generation is not None, expected=expected,
                          catalog_fingerprint=catalog.catalog_fingerprint,
                          catalog_valid_until=worker_inputs.get("catalog_valid_until"))
    return admission, dict(max_age_seconds=catalog.max_age_seconds, **worker_inputs)


@paper_router.post("/eligibility", response_model=PaperAdmission, responses=PAPER_DECISIONS)
async def paper_eligibility(proposal: PaperProposal, request: Request):
    admission, _ = await _admit(request, proposal)
    return _decision_response(admission)


@paper_router.post("/run", response_model=GeneralizedPaperResult, responses=PAPER_DECISIONS)
async def paper_run(body: PaperRunRequest, request: Request):
    proposal = PaperProposal.model_validate(body.model_dump(exclude={"expected"}))
    admission, worker_inputs = await _admit(request, proposal, expected=body.expected)
    if admission.status != "ELIGIBLE":
        return _decision_response(admission)
    try:
        result = await request.app.state.simulation_executor.execute(
            "run_generalized_paper", proposal=proposal, metadata=admission.profile.metadata,
            network=admission.identity.network, expected=admission.binding, **worker_inputs,
        )
    except PaperRejected as exc:
        return _decision_response(exc.admission)
    except (ResearchBusyError, ResearchUnavailableError) as exc:
        status = 429 if isinstance(exc, ResearchBusyError) else 503
        raise HTTPException(status, "Local PAPER worker unavailable",
                            headers={"Cache-Control": "no-store"}) from None
    except (ArithmeticError, ValueError):
        return _decision_response(decision(admission.identity, datetime.now(timezone.utc),
                                           "SCENARIO_INFEASIBLE", profile=admission.profile))
    result = GeneralizedPaperResult.model_validate(result)
    if result.admission.binding != admission.binding or result.proposal != proposal:
        raise HTTPException(500, "Local PAPER result does not match the admitted inputs",
                            headers={"Cache-Control": "no-store"})
    response = _paper_response(result)
    if len(response.body) > MAX_RESPONSE_BYTES:
        raise HTTPException(500, "Local PAPER result exceeded its transport bound",
                            headers={"Cache-Control": "no-store"})
    return response


router.include_router(paper_router)
