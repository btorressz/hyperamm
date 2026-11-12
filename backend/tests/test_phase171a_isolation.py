"""17.1A foundation remains pure when 17.2 orchestration is added."""
from pathlib import Path

from app.agents.config import AgentConfig
from app.portfolio_research.provenance import capture_portfolio_provenance
from app.risk.firewall import RiskFirewallConfig
from app.strategy.models import StrategyConfig
from phase171a_fixtures import config


def test_portfolio_contract_capture_cannot_mutate_operational_config():
    strategy=StrategyConfig()
    agents=AgentConfig()
    risk=RiskFirewallConfig()
    originals=(strategy.model_dump_json(), agents.model_dump_json(), risk.model_dump_json())
    p=config()
    r=capture_portfolio_provenance(p)
    assert (strategy.model_dump_json(), agents.model_dump_json(), risk.model_dump_json())==originals
    assert r.authority=="NONE"
    assert r.results_engine_attested is False


def test_portfolio_contract_package_does_not_own_runtime_or_api():
    root=Path(__file__).resolve().parents[1]/"app"/"portfolio_research"
    py=list(root.glob("*.py"))
    assert {p.name for p in py}=={
        "__init__.py","models.py","config.py","allocation.py","provenance.py",
        "orchestration.py", "service.py", "aggregation.py",
        "accounting.py", "exposure.py", "risk.py", "temporal.py"}
    combined="\n".join(p.read_text() for p in py)
    for forbidden in (
        "place_order(", "sign_transaction(", "send_order(", "app.state",
        "APIRouter(", "SimulationExecutor(", "SimulationEngine(", "create_task("
    ):
        assert forbidden not in combined
