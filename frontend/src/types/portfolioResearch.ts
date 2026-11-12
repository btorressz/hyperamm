export type Market = "BTC" | "ETH" | "SOL";
export type TemporalClass =
  | "MODELED_ALIGNED"
  | "FINAL_ONLY"
  | "INCOMPARABLE"
  | "UNAVAILABLE";
export type Decision = "NORMAL" | "WARN" | "REDUCE" | "HALT";
export type StressKind =
  | "CORRELATED_SELLOFF"
  | "BTC_LED_VOLATILITY"
  | "LIQUIDITY_SHOCK"
  | "FUNDING_STRESS"
  | "ORACLE_DEGRADATION"
  | "CONCENTRATION_STRESS";
export type Mode = "RUN" | "ANALYZE" | "STRESS";
export type RiskLimits = {
  max_gross_exposure_quote: string;
  max_abs_net_exposure_quote: string;
  max_session_loss_quote: string;
  max_drawdown_fraction: string;
  max_capital_utilization: string;
  max_inventory_concentration: string;
  modeled_leverage_ceiling: string;
};
export type RiskPolicy = {
  warning_ratio: string;
  reduction_ratio: string;
  missing_critical_evidence?: "BLOCKED";
};
export type Execution = {
  mode: "BASELINE" | "MODELED_CROSSING";
  order_latency_ms: number;
  cancel_latency_ms: number;
  slippage_bps: string;
  depth_sensitive: boolean;
  allow_partial_fills: boolean;
  participation_rate: string;
  max_fill_fraction: string;
};
export type StressScenario = {
  scenario_type: StressKind;
  selected_markets: Market[];
  onset_frame: number;
  duration_frames: number;
  recovery_profile: "STEP_WINDOW" | "LINEAR_TO_BASELINE";
  assumptions: Record<string, unknown>;
};
export type PortfolioDraft = {
  budget: { total_equity_quote: string; minimum_reserve_quote: string };
  allocations: { market: Market; allocated_equity_quote: string }[];
  risk_limits: RiskLimits;
  risk_policy: RiskPolicy;
  strategy: {
    amm_model: "CONSTANT_PRODUCT" | "CONCENTRATED";
    levels_per_side: number;
    max_distance_bps: string;
    base_order_size: string;
    total_liquidity: string;
    concentration_factor: string;
    inventory_skew_enabled: boolean;
    market_adaptation_enabled: boolean;
  };
  paper: {
    fee_enabled: boolean;
    maker_fee_bps: string;
    taker_fee_bps: string;
    funding_enabled: boolean;
    funding_interval_seconds: number;
    execution: Execution;
  };
  frames: number;
  scenario: string;
  stress: StressScenario | null;
};
export type Config = {
  contract_version: string;
  budget: PortfolioDraft["budget"];
  allocations: PortfolioDraft["allocations"];
  risk_limits: RiskLimits;
  scenarios: {
    market: Market;
    scenario: string;
    frames: number;
    captured: {
      canonical_json: string;
      fingerprint: string;
      market_profile_fingerprint: string;
      strategy_fingerprint: string;
      execution_fingerprint: string;
      accounting_fingerprint: string;
    };
  }[];
  simulated: true;
  execution_mode: "PAPER";
  read_only: true;
  authority: "NONE";
};
export type Preview = {
  contract_version: "phase175-preview-v1";
  config: Config;
  config_fingerprint: string;
  risk_policy: RiskPolicy;
  stress: StressScenario | null;
  allocated_quote: string;
  reserve_quote: string;
  allocation_percentages: Partial<Record<Market, string>>;
  workload: Record<string, number>;
  workload_limits?: Record<string, number>;
  trace_eligibility: "MODELED_ALIGNED" | "FINAL_ONLY";
  simulated: true;
  execution_mode: "PAPER";
  read_only: true;
  authority: "NONE";
};
export type TerminalRequest = {
  mode: Mode;
  config: Config;
  config_fingerprint: string;
  risk_policy: RiskPolicy;
  scenario?: StressScenario;
};
export type RiskReport = {
  evidence_fingerprint: string;
  outcome: "ASSESSED" | "BLOCKED";
  decision: Decision | null;
  reasons: string[];
  checks: {
    limit: keyof RiskLimits;
    observed: string | null;
    ceiling: string;
    state: Decision | "UNAVAILABLE";
  }[];
  operational_authority: "NONE";
  historical_orders_prevented: false;
  policy: RiskPolicy;
};
export type ChartPoint = {
  sequence: number;
  timestamp: string;
  equity_quote: string;
  pnl_quote: string;
  drawdown_fraction: string;
};
export type ChartEvidence = {
  status: "AVAILABLE" | "UNAVAILABLE";
  reason: string;
  source_count: number;
  sampled: boolean;
  methodology: string;
  analysis_fingerprint: string;
  accounting_fingerprint: string;
  temporal_fingerprint: string;
  native_evidence_fingerprints: string[];
  equity_series_fingerprint: string | null;
  evidence_fingerprint: string;
  points: ChartPoint[];
};
export type TerminalLeg = {
  status: "COMPLETED";
  analysis_fingerprint: string;
  bundle_fingerprint: string;
  temporal: {
    classification: TemporalClass;
    evidence_fingerprint: string;
    reasons: string[];
    historical_market_synchronization_verified: false;
    clocks: {
      market: Market;
      frames: number;
      complete: boolean;
      native_evidence_fingerprint: string;
      market_receipt_fingerprint: string;
    }[];
  };
  accounting: {
    status: "SUPPORTED" | "UNAVAILABLE";
    evidence_fingerprint: string;
    initial_capital_quote: string;
    allocated_capital_quote: string;
    reserve_quote: string;
    capital_allocation_utilization: string;
    equity_quote: string | null;
    pnl_quote: string | null;
    session_loss_quote: string | null;
    drawdown: {
      max_drawdown_fraction: string;
      equity_series_fingerprint: string;
    } | null;
  };
  exposure: {
    evidence_fingerprint: string;
    gross_exposure_quote: string | null;
    net_exposure_quote: string | null;
    max_inventory_concentration: string | null;
    gross_notional_utilization: string | null;
    modeled_leverage: string | null;
    reserved_capital_quote: string | null;
    reserved_capital_utilization: string | null;
    positions: {
      market: Market;
      position_base: string;
      mark_price_quote: string;
      signed_exposure_quote: string;
      gross_concentration: string | null;
    }[];
  };
  risk: RiskReport;
  charts: ChartEvidence;
  markets: {
    market: Market;
    market_profile_fingerprint: string;
    dataset_fingerprint: string;
    run_fingerprint: string;
    result_fingerprint: string;
    accounting_fingerprint: string;
    receipt_fingerprint: string;
    execution_assumptions: Execution;
  }[];
};
export type TerminalResult = {
  contract_version: "phase175-terminal-v1";
  mode: Mode;
  config_fingerprint: string;
  request_fingerprint: string;
  source_result_fingerprint: string;
  scenario_fingerprint: string | null;
  evidence_fingerprint: string;
  baseline: TerminalLeg;
  stressed: TerminalLeg | null;
  metrics: {
    temporal_classification: TemporalClass;
    comparisons: {
      metric: string;
      baseline: string | null;
      stressed: string | null;
      difference: string | null;
      status: "COMPARABLE" | "UNAVAILABLE";
    }[];
  } | null;
  risk_transition: {
    baseline_outcome: string;
    stressed_outcome: string;
    baseline_decision: Decision | null;
    stressed_decision: Decision | null;
    status: string;
    transition: string | null;
  } | null;
  limitations: string[];
  simulated: true;
  execution_mode: "PAPER";
  read_only: true;
  authority: "NONE";
};
export type FormDraft = Omit<
  PortfolioDraft,
  "frames" | "stress" | "strategy" | "paper"
> & {
  frames: string;
  strategy: Omit<PortfolioDraft["strategy"], "levels_per_side"> & {
    levels_per_side: string;
  };
  paper: Omit<PortfolioDraft["paper"], "execution"> & {
    execution: Omit<Execution, "order_latency_ms" | "cancel_latency_ms"> & {
      order_latency_ms: string;
      cancel_latency_ms: string;
    };
  };
  stressEnabled: boolean;
  stressKind: StressKind;
  onset: string;
  duration: string;
  recovery: StressScenario["recovery_profile"];
  stressFields: Record<string, string>;
  declines: Record<Market, string>;
  funding: Record<Market, string>;
};
