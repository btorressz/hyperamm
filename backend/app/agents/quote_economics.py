"""Hypothetical economics of a selected Generalized PAPER quote cohort."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, localcontext
from typing import Annotated, Literal

from pydantic import Field

from app.accounting.config import bounded_exact_decimal
from app.accounting.fees import paper_fee
from app.accounting.funding import interval_boundary, paper_funding
from app.execution.models import Fill, StrategyOrder
from app.market_data.history import MarketPriceHistory
from app.market_data.market_universe_contracts import _utc
from app.market_data.perp_context import BPS
from app.risk.market_risk_contracts import RiskFinancialUnit
from app.risk.market_risk_engine import RISK_CONTEXT
from app.simulation.generalized_market_profiles import DECIMAL_CONTEXT, GeneralizedPaperResult
from app.simulation.references import build_simulated_references

from .advisory_contracts import AdvisoryContext, AdvisoryDecimal, AdvisoryEvidence, QuoteEconomicsAdvisory
from .advisory_evidence import AdvisoryBindingError, AdvisoryEvaluation, captured_paper_scenario, captured_source
from .evidence import AgentTelemetryStore
from .funding_basis import BPS_LIMIT, BPS_QUANTUM

ZERO = Decimal(0)
MAX_COHORT_ORDERS = 64
MAX_COHORT_FILLS = 1000


class QuoteCostAssumptions(AdvisoryEvidence):
    holding_seconds: int = Field(ge=1, le=604800)
    closing_liquidity: Literal["MAKER", "TAKER"]
    exit_slippage_bps: Annotated[AdvisoryDecimal, Field(ge=0, le=10000)]
    inventory_rate_bps: Annotated[AdvisoryDecimal, Field(ge=0, le=10000)]


@dataclass(frozen=True)
class QuoteEconomicsObservation:
    """A retained PAPER order cohort with explicit residual inventory assumptions."""

    paper: GeneralizedPaperResult
    quote_sequence: int
    assumptions: QuoteCostAssumptions
    captured_at: datetime
    valid_until: datetime

    def _checked(self):
        with localcontext(DECIMAL_CONTEXT):
            paper = GeneralizedPaperResult.model_validate(self.paper)
        assumptions = QuoteCostAssumptions.model_validate(self.assumptions)
        if type(self.quote_sequence) is not int or self.quote_sequence < 0:
            raise AdvisoryBindingError("invalid PAPER quote cohort")
        if _utc(self.captured_at) < paper.started_at or _utc(self.valid_until) <= _utc(self.captured_at):
            raise AdvisoryBindingError("invalid PAPER economics capture or expiry")
        return paper, assumptions

    def source_evidence(self):
        return self._sources(*self._checked())

    def _sources(self, paper, assumptions):
        metadata = paper.admission.profile.metadata
        unit = _paper_unit(metadata.identity.network)
        common = dict(metadata=metadata, captured_at=_utc(self.captured_at), valid_until=_utc(self.valid_until))
        trace = next((point for point in paper.result.trace if point.sequence == self.quote_sequence), None)
        if trace is None:
            return ()
        evidence = (paper.result_fingerprint, self.quote_sequence)
        cohort_sources = (
            ("QUOTE_LADDER", "PAPER_SUBMITTED_QUOTES"),
            ("PAPER_FILLS", "PAPER_EXECUTION_RECEIPTS"),
            ("FILL_MARKOUT", "PAPER_MATURE_MARKOUT"),
        )
        sources = [captured_source(
            **common, value=evidence, category=category, provenance="SCENARIO_SYNTHETIC",
            source_id=source_id, scenario_at=trace.timestamp, financial_unit=unit,
        ) for category, source_id in cohort_sources]
        sources.append(captured_source(
            **common, value=(evidence, paper.proposal.economics, assumptions.closing_liquidity,
                             assumptions.exit_slippage_bps),
            category="FEES", provenance="HYPOTHETICAL_ASSUMPTION", source_id="ASSUMPTION_PAPER_FEES",
            financial_unit=unit,
        ))
        sources.append(captured_source(
            **common, value=(evidence, assumptions.inventory_rate_bps, assumptions.holding_seconds),
            category="INVENTORY", provenance="HYPOTHETICAL_ASSUMPTION", source_id="ASSUMPTION_PAPER_INVENTORY",
            financial_unit=unit,
        ))
        if paper.proposal.economics.funding_interval_seconds is not None:
            sources.append(captured_source(
                **common, value=(evidence, paper.proposal.economics.funding_interval_seconds, assumptions.holding_seconds),
                category="FUNDING", provenance="SCENARIO_SYNTHETIC", source_id="PAPER_QUOTE_CARRY",
                scenario_at=trace.timestamp, unit="MARK_NOTIONAL_RATE_PER_PAPER_INTERVAL",
            ))
        if paper.research_risk is not None:
            sources.append(captured_source(
                **common, value=evidence, category="RISK_MODEL", provenance="SCENARIO_SYNTHETIC",
                source_id="PAPER_QUOTE_RISK", scenario_at=trace.timestamp,
                financial_unit=paper.admission.risk_model.margin_unit,
            ))
        return tuple(sources)


def _paper_unit(network):
    return RiskFinancialUnit(
        kind="HYPOTHETICAL_QUOTE", network=network, symbol="HYPOTHETICAL_QUOTE",
        provenance="RESEARCH_ASSUMPTION",
    )


class _EconomicsUnavailable(ValueError):
    def __init__(self, reason, requirement, *, status="INSUFFICIENT_DATA"):
        self.reason = reason
        self.requirement = requirement
        self.status = status


def _cohort(paper, trace):
    market = paper.admission.profile.market
    orders = {}
    for raw in paper.result.orders:
        if raw.get("created_at") is None:
            raise AdvisoryBindingError("PAPER order lacks its scenario time")
        created = raw["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if _utc(created) != trace.timestamp:
            continue
        for name in ("price", "size", "filled_size"):
            bounded_exact_decimal(raw.get(name))
        order = StrategyOrder.model_validate(raw)
        if (order.market != market or order.side not in {"BID", "ASK"}
                or order.client_order_id in orders):
            raise AdvisoryBindingError("inconsistent PAPER order cohort")
        orders[order.client_order_id] = order
    if len(orders) > MAX_COHORT_ORDERS:
        raise AdvisoryBindingError("PAPER order cohort exceeds capacity")
    if {order.side for order in orders.values()} != {"BID", "ASK"}:
        raise _EconomicsUnavailable("A two-sided submitted PAPER ladder is required for the spread baseline.",
                                    "TWO_SIDED_QUOTE_LADDER")
    fills = []
    sizes = defaultdict(Decimal)
    for raw in paper.result.fills:
        order = orders.get(raw.get("client_order_id"))
        if order is None:
            continue
        bounded_exact_decimal(raw.get("price"))
        bounded_exact_decimal(raw.get("size"))
        fill = Fill.model_validate(raw)
        if (fill.market != market or fill.side != order.side or fill.execution_mode != "PAPER"
                or _utc(fill.timestamp) < trace.timestamp or fill.size <= 0 or fill.price <= 0):
            raise AdvisoryBindingError("PAPER fill does not match its submitted quote")
        sizes[fill.client_order_id] += fill.size
        fills.append(fill)
    if len(fills) > MAX_COHORT_FILLS:
        raise AdvisoryBindingError("PAPER fill cohort exceeds capacity")
    if any(sizes[key] != order.filled_size or sizes[key] > order.size for key, order in orders.items()):
        raise AdvisoryBindingError("PAPER fill quantities do not reconcile with retained orders")
    if not fills:
        raise _EconomicsUnavailable("The selected PAPER quote cohort has no fills.", "PAPER_FILLS")
    return tuple(orders.values()), fills


def _references(prepared, frame):
    with localcontext(DECIMAL_CONTEXT):
        return build_simulated_references(
            frame, agreement_bps=prepared.risk.source_agreement_bps,
            outlier_bps=prepared.risk.source_outlier_bps, version=frame.sequence,
        )


def _captures(prepared, trace, fills):
    frames = prepared.dataset.frames
    by_time = {frame.timestamp: frame for frame in frames}
    quote_frame = by_time.get(trace.timestamp)
    if quote_frame is None or quote_frame.sequence != trace.sequence:
        raise AdvisoryBindingError("PAPER trace does not match the scenario dataset")
    quote_reference = _references(prepared, quote_frame).consensus.consensus_price
    if quote_reference is None:
        raise _EconomicsUnavailable("The quote frame has no accepted synthetic reference.", "QUOTE_REFERENCE")
    history = MarketPriceHistory()
    telemetry = AgentTelemetryStore(max_fills=MAX_COHORT_FILLS)
    for frame in frames:
        history.add_snapshot(frame.market)
    for fill in fills:
        frame = by_time.get(fill.timestamp)
        if frame is None:
            raise AdvisoryBindingError("PAPER fill falls outside the captured research frames")
        refs = _references(prepared, frame)
        if refs.consensus.consensus_price is None:
            raise _EconomicsUnavailable("A PAPER fill has no accepted synthetic reference.", "FILL_REFERENCE")
        if not telemetry.observe_fill_from_references(fill, refs):
            raise AdvisoryBindingError("duplicate PAPER fill in quote cohort")

    with localcontext(DECIMAL_CONTEXT):
        markouts, _ = telemetry.markouts(
            history, horizon_seconds=prepared.agents.toxic_flow_markout_horizon_seconds, window=len(fills),
        )
    if len(markouts) != len(fills):
        raise _EconomicsUnavailable("Each attributed PAPER fill requires a matured synthetic markout.", "MATURE_MARKOUTS")
    observations = {fill.identity: fill for fill in telemetry.fills(len(fills))}
    return quote_reference, observations, {row.fill_identity: row for row in markouts}, by_time[max(f.timestamp for f in fills)]


def _risk_evidence(paper, trace, unit):
    if trace.risk_state == "HALT":
        raise _EconomicsUnavailable("The existing Risk Firewall halted the selected PAPER frame.",
                                    "UNRETIRED_RESEARCH_QUOTES", status="UNSUPPORTED")
    if trace.desired_quote_count and not trace.authorized_quote_count:
        raise _EconomicsUnavailable("The selected PAPER quote frame was retired.",
                                    "UNRETIRED_RESEARCH_QUOTES", status="UNSUPPORTED")
    if paper.research_risk is None:
        return {}
    risk_frame = next((item for item in paper.research_risk.frames if item.sequence == trace.sequence), None)
    if risk_frame is None or risk_frame.state != trace.risk_state:
        raise AdvisoryBindingError("risk and quote trace frames disagree")
    snapshot = paper.research_risk.final_snapshot
    model = paper.admission.risk_model
    if snapshot is not None and (snapshot.exposure.base_instrument != paper.admission.identity
                                 or snapshot.exposure.quote_unit != unit or snapshot.margin.unit != model.margin_unit):
        raise AdvisoryBindingError("PAPER risk valuation has incompatible financial units")
    if risk_frame.state == "HALT" or risk_frame.margin_retired_quotes:
        raise _EconomicsUnavailable("The existing modeled margin policy retired the selected frame's quotes.",
                                    "UNRETIRED_RESEARCH_QUOTES", status="UNSUPPORTED")
    headroom = risk_frame.projected_headroom
    if headroom is None or headroom < 0:
        raise _EconomicsUnavailable("The selected frame lacks sufficient modeled margin headroom.",
                                    "MODELED_MARGIN_HEADROOM", status="UNSUPPORTED")
    return dict(projected_margin_headroom=headroom, margin_headroom_unit=model.margin_unit)


def _bps(amount: Decimal, denominator: Decimal, *, cost=False):
    return (amount * BPS / denominator).quantize(BPS_QUANTUM, rounding=ROUND_CEILING if cost else ROUND_FLOOR)


def _economics(paper, trace, options, interval, unit):
    risk_fields = _risk_evidence(paper, trace, unit)
    orders, fills = _cohort(paper, trace)
    if interval is None:
        raise _EconomicsUnavailable("An explicit PAPER funding schedule is required.", "PAPER_FUNDING_INTERVAL")
    prepared = captured_paper_scenario(paper)
    quote_reference, observations, markouts, carry_frame = _captures(prepared, trace, fills)
    bid = max(order.price for order in orders if order.side == "BID")
    ask = min(order.price for order in orders if order.side == "ASK")
    if ask <= bid:
        raise _EconomicsUnavailable("The selected PAPER quote cohort is crossed.", "UNCROSSED_PAPER_LADDER",
                                    status="UNSUPPORTED")

    reference_notional = defaultdict(Decimal)
    capture = defaultdict(Decimal)
    fees = adverse = residual_base = total_base = ZERO
    for fill in fills:
        key = AgentTelemetryStore.fill_identity(fill)
        reference = observations[key].reference_price
        exposure = fill.size * reference
        sign = 1 if fill.side == "BID" else -1
        fill_capture = sign * (reference - fill.price) * fill.size
        reference_notional[fill.side] += exposure
        capture[fill.side] += fill_capture
        fees += paper_fee(fill, key, prepared.simulation.accounting).fee_quote
        markout = markouts[key]
        # Charge the adverse move from fill-time reference. Spread capture already
        # includes the fill-to-reference move, so the two components disjointly sum.
        adverse += max(ZERO, sign * (reference - markout.future_reference_price) * fill.size)
        residual_base += sign * fill.size
        total_base += fill.size

    horizon = options.holding_seconds
    start = carry_frame.timestamp
    end = start + timedelta(seconds=horizon)
    elapsed = interval_boundary(end, interval) - interval_boundary(start, interval)
    intervals = (elapsed.days * 86400 + elapsed.seconds) // interval
    mark = carry_frame.perp_context.mark_price
    carry = paper_funding(
        market=carry_frame.market.market, effective_at=start, position=residual_base,
        mark=mark, rate=carry_frame.perp_context.funding_rate, evidence_version=carry_frame.sequence,
    )
    funding = -carry.funding_delta_quote * intervals
    close_reference = _references(prepared, carry_frame).consensus.consensus_price
    slippage = abs(residual_base) * close_reference * options.exit_slippage_bps / BPS
    if residual_base:
        # The residual exits at reference plus the explicitly assumed adverse
        # slippage, so the fee uses that exit's modeled execution notional.
        side = "ASK" if residual_base > 0 else "BID"
        price = close_reference * (1 - options.exit_slippage_bps / BPS if side == "ASK"
                                   else 1 + options.exit_slippage_bps / BPS)
        if price <= 0:
            raise _EconomicsUnavailable("The assumed residual close price is outside supported bounds.",
                                        "POSITIVE_MODELED_EXIT_PRICE", status="UNSUPPORTED")
        exit_fill = Fill(
            client_order_id="hypothetical-residual-close", market=carry_frame.market.market,
            side=side, price=price, size=abs(residual_base), timestamp=end, liquidity=options.closing_liquidity,
        )
        fees += paper_fee(exit_fill, exit_fill.client_order_id, prepared.simulation.accounting).fee_quote
    utilization = bounded_exact_decimal(paper.result.metrics.max_inventory_utilization)
    if utilization < 0:
        raise AdvisoryBindingError("invalid reported PAPER inventory utilization")
    carry_trace = next((point for point in paper.result.trace if point.sequence == carry_frame.sequence), None)
    if carry_trace is None or carry_trace.timestamp != start:
        raise _EconomicsUnavailable("The last attributed fill lacks retained inventory evidence.", "INVENTORY_TRACE")
    position = bounded_exact_decimal(carry_trace.inventory_base)
    inventory_expansion = max(ZERO, abs(position) - abs(position - residual_base))
    inventory = inventory_expansion * mark * utilization * options.inventory_rate_bps / BPS

    denominator = sum(reference_notional.values())
    gross = (ask - bid) * BPS / quote_reference
    captured = _bps(sum(capture.values()), denominator)
    components = tuple(_bps(amount, denominator, cost=True) for amount in (fees, funding, inventory, adverse, slippage))
    fee_bps, funding_bps, inventory_bps, adverse_bps, slippage_bps = components
    break_even = sum(components)
    edge = captured - break_even
    side_capture = {side: _bps(capture[side], base) for side, base in reference_notional.items()}
    if max(map(abs, (gross, edge, break_even, captured, *components, *side_capture.values()))) > BPS_LIMIT:
        raise _EconomicsUnavailable("Modeled spread or cost exceeds supported research bounds.",
                                    "BOUNDED_MODELED_COMPONENTS", status="UNSUPPORTED")

    return dict(
        accounting_unit=unit, gross_spread_bps=gross.quantize(BPS_QUANTUM, rounding=ROUND_FLOOR),
        captured_spread_bps=captured, fee_cost_bps=fee_bps, funding_cost_bps=funding_bps,
        inventory_cost_bps=inventory_bps, adverse_selection_cost_bps=adverse_bps,
        slippage_cost_bps=slippage_bps, break_even_capture_bps=break_even, modeled_edge_bps=edge,
        quoted_notional=sum(order.price * order.size for order in orders),
        executed_reference_notional=denominator, holding_seconds=horizon, funding_interval_seconds=interval,
        fill_coverage="BOTH_SIDES" if len(side_capture) == 2 else "ONE_SIDED",
        bid_capture_bps=side_capture.get("BID"), ask_capture_bps=side_capture.get("ASK"),
        residual_base=residual_base, filled_base=total_base, inventory_expansion_base=inventory_expansion,
        **risk_fields,
    ), len(fills)


class QuoteEconomicsAgent:
    def __init__(self, *, max_metadata_age_seconds: int = 60):
        self._metadata_age = max_metadata_age_seconds

    def evaluate(self, context: AdvisoryContext, observation: QuoteEconomicsObservation | None, *,
                 as_of: datetime) -> QuoteEconomicsAdvisory:
        evaluation = AdvisoryEvaluation(context, as_of=as_of, max_metadata_age_seconds=self._metadata_age)

        def unavailable(status, reason, *missing):
            return QuoteEconomicsAdvisory(
                **evaluation.fields(), status=status, reasons=(reason,), missing_requirements=missing,
            )

        if issue := evaluation.market_issue:
            return unavailable(*issue)
        if observation is None:
            return unavailable("INSUFFICIENT_DATA", "A PAPER quote cohort and modeled cost assumptions are required.",
                               "PAPER_QUOTE_COHORT", "COST_ASSUMPTIONS")
        if not isinstance(observation, QuoteEconomicsObservation):
            raise AdvisoryBindingError("quote economics requires a captured PAPER run")
        paper, assumptions = observation._checked()
        binding = paper.admission.binding
        context = evaluation.context
        if (paper.admission.profile.metadata != context.metadata or binding.catalog_fingerprint != context.catalog_fingerprint
                or binding.configuration_fingerprint != context.paper_binding_fingerprint
                or binding.research_risk_fingerprint != context.risk_model_fingerprint):
            raise AdvisoryBindingError("quote economics evidence does not match PAPER and risk context bindings")
        trace = next((item for item in paper.result.trace if item.sequence == observation.quote_sequence), None)
        if trace is None:
            return unavailable("INSUFFICIENT_DATA", "The selected quote frame was outside the retained PAPER trace.",
                               "RETAINED_PAPER_TRACE")
        sources = observation._sources(paper, assumptions)
        # Check all bindings even when incomplete. Publish sources only after
        # calculating which categories were used for a conclusion.
        if not evaluation.bind(sources, contribute=False):
            return unavailable("STALE", "The captured PAPER economics evidence has expired.")
        interval = paper.proposal.economics.funding_interval_seconds
        unit = _paper_unit(context.identity.network)
        try:
            with localcontext(RISK_CONTEXT):
                fields, count = _economics(paper, trace, assumptions, interval, unit)
                confidence = min(Decimal("0.75"), Decimal(count) / 10)
            evaluation.bind(sources)
            edge = fields["modeled_edge_bps"]
            state = "MODELED_POSITIVE" if edge > 0 else "MODELED_NEGATIVE" if edge < 0 else "MODELED_BREAKEVEN"
            return QuoteEconomicsAdvisory(
                **evaluation.fields(), **fields, status="READY", state=state, confidence=confidence,
                reasons=(
                    "Modeled edge uses attributed PAPER fills against their accepted synthetic references.",
                    "Residual carry holds the last attributed frame's rate and mark constant over scheduled boundaries.",
                    "Inventory expansion is charged at scenario peak utilization. Fill probabilities are unavailable.",
                ),
            )
        except _EconomicsUnavailable as exc:
            evaluation.bind(source for source in sources if source.category == "QUOTE_LADDER")
            return unavailable(exc.status, exc.reason, exc.requirement)
        except ArithmeticError:
            return unavailable("ERROR", "Modeled economics arithmetic exceeds supported bounds.", "BOUNDED_MODELED_COMPONENTS")
