"""Strict bounded wire contracts. Client hashes identify evidence, never authenticate it."""
from typing import Annotated, Literal
from decimal import Decimal
import re
from pydantic import AwareDatetime, Field, StrictInt, StrictBool, model_validator, PlainSerializer, BeforeValidator, field_validator
from app.market_data.live_models import Evidence, financial_decimal
from app.market_data.live_stream_models import LiveStreamSnapshot
from app.simulation.market_profiles import ResearchPerpMarketId
from app.simulation.models import ResearchMarketAssumptions, Fingerprint, BoundedText
from app.simulation.scenarios import ScenarioName
from app.simulation.research_vault import ResearchProposal, ResearchVaultConfig

def input_decimal(value):
    if isinstance(value, str):
        if len(value) > 80 or not re.fullmatch(r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d{1,3})?', value):
            raise ValueError('invalid bounded financial string')
        value = Decimal(value)
    return financial_decimal(value)


FinancialDecimal = Annotated[Decimal, BeforeValidator(input_decimal), PlainSerializer(lambda v: format(v, 'f'), return_type=str, when_used='json')]
ComparisonStatus = Literal['COMPARABLE', 'PARTIAL', 'NOT_COMPARABLE', 'UNAVAILABLE']
# Outputs can exceed input bounds for extreme relative differences; remain Decimal strings.
OutputDecimal = Annotated[Decimal, Field(allow_inf_nan=False), PlainSerializer(lambda v: format(v, 'f'), return_type=str, when_used='json')]


class ResearchPerformanceContext(Evidence):
    frame_count: StrictInt = Field(ge=2, le=5000)
    session_pnl: FinancialDecimal
    return_pct: FinancialDecimal
    realized_pnl: FinancialDecimal
    unrealized_pnl: FinancialDecimal
    max_drawdown_pct: FinancialDecimal = Field(ge=0)
    fill_count: StrictInt = Field(ge=0, le=1000000)
    quoted_notional: FinancialDecimal = Field(ge=0)
    filled_notional: FinancialDecimal = Field(ge=0)
    fill_activity_ratio: FinancialDecimal | None
    mean_spread_capture_bps: FinancialDecimal | None
    mean_mature_markout_bps: FinancialDecimal | None
    adverse_fill_rate: FinancialDecimal | None
    ending_inventory_base: FinancialDecimal
    max_inventory_utilization: FinancialDecimal
    risk_halt_fraction: FinancialDecimal = Field(ge=0, le=1)
    risk_state_counts: dict[Literal['NORMAL', 'WIDEN', 'REDUCE', 'HALT'], Annotated[int, Field(strict=True, ge=0, le=5000)]]
    fees_quote: FinancialDecimal | None = None
    funding_quote: FinancialDecimal | None = None

    @model_validator(mode='after')
    def counts(self):
        if sum(self.risk_state_counts.values()) != self.frame_count:
            raise ValueError('risk counts do not match simulated frame count')
        return self


class ResearchAccountingProvenance(Evidence):
    research_config_version: Literal['phase14-v1']
    selected_preset_id: Annotated[str, Field(max_length=64)] | None
    selected_preset_version: Annotated[str, Field(max_length=32)] | None
    normalized_config: ResearchVaultConfig
    config_fingerprint: Fingerprint
    customized: StrictBool

    @field_validator('normalized_config', mode='before')
    @classmethod
    def exact_config_values(cls, value):
        data = value.model_dump() if isinstance(value, ResearchVaultConfig) else value
        if isinstance(data, dict):
            for key in ('initial_equity_quote', 'paper_maker_fee_bps', 'paper_taker_fee_bps', 'max_capital_utilization'):
                if key in data:
                    input_decimal(data[key])
        return value

    @model_validator(mode='after')
    def provenance(self):
        expected = ResearchProposal(config=self.normalized_config, selected_preset_id=self.selected_preset_id).provenance()
        if any(getattr(self, k) != expected[k] for k in ('config_fingerprint', 'selected_preset_version', 'customized')):
            raise ValueError('inconsistent research configuration provenance')
        return self


class ResearchEvidenceSummary(Evidence):
    engine_version: Annotated[str, Field(pattern=r'^[a-zA-Z0-9._-]{1,64}$')]
    research_market: ResearchPerpMarketId
    market_profile_version: Literal['phase146-v1'] | None
    market_profile_fingerprint: Fingerprint | None
    metadata_source: Literal['PINNED_RESEARCH_FIXTURE', 'OFFICIAL_SDK_NATIVE_META'] | None
    metadata_status: Literal['DEMO_PROFILE', 'EXCHANGE_VERIFIED'] | None
    run_fingerprint: Fingerprint
    dataset_fingerprint: Fingerprint
    strategy_fingerprint: Fingerprint
    scenario: ScenarioName
    simulated: Literal[True]
    assumptions: ResearchMarketAssumptions | None
    performance: ResearchPerformanceContext
    research_configuration: ResearchAccountingProvenance | None = None

    @field_validator('simulated', mode='before')
    @classmethod
    def paper_flag(cls, value):
        if value is not True:
            raise ValueError('research evidence requires explicit simulated true')
        return value

    @model_validator(mode='after')
    def identities(self):
        if self.assumptions is not None:
            a = self.assumptions
            if (a.market, a.scenario, a.dataset_fingerprint, a.market_profile_version, a.market_profile_fingerprint, a.frame_count) != (
                self.research_market, self.scenario.value, self.dataset_fingerprint, self.market_profile_version,
                self.market_profile_fingerprint, self.performance.frame_count):
                raise ValueError('inconsistent research evidence identities')
        if (self.market_profile_version is None) != (self.market_profile_fingerprint is None):
            raise ValueError('incomplete research profile evidence')
        if (self.metadata_status, self.metadata_source) not in ((None, None),
            ('DEMO_PROFILE', 'PINNED_RESEARCH_FIXTURE'), ('EXCHANGE_VERIFIED', 'OFFICIAL_SDK_NATIVE_META')):
            raise ValueError('inconsistent research metadata provenance')
        return self


class ResearchMarketComparisonRequest(Evidence):
    market: ResearchPerpMarketId
    research: ResearchEvidenceSummary


class ObservedMarketEvidence(Evidence):
    snapshot: LiveStreamSnapshot
    acquisition_gap_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    bid_depth_base: OutputDecimal | None = None
    ask_depth_base: OutputDecimal | None = None
    depth_level_count: StrictInt = Field(ge=0, le=5)
    depth_measurement_method: Literal['TOP_5_LEVELS_PER_SIDE_BASE'] = 'TOP_5_LEVELS_PER_SIDE_BASE'
    book_eligible: StrictBool
    context_eligible: StrictBool
    funding_convention: Literal['NATIVE_RAW_HOURLY_RATE_EVENT_TIME_UNKNOWN'] = 'NATIVE_RAW_HOURLY_RATE_EVENT_TIME_UNKNOWN'


class ComparisonMetric(Evidence):
    metric_name: Literal['midpoint', 'best_bid', 'best_ask', 'mark_price', 'oracle_price', 'spread_quote',
        'spread_bps', 'funding_rate', 'bid_depth_base', 'ask_depth_base', 'open_interest_base']
    observed_value: OutputDecimal | None
    research_assumed_value: OutputDecimal | None
    absolute_difference: OutputDecimal | None
    difference_bps: OutputDecimal | None
    unit: Literal['quote/base', 'quote', 'bps', 'raw rate', 'base']
    comparison_status: ComparisonStatus
    reason: BoundedText


class ComparisonProvenance(Evidence):
    comparison_fingerprint: Fingerprint
    research_trust: Literal['STRUCTURALLY_VALIDATED_CLIENT_SUPPLIED_NOT_AUTHENTICATED'] = 'STRUCTURALLY_VALIDATED_CLIENT_SUPPLIED_NOT_AUTHENTICATED'
    observer_instance_id: str
    connection_generation: StrictInt = Field(ge=0)
    research_frame_timestamp: AwareDatetime | None
    l2_source_timestamp: AwareDatetime | None
    l2_observed_at: AwareDatetime | None
    perp_observed_at: AwareDatetime | None
    perp_event_time: Literal['UNKNOWN'] = 'UNKNOWN'


class ComparisonExplainability(Evidence):
    completeness: Literal['COMPLETE_FOR_SUPPORTED_METRICS', 'PARTIAL', 'INSUFFICIENT', 'UNAVAILABLE']
    interpretation: Literal['CROSS_CONTEXT_DESCRIPTIVE_ONLY'] = 'CROSS_CONTEXT_DESCRIPTIVE_ONLY'
    available_metrics: tuple[str, ...]
    missing_metrics: tuple[str, ...]
    statements: tuple[str, ...]


class MarketResearchComparisonResult(Evidence):
    contract_version: Literal['phase154-v1'] = 'phase154-v1'
    market: ResearchPerpMarketId
    read_only: Literal[True] = True
    generated_at: AwareDatetime
    comparison_status: ComparisonStatus
    research: ResearchEvidenceSummary
    observed: ObservedMarketEvidence
    metrics: tuple[ComparisonMetric, ...]
    explainability: ComparisonExplainability
    provenance: ComparisonProvenance
    limitations: tuple[str, ...]
