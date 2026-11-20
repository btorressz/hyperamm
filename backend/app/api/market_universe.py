"""Public perpetual metadata evidence and local PAPER research admission."""
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import Field, ValidationError

from app.agents.advisory_coordinator import (
    MAX_ADVISORY_BYTES, RECEIPT_HEADER, AdvisoryRequest, AdvisoryResponse, AdvisoryUnavailable,
)
from app.agents.advisory_evidence import AdvisoryBindingError
from app.infrastructure.research import ResearchUnavailableError
from app.market_data.market_risk_metadata import MarketFinancialObservation, SourceEvidence, SourceStatus
from app.market_data.market_universe_contracts import (
    CONTRACT_VERSION, InstrumentType, MarketInstrumentIdentity, Network, UtcDatetime,
)
from app.risk.market_risk_contracts import RiskFingerprint
from app.risk.market_risk_engine import MODEL_VERSION, RiskReason, source_policy_rejection, supported_tier_denomination
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


class FinancialEvidenceSelection(SourceEvidence):
    network: Network
    instrument_type: InstrumentType
    dex: str = Field(max_length=32)
    instrument_name: str = Field(min_length=1, max_length=64)
    catalog_fingerprint: RiskFingerprint


class FinancialEvidenceResponse(SourceEvidence):
    schema_version: Literal["phase183e-v1"] = "phase183e-v1"
    model_version: Literal["phase183c-v1"] = MODEL_VERSION
    identity: MarketInstrumentIdentity
    catalog_fingerprint: RiskFingerprint
    metadata_fingerprint: RiskFingerprint
    evaluated_at: UtcDatetime
    valid_until: UtcDatetime
    status: SourceStatus
    observation: MarketFinancialObservation | None
    source_fingerprint: RiskFingerprint | None
    source_constraint_reason: RiskReason | None
    source_margin_modes: tuple[Literal["ISOLATED", "STRICT_ISOLATED", "NO_CROSS"], ...] = Field(max_length=2)
    scope: Literal["LOCAL_PAPER_ONLY"] = "LOCAL_PAPER_ONLY"
    read_only: Literal[True] = True
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"


@router.get("/market-universe/risk-evidence", response_model=FinancialEvidenceResponse)
async def financial_evidence(selection: Annotated[FinancialEvidenceSelection, Query()], request: Request, response: Response):
    headers = {"Cache-Control": "no-store"}
    response.headers.update(headers)
    try:
        identity = MarketInstrumentIdentity.model_validate(selection.model_dump(exclude={"catalog_fingerprint"}))
    except ValidationError:
        raise HTTPException(422, "Invalid canonical market identity", headers=headers) from None
    discovery = request.app.state.market_universe_discovery
    catalog = await discovery.catalog()
    if identity.network != catalog.network or selection.catalog_fingerprint != catalog.catalog_fingerprint:
        raise HTTPException(409, "Discovery generation changed", headers=headers)
    generation = discovery.paper_generation(selection.catalog_fingerprint)
    if (catalog.availability != "AVAILABLE" or catalog.catalog is None
            or generation is None or catalog.evaluated_at >= generation[0]):
        raise HTTPException(409, "Discovery generation expired", headers=headers)
    metadata = next((record for record in catalog.catalog.records if record.identity == identity), None)
    if metadata is None:
        raise HTTPException(404, "Market missing from the selected catalog", headers=headers)
    observed = discovery.financial_observation(selection.catalog_fingerprint, identity)
    status = observed.status_at(catalog.evaluated_at, catalog.max_age_seconds) if observed else "UNAVAILABLE"
    deadline = min(generation[0], observed.valid_until(catalog.max_age_seconds)) if observed else generation[0]
    if not metadata.listed:
        status, reason = "UNSUPPORTED", "RISK_SOURCE_UNSUPPORTED"
    else:
        reason = source_policy_rejection(observed, status)
    modes = ()
    if reason is None:
        if not supported_tier_denomination(observed):
            reason = "RISK_SOURCE_UNSUPPORTED"
        else:
            modes = (("ISOLATED", observed.margin.mode) if observed.margin.mode in {"STRICT_ISOLATED", "NO_CROSS"}
                     else ("ISOLATED",))
    return FinancialEvidenceResponse(
        identity=identity, catalog_fingerprint=selection.catalog_fingerprint,
        metadata_fingerprint=metadata.fingerprint(), evaluated_at=catalog.evaluated_at,
        valid_until=deadline, status=status, observation=observed,
        source_fingerprint=observed.fingerprint() if observed else None,
        source_constraint_reason=reason, source_margin_modes=modes,
    )


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
    if generation is not None and proposal.research_risk is not None:
        worker_inputs["risk_source"] = source.financial_observation(catalog.catalog_fingerprint, proposal.identity)
    policy = proposal.asset_amm_policy
    if generation is not None and policy is not None and policy.advisory_snapshot_fingerprint is not None:
        coordinator = getattr(request.app.state, "advisory_coordinator", None)
        if coordinator is not None:
            worker_inputs["advisory_evidence"] = coordinator.resolve_snapshot(policy.advisory_snapshot_fingerprint)
    metadata = next((record for record in catalog.catalog.records
                     if record.identity == proposal.identity), None) if catalog.catalog is not None else None
    admission, _ = assess(proposal, metadata, network=catalog.network, evaluated_at=catalog.evaluated_at,
                          max_age_seconds=catalog.max_age_seconds,
                          metadata_current=generation is not None, expected=expected,
                          catalog_fingerprint=catalog.catalog_fingerprint,
                          catalog_valid_until=worker_inputs.get("catalog_valid_until"),
                          risk_source=worker_inputs.get("risk_source"),
                          advisory_evidence=worker_inputs.get("advisory_evidence"))
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
    if admission.risk_model is not None or proposal.asset_amm_policy is not None:
        now = datetime.now(timezone.utc)
        if now >= admission.valid_until or not worker_inputs["catalog_guard"]():
            reason = "RISK_SOURCE_STALE" if admission.risk_model and admission.risk_model.source else "METADATA_STALE"
            advisory_evidence = worker_inputs.get("advisory_evidence")
            if advisory_evidence is not None and now >= advisory_evidence[1]:
                reason = "ADVISORY_STALE"
            return _decision_response(decision(admission.identity, now, reason, profile=admission.profile))
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
    coordinator = getattr(request.app.state, "advisory_coordinator", None)
    if coordinator is not None:
        response.headers[RECEIPT_HEADER] = coordinator.retain(result, response.body)
    return response


@router.post("/market-universe/advisory", response_model=AdvisoryResponse)
async def advisory(body: AdvisoryRequest, request: Request):
    headers = {"Cache-Control": "no-store"}
    try:
        coordinator = getattr(request.app.state, "advisory_coordinator", None)
        if coordinator is None:
            raise AdvisoryUnavailable("RESEARCH_WORKER_UNAVAILABLE", 503, "Advisory research is unavailable.")
        evidence = await coordinator.evaluate(body)
    except AdvisoryUnavailable as exc:
        raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}, headers=headers) from None
    except AdvisoryBindingError as exc:
        raise HTTPException(500, {"code": "EVIDENCE_BINDING_FAILURE", "message": "Advisory evidence failed validation."},
                            headers=headers) from exc
    response = _paper_response(evidence)
    if len(response.body) > MAX_ADVISORY_BYTES:
        raise HTTPException(500, {"code": "RESPONSE_TOO_LARGE", "message": "Advisory evidence exceeded its size bound."},
                            headers=headers)
    return response


router.include_router(paper_router)
