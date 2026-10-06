from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
SIM=ROOT/'backend'/'app'/'simulation'


def test_simulation_package_has_no_network_provider_or_private_key_access():
    forbidden=(
        'httpx','websockets','ReferenceService','app.references.providers',
        'HyperliquidTestnetExecutionAdapter','hyperliquid_private_key','api_key',
    )
    hits=[]
    for path in SIM.glob('*.py'):
        text=path.read_text()
        for token in forbidden:
            if token in text:
                hits.append((path.name,token))
    assert hits==[]


def test_simulation_package_has_no_external_optimizer_or_llm_imports():
    forbidden=(
        'numpy','pandas','scipy','sklearn','optuna','ray','torch','tensorflow',
        'openai','anthropic','gemini','langchain',
    )
    for path in SIM.glob('*.py'):
        lowered=path.read_text().lower()
        for token in forbidden:
            assert token not in lowered


def test_no_github_actions_or_forbidden_oracle_added():
    assert not (ROOT/'.github').exists()
    forbidden=re.compile(r'\\bpyth\\b',re.IGNORECASE)
    hits=[]
    for base in (ROOT/'backend'/'app',ROOT/'backend'/'tests',ROOT/'docs',ROOT/'README.md'):
        paths=[base] if base.is_file() else base.rglob('*')
        for path in paths:
            if not path.is_file() or path.resolve()==Path(__file__).resolve():
                continue
            if path.suffix.lower() not in {'.py','.md','.txt',''}:
                continue
            try:
                text=path.read_text()
            except UnicodeDecodeError:
                continue
            if forbidden.search(text):
                hits.append(str(path.relative_to(ROOT)))
    assert hits==[]


def test_simulation_frontend_has_no_auto_apply_or_deploy_action():
    text=(ROOT/'frontend'/'src'/'pages'/'Simulation.tsx').read_text().lower()
    for token in ('apply best','deploy strategy','trade best','activate optimized'):
        assert token not in text


def test_phase10_does_not_start_phase11_vault_work():
    for path in SIM.glob('*.py'):
        lowered=path.read_text().lower()
        for token in ('deposit','withdrawal','performance fee','investor shares','nav accounting'):
            assert token not in lowered


def test_readme_literal_backslash_n_defects_are_removed():
    text=(ROOT/'README.md').read_text()
    assert '\\n- **Phase 9' not in text
    assert 'RISK_FIREWALL.md`\\n-' not in text