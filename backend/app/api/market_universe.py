"""Public perpetual metadata evidence and local PAPER research admission."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from functools import partial
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import Field, StrictInt, StrictStr, ValidationError
from pydantic_core import to_json

from app.agents.advisory_coordinator import (
    MAX_ADVISORY_BYTES, RECEIPT_HEADER, AdvisoryRequest, AdvisoryResponse, AdvisoryUnavailable,
)
from app.agents.advisory_evidence import AdvisoryBindingError
from app.amm.asset_policy import CONTROL_FIELDS
from app.amm.asset_policy_contracts import (
    AssetAmmPolicyAssessment, AssetAmmResearchControls, AssetAmmResearchPolicy,
    AssetFamily, AssetResearchClassification, assess_asset_amm_policy,
)
from app.infrastructure.research import ResearchUnavailableError
from app.market_data.live_models import Evidence
from app.market_data.market_risk_metadata import MarketFinancialObservation, SourceEvidence, SourceStatus
from app.market_data.market_universe_contracts import (
    CONTRACT_VERSION, InstrumentType, MarketInstrumentIdentity, Network, UtcDatetime,
)
from app.risk.market_risk_contracts import RiskFinancialUnit, RiskFingerprint
from app.risk.market_risk_engine import (
    MODEL_VERSION, ResearchRiskError, ResearchRiskSettings, RiskReason, bind_research_model,
    source_policy_rejection, supported_tier_denomination,
)
from app.simulation.executor import ResearchBusyError
from app.simulation.generalized_market_profiles import (
    DECIMAL_CONTEXT, GeneralizedPaperResult, MAX_RESPONSE_BYTES, PROFILE_VERSION, PaperAdmission, PaperProposal,
    PaperRejected, PaperRunRequest, ResearchDecimal, advisory_rejection, baseline_strategy, decision,
    paper_freshness_rejection, prepare_assessment,
)
from app.market_data.market_summaries import MarketSummaryRequest, MarketSummaryResponse
from app.market_data.market_universe_discovery import (
    DiscoveryFailure, MarketUniverseResponse, RATE_LIMIT_BACKOFF, RESPONSE_VERSION,
)
from app.simulation.market_profiles import GeneralizedPrecisionError

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


@router.post("/market-universe/market-summaries", response_model=MarketSummaryResponse)
async def market_summaries(body: MarketSummaryRequest, request: Request, response: Response):
    headers = {"Cache-Control": "no-store"}
    response.headers.update(headers)

    async def collect():
        discovery = request.app.state.market_universe_discovery
        catalog = await discovery.catalog()
        generation = discovery.paper_generation(body.catalog_fingerprint)
        if (body.network != catalog.network or body.catalog_fingerprint != catalog.catalog_fingerprint
                or catalog.availability != "AVAILABLE" or catalog.catalog is None
                or generation is None or catalog.evaluated_at >= generation[0]):
            raise HTTPException(409, "Discovery generation changed or expired", headers=headers)
        keys = {record.identity.stable_key for record in catalog.catalog.records}
        if not keys.issuperset(body.market_keys):
            raise HTTPException(404, "Market missing from the selected catalog", headers=headers)
        try:
            return await request.app.state.market_summary_observations.summarize(body, catalog, discovery, generation)
        except DiscoveryFailure as exc:
            if exc.code not in {"MISSING_METADATA", "NETWORK_MISMATCH"}:
                raise
            raise HTTPException(409, "Discovery generation changed or expired", headers=headers) from None

    async def disconnected():
        while (await request.receive())["type"] != "http.disconnect":
            pass

    work = asyncio.create_task(collect())
    monitor = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait((work, monitor), return_when=asyncio.FIRST_COMPLETED)
        if work in done:
            return work.result()
        raise HTTPException(499, "Market summary request disconnected", headers=headers)
    finally:
        for task in (work, monitor):
            if not task.done():
                task.cancel()
        await asyncio.gather(work, monitor, return_exceptions=True)


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


async def _paper_catalog(request: Request, identity):
    source = request.app.state.market_universe_discovery
    catalog = await source.catalog()
    supported = (catalog.schema_version == RESPONSE_VERSION and catalog.contract_version == CONTRACT_VERSION
                 and (catalog.catalog is None or catalog.catalog.contract_version == CONTRACT_VERSION))
    if not supported:
        return source, catalog, None, None, False
    generation = (source.paper_generation(catalog.catalog_fingerprint)
                  if catalog.availability == "AVAILABLE" and catalog.catalog_fingerprint is not None else None)
    records = catalog.catalog.records if catalog.catalog is not None else ()
    metadata = next((record for record in records if record.identity == identity), None)
    return source, catalog, generation, metadata, True


def _published_advisory(request: Request, fingerprint: str):
    coordinator = getattr(request.app.state, "advisory_coordinator", None)
    return coordinator.resolve_snapshot(fingerprint) if coordinator is not None else None


class AssetPolicyPreviewRequest(Evidence):
    profile_version: Literal["phase182-v1"]
    identity: MarketInstrumentIdentity
    catalog_fingerprint: RiskFingerprint
    simulated_reference_price: ResearchDecimal = Field(gt=0, le=10_000_000)
    minimum_order_notional: ResearchDecimal = Field(default=Decimal("100"), gt=0, le=2000)
    family: AssetFamily
    controls: dict[Annotated[str, Field(max_length=40)], Annotated[StrictStr, Field(max_length=80)] | StrictInt] = Field(
        default_factory=dict, max_length=len(CONTROL_FIELDS),
    )
    research_risk: ResearchRiskSettings | None = None
    advisory_snapshot_fingerprint: RiskFingerprint | None = None


class AssetPolicyPreview(Evidence):
    policy: AssetAmmResearchPolicy
    assessment: AssetAmmPolicyAssessment


@paper_router.post("/asset-policy/preview", response_model=AssetPolicyPreview, responses=PAPER_DECISIONS)
async def asset_policy_preview(body: AssetPolicyPreviewRequest, request: Request):
    source, catalog, generation, metadata, supported = await _paper_catalog(request, body.identity)
    now = catalog.evaluated_at

    def reject(reason):
        return _decision_response(decision(body.identity, now, reason))

    if not supported or catalog.catalog is None:
        return reject("METADATA_UNAVAILABLE")
    if body.identity.network != catalog.network:
        return reject("NETWORK_MISMATCH")
    if generation is None or now >= generation[0] or not generation[1]():
        return reject("METADATA_STALE")
    if body.catalog_fingerprint != catalog.catalog_fingerprint:
        return reject("CATALOG_FINGERPRINT_MISMATCH")
    if metadata is None:
        return reject("IDENTITY_MISMATCH")
    if metadata.listed is not True:
        return reject("MARKET_DELISTED")
    if (body.controls.keys() - set(CONTROL_FIELDS)
            or any(type(value) is not (int if name == "levels_per_side" else str)
                   for name, value in body.controls.items())):
        return reject("CONFIGURATION_INVALID")

    try:
        with localcontext(DECIMAL_CONTEXT):
            strategy = baseline_strategy(body.identity.stable_key, metadata.sz_decimals,
                                         body.simulated_reference_price, body.minimum_order_notional)
            values = strategy.model_dump(mode="json", include=set(CONTROL_FIELDS))
            controls = AssetAmmResearchControls.model_validate_json(to_json(values | body.controls))
            risk_model = None
            if body.research_risk is not None:
                risk_model = bind_research_model(
                    body.research_risk, metadata, source=source.financial_observation(body.catalog_fingerprint, body.identity),
                    evaluated_at=now, max_age_seconds=catalog.max_age_seconds,
                )
            risk_fingerprint = risk_model.fingerprint() if risk_model is not None else None
            policy = AssetAmmResearchPolicy(
                metadata=metadata, metadata_fingerprint=metadata.fingerprint(),
                classification=AssetResearchClassification(family=body.family), controls=controls,
                hypothetical_accounting_unit=RiskFinancialUnit(
                    network=metadata.identity.network, kind="HYPOTHETICAL_QUOTE",
                    symbol="HYPOTHETICAL_QUOTE", provenance="RESEARCH_ASSUMPTION",
                ),
                simulated_reference_price=body.simulated_reference_price, declared_at=now,
                catalog_fingerprint=body.catalog_fingerprint, research_risk_fingerprint=risk_fingerprint,
                advisory_snapshot_fingerprint=body.advisory_snapshot_fingerprint,
            )
            assessment = assess_asset_amm_policy(policy, evaluated_at=now, max_age_seconds=catalog.max_age_seconds)
    except (ResearchRiskError, GeneralizedPrecisionError) as exc:
        return reject(exc.reason)
    except (ArithmeticError, ValueError, TypeError):
        return reject("CONFIGURATION_INVALID")
    if assessment.status == "BLOCKED":
        return reject("METADATA_STALE")
    if body.advisory_snapshot_fingerprint is not None:
        reason = advisory_rejection(policy, metadata, body.catalog_fingerprint, risk_fingerprint, now,
                                    _published_advisory(request, body.advisory_snapshot_fingerprint))
        if reason is not None:
            return reject(reason)
    return _paper_response(AssetPolicyPreview(policy=policy, assessment=assessment))


async def _admit(request: Request, proposal: PaperProposal, expected=None):
    source, catalog, generation, metadata, supported = await _paper_catalog(request, proposal.identity)
    if not supported:
        return decision(proposal.identity, datetime.now(timezone.utc), "METADATA_UNAVAILABLE"), {}
    policy = proposal.asset_amm_policy

    def capture_sources():
        evidence = {}
        if generation is not None and proposal.research_risk is not None:
            evidence["risk_source"] = source.financial_observation(catalog.catalog_fingerprint, proposal.identity)
        if generation is not None and policy is not None and policy.advisory_snapshot_fingerprint is not None:
            evidence["advisory_evidence"] = _published_advisory(request, policy.advisory_snapshot_fingerprint)
        return evidence

    catalog_deadline, catalog_guard = generation if generation is not None else (None, None)
    catalog_inputs = dict(network=catalog.network, max_age_seconds=catalog.max_age_seconds,
                          catalog_fingerprint=catalog.catalog_fingerprint, catalog_valid_until=catalog_deadline)
    evidence = capture_sources()
    assessment = prepare_assessment(proposal, metadata, evaluated_at=catalog.evaluated_at,
                                    metadata_current=generation is not None, expected=expected,
                                    **catalog_inputs, **evidence)
    if isinstance(assessment, PaperAdmission):
        return assessment, {}

    def clock():
        return datetime.now(timezone.utc)

    compile_scenario = partial(assessment.compile, catalog_guard, evidence.get("advisory_evidence"), clock)
    try:
        admission, prepared = await request.app.state.simulation_executor.preflight(compile_scenario)
    except ResearchBusyError:
        raise HTTPException(429, "Local PAPER preflight busy", headers={"Cache-Control": "no-store"}) from None
    if prepared is None:
        return admission, {}
    if await request.is_disconnected():
        raise HTTPException(499, "PAPER request disconnected", headers={"Cache-Control": "no-store"})
    # The captured metadata belongs to this specific generation, including when
    # another refresh produces the same catalog fingerprint. No refresh is needed here.
    now = max(catalog.evaluated_at, clock())
    rejection = paper_freshness_rejection(admission, now, catalog_guard, evidence.get("advisory_evidence"))
    if rejection is not None:
        return rejection, {}
    evidence = capture_sources()
    current = prepare_assessment(proposal, metadata, evaluated_at=now, expected=admission.binding,
                                 **catalog_inputs, **evidence)
    if isinstance(current, PaperAdmission):
        return current, {}
    # Rebind the server-prepared scenario to the current source inputs without
    # compiling or preflighting its frames a second time.
    current_admission, _ = current.finish(prepared)
    if current_admission.status != "ELIGIBLE":
        return current_admission, {}
    rejection = paper_freshness_rejection(current_admission, max(now, clock()), catalog_guard,
                                          evidence.get("advisory_evidence"))
    if rejection is not None:
        return rejection, {}
    return current_admission, dict(max_age_seconds=catalog.max_age_seconds, catalog_valid_until=catalog_deadline,
                                   catalog_guard=catalog_guard, preflighted=prepared, **evidence)


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
