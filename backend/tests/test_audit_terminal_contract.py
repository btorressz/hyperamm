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
