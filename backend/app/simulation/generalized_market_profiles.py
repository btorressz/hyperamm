"""Admission and deterministic inputs for single-market hypothetical PAPER research."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
from typing import Annotated, Literal

from pydantic import (
    BeforeValidator, ConfigDict, Field, StrictInt, field_validator, model_serializer, model_validator,
)
from pydantic_core import to_json

from app.accounting.config import AccountingConfig, bounded_exact_decimal
from app.accounting.vault import reserved_capital
from app.agents.advisory_contracts import AdvisorySnapshot
from app.agents.config import AgentConfig
from app.amm.asset_policy import apply_asset_research_policy
from app.amm.asset_policy_contracts import AssetAmmResearchPolicy, assess_asset_amm_policy
from app.amm.numeric import executable_distance, quantize_size
from app.market_data.history import MarketPriceHistory
from app.market_data.live_models import Evidence
from app.market_data.market_risk_metadata import MarketFinancialObservation, SourceStatus
from app.market_data.market_universe_contracts import (
    DiscoveryEligibility, MarketInstrumentIdentity, MarketUniverseMetadata, Network, UtcDatetime, _strict_bool,
    evaluate_discovery,
)
from app.references.models import GENERALIZED_REFERENCE_SOURCE, SYNTHETIC_AGREEMENT
from app.risk.firewall import RiskFirewallConfig
from app.risk.limits import validate_quotes
from app.risk.models import RiskStatus
from app.risk.market_risk_engine import (
    PaperRiskResult, PaperRiskRun, ResearchRiskError, ResearchRiskModel, ResearchRiskSettings,
    bind_research_model, evaluate_research_risk, opening_feasible,
)
from app.strategy.inventory import build_inventory_state
from app.strategy.models import StrategyConfig
from app.strategy.quote_engine import QuoteEngine

from .config import SimulationConfig
from .market_profiles import GeneralizedPrecisionError, round_level, validate_price
from .models import Fingerprint, SimulationDataset, SimulationResult, stable_fingerprint
from .scenarios import ScenarioName, generate_scenario

PROFILE_VERSION = "phase182-v1"
MAX_FRAMES = 120
MAX_RESPONSE_BYTES = 2_000_000
DECIMAL_CONTEXT = Context(prec=28)
LIMITATIONS = (
    "Local single-market PAPER simulation using a user-supplied hypothetical reference price.",
    "Market prices, references, depth, fills and funding are synthetic.",
    "Quote amounts use hypothetical accounting units and full-notional reservation.",
    "Venue fees, funding conventions, collateral, margin and settlement are unverified.",
    "Metadata and PAPER admission grant no exchange execution authority.",
)
FUNDING_SCENARIOS = {ScenarioName.POSITIVE_FUNDING_STRESS, ScenarioName.NEGATIVE_FUNDING_STRESS}


def exact_decimal(value):
    result = bounded_exact_decimal(value)
    if not result:
        return Decimal(0)
    text = format(result, "f")
    return Decimal(text.rstrip("0").rstrip(".") if "." in text else text)


ResearchDecimal = Annotated[Decimal, BeforeValidator(exact_decimal), Field(max_digits=20, decimal_places=12)]
Reason = Literal[
    "ADMITTED", "METADATA_UNAVAILABLE", "METADATA_STALE", "MARKET_DELISTED", "NETWORK_MISMATCH",
    "IDENTITY_MISMATCH", "PROFILE_UNSUPPORTED", "PRICE_UNREPRESENTABLE",
    "SIZE_UNREPRESENTABLE", "SCENARIO_INFEASIBLE", "FUNDING_MODEL_UNSUPPORTED",
    "CONFIGURATION_INVALID", "PROFILE_FINGERPRINT_MISMATCH", "METADATA_FINGERPRINT_MISMATCH",
    "CONFIGURATION_FINGERPRINT_MISMATCH", "CATALOG_FINGERPRINT_MISMATCH", "RISK_FINGERPRINT_MISMATCH",
    "RISK_SOURCE_UNAVAILABLE", "RISK_SOURCE_STALE", "RISK_SOURCE_UNSUPPORTED", "RISK_UNIT_MISMATCH",
    "RISK_MARGIN_MODE_UNSUPPORTED", "RISK_LEVERAGE_UNSUPPORTED", "RISK_CAPITAL_INSUFFICIENT",
    "RISK_EXPOSURE_INVALID", "ASSET_POLICY_FINGERPRINT_MISMATCH", "ADVISORY_FINGERPRINT_MISMATCH",
    "ADVISORY_UNAVAILABLE", "ADVISORY_STALE", "ORDER_NOTIONAL_TOO_SMALL",
]
REASONS = {
    "ADMITTED": ("admission", "The captured scenario is eligible for local hypothetical PAPER research."),
    "METADATA_UNAVAILABLE": ("metadata", "Current official metadata for this instrument is unavailable."),
    "METADATA_STALE": ("freshness", "The metadata snapshot is stale or has an invalid observation time."),
    "MARKET_DELISTED": ("listing", "The instrument is delisted."),
    "NETWORK_MISMATCH": ("network", "The selected instrument belongs to a different discovery network."),
    "IDENTITY_MISMATCH": ("identity", "The selected canonical instrument is absent from the current catalog."),
    "PROFILE_UNSUPPORTED": ("profile_version", "Select the supported generalized PAPER profile version."),
    "PRICE_UNREPRESENTABLE": ("price_precision", "The reference or scenario price ladder exceeds instrument precision."),
    "SIZE_UNREPRESENTABLE": ("quantity_precision", "The order, inventory or scenario depth rounds below a positive lot."),
    "SCENARIO_INFEASIBLE": ("scenario_preflight", "The scenario cannot produce feasible quotes within the PAPER bounds."),
    "FUNDING_MODEL_UNSUPPORTED": ("funding_assumptions", "Choose a hypothetical funding interval shorter than the scenario frame count."),
    "CONFIGURATION_INVALID": ("request", "Check canonical identity, bounds and the required hypothetical assumptions."),
    "PROFILE_FINGERPRINT_MISMATCH": ("profile_fingerprint", "The profile changed or failed verification. Check eligibility again."),
    "METADATA_FINGERPRINT_MISMATCH": ("metadata_fingerprint", "The metadata observation changed. Check eligibility again."),
    "CATALOG_FINGERPRINT_MISMATCH": ("catalog_fingerprint", "The discovery catalog changed. Check eligibility again."),
    "RISK_FINGERPRINT_MISMATCH": ("research_risk_fingerprint", "The modeled settings or source observation changed. Check eligibility again."),
    "RISK_SOURCE_UNAVAILABLE": ("financial_source", "The current public collateral or margin observation is unavailable."),
    "RISK_SOURCE_STALE": ("financial_source", "The captured financial source expired or its discovery generation was retired."),
    "RISK_SOURCE_UNSUPPORTED": ("financial_source", "The observed margin schedule or collateral is unsupported for this model."),
    "RISK_UNIT_MISMATCH": ("risk_valuation", "An explicit valuation matching the observed collateral identity is required."),
    "RISK_MARGIN_MODE_UNSUPPORTED": ("margin_mode", "The selected mode cannot be modeled for this market and single-market PAPER scope."),
    "RISK_LEVERAGE_UNSUPPORTED": ("research_leverage", "The selected leverage exceeds a supported margin tier limit."),
    "RISK_CAPITAL_INSUFFICIENT": ("research_capital", "The modeled capital cannot support the smallest generated opening quote."),
    "RISK_EXPOSURE_INVALID": ("research_exposure", "The modeled exposure or stress falls outside supported financial bounds."),
    "CONFIGURATION_FINGERPRINT_MISMATCH": ("configuration_fingerprint", "The scenario or economic assumptions changed. Check eligibility again."),
    "ASSET_POLICY_FINGERPRINT_MISMATCH": ("asset_policy_fingerprint", "The asset research policy changed. Check eligibility again."),
    "ADVISORY_FINGERPRINT_MISMATCH": ("advisory_snapshot_fingerprint", "The advisory snapshot does not match this research policy and market."),
    "ADVISORY_UNAVAILABLE": ("advisory_snapshot_fingerprint", "The server has no retained advisory snapshot for this fingerprint."),
    "ADVISORY_STALE": ("advisory_snapshot_fingerprint", "The advisory snapshot expired. Refresh the advisory evidence."),
    "ORDER_NOTIONAL_TOO_SMALL": ("minimum_order_notional", "A normalized quote is below the selected minimum order notional."),
}
UNAVAILABLE_REASONS = {"METADATA_UNAVAILABLE", "METADATA_STALE", "RISK_SOURCE_UNAVAILABLE", "RISK_SOURCE_STALE",
                       "ADVISORY_UNAVAILABLE", "ADVISORY_STALE"}


class PaperContract(Evidence):
    model_config = ConfigDict(revalidate_instances="always", validate_default=True)
    profile_version: Literal["phase182-v1"] = PROFILE_VERSION

    @model_serializer(mode="wrap")
    def omit_unset_extensions(self, serialize):
        payload = serialize(self)
        for name in ("research_risk", "risk_model", "risk_source", "risk_source_status", "asset_amm_policy"):
            if payload.get(name) is None:
                payload.pop(name, None)
        return payload


class HypotheticalEconomics(Evidence):
    model_config = ConfigDict(revalidate_instances="always", validate_default=True)
    model: Literal["HYPOTHETICAL_LINEAR"]
    maker_fee_bps: ResearchDecimal = Field(default=Decimal("0"), ge=0, le=100)
    taker_fee_bps: ResearchDecimal = Field(default=Decimal("0"), ge=0, le=100)
    funding_interval_seconds: StrictInt | None = Field(default=None, ge=1, le=120)


class PaperEvidenceBoundary(Evidence):
    model_config = ConfigDict(revalidate_instances="always", validate_default=True)
    version: Literal["phase182g-v1"] = "phase182g-v1"
    references: Literal["phase182g-v1:synthetic-scenario"] = GENERALIZED_REFERENCE_SOURCE
    reference_clock: Literal["SIMULATION_FRAME_TIME"] = "SIMULATION_FRAME_TIME"
    order_book: Literal["SYNTHETIC_DEPTH"] = "SYNTHETIC_DEPTH"
    accounting_units: Literal["HYPOTHETICAL_QUOTE"] = "HYPOTHETICAL_QUOTE"
    capital_reservation: Literal["SIMULATED_FULL_NOTIONAL"] = "SIMULATED_FULL_NOTIONAL"
    fees: Literal["HYPOTHETICAL_MAKER_TAKER"] = "HYPOTHETICAL_MAKER_TAKER"
    funding: Literal["HYPOTHETICAL_SCHEDULED"] = "HYPOTHETICAL_SCHEDULED"
    exchange_economics: Literal["UNVERIFIED"] = "UNVERIFIED"
    risk_readiness: Literal["SINGLE_MARKET_RESEARCH_ONLY"] = "SINGLE_MARKET_RESEARCH_ONLY"


PAPER_EVIDENCE = PaperEvidenceBoundary()


class PaperProposal(PaperContract):
    profile_version: Literal["phase182-v1"]
    identity: MarketInstrumentIdentity
    simulated_reference_price: ResearchDecimal = Field(gt=0, le=Decimal("10000000"))
    minimum_order_notional: ResearchDecimal = Field(default=Decimal("100"), gt=0, le=2000)
    synthetic_top_depth_quote: ResearchDecimal = Field(default=Decimal("18000"), gt=0, le=100_000_000)
    scenario: ScenarioName
    frames: StrictInt = Field(default=40, ge=2, le=MAX_FRAMES)
    trace_max_points: StrictInt = Field(default=40, ge=0, le=MAX_FRAMES)
    economics: HypotheticalEconomics
    research_risk: ResearchRiskSettings | None = None
    asset_amm_policy: AssetAmmResearchPolicy | None = None

    @field_validator("asset_amm_policy", mode="before")
    @classmethod
    def parse_asset_policy(cls, value):
        # FastAPI decodes JSON to Python first. The strict contract accepts
        # wire strings for enum values and timestamps in JSON mode.
        return AssetAmmResearchPolicy.model_validate_json(to_json(value)) if isinstance(value, dict) else value


class PaperFingerprintBinding(Evidence):
    model_config = ConfigDict(revalidate_instances="always")
    metadata_fingerprint: Fingerprint
    profile_fingerprint: Fingerprint
    configuration_fingerprint: Fingerprint
    catalog_fingerprint: Fingerprint | None = None
    research_risk_fingerprint: Fingerprint | None = None
    asset_policy_fingerprint: Fingerprint | None = None

    @model_serializer(mode="wrap")
    def omit_unset_extensions(self, serialize):
        payload = serialize(self)
        for name in ("research_risk_fingerprint", "asset_policy_fingerprint"):
            if payload.get(name) is None:
                payload.pop(name, None)
        return payload


class PaperRunRequest(PaperProposal):
    expected: PaperFingerprintBinding


def _profile_fingerprint(metadata, reference, depth, economics):
    return stable_fingerprint({
        "profile_version": PROFILE_VERSION,
        "metadata": metadata.model_dump(exclude={"observed_at", "universe_index"}),
        "simulated_reference_price": reference,
        "synthetic_top_depth_quote": depth,
        "reference_source": "USER_SUPPLIED_SYNTHETIC",
        "evidence_boundary": PAPER_EVIDENCE,
        "economics": economics,
    })


class GeneralizedMarketProfile(PaperContract):
    metadata: MarketUniverseMetadata
    discovery: DiscoveryEligibility
    stable_key: str = Field(max_length=140)
    exchange_coin: str = Field(max_length=97)
    metadata_fingerprint: Fingerprint
    profile_fingerprint: Fingerprint
    simulated_reference_price: ResearchDecimal = Field(gt=0, le=Decimal("10000000"))
    synthetic_top_depth_quote: ResearchDecimal = Field(gt=0, le=100_000_000)
    economics: HypotheticalEconomics
    reference_source: Literal["USER_SUPPLIED_SYNTHETIC"] = "USER_SUPPLIED_SYNTHETIC"
    model_compatibility: Literal["HYPOTHETICAL_LINEAR_ONLY"] = "HYPOTHETICAL_LINEAR_ONLY"
    evidence_boundary: PaperEvidenceBoundary
    paper_eligibility: Literal["REQUIRES_ADMISSION"] = "REQUIRES_ADMISSION"
    limitations: tuple[str, ...] = Field(default=LIMITATIONS, max_length=len(LIMITATIONS))
    authority: Literal["NONE"] = "NONE"
    execution_eligible: Literal[False] = False
    _execution_flag = field_validator("execution_eligible", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def verify_source_binding(self):
        if (self.limitations != LIMITATIONS
                or self.stable_key != self.metadata.identity.stable_key
                or self.exchange_coin != self.metadata.identity.exchange_coin
                or self.discovery.identity != self.metadata.identity
                or self.discovery.metadata_fingerprint != self.metadata_fingerprint
                or self.metadata_fingerprint != self.metadata.fingerprint()
                or self.profile_fingerprint != _profile_fingerprint(
                    self.metadata, self.simulated_reference_price, self.synthetic_top_depth_quote, self.economics)):
            raise ValueError("generalized profile evidence mismatch")
        return self

    @property
    def market(self) -> str:
        return self.stable_key

    @property
    def sz_decimals(self) -> int:
        return self.metadata.sz_decimals

    def normalize_quotes(self, quotes, center, *, preflight=False, minimum_order_notional=None, side_liquidity=None):
        rounded = []
        used = set()
        if side_liquidity is not None:
            side_liquidity = quantize_size(side_liquidity, self.sz_decimals)
        remaining = {"BID": side_liquidity, "ASK": side_liquidity}
        for quote in quotes:
            size = quote.size
            if side_liquidity is not None:
                size = min(size, remaining[quote.side])
                # The existing transforms can retain one lot when a reduction
                # falls below it. Retire that lot on the asset-aware path.
                if quote.pre_agent_size is not None and quote.agent_size_multiplier is not None:
                    size = min(size, quote.pre_agent_size * quote.agent_size_multiplier)
                if quote.pre_risk_size is not None and quote.risk_size_multiplier is not None:
                    size = min(size, quote.pre_risk_size * quote.risk_size_multiplier)
            price, size = round_level(quote.price, size, self.sz_decimals, up=quote.side == "ASK")
            key = (quote.side, price)
            if size == 0 or key in used:
                if preflight:
                    raise GeneralizedPrecisionError("SIZE_UNREPRESENTABLE" if size == 0 else "PRICE_UNREPRESENTABLE")
                # Later inventory and risk transforms may retire feasible levels.
                continue
            if minimum_order_notional is not None and price * size < minimum_order_notional:
                if preflight:
                    raise GeneralizedPrecisionError("ORDER_NOTIONAL_TOO_SMALL")
                continue
            if side_liquidity is not None:
                remaining[quote.side] -= size
            used.add(key)
            rounded.append(quote.model_copy(update={
                "price": price, "size": size, "distance_bps": executable_distance(price, center),
            }))
        if preflight and {quote.side for quote in rounded} != {"BID", "ASK"}:
            raise GeneralizedPrecisionError("SIZE_UNREPRESENTABLE")
        return rounded

    def evidence(self):
        return {"research_market": self.market, "market_profile_version": self.profile_version,
                "market_profile_fingerprint": self.profile_fingerprint,
                "metadata_source": self.metadata.metadata_source, "metadata_status": self.metadata.metadata_status}


def candidate(metadata: MarketUniverseMetadata, discovery: DiscoveryEligibility,
              proposal: PaperProposal) -> GeneralizedMarketProfile:
    if metadata.identity != proposal.identity:
        raise ValueError("generalized profile source identity mismatch")
    return GeneralizedMarketProfile(
        metadata=metadata, discovery=discovery,
        stable_key=metadata.identity.stable_key, exchange_coin=metadata.identity.exchange_coin,
        metadata_fingerprint=metadata.fingerprint(), simulated_reference_price=proposal.simulated_reference_price,
        synthetic_top_depth_quote=proposal.synthetic_top_depth_quote, economics=proposal.economics,
        evidence_boundary=PAPER_EVIDENCE,
        profile_fingerprint=_profile_fingerprint(metadata, proposal.simulated_reference_price,
                                                 proposal.synthetic_top_depth_quote, proposal.economics),
    )


class PaperAdmission(PaperContract):
    identity: MarketInstrumentIdentity | None
    status: Literal["ELIGIBLE", "REJECTED", "UNAVAILABLE"]
    reason: Reason
    checks: tuple[str, ...] = Field(max_length=1)
    explanation: str = Field(max_length=180)
    evaluated_at: UtcDatetime
    valid_until: UtcDatetime | None
    profile: GeneralizedMarketProfile | None
    binding: PaperFingerprintBinding | None
    risk_model: ResearchRiskModel | None = None
    risk_source: MarketFinancialObservation | None = None
    risk_source_status: SourceStatus | None = None
    limitations: tuple[str, ...] = Field(default=LIMITATIONS, max_length=len(LIMITATIONS))
    scope: Literal["LOCAL_PAPER_ONLY"] = "LOCAL_PAPER_ONLY"
    authority: Literal["NONE"] = "NONE"
    execution_eligible: Literal[False] = False
    _execution_flag = field_validator("execution_eligible", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def verify_decision(self):
        status = ("ELIGIBLE" if self.reason == "ADMITTED" else
                  "UNAVAILABLE" if self.reason in UNAVAILABLE_REASONS else "REJECTED")
        check, explanation = REASONS[self.reason]
        if (self.status != status or self.explanation != explanation or self.limitations != LIMITATIONS
                or self.checks != (() if status == "ELIGIBLE" else (check,))):
            raise ValueError("inconsistent PAPER admission decision")
        if self.profile is not None and self.profile.metadata.identity != self.identity:
            raise ValueError("PAPER admission profile identity mismatch")
        if ((self.risk_model is not None and self.risk_model.identity != self.identity)
                or (self.risk_source is not None and self.risk_source.identity != self.identity)):
            raise ValueError("PAPER research risk identity mismatch")
        if status == "ELIGIBLE":
            if (self.profile is None or self.binding is None or self.valid_until is None
                    or not self.profile.discovery.discovery_eligible
                    or self.profile.discovery.evaluated_at != self.evaluated_at
                    or self.profile.metadata.metadata_status != "EXCHANGE_VERIFIED"
                    or self.profile.metadata.listed is not True
                    or self.profile.metadata.observed_at is None
                    or not self.profile.metadata.observed_at <= self.evaluated_at < self.valid_until
                    <= self.profile.metadata.observed_at + timedelta(days=1)
                    or self.binding.metadata_fingerprint != self.profile.metadata_fingerprint
                    or self.binding.profile_fingerprint != self.profile.profile_fingerprint
                    or self.binding.research_risk_fingerprint != (
                        self.risk_model.fingerprint() if self.risk_model is not None else None
                    )):
                raise ValueError("missing or inconsistent admission evidence")
        elif self.binding is not None or self.valid_until is not None:
            raise ValueError("rejected admission cannot bind execution inputs")
        return self


def decision(identity, evaluated_at, reason, *, profile=None, binding=None, valid_until=None, **risk_evidence):
    check, explanation = REASONS[reason]
    status = ("ELIGIBLE" if reason == "ADMITTED" else
              "UNAVAILABLE" if reason in UNAVAILABLE_REASONS else "REJECTED")
    return PaperAdmission(identity=identity, status=status, reason=reason, explanation=explanation,
                          checks=() if status == "ELIGIBLE" else (check,), evaluated_at=evaluated_at,
                          valid_until=valid_until, profile=profile, binding=binding, **risk_evidence)


@dataclass(frozen=True)
class PreparedScenario:
    dataset: SimulationDataset
    strategy: StrategyConfig
    agents: AgentConfig
    risk: RiskFirewallConfig
    simulation: SimulationConfig


def baseline_strategy(market: str, precision: int, reference: Decimal, minimum_order_notional: Decimal) -> StrategyConfig:
    minimum = quantize_size(minimum_order_notional / reference, precision)
    liquidity = quantize_size(minimum_order_notional * 12 / reference, precision)
    soft = quantize_size(minimum_order_notional * 35 / reference, precision)
    hard = quantize_size(minimum_order_notional * 70 / reference, precision)
    if minimum <= 0 or not liquidity < soft < hard:
        raise GeneralizedPrecisionError("SIZE_UNREPRESENTABLE")
    quote_reserve = Decimal("300000")
    return StrategyConfig(
        market=market, size_precision=precision, levels_per_side=4,
        # Internal transforms use the finest allowed decimal grid. Executable
        # prices are rounded using their own magnitude before risk and matching.
        tick_size=Decimal(1).scaleb(precision - 6), virtual_quote_reserve=quote_reserve,
        virtual_base_reserve=quote_reserve / reference, base_order_size=minimum,
        total_liquidity=liquidity, soft_inventory_limit_base=soft, hard_inventory_limit_base=hard,
        size_tolerance=Decimal(1).scaleb(-precision) / 10,
    )


def _build_scenario(proposal, profile):
    precision, reference = profile.sz_decimals, profile.simulated_reference_price
    strategy = baseline_strategy(profile.market, precision, reference, proposal.minimum_order_notional)
    hard = strategy.hard_inventory_limit_base
    risk = RiskFirewallConfig(max_projected_long_base=hard, max_projected_short_base=hard)
    if proposal.asset_amm_policy is not None:
        strategy = apply_asset_research_policy(strategy, proposal.asset_amm_policy, metadata=profile.metadata)
        target, limit = strategy.target_inventory_base, strategy.hard_inventory_limit_base
        # The existing absolute cap and the target-relative policy both apply.
        with localcontext(Context(prec=80)):
            long_limit = quantize_size(min(hard, limit, limit + target), precision)
            short_limit = quantize_size(min(hard, limit, limit - target), precision)
        risk = RiskFirewallConfig(
            max_projected_long_base=long_limit, max_projected_short_base=short_limit,
        )
        if not -risk.max_projected_short_base < target < risk.max_projected_long_base:
            raise ValueError("inventory target is outside the PAPER exposure limit")
    economics = profile.economics
    simulation = SimulationConfig(
        max_frames=proposal.frames, record_trace=proposal.trace_max_points > 0,
        trace_max_points=min(proposal.frames, proposal.trace_max_points),
        accounting=AccountingConfig(
            paper_fee_model_enabled=bool(economics.maker_fee_bps or economics.taker_fee_bps),
            paper_maker_fee_bps=economics.maker_fee_bps, paper_taker_fee_bps=economics.taker_fee_bps,
            paper_funding_accounting_enabled=economics.funding_interval_seconds is not None,
            paper_funding_interval_seconds=economics.funding_interval_seconds or 3600,
        ),
    )
    dataset = generate_scenario(proposal.scenario, frames=proposal.frames, market=profile.market,
                                generalized_profile=profile)
    return PreparedScenario(dataset, strategy, AgentConfig(), risk, simulation)


def _preflight(prepared, profile, risk_model, *, minimum_order_notional=None):
    strategy = prepared.strategy
    history = MarketPriceHistory()
    engine = QuoteEngine()
    limits = RiskStatus(max_order_size=strategy.total_liquidity)
    for index, frame in enumerate(prepared.dataset.frames):
        history.add_snapshot(frame.market)
        flat = build_inventory_state(
            market=profile.market, position=Decimal(0), target=strategy.target_inventory_base,
            soft_limit=strategy.soft_inventory_limit_base, source="PAPER", updated_at=frame.timestamp,
            stale=False, version=0,
        )
        _, _, quotes, inventory, _, _ = engine.generate_perp_market_adaptive(
            strategy, frame.market, flat, history, frame.perp_context,
        )
        rounded = profile.normalize_quotes(
            quotes, inventory.reservation_price, preflight=True, minimum_order_notional=minimum_order_notional,
            side_liquidity=strategy.total_liquidity if minimum_order_notional is not None else None,
        )
        validate_quotes(rounded, frame.market, limits)
        if minimum_order_notional is not None and index == 0:
            if (sum(q.size for q in rounded if q.side == "BID") > prepared.risk.max_projected_long_base
                    or sum(q.size for q in rounded if q.side == "ASK") > prepared.risk.max_projected_short_base):
                raise ResearchRiskError("RISK_EXPOSURE_INVALID")
            capital = prepared.simulation.initial_equity_quote * prepared.simulation.accounting.max_capital_utilization
            if reserved_capital(Decimal(0), frame.perp_context.mark_price, rounded) > capital:
                raise ResearchRiskError("RISK_CAPITAL_INSUFFICIENT")
        if risk_model is not None:
            inputs = dict(mark=frame.perp_context.mark_price, position=Decimal(0),
                          position_limit=strategy.hard_inventory_limit_base, valuation_time=frame.timestamp)
            evaluate_research_risk(risk_model, quotes=rounded, include_stresses=index == 0, **inputs)
            if index == 0:
                minimum = tuple(min((quote for quote in rounded if quote.side == side), key=lambda quote: quote.size)
                                for side in ("BID", "ASK"))
                margin = evaluate_research_risk(risk_model, quotes=minimum, include_stresses=False, **inputs).margin
                if not (margin.projected_long.leverage_supported and margin.projected_short.leverage_supported):
                    raise ResearchRiskError("RISK_LEVERAGE_UNSUPPORTED")
                if not opening_feasible(margin):
                    raise ResearchRiskError("RISK_CAPITAL_INSUFFICIENT")


def advisory_rejection(policy, metadata, catalog_fingerprint, risk_fingerprint, evaluated_at, evidence):
    if evidence is None:
        return "ADVISORY_UNAVAILABLE"
    snapshot, expiry = evidence
    context = snapshot.context
    if (snapshot.fingerprint() != policy.advisory_snapshot_fingerprint
            or context.metadata != metadata or context.catalog_fingerprint != catalog_fingerprint
            or context.evaluated_at > policy.declared_at
            or context.risk_model_fingerprint not in (None, risk_fingerprint)):
        return "ADVISORY_FINGERPRINT_MISMATCH"
    if expiry <= evaluated_at:
        return "ADVISORY_STALE"
    try:
        snapshot.validate_at(as_of=evaluated_at)
    except ValueError:
        return "ADVISORY_STALE"
    return None


def assess(proposal: PaperProposal, metadata: MarketUniverseMetadata | None, *,
           network: Network, evaluated_at: datetime, max_age_seconds: int,
           metadata_current: bool = True, expected: PaperFingerprintBinding | None = None,
           catalog_fingerprint: str | None = None, catalog_valid_until: datetime | None = None,
           risk_source: MarketFinancialObservation | None = None,
           advisory_evidence: tuple[AdvisorySnapshot, datetime] | None = None):
    """Use a server-owned observation and clock. Client input contains assumptions only."""
    from . import version

    proposal = PaperProposal.model_validate(proposal)
    identity = proposal.identity
    profile = None
    risk_evidence = {}

    def reject(reason):
        return decision(identity, evaluated_at, reason, profile=profile, **risk_evidence), None

    if identity.network != network:
        return reject("NETWORK_MISMATCH")
    if metadata is None:
        return reject("IDENTITY_MISMATCH" if metadata_current else "METADATA_UNAVAILABLE")
    metadata = MarketUniverseMetadata.model_validate(metadata)
    if metadata.identity != identity:
        return reject("IDENTITY_MISMATCH")
    discovery = evaluate_discovery(metadata, evaluated_at=evaluated_at, max_age_seconds=max_age_seconds)
    profile = candidate(metadata, discovery, proposal)
    if discovery.reason == "NOT_LISTED":
        return reject("MARKET_DELISTED")
    if not discovery.discovery_eligible or not metadata_current:
        return reject("METADATA_STALE" if discovery.reason in
                      {"FUTURE_TIMESTAMP", "STALE_METADATA", "DISCOVERABLE"} else "METADATA_UNAVAILABLE")
    valid_until = metadata.observed_at + timedelta(seconds=max_age_seconds)
    if catalog_valid_until is not None:
        valid_until = min(valid_until, catalog_valid_until)
    if evaluated_at >= valid_until:
        return reject("METADATA_STALE")
    if expected is not None:
        expected = PaperFingerprintBinding.model_validate(expected)
        if expected.metadata_fingerprint != profile.metadata_fingerprint:
            return reject("METADATA_FINGERPRINT_MISMATCH")
        if expected.catalog_fingerprint != catalog_fingerprint:
            return reject("CATALOG_FINGERPRINT_MISMATCH")
        if expected.profile_fingerprint != profile.profile_fingerprint:
            return reject("PROFILE_FINGERPRINT_MISMATCH")
    risk_model = None
    if proposal.research_risk is not None:
        risk_evidence = {"risk_source_status": "UNAVAILABLE"}
        if risk_source is not None and risk_source.identity == identity:
            risk_evidence = {"risk_source": risk_source, "risk_source_status": risk_source.status_at(evaluated_at, max_age_seconds)}
        try:
            risk_model = bind_research_model(proposal.research_risk, metadata, source=risk_source,
                                             evaluated_at=evaluated_at, max_age_seconds=max_age_seconds)
        except ResearchRiskError as exc:
            return reject(exc.reason)
        if risk_model.source is not None:
            valid_until = min(valid_until, risk_model.source.valid_until(max_age_seconds))
    risk_fingerprint = risk_model.fingerprint() if risk_model is not None else None
    if expected is not None and expected.research_risk_fingerprint != risk_fingerprint:
        return reject("RISK_FINGERPRINT_MISMATCH")
    policy = proposal.asset_amm_policy
    policy_fingerprint = None
    if policy is not None:
        if policy.identity != identity:
            return reject("NETWORK_MISMATCH" if policy.identity.network != network else "IDENTITY_MISMATCH")
        if policy.metadata_fingerprint != profile.metadata_fingerprint:
            return reject("METADATA_FINGERPRINT_MISMATCH")
        if catalog_valid_until is None or catalog_fingerprint is None or policy.catalog_fingerprint != catalog_fingerprint:
            return reject("CATALOG_FINGERPRINT_MISMATCH")
        if policy.simulated_reference_price != proposal.simulated_reference_price or policy.declared_at > evaluated_at:
            return reject("CONFIGURATION_INVALID")
        draft = assess_asset_amm_policy(policy, evaluated_at=evaluated_at, max_age_seconds=max_age_seconds)
        if draft.status != "RESEARCH_DRAFT":
            return reject("CONFIGURATION_INVALID")
        if policy.research_risk_fingerprint is not None and policy.research_risk_fingerprint != risk_fingerprint:
            return reject("RISK_FINGERPRINT_MISMATCH")
        if policy.advisory_snapshot_fingerprint is not None:
            reason = advisory_rejection(policy, metadata, catalog_fingerprint, risk_fingerprint, evaluated_at,
                                        advisory_evidence)
            if reason is not None:
                return reject(reason)
            valid_until = min(valid_until, advisory_evidence[1])
        policy_fingerprint = draft.policy_fingerprint
    if expected is not None and expected.asset_policy_fingerprint != policy_fingerprint:
        return reject("ASSET_POLICY_FINGERPRINT_MISMATCH")
    if proposal.scenario in FUNDING_SCENARIOS:
        interval = proposal.economics.funding_interval_seconds
        if interval is None or interval >= proposal.frames:
            return reject("FUNDING_MODEL_UNSUPPORTED")
    if ((proposal.scenario == ScenarioName.FLASH_MOVE and proposal.frames < 3)
            or (proposal.scenario == ScenarioName.LIQUIDITY_SHOCK and proposal.frames < 5)):
        return reject("SCENARIO_INFEASIBLE")
    with localcontext(DECIMAL_CONTEXT):
        try:
            valid_price = validate_price(profile.simulated_reference_price, profile.sz_decimals)
        except (ArithmeticError, ValueError):
            valid_price = False
        if not valid_price:
            return reject("PRICE_UNREPRESENTABLE")
        try:
            prepared = _build_scenario(proposal, profile)
            binding = PaperFingerprintBinding(
                metadata_fingerprint=profile.metadata_fingerprint, profile_fingerprint=profile.profile_fingerprint,
                catalog_fingerprint=catalog_fingerprint, research_risk_fingerprint=risk_fingerprint,
                asset_policy_fingerprint=policy_fingerprint,
                configuration_fingerprint=stable_fingerprint({
                    "profile_fingerprint": profile.profile_fingerprint, "proposal": proposal,
                    "catalog_fingerprint": catalog_fingerprint,
                    "engine_version": version.SIMULATION_ENGINE_VERSION, "dataset": prepared.dataset.fingerprint,
                    "strategy": prepared.strategy, "agents": prepared.agents, "risk": prepared.risk,
                    "simulation": prepared.simulation,
                    **({"research_risk_fingerprint": risk_fingerprint} if risk_fingerprint is not None else {}),
                    **({"asset_policy_fingerprint": policy_fingerprint} if policy_fingerprint is not None else {}),
                }),
            )
            if expected is not None and expected != binding:
                return reject("CONFIGURATION_FINGERPRINT_MISMATCH")
            if policy is None:
                _preflight(prepared, profile, risk_model)
            else:
                _preflight(prepared, profile, risk_model, minimum_order_notional=proposal.minimum_order_notional)
        except ResearchRiskError as exc:
            return reject(exc.reason)
        except GeneralizedPrecisionError as exc:
            return reject(exc.reason)
        except (ArithmeticError, ValueError):
            return reject("SCENARIO_INFEASIBLE")
    return decision(identity, evaluated_at, "ADMITTED", profile=profile, binding=binding,
                    valid_until=valid_until, risk_model=risk_model,
                    risk_source_status=risk_evidence.get("risk_source_status")), prepared


class PaperRejected(ValueError):
    def __init__(self, admission):
        self.admission = admission
        super().__init__(admission.reason)


class GeneralizedPaperResult(PaperContract):
    admission: PaperAdmission
    proposal: PaperProposal
    result: SimulationResult
    result_fingerprint: Fingerprint
    research_risk: PaperRiskResult | None = None
    started_at: UtcDatetime
    execution_mode: Literal["PAPER"] = "PAPER"
    simulated: Literal[True] = True
    _simulation_flag = field_validator("simulated", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def verify_result(self):
        profile = self.admission.profile
        result = self.result
        model = self.admission.risk_model
        risk_result = self.research_risk
        binding = self.admission.binding
        policy = self.proposal.asset_amm_policy
        if binding is not None and (binding.asset_policy_fingerprint != (policy.fingerprint() if policy else None)
                or (policy is not None and (
                    policy.metadata_fingerprint != binding.metadata_fingerprint
                    or policy.catalog_fingerprint != binding.catalog_fingerprint
                    or policy.simulated_reference_price != self.proposal.simulated_reference_price
                    or policy.declared_at > self.admission.evaluated_at
                    or policy.research_risk_fingerprint not in (None, binding.research_risk_fingerprint)
                ))):
            raise ValueError("PAPER asset policy result mismatch")
        if ((self.proposal.research_risk is None) != (model is None)
                or (risk_result is None) != (model is None)
                or (model is not None and (
                    self.proposal.research_risk != model.settings
                    or risk_result.model_fingerprint != model.fingerprint()
                    or len(risk_result.frames) != result.metrics.frame_count
                    or (risk_result.final_snapshot is not None and (
                        risk_result.final_snapshot.configuration_fingerprint != model.fingerprint()
                        or risk_result.final_snapshot.exposure.base_instrument != model.identity
                        or result.vault is None
                        or risk_result.final_snapshot.exposure.signed_base != result.vault.position_base
                    ))
                ))):
            raise ValueError("PAPER research risk result mismatch")
        if (self.admission.status != "ELIGIBLE" or profile is None
                or not self.admission.evaluated_at <= self.started_at < self.admission.valid_until
                or self.proposal.identity != self.admission.identity
                or self.proposal.simulated_reference_price != profile.simulated_reference_price
                or self.proposal.synthetic_top_depth_quote != profile.synthetic_top_depth_quote
                or self.proposal.economics != profile.economics
                or result.simulated is not True or result.research_market != profile.stable_key
                or result.market_profile_version != PROFILE_VERSION
                or result.market_profile_fingerprint != profile.profile_fingerprint
                or result.scenario != self.proposal.scenario or result.metrics.frame_count != self.proposal.frames
                or len(result.trace) > self.proposal.trace_max_points or result.vault is None
                or any(point.reference_confidence not in {SYNTHETIC_AGREEMENT, "DEGRADED", "CONFLICTED", "INSUFFICIENT"}
                       for point in result.trace)
                or result.vault.market != profile.stable_key or result.vault.mode != "PAPER"
                or result.vault.simulated is not True
                or any(fill.get("execution_mode", "PAPER") != "PAPER"
                       or fill.get("source") != "SIMULATED PAPER FILL" or fill.get("market") != profile.stable_key
                       for fill in result.fills)
                or any(entry.simulated is not True or entry.market != profile.stable_key
                       for entry in result.accounting_ledger)
                or self.result_fingerprint != _result_fingerprint(binding, self.proposal, result, risk_result)):
            raise ValueError("generalized PAPER result evidence mismatch")
        return self


def _result_fingerprint(binding, proposal, result, research_risk):
    components = (binding.configuration_fingerprint, proposal, result)
    return stable_fingerprint(components if research_risk is None else (*components, research_risk))


async def execute_paper(engine, *, proposal, metadata, network, max_age_seconds, expected,
                        catalog_valid_until=None, catalog_guard=None, risk_source=None, advisory_evidence=None):
    expected = PaperFingerprintBinding.model_validate(expected)
    if expected.catalog_fingerprint is not None and (catalog_guard is None or catalog_valid_until is None):
        raise ValueError("catalog-bound PAPER worker requires captured server generation")
    admission, prepared = assess(proposal, metadata, network=network, evaluated_at=datetime.now(timezone.utc),
                                 max_age_seconds=max_age_seconds, expected=expected,
                                 catalog_fingerprint=expected.catalog_fingerprint, catalog_valid_until=catalog_valid_until,
                                 risk_source=risk_source, advisory_evidence=advisory_evidence)
    if prepared is None:
        raise PaperRejected(admission)
    started_at = datetime.now(timezone.utc)
    if started_at >= admission.valid_until or (catalog_guard is not None and not catalog_guard()):
        reason = "RISK_SOURCE_STALE" if admission.risk_model and admission.risk_model.source else "METADATA_STALE"
        if (advisory_evidence is not None and proposal.asset_amm_policy is not None
                and proposal.asset_amm_policy.advisory_snapshot_fingerprint is not None
                and started_at >= advisory_evidence[1]):
            reason = "ADVISORY_STALE"
        raise PaperRejected(decision(proposal.identity, started_at,
                                     reason, profile=admission.profile))
    risk_run = PaperRiskRun(admission.risk_model) if admission.risk_model is not None else None
    with localcontext(DECIMAL_CONTEXT):
        result = await engine.run(
            dataset=prepared.dataset, strategy_config=prepared.strategy, agent_config=prepared.agents,
            risk_config=prepared.risk, simulation_config=prepared.simulation, scenario=proposal.scenario.value,
            generalized_profile=admission.profile,
            **({"paper_risk_run": risk_run} if risk_run is not None else {}),
            **({"minimum_order_notional": proposal.minimum_order_notional} if proposal.asset_amm_policy else {}),
        )
    if proposal.asset_amm_policy is not None and result.strategy_fingerprint != stable_fingerprint(prepared.strategy):
        raise ValueError("PAPER worker strategy fingerprint mismatch")
    risk_result = risk_run.evidence() if risk_run is not None else None
    return GeneralizedPaperResult(
        admission=admission, proposal=proposal, result=result,
        started_at=started_at, research_risk=risk_result,
        result_fingerprint=_result_fingerprint(admission.binding, proposal, result, risk_result),
    )
