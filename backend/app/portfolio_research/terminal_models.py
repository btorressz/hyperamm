"""Compact presentation contracts. Requests contain configuration, never receipts."""
from typing import Literal
from pydantic import AwareDatetime, Field, StrictInt, model_validator
from app.market_data.live_models import FinancialDecimal, NonnegativeDecimal
from app.research_replay.models import Fingerprint
from app.execution.research import PaperExecutionAssumptions
from .models import (PortfolioEvidence, PortfolioAnalysisRequest, PortfolioStressRequest,
    PortfolioStressScenario, PortfolioTemporalReport, PortfolioAccountingReport,
    PortfolioExposureReport, PortfolioRiskReport, PortfolioStressMetrics,
    PortfolioStressRiskTransition, AnalysisEvidence)


class TerminalRequest(PortfolioAnalysisRequest):
    contract_version: Literal["phase175-terminal-v1"] = "phase175-terminal-v1"
    mode: Literal["RUN", "ANALYZE", "STRESS"]
    scenario: PortfolioStressScenario | None = None

    @model_validator(mode="after")
    def mode_boundary(self):
        if self.mode == "STRESS":
            self.stress_request()
        elif self.scenario is not None:
            raise ValueError("stress assumptions require STRESS mode")
        return self

    def stress_request(self):
        return PortfolioStressRequest(config=self.config, config_fingerprint=self.config_fingerprint,
            risk_policy=self.risk_policy, scenario=self.scenario)


class ChartPoint(PortfolioEvidence):
    sequence: StrictInt = Field(ge=1, le=3000)
    timestamp: AwareDatetime
    equity_quote: FinancialDecimal
    pnl_quote: FinancialDecimal
    drawdown_fraction: NonnegativeDecimal


class ChartEvidence(AnalysisEvidence):
    status: Literal["AVAILABLE", "UNAVAILABLE"]
    reason: str = Field(max_length=100)
    source_count: StrictInt = Field(ge=0, le=1500)
    sampled: bool
    methodology: Literal["NATIVE_ALIGNED_EXTREMA_BUCKETS_V1"] = "NATIVE_ALIGNED_EXTREMA_BUCKETS_V1"
    analysis_fingerprint: Fingerprint
    accounting_fingerprint: Fingerprint
    temporal_fingerprint: Fingerprint
    native_evidence_fingerprints: tuple[Fingerprint, ...] = Field(min_length=1, max_length=3)
    equity_series_fingerprint: Fingerprint | None
    points: tuple[ChartPoint, ...] = Field(max_length=120)

    @model_validator(mode="after")
    def eligible_projection(self):
        p = self.points
        if self.status == "AVAILABLE":
            if (not self.equity_series_fingerprint or len(p) < 2 or p[0].sequence != 1 or
                    p[-1].sequence != self.source_count or self.sampled != (len(p) < self.source_count) or
                    any(a.sequence >= b.sequence or a.timestamp >= b.timestamp for a, b in zip(p, p[1:]))):
                raise ValueError("invalid bounded chart projection")
        elif p:
            raise ValueError("unavailable chart must not contain points")
        return self


class TerminalMarketSource(PortfolioEvidence):
    market: Literal["BTC", "ETH", "SOL"]
    market_profile_fingerprint: Fingerprint
    dataset_fingerprint: Fingerprint
    run_fingerprint: Fingerprint
    result_fingerprint: Fingerprint
    accounting_fingerprint: Fingerprint
    receipt_fingerprint: Fingerprint
    execution_assumptions: PaperExecutionAssumptions


class TerminalLeg(PortfolioEvidence):
    analysis_fingerprint: Fingerprint
    bundle_fingerprint: Fingerprint
    status: Literal["COMPLETED"] = "COMPLETED"
    temporal: PortfolioTemporalReport
    accounting: PortfolioAccountingReport
    exposure: PortfolioExposureReport
    risk: PortfolioRiskReport
    charts: ChartEvidence
    markets: tuple[TerminalMarketSource, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def source_bindings(self):
        c, t, a = self.charts, self.temporal, self.accounting
        if (c.analysis_fingerprint != self.analysis_fingerprint or
                c.temporal_fingerprint != t.evidence_fingerprint or c.accounting_fingerprint != a.evidence_fingerprint or
                c.native_evidence_fingerprints != tuple(k.native_evidence_fingerprint for k in t.clocks) or
                tuple(m.receipt_fingerprint for m in self.markets) != tuple(k.market_receipt_fingerprint for k in t.clocks)):
            raise ValueError("terminal chart or market source binding mismatch")
        if c.status == "AVAILABLE" and (t.classification != "MODELED_ALIGNED" or a.drawdown is None or
                c.equity_series_fingerprint != a.drawdown.equity_series_fingerprint or
                c.points[-1].equity_quote != a.equity_quote or c.points[-1].pnl_quote != a.pnl_quote):
            raise ValueError("terminal chart eligibility or financial endpoint mismatch")
        return self


class TerminalResult(AnalysisEvidence):
    contract_version: Literal["phase175-terminal-v1"] = "phase175-terminal-v1"
    mode: Literal["RUN", "ANALYZE", "STRESS"]
    config_fingerprint: Fingerprint
    request_fingerprint: Fingerprint
    source_result_fingerprint: Fingerprint
    scenario_fingerprint: Fingerprint | None
    baseline: TerminalLeg
    stressed: TerminalLeg | None
    metrics: PortfolioStressMetrics | None
    risk_transition: PortfolioStressRiskTransition | None
    limitations: tuple[str, ...]
    simulated: Literal[True] = True
    execution_mode: Literal["PAPER"] = "PAPER"
    read_only: Literal[True] = True
    authority: Literal["NONE"] = "NONE"

    @model_validator(mode="after")
    def mode_projection(self):
        stress = self.mode == "STRESS"
        if any((value is not None) != stress for value in
                (self.stressed, self.scenario_fingerprint, self.metrics, self.risk_transition)):
            raise ValueError("terminal mode projection mismatch")
        return self
