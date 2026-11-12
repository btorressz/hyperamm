from decimal import Decimal

import pytest

from app.simulation import engine
from app.simulation.service import SimulationService
from phase172_fixtures import portfolio, request_for, standalone
from test_phase14_research_vault import authority, research_client


async def test_actual_run_local_state_and_full_outputs_match_independent_runs(monkeypatch):
    retained = {}
    for name in ("AccountingService", "PaperExecutionAdapter", "MarketPriceHistory", "AgentTelemetryStore",
                 "AgentSupervisor", "RiskFirewall", "OrderManager", "MetricsAccumulator", "QuoteEngine"):
        original = getattr(engine, name)
        retained[name] = []
        def build(*args, _original=original, _name=name, **kwargs):
            value = _original(*args, **kwargs)
            retained[_name].append(value)
            return value
        monkeypatch.setattr(engine, name, build)
    # Actual fills, pending cancellations, funding, risk and agent histories.
    from app.execution.research import PaperExecutionAssumptions
    from app.accounting.config import AccountingConfig
    overrides = {}
    for market, amount in (("BTC", "40000"), ("ETH", "35000"), ("SOL", "20000")):
        overrides[market] = {"simulation": {
            "accounting": AccountingConfig(paper_initial_equity_quote=amount,
                paper_funding_accounting_enabled=True, paper_funding_interval_seconds=1,
                paper_fee_model_enabled=True).model_dump(mode="json"),
            "execution": PaperExecutionAssumptions(mode="MODELED_CROSSING", cancel_latency_ms=2000,
                order_latency_ms=1000, participation_rate="0.5").model_dump(mode="json")}}
    p = portfolio(frames=40, scenario={"BTC": "FLASH_MOVE", "ETH": "TREND_DOWN", "SOL": "NEGATIVE_FUNDING_STRESS"},
                  overrides=overrides)
    service = SimulationService()
    results = []
    original = service.run_scenario
    async def observe(**kwargs):
        result = await original(**kwargs)
        results.append(result)
        return result
    monkeypatch.setattr(service, "run_scenario", observe)
    bundle = await service.run_portfolio_research(request=request_for(p))
    assert len(results) == 3
    for name, objects in retained.items():
        assert len(objects) == 3, name
        assert len({id(o) for o in objects}) == 3, name
    for index, scenario in enumerate(p.scenarios):
        raw = results[index].result
        independent = await standalone(SimulationService(), scenario)
        assert results[index] == independent  # every order/fill/trace/ledger/hash
        assert all(o["market"] == scenario.market for o in raw.orders)
        assert all(f["market"] == scenario.market for f in raw.fills)
        assert all(e.market == scenario.market for e in raw.accounting_ledger)
        assert raw.trace[0].inventory_base == 0
        assert raw.vault.initial_equity_quote == Decimal(("40000", "35000", "20000")[index])
    assert any(r.result.metrics.fill_count > 0 for r in results)
    assert any(r.result.vault.funding_quote != 0 for r in results)
    assert len({r.provenance.dataset_fingerprint for r in results}) == 3
    # Poison retained BTC state *after* completion; ETH and SOL objects/results
    # are independently owned, and the already projected bundle is detached.
    before = bundle.model_dump_json()
    retained["AccountingService"][0]._position = retained["AccountingService"][0].position.model_copy(
        update={"position_base": Decimal("999")})
    assert retained["AccountingService"][1].position.position_base != Decimal("999")
    assert bundle.model_dump_json() == before
    assert service.engine.__dict__ == {"network_access": False}


def test_real_endpoint_preserves_operational_authority_and_observers(research_client):
    client, rt = research_client
    rt.risk.kill_switch_active = True
    before = authority(rt)
    from copy import deepcopy
    observer = deepcopy(rt.market_history.__dict__)
    signing = (id(rt.testnet), id(rt.testnet.authority), rt.testnet.enabled,
               id(rt.settings), rt.settings.enable_hyperliquid_testnet_orders)
    listeners = tuple(rt.market._listeners)
    response = client.post("/api/v1/portfolio-research/run", json=request_for(portfolio(frames=16, scenario="FLASH_MOVE")).model_dump(mode="json"))
    assert response.status_code == 200, response.text
    assert authority(rt) == before
    assert rt.market_history.__dict__ == observer
    assert tuple(rt.market._listeners) == listeners
    assert signing == (id(rt.testnet), id(rt.testnet.authority), rt.testnet.enabled,
                       id(rt.settings), rt.settings.enable_hyperliquid_testnet_orders)
