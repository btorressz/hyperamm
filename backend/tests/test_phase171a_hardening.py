"""Native acceptance adversaries for the portfolio-only trust boundary."""
from decimal import Decimal, localcontext
from itertools import permutations

import pytest
from pydantic import ValidationError

from app.portfolio_research.allocation import allocation_totals
from app.portfolio_research.models import PortfolioResearchConfig, PortfolioResearchResult, PortfolioResearchScenario
from app.portfolio_research.provenance import PortfolioResearchProvenance, capture_portfolio_provenance
from app.research_replay.comparison import ComparisonConfigSnapshot
from app.simulation.config import SimulationConfig
from app.simulation.research_vault import ResearchVaultConfig
from phase171a_fixtures import config, market_scenario
from test_phase14_research_vault import authority, research_client


def replace_capture(p, **domains):
    payload = p.scenarios[0].captured.inputs().model_dump(mode="json")
    for domain, updates in domains.items():
        payload[domain].update(updates)
    raw = p.model_dump()
    raw["scenarios"] = (PortfolioResearchScenario(market="BTC", scenario="QUIET", frames=4,
        captured=ComparisonConfigSnapshot.from_payload(payload)), *p.scenarios[1:])
    return PortfolioResearchConfig.model_validate(raw)


@pytest.mark.parametrize("markets,amounts,total,reserve", [
    (("SOL",), ("20",), "20", "0"),
    (("ETH", "BTC"), ("35", "40"), "100", "25"),
    (("BTC", "ETH", "SOL"), ("40", "35", "25"), "100", "0"),
    (("BTC", "ETH"), ("999999999998.999999999999999999", "0.000000000000000001"),
     "999999999999.999999999999999999", "0.999999999999999999"),
])
def test_selected_markets_reconcile_under_low_ambient_precision(markets, amounts, total, reserve):
    p = config(markets=markets, amounts=amounts, total=total)
    with localcontext() as ctx:
        ctx.prec = 8
        allocated, remaining = allocation_totals(Decimal(total), zip(markets, map(Decimal, amounts)))
        assert allocated == p.allocated_equity_quote
        assert remaining == p.unallocated_reserve_quote == Decimal(reserve)


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_all_market_orders_preserve_config_and_receipt(order):
    p = config()
    raw = p.model_dump()
    raw["allocations"] = tuple(p.allocations[i] for i in order)
    raw["scenarios"] = tuple(p.scenarios[i] for i in reversed(order))
    q = PortfolioResearchConfig.model_validate(raw)
    assert p.canonical_payload() == q.canonical_payload()
    assert capture_portfolio_provenance(p).provenance_fingerprint == capture_portfolio_provenance(q).provenance_fingerprint


@pytest.mark.parametrize("amount", [True, False, 0.5, "NaN", "Infinity", "1e99999",
                                    "1.0000000000000000001", "1000000000001", "0", "-1"])
def test_public_reconciliation_rejects_unsafe_inputs(amount):
    with pytest.raises(ValueError):
        allocation_totals(amount, [("BTC", Decimal("1"))])
    with pytest.raises(ValueError):
        allocation_totals(Decimal("100"), [("BTC", amount)])


@pytest.mark.parametrize("field,updates", [
    ("budget", {"quote_currency": "USD"}),
    ("budget", {"minimum_reserve_quote": Decimal("-1")}),
    ("allocations", {"allocated_equity_quote": True}),
    ("allocations", {"unexpected_wallet": "forbidden"}),
    ("risk_limits", {"max_drawdown_fraction": Decimal("2")}),
    ("scenarios", {"source_authenticated": True}),
    ("scenarios", {"source_kind": "HISTORICAL"}),
    ("scenarios", {"frames": True}), ("scenarios", {"authority": "MAINNET"}),
])
def test_nested_model_copy_cannot_bypass_contract_fields(field, updates):
    p = config()
    raw = p.model_dump()
    value = getattr(p, field)
    raw[field] = ((value[0].model_copy(update=updates), *value[1:])
                  if isinstance(value, tuple) else value.model_copy(update=updates))
    with pytest.raises(ValidationError):
        PortfolioResearchConfig.model_validate(raw)


@pytest.mark.parametrize("updates", [{"execution_mode": "TESTNET"}, {"simulated": False},
                                      {"authority": "MAINNET"}, {"read_only": False}])
def test_forged_top_level_config_cannot_receive_receipt(updates):
    p = config().model_copy(update=updates)
    with pytest.raises(ValidationError):
        capture_portfolio_provenance(p)
    with pytest.raises(ValidationError):
        PortfolioResearchProvenance(config=p, **capture_portfolio_provenance(config()).model_dump(exclude={"config"}))
    with pytest.raises(ValidationError):
        p.fingerprint()


def test_receipt_verify_revalidates_itself_and_nested_capture():
    p = config()
    r = capture_portfolio_provenance(p)
    with pytest.raises(ValidationError):
        r.model_copy(update={"allocation_fingerprint": "0" * 64}).verify_config(p)
    s = p.scenarios[0]
    forged = s.captured.model_copy(update={"fingerprint": "0" * 64})
    with pytest.raises(ValidationError):
        PortfolioResearchScenario(market=s.market, scenario=s.scenario, frames=s.frames, captured=forged)
    invalid = p.model_copy(update={"scenarios": (s.model_copy(update={"captured": forged}), *p.scenarios[1:])})
    with pytest.raises(ValidationError):
        r.verify_config(invalid)


@pytest.mark.parametrize("frames", [True, 4.0, "4", 1, 5001])
def test_frames_are_strict_and_bounded(frames):
    raw = market_scenario("BTC", "40000").model_dump()
    raw["frames"] = frames
    with pytest.raises(ValidationError):
        PortfolioResearchScenario.model_validate(raw)


def test_market_substitution_duplicate_scenario_and_profile_forgery():
    p = config()
    raw = p.model_dump()
    raw["scenarios"] = (p.scenarios[1], p.scenarios[1], p.scenarios[2])
    with pytest.raises(ValidationError):
        PortfolioResearchConfig.model_validate(raw)
    raw = p.scenarios[0].model_dump()
    raw["captured"] = p.scenarios[1].captured
    with pytest.raises(ValidationError, match="market"):
        PortfolioResearchScenario.model_validate(raw)
    payload = p.scenarios[0].captured.inputs().model_dump(mode="json")
    payload["strategy"]["market"] = "SOL"
    with pytest.raises(ValueError, match="profile"):
        ComparisonConfigSnapshot.from_payload(payload)
    payload = p.scenarios[0].captured.inputs().model_dump(mode="json")
    payload["market_profile"]["profile_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        ComparisonConfigSnapshot.from_payload(payload)


@pytest.mark.parametrize("updates", [{"paper_initial_equity_quote": "39999"}, {"enabled": False}])
def test_accounting_capital_and_enabled_state_are_enforced(updates):
    p = config()
    simulation = p.scenarios[0].captured.inputs().simulation.model_dump(mode="json")
    simulation["accounting"].update(updates)
    with pytest.raises(ValidationError):
        replace_capture(p, simulation=simulation)


def test_utilization_cannot_exceed_portfolio_ceiling():
    p = config()
    with pytest.raises(ValidationError, match="utilization"):
        PortfolioResearchConfig.model_validate({**p.model_dump(), "risk_limits":
            p.risk_limits.model_copy(update={"max_capital_utilization": Decimal("0.9")})})


@pytest.mark.parametrize("domain,updates", [
    ("strategy", {"amm_model": "CONCENTRATED"}), ("agents", {"agents_enabled": False}),
    ("risk", {"max_session_loss_quote": "4999"}), ("simulation", {"record_trace": False}),
])
def test_material_inputs_change_identity(domain, updates):
    p = config()
    changed = replace_capture(p, **{domain: updates})
    assert changed.fingerprint() != p.fingerprint()
    with pytest.raises(ValueError, match="does not bind"):
        capture_portfolio_provenance(p).verify_config(changed)


def test_changed_profile_source_changes_identity():
    from app.simulation.market_profiles import ResearchPerpMarketMetadata, profile
    p = config()
    selected = p.scenarios[0].captured.inputs().market_profile
    metadata = {name: getattr(selected, name) for name in ResearchPerpMarketMetadata.model_fields}
    metadata["metadata_source"] = "ANOTHER_LOCAL_FIXTURE"
    changed = replace_capture(p, market_profile=profile(ResearchPerpMarketMetadata(**metadata)).model_dump(mode="json"))
    assert p.fingerprint() != changed.fingerprint()


@pytest.mark.parametrize("updates", [
    {"paper_fee_model_enabled": True}, {"paper_maker_fee_bps": "2"},
    {"paper_taker_fee_bps": "4"}, {"paper_funding_accounting_enabled": True},
    {"paper_funding_interval_seconds": 60}, {"max_capital_utilization": "0.75"},
])
def test_research_vault_assumptions_are_detached_and_change_identity(updates):
    p = config()
    vault = ResearchVaultConfig(initial_equity_quote="40000", **updates)
    controls = SimulationConfig(max_frames=4, trace_max_points=4)
    before = vault.model_dump_json(), controls.model_dump_json()
    simulation = vault.to_simulation(controls)
    changed = replace_capture(p, simulation=simulation.model_dump(mode="json"))
    assert changed.fingerprint() != p.fingerprint()
    assert (vault.model_dump_json(), controls.model_dump_json()) == before
    assert changed.scenarios[0].captured.inputs().simulation.accounting == simulation.accounting


def test_numeric_equivalence_in_captured_money_preserves_identity():
    a = config(markets=("BTC",), amounts=("40000",))
    b = config(markets=("BTC",), amounts=("40000.00",))
    b = replace_capture(b, risk={"max_session_loss_quote": "5000.000"})
    assert a.fingerprint() == b.fingerprint()
    assert capture_portfolio_provenance(a) == capture_portfolio_provenance(b)


@pytest.mark.parametrize("claim", [
    {"status": "COMPLETED"}, {"aggregate_equity_quote": "100000"},
    {"aggregate_pnl_quote": "1"}, {"synchronized_window_verified": True},
    {"execution_authority": "MAINNET"}, {"real_exchange_fills": []},
])
def test_result_cannot_claim_execution_or_synchronized_performance(claim):
    with pytest.raises(ValidationError):
        PortfolioResearchResult(config_fingerprint="a" * 64, **claim)


@pytest.mark.parametrize("field", ["config_fingerprint", "allocation_fingerprint",
                                    "provenance_fingerprint", "market_capture_fingerprints"])
def test_every_receipt_identity_is_verified(field):
    r = capture_portfolio_provenance(config())
    raw = r.model_dump(mode="json")
    raw[field] = ["0" * 64] * 3 if field == "market_capture_fingerprints" else "0" * 64
    with pytest.raises(ValidationError):
        PortfolioResearchProvenance.model_validate(raw)


def test_evidence_frozen_and_inputs_detached():
    p = config()
    r = capture_portfolio_provenance(p)
    original = p.model_dump_json()
    with pytest.raises(ValidationError):
        p.budget.quote_currency = "USD"
    with pytest.raises(ValidationError):
        p.scenarios[0].captured.canonical_json = "{}"
    inputs = p.scenarios[0].captured.inputs()
    inputs.strategy.market = "DOGE"
    inputs.agents.agents_enabled = False
    inputs.risk.enabled = False
    inputs.simulation.initial_equity_quote = Decimal("1")
    assert p.model_dump_json() == original
    r.verify_config(p)


def test_constructing_portfolio_preserves_real_runtime_authority(research_client, monkeypatch):
    _, runtime = research_client
    before = authority(runtime)
    def forbidden(*args, **kwargs):
        pytest.fail("portfolio contract attempted execution or wallet access")
    for adapter in (runtime.paper, runtime.testnet):
        for name in ("submit", "cancel", "replace", "get_account_state"):
            if hasattr(adapter, name):
                monkeypatch.setattr(adapter, name, forbidden)
    p = config()
    receipt = capture_portfolio_provenance(p)
    receipt.verify_config(p)
    assert authority(runtime) == before
