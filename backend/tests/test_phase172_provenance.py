import pytest
from pydantic import ValidationError

from app.portfolio_research.models import PortfolioExecutedResult, PortfolioMarketExecution
from app.simulation.service import SimulationService
from phase172_fixtures import portfolio, request_for, standalone


@pytest.mark.parametrize("domain,updates", [
    ("strategy", {"replace_tolerance_bps": "1"}),
    ("agents", {"agents_enabled": False}),
    ("risk", {"enabled": False}),
])
async def test_configuration_and_execution_identity_change_together(domain, updates):
    service = SimulationService()
    one = await service.run_portfolio_research(request=request_for(portfolio(("BTC",))))
    two = await service.run_portfolio_research(request=request_for(portfolio(("BTC",), overrides={"BTC": {domain: updates}})))
    assert one.config_fingerprint != two.config_fingerprint
    assert one.markets[0].provenance.run_fingerprint != two.markets[0].provenance.run_fingerprint
    assert one.markets[0].provenance.result_fingerprint != two.markets[0].provenance.result_fingerprint


@pytest.mark.parametrize("domain", ["accounting", "execution"])
async def test_changed_fee_funding_or_execution_assumptions_are_retained(domain):
    from app.accounting.config import AccountingConfig
    from app.execution.research import PaperExecutionAssumptions
    value = (AccountingConfig(paper_initial_equity_quote="40000", paper_fee_model_enabled=True,
        paper_funding_accounting_enabled=True, paper_funding_interval_seconds=1) if domain == "accounting"
        else PaperExecutionAssumptions(mode="MODELED_CROSSING", slippage_bps="2", cancel_latency_ms=1000))
    p = portfolio(("BTC",), overrides={"BTC": {"simulation": {domain: value.model_dump(mode="json")}}})
    one = await SimulationService().run_portfolio_research(request=request_for(portfolio(("BTC",))))
    two = await SimulationService().run_portfolio_research(request=request_for(p))
    assert two.markets[0].provenance.captured == p.scenarios[0].captured
    assert one.markets[0].provenance.run_fingerprint != two.markets[0].provenance.run_fingerprint
    assert one.markets[0].provenance.result_fingerprint != two.markets[0].provenance.result_fingerprint


@pytest.mark.parametrize("kind", ["metric", "market", "source", "result_hash", "run_hash", "accounting",
    "capture", "incomplete", "duplicate", "reserve", "authority", "aggregate", "limitations"])
async def test_independent_wire_validation_rejects_tampered_bundle(kind):
    result = await SimulationService().run_portfolio_research(request=request_for())
    raw = result.model_dump(mode="json")
    r = raw["markets"][0]
    if kind == "metric": r["metrics"]["session_pnl"] = "999"
    elif kind == "market": r["market"] = "ETH"
    elif kind == "source": r["market_assumptions"] = raw["markets"][1]["market_assumptions"]
    elif kind == "result_hash": r["provenance"]["result_fingerprint"] = "a" * 64
    elif kind == "run_hash": r["provenance"]["run_fingerprint"] = "a" * 64
    elif kind == "accounting": r["vault"]["initial_equity_quote"] = "35000"
    elif kind == "capture": r["provenance"]["captured"] = raw["markets"][1]["provenance"]["captured"]
    elif kind == "incomplete": raw["markets"].pop()
    elif kind == "duplicate": raw["markets"][0] = raw["markets"][1]
    elif kind == "reserve": raw["unallocated_reserve_quote"] = "5001"
    elif kind == "authority": raw["authority"] = "MAINNET"
    elif kind == "aggregate": raw["portfolio_pnl"] = "10"
    else: raw["limitations"] = []
    with pytest.raises(ValidationError):
        PortfolioExecutedResult.model_validate(raw)


async def test_valid_eth_evidence_cannot_replace_btc_even_with_standalone_hash():
    p = portfolio()
    captured = await standalone(SimulationService(), p.scenarios[1])
    with pytest.raises(ValueError, match="market|capture"):
        PortfolioMarketExecution(config_fingerprint=p.fingerprint(), scenario=p.scenarios[0], captured_result=captured)


async def test_native_result_mutation_is_detected_before_projection():
    p = portfolio(("BTC",), frames=16, scenario="FLASH_MOVE")
    captured = await standalone(SimulationService(), p.scenarios[0])
    captured.result.metrics.session_pnl += 1
    with pytest.raises(ValueError, match="provenance"):
        PortfolioMarketExecution(config_fingerprint=p.fingerprint(), scenario=p.scenarios[0], captured_result=captured)


async def test_forged_nested_models_and_incomplete_copies_are_revalidated():
    result = await SimulationService().run_portfolio_research(request=request_for())
    with pytest.raises(ValueError):
        PortfolioExecutedResult.model_validate(result.model_copy(update={"markets": result.markets[:1]}))
    receipt = result.markets[0].model_copy(update={"provenance": result.markets[0].provenance.model_copy(
        update={"result_fingerprint": "0" * 64})})
    with pytest.raises(ValueError):
        PortfolioExecutedResult.model_validate(result.model_copy(update={"markets": (receipt, *result.markets[1:])}))
