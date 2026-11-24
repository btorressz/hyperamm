"""Application-owned advisory research over discovery and completed local PAPER runs."""
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import localcontext
from os import urandom
from typing import Literal

from anyio import CapacityLimiter, WouldBlock, to_thread
from pydantic import Field, model_validator

from app.market_data.advisory_market_observations import AdvisoryMarketObservations
from app.market_data.market_universe_contracts import MarketInstrumentIdentity, UtcDatetime
from app.market_data.market_universe_discovery import MarketUniverseDiscovery
from app.market_data.models import utcnow
from app.risk.firewall import RiskState
from app.risk.market_risk_contracts import RiskFingerprint
from app.simulation.generalized_market_profiles import (
    DECIMAL_CONTEXT, MAX_FRAMES, GeneralizedPaperResult, PaperProposal,
)

from .advisory_contracts import AdvisoryEvidence, AdvisorySnapshot, ResearchOperation
from .advisory_evidence import AdvisoryBindingError, capture_context
from .funding_basis import FundingBasisAgent, PaperFundingObservation
from .market_eligibility import MarketEligibilityAgent, PaperEligibilityCapture
from .quote_economics import QuoteCostAssumptions, QuoteEconomicsAgent, QuoteEconomicsObservation

SCHEMA_VERSION = "phase184e-v1"
RECEIPT_HEADER = "X-Paper-Advisory-Receipt"
MAX_ADVISORY_BYTES = 65_536
RECEIPT_LIMIT = 8
RECEIPT_AGE = timedelta(minutes=5)
PAPER_OPERATIONS = frozenset({"STANDARD_PAPER", "HYPOTHETICAL_RISK", "SOURCE_CONSTRAINED_RISK"})


class QuoteSelection(AdvisoryEvidence):
    sequence: int = Field(ge=1, le=MAX_FRAMES)
    assumptions: QuoteCostAssumptions


class AdvisoryRequest(AdvisoryEvidence):
    identity: MarketInstrumentIdentity
    catalog_fingerprint: RiskFingerprint
    operation: ResearchOperation
    proposal: PaperProposal | None = None
    funding_mode: Literal["OBSERVED", "PAPER"] | None = None
    paper_receipt: RiskFingerprint | None = None
    quote: QuoteSelection | None = None

    @model_validator(mode="after")
    def check_selectors(self):
        if self.proposal is not None and (self.proposal.identity != self.identity
                or self.operation not in PAPER_OPERATIONS or self.paper_receipt is not None):
            raise ValueError("PAPER proposal must match the market and requested admission operation")
        if self.paper_receipt is not None and self.funding_mode != "PAPER" and self.quote is None and self.operation != "QUOTE_ECONOMICS":
            raise ValueError("PAPER receipt requires synthetic funding or quote research")
        return self


IssueCode = Literal[
    "PAPER_RESULT_REQUIRED", "PAPER_RESULT_UNAVAILABLE", "PAPER_EVIDENCE_EXPIRED",
    "QUOTE_COHORT_REQUIRED", "INVALID_QUOTE_COHORT",
    "PROVIDER_OBSERVATION_UNAVAILABLE", "PROVIDER_RATE_LIMITED", "PROVIDER_TIMEOUT",
    "PROVIDER_IDENTITY_MISMATCH",
]


class AdvisoryResponse(AdvisoryEvidence):
    schema_version: Literal["phase184e-v1"] = SCHEMA_VERSION
    identity: MarketInstrumentIdentity
    snapshot: AdvisorySnapshot
    snapshot_fingerprint: RiskFingerprint
    evaluated_at: UtcDatetime
    valid_until: UtcDatetime
    funding_mode: Literal["OBSERVED", "PAPER"] | None
    paper_result_fingerprint: RiskFingerprint | None
    quote_cohorts: tuple[int, ...] = Field(max_length=MAX_FRAMES)
    quote_sequence: int | None
    quote_risk_state: RiskState | None
    issues: tuple[IssueCode, ...] = Field(max_length=5)
    read_only: Literal[True] = True
    affects_quotes: Literal[False] = False
    can_override_risk: Literal[False] = False
    can_authorize_paper: Literal[False] = False
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"


class AdvisoryUnavailable(Exception):
    def __init__(self, code: str, status: int, message: str):
        self.code, self.status, self.message = code, status, message


@dataclass(frozen=True)
class _Receipt:
    identity: MarketInstrumentIdentity
    catalog_fingerprint: str
    captured_at: datetime
    valid_until: datetime
    body: bytes


class AdvisoryCoordinator:
    def __init__(self, discovery: MarketUniverseDiscovery, *, clock=utcnow, budget=None):
        self._discovery = discovery
        self._observations = AdvisoryMarketObservations(network=discovery.network, clock=clock, budget=budget)
        self._clock = clock
        self._receipts: OrderedDict[str, _Receipt] = OrderedDict()
        self._snapshots: OrderedDict[str, tuple[AdvisorySnapshot, datetime]] = OrderedDict()
        self._requests = CapacityLimiter(8)
        self._evaluations = CapacityLimiter(3)

    def retain(self, result: GeneralizedPaperResult, body: bytes) -> str:
        """Publish a fresh receipt only for a validated worker response."""
        now = self._clock()
        receipt = urandom(32).hex()
        self._receipts[receipt] = _Receipt(
            result.admission.identity, result.admission.binding.catalog_fingerprint,
            now, min(now + RECEIPT_AGE, result.admission.valid_until), body,
        )
        if len(self._receipts) > RECEIPT_LIMIT:
            self._receipts.popitem(last=False)
        return receipt

    def resolve_snapshot(self, fingerprint: str) -> tuple[AdvisorySnapshot, datetime] | None:
        """Supply previously published server evidence to PAPER admission."""
        return self._snapshots.get(fingerprint)

    async def close(self):
        self._receipts.clear()
        self._snapshots.clear()
        await self._observations.close()

    async def evaluate(self, request: AdvisoryRequest) -> AdvisoryResponse:
        try:
            self._requests.acquire_nowait()
        except WouldBlock:
            raise AdvisoryUnavailable("RESEARCH_WORKER_UNAVAILABLE", 503, "Advisory research capacity is busy.") from None
        try:
            return await self._evaluate(request)
        finally:
            self._requests.release()

    async def _evaluate(self, request: AdvisoryRequest) -> AdvisoryResponse:
        catalog = await self._discovery.catalog()
        identity = request.identity
        if identity.network != catalog.network:
            raise AdvisoryUnavailable("WRONG_NETWORK", 409, "The market is on a different discovery network.")
        if catalog.catalog is None:
            raise AdvisoryUnavailable("CATALOG_UNAVAILABLE", 503, "Current discovery metadata is unavailable.")
        if catalog.catalog_fingerprint != request.catalog_fingerprint or catalog.availability != "AVAILABLE":
            raise AdvisoryUnavailable("CATALOG_STALE", 409, "Refresh discovery and select the market again.")
        generation = self._discovery.paper_generation(request.catalog_fingerprint)
        if generation is None:
            raise AdvisoryUnavailable("CATALOG_STALE", 409, "The discovery generation was retired.")
        deadline, active = generation

        def current_time():
            now = self._clock()
            if now >= deadline or not active():
                raise AdvisoryUnavailable("CATALOG_STALE", 409, "The discovery generation expired during research.")
            return now

        current_time()
        if identity.dex and not any(check.dex == identity.dex for check in catalog.namespaces):
            raise AdvisoryUnavailable("WRONG_DEX", 404, "The DEX namespace is absent from discovery.")
        metadata = next((record for record in catalog.catalog.records if record.identity == identity), None)
        if metadata is None:
            raise AdvisoryUnavailable("UNKNOWN_MARKET", 404, "The market is absent from this DEX and catalog.")

        receipt = self._receipts.get(request.paper_receipt)
        if receipt is not None and receipt.identity != identity:
            raise AdvisoryUnavailable("PAPER_BINDING_MISMATCH", 409, "The PAPER receipt belongs to a different market.")
        risk_source = (self._discovery.financial_observation(request.catalog_fingerprint, identity)
                       if request.proposal is not None and request.proposal.research_risk is not None else None)
        policy = request.proposal.asset_amm_policy if request.proposal is not None else None
        advisory_evidence = (self.resolve_snapshot(policy.advisory_snapshot_fingerprint)
                             if policy is not None and policy.advisory_snapshot_fingerprint is not None else None)
        funding_mode = request.funding_mode or ("OBSERVED" if request.operation == "FUNDING_BASIS" else None)
        public = await self._observations.observe(metadata) if funding_mode == "OBSERVED" else None

        # Drop expired sources through the evaluators if a source expired during
        # CPU work. The owning event loop checks the catalog again at publication.
        for _ in range(2):
            now = current_time()
            response = await to_thread.run_sync(
                self._capture, request, metadata, catalog.max_age_seconds, deadline, now,
                risk_source, receipt, funding_mode, public, advisory_evidence, limiter=self._evaluations,
            )
            published_at = current_time()
            if published_at < response.valid_until:
                response.snapshot.validate_at(as_of=published_at)
                self._snapshots[response.snapshot_fingerprint] = (response.snapshot, response.valid_until)
                self._snapshots.move_to_end(response.snapshot_fingerprint)
                if len(self._snapshots) > RECEIPT_LIMIT:
                    self._snapshots.popitem(last=False)
                return response
        raise AdvisoryUnavailable("EVIDENCE_EXPIRED", 409, "Advisory evidence expired during evaluation.")

    @staticmethod
    def _capture(request, metadata, max_age, deadline, now, risk_source, receipt, funding_mode, public, advisory_evidence):
        issues = []
        sources = []
        admission = None
        paper = None
        funding = public
        economics = None
        quote_sequence = None
        quote_risk_state = None
        cohorts = ()
        wants_quote = request.operation == "QUOTE_ECONOMICS" or request.quote is not None
        if request.proposal is not None:
            admission = PaperEligibilityCapture.from_assessment(
                request.proposal, metadata, network=metadata.identity.network, evaluated_at=now,
                catalog_valid_until=deadline, catalog_fingerprint=request.catalog_fingerprint,
                max_age_seconds=max_age, risk_source=risk_source, advisory_evidence=advisory_evidence,
            )
            sources.extend(admission.source_evidence())
        if wants_quote or funding_mode == "PAPER":
            if request.paper_receipt is None:
                issues.append("PAPER_RESULT_REQUIRED")
            elif receipt is None:
                issues.append("PAPER_RESULT_UNAVAILABLE")
            elif receipt.catalog_fingerprint != request.catalog_fingerprint or now >= receipt.valid_until:
                issues.append("PAPER_EVIDENCE_EXPIRED")
            else:
                with localcontext(DECIMAL_CONTEXT):
                    paper = GeneralizedPaperResult.model_validate_json(receipt.body)
                if paper.admission.profile.metadata != metadata or paper.admission.binding.catalog_fingerprint != request.catalog_fingerprint:
                    raise AdvisoryBindingError("retained PAPER result does not match the active catalog")
        if paper is not None:
            if funding_mode == "PAPER":
                funding = PaperFundingObservation(paper, receipt.captured_at, receipt.valid_until)
            if wants_quote:
                cohorts = tuple(sorted(point.sequence for point in paper.result.trace))
                if request.quote is None:
                    issues.append("QUOTE_COHORT_REQUIRED")
                elif request.quote.sequence not in cohorts:
                    issues.append("INVALID_QUOTE_COHORT")
                else:
                    trace = next(point for point in paper.result.trace if point.sequence == request.quote.sequence)
                    quote_sequence, quote_risk_state = trace.sequence, RiskState(trace.risk_state)
                    economics = QuoteEconomicsObservation(
                        paper, trace.sequence, request.quote.assumptions, receipt.captured_at, receipt.valid_until,
                    )
                    sources.extend(economics.source_evidence())
        if funding is not None:
            sources.extend(funding.source_evidence())
        if public is not None:
            issue = {
                "RATE_LIMITED": "PROVIDER_RATE_LIMITED",
                "TIMEOUT": "PROVIDER_TIMEOUT",
                "NAMESPACE_CONFLICT": "PROVIDER_IDENTITY_MISMATCH",
                "NETWORK_MISMATCH": "PROVIDER_IDENTITY_MISMATCH",
            }.get(public.failure_code)
            if issue or public.status != "AVAILABLE":
                issues.append(issue or "PROVIDER_OBSERVATION_UNAVAILABLE")

        binding = (paper.admission.binding if paper is not None
                   else admission.admission.binding if admission is not None else None)
        context = capture_context(
            metadata, evaluated_at=now, valid_until=deadline, sources=sources,
            catalog_fingerprint=request.catalog_fingerprint, max_metadata_age_seconds=max_age,
            paper_binding_fingerprint=binding.configuration_fingerprint if binding else None,
            risk_model_fingerprint=binding.research_risk_fingerprint if binding else None,
        )
        if context.valid_until is None:
            raise AdvisoryUnavailable("CATALOG_STALE", 409, "Selected market metadata expired.")
        eligibility = MarketEligibilityAgent(max_metadata_age_seconds=max_age).evaluate(
            context, request.operation, paper=admission, funding=funding, economics=economics, as_of=now,
        )
        snapshot = AdvisorySnapshot(
            context=context, market_eligibility=eligibility,
            funding_basis=(FundingBasisAgent(max_metadata_age_seconds=max_age).evaluate(context, funding, as_of=now)
                           if funding_mode is not None else None),
            quote_economics=(QuoteEconomicsAgent(max_metadata_age_seconds=max_age).evaluate(context, economics, as_of=now)
                             if wants_quote else None),
        )
        used = {fp for item in (eligibility, snapshot.funding_basis, snapshot.quote_economics)
                if item is not None for fp in item.source_fingerprints}
        expiry = min([context.valid_until, *(source.valid_until for source in context.sources
                     if source.valid_until is not None and source.source_fingerprint in used)])
        return AdvisoryResponse(
            identity=request.identity, snapshot=snapshot, snapshot_fingerprint=snapshot.fingerprint(),
            evaluated_at=now, valid_until=expiry, funding_mode=funding_mode,
            paper_result_fingerprint=paper.result_fingerprint if paper is not None else None,
            quote_cohorts=cohorts, quote_sequence=quote_sequence, quote_risk_state=quote_risk_state,
            issues=tuple(issues),
        )
