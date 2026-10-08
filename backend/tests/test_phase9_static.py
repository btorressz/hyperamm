from pathlib import Path
import re
import tomllib

ROOT=Path(__file__).resolve().parents[2]
AGENTS=ROOT/"backend"/"app"/"agents"


def test_agents_have_no_direct_execution_authority():
    forbidden=("submit_orders(","cancel_orders(","replace_orders(","Exchange.order(","cancel_by_cloid(")
    hits=[]
    for path in AGENTS.glob("*.py"):
        text=path.read_text()
        for token in forbidden:
            if token in text:hits.append((path.name,token))
    assert hits==[]


def test_phase9_has_no_llm_or_model_framework_dependency():
    pyproject=(ROOT/"backend"/"pyproject.toml").read_text().lower()
    for token in ("openai","anthropic","langchain","crewai","autogen","tensorflow","torch"):
        assert token not in pyproject


def test_ml_dependency_is_optional_and_training_has_no_execution_imports():
    project=tomllib.loads((ROOT/"backend"/"pyproject.toml").read_text())["project"]
    assert all("scikit-learn" not in d for d in project["dependencies"])
    assert any("scikit-learn" in d for d in project["optional-dependencies"]["ml"])
    for path in (ROOT/"backend"/"app"/"research"/"ml").glob("*.py"):
        text=path.read_text()
        for token in ("app.execution", "eth_account", "hyperliquid", "app.runtime", "app.risk", "app.accounting"):
            assert token not in text
    assert "research.ml.training" not in (ROOT/"backend"/"app"/"runtime.py").read_text()


def test_no_agent_execution_endpoint_exists():
    api=(ROOT/"backend"/"app"/"api"/"agents.py").read_text().lower()
    assert "@router.post" not in api
    for token in ("/agents/trade","/agents/execute","/agents/order"):
        assert token not in api


def test_phase9_does_not_create_github_actions_or_forbidden_oracle():
    assert not (ROOT/".github").exists()
    forbidden=re.compile(r"\bpyth\b",re.IGNORECASE)
    hits=[]
    for root in (ROOT/"backend"/"app",ROOT/"backend"/"tests",ROOT/"docs",ROOT/"README.md"):
        paths=[root] if root.is_file() else root.rglob("*")
        for path in paths:
            if not path.is_file() or path.resolve()==Path(__file__).resolve():continue
            if path.suffix.lower() not in {".py",".md",".txt",""}:continue
            try:text=path.read_text()
            except UnicodeDecodeError:continue
            if forbidden.search(text):hits.append(str(path.relative_to(ROOT)))
    assert hits==[]


def test_agent_package_contains_no_mainnet_or_secret_configuration():
    for path in AGENTS.glob("*.py"):
        text=path.read_text().lower()
        assert "mainnet" not in text
        for token in ("private_key","api_key","password","secret"):
            assert token not in text
