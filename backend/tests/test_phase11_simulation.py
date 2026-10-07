from decimal import Decimal as D

import pytest

from app.accounting import AccountingService
from app.agents import AgentConfig
from app.risk.firewall import RiskFirewallConfig
from app.simulation.config import SimulationConfig
from app.simulation.engine import SimulationEngine
from app.simulation.scenarios import generate_scenario
from app.strategy.models import StrategyConfig
from app.accounting.config import AccountingConfig


@pytest.mark.asyncio
async def test_shared_engine_replay_includes_identical_vault_ledger_and_fingerprint(monkeypatch):
    calls = []
    original = AccountingService.mark
    def mark(self, value, **kwargs):
        calls.append((value, kwargs["observed_at"]))
        return original(self, value, **kwargs)
    monkeypatch.setattr(AccountingService, "mark", mark)
    dataset = generate_scenario("FLASH_MOVE", frames=30)
    kwargs = dict(dataset=dataset, strategy_config=StrategyConfig(), agent_config=AgentConfig(),
                  risk_config=RiskFirewallConfig(), simulation_config=SimulationConfig(max_frames=30,
                  accounting=AccountingConfig(paper_fee_model_enabled=True)))
    a = await SimulationEngine().run(**kwargs)
    b = await SimulationEngine().run(**kwargs)
    assert len(calls) == 120
    assert a.vault == b.vault
    assert a.accounting_ledger == b.accounting_ledger
    assert a.accounting_fingerprint == b.accounting_fingerprint
    assert a.vault.updated_at == dataset.frames[-1].timestamp
    assert a.vault.simulated
    assert a.metrics.session_pnl == a.vault.net_pnl_quote
    assert a.metrics.ending_equity == a.vault.equity_quote
    assert a.metrics.realized_pnl == a.vault.realized_pnl_quote
    assert a.metrics.unrealized_pnl == a.vault.unrealized_pnl_quote


@pytest.mark.asyncio
async def test_configured_simulation_fees_funding_are_provenance_bound():
    dataset = generate_scenario("TREND_DOWN", frames=30)
    base = dict(dataset=dataset, strategy_config=StrategyConfig(), agent_config=AgentConfig(),
                risk_config=RiskFirewallConfig())
    a = await SimulationEngine().run(**base, simulation_config=SimulationConfig(max_frames=30))
    b = await SimulationEngine().run(**base, simulation_config=SimulationConfig(max_frames=30,
             accounting=AccountingConfig(paper_fee_model_enabled=True, paper_funding_accounting_enabled=True,
                                          paper_funding_interval_seconds=1)))
    assert a.run_fingerprint != b.run_fingerprint
    assert a.accounting_fingerprint != b.accounting_fingerprint
    assert a.vault.fees_quote == 0
    assert any(entry.event_type == "FUNDING" for entry in b.accounting_ledger)
    assert all(entry.simulated for entry in b.accounting_ledger)
    assert b.vault.equity_quote == D("100000") + b.vault.net_pnl_quote


@pytest.mark.asyncio
async def test_simulation_capital_authority_halts_insufficient_research_capital():
    result = await SimulationEngine().run(dataset=generate_scenario("QUIET", frames=3),
                strategy_config=StrategyConfig(), agent_config=AgentConfig(), risk_config=RiskFirewallConfig(),
                simulation_config=SimulationConfig(max_frames=3, initial_equity_quote=D("1")))
    assert result.metrics.risk_state_counts == {"HALT": 3}
    assert result.orders == []
