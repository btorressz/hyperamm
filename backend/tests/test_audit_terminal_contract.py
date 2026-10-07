"""A1-012: generated wire schema stays derived from the backend contract."""
import importlib.util
import json
from pathlib import Path
from app.terminal.models import TerminalSnapshot

ROOT = Path(__file__).resolve().parents[2]


def test_generated_terminal_schema_is_current():
    spec = importlib.util.spec_from_file_location('contract_generator', ROOT/'backend/scripts/generate_terminal_contract.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.build_contract() == json.loads((ROOT/'frontend/src/contracts/terminal.schema.json').read_text())


def test_frontend_valid_fixtures_match_backend_contract():
    for name in ('terminal-valid.json', 'terminal-unavailable.json'):
        TerminalSnapshot.model_validate_json((ROOT/'frontend/tests/fixtures'/name).read_text())


def test_runtime_agent_telemetry_matches_generated_schema_and_fixtures():
    from app.config import Settings
    from app.runtime import HyperAmmRuntime

    schema = json.loads((ROOT/'frontend/src/contracts/terminal.schema.json').read_text())
    telemetry = schema['properties']['agents']['properties']['telemetry']
    assert telemetry['additionalProperties'] is False
    for mode, name in (('PAPER', 'terminal-valid.json'), ('TESTNET', 'terminal-unavailable.json')):
        rt = HyperAmmRuntime(Settings(_env_file=None, execution_mode=mode))
        actual = rt.agents_payload()['telemetry']
        assert set(actual) == set(telemetry['properties']) == set(telemetry['required'])
        fixture = json.loads((ROOT/'frontend/tests/fixtures'/name).read_text())
        assert set(fixture['agents']['telemetry']) == set(actual)
