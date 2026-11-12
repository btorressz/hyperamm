"""Bounded result bundling only; no cross-market economic calculations."""
from app.simulation.models import stable_fingerprint
from app.execution.research import PaperExecutionAssumptions
from .config import MAX_RESPONSE_BYTES, PortfolioResponseTooLarge
from .models import (
    PortfolioMarketExecution, PortfolioMarketReceipt, PortfolioExecutedResult,
    fingerprinted,
)


def project_market(execution: PortfolioMarketExecution) -> PortfolioMarketReceipt:
    execution = PortfolioMarketExecution.model_validate(execution)
    result = execution.captured_result.result
    return fingerprinted(PortfolioMarketReceipt,
        config_fingerprint=execution.config_fingerprint, market=execution.scenario.market,
        provenance=execution.captured_result.provenance, metrics=result.metrics,
        vault=result.vault, market_assumptions=result.research_assumptions,
        execution_assumptions=PaperExecutionAssumptions.model_validate(result.execution_assumptions),
        accounting_fingerprint=result.accounting_fingerprint,
        retained_ledger_fingerprint=stable_fingerprint(result.accounting_ledger),
        retained_ledger_entries=len(result.accounting_ledger), original_trace_points=len(result.trace))


def assemble_bundle(config, markets) -> PortfolioExecutedResult:
    bundle = fingerprinted(PortfolioExecutedResult,
        config=config, config_fingerprint=config.fingerprint(),
        selected_markets=tuple(r.market for r in markets), markets=tuple(markets),
        unallocated_reserve_quote=config.unallocated_reserve_quote)
    # Serialize in the worker too: failures/oversize cannot escape as a successful
    # admitted computation or be mirrored as completed by Redis coordination.
    bounded_json(bundle)
    return bundle


def bounded_json(bundle) -> str:
    wire = bundle.model_dump_json()
    if len(wire.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise PortfolioResponseTooLarge("portfolio response exceeds transport budget")
    return wire
