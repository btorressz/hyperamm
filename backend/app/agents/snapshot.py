"""One coherent observational publication per successful strategy cycle."""
from pydantic import ConfigDict, Field, model_validator

from .config import AgentConfig
from .models import (AgentModel, AgentEvidenceSnapshot, AgentSupervisorDecision,
    RegimeAgentOutput, ToxicFlowAgentOutput, ExecutionQualityAgentOutput,
    LiquidityQualityAgentOutput, PerpCrowdingAgentOutput, PredictiveAdverseSelectionAgentOutput)


class AgentTelemetrySummary(AgentModel):
    version: int = Field(ge=0)
    fill_observations: int = Field(ge=0, le=1000)
    unavailable_markouts: int = Field(ge=0, le=8000)
    evicted_unavailable_markouts: int = Field(ge=0)
    perp_observations: int = Field(ge=0, le=120)
    retained_markout_horizons: int = Field(ge=0, le=8)
    reconcile_cycles: int = Field(ge=0, le=1000)
    tracked_orders: int = Field(ge=0, le=1000)
    unknown_orders: int = Field(ge=0, le=1000)
    rejected_orders: int = Field(ge=0, le=1000)


class AgentSystemSnapshot(AgentModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)
    config: AgentConfig
    evidence: AgentEvidenceSnapshot | None
    regime: RegimeAgentOutput | None
    toxic_flow: ToxicFlowAgentOutput | None
    execution_quality: ExecutionQualityAgentOutput | None
    liquidity_quality: LiquidityQualityAgentOutput | None
    perp_crowding: PerpCrowdingAgentOutput | None
    predictive_adverse_selection: PredictiveAdverseSelectionAgentOutput | None
    supervisor: AgentSupervisorDecision | None
    agent_version: int = Field(ge=0)
    agent_fingerprint: str
    telemetry: AgentTelemetrySummary

    @model_validator(mode="after")
    def coherent_cycle(self):
        if self.supervisor is not None:
            d = self.supervisor
            if self.evidence is None or self.agent_version != d.version or self.agent_fingerprint != d.fingerprint:
                raise ValueError("agent snapshot decision/evidence mismatch")
            for name in ("market", "market_version", "inventory_version", "perp_version", "reference_version"):
                if getattr(self.evidence, name) != getattr(d, name):
                    raise ValueError("agent snapshot upstream cycle mismatch")
            for name in ("regime", "toxic_flow", "execution_quality", "liquidity_quality", "perp_crowding", "predictive_adverse_selection"):
                output = getattr(self, name)
                if output != getattr(d, name) or output is not None and output.evidence_version != self.evidence.version:
                    raise ValueError("agent snapshot output cycle mismatch")
        return self

    @classmethod
    def capture(cls, config, evidence, decision, telemetry, supervisor):
        names = ("regime", "toxic_flow", "execution_quality", "liquidity_quality", "perp_crowding", "predictive_adverse_selection")
        return cls(config=config.model_copy(deep=True), evidence=evidence.model_copy(deep=True) if evidence else None,
            supervisor=decision.model_copy(deep=True) if decision else None,
            **{name: getattr(decision, name).model_copy(deep=True) if decision and getattr(decision, name) else None for name in names},
            agent_version=decision.version if decision else supervisor.version,
            agent_fingerprint=decision.fingerprint if decision else supervisor.fingerprint,
            telemetry=AgentTelemetrySummary(**telemetry.summary()))
