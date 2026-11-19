"""Admission and deterministic inputs for single-market hypothetical PAPER research."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, localcontext
from typing import Annotated, Literal

from pydantic import (
    BeforeValidator, ConfigDict, Field, StrictInt, field_validator, model_validator,
)

from app.accounting.config import AccountingConfig, bounded_exact_decimal
from app.agents.config import AgentConfig
from app.amm.numeric import executable_distance, quantize_size
from app.market_data.history import MarketPriceHistory
from app.market_data.live_models import Evidence
from app.market_data.market_universe_contracts import (
    DiscoveryEligibility, MarketInstrumentIdentity, MarketUniverseMetadata, Network, UtcDatetime, _strict_bool,
    evaluate_discovery,
)
from app.references.models import GENERALIZED_REFERENCE_SOURCE, SYNTHETIC_AGREEMENT
from app.risk.firewall import RiskFirewallConfig
from app.risk.limits import validate_quotes
from app.risk.models import RiskStatus
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
    "CONFIGURATION_FINGERPRINT_MISMATCH", "CATALOG_FINGERPRINT_MISMATCH",
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
    "CONFIGURATION_FINGERPRINT_MISMATCH": ("configuration_fingerprint", "The scenario or economic assumptions changed. Check eligibility again."),
}
UNAVAILABLE_REASONS = {"METADATA_UNAVAILABLE", "METADATA_STALE"}


class PaperContract(Evidence):
    model_config = ConfigDict(revalidate_instances="always", validate_default=True)
    profile_version: Literal["phase182-v1"] = PROFILE_VERSION


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


class PaperFingerprintBinding(Evidence):
    model_config = ConfigDict(revalidate_instances="always")
    metadata_fingerprint: Fingerprint
    profile_fingerprint: Fingerprint
    configuration_fingerprint: Fingerprint
    catalog_fingerprint: Fingerprint | None = None


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

    def normalize_quotes(self, quotes, center, *, preflight=False):
        rounded = []
        used = set()
        for quote in quotes:
            price, size = round_level(quote.price, quote.size, self.sz_decimals, up=quote.side == "ASK")
            key = (quote.side, price)
            if size == 0 or key in used:
                if preflight:
                    raise GeneralizedPrecisionError("SIZE_UNREPRESENTABLE" if size == 0 else "PRICE_UNREPRESENTABLE")
                # Later inventory and risk transforms may retire feasible levels.
                continue
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
                    or self.binding.profile_fingerprint != self.profile.profile_fingerprint):
                raise ValueError("missing or inconsistent admission evidence")
        elif self.binding is not None or self.valid_until is not None:
            raise ValueError("rejected admission cannot bind execution inputs")
        return self


def decision(identity, evaluated_at, reason, *, profile=None, binding=None, valid_until=None):
    check, explanation = REASONS[reason]
    status = ("ELIGIBLE" if reason == "ADMITTED" else
              "UNAVAILABLE" if reason in UNAVAILABLE_REASONS else "REJECTED")
    return PaperAdmission(identity=identity, status=status, reason=reason, explanation=explanation,
                          checks=() if status == "ELIGIBLE" else (check,), evaluated_at=evaluated_at,
                          valid_until=valid_until, profile=profile, binding=binding)


@dataclass(frozen=True)
class PreparedScenario:
    dataset: SimulationDataset
    strategy: StrategyConfig
    agents: AgentConfig
    risk: RiskFirewallConfig
    simulation: SimulationConfig


def _build_scenario(proposal, profile):
    precision, reference = profile.sz_decimals, profile.simulated_reference_price
    minimum = quantize_size(proposal.minimum_order_notional / reference, precision)
    liquidity = quantize_size(proposal.minimum_order_notional * 12 / reference, precision)
    soft = quantize_size(proposal.minimum_order_notional * 35 / reference, precision)
    hard = quantize_size(proposal.minimum_order_notional * 70 / reference, precision)
    if minimum <= 0 or not liquidity < soft < hard:
        raise GeneralizedPrecisionError("SIZE_UNREPRESENTABLE")
    quote_reserve = Decimal("300000")
    strategy = StrategyConfig(
        market=profile.market, size_precision=precision, levels_per_side=4,
        # Internal transforms use the finest allowed decimal grid. Executable
        # prices are rounded using their own magnitude before risk and matching.
        tick_size=Decimal(1).scaleb(precision - 6), virtual_quote_reserve=quote_reserve,
        virtual_base_reserve=quote_reserve / reference, base_order_size=minimum,
        total_liquidity=liquidity, soft_inventory_limit_base=soft, hard_inventory_limit_base=hard,
        size_tolerance=Decimal(1).scaleb(-precision) / 10,
    )
    risk = RiskFirewallConfig(max_projected_long_base=hard, max_projected_short_base=hard)
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


def _preflight(prepared, profile):
    strategy = prepared.strategy
    history = MarketPriceHistory()
    engine = QuoteEngine()
    limits = RiskStatus(max_order_size=strategy.total_liquidity)
    for frame in prepared.dataset.frames:
        history.add_snapshot(frame.market)
        flat = build_inventory_state(
            market=profile.market, position=Decimal(0), target=Decimal(0),
            soft_limit=strategy.soft_inventory_limit_base, source="PAPER", updated_at=frame.timestamp,
            stale=False, version=0,
        )
        _, _, quotes, inventory, _, _ = engine.generate_perp_market_adaptive(
            strategy, frame.market, flat, history, frame.perp_context,
        )
        rounded = profile.normalize_quotes(quotes, inventory.reservation_price, preflight=True)
        validate_quotes(rounded, frame.market, limits)


def assess(proposal: PaperProposal, metadata: MarketUniverseMetadata | None, *,
           network: Network, evaluated_at: datetime, max_age_seconds: int,
           metadata_current: bool = True, expected: PaperFingerprintBinding | None = None,
           catalog_fingerprint: str | None = None, catalog_valid_until: datetime | None = None):
    """Use a server-owned observation and clock. Client input contains assumptions only."""
    from . import version

    proposal = PaperProposal.model_validate(proposal)
    identity = proposal.identity
    profile = None

    def reject(reason):
        return decision(identity, evaluated_at, reason, profile=profile), None

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
                catalog_fingerprint=catalog_fingerprint,
                configuration_fingerprint=stable_fingerprint({
                    "profile_fingerprint": profile.profile_fingerprint, "proposal": proposal,
                    "catalog_fingerprint": catalog_fingerprint,
                    "engine_version": version.SIMULATION_ENGINE_VERSION, "dataset": prepared.dataset.fingerprint,
                    "strategy": prepared.strategy, "agents": prepared.agents, "risk": prepared.risk,
                    "simulation": prepared.simulation,
                }),
            )
            if expected is not None and expected != binding:
                return reject("CONFIGURATION_FINGERPRINT_MISMATCH")
            _preflight(prepared, profile)
        except GeneralizedPrecisionError as exc:
            return reject(exc.reason)
        except (ArithmeticError, ValueError):
            return reject("SCENARIO_INFEASIBLE")
    return decision(identity, evaluated_at, "ADMITTED", profile=profile, binding=binding,
                    valid_until=valid_until), prepared


class PaperRejected(ValueError):
    def __init__(self, admission):
        self.admission = admission
        super().__init__(admission.reason)


class GeneralizedPaperResult(PaperContract):
    admission: PaperAdmission
    proposal: PaperProposal
    result: SimulationResult
    result_fingerprint: Fingerprint
    started_at: UtcDatetime
    execution_mode: Literal["PAPER"] = "PAPER"
    simulated: Literal[True] = True
    _simulation_flag = field_validator("simulated", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def verify_result(self):
        profile = self.admission.profile
        result = self.result
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
                or self.result_fingerprint != stable_fingerprint((self.admission.binding.configuration_fingerprint, self.proposal, result))):
            raise ValueError("generalized PAPER result evidence mismatch")
        return self


async def execute_paper(engine, *, proposal, metadata, network, max_age_seconds, expected,
                        catalog_valid_until=None, catalog_guard=None):
    expected = PaperFingerprintBinding.model_validate(expected)
    if expected.catalog_fingerprint is not None and (catalog_guard is None or catalog_valid_until is None):
        raise ValueError("catalog-bound PAPER worker requires captured server generation")
    admission, prepared = assess(proposal, metadata, network=network, evaluated_at=datetime.now(timezone.utc),
                                 max_age_seconds=max_age_seconds, expected=expected,
                                 catalog_fingerprint=expected.catalog_fingerprint, catalog_valid_until=catalog_valid_until)
    if prepared is None:
        raise PaperRejected(admission)
    started_at = datetime.now(timezone.utc)
    if started_at >= admission.valid_until or (catalog_guard is not None and not catalog_guard()):
        raise PaperRejected(decision(proposal.identity, started_at,
                                     "METADATA_STALE", profile=admission.profile))
    with localcontext(DECIMAL_CONTEXT):
        result = await engine.run(
            dataset=prepared.dataset, strategy_config=prepared.strategy, agent_config=prepared.agents,
            risk_config=prepared.risk, simulation_config=prepared.simulation, scenario=proposal.scenario.value,
            generalized_profile=admission.profile,
        )
    return GeneralizedPaperResult(
        admission=admission, proposal=proposal, result=result,
        started_at=started_at,
        result_fingerprint=stable_fingerprint((admission.binding.configuration_fingerprint, proposal, result)),
    )
