"""Single-market, unit-aware research margin and stress. No ledger or routing effects."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Context, Decimal, ROUND_CEILING, localcontext
from typing import Annotated, Literal

from pydantic import BeforeValidator, ConfigDict, Field, field_validator, model_validator

from app.accounting.config import bounded_exact_decimal
from app.market_data.live_models import Evidence
from app.market_data.market_risk_metadata import MarketFinancialObservation, SourceStatus
from app.market_data.market_universe_contracts import MarketInstrumentIdentity, MarketUniverseMetadata, UtcDatetime, _strict_bool
from app.risk.market_risk_contracts import (
    MarketCollateralIdentity, MarketMarginPolicy, MarketRiskReadiness, RiskFinancialUnit, RiskFingerprint,
    assess_market_risk_readiness,
)
from app.simulation.models import stable_fingerprint

MODEL_VERSION = "phase183c-v1"
ZERO = Decimal(0)
ONE = Decimal(1)
BPS = Decimal(10000)
QUANTUM = Decimal("0.00000001")
RISK_CONTEXT = Context(prec=120, rounding=ROUND_CEILING)


def exact_input(value):
    result = bounded_exact_decimal(value)
    text = format(result, "f")
    return ZERO if result == 0 else Decimal(text.rstrip("0").rstrip(".") if "." in text else text)


RiskDecimal = Annotated[Decimal, BeforeValidator(exact_input), Field(max_digits=30, decimal_places=12)]
RiskMode = Literal["HYPOTHETICAL", "SOURCE_CONSTRAINED"]
MarginMode = Literal["ISOLATED", "STRICT_ISOLATED", "NO_CROSS", "CROSS"]
RiskReason = Literal[
    "RISK_SOURCE_UNAVAILABLE", "RISK_SOURCE_STALE", "RISK_SOURCE_UNSUPPORTED",
    "RISK_UNIT_MISMATCH", "RISK_MARGIN_MODE_UNSUPPORTED", "RISK_LEVERAGE_UNSUPPORTED",
    "RISK_CAPITAL_INSUFFICIENT", "RISK_EXPOSURE_INVALID",
]


class ResearchRiskError(ValueError):
    def __init__(self, reason: RiskReason):
        super().__init__(reason)
        self.reason = reason


class ResearchEvidence(Evidence):
    model_config = ConfigDict(revalidate_instances="always", validate_default=True)


class ValuationAssumption(ResearchEvidence):
    collateral_unit: RiskFinancialUnit
    collateral_per_paper_quote: RiskDecimal = Field(gt=0, le=1_000_000)
    provenance: Literal["FIXED_HYPOTHETICAL_SCENARIO_RATE"] = "FIXED_HYPOTHETICAL_SCENARIO_RATE"


class StressAssumption(ResearchEvidence):
    name: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
    price_shock_bps: RiskDecimal = Field(default=ZERO, gt=-10000, le=100000)
    collateral_loss_bps: RiskDecimal = Field(default=ZERO, ge=0, le=10000)
    capital_reduction_bps: RiskDecimal = Field(default=ZERO, ge=0, le=10000)
    funding_cost_bps: RiskDecimal = Field(default=ZERO, ge=0, le=10000)
    fees_bps: RiskDecimal = Field(default=ZERO, ge=0, le=10000)


class ResearchRiskSettings(ResearchEvidence):
    mode: RiskMode
    margin_mode: MarginMode
    capital_paper_quote: RiskDecimal = Field(gt=0, le=1_000_000_000)
    initial_margin_fraction: RiskDecimal | None = Field(default=None, gt=0, le=1)
    maintenance_margin_fraction: RiskDecimal | None = Field(default=None, gt=0, le=1)
    max_leverage: RiskDecimal | None = Field(default=None, ge=1, le=100)
    leverage: RiskDecimal | None = Field(default=None, ge=1, le=100)
    valuation: ValuationAssumption | None = None
    stresses: tuple[StressAssumption, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_assumptions(self):
        if len({stress.name for stress in self.stresses}) != len(self.stresses):
            raise ValueError("stress names must be unique")
        if self.mode == "HYPOTHETICAL":
            if self.initial_margin_fraction is None or self.maintenance_margin_fraction is None or self.valuation is not None:
                raise ValueError("hypothetical margin requires explicit fractions in PAPER quote")
            if self.maintenance_margin_fraction > self.initial_margin_fraction:
                raise ValueError("maintenance margin exceeds initial margin")
            if self.leverage is not None:
                with localcontext(RISK_CONTEXT):
                    if (self.max_leverage is None or self.leverage > self.max_leverage
                            or self.leverage * self.initial_margin_fraction < ONE):
                        raise ValueError("hypothetical leverage requires a compatible declared ceiling and initial margin")
        elif (any(v is not None for v in (self.initial_margin_fraction, self.maintenance_margin_fraction, self.max_leverage))
              or self.leverage is None or self.leverage != self.leverage.to_integral_value()):
            raise ValueError("source-constrained margin requires integer leverage and source-derived requirements")
        return self


class ResearchRiskModel(ResearchEvidence):
    version: Literal["phase183c-v1"] = MODEL_VERSION
    settings: ResearchRiskSettings
    declaration: MarketMarginPolicy
    readiness: MarketRiskReadiness
    source: MarketFinancialObservation | None
    source_fingerprint: RiskFingerprint | None
    margin_unit: RiskFinancialUnit
    formula: Literal["HYPOTHETICAL_LINEAR", "DOCUMENTED_HYPERLIQUID_TIERS"]
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    _flag = field_validator("execution_eligible", mode="before")(_strict_bool)

    @model_validator(mode="after")
    def validate_binding(self):
        units = self.declaration.financial_units
        if (self.readiness.identity != units.instrument
                or self.readiness.margin_policy_fingerprint != self.declaration.fingerprint()
                or (self.source_fingerprint != (self.source.fingerprint() if self.source else None))
                or (self.source is not None and self.source.metadata != units.metadata)):
            raise ValueError("inconsistent research model evidence")
        if self.settings.mode == "HYPOTHETICAL":
            if self.margin_unit != units.paper_accounting_unit or self.formula != "HYPOTHETICAL_LINEAR":
                raise ValueError("invalid hypothetical model unit")
        elif (self.source is None or self.source.collateral is None or not self.source.margin.tiers
              or self.settings.valuation is None or self.margin_unit != self.settings.valuation.collateral_unit
              or self.margin_unit != self.source.collateral.financial_unit()
              or self.formula != "DOCUMENTED_HYPERLIQUID_TIERS"):
            raise ValueError("invalid source-constrained model evidence")
        return self

    def fingerprint(self):
        return stable_fingerprint(self.model_dump(exclude={"readiness"}))

    @property
    def identity(self):
        return self.declaration.financial_units.instrument


def source_policy_rejection(source: MarketFinancialObservation | None, status: SourceStatus) -> RiskReason | None:
    """Check whether the captured public policy can support the documented formula."""
    if status == "STALE":
        return "RISK_SOURCE_STALE"
    if source is None or source.collateral_status == "UNAVAILABLE":
        return "RISK_SOURCE_UNAVAILABLE"
    if source.margin.mode in {"UNKNOWN", "ISOLATED_UNSPECIFIED"}:
        return "RISK_MARGIN_MODE_UNSUPPORTED"
    if status != "SOURCE_OBSERVED" or source.collateral is None:
        return "RISK_SOURCE_UNAVAILABLE" if status == "UNAVAILABLE" else "RISK_SOURCE_UNSUPPORTED"
    return None


def supported_tier_denomination(source: MarketFinancialObservation) -> bool:
    # The published multi-tier Core schedules specify USDC thresholds.
    # A HIP-3 multi-tier denomination cannot be inferred from collateral alone.
    return len(source.margin.tiers) <= 1 or (
        source.identity.instrument_type == "CORE_PERP" and source.collateral.is_canonical_usdc
    )


def bind_research_model(settings: ResearchRiskSettings, metadata: MarketUniverseMetadata, *,
                        source: MarketFinancialObservation | None, evaluated_at: datetime,
                        max_age_seconds: int) -> ResearchRiskModel:
    settings = ResearchRiskSettings.model_validate(settings)
    if settings.margin_mode == "CROSS":
        raise ResearchRiskError("RISK_MARGIN_MODE_UNSUPPORTED")
    status = "UNAVAILABLE"
    if source is not None:
        source = MarketFinancialObservation.model_validate(source)
        if source.metadata != metadata:
            raise ResearchRiskError("RISK_SOURCE_UNSUPPORTED")
        status = source.status_at(evaluated_at, max_age_seconds)
        if status == "STALE":
            if settings.mode == "SOURCE_CONSTRAINED":
                raise ResearchRiskError("RISK_SOURCE_STALE")
            source = None
        elif source.margin.mode not in {
            "UNKNOWN", "CROSS_ELIGIBLE", "ISOLATED_UNSPECIFIED",
            settings.margin_mode,
        } and settings.margin_mode != "ISOLATED":
            raise ResearchRiskError("RISK_MARGIN_MODE_UNSUPPORTED")

    paper_unit = RiskFinancialUnit(network=metadata.identity.network, kind="HYPOTHETICAL_QUOTE",
                                   symbol="HYPOTHETICAL_QUOTE", provenance="RESEARCH_ASSUMPTION")
    collateral_unit = source.collateral.financial_unit() if source and source.collateral else None
    formula = "HYPOTHETICAL_LINEAR"
    if settings.mode == "SOURCE_CONSTRAINED":
        if reason := source_policy_rejection(source, status):
            raise ResearchRiskError(reason)
        if settings.margin_mode != "ISOLATED" and settings.margin_mode != source.margin.mode:
            raise ResearchRiskError("RISK_MARGIN_MODE_UNSUPPORTED")
        if settings.valuation is None or settings.valuation.collateral_unit != collateral_unit:
            raise ResearchRiskError("RISK_UNIT_MISMATCH")
        if not supported_tier_denomination(source):
            raise ResearchRiskError("RISK_SOURCE_UNSUPPORTED")
        formula = "DOCUMENTED_HYPERLIQUID_TIERS"

    declared = MarketCollateralIdentity(metadata=metadata, metadata_fingerprint=metadata.fingerprint(),
                                        collateral_unit=collateral_unit, paper_accounting_unit=paper_unit)
    policy = MarketMarginPolicy(
        financial_units=declared, margin_mode=settings.margin_mode,
        policy_evidence="HYPOTHETICAL" if settings.mode == "HYPOTHETICAL" else "UNVERIFIED",
        initial_margin_fraction=settings.initial_margin_fraction,
        maintenance_margin_fraction=settings.maintenance_margin_fraction,
        modeled_max_leverage=settings.max_leverage,
    )
    return ResearchRiskModel(
        settings=settings, declaration=policy,
        readiness=assess_market_risk_readiness(policy, evaluated_at=evaluated_at, max_age_seconds=max_age_seconds),
        source=source, source_fingerprint=source.fingerprint() if source else None,
        margin_unit=paper_unit if formula == "HYPOTHETICAL_LINEAR" else collateral_unit, formula=formula,
    )


class ResearchExposure(ResearchEvidence):
    base_instrument: MarketInstrumentIdentity
    quote_unit: RiskFinancialUnit
    mark_paper_quote_per_base: Decimal
    signed_base: Decimal
    absolute_notional: Decimal
    gross_long_notional: Decimal
    gross_short_notional: Decimal
    proposed_bid_notional: Decimal
    proposed_ask_notional: Decimal
    resting_bid_notional: Decimal
    resting_ask_notional: Decimal
    effective_bid_notional: Decimal
    effective_ask_notional: Decimal
    projected_long_base: Decimal
    projected_short_base: Decimal
    inventory_utilization: Decimal
    capital_concentration: Decimal


class Requirements(ResearchEvidence):
    initial: Decimal
    maintenance: Decimal
    tier_lower_bound: Decimal | None = None
    source_max_leverage: int | None = None
    margin_leverage: Decimal | None = None
    leverage_supported: bool = True


class ResearchMargin(ResearchEvidence):
    unit: RiskFinancialUnit
    capital: Decimal
    current: Requirements
    projected_long: Requirements
    projected_short: Requirements
    projected_initial: Decimal
    projected_maintenance: Decimal
    initial_headroom: Decimal
    maintenance_headroom: Decimal
    projected_headroom: Decimal
    projected_utilization: Decimal | None


class StressResult(ResearchEvidence):
    assumptions: StressAssumption
    mark_paper_quote_per_base: Decimal
    adverse_pnl_paper_quote: Decimal
    costs_paper_quote: Decimal
    margin: ResearchMargin
    headroom_deterioration: Decimal
    tier_changed: bool
    feasible: bool


class ResearchRiskSnapshot(ResearchEvidence):
    valuation_time: UtcDatetime
    configuration_fingerprint: RiskFingerprint
    exposure: ResearchExposure
    margin: ResearchMargin
    stresses: tuple[StressResult, ...] = ()
    execution_eligible: Literal[False] = False
    authority: Literal["NONE"] = "NONE"

    _flag = field_validator("execution_eligible", mode="before")(_strict_bool)


def _requirements(model, notional):
    settings, source = model.settings, model.source
    if settings.mode == "HYPOTHETICAL":
        supported = not (settings.leverage is not None and source and source.margin.tiers
                         and settings.leverage > source.margin.tiers[-1].max_leverage)
        return Requirements(initial=(notional * settings.initial_margin_fraction).quantize(QUANTUM),
                            maintenance=(notional * settings.maintenance_margin_fraction).quantize(QUANTUM),
                            leverage_supported=supported)

    tiers = source.margin.tiers
    maintenance = ZERO
    tier = tiers[0]
    # Marginal segments are equivalent to the documented continuous deduction
    # formula. They avoid subtracting two rounded, potentially large amounts.
    for i, current in enumerate(tiers):
        if current.lower_bound > notional:
            break
        tier = current
        end = tiers[i + 1].lower_bound if i + 1 < len(tiers) else notional
        maintenance += (min(notional, end) - tier.lower_bound) / (2 * tier.max_leverage)
    leverage = min(settings.leverage, tier.max_leverage)
    return Requirements(initial=(notional / leverage).quantize(QUANTUM),
                        maintenance=maintenance.quantize(QUANTUM), tier_lower_bound=tier.lower_bound,
                        source_max_leverage=tier.max_leverage, margin_leverage=leverage,
                        leverage_supported=settings.leverage <= tier.max_leverage)


def _margin(model, position, long, short, mark, capital_quote):
    rate = model.settings.valuation.collateral_per_paper_quote if model.settings.valuation else ONE
    capital = capital_quote * rate
    current, bid, ask = (_requirements(model, abs(base) * mark * rate) for base in (position, long, short))
    initial = max(current.initial, bid.initial, ask.initial)
    maintenance = max(current.maintenance, bid.maintenance, ask.maintenance)
    return ResearchMargin(
        unit=model.margin_unit, capital=capital, current=current, projected_long=bid, projected_short=ask,
        projected_initial=initial, projected_maintenance=maintenance, initial_headroom=capital - current.initial,
        maintenance_headroom=capital - current.maintenance, projected_headroom=capital - initial,
        projected_utilization=initial / capital if capital > 0 else None,
    )


def _by_tier(margin):
    return tuple(value.tier_lower_bound for value in (margin.current, margin.projected_long, margin.projected_short))


def opening_feasible(margin):
    return (margin.projected_headroom >= 0 and margin.current.leverage_supported
            and margin.projected_long.leverage_supported and margin.projected_short.leverage_supported)


def evaluate_research_risk(model: ResearchRiskModel, *, mark, position, position_limit, valuation_time,
                           quotes=(), existing=(), net_pnl=ZERO, include_stresses=True):
    """Mark quantities once and use the firewall's KEEP/REPLACE overlap rules."""
    from app.risk.firewall import exposure_metrics

    with localcontext(RISK_CONTEXT):
        try:
            mark, position, limit, pnl = map(bounded_exact_decimal, (mark, position, position_limit, net_pnl))
            if mark <= 0 or limit <= 0 or len(quotes) > 64 or len(existing) > 128:
                raise ValueError("invalid research exposure bounds")
            for order in (*quotes, *existing):
                if (order.side not in {"BID", "ASK"} or bounded_exact_decimal(order.price) <= 0
                        or bounded_exact_decimal(order.size) <= 0):
                    raise ValueError("invalid research order")
            for order in existing:
                bounded_exact_decimal(order.filled_size)
            proposed = exposure_metrics(quotes, position, mark, limit)
            resting = exposure_metrics((), position, mark, limit, existing)
            effective = exposure_metrics(quotes, position, mark, limit, existing)
            long, short = effective.projected_long_base, effective.projected_short_base
            capital = model.settings.capital_paper_quote + pnl
            margin = _margin(model, position, long, short, mark, capital)
            exposure = ResearchExposure(
                base_instrument=model.identity, quote_unit=model.declaration.financial_units.paper_accounting_unit,
                mark_paper_quote_per_base=mark, signed_base=position, absolute_notional=effective.current_position_notional,
                gross_long_notional=max(ZERO, position) * mark + effective.bid_quote_notional,
                gross_short_notional=max(ZERO, -position) * mark + effective.ask_quote_notional,
                proposed_bid_notional=proposed.bid_quote_notional, proposed_ask_notional=proposed.ask_quote_notional,
                resting_bid_notional=resting.bid_quote_notional, resting_ask_notional=resting.ask_quote_notional,
                effective_bid_notional=effective.bid_quote_notional, effective_ask_notional=effective.ask_quote_notional,
                projected_long_base=long, projected_short_base=short, inventory_utilization=effective.inventory_utilization,
                capital_concentration=effective.current_position_notional / model.settings.capital_paper_quote,
            )
            stresses = []
            for shock in model.settings.stresses if include_stresses else ():
                stressed_mark = mark * (ONE + shock.price_shock_bps / BPS)
                # Worst P&L over known position and one-sided projected fills at the reference mark.
                adverse_pnl = min(base * (stressed_mark - mark) for base in (position, long, short))
                costs = max(abs(position), abs(long), abs(short)) * stressed_mark * (shock.funding_cost_bps + shock.fees_bps) / BPS
                haircut = (ONE - shock.collateral_loss_bps / BPS) * (ONE - shock.capital_reduction_bps / BPS)
                stressed_capital = min(capital, ZERO) + max(capital, ZERO) * haircut + adverse_pnl - costs
                stressed = _margin(model, position, long, short, stressed_mark, stressed_capital)
                stresses.append(StressResult(
                    assumptions=shock, mark_paper_quote_per_base=stressed_mark, adverse_pnl_paper_quote=adverse_pnl,
                    costs_paper_quote=costs, margin=stressed, headroom_deterioration=margin.projected_headroom - stressed.projected_headroom,
                    tier_changed=_by_tier(margin) != _by_tier(stressed), feasible=opening_feasible(stressed),
                ))
            return ResearchRiskSnapshot(valuation_time=valuation_time, configuration_fingerprint=model.fingerprint(),
                                        exposure=exposure, margin=margin, stresses=tuple(stresses))
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ResearchRiskError("RISK_EXPOSURE_INVALID") from exc


class PaperRiskFrame(ResearchEvidence):
    sequence: int
    state: Literal["NORMAL", "WIDEN", "REDUCE", "HALT"]
    candidate_quotes: int = Field(ge=0, le=64)
    authorized_quotes: int = Field(ge=0, le=64)
    margin_retired_quotes: bool = False
    projected_headroom: Decimal | None
    decision_reasons: tuple[str, ...] = Field(max_length=16)


class PaperRiskResult(ResearchEvidence):
    version: Literal["phase183d-v1"] = "phase183d-v1"
    model_fingerprint: RiskFingerprint
    frames: tuple[PaperRiskFrame, ...] = Field(min_length=1, max_length=120)
    final_snapshot: ResearchRiskSnapshot | None
    final_snapshot_status: Literal["MODELED", "RISK_EXPOSURE_INVALID"]
    capital_treatment: Literal["SEPARATE_RESEARCH_BUDGET"] = "SEPARATE_RESEARCH_BUDGET"
    authority: Literal["NONE"] = "NONE"
    execution_eligible: Literal[False] = False

    _flag = field_validator("execution_eligible", mode="before")(_strict_bool)


@dataclass
class PaperRiskRun:
    """Run-local evidence collected by the existing PAPER engine."""
    model: ResearchRiskModel
    frames: list[PaperRiskFrame] = field(default_factory=list)
    final: ResearchRiskSnapshot | None = None

    def evidence(self):
        return PaperRiskResult(model_fingerprint=self.model.fingerprint(), frames=tuple(self.frames),
                               final_snapshot=self.final,
                               final_snapshot_status="MODELED" if self.final is not None else "RISK_EXPOSURE_INVALID")
