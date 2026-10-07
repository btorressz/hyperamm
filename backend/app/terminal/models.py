"""Versioned observation contracts. No execution or accounting authority."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from app.market_data.models import MarketSnapshot
from app.strategy.models import StrategyState
from app.amm.models import QuoteLevel, VirtualPool
from app.execution.models import StrategyOrder, Fill
from app.accounting.models import VaultSnapshot
from app.references.models import ReferenceSnapshot, ReferenceConsensus
from app.risk.models import RiskStatus

TERMINAL_CONTRACT_VERSION = "phase12-v1"


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    HALTED = "HALTED"
    UNAVAILABLE = "UNAVAILABLE"


class SubsystemHealth(Observation):
    status: HealthStatus
    reason: str


class SystemHealthState(Observation):
    status: HealthStatus
    observational: Literal[True] = True
    subsystems: dict[str, SubsystemHealth]


class TerminalSnapshot(Observation):
    contract_version: Literal["phase12-v1"] = TERMINAL_CONTRACT_VERSION
    process_id: str
    session_id: str
    sequence: int = Field(ge=1)
    emitted_at: AwareDatetime
    market: MarketSnapshot
    strategy: StrategyState
    fair_value: Decimal | None
    pool: VirtualPool | None
    strategy_quotes: list[QuoteLevel]
    agent_quotes: list[QuoteLevel]
    authorized_quotes: list[QuoteLevel]
    quotes: list[QuoteLevel]  # Backward-compatible final/authorized stage.
    inventory: dict[str, Any] | None
    market_adaptation: dict[str, Any] | None
    perp_context: dict[str, Any] | None
    references: ReferenceSnapshot | None
    reference_consensus: ReferenceConsensus | None
    agents: dict[str, Any]
    agent_events: list[dict[str, Any]]
    risk_firewall: dict[str, Any]
    risk_authorization: dict[str, Any]
    risk_events: list[dict[str, Any]]
    projected_exposure: dict[str, Any] | None
    pnl_drawdown: dict[str, Any] | None
    vault: VaultSnapshot
    accounting: dict[str, Any]
    risk: RiskStatus
    orders: list[StrategyOrder]
    fills: list[Fill]
    venue_reconciliation: dict[str, Any]
    reconciliation: list[dict[str, Any]]
    system_health: SystemHealthState
    execution_summary: dict[str, Any]
    diagnostics: dict[str, bool]


class TerminalHistoryPoint(Observation):
    sequence: int = Field(ge=1)
    timestamp: AwareDatetime
    mid_price: Decimal | None = None
    fair_value: Decimal | None = None
    strategy_reference_price: Decimal | None = None
    mark_price: Decimal | None = None
    oracle_price: Decimal | None = None
    consensus_price: Decimal | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    position_base: Decimal | None = None
    inventory_ratio: Decimal | None = None
    risk_state: str
    agent_regime: str | None = None
    equity: Decimal | None = None
    peak_equity: Decimal | None = None
    net_pnl: Decimal | None = None
    drawdown_pct: Decimal | None = None
    capital_utilization: Decimal | None = None
    simulated: bool
    execution_mode: str


class EventCategory(StrEnum):
    STRATEGY = "STRATEGY"
    MARKET = "MARKET"
    REFERENCES = "REFERENCES"
    AGENTS = "AGENTS"
    RISK = "RISK"
    EXECUTION = "EXECUTION"
    ACCOUNTING = "ACCOUNTING"
    SYSTEM = "SYSTEM"


class TerminalEvent(Observation):
    event_id: str
    timestamp: AwareDatetime
    category: EventCategory
    previous_state: str | None = None
    state: str | None = None
    message: str
    reference: str | None = None
    version: int | None = None
    simulated: bool
