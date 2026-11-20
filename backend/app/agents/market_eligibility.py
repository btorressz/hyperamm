"""Operation-specific research suitability using existing server admission evidence."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.market_data.advisory_market_observations import OfficialPerpObservation
from app.market_data.market_risk_metadata import MarketFinancialObservation
from app.market_data.market_universe_contracts import MarketUniverseMetadata, Network, _utc
from app.simulation.generalized_market_profiles import PaperAdmission, PaperFingerprintBinding, PaperProposal, assess

from .advisory_contracts import AdvisoryContext, MarketEligibilityAdvisory, ResearchOperation
from .advisory_evidence import AdvisoryBindingError, AdvisoryEvaluation, captured_source, discovery_source
from .funding_basis import FundingBasisAgent, PaperFundingObservation

if TYPE_CHECKING:
    from .quote_economics import QuoteEconomicsObservation


@dataclass(frozen=True, init=False)
class PaperEligibilityCapture:
    """A server-owned call to the established PAPER assessor."""

    metadata: MarketUniverseMetadata
    proposal: PaperProposal
    admission: PaperAdmission
    catalog_fingerprint: str | None

    @classmethod
    def from_assessment(
        cls, proposal: PaperProposal, metadata: MarketUniverseMetadata, *,
        network: Network, evaluated_at: datetime, max_age_seconds: int,
        catalog_fingerprint: str | None = None, catalog_valid_until: datetime | None = None,
        metadata_current: bool = True, expected: PaperFingerprintBinding | None = None,
        risk_source: MarketFinancialObservation | None = None,
        advisory_evidence=None,
    ):
        proposal = PaperProposal.model_validate(proposal)
        metadata = MarketUniverseMetadata.model_validate(metadata)
        if proposal.identity != metadata.identity or metadata.identity.network != network:
            raise AdvisoryBindingError("PAPER proposal is outside the captured market/network")
        if risk_source is not None and MarketFinancialObservation.model_validate(risk_source).metadata != metadata:
            raise AdvisoryBindingError("financial source is outside the captured metadata generation")
        admission, _ = assess(
            proposal, metadata, network=network, evaluated_at=_utc(evaluated_at),
            max_age_seconds=max_age_seconds, catalog_fingerprint=catalog_fingerprint,
            catalog_valid_until=catalog_valid_until, metadata_current=metadata_current,
            expected=expected, risk_source=risk_source, advisory_evidence=advisory_evidence,
        )
        captured = object.__new__(cls)
        object.__setattr__(captured, "metadata", metadata)
        object.__setattr__(captured, "proposal", proposal)
        object.__setattr__(captured, "admission", admission)
        object.__setattr__(captured, "catalog_fingerprint", catalog_fingerprint)
        return captured

    def source_evidence(self):
        admission = PaperAdmission.model_validate(self.admission)
        sources = [captured_source(
            metadata=self.metadata, value=(self.proposal, admission, self.catalog_fingerprint),
            category="PAPER_ADMISSION", provenance="HYPOTHETICAL_ASSUMPTION",
            source_id="ASSUMPTION_PAPER_ASSESSMENT", captured_at=admission.evaluated_at,
            valid_until=admission.valid_until,
        )]
        model = admission.risk_model
        if model is not None:
            sources.append(captured_source(
                metadata=self.metadata, value=model, category="RISK_MODEL",
                provenance="HYPOTHETICAL_ASSUMPTION", source_id="ASSUMPTION_PAPER_RISK_MODEL",
                captured_at=admission.evaluated_at, valid_until=admission.valid_until,
                financial_unit=model.margin_unit,
            ))
        if model is not None and model.settings.mode == "SOURCE_CONSTRAINED":
            source = model.source
            sources.append(captured_source(
                metadata=self.metadata, value=source, category="MARGIN_POLICY",
                provenance="EXCHANGE_OBSERVED", source_id="HYPERLIQUID_FINANCIAL_METADATA",
                captured_at=source.metadata.observed_at, observation_clock="LOCAL_RECEIPT",
                valid_until=admission.valid_until, financial_unit=source.collateral.financial_unit(),
                limitations=("Public margin and collateral metadata use a hypothetical valuation.",),
            ))
        return tuple(sources)


class MarketEligibilityAgent:
    def __init__(self, *, max_metadata_age_seconds: int = 60):
        self._metadata_age = max_metadata_age_seconds

    def evaluate(
        self, context: AdvisoryContext, operation: ResearchOperation, *, as_of: datetime,
        paper: PaperEligibilityCapture | None = None,
        funding: OfficialPerpObservation | PaperFundingObservation | None = None,
        economics: QuoteEconomicsObservation | None = None,
    ) -> MarketEligibilityAdvisory:
        evaluation = AdvisoryEvaluation(context, as_of=as_of, max_metadata_age_seconds=self._metadata_age)
        context = evaluation.context

        def outcome(status, suitability, reason, missing=(), confidence=Decimal(0)):
            return MarketEligibilityAdvisory(
                **evaluation.fields(), operation=operation, status=status, suitability=suitability,
                confidence=confidence, reasons=(reason,), missing_requirements=missing,
            )

        if issue := evaluation.market_issue:
            status, reason = issue
            suitability = "NOT_SUITABLE" if status == "UNSUPPORTED" else "UNKNOWN"
            return outcome(status, suitability, reason, ("CURRENT_LISTED_MARKET_METADATA",))
        evaluation.bind((discovery_source(context.metadata),))

        if operation == "DISCOVERY":
            return outcome("READY", "SUITABLE", "Verified discovery supports this listed market and precision.",
                           confidence=Decimal(1))
        if operation in {"FUNDING_BASIS", "QUOTE_ECONOMICS"}:
            if operation == "FUNDING_BASIS":
                result = FundingBasisAgent(max_metadata_age_seconds=self._metadata_age).evaluate(
                    context, funding, as_of=as_of,
                )
            else:
                from .quote_economics import QuoteEconomicsAgent

                result = QuoteEconomicsAgent(max_metadata_age_seconds=self._metadata_age).evaluate(
                    context, economics, as_of=as_of,
                )
            used = set(result.source_fingerprints)
            evaluation.bind(source for source in context.sources if source.source_fingerprint in used)
            if result.status == "READY":
                suitability = "CONDITIONAL" if result.missing_requirements or result.agent == "QUOTE_ECONOMICS" else "SUITABLE"
                return outcome("READY", suitability, result.reasons[0], result.missing_requirements, result.confidence)
            suitability = "NOT_SUITABLE" if result.status == "UNSUPPORTED" else "UNKNOWN"
            return outcome(result.status, suitability, result.reasons[0], result.missing_requirements)

        if paper is None:
            return outcome("INSUFFICIENT_DATA", "UNKNOWN", "A captured PAPER assessment is required.",
                           ("PAPER_PROPOSAL_AND_ASSESSMENT",))
        if not isinstance(paper, PaperEligibilityCapture):
            raise AdvisoryBindingError("PAPER assessment must come from the server assessor")
        if paper.metadata != context.metadata or paper.catalog_fingerprint != context.catalog_fingerprint:
            raise AdvisoryBindingError("PAPER assessment is outside the captured context generation")
        required_mode = {"HYPOTHETICAL_RISK": "HYPOTHETICAL", "SOURCE_CONSTRAINED_RISK": "SOURCE_CONSTRAINED"}.get(operation)
        actual_mode = paper.proposal.research_risk.mode if paper.proposal.research_risk else None
        if actual_mode != required_mode:
            return outcome("INSUFFICIENT_DATA", "UNKNOWN", "Capture a PAPER assessment for the requested research mode.",
                           ("MATCHING_RESEARCH_SCENARIO",))

        admission = PaperAdmission.model_validate(paper.admission)
        if admission.binding is not None and (
                admission.binding.configuration_fingerprint != context.paper_binding_fingerprint
                or admission.binding.research_risk_fingerprint != context.risk_model_fingerprint):
            raise AdvisoryBindingError("PAPER or risk fingerprint differs from the captured context")
        if not evaluation.bind(paper.source_evidence()):
            return outcome("STALE", "UNKNOWN", "The captured PAPER assessment has expired.",
                           ("CURRENT_PAPER_ASSESSMENT",))

        if admission.status == "ELIGIBLE":
            return outcome("READY", "SUITABLE", "The existing PAPER assessment supports this research configuration.",
                           confidence=Decimal("0.85"))

        reason = admission.reason
        if reason in {"NETWORK_MISMATCH", "IDENTITY_MISMATCH", "METADATA_FINGERPRINT_MISMATCH",
                      "PROFILE_FINGERPRINT_MISMATCH", "CONFIGURATION_FINGERPRINT_MISMATCH",
                      "CATALOG_FINGERPRINT_MISMATCH", "RISK_FINGERPRINT_MISMATCH"}:
            raise AdvisoryBindingError(f"PAPER assessment rejected inconsistent binding ({reason})")
        if reason in {"METADATA_STALE", "RISK_SOURCE_STALE"}:
            status, suitability = "STALE", "UNKNOWN"
        elif admission.status == "UNAVAILABLE" or reason == "RISK_SOURCE_UNAVAILABLE":
            status, suitability = "INSUFFICIENT_DATA", "UNKNOWN"
        else:
            status, suitability = "UNSUPPORTED", "NOT_SUITABLE"
        return outcome(status, suitability, admission.explanation, admission.checks)
