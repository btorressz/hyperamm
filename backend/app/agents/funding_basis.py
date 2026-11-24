"""Read-only funding and basis analysis for one captured market."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from app.market_data.advisory_market_observations import OfficialPerpObservation
from app.market_data.market_universe_contracts import _utc
from app.market_data.perp_context import _basis
from app.market_data.public_perp_financials import HYPERLIQUID_INTERVAL_SECONDS
from app.risk.market_risk_engine import RISK_CONTEXT
from app.simulation.generalized_market_profiles import DECIMAL_CONTEXT, GeneralizedPaperResult

from .advisory_contracts import AdvisoryContext, FundingBasisAdvisory
from .advisory_evidence import AdvisoryBindingError, AdvisoryEvaluation, captured_paper_scenario, captured_source
from .common import mean
from .config import AgentConfig

REQUIRED_CATEGORIES = ("FUNDING", "MARK_PRICE", "ORACLE_PRICE")
BPS_QUANTUM = Decimal("0.00000001")
BPS_LIMIT = Decimal("1000000")


@dataclass(frozen=True)
class PaperFundingObservation:
    """A server-owned Generalized PAPER result with its receipt and research clocks."""

    paper: GeneralizedPaperResult
    captured_at: datetime
    valid_until: datetime

    def _checked(self):
        with localcontext(DECIMAL_CONTEXT):
            paper = GeneralizedPaperResult.model_validate(self.paper)
        captured_at = _utc(self.captured_at)
        if captured_at < paper.started_at or _utc(self.valid_until) <= captured_at:
            raise AdvisoryBindingError("invalid PAPER observation capture or expiry")
        return paper

    def source_evidence(self):
        paper = self._checked()
        return self._sources(paper, captured_paper_scenario(paper).dataset.frames[-1])

    def _sources(self, paper, frame):
        perp = frame.perp_context
        interval = paper.proposal.economics.funding_interval_seconds
        values = (
            ("FUNDING", "RATE_PER_PAPER_INTERVAL", None if interval is None else (perp.funding_rate, interval)),
            ("MARK_PRICE", "PAPER_QUOTE_PER_BASE", perp.mark_price),
            ("ORACLE_PRICE", "PAPER_QUOTE_PER_BASE", perp.oracle_price),
            ("MID_PRICE", "PAPER_QUOTE_PER_BASE", frame.market.mid_price),
            ("OPEN_INTEREST", "BASE", perp.open_interest_base),
        )
        return tuple(captured_source(
            metadata=paper.admission.profile.metadata,
            value=(paper.result_fingerprint, value),
            category=category, provenance="SCENARIO_SYNTHETIC", source_id="PAPER_LAST_FRAME",
            captured_at=_utc(self.captured_at), scenario_at=frame.timestamp,
            valid_until=_utc(self.valid_until), unit=unit,
        ) for category, unit, value in values if value is not None)


class FundingBasisAgent:
    def __init__(self, config: AgentConfig | None = None, *, max_metadata_age_seconds: int = 60):
        self._basis_threshold = (config or AgentConfig()).crowding_basis_threshold_bps
        self._metadata_age = max_metadata_age_seconds

    def evaluate(
        self, context: AdvisoryContext, observation: OfficialPerpObservation | PaperFundingObservation | None,
        *, as_of: datetime,
    ) -> FundingBasisAdvisory:
        evaluation = AdvisoryEvaluation(context, as_of=as_of, max_metadata_age_seconds=self._metadata_age)

        def unavailable(status, reason, missing=(), **fields):
            return FundingBasisAdvisory(
                **evaluation.fields(), status=status, reasons=(reason,), missing_requirements=missing, **fields,
            )

        if issue := evaluation.market_issue:
            return unavailable(*issue)
        if observation is None:
            return unavailable("INSUFFICIENT_DATA", "Capture an official observation or a PAPER scenario.",
                               REQUIRED_CATEGORIES)
        if isinstance(observation, OfficialPerpObservation):
            if (observation.metadata != evaluation.context.metadata
                    or observation.catalog_fingerprint != evaluation.context.catalog_fingerprint):
                raise AdvisoryBindingError("official funding observation does not match captured metadata or catalog")
            if observation.status != "AVAILABLE":
                missing = tuple(category for category in REQUIRED_CATEGORIES if observation.point(category) is None)
                if observation.status == "INSUFFICIENT_DATA":
                    if not evaluation.bind(observation.source_evidence()):
                        return unavailable("STALE", "Public funding evidence has expired.", missing)
                    if not missing:
                        missing = ("PRICE_UNIT_COMPATIBILITY",)
                elif observation.status == "UNSUPPORTED" and observation.failure_code == "UNSUPPORTED_METADATA":
                    missing += ("PRICE_UNIT_COMPATIBILITY",)
                prices = {
                    field: point.value
                    for category, field in (("MARK_PRICE", "mark_price"), ("ORACLE_PRICE", "oracle_price"))
                    if (point := observation.point(category)) is not None
                    and observation.status == "INSUFFICIENT_DATA"
                }
                return unavailable(observation.status, observation.limitations[0], missing, **prices)
            points = {point.category: point for point in observation.points}
            if (not set(REQUIRED_CATEGORIES) <= points.keys()
                    or {points[key].operation for key in REQUIRED_CATEGORIES} != {"metaAndAssetCtxs"}
                    or len({points[key].captured_at for key in REQUIRED_CATEGORIES}) != 1
                    or points["FUNDING"].details != (HYPERLIQUID_INTERVAL_SECONDS,)
                    or points["FUNDING"].unit != "RATE_PER_HOUR"
                    or points["MARK_PRICE"].unit != "PRICE_QUOTE_PER_BASE"
                    or points["ORACLE_PRICE"].unit != "PRICE_QUOTE_PER_BASE"):
                raise AdvisoryBindingError("unaligned official funding and price evidence")
            rate, mark, oracle = (points[key].value for key in REQUIRED_CATEGORIES)
            interval = HYPERLIQUID_INTERVAL_SECONDS
            convention = "HYPERLIQUID_HOURLY"
            mid = points["MID_PRICE"].value if "MID_PRICE" in points else None
            oi = points["OPEN_INTEREST"].value if "OPEN_INTEREST" in points else None
            history = points["FUNDING_HISTORY"].value if "FUNDING_HISTORY" in points else ()
            confidence = Decimal("0.90")
            reasons = ["Current hourly funding uses compatible public mark and oracle from the same response.",
                       "Current context has a receipt time only. Rates can change before settlement."]
            reasons.extend(observation.limitations)
            sources = observation.source_evidence()
        elif isinstance(observation, PaperFundingObservation):
            paper = observation._checked()
            if (paper.admission.profile.metadata != evaluation.context.metadata
                    or paper.admission.binding.catalog_fingerprint != evaluation.context.catalog_fingerprint
                    or paper.admission.binding.configuration_fingerprint != evaluation.context.paper_binding_fingerprint
                    or paper.admission.binding.research_risk_fingerprint != evaluation.context.risk_model_fingerprint):
                raise AdvisoryBindingError("PAPER funding observation does not match context bindings")
            interval = paper.proposal.economics.funding_interval_seconds
            if interval is None:
                return unavailable("INSUFFICIENT_DATA", "An explicit PAPER funding schedule is required.",
                                   ("PAPER_FUNDING_INTERVAL",))
            frame = captured_paper_scenario(paper).dataset.frames[-1]
            perp = frame.perp_context
            rate, mark, oracle = perp.funding_rate, perp.mark_price, perp.oracle_price
            mid, oi, history = frame.market.mid_price, perp.open_interest_base, ()
            convention = "PAPER_SCHEDULED_INTERVAL"
            confidence = Decimal("0.60")
            reasons = ["The last PAPER frame supplies synthetic prices and a rate per configured PAPER interval."]
            sources = observation._sources(paper, frame)
        else:
            raise AdvisoryBindingError("funding evidence must be captured by the backend")

        by_category = {source.category: source for source in sources}
        if not evaluation.bind(by_category[key] for key in REQUIRED_CATEGORIES):
            return unavailable("STALE", "Funding and basis inputs have expired.")
        optional = {}
        for key, value in (("MID_PRICE", mid), ("OPEN_INTEREST", oi), ("FUNDING_HISTORY", history or None)):
            if value is not None and evaluation.bind((by_category[key],)):
                optional[key] = value
        mid, oi, history = optional.get("MID_PRICE"), optional.get("OPEN_INTEREST"), optional.get("FUNDING_HISTORY", ())
        missing = tuple(key for key in ("MID_PRICE", "OPEN_INTEREST") if key not in optional)
        if convention == "HYPERLIQUID_HOURLY" and not history:
            missing += ("FUNDING_HISTORY",)

        with localcontext(RISK_CONTEXT):
            mark_oracle = _basis(mark, oracle)
            if abs(mark_oracle) > BPS_LIMIT:
                return unavailable("UNSUPPORTED", "Mark/oracle basis exceeds supported bounds.", ("BASIS",))
            if mid is not None:
                mark_mid, oracle_mid = _basis(mark, mid), _basis(oracle, mid)
                if max(abs(mark_mid), abs(oracle_mid)) > BPS_LIMIT:
                    mark_mid = oracle_mid = None
                    missing += ("ALIGNED_MID_BASIS",)
                    reasons.append("Midpoint basis exceeds supported bounds.")
            else:
                mark_mid = oracle_mid = None
            mark_oracle = mark_oracle.quantize(BPS_QUANTUM, rounding=ROUND_HALF_EVEN)
            if mark_mid is not None:
                mark_mid = mark_mid.quantize(BPS_QUANTUM, rounding=ROUND_HALF_EVEN)
                oracle_mid = oracle_mid.quantize(BPS_QUANTUM, rounding=ROUND_HALF_EVEN)
            average = mean(row.funding_rate for row in history)
            if average is not None:
                average = average.quantize(Decimal("0.000000000000000001"), rounding=ROUND_HALF_EVEN)

        direction = "LONGS_PAY" if rate > 0 else "SHORTS_PAY" if rate < 0 else "FLAT"
        if max(abs(mark_oracle), abs(mark_mid or 0)) >= self._basis_threshold:
            state = "BASIS_STRESSED"
            reasons.append("Signed basis exceeded the configured crowding basis threshold.")
        else:
            state = "FUNDING_POSITIVE" if rate > 0 else "FUNDING_NEGATIVE" if rate < 0 else "NEUTRAL"
        return FundingBasisAdvisory(
            **evaluation.fields(), status="READY", confidence=confidence, state=state,
            funding_rate=rate, funding_interval_seconds=interval, funding_direction=direction,
            funding_convention=convention, mark_price=mark, oracle_price=oracle, midpoint_price=mid,
            mark_oracle_basis_bps=mark_oracle,
            mark_mid_basis_bps=mark_mid, oracle_mid_basis_bps=oracle_mid, open_interest_base=oi,
            history_count=len(history) if convention == "HYPERLIQUID_HOURLY" else None,
            recent_history_mean_rate=average, reasons=tuple(reasons), missing_requirements=missing,
        )
